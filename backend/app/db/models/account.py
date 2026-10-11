"""Team platform accounts (Claude, ChatGPT, Google...). Secrets are stored encrypted only."""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.db.types import BigInt, BigIntPK

ACCOUNT_STATUSES = ("ACTIVE", "STANDBY", "BANNED", "DISABLED")


class AccountRecord(Base):
    __tablename__ = "account_records"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'STANDBY', 'BANNED', 'DISABLED')", name="ck_account_status"),
        CheckConstraint("active_identity IS NULL OR active_identity = identity", name="ck_account_active_identity"),
        Index("ix_account_client", "client"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    client: Mapped[str] = mapped_column(String(50), nullable=False)
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    # Case-folded "client\nlogin"; active_identity is NULL once archived, so uniqueness covers live rows only.
    identity: Mapped[str] = mapped_column(String(310), nullable=False)
    active_identity: Mapped[str | None] = mapped_column(String(310), unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)
    owner: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    recovery_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    password_enc: Mapped[str | None] = mapped_column(Text)
    secret_notes_enc: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(BigInt, default=1, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AccountEvent(Base):
    """Audit trail. Never holds plaintext or ciphertext of secrets, only that they changed or were read."""
    __tablename__ = "account_events"
    __table_args__ = (Index("ix_account_event_account", "account_id", "id"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(BigInt, ForeignKey("account_records.id"), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
