"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extension_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sub2api_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username_snapshot", sa.String(100)),
        sa.Column("email_snapshot", sa.String(255)),
        sa.Column("sub2api_role", sa.String(20), nullable=False),
        sa.Column("extension_role", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sub2api_user_id"),
    )
    op.create_index("ix_extension_users_sub2api_role", "extension_users", ["sub2api_role"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("supplier_type", sa.String(64)),
        sa.Column("tax_number", sa.String(64)),
        sa.Column("contact_name", sa.String(100)),
        sa.Column("contact_phone", sa.String(50)),
        sa.Column("contact_email", sa.String(255)),
        sa.Column("bank_name", sa.String(100)),
        sa.Column("bank_account", sa.String(64)),
        sa.Column("notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cost_centers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "payment_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("account_type", sa.String(32), nullable=False),
        sa.Column("account_no_masked", sa.String(64)),
        sa.Column("owner_label", sa.String(100)),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_no", sa.String(32), nullable=False),
        sa.Column("creator_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(8), nullable=False, server_default="P2"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("claimed_by_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("ref_ticket_no", sa.String(32)),
        sa.Column("request_id", sa.String(128)),
        sa.Column("model_name", sa.String(128)),
        sa.Column("api_endpoint", sa.String(255)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("closed_by", sa.String(10)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_no"),
    )
    op.create_index("ix_tickets_creator_created", "tickets", ["creator_user_id", "created_at"])
    op.create_index("ix_tickets_status_claimed", "tickets", ["status", "claimed_by_user_id"])
    op.create_index("ix_tickets_category", "tickets", ["category"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_ref_ticket_no", "tickets", ["ref_ticket_no"])

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("sender_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("sender_role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_messages_ticket_created", "ticket_messages", ["ticket_id", "created_at"])
    op.create_index("ix_ticket_messages_ticket_internal", "ticket_messages", ["ticket_id", "is_internal"])

    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("message_id", sa.BigInteger(), sa.ForeignKey("ticket_messages.id")),
        sa.Column("uploader_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("old_value", json_type),
        sa.Column("new_value", json_type),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_events_ticket_created", "ticket_events", ["ticket_id", "created_at"])

    op.create_table(
        "expense_claims",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_no", sa.String(32), nullable=False),
        sa.Column("applicant_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), sa.ForeignKey("suppliers.id")),
        sa.Column("cost_center_id", sa.BigInteger(), sa.ForeignKey("cost_centers.id")),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("amount_tax_included", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_tax_excluded", sa.Numeric(18, 2)),
        sa.Column("tax_amount", sa.Numeric(18, 2)),
        sa.Column("tax_rate", sa.Numeric(8, 4)),
        sa.Column("description", sa.Text()),
        sa.Column("pay_type", sa.String(32), nullable=False),
        sa.Column("payment_method", sa.String(64)),
        sa.Column("payment_account_id", sa.BigInteger(), sa.ForeignKey("payment_accounts.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("invoice_required", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("invoice_status", sa.String(20), server_default="NONE"),
        sa.Column("invoice_type", sa.String(32)),
        sa.Column("invoice_number", sa.String(64)),
        sa.Column("invoice_date", sa.Date()),
        sa.Column("seller_name", sa.String(200)),
        sa.Column("seller_tax_no", sa.String(64)),
        sa.Column("buyer_name", sa.String(200)),
        sa.Column("buyer_tax_no", sa.String(64)),
        sa.Column("deductible", sa.Boolean()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("paid_by_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_no"),
    )
    op.create_index("ix_expense_claims_status", "expense_claims", ["status"])
    op.create_index("ix_expense_claims_category", "expense_claims", ["category"])
    op.create_index("ix_expense_claims_applicant", "expense_claims", ["applicant_user_id"])

    op.create_table(
        "expense_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), sa.ForeignKey("expense_claims.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4)),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "expense_attachments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), sa.ForeignKey("expense_claims.id"), nullable=False),
        sa.Column("uploader_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("attachment_type", sa.String(32)),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "expense_payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), sa.ForeignKey("expense_claims.id"), nullable=False),
        sa.Column("payment_account_id", sa.BigInteger(), sa.ForeignKey("payment_accounts.id")),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3)),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_no", sa.String(128)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "expense_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.BigInteger(), sa.ForeignKey("expense_claims.id"), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("old_value", json_type),
        sa.Column("new_value", json_type),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expense_events_claim_created", "expense_events", ["claim_id", "created_at"])


def downgrade() -> None:
    for t in [
        "expense_events",
        "expense_payments",
        "expense_attachments",
        "expense_items",
        "expense_claims",
        "ticket_events",
        "ticket_attachments",
        "ticket_messages",
        "tickets",
        "payment_accounts",
        "cost_centers",
        "suppliers",
        "sessions",
        "extension_users",
    ]:
        op.drop_table(t)
