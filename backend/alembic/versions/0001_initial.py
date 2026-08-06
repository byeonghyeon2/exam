"""Initial normalized exam schema.

The model metadata is the single schema source. This bootstrap migration creates
all named constraints and indexes declared there; subsequent changes use explicit
Alembic operations and never mutate production tables through create_all.
"""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)

