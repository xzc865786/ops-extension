"""Sub2API orders referenced by tickets

Revision ID: 006
Revises: 005
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("out_trade_no", sa.String(64), nullable=False),
        sa.Column("sub2api_order_id", sa.BigInteger()),
        sa.Column("snapshot", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_orders_out_trade_no_purpose", "ticket_orders", ["out_trade_no", "purpose"])
    op.create_index("ix_ticket_orders_ticket", "ticket_orders", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_ticket_orders_ticket", table_name="ticket_orders")
    op.drop_index("ix_ticket_orders_out_trade_no_purpose", table_name="ticket_orders")
    op.drop_table("ticket_orders")
