from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage
from app.common.errors import forbidden, not_found
from app.db.models.expense import ExpenseAttachment
from app.db.models.ticket import Ticket, TicketAttachment
from app.db.session import get_db
from app.deps import CurrentUser, require_login

router = APIRouter(prefix="/ext/api/v1", tags=["attachments"])


@router.get("/attachments/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    source: str = "ticket",
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

    storage = get_storage()
    public_url = storage.presigned_get_public(object_key, expires_seconds=180)
    if public_url:
        return RedirectResponse(public_url)

    data = storage.get_bytes(object_key)
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
