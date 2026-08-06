import argparse
import json
from datetime import datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.importers.dataset_importer import import_dataset
from app.models.entities import Certification, Domain
from sqlalchemy import select


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def load_dataset_metadata(db, directory: Path) -> None:
    """Load certification/domain reference rows before streaming questions."""
    certifications_path = directory / "certifications.json"
    domains_path = directory / "domains.json"
    if not certifications_path.is_file() or not domains_path.is_file():
        raise ValueError("dataset directory must contain certifications.json and domains.json")

    certifications = json.loads(certifications_path.read_text(encoding="utf-8-sig"))
    domains = json.loads(domains_path.read_text(encoding="utf-8-sig"))
    for item in certifications:
        code = item["certification_code"]
        certification = db.scalar(
            select(Certification).where(Certification.certification_code == code)
        )
        if certification is None:
            certification = Certification(certification_code=code)
            db.add(certification)
        for field in (
            "name_en", "name_ko", "exam_version", "default_question_count",
            "default_duration_minutes", "passing_score", "score_type",
            "official_reference_url", "is_active",
        ):
            if field in item:
                setattr(certification, field, item[field])
        certification.official_verified_at = _parse_datetime(item.get("official_verified_at"))
    db.flush()

    for item in domains:
        certification = db.scalar(
            select(Certification).where(
                Certification.certification_code == item["certification_code"]
            )
        )
        if certification is None:
            raise ValueError(f"unknown certification: {item['certification_code']}")
        domain = db.scalar(
            select(Domain).where(
                Domain.certification_id == certification.id,
                Domain.domain_code == item["domain_code"],
            )
        )
        if domain is None:
            domain = Domain(
                certification_id=certification.id,
                domain_code=item["domain_code"],
            )
            db.add(domain)
        for field in ("name_en", "name_ko", "exam_weight", "sort_order", "is_active"):
            if field in item:
                setattr(domain, field, item[field])
    db.flush()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-dataset", help="Validate or import a dataset JSONL stream")
    importer.add_argument("--path", required=True, type=Path)
    importer.add_argument("--mode", choices=["dry-run", "strict", "partial"], default="dry-run")
    args = parser.parse_args()
    path: Path = args.path.resolve()
    if not path.is_dir():
        raise SystemExit("--path must point to a dataset package directory")
    with SessionLocal() as db:
        result = import_dataset(db, path, args.mode)
    print(
        f"total={result.total} added={result.added} updated={result.updated} "
        f"unchanged={result.unchanged} excluded={result.excluded} failed={result.failed}"
    )
    for error in result.errors:
        print(error)
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
