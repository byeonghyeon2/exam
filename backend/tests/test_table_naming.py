from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.db.base import Base


def test_all_application_tables_use_exam_prefix() -> None:
    import app.models  # noqa: F401

    assert Base.metadata.tables
    assert all(name.startswith("exam_") for name in Base.metadata.tables)


def test_prefix_migration_covers_every_application_table() -> None:
    path = Path(__file__).parents[1] / "alembic/versions/0008_prefix_application_tables.py"
    spec = spec_from_file_location("prefix_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert {f"exam_{name}" for name in migration.APPLICATION_TABLES} == set(Base.metadata.tables)
