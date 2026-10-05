"""per-category ticket forms: config versions and form columns on tickets

Revision ID: 005
Revises: 004
Create Date: 2026-10-05
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of the categories and fixed troubleshooting columns that existed before this revision.
LEGACY_CATEGORIES = {
    "API_ERROR": ("API 错误", "general"),
    "AUTH_ERROR": ("认证错误", "general"),
    "BILLING_ERROR": ("计费错误", "general"),
    "RECHARGE_PAYMENT": ("充值/支付", "payment"),
    "INVOICE": ("发票", "invoice"),
    "REFUND": ("退款", "refund"),
    "MODEL_AVAILABILITY": ("模型可用性", "general"),
    "RATE_LIMIT": ("限流", "general"),
    "ACCOUNT": ("账户", "general"),
    "FEATURE_REQUEST": ("功能建议", "general"),
    "OTHER": ("其他", "general"),
}
LEGACY_FIELDS = [
    {"key": "request_id", "label": "Request ID", "type": "text"},
    {"key": "model_name", "label": "模型", "type": "text"},
    {"key": "api_endpoint", "label": "API 接口", "type": "text"},
    {"key": "occurred_at", "label": "发生时间", "type": "datetime"},
    {"key": "error_message", "label": "错误信息", "type": "textarea"},
]


def upgrade() -> None:
    op.create_table(
        "ticket_form_config_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.String(200)),
        sa.Column("restored_from", sa.Integer()),
        sa.Column("created_by_user_id", sa.BigInteger(), sa.ForeignKey("extension_users.id")),
        sa.Column("created_by_name", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_ticket_form_config_versions_version"),
    )
    op.add_column("tickets", sa.Column("form_version", sa.Integer()))
    op.add_column("tickets", sa.Column("form_schema", postgresql.JSONB()))
    op.add_column(
        "tickets",
        sa.Column("form_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    # Old tickets keep their values; their snapshot describes the fixed columns they were created with.
    op.execute(
        """
        UPDATE tickets SET form_data = jsonb_strip_nulls(jsonb_build_object(
            'request_id', NULLIF(request_id, ''),
            'model_name', NULLIF(model_name, ''),
            'api_endpoint', NULLIF(api_endpoint, ''),
            'occurred_at', to_char(occurred_at AT TIME ZONE INTERVAL '+08:00', 'YYYY-MM-DD"T"HH24:MI'),
            'error_message', NULLIF(error_message, '')
        ))
        """
    )
    fields = [{**f, "required": False, "system": False} for f in LEGACY_FIELDS]
    stmt = sa.text("UPDATE tickets SET form_schema = CAST(:schema AS jsonb) WHERE category = :key")
    for key, (label, kind) in LEGACY_CATEGORIES.items():
        schema = {"key": key, "label": label, "kind": kind, "fields": fields}
        op.get_bind().execute(stmt, {"schema": json.dumps(schema, ensure_ascii=False), "key": key})


def downgrade() -> None:
    op.drop_column("tickets", "form_data")
    op.drop_column("tickets", "form_schema")
    op.drop_column("tickets", "form_version")
    op.drop_table("ticket_form_config_versions")
