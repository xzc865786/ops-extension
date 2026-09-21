from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage
from app.common.errors import bad_request, forbidden
from app.common.enums import TicketEventType, TicketStatus
from app.db.models.ticket import TicketAttachment
from app.db.session import get_db
from app.deps import CurrentUser, require_admin, require_login
from app.tickets import service
from app.tickets.schemas import (
    TicketAdminPatch,
    TicketAttachmentOut,
    TicketCreate,
    TicketEventOut,
    TicketListItem,
    TicketMessageOut,
    TicketOut,
    TicketReply,
)

router = APIRouter(prefix="/ext/api/v1", tags=["tickets"])


def _ticket_out(ticket, *, include_internal: bool) -> dict:
    data = TicketOut.model_validate(ticket).model_dump()
    if not include_internal:
        data["messages"] = [m for m in data["messages"] if not m["is_internal"]]
        data["events"] = [e for e in data["events"] if e["event_type"] != TicketEventType.INTERNAL_NOTE_ADDED.value]
    return data


@router.get("/tickets/meta")
def tickets_meta(user: CurrentUser = Depends(require_login)):
    return service.meta_for_user(is_admin=user.is_admin)


@router.get("/tickets")
def list_my_tickets(
    status: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    items, total = service.list_user_tickets(
        db, user, status=status, category=category, page=page, page_size=page_size
    )
    return {
        "items": [TicketListItem.model_validate(i).model_dump() for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/tickets", status_code=201)
def create_ticket(
    body: TicketCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    ticket = service.create_ticket(db, user, body)
    detail = service.load_ticket_detail(db, ticket.id, include_internal=False)
    return _ticket_out(detail, include_internal=False)


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    service.assert_owner_or_admin(ticket, user)
    detail = service.load_ticket_detail(db, ticket_id, include_internal=user.is_admin)
    return _ticket_out(detail, include_internal=user.is_admin)


@router.post("/tickets/{ticket_id}/replies", status_code=201)
def reply_ticket(
    ticket_id: int,
    body: TicketReply,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    if user.is_admin and ticket.creator_user_id != user.id:
        # user endpoint: only owner (even admins acting as user on own tickets)
        # Plan: user API is owner-only
        pass
    if ticket.creator_user_id != user.id:
        raise forbidden("仅工单创建者可在此接口回复", "NOT_OWNER")
    if body.is_internal:
        raise forbidden("用户不可写内部备注")
    msg = service.reply_ticket(db, ticket, user, body.content, is_internal=False)
    return TicketMessageOut.model_validate(msg).model_dump()


@router.post("/tickets/{ticket_id}/close")
def close_my_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    ticket = service.close_ticket(db, ticket, user, by_admin=False)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/tickets/{ticket_id}/attachments", status_code=201)
async def upload_ticket_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_login),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    service.assert_owner_or_admin(ticket, user)
    if not user.is_admin and ticket.creator_user_id != user.id:
        raise forbidden()
    if ticket.status == TicketStatus.CLOSED.value:
        raise bad_request("工单已关闭", "TICKET_CLOSED")
    data = await file.read()
    stored = get_storage().upload(
        prefix="tickets",
        entity_id=ticket.id,
        filename=file.filename or "file",
        content_type=file.content_type,
        data=data,
    )
    att = TicketAttachment(
        ticket_id=ticket.id,
        uploader_user_id=user.id,
        file_name=stored.file_name,
        object_key=stored.object_key,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
    )
    db.add(att)
    service.add_event(
        db,
        ticket.id,
        user.id,
        TicketEventType.ATTACHMENT_ADDED.value,
        new_value={"file_name": stored.file_name},
    )
    db.commit()
    db.refresh(att)
    return TicketAttachmentOut.model_validate(att).model_dump()


# ---- Admin ----

@router.get("/admin/tickets")
def admin_list_tickets(
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    claimed_by: int | None = None,
    unclaimed: bool | None = None,
    creator_user_id: int | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    items, total = service.list_admin_tickets(
        db,
        status=status,
        category=category,
        priority=priority,
        claimed_by=claimed_by,
        unclaimed=unclaimed,
        creator_user_id=creator_user_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [TicketListItem.model_validate(i).model_dump() for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/admin/tickets/{ticket_id}")
def admin_get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    detail = service.load_ticket_detail(db, ticket_id, include_internal=True)
    return _ticket_out(detail, include_internal=True)


@router.post("/admin/tickets/{ticket_id}/claim")
def admin_claim(ticket_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    ticket = service.claim_ticket(db, ticket_id, admin)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/admin/tickets/{ticket_id}/unclaim")
def admin_unclaim(ticket_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    ticket = service.unclaim_ticket(db, ticket_id, admin)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/admin/tickets/{ticket_id}/takeover")
def admin_takeover(ticket_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    ticket = service.takeover_ticket(db, ticket_id, admin)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/admin/tickets/{ticket_id}/replies", status_code=201)
def admin_reply(
    ticket_id: int,
    body: TicketReply,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    msg = service.reply_ticket(db, ticket, admin, body.content, is_internal=body.is_internal)
    return TicketMessageOut.model_validate(msg).model_dump()


@router.patch("/admin/tickets/{ticket_id}")
def admin_patch(
    ticket_id: int,
    body: TicketAdminPatch,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    ticket = service.get_ticket_or_404(db, ticket_id)
    ticket = service.patch_ticket_admin(db, ticket, admin, body)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/admin/tickets/{ticket_id}/close")
def admin_close(ticket_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    ticket = service.get_ticket_or_404(db, ticket_id)
    ticket = service.close_ticket(db, ticket, admin, by_admin=True)
    return TicketListItem.model_validate(ticket).model_dump()


@router.post("/admin/tickets/{ticket_id}/attachments", status_code=201)
async def admin_upload_attachment(
    ticket_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return await upload_ticket_attachment(ticket_id, file, db, admin)


@router.get("/admin/tickets/{ticket_id}/events")
def admin_events(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    detail = service.load_ticket_detail(db, ticket_id, include_internal=True)
    return [TicketEventOut.model_validate(e).model_dump() for e in detail.events]
