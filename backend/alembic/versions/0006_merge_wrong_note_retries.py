"""Link retry sessions to their original wrong-note study group."""

import sqlalchemy as sa
from alembic import op

revision = "0006_merge_wrong_note_retries"
down_revision = "0005_user_owned_learning_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("study_sessions") as batch:
        batch.add_column(sa.Column("retry_of_session_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_study_sessions_retry_of_session_id", ["retry_of_session_id"])


def downgrade() -> None:
    with op.batch_alter_table("study_sessions") as batch:
        batch.drop_index("ix_study_sessions_retry_of_session_id")
        batch.drop_column("retry_of_session_id")
