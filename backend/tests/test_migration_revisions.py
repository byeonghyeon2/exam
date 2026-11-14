from pathlib import Path
import runpy


VERSIONS = Path(__file__).parents[1] / "alembic" / "versions"


def test_migration_revisions_fit_alembic_version_column() -> None:
    revisions = [runpy.run_path(path) for path in VERSIONS.glob("*.py")]

    assert all(len(item["revision"]) <= 32 for item in revisions)
    assert all(
        item.get("down_revision") is None
        or (isinstance(item["down_revision"], str) and len(item["down_revision"]) <= 32)
        for item in revisions
    )
