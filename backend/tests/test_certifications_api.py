from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import Certification


def test_certification_list_returns_every_active_certification() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        for code, active in (("DEA-C01", True), ("SAA-C03", True), ("OLD-C01", False)):
            db.add(
                Certification(
                    certification_code=code,
                    name_en=code,
                    name_ko=code,
                    exam_version=code,
                    default_question_count=10,
                    default_duration_minutes=30,
                    passing_score=70,
                    is_active=active,
                )
            )
        db.commit()

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/certifications")
            assert response.status_code == 200
            assert [item["code"] for item in response.json()] == ["DEA-C01", "SAA-C03"]
            assert client.get("/api/v1/certifications/SAA-C03").status_code == 200
            assert client.get("/api/v1/certifications/OLD-C01").status_code == 404
    finally:
        app.dependency_overrides.clear()
