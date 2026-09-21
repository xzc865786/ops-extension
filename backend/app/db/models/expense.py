from app.db.types import BigInt, BigIntPK
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_type: Mapped[str | None] = mapped_column(String(64))
    tax_number: Mapped[str | None] = mapped_column(String(64))
    contact_name: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CostCenter(Base):
    __tablename__ = "cost_centers"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaymentAccount(Base):
    __tablename__ = "payment_accounts"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    account_no_masked: Mapped[str | None] = mapped_column(String(64))
    owner_label: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExpenseClaim(Base):
    __tablename__ = "expense_claims"
    __table_args__ = (
        Index("ix_expense_claims_status", "status"),
        Index("ix_expense_claims_category", "category"),
        Index("ix_expense_claims_applicant", "applicant_user_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    claim_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    applicant_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("suppliers.id"))
    cost_center_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("cost_centers.id"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    amount_tax_included: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    amount_tax_excluded: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    description: Mapped[str | None] = mapped_column(Text)
    pay_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(64))
    payment_account_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("payment_accounts.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    invoice_required: Mapped[bool] = mapped_column(Boolean, default=True)
    invoice_status: Mapped[str] = mapped_column(String(20), default="NONE")
    invoice_type: Mapped[str | None] = mapped_column(String(32))
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    seller_name: Mapped[str | None] = mapped_column(String(200))
    seller_tax_no: Mapped[str | None] = mapped_column(String(64))
    buyer_name: Mapped[str | None] = mapped_column(String(200))
    buyer_tax_no: Mapped[str | None] = mapped_column(String(64))
    deductible: Mapped[bool | None] = mapped_column(Boolean)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["ExpenseItem"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(back_populates="claim")
    payments: Mapped[list["ExpensePayment"]] = relationship(back_populates="claim")
    events: Mapped[list["ExpenseEvent"]] = relationship(back_populates="claim")


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_claims.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[ExpenseClaim] = relationship(back_populates="items")


class ExpenseAttachment(Base):
    __tablename__ = "expense_attachments"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_claims.id"), nullable=False)
    uploader_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    attachment_type: Mapped[str] = mapped_column(String(32), default="OTHER")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInt, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[ExpenseClaim] = relationship(back_populates="attachments")


class ExpensePayment(Base):
    __tablename__ = "expense_payments"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_claims.id"), nullable=False)
    payment_account_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("payment_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[ExpenseClaim] = relationship(back_populates="payments")


class ExpenseEvent(Base):
    __tablename__ = "expense_events"
    __table_args__ = (Index("ix_expense_events_claim_created", "claim_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    claim_id: Mapped[int] = mapped_column(BigInt, ForeignKey("expense_claims.id"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    new_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[ExpenseClaim] = relationship(back_populates="events")
