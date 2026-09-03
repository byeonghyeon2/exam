"""Store the latest AI concept summary for each learner and certification."""

import sqlalchemy as sa

from alembic import op


revision = "0011_ai_concept_summaries"
down_revision = "0010_notices_and_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "exam_ai_concept_summaries" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "exam_ai_concept_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("exam_users.id"), nullable=False),
        sa.Column("certification_id", sa.Integer(), sa.ForeignKey("exam_certifications.id"), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("normal_session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_name", sa.String(128)),
        sa.UniqueConstraint("user_id", "certification_id", name="uq_ai_concept_summary_user_certification"),
    )
    op.create_index("ix_exam_ai_concept_summaries_user_id", "exam_ai_concept_summaries", ["user_id"])
    op.create_index("ix_exam_ai_concept_summaries_certification_id", "exam_ai_concept_summaries", ["certification_id"])


def downgrade() -> None:
    if "exam_ai_concept_summaries" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("exam_ai_concept_summaries")
