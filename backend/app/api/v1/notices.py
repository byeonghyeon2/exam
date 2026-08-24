from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import current_user, require_admin, session_identity
from app.db.base import utcnow
from app.db.session import get_db
from app.models.entities import AppSetting, Notice, User
from app.schemas.api import NoticeOut, NoticeWrite
from app.services.maintenance import (
    active_maintenance,
    enforce_active_maintenance,
    finalize_user_for_maintenance,
)

Db = Annotated[Session, Depends(get_db)]

public_notices = APIRouter()
admin_notices = APIRouter(prefix="/admin/notices", dependencies=[Depends(require_admin)])


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_maintenance_overlap(db: Session, payload: NoticeWrite, exclude_id: int | None = None) -> None:
    if payload.notice_type != "maintenance" or not payload.maintenance_screen_enabled:
        return
    # The migration creates this sentinel row. Locking it serializes competing
    # maintenance writes so two simultaneous requests cannot both pass validation.
    lock = db.scalar(select(AppSetting).where(AppSetting.key == "maintenance_schedule_lock").with_for_update())
    if lock is None:
        lock = AppSetting(key="maintenance_schedule_lock", value_json={"version": 1})
        db.add(lock)
        db.flush()
    assert payload.maintenance_start_at is not None and payload.maintenance_end_at is not None
    candidates = db.scalars(select(Notice).where(
        Notice.notice_type == "maintenance", Notice.maintenance_screen_enabled.is_(True)
    ))
    start, end = _aware(payload.maintenance_start_at), _aware(payload.maintenance_end_at)
    for item in candidates:
        if item.id == exclude_id or item.maintenance_start_at is None or item.maintenance_end_at is None:
            continue
        if start < _aware(item.maintenance_end_at) and _aware(item.maintenance_start_at) < end:
            raise HTTPException(status.HTTP_409_CONFLICT, "점검 화면 기간은 다른 점검 공지와 겹칠 수 없습니다")


def _apply(item: Notice, payload: NoticeWrite) -> Notice:
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    return item


@public_notices.get("/notices/active")
def active_notices(_user: Annotated[User, Depends(current_user)], db: Db) -> dict[str, object]:
    now = utcnow()
    notices = list(db.scalars(select(Notice).where(Notice.is_published.is_(True)).order_by(Notice.display_start_at, Notice.id)))
    visible = [notice for notice in notices if _aware(notice.display_start_at) <= now < _aware(notice.display_end_at)]
    maintenance = active_maintenance(db, now)
    upcoming = db.scalar(select(Notice).where(
        Notice.notice_type == "maintenance", Notice.is_published.is_(True),
        Notice.maintenance_screen_enabled.is_(True), Notice.maintenance_start_at > now,
    ).order_by(Notice.maintenance_start_at))
    return {"notices": [NoticeOut.model_validate(item) for item in visible], "maintenance": NoticeOut.model_validate(maintenance) if maintenance else None, "upcoming_maintenance": NoticeOut.model_validate(upcoming) if upcoming else None, "server_time": now.isoformat()}


@public_notices.get("/system/status")
def system_status(db: Db) -> dict[str, object]:
    now = utcnow()
    item = active_maintenance(db, now)
    if item is not None:
        item = enforce_active_maintenance(db, now)
    upcoming = db.scalar(select(Notice).where(
        Notice.notice_type == "maintenance", Notice.is_published.is_(True),
        Notice.maintenance_screen_enabled.is_(True), Notice.maintenance_start_at > now,
    ).order_by(Notice.maintenance_start_at))
    return {"maintenance_active": item is not None, "maintenance": NoticeOut.model_validate(item) if item else None, "upcoming_maintenance": NoticeOut.model_validate(upcoming) if upcoming else None, "server_time": now.isoformat()}


@public_notices.post("/maintenance/finalize-current-user", status_code=204)
def finalize_current_user_for_maintenance(
    identity: Annotated[tuple[object, User] | None, Depends(session_identity)], db: Db
) -> None:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    _session, user = identity
    if user.role == "admin":
        return
    if active_maintenance(db) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "현재 점검 시간이 아닙니다")
    finalize_user_for_maintenance(db, user.id)
    db.commit()


@admin_notices.get("", response_model=list[NoticeOut])
def list_notices(db: Db) -> list[Notice]:
    return list(db.scalars(select(Notice).order_by(Notice.display_start_at.desc(), Notice.id.desc())))


@admin_notices.post("", response_model=NoticeOut, status_code=201)
def create_notice(payload: NoticeWrite, db: Db) -> Notice:
    _validate_maintenance_overlap(db, payload)
    item = _apply(Notice(), payload)
    db.add(item); db.commit(); db.refresh(item)
    return item


@admin_notices.patch("/{notice_id}", response_model=NoticeOut)
def update_notice(notice_id: int, payload: NoticeWrite, db: Db) -> Notice:
    item = db.scalar(select(Notice).where(Notice.id == notice_id).with_for_update())
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "공지를 찾을 수 없습니다")
    if item.maintenance_started_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "이미 실행된 점검 공지는 수정할 수 없습니다. 새 공지를 등록해주세요",
        )
    _validate_maintenance_overlap(db, payload, exclude_id=notice_id)
    _apply(item, payload); item.revision += 1; db.commit(); db.refresh(item)
    return item


@admin_notices.delete("/{notice_id}", status_code=204)
def delete_notice(notice_id: int, db: Db) -> None:
    item = db.scalar(select(Notice).where(Notice.id == notice_id).with_for_update())
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "공지를 찾을 수 없습니다")
    now = utcnow()
    if (
        item.notice_type == "maintenance"
        and item.maintenance_start_at is not None
        and item.maintenance_end_at is not None
        and _aware(item.maintenance_start_at) <= now < _aware(item.maintenance_end_at)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "진행 중인 점검 공지는 삭제할 수 없습니다")
    db.delete(item); db.commit()
