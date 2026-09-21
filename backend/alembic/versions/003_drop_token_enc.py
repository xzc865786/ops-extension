"""drop sessions.token_enc — tokens must never be stored in business DB

Revision ID: 003
Revises: 002
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("sessions", "token_enc")


def downgrade() -> None:
    # Downgrade restores the column shape only; do not resume storing bearers.
    op.add_column("sessions", sa.Column("token_enc", sa.Text(), nullable=True))
