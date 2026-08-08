"""Track study attempts processed into wrong notes.

Wrong notes are now updated once when a completed study session is finalized,
instead of once per submitted answer. The flag makes finalization idempotent.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_batch_study_wrong_notes"
down_revision = "0002_aws_domain_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("study_attempts")}
    indexes = {index["name"] for index in inspector.get_indexes("study_attempts")}
    with op.batch_alter_table("study_attempts") as batch:
        if "wrong_note_processed" not in columns:
            batch.add_column(
                sa.Column(
                    "wrong_note_processed",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        if "ix_study_attempts_wrong_note_processed" not in indexes:
            batch.create_index(
                "ix_study_attempts_wrong_note_processed",
                ["wrong_note_processed"],
            )


def downgrade() -> None:
    with op.batch_alter_table("study_attempts") as batch:
        batch.drop_index("ix_study_attempts_wrong_note_processed")
        batch.drop_column("wrong_note_processed")
