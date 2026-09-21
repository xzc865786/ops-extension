from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

from minio import Minio

from app.common.errors import bad_request
from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_MIME = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/gif": {".gif"},
    "image/webp": {".webp"},
    "application/pdf": {".pdf"},
    "text/plain": {".log", ".txt"},
}

EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".log": "text/plain",
    ".txt": "text/plain",
}


def safe_filename(name: str) -> str:
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = re.sub(r"[^\w.\-()+ ]+", "_", base, flags=re.UNICODE)
    return base[:200] or "file"


def validate_attachment(filename: str, content_type: str | None, size: int) -> tuple[str, str]:
    settings = get_settings()
    if size <= 0:
        raise bad_request("空文件", "EMPTY_FILE")
    if size > settings.attachment_max_bytes:
        raise bad_request("文件超过 20MB 限制", "FILE_TOO_LARGE")
    fname = safe_filename(filename)
    ext = ""
    if "." in fname:
        ext = "." + fname.rsplit(".", 1)[-1].lower()
    mime = (content_type or "").split(";")[0].strip().lower()
    if not mime or mime == "application/octet-stream":
        mime = EXT_TO_MIME.get(ext, "")
    allowed_exts = ALLOWED_MIME.get(mime)
    if not allowed_exts or ext not in allowed_exts:
        raise bad_request("不支持的文件类型（仅图片/PDF/日志）", "INVALID_FILE_TYPE")
    return fname, mime




def resolve_public_minio_target() -> tuple[str, bool] | None:
    """Return (endpoint host:port, secure) for browser-facing presign, or None.

    When neither MINIO_PUBLIC_ENDPOINT nor MINIO_PUBLIC_URL is set, callers must
    stream through the API and must not redirect to the internal compose hostname.
    """
    settings = get_settings()
    if settings.minio_public_endpoint:
        ep = settings.minio_public_endpoint.strip()
        secure = settings.minio_use_ssl
        if "://" in ep:
            parsed = urlparse(ep)
            host = parsed.hostname or ""
            port = parsed.port
            if parsed.scheme in ("http", "https"):
                secure = parsed.scheme == "https"
            ep = f"{host}:{port}" if port else host
        return (ep, secure) if ep else None
    if settings.minio_public_url:
        parsed = urlparse(settings.minio_public_url.strip())
        if not parsed.hostname:
            return None
        host = parsed.hostname
        port = parsed.port
        secure = parsed.scheme == "https"
        ep = f"{host}:{port}" if port else host
        return ep, secure
    return None

@dataclass
class StoredObject:
    object_key: str
    sha256: str
    file_size: int
    mime_type: str
    file_name: str


class MinioStorage:
    def __init__(self):
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        self._ensured = False

    def ensure_bucket(self) -> None:
        if self._ensured:
            return
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._ensured = True
        except Exception as exc:
            logger.warning("ensure_bucket failed: %s", exc)
            raise

    def upload(
        self,
        *,
        prefix: str,
        entity_id: int,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> StoredObject:
        fname, mime = validate_attachment(filename, content_type, len(data))
        digest = hashlib.sha256(data).hexdigest()
        key = f"{prefix}/{entity_id}/{uuid.uuid4().hex}/{fname}"
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=mime,
        )
        return StoredObject(
            object_key=key,
            sha256=digest,
            file_size=len(data),
            mime_type=mime,
            file_name=fname,
        )

    def presigned_get(self, object_key: str, expires_seconds: int = 120) -> str:
        from datetime import timedelta

        return self.client.presigned_get_object(
            self.bucket, object_key, expires=timedelta(seconds=expires_seconds)
        )


    def presigned_get_public(self, object_key: str, expires_seconds: int = 180) -> str | None:
        """Presign using MINIO_PUBLIC_ENDPOINT / MINIO_PUBLIC_URL when configured; else None."""
        target = resolve_public_minio_target()
        if not target:
            return None
        endpoint, secure = target
        settings = get_settings()
        public_client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
        )
        from datetime import timedelta

        return public_client.presigned_get_object(
            self.bucket, object_key, expires=timedelta(seconds=expires_seconds)
        )

    def get_bytes(self, object_key: str) -> bytes:
        resp = self.client.get_object(self.bucket, object_key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()


_storage: MinioStorage | None = None


def get_storage() -> MinioStorage:
    global _storage
    if _storage is None:
        _storage = MinioStorage()
    return _storage


def reset_storage_for_tests() -> None:
    global _storage
    _storage = None
