"""ticket resolutions, refund operations and invoice attachments

Revision ID: 007
Revises: 006
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolution", postgresql.JSONB()))
    op.add_column(
        "ticket_attachments",
        sa.Column("kind", sa.String(20), nullable=False, server_default="GENERAL"),
    )
    op.create_table(
        "ticket_refund_operations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("sub2api_order_id", sa.BigInteger(), nullable=False),
        sa.Column("out_trade_no", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("deduct_balance", sa.Boolean(), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("response_summary", postgresql.JSONB()),
        sa.Column("operator_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("operator_name", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_refund_operations_ticket", "ticket_refund_operations", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_refund_operations_ticket", table_name="ticket_refund_operations")
    op.drop_table("ticket_refund_operations")
    op.drop_column("ticket_attachments", "kind")
    op.drop_column("tickets", "resolution")
