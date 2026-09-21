from app.db.types import BigInt, BigIntPK
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExtensionUser(Base):
    __tablename__ = "extension_users"
    __table_args__ = (Index("ix_extension_users_sub2api_role", "sub2api_role"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    sub2api_user_id: Mapped[int] = mapped_column(BigInt, unique=True, nullable=False)
    username_snapshot: Mapped[str | None] = mapped_column(String(100))
    email_snapshot: Mapped[str | None] = mapped_column(String(255))
    sub2api_role: Mapped[str] = mapped_column(String(20), nullable=False)
    extension_role: Mapped[str | None] = mapped_column(String(32))  # retained; unused for V1 authz
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("extension_users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    # Bootstrap freshness only (role/status snapshots live on extension_users).
    # Sub2API bearer is NEVER stored here or elsewhere.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[ExtensionUser] = relationship(back_populates="sessions")
