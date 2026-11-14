"""Persist administrator-facing audit reasons for question corrections and holds."""

import sqlalchemy as sa

from alembic import op

revision = "0013_question_reviews"
down_revision = "0012_wrongnote_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "exam_question_review_audits" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "exam_question_review_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("exam_questions.id"), nullable=False),
        sa.Column("audit_batch", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("audit_status", sa.String(length=32), nullable=False),
        sa.Column("issue_summary", sa.Text(), nullable=False),
        sa.Column("correction_summary", sa.Text(), nullable=False),
        sa.Column("source_pdf_page", sa.Integer()),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("proposed_answers", sa.JSON(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("question_id", "audit_batch"),
    )
    op.create_index("ix_exam_question_review_audits_question_id", "exam_question_review_audits", ["question_id"])
    op.create_index("ix_exam_question_review_audits_audit_batch", "exam_question_review_audits", ["audit_batch"])
    op.create_index("ix_question_review_audit_status", "exam_question_review_audits", ["audit_status"])


def downgrade() -> None:
    if "exam_question_review_audits" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("exam_question_review_audits")
