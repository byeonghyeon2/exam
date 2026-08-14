"""Add AWS domain-classification and detailed import counters."""

import sqlalchemy as sa

from alembic import op

revision = "0002_aws_domain_classification"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if any(name.startswith("exam_") for name in inspector.get_table_names()):
        return
    question_columns = {column["name"] for column in inspector.get_columns("questions")}
    additions = [
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classification_reason", sa.Text(), nullable=True),
        sa.Column("classification_model", sa.String(128), nullable=True),
        sa.Column("classification_prompt_version", sa.String(32), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("classification_status", sa.String(32), nullable=True),
    ]
    with op.batch_alter_table("questions") as batch:
        for column in additions:
            if column.name not in question_columns:
                batch.add_column(column)
        indexes = {index["name"] for index in inspector.get_indexes("questions")}
        if "ix_questions_classification_status" not in indexes:
            batch.create_index("ix_questions_classification_status", ["classification_status"])
    import_columns = {column["name"] for column in inspector.get_columns("import_jobs")}
    with op.batch_alter_table("import_jobs") as batch:
        if "updated_count" not in import_columns:
            batch.add_column(sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"))
        if "excluded_count" not in import_columns:
            batch.add_column(sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("import_jobs") as batch:
        batch.drop_column("excluded_count")
        batch.drop_column("updated_count")
    with op.batch_alter_table("questions") as batch:
        batch.drop_index("ix_questions_classification_status")
        batch.drop_column("classification_status")
        batch.drop_column("classified_at")
        batch.drop_column("classification_prompt_version")
        batch.drop_column("classification_model")
        batch.drop_column("classification_reason")
        batch.drop_column("classification_confidence")
