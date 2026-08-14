"""Add one-device passkey credentials and staged authentication sessions."""

import sqlalchemy as sa

from alembic import op

revision = "0007_passkey_authentication"
down_revision = "0006_merge_wrong_note_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    auth_columns = {column["name"] for column in inspector.get_columns("auth_sessions")}
    if "purpose" not in auth_columns:
        op.add_column("auth_sessions", sa.Column("purpose", sa.String(length=32), nullable=False, server_default="full"))
    if "challenge" not in auth_columns:
        op.add_column("auth_sessions", sa.Column("challenge", sa.String(length=255), nullable=True))
    if "challenge_type" not in auth_columns:
        op.add_column("auth_sessions", sa.Column("challenge_type", sa.String(length=32), nullable=True))
    if "challenge_expires_at" not in auth_columns:
        op.add_column("auth_sessions", sa.Column("challenge_expires_at", sa.DateTime(timezone=True), nullable=True))
    auth_indexes = {index["name"] for index in inspector.get_indexes("auth_sessions")}
    if op.f("ix_auth_sessions_purpose") not in auth_indexes:
        op.create_index(op.f("ix_auth_sessions_purpose"), "auth_sessions", ["purpose"], unique=False)
    if "passkey_credentials" not in inspector.get_table_names():
        op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(length=1024), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports_json", sa.JSON(), nullable=False),
        sa.Column("device_type", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        )
        op.create_index(op.f("ix_passkey_credentials_user_id"), "passkey_credentials", ["user_id"], unique=True)
        op.create_index(op.f("ix_passkey_credentials_credential_id"), "passkey_credentials", ["credential_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_passkey_credentials_credential_id"), table_name="passkey_credentials")
    op.drop_index(op.f("ix_passkey_credentials_user_id"), table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
    op.drop_index(op.f("ix_auth_sessions_purpose"), table_name="auth_sessions")
    op.drop_column("auth_sessions", "challenge_expires_at")
    op.drop_column("auth_sessions", "challenge_type")
    op.drop_column("auth_sessions", "challenge")
    op.drop_column("auth_sessions", "purpose")
