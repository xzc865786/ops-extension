import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response
from minio.error import S3Error
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage, safe_filename
from app.common.errors import AppError, forbidden, not_found
from app.db.models.expense import ExpenseAttachment
from app.db.models.ticket import Ticket, TicketAttachment
from app.db.session import get_db
from app.deps import CurrentUser, require_login

router = APIRouter(prefix="/ext/api/v1", tags=["attachments"])
logger = logging.getLogger(__name__)


def _content_disposition(filename: str) -> str:
    safe_name = safe_filename(filename)
    ascii_name = safe_name.encode("ascii", "ignore").decode("ascii")
    if not ascii_name or ascii_name.startswith("."):
        suffix = ascii_name if ascii_name.startswith(".") else ""
        ascii_name = f"attachment{suffix}"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe_name, safe="")}'


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    source: str = "ticket",
    proxy: bool = False,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    """Download ticket or expense attachment after authz.

    Default: stream bytes through this authenticated API (works with compose-internal MinIO).
    Optional: if MINIO_PUBLIC_ENDPOINT / MINIO_PUBLIC_URL is set, redirect to a short-lived
    presigned URL signed against that browser-reachable host. Never redirect to the internal
    compose hostname alone.
    """
    if source == "expense":
        if not user.is_admin:
            raise forbidden()
        att = db.get(ExpenseAttachment, attachment_id)
        if not att:
            raise not_found("附件不存在")
        object_key = att.object_key
        filename = att.file_name
        mime = att.mime_type
    else:
        att = db.get(TicketAttachment, attachment_id)
        if not att:
            raise not_found("附件不存在")
        ticket = db.get(Ticket, att.ticket_id)
        if not ticket:
            raise not_found()
        if not user.is_admin and ticket.creator_user_id != user.id:
            raise forbidden()
        object_key = att.object_key
        filename = att.file_name
        mime = att.mime_type

    try:
        storage = get_storage()
        if not proxy:
            public_url = storage.presigned_get_public(object_key, expires_seconds=180)
            if public_url:
                return RedirectResponse(public_url)
        data = storage.get_bytes(object_key)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            logger.warning("attachment object missing source=%s attachment_id=%s", source, attachment_id)
            raise AppError(404, "附件文件不存在，请联系管理员", "ATTACHMENT_OBJECT_MISSING") from exc
        logger.error("attachment storage error source=%s attachment_id=%s s3_code=%s", source, attachment_id, exc.code)
        raise AppError(503, "附件存储暂不可用，请稍后重试", "ATTACHMENT_STORAGE_UNAVAILABLE") from exc
    except Exception as exc:
        logger.error("attachment storage error source=%s attachment_id=%s error_type=%s", source, attachment_id, type(exc).__name__)
        raise AppError(503, "附件存储暂不可用，请稍后重试", "ATTACHMENT_STORAGE_UNAVAILABLE") from exc
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": _content_disposition(filename)},
    )
