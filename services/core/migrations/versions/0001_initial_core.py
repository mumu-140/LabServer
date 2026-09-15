"""Initial core planning schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "managed_servers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("memory_gb", sa.Float(), nullable=True),
        sa.Column("gpu_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "task_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project", sa.String(length=256), nullable=True),
        sa.Column(
            "preferred_server_id",
            sa.Uuid(),
            sa.ForeignKey("managed_servers.id"),
            nullable=False,
        ),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("requested_cpu_cores", sa.Integer(), nullable=False),
        sa.Column("requested_memory_gb", sa.Float(), nullable=True),
        sa.Column("requested_gpu_count", sa.Integer(), nullable=False),
        sa.Column("preferred_gpu_ids", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_changed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("task_requests.id"), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("server_id", sa.Uuid(), sa.ForeignKey("managed_servers.id"), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=False),
        sa.Column("memory_gb", sa.Float(), nullable=True),
        sa.Column("gpu_count", sa.Integer(), nullable=False),
        sa.Column("gpu_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_reservations_request_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("reservations")
    op.drop_table("task_requests")
    op.drop_table("managed_servers")
    op.drop_table("users")
