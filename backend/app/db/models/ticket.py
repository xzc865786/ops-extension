from app.db.types import BigInt, BigIntPK
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket")
    attachments: Mapped[list["TicketAttachment"]] = relationship(back_populates="ticket")
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")


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
