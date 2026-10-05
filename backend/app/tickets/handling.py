"""Admin handling of refund and invoice tickets: refunds through Sub2API, rejections, invoice records.

Sub2API's order status is the source of truth for a refund. Every request is recorded as a
``TicketRefundOperation`` before it is sent, so a timeout or crash leaves a visible open operation
that the admin settles with "sync" instead of refunding twice.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import TicketEventType, TicketStatus
from app.common.errors import AppError, bad_request, conflict
from app.db.models.ticket import Ticket, TicketAttachment, TicketMessage, TicketOrder, TicketRefundOperation
from app.db.models.user import ExtensionUser
from app.deps import CurrentUser
from app.orders.service import invoiceable_amount, problem, snapshot
from app.orders.sub2api import Sub2APIError, Sub2APIUnavailable, admin_reason, get_admin_client
from app.tickets.service import add_event, get_ticket_or_404

CHINA_TZ = timezone(timedelta(hours=8))
CENT = Decimal("0.01")
OPEN_RESULTS = ("IN_PROGRESS", "PENDING", "UNKNOWN")
REFUNDED_STATUSES = ("REFUNDED", "PARTIALLY_REFUNDED")
PENDING_STATUSES = ("REFUND_PENDING", "REFUNDING")
INVOICE_NO_RE = re.compile(r"^[A-Za-z0-9-]{4,40}$")
KIND_LABELS = {"refund": "退款", "invoice": "开票"}

FORCE_WARNINGS = {
    "balance is insufficient": "用户余额不足以扣减退款金额。强制执行会只扣减用户现有的余额，然后照常退款。",
    "cannot find active subscription": "找不到用户的有效订阅，无法扣减订阅天数。强制执行会跳过扣减，然后照常退款。",
    "cannot fetch user balance": "无法读取用户余额。强制执行会跳过余额检查，然后照常退款。",
}


def ticket_kind(ticket: Ticket) -> str:
    return (ticket.form_schema or {}).get("kind", "general")


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CENT)
    except InvalidOperation:
        return Decimal("0.00")


def _parse_amount(raw) -> Decimal:
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise bad_request("金额格式不正确", "INVALID_AMOUNT") from exc
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(CENT):
        raise bad_request("金额须大于 0，最多两位小数", "INVALID_AMOUNT")
    return amount.quantize(CENT)


def gateway_amount(order: dict, refund_amount: Decimal) -> Decimal:
    """Money returned to the payer: Sub2API scales the credited refund to the amount actually paid."""
    amount, pay = _money(order.get("amount")), _money(order.get("pay_amount"))
    if amount <= 0 or pay <= 0:
        return refund_amount
    if abs(refund_amount - amount) <= CENT:
        return pay
    return (pay * refund_amount / amount).quantize(CENT, rounding=ROUND_HALF_UP)


def _fmt(amount, currency: str | None = None) -> str:
    return f"¥{amount}" if (currency or "CNY") == "CNY" else f"{currency} {amount}"


def _name(user: CurrentUser) -> str | None:
    return user.username_snapshot or user.email_snapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client():
    client = get_admin_client()
    if client is None:
        raise bad_request("未配置 Sub2API Admin API Key，无法在工单中退款", "ORDER_LOOKUP_DISABLED")
    return client


def _admin_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (Sub2APIUnavailable, Sub2APIError) as exc:
        raise AppError(503, admin_reason(exc), "ORDER_SERVICE_UNAVAILABLE") from exc


def _require(ticket: Ticket, kind: str) -> None:
    if ticket_kind(ticket) != kind:
        raise bad_request(f"这不是{KIND_LABELS[kind]}工单", "WRONG_TICKET_KIND")
    if ticket.status == TicketStatus.CLOSED.value:
        raise bad_request("工单已关闭", "TICKET_CLOSED")
    if ticket.resolution:
        raise conflict("这张工单已经登记过处理结果", "TICKET_ALREADY_RESOLVED")


def _open_operation(db: Session, ticket_id: int) -> TicketRefundOperation | None:
    return db.scalar(
        select(TicketRefundOperation)
        .where(TicketRefundOperation.ticket_id == ticket_id, TicketRefundOperation.result.in_(OPEN_RESULTS))
        .order_by(TicketRefundOperation.id.desc()).limit(1)
    )


def _refund_order(db: Session, client, ticket: Ticket) -> TicketOrder:
    row = next((o for o in ticket.orders if o.purpose == "REFUND"), None)
    if not row:
        raise bad_request("这张工单没有关联订单，无法在工单中退款", "NO_ORDER")
    if row.sub2api_order_id is None:
        # Submitted before order checks were configured: resolve it now, still scoped to the ticket's owner.
        creator = db.get(ExtensionUser, ticket.creator_user_id)
        order = _admin_call(client.find_user_order, creator.sub2api_user_id, row.out_trade_no) if creator else None
        if not order:
            raise bad_request(f"Sub2API 中找不到工单创建人的订单 {row.out_trade_no}", "ORDER_NOT_FOUND")
        row.sub2api_order_id = int(order["id"])
        row.snapshot = snapshot(order)
        db.commit()
    return row


def _set_status(db: Session, ticket: Ticket, admin: CurrentUser, status: TicketStatus) -> None:
    if ticket.status == status.value:
        return
    old = ticket.status
    ticket.status = status.value
    if status == TicketStatus.RESOLVED:
        ticket.resolved_at = _now()
    add_event(db, ticket.id, admin.id, TicketEventType.STATUS_CHANGED.value,
              old_value={"status": old}, new_value={"status": status.value})


def _reply(db: Session, ticket: Ticket, admin: CurrentUser, content: str) -> None:
    db.add(TicketMessage(ticket_id=ticket.id, sender_user_id=admin.id, sender_role=admin.sub2api_role,
                         content=content, is_internal=False))
    add_event(db, ticket.id, admin.id, TicketEventType.ADMIN_REPLIED.value, new_value={"message_preview": content[:80]})


def _resolve(db: Session, ticket: Ticket, admin: CurrentUser, resolution: dict, reply: str, event: str) -> None:
    ticket.resolution = {**resolution, "operator_user_id": admin.id, "operator_name": _name(admin),
                         "at": _now().isoformat()}
    ticket.updated_at = _now()
    add_event(db, ticket.id, admin.id, event, new_value={"outcome": resolution["outcome"]})
    _reply(db, ticket, admin, reply)
    _set_status(db, ticket, admin, TicketStatus.RESOLVED)


def _finalize_refund(db: Session, ticket: Ticket, admin: CurrentUser, order: dict, *, source: str,
                     op: TicketRefundOperation | None) -> None:
    refund_amount = _money(order.get("refund_amount")) or (op.amount if op else Decimal("0.00"))
    back = gateway_amount(order, refund_amount)
    summary = (op.response_summary or {}) if op else {}
    balance = summary.get("balance_deducted")
    days = summary.get("subscription_days_deducted")
    currency = order.get("currency")
    no = order.get("out_trade_no") or (op.out_trade_no if op else "")
    reply = f"已为订单 {no} 办理退款，原路退回 {_fmt(back, currency)}，到账时间以支付渠道为准（通常 1–3 个工作日）。"
    if balance:
        reply += f"账户余额相应扣减 {_money(balance)}。"
    if days:
        reply += f"订阅相应扣减 {days} 天。"
    _resolve(db, ticket, admin, {
        "outcome": "REFUNDED", "source": source, "out_trade_no": no, "currency": currency,
        "refund_amount": str(refund_amount), "gateway_amount": str(back),
        "balance_deducted": str(_money(balance)) if balance else None, "subscription_days_deducted": days,
    }, reply, TicketEventType.REFUND_SUCCEEDED.value)


def _translate_warning(warning: str | None) -> str:
    text = (warning or "").lower()
    for needle, message in FORCE_WARNINGS.items():
        if needle in text:
            return message
    if "pending" in text:
        return "支付渠道正在处理退款，请稍后点“同步结果”确认"
    if "gateway failed" in text:
        return f"支付渠道退款失败，已自动回滚（{warning[:200]}）"
    return warning or ""


def _settle(db: Session, ticket: Ticket, admin: CurrentUser, op: TicketRefundOperation, order: dict | None,
            *, source: str) -> None:
    """Record what Sub2API's order status says about a refund operation."""
    status = (order or {}).get("status")
    if status in REFUNDED_STATUSES:
        op.result = "SUCCESS"
        op.message = None
        _finalize_refund(db, ticket, admin, order, source=source, op=op)
    elif status in PENDING_STATUSES:
        op.result = "PENDING"
        op.message = "支付渠道正在处理退款，请稍后点“同步结果”确认"
        add_event(db, ticket.id, admin.id, TicketEventType.REFUND_PENDING.value, new_value={"operation_id": op.id})
        if ticket.status in (TicketStatus.OPEN.value, TicketStatus.WAITING_USER.value):
            _set_status(db, ticket, admin, TicketStatus.PROCESSING)
    elif order is None:
        op.result = "UNKNOWN"
        op.message = "无法读取订单状态，退款结果未知，请稍后点“同步结果”确认，确认前不要重复退款"
    else:
        op.result = "FAILED"
        warning = _translate_warning((op.response_summary or {}).get("warning"))
        op.message = warning or f"Sub2API 中订单未退款（状态：{status}）"
        add_event(db, ticket.id, admin.id, TicketEventType.REFUND_FAILED.value, new_value={"operation_id": op.id})


def execute_refund(db: Session, ticket_id: int, admin: CurrentUser, *, amount, deduct_balance: bool,
                   force: bool, reason: str) -> TicketRefundOperation:
    client = _client()
    ticket = get_ticket_or_404(db, ticket_id)
    _require(ticket, "refund")
    if _open_operation(db, ticket.id):
        raise conflict("有未完成的退款操作，请先点“同步结果”确认", "REFUND_IN_PROGRESS")
    row = _refund_order(db, client, ticket)
    amount = _parse_amount(amount)
    order = _admin_call(client.get_order, row.sub2api_order_id)
    if not order:
        raise bad_request("Sub2API 中找不到该订单", "ORDER_NOT_FOUND")
    reason_problem = problem("refund", snapshot(order))
    if reason_problem:
        raise bad_request(reason_problem, "ORDER_NOT_ELIGIBLE")
    if amount > _money(order.get("amount")):
        raise bad_request(f"退款金额不能超过订单到账额度 {_money(order.get('amount'))}", "REFUND_AMOUNT_EXCEEDED")

    # Serialise per ticket; a second click waits here, then sees the open operation.
    locked = db.scalar(select(Ticket).where(Ticket.id == ticket.id).with_for_update())
    if locked.resolution:
        raise conflict("这张工单已经登记过处理结果", "TICKET_ALREADY_RESOLVED")
    if _open_operation(db, ticket.id):
        raise conflict("有未完成的退款操作，请先点“同步结果”确认", "REFUND_IN_PROGRESS")
    full_reason = f"工单 {ticket.ticket_no} · {_name(admin) or admin.id} · {(reason or '').strip()}".strip(" ·")[:200]
    op = TicketRefundOperation(
        ticket_id=ticket.id, sub2api_order_id=row.sub2api_order_id, out_trade_no=row.out_trade_no,
        amount=amount, deduct_balance=deduct_balance, force=force, reason=full_reason, result="IN_PROGRESS",
        operator_user_id=admin.id, operator_name=_name(admin),
    )
    db.add(op)
    db.flush()
    add_event(db, ticket.id, admin.id, TicketEventType.REFUND_SUBMITTED.value,
              new_value={"operation_id": op.id, "amount": str(amount), "deduct_balance": deduct_balance, "force": force})
    db.commit()

    try:
        data = client.refund(row.sub2api_order_id, amount=amount, reason=full_reason,
                             deduct_balance=deduct_balance, force=force)
    except Sub2APIUnavailable:
        op.result = "UNKNOWN"
        op.message = "请求 Sub2API 失败或超时，退款结果未知。请点“同步结果”确认，确认前不要重复退款"
        db.commit()
        return op
    except Sub2APIError as exc:
        op.result = "FAILED"
        op.message = admin_reason(exc)
        add_event(db, ticket.id, admin.id, TicketEventType.REFUND_FAILED.value, new_value={"operation_id": op.id})
        db.commit()
        return op

    op.response_summary = {k: data.get(k) for k in
                           ("success", "warning", "require_force", "balance_deducted", "subscription_days_deducted")
                           if data.get(k) is not None}
    if data.get("require_force"):
        op.result = "REQUIRE_FORCE"
        op.message = _translate_warning(data.get("warning"))
        db.commit()
        return op
    try:
        current = client.get_order(row.sub2api_order_id)
    except (Sub2APIUnavailable, Sub2APIError):
        current = None
    if current is None and data.get("success"):
        # Sub2API confirmed the refund but the follow-up read failed: record what it confirmed.
        current = {**order, "status": "REFUNDED" if amount >= _money(order.get("amount")) else "PARTIALLY_REFUNDED",
                   "refund_amount": str(amount)}
    _settle(db, ticket, admin, op, current, source="SUB2API")
    db.commit()
    return op


def sync_refund(db: Session, ticket_id: int, admin: CurrentUser) -> dict:
    """Re-read the order (finalising a pending gateway refund first) and record the outcome."""
    client = _client()
    ticket = get_ticket_or_404(db, ticket_id)
    _require(ticket, "refund")
    row = _refund_order(db, client, ticket)
    order = _admin_call(client.get_order, row.sub2api_order_id)
    if not order:
        raise bad_request("Sub2API 中找不到该订单", "ORDER_NOT_FOUND")
    note = None
    if order.get("status") == "REFUND_PENDING":
        try:
            client.query_refund(row.sub2api_order_id)
        except Sub2APIError as exc:
            note = admin_reason(exc)
        except Sub2APIUnavailable as exc:
            raise AppError(503, admin_reason(exc), "ORDER_SERVICE_UNAVAILABLE") from exc
        order = _admin_call(client.get_order, row.sub2api_order_id) or order

    op = _open_operation(db, ticket.id)
    status = order.get("status")
    if op:
        _settle(db, ticket, admin, op, order, source="SUB2API")
    elif status in REFUNDED_STATUSES:
        # Refunded outside the ticket (for example in the Sub2API admin pages).
        _finalize_refund(db, ticket, admin, order, source="SYNC", op=None)
    db.commit()
    return {"order": snapshot(order), "note": note,
            "outcome": "REFUNDED" if status in REFUNDED_STATUSES else
                       "PENDING" if status in PENDING_STATUSES else "NOT_REFUNDED"}


def reject(db: Session, ticket_id: int, admin: CurrentUser, reason: str) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)
    kind = ticket_kind(ticket)
    if kind not in KIND_LABELS:
        raise bad_request("只有退款和开票工单可以驳回", "WRONG_TICKET_KIND")
    _require(ticket, kind)
    reason = (reason or "").strip()
    if not reason:
        raise bad_request("请填写驳回原因", "REASON_REQUIRED")
    if kind == "refund" and _open_operation(db, ticket.id):
        raise conflict("有未完成的退款操作，请先点“同步结果”确认", "REFUND_IN_PROGRESS")
    _resolve(db, ticket, admin, {"outcome": "REJECTED", "reason": reason},
             f"您的{KIND_LABELS[kind]}申请未通过：{reason}", TicketEventType.REQUEST_REJECTED.value)
    db.commit()
    db.refresh(ticket)
    return ticket


def register_manual_refund(db: Session, ticket_id: int, admin: CurrentUser, amount, note: str | None) -> Ticket:
    """Record a refund done outside Ops when order checks are not configured."""
    if get_admin_client() is not None:
        raise bad_request("已配置订单查询，请点“同步结果”登记在 Sub2API 后台完成的退款", "USE_SYNC")
    ticket = get_ticket_or_404(db, ticket_id)
    _require(ticket, "refund")
    amount = _parse_amount(amount)
    no = next((o.out_trade_no for o in ticket.orders if o.purpose == "REFUND"), "")
    reply = f"已为{'订单 ' + no if no else '您'}办理退款 {_fmt(amount)}，到账时间以支付渠道为准（通常 1–3 个工作日）。"
    _resolve(db, ticket, admin, {"outcome": "REFUNDED", "source": "MANUAL", "out_trade_no": no, "currency": "CNY",
                                 "refund_amount": str(amount), "gateway_amount": str(amount),
                                 "note": (note or "").strip()[:200] or None},
             reply, TicketEventType.REFUND_REGISTERED.value)
    db.commit()
    db.refresh(ticket)
    return ticket


def issue_invoice(db: Session, ticket_id: int, admin: CurrentUser, *, invoice_no: str, issued_on: date,
                  amount, attachment_id: int, emailed: bool) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)
    _require(ticket, "invoice")
    invoice_no = (invoice_no or "").strip()
    if not INVOICE_NO_RE.match(invoice_no):
        raise bad_request("发票号码只能包含字母、数字和 -（4 到 40 位）", "INVALID_INVOICE_NO")
    if issued_on > datetime.now(CHINA_TZ).date():
        raise bad_request("开票日期不能晚于今天", "INVALID_DATE")
    amount = _parse_amount(amount)
    rows = [o for o in ticket.orders if o.purpose == "INVOICE"]
    if rows and all(o.snapshot for o in rows):
        total = sum((invoiceable_amount(o.snapshot) for o in rows), Decimal("0.00"))
        if amount > total:
            raise bad_request(f"开票金额不能超过可开票金额 {total}", "INVOICE_AMOUNT_EXCEEDED")
    attachment = db.get(TicketAttachment, attachment_id)
    if not attachment or attachment.ticket_id != ticket.id:
        raise bad_request("请先上传发票文件", "INVOICE_FILE_REQUIRED")
    if attachment.mime_type != "application/pdf":
        raise bad_request("发票文件须为 PDF", "INVOICE_FILE_REQUIRED")
    if not emailed:
        raise bad_request("请先把发票发送到用户的收票邮箱，再登记", "INVOICE_NOT_EMAILED")
    attachment.kind = "INVOICE_FILE"
    email = (ticket.form_data or {}).get("email")
    reply = f"发票已开具：发票号码 {invoice_no}，金额 {_fmt(amount)}。"
    reply += f"已发送至 {email}，" if email else ""
    reply += "也可以在本工单的附件中下载。"
    _resolve(db, ticket, admin, {"outcome": "ISSUED", "invoice_no": invoice_no, "issued_on": issued_on.isoformat(),
                                 "amount": str(amount), "email": email, "attachment_id": attachment.id,
                                 "file_name": attachment.file_name},
             reply, TicketEventType.INVOICE_ISSUED.value)
    db.commit()
    db.refresh(ticket)
    return ticket
