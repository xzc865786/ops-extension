from app.db.types import BigInt, BigIntPK
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_creator_created", "creator_user_id", "created_at"),
        Index("ix_tickets_status_claimed", "status", "claimed_by_user_id"),
        Index("ix_tickets_category", "category"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_ref_ticket_no", "ref_ticket_no"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    creator_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P2")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    claimed_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_ticket_no: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(128))
    api_endpoint: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[str | None] = mapped_column(String(10))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Per-category form: the config version used, a snapshot of the category's fields and the cleaned values.
    form_version: Mapped[int | None] = mapped_column(Integer)
    form_schema: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    form_data: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict
    )
    # Admin's recorded outcome for refund / invoice tickets (refunded, rejected, invoice issued).
    resolution: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket")
    attachments: Mapped[list["TicketAttachment"]] = relationship(back_populates="ticket")
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")
    orders: Mapped[list["TicketOrder"]] = relationship(back_populates="ticket", order_by="TicketOrder.id")
    refund_operations: Mapped[list["TicketRefundOperation"]] = relationship(
        back_populates="ticket", order_by="TicketRefundOperation.id"
    )

    @property
    def order_nos(self) -> list[str]:
        return [o.out_trade_no for o in self.orders]


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),
        Index("ix_ticket_messages_ticket_internal", "ticket_id", "is_internal"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tickets.id"), nullable=False)
    sender_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="messages")


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tickets.id"), nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("ticket_messages.id"))
    uploader_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInt, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERAL")  # GENERAL | INVOICE_FILE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (Index("ix_ticket_events_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tickets.id"), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    new_value: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class TicketOrder(Base):
    """A Sub2API payment order referenced by a refund / invoice / payment ticket."""

    __tablename__ = "ticket_orders"
    __table_args__ = (
        Index("ix_ticket_orders_out_trade_no_purpose", "out_trade_no", "purpose"),
        Index("ix_ticket_orders_ticket", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tickets.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False)
    # Null when the order could not be verified (Sub2API admin key not configured).
    sub2api_order_id: Mapped[int | None] = mapped_column(BigInt)
    snapshot: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="orders")


class TicketRefundOperation(Base):
    """One refund request sent to Sub2API from a ticket, with what came of it."""

    __tablename__ = "ticket_refund_operations"
    __table_args__ = (Index("ix_ticket_refund_operations_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tickets.id"), nullable=False)
    sub2api_order_id: Mapped[int] = mapped_column(BigInt, nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deduct_balance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    # IN_PROGRESS | SUCCESS | PENDING | REQUIRE_FORCE | FAILED | UNKNOWN
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    response_summary: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    operator_user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="refund_operations")


class TicketFormConfigVersion(Base):
    """One row per saved ticket form configuration; the highest version is the live one."""

    __tablename__ = "ticket_form_config_versions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    restored_from: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    created_by_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
