"""Independent RMB ledger; legacy claims and payments remain untouched."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.db.types import BigInt, BigIntPK


class RateQuote(Base):
    __tablename__ = "expense_rate_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)


class ExpenseRecord(Base):
    __tablename__ = "expense_records"
    __table_args__ = (
        CheckConstraint("amount > 0 AND rmb_amount > 0", name="ck_record_positive"),
        CheckConstraint("currency IN ('CNY', 'USD')", name="ck_record_currency"),
        CheckConstraint("amount_mode IN ('AUTO', 'MANUAL')", name="ck_record_mode"),
        Index("ix_record_date_active", "expense_date", "active"),
        Index("ix_record_payer", "payer"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    payer: Mapped[str] = mapped_column(String(100), nullable=False)
    merchant: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    rmb_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("expense_rate_quotes.id"))
    reference_rate: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    rate_date: Mapped[date | None] = mapped_column(Date)
    rate_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_source: Mapped[str | None] = mapped_column(String(100))
    needs_reimbursement: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    version: Mapped[int] = mapped_column(BigInt, default=1, nullable=False)
    legacy_claim_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("expense_claims.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Reimbursement(Base):
    __tablename__ = "expense_reimbursements"
    __table_args__ = (CheckConstraint("actual_amount > 0", name="ck_reimbursement_positive"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    payer: Mapped[str] = mapped_column(String(100), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reimbursement_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    difference_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    revoked_by: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInt, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReimbursementItem(Base):
    __tablename__ = "expense_reimbursement_items"
    __table_args__ = (
        CheckConstraint("actual_amount >= 0 AND expected_amount > 0", name="ck_reimbursement_item_amount"),
        CheckConstraint("active_record_id IS NULL OR active_record_id = record_id", name="ck_item_active_record"),
        Index("ix_reimbursement_item_record", "record_id"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_records.id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_reimbursements.id"), nullable=False)
    # NULL after whole-batch revocation; unique enforces one active batch per expense.
    active_record_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("expense_records.id"), unique=True)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class LedgerAttachment(Base):
    __tablename__ = "expense_ledger_attachments"
    __table_args__ = (CheckConstraint("(record_id IS NULL) != (batch_id IS NULL)", name="ck_ledger_attachment_owner"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    record_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("expense_records.id"))
    batch_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("expense_reimbursements.id"))
    uploader_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInt, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEvent(Base):
    __tablename__ = "expense_ledger_events"
    __table_args__ = (Index("ix_ledger_event_record", "record_id", "id"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_records.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("expense_reimbursements.id"))
    actor_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    new_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
