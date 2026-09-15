"""Simple planning schema: plan_entries replaces task_requests/reservations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_simple_planning"
down_revision: str | None = "0001_initial_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "server_id", sa.Uuid(), sa.ForeignKey("managed_servers.id"), nullable=False
        ),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("project", sa.String(length=256), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=True),
        sa.Column("memory_gb", sa.Float(), nullable=True),
        sa.Column("gpu_count", sa.Integer(), nullable=True),
        sa.Column("gpu_ids", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_plan_entries_server_window",
        "plan_entries",
        ["server_id", "start_at", "end_at"],
    )
    op.create_index(
        "ix_plan_entries_owner_start",
        "plan_entries",
        ["owner_id", "start_at"],
    )

    # Migrate existing approved/planned reservation data into published intents.
    # The reservation UUID becomes the plan UUID. Requests without a reservation
    # never represented published intended use, so they are intentionally not
    # converted. Cancelled reservations keep their cancellation timestamp.
    op.execute(
        sa.text(
            """
            INSERT INTO plan_entries (
                id, owner_id, server_id, title, project, start_at, end_at,
                cpu_cores, memory_gb, gpu_count, gpu_ids, note,
                cancelled_at, created_at, updated_at
            )
            SELECT
                r.id,
                r.owner_id,
                r.server_id,
                r.title,
                req.project,
                r.start_at,
                r.end_at,
                r.cpu_cores,
                r.memory_gb,
                r.gpu_count,
                r.gpu_ids,
                req.note,
                CASE WHEN r.status = 'cancelled' THEN r.updated_at ELSE NULL END,
                r.created_at,
                r.updated_at
            FROM reservations AS r
            LEFT JOIN task_requests AS req ON req.id = r.request_id
            """
        )
    )

    op.drop_table("reservations")
    op.drop_table("task_requests")


def downgrade() -> None:
    op.drop_index("ix_plan_entries_owner_start", table_name="plan_entries")
    op.drop_index("ix_plan_entries_server_window", table_name="plan_entries")
    op.drop_table("plan_entries")

    # Data dropped by the upgrade cannot be restored; recreate the M1 shape only.
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
