from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.db.base import Base


def test_all_application_tables_use_exam_prefix() -> None:
    import app.models  # noqa: F401

    assert Base.metadata.tables
    assert all(name.startswith("exam_") for name in Base.metadata.tables)


def test_migrations_cover_every_application_table() -> None:
    path = Path(__file__).parents[1] / "alembic/versions/0008_prefix_application_tables.py"
    spec = spec_from_file_location("prefix_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    migrated_tables = {f"exam_{name}" for name in migration.APPLICATION_TABLES}
    challenge_migration = Path(__file__).parents[1] / "alembic/versions/0009_passkey_challenges.py"
    assert '"exam_passkey_challenges"' in challenge_migration.read_text(encoding="utf-8")
    migrated_tables.add("exam_passkey_challenges")
    assert migrated_tables == set(Base.metadata.tables)
