"""Auth schema: nullable user password hashes and server-side sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_auth"
down_revision: str | None = "0002_simple_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_sessions")
    op.drop_column("users", "password_hash")
