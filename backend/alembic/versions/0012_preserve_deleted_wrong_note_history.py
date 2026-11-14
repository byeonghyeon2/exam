"""Keep deleted wrong-note sessions out of the list without losing analysis history."""

import sqlalchemy as sa

from alembic import op


revision = "0012_wrongnote_history"
down_revision = "0011_ai_concept_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("exam_study_sessions")}
    if "wrong_note_hidden_at" not in columns:
        op.add_column("exam_study_sessions", sa.Column("wrong_note_hidden_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_exam_study_sessions_wrong_note_hidden_at", "exam_study_sessions", ["wrong_note_hidden_at"])


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("exam_study_sessions")}
    if "wrong_note_hidden_at" in columns:
        op.drop_index("ix_exam_study_sessions_wrong_note_hidden_at", table_name="exam_study_sessions")
        op.drop_column("exam_study_sessions", "wrong_note_hidden_at")
