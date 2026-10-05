from datetime import datetime, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, selectinload

from app.common.enums import (
    TICKET_STATUS_TRANSITIONS,
    ClosedBy,
    TicketEventType,
    TicketPriority,
    TicketStatus,
)
from app.common.errors import AppError, bad_request, conflict, forbidden, not_found
from app.db.models.ticket import Ticket, TicketAttachment, TicketEvent, TicketMessage, TicketOrder
from app.deps import CurrentUser
from app.orders import service as orders
from app.orders.sub2api import get_admin_client
from app.tickets import form_config
from app.tickets.form_schema import (
    LEGACY_FIELDS,
    legacy_snapshot,
    render_title,
    snapshot,
    validate_form_data,
)


def generate_ticket_no(db: Session) -> str:
    """Allocate next ticket_no for today using PG advisory lock + max+1.

    Callers should still retry on unique conflicts for non-PG dialects / races.
    """
    import hashlib

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"T{today}"
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        lock_key = int(hashlib.sha256(prefix.encode()).hexdigest()[:8], 16) % (2**31 - 1)
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

    last = db.scalar(
        select(func.max(Ticket.ticket_no)).where(Ticket.ticket_no.like(f"{prefix}%"))
    )
    if last and last.startswith(prefix):
        try:
            seq = int(last[len(prefix) :]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def add_event(
    db: Session,
    ticket_id: int,
    actor_user_id: int | None,
    event_type: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> TicketEvent:
    ev = TicketEvent(
        ticket_id=ticket_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(ev)
    return ev


def _prepare_form(db: Session, data) -> tuple[dict, str]:
    """Validate a submission against the live form config.

    Returns the ticket's form columns and texts, and the category kind that drives order checks.
    """
    version, config = form_config.live_config(db)
    category = config.category(data.category)
    if not category or not category.enabled:
        raise bad_request("无效分类", "INVALID_CATEGORY")
    title = (data.title or "").strip()
    description = (data.description or "").strip()

    if data.form_version is None:
        # Pre-form clients send the fixed troubleshooting columns; accepted until they are gone.
        if not title or not description:
            raise bad_request("标题和描述不能为空", "TICKET_FORM_INVALID")
        legacy = {f["key"]: getattr(data, f["key"]) for f in LEGACY_FIELDS}
        form_data = {k: (v.isoformat(timespec="minutes") if isinstance(v, datetime) else v)
                     for k, v in legacy.items() if v not in (None, "")}
        form = {"title": title, "description": description, "form_version": None,
                "form_schema": legacy_snapshot(category.key, category.label), "form_data": form_data, **legacy}
        return form, "general"

    try:
        form_data = validate_form_data(category, data.form_data or {})
    except ValueError as exc:
        message = str(exc)
        if data.form_version != version:
            message += "（表单配置已更新，请刷新页面后重新填写）"
        raise AppError(422, message, "TICKET_FORM_INVALID") from exc

    if category.title_mode == "auto" or (category.title_mode == "optional" and not title):
        title = render_title(category, form_data) if category.title_template else category.label
    if not title:
        raise AppError(422, "标题不能为空", "TICKET_FORM_INVALID")
    if category.description_mode == "hidden":
        description = ""
    elif category.description_mode == "required" and not description:
        raise AppError(422, "描述不能为空", "TICKET_FORM_INVALID")
    form = {"title": title[:200], "description": description, "form_version": version,
            "form_schema": snapshot(category), "form_data": form_data}
    return form, category.kind


def create_ticket(db: Session, user: CurrentUser, data) -> Ticket:
    from sqlalchemy.exc import IntegrityError

    form, kind = _prepare_form(db, data)
    nos = orders.order_nos(kind, form["form_data"])
    # Sub2API is called before the insert transaction so no lock is held during the network round trip.
    order_rows = orders.verify_orders(user, kind, nos) if nos else []
    last_err: Exception | None = None
    for _attempt in range(8):
        try:
            if nos:
                orders.lock_and_check_duplicates(db, kind, nos)
            ticket = Ticket(
                ticket_no=generate_ticket_no(db),
                creator_user_id=user.id,
                category=data.category,
                priority=TicketPriority.P2.value,  # forced
                status=TicketStatus.OPEN.value,
                ref_ticket_no=data.ref_ticket_no,
                **form,
            )
            db.add(ticket)
            db.flush()
            orders.attach(db, ticket, kind, order_rows)
            if form["description"]:
                # first message mirrors description
                db.add(TicketMessage(
                    ticket_id=ticket.id,
                    sender_user_id=user.id,
                    sender_role=user.sub2api_role,
                    content=form["description"],
                    is_internal=False,
                ))
            add_event(
                db,
                ticket.id,
                user.id,
                TicketEventType.CREATED.value,
                new_value={"ticket_no": ticket.ticket_no},
            )
            if data.ref_ticket_no:
                add_event(
                    db,
                    ticket.id,
                    user.id,
                    TicketEventType.REF_TICKET_LINKED.value,
                    new_value={"ref_ticket_no": data.ref_ticket_no},
                )
            db.commit()
            db.refresh(ticket)
            return ticket
        except IntegrityError as exc:
            last_err = exc
            db.rollback()
            continue
    raise conflict("工单号分配冲突，请重试", "TICKET_NO_CONFLICT") from last_err


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise not_found("工单不存在", "TICKET_NOT_FOUND")
    return ticket


def assert_owner_or_admin(ticket: Ticket, user: CurrentUser) -> None:
    if user.is_admin:
        return
    if ticket.creator_user_id != user.id:
        raise forbidden("无权访问该工单", "NOT_OWNER")


def list_user_tickets(
    db: Session,
    user: CurrentUser,
    *,
    status: str | None,
    category: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Ticket], int]:
    q = select(Ticket).where(Ticket.creator_user_id == user.id)
    if status:
        q = q.where(Ticket.status == status)
    if category:
        q = q.where(Ticket.category == category)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(
        q.options(selectinload(Ticket.orders))
        .order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def list_admin_tickets(
    db: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    claimed_by: int | None = None,
    unclaimed: bool | None = None,
    creator_user_id: int | None = None,
    keyword: str | None = None,
    active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Ticket], int]:
    q = select(Ticket)
    if status:
        q = q.where(Ticket.status == status)
    if category:
        q = q.where(Ticket.category == category)
    if priority:
        q = q.where(Ticket.priority == priority)
    if claimed_by is not None:
        q = q.where(Ticket.claimed_by_user_id == claimed_by)
    if unclaimed:
        q = q.where(Ticket.claimed_by_user_id.is_(None))
    if creator_user_id is not None:
        q = q.where(Ticket.creator_user_id == creator_user_id)
    if active:
        q = q.where(Ticket.status.not_in([TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]))
    if keyword:
        like = f"%{keyword}%"
        by_order = select(TicketOrder.ticket_id).where(TicketOrder.out_trade_no.ilike(like))
        q = q.where(Ticket.title.ilike(like) | Ticket.ticket_no.ilike(like) | Ticket.id.in_(by_order))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(
        q.options(selectinload(Ticket.orders))
        .order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def load_ticket_detail(db: Session, ticket_id: int, *, include_internal: bool) -> Ticket:
    ticket = db.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.messages),
            selectinload(Ticket.attachments),
            selectinload(Ticket.events),
            selectinload(Ticket.orders),
        )
    )
    if not ticket:
        raise not_found("工单不存在", "TICKET_NOT_FOUND")
    if not include_internal:
        ticket.messages = [m for m in ticket.messages if not m.is_internal]
        # filter events that leak internal notes
        ticket.events = [
            e
            for e in ticket.events
            if e.event_type != TicketEventType.INTERNAL_NOTE_ADDED.value
        ]
    return ticket


def reply_ticket(
    db: Session,
    ticket: Ticket,
    user: CurrentUser,
    content: str,
    *,
    is_internal: bool = False,
) -> TicketMessage:
    if ticket.status == TicketStatus.CLOSED.value:
        raise bad_request("工单已关闭", "TICKET_CLOSED")
    if is_internal and not user.is_admin:
        raise forbidden("仅管理员可写内部备注")
    if not user.is_admin and ticket.creator_user_id != user.id:
        raise forbidden()
    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_user_id=user.id,
        sender_role=user.sub2api_role,
        content=content.strip(),
        is_internal=is_internal,
    )
    db.add(msg)
    if is_internal:
        et = TicketEventType.INTERNAL_NOTE_ADDED.value
    elif user.is_admin:
        et = TicketEventType.ADMIN_REPLIED.value
    else:
        et = TicketEventType.USER_REPLIED.value
    add_event(db, ticket.id, user.id, et, new_value={"message_preview": content[:80]})
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def _record_close(db: Session, ticket: Ticket, user: CurrentUser, *, by_admin: bool) -> None:
    ticket.status = TicketStatus.CLOSED.value
    ticket.closed_by = ClosedBy.ADMIN.value if by_admin else ClosedBy.USER.value
    ticket.closed_at = datetime.now(timezone.utc)
    ticket.updated_at = datetime.now(timezone.utc)
    et = TicketEventType.CLOSED_BY_ADMIN.value if by_admin else TicketEventType.CLOSED_BY_USER.value
    add_event(db, ticket.id, user.id, et)


def close_ticket(db: Session, ticket: Ticket, user: CurrentUser, *, by_admin: bool) -> Ticket:
    if ticket.status == TicketStatus.CLOSED.value:
        raise bad_request("工单已关闭", "TICKET_CLOSED")
    if not by_admin and ticket.creator_user_id != user.id:
        raise forbidden()
    _record_close(db, ticket, user, by_admin=by_admin)
    db.commit()
    db.refresh(ticket)
    return ticket


def claim_ticket(db: Session, ticket_id: int, admin: CurrentUser) -> Ticket:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.claimed_by_user_id.is_(None),
            Ticket.status != TicketStatus.CLOSED.value,
        )
        .values(claimed_by_user_id=admin.id, claimed_at=now, updated_at=now)
    )
    if result.rowcount != 1:
        # distinguish closed vs already claimed
        t = get_ticket_or_404(db, ticket_id)
        if t.status == TicketStatus.CLOSED.value:
            raise conflict("工单已关闭", "TICKET_CLOSED")
        raise conflict("工单已被认领", "TICKET_ALREADY_CLAIMED")
    add_event(db, ticket_id, admin.id, TicketEventType.CLAIMED.value, new_value={"claimed_by": admin.id})
    db.commit()
    return get_ticket_or_404(db, ticket_id)


def unclaim_ticket(db: Session, ticket_id: int, admin: CurrentUser) -> Ticket:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.claimed_by_user_id == admin.id,
            Ticket.status != TicketStatus.CLOSED.value,
        )
        .values(claimed_by_user_id=None, claimed_at=None, updated_at=now)
    )
    if result.rowcount != 1:
        raise conflict("无法释放（非认领人或已关闭）", "UNCLAIM_FAILED")
    add_event(db, ticket_id, admin.id, TicketEventType.UNCLAIMED.value)
    db.commit()
    return get_ticket_or_404(db, ticket_id)


def takeover_ticket(db: Session, ticket_id: int, admin: CurrentUser) -> Ticket:
    now = datetime.now(timezone.utc)
    t = get_ticket_or_404(db, ticket_id)
    if t.status == TicketStatus.CLOSED.value:
        raise conflict("工单已关闭", "TICKET_CLOSED")
    old = t.claimed_by_user_id
    if old == admin.id:
        return t
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.status != TicketStatus.CLOSED.value,
            Ticket.claimed_by_user_id.is_distinct_from(admin.id),
        )
        .values(claimed_by_user_id=admin.id, claimed_at=now, updated_at=now)
    )
    if result.rowcount != 1:
        raise conflict("接管失败", "TAKEOVER_FAILED")
    add_event(
        db,
        ticket_id,
        admin.id,
        TicketEventType.TAKEN_OVER.value,
        old_value={"claimed_by": old},
        new_value={"claimed_by": admin.id},
    )
    db.commit()
    return get_ticket_or_404(db, ticket_id)


def patch_ticket_admin(db: Session, ticket: Ticket, admin: CurrentUser, data) -> Ticket:
    if ticket.status == TicketStatus.CLOSED.value:
        raise bad_request("工单已关闭，不可修改", "TICKET_CLOSED")
    if data.status is not None:
        try:
            new_status = TicketStatus(data.status)
        except ValueError as exc:
            raise bad_request("无效状态", "INVALID_STATUS") from exc
        cur = TicketStatus(ticket.status)
        if new_status != cur:
            if new_status not in TICKET_STATUS_TRANSITIONS.get(cur, set()) and new_status != TicketStatus.CLOSED:
                # allow direct CLOSED from any non-closed
                if new_status != TicketStatus.CLOSED:
                    raise bad_request(f"不允许从 {cur} 转到 {new_status}", "INVALID_TRANSITION")
            old = ticket.status
            if new_status == TicketStatus.CLOSED:
                _record_close(db, ticket, admin, by_admin=True)
            else:
                ticket.status = new_status.value
            if new_status == TicketStatus.RESOLVED:
                ticket.resolved_at = datetime.now(timezone.utc)
            add_event(
                db,
                ticket.id,
                admin.id,
                TicketEventType.STATUS_CHANGED.value,
                old_value={"status": old},
                new_value={"status": ticket.status},
            )
    if data.category is not None:
        # Admins may move a ticket to any configured category, disabled ones included.
        _, config = form_config.live_config(db)
        if not config.category(data.category):
            raise bad_request("无效分类", "INVALID_CATEGORY")
        if data.category != ticket.category:
            old = ticket.category
            ticket.category = data.category
            add_event(
                db,
                ticket.id,
                admin.id,
                TicketEventType.CATEGORY_CHANGED.value,
                old_value={"category": old},
                new_value={"category": ticket.category},
            )
    if data.priority is not None:
        try:
            pri = TicketPriority(data.priority)
        except ValueError as exc:
            raise bad_request("无效优先级", "INVALID_PRIORITY") from exc
        if pri.value != ticket.priority:
            old = ticket.priority
            ticket.priority = pri.value
            add_event(
                db,
                ticket.id,
                admin.id,
                TicketEventType.PRIORITY_CHANGED.value,
                old_value={"priority": old},
                new_value={"priority": ticket.priority},
            )
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return ticket


def meta_for_user(db: Session, *, is_admin: bool) -> dict:
    version, config = form_config.live_config(db)
    # Disabled categories stay listed so existing tickets keep their labels; the create form hides them.
    cats = [{"value": c.key, "label": c.label, **c.model_dump(mode="json", by_alias=True, exclude_none=True)}
            for c in config.categories]
    priorities = [{"value": p.value, "label": p.value} for p in TicketPriority]
    if not is_admin:
        priorities = [p for p in priorities if p["value"] == "P2"]
    statuses = [{"value": s.value, "label": s.value} for s in TicketStatus]
    return {"form_version": version, "categories": cats, "priorities": priorities, "statuses": statuses,
            "order_lookup": get_admin_client() is not None}
