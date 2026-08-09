"""Scope study, wrong-note, and mock-exam data to users."""

import json

import sqlalchemy as sa

from alembic import op

revision = "0005_user_owned_learning_data"
down_revision = "0004_user_authentication"
branch_labels = None
depends_on = None


def _admin_id(connection: sa.Connection) -> int | None:
    return connection.execute(sa.text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")).scalar()


def upgrade() -> None:
    connection = op.get_bind()
    admin_id = _admin_id(connection)
    inspector = sa.inspect(connection)
    if "study_sessions" not in inspector.get_table_names():
        op.create_table(
            "study_sessions",
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("certification_id", sa.Integer(), nullable=False),
            sa.Column("question_ids_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["certification_id"], ["certifications.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("session_id"),
        )
        op.create_index(op.f("ix_study_sessions_user_id"), "study_sessions", ["user_id"], unique=False)
        op.create_index(op.f("ix_study_sessions_certification_id"), "study_sessions", ["certification_id"], unique=False)
        op.create_index(op.f("ix_study_sessions_status"), "study_sessions", ["status"], unique=False)
        op.create_index(op.f("ix_study_sessions_completed_at"), "study_sessions", ["completed_at"], unique=False)

    for table, foreign_key_name, index_name in (
        ("study_attempts", "fk_study_attempts_user_id_users", "ix_study_attempts_user_id"),
        ("mock_exams", "fk_mock_exams_user_id_users", "ix_mock_exams_user_id"),
    ):
        inspector = sa.inspect(connection)
        columns = {column["name"] for column in inspector.get_columns(table)}
        foreign_keys = {foreign_key.get("name") for foreign_key in inspector.get_foreign_keys(table)}
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        with op.batch_alter_table(table) as batch:
            if "user_id" not in columns:
                batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
            if foreign_key_name not in foreign_keys:
                batch.create_foreign_key(foreign_key_name, "users", ["user_id"], ["id"])
            if index_name not in indexes:
                batch.create_index(index_name, ["user_id"])

    inspector = sa.inspect(connection)
    wrong_note_columns = {column["name"] for column in inspector.get_columns("wrong_notes")}
    wrong_note_indexes = {index["name"] for index in inspector.get_indexes("wrong_notes")}
    wrong_note_foreign_keys = {foreign_key.get("name") for foreign_key in inspector.get_foreign_keys("wrong_notes")}
    if "ix_wrong_notes_question_id" not in wrong_note_indexes:
        # MySQL needs a non-unique question_id index before the old unique index
        # can be removed because that index also supports the foreign key.
        op.create_index("ix_wrong_notes_question_id", "wrong_notes", ["question_id"], unique=False)
    for constraint in sa.inspect(connection).get_unique_constraints("wrong_notes"):
        if constraint.get("column_names") == ["question_id"] and constraint.get("name"):
            op.drop_constraint(constraint["name"], "wrong_notes", type_="unique")
    with op.batch_alter_table("wrong_notes") as batch:
        if "user_id" not in wrong_note_columns:
            batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        if "fk_wrong_notes_user_id_users" not in wrong_note_foreign_keys:
            batch.create_foreign_key("fk_wrong_notes_user_id_users", "users", ["user_id"], ["id"])
        if "ix_wrong_notes_user_id" not in wrong_note_indexes:
            batch.create_index("ix_wrong_notes_user_id", ["user_id"])
    composite_unique_exists = any(
        constraint.get("column_names") == ["user_id", "question_id"]
        for constraint in sa.inspect(connection).get_unique_constraints("wrong_notes")
    )
    if not composite_unique_exists:
        op.create_unique_constraint("uq_wrong_notes_user_id", "wrong_notes", ["user_id", "question_id"])

    if admin_id is not None:
        for table in ("study_attempts", "mock_exams", "wrong_notes"):
            connection.execute(sa.text(f"UPDATE {table} SET user_id = :admin_id WHERE user_id IS NULL"), {"admin_id": admin_id})

        legacy_sessions = list(connection.execute(sa.text("SELECT DISTINCT session_id FROM study_attempts")).scalars())
        for session_id in legacy_sessions:
            rows = connection.execute(
                sa.text(
                    "SELECT sa.question_id, q.certification_id, sa.wrong_note_processed "
                    "FROM study_attempts sa JOIN questions q ON q.id = sa.question_id "
                    "WHERE sa.session_id = :session_id ORDER BY sa.id"
                ),
                {"session_id": session_id},
            ).all()
            if not rows:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO study_sessions "
                    "(session_id, user_id, certification_id, question_ids_json, status, started_at, completed_at) "
                    "VALUES (:session_id, :user_id, :certification_id, :question_ids, :status, CURRENT_TIMESTAMP, :completed_at)"
                ),
                {
                    "session_id": session_id,
                    "user_id": admin_id,
                    "certification_id": rows[0].certification_id,
                    "question_ids": json.dumps([row.question_id for row in rows]),
                    "status": "completed" if all(row.wrong_note_processed for row in rows) else "abandoned",
                    "completed_at": connection.execute(sa.text("SELECT CURRENT_TIMESTAMP")).scalar(),
                },
            )


def downgrade() -> None:
    with op.batch_alter_table("wrong_notes") as batch:
        batch.drop_constraint("uq_wrong_notes_user_id", type_="unique")
        batch.create_unique_constraint("uq_wrong_notes_question_id", ["question_id"])
        batch.drop_index(op.f("ix_wrong_notes_question_id"))
        batch.drop_constraint("fk_wrong_notes_user_id_users", type_="foreignkey")
        batch.drop_index(op.f("ix_wrong_notes_user_id"))
        batch.drop_column("user_id")
    with op.batch_alter_table("mock_exams") as batch:
        batch.drop_constraint("fk_mock_exams_user_id_users", type_="foreignkey")
        batch.drop_index(op.f("ix_mock_exams_user_id"))
        batch.drop_column("user_id")
    with op.batch_alter_table("study_attempts") as batch:
        batch.drop_constraint("fk_study_attempts_user_id_users", type_="foreignkey")
        batch.drop_index(op.f("ix_study_attempts_user_id"))
        batch.drop_column("user_id")
    op.drop_table("study_sessions")
