"""Add anonymous Passkey authentication challenges."""

import sqlalchemy as sa

from alembic import op

revision = "0009_passkey_challenges"
down_revision = "0008_prefix_application_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "exam_passkey_challenges" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "exam_passkey_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("challenge", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_exam_passkey_challenges_token_hash"),
        "exam_passkey_challenges",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_exam_passkey_challenges_expires_at"),
        "exam_passkey_challenges",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_exam_passkey_challenges_consumed_at"),
        "exam_passkey_challenges",
        ["consumed_at"],
        unique=False,
    )


def downgrade() -> None:
    if "exam_passkey_challenges" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index(
        op.f("ix_exam_passkey_challenges_consumed_at"),
        table_name="exam_passkey_challenges",
    )
    op.drop_index(
        op.f("ix_exam_passkey_challenges_expires_at"),
        table_name="exam_passkey_challenges",
    )
    op.drop_index(
        op.f("ix_exam_passkey_challenges_token_hash"),
        table_name="exam_passkey_challenges",
    )
    op.drop_table("exam_passkey_challenges")
