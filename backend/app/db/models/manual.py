from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import BigInt, BigIntPK


class ManualConfigVersion(Base):
    """One row per saved manual configuration; the highest version is the live one."""

    __tablename__ = "manual_config_versions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    restored_from: Mapped[int | None] = mapped_column(Integer)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    created_by_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManualFile(Base):
    """Files offered for download from the manual (installers, archives), stored in MinIO."""

    __tablename__ = "manual_files"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uploaded_by_user_id: Mapped[int | None] = mapped_column(BigInt, ForeignKey("extension_users.id"))
    uploaded_by_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
