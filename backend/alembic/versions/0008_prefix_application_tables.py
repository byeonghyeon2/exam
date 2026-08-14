"""Prefix all application-owned tables with exam_."""

import sqlalchemy as sa

from alembic import op

revision = "0008_prefix_application_tables"
down_revision = "0007_passkey_authentication"
branch_labels = None
depends_on = None

APPLICATION_TABLES = (
    "certifications",
    "domains",
    "questions",
    "question_choices",
    "question_answer_versions",
    "question_explanations",
    "study_sessions",
    "study_attempts",
    "mock_exams",
    "mock_exam_questions",
    "wrong_notes",
    "question_reports",
    "app_settings",
    "ai_usage_logs",
    "import_jobs",
    "import_job_errors",
    "users",
    "auth_sessions",
    "passkey_credentials",
)


def _rename_tables(source_prefix: str, target_prefix: str) -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for base_name in APPLICATION_TABLES:
        source = f"{source_prefix}{base_name}"
        target = f"{target_prefix}{base_name}"
        if source in existing and target in existing:
            raise RuntimeError(f"Both {source} and {target} exist; table rename cannot continue safely")
        if source in existing:
            op.rename_table(source, target)
            existing.remove(source)
            existing.add(target)


def upgrade() -> None:
    _rename_tables("", "exam_")


def downgrade() -> None:
    _rename_tables("exam_", "")
