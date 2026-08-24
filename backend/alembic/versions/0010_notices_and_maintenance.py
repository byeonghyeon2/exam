"""Add notices and maintenance-safe learner draft state."""

import sqlalchemy as sa

from alembic import op

revision = "0010_notices_and_maintenance"
down_revision = "0009_passkey_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "exam_notices" not in tables:
        op.create_table(
            "exam_notices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("notice_type", sa.String(16), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("display_start_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("display_end_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("maintenance_start_at", sa.DateTime(timezone=True)),
            sa.Column("maintenance_end_at", sa.DateTime(timezone=True)),
            sa.Column("maintenance_screen_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("title_color", sa.String(16), nullable=False, server_default="default"),
            sa.Column("content_color", sa.String(16), nullable=False, server_default="default"),
            sa.Column("title_weight", sa.String(16), nullable=False, server_default="bold"),
            sa.Column("content_weight", sa.String(16), nullable=False, server_default="normal"),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("maintenance_started_at", sa.DateTime(timezone=True)),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_exam_notices_active_display", "exam_notices", ["is_published", "display_start_at", "display_end_at"])
        op.create_index("ix_exam_notices_maintenance", "exam_notices", ["notice_type", "maintenance_start_at", "maintenance_end_at"])
    connection = op.get_bind()
    exists = connection.execute(
        sa.text("SELECT COUNT(*) FROM exam_app_settings WHERE `key` = :key"),
        {"key": "maintenance_schedule_lock"},
    ).scalar_one()
    if not exists:
        connection.execute(
            sa.text("INSERT INTO exam_app_settings (`key`, value_json, created_at, updated_at) VALUES (:key, :value, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
            {"key": "maintenance_schedule_lock", "value": "{\"version\": 1}"},
        )
    columns = {item["name"] for item in sa.inspect(bind).get_columns("exam_study_sessions")}
    if "pending_question_id" not in columns:
        with op.batch_alter_table("exam_study_sessions") as batch:
            batch.add_column(sa.Column("pending_question_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_exam_study_sessions_pending_question_id", "exam_questions", ["pending_question_id"], ["id"])
            batch.create_index("ix_exam_study_sessions_pending_question_id", ["pending_question_id"])
    if "pending_selected_answers_json" not in columns:
        op.add_column("exam_study_sessions", sa.Column("pending_selected_answers_json", sa.JSON(), nullable=True))
    if "pending_updated_at" not in columns:
        op.add_column("exam_study_sessions", sa.Column("pending_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "exam_study_sessions" in tables:
        columns = {item["name"] for item in sa.inspect(bind).get_columns("exam_study_sessions")}
        with op.batch_alter_table("exam_study_sessions") as batch:
            if "pending_updated_at" in columns:
                batch.drop_column("pending_updated_at")
            if "pending_selected_answers_json" in columns:
                batch.drop_column("pending_selected_answers_json")
            if "pending_question_id" in columns:
                batch.drop_index("ix_exam_study_sessions_pending_question_id")
                if bind.dialect.name != "sqlite":
                    batch.drop_constraint(
                        "fk_exam_study_sessions_pending_question_id", type_="foreignkey"
                    )
                batch.drop_column("pending_question_id")
    if "exam_notices" in tables:
        # The project naming convention removes the application table prefix
        # from explicitly named indexes when DDL is emitted.
        op.drop_index("ix_notices_maintenance", table_name="exam_notices")
        op.drop_index("ix_notices_active_display", table_name="exam_notices")
        op.drop_table("exam_notices")
    if "exam_app_settings" in tables:
        bind.execute(
            sa.text("DELETE FROM exam_app_settings WHERE `key` = :key"),
            {"key": "maintenance_schedule_lock"},
        )
