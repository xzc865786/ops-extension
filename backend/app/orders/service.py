"""Order checks for refund / invoice / payment tickets against Sub2API."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import deque
from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.common.enums import TicketStatus
from app.common.errors import AppError, bad_request, conflict, not_found
from app.db.models.ticket import Ticket, TicketOrder
from app.db.models.user import ExtensionUser
from app.deps import CurrentUser
from app.orders.sub2api import Sub2APIError, Sub2APIUnavailable, admin_reason, get_admin_client
from app.tickets.form_schema import ORDER_NO_RE

logger = logging.getLogger(__name__)

PURPOSES = {"refund": "REFUND", "invoice": "INVOICE", "payment": "PAYMENT"}
PURPOSE_LABELS = {"REFUND": "退款", "INVOICE": "开票", "PAYMENT": "充值/支付"}
ORDER_FIELDS = {"refund": "order_no", "invoice": "order_nos", "payment": "order_no"}
# Only these fields are kept: no payer email/name, pay URLs, QR codes or provider internals.
SNAPSHOT_FIELDS = (
    "id", "user_id", "out_trade_no", "amount", "pay_amount", "bonus_amount", "refund_amount", "currency",
    "status", "order_type", "payment_type", "created_at", "paid_at", "completed_at", "refund_at",
)
AMOUNT_FIELDS = ("amount", "pay_amount", "bonus_amount", "refund_amount")
CENT = Decimal("0.01")

LOOKUPS_PER_MINUTE = 30
_hits: dict[int, deque] = {}
_hits_lock = threading.Lock()


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CENT)
    except InvalidOperation:
        return Decimal("0.00")


def invoiceable_amount(order: dict) -> Decimal:
    """Paid amount still standing after refunds (refunds are in credited-amount units, scaled to paid)."""
    amount, pay, refund = _money(order.get("amount")), _money(order.get("pay_amount")), _money(order.get("refund_amount"))
    if amount <= 0 or pay <= 0:
        return Decimal("0.00")
    refunded = (pay * refund / amount).quantize(CENT)
    return max(pay - refunded, Decimal("0.00"))


def snapshot(order: dict) -> dict:
    snap = {k: order.get(k) for k in SNAPSHOT_FIELDS if order.get(k) is not None}
    for k in AMOUNT_FIELDS:
        if k in snap:
            snap[k] = str(_money(snap[k]))
    snap["invoiceable_amount"] = str(invoiceable_amount(order))
    return snap


def problem(kind: str, snap: dict) -> str | None:
    """Why this order cannot back a ticket of this kind, or None."""
    status = snap.get("status")
    if kind == "refund":
        if status in ("COMPLETED", "REFUND_REQUESTED", "REFUND_FAILED"):
            return None
        if status in ("PARTIALLY_REFUNDED", "REFUNDED"):
            return "该订单已退款，不能再次申请"
        if status in ("REFUNDING", "REFUND_PENDING"):
            return "该订单正在退款中"
        if status in ("PAID", "RECHARGING"):
            return "该订单还在充值处理中，请稍后再试"
        return "该订单未支付成功，不能申请退款"
    if kind == "invoice":
        if status == "REFUNDED":
            return "该订单已全额退款，不能开票"
        if status not in ("COMPLETED", "PARTIALLY_REFUNDED"):
            return "该订单未完成支付，暂不能开票"
        if Decimal(snap.get("invoiceable_amount") or "0") <= 0:
            return "该订单没有可开票金额"
    return None


def order_nos(kind: str, form_data: dict) -> list[str]:
    field = ORDER_FIELDS.get(kind)
    value = form_data.get(field) if field else None
    if not value:
        return []
    return list(value) if isinstance(value, list) else [value]


def _rate_limit(user_id: int, cost: int = 1) -> None:
    now = time.monotonic()
    with _hits_lock:
        hits = _hits.setdefault(user_id, deque())
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) + cost > LOOKUPS_PER_MINUTE:
            raise AppError(429, "查询订单过于频繁，请 1 分钟后再试", "ORDER_LOOKUP_RATE_LIMITED")
        hits.extend([now] * cost)


def _user_call(fn, *args):
    """Call Sub2API on a user's behalf: details go to the log, the user gets a generic message."""
    try:
        return fn(*args)
    except (Sub2APIUnavailable, Sub2APIError) as exc:
        logger.error("order check failed: %s", admin_reason(exc))
        raise AppError(503, "订单校验服务暂时不可用，请稍后再试", "ORDER_SERVICE_UNAVAILABLE") from exc


def active_duplicate(db: Session, purpose: str, nos: list[str], *, exclude_ticket_id: int | None = None):
    """(out_trade_no, ticket_no) of a ticket already handling one of these orders for this purpose.

    Payment tickets may repeat. A refund / invoice ticket blocks while open, and for good once it
    has been resolved, even if closed afterwards.
    """
    if purpose == "PAYMENT" or not nos:
        return None
    q = (
        select(TicketOrder.out_trade_no, Ticket.ticket_no)
        .join(Ticket, Ticket.id == TicketOrder.ticket_id)
        .where(TicketOrder.purpose == purpose, TicketOrder.out_trade_no.in_(nos),
               or_(Ticket.status != TicketStatus.CLOSED.value, Ticket.resolved_at.is_not(None)))
        .order_by(Ticket.id)
    )
    if exclude_ticket_id is not None:
        q = q.where(Ticket.id != exclude_ticket_id)
    row = db.execute(q.limit(1)).first()
    return tuple(row) if row else None


def _duplicate_message(purpose: str, dup: tuple) -> str:
    return f"订单 {dup[0]} 已有{PURPOSE_LABELS[purpose]}工单 {dup[1]}，请在原工单中跟进"


def lookup(db: Session, user: CurrentUser, kind: str, out_trade_no: str) -> dict:
    client = get_admin_client()
    if client is None:
        raise bad_request("未开启订单查询", "ORDER_LOOKUP_DISABLED")
    if kind not in PURPOSES:
        raise bad_request("无效的业务类型", "INVALID_KIND")
    out_trade_no = (out_trade_no or "").strip()
    if not ORDER_NO_RE.match(out_trade_no):
        raise bad_request("订单号格式不正确", "INVALID_ORDER_NO")
    _rate_limit(user.id)
    order = _user_call(client.find_user_order, user.sub2api_user_id, out_trade_no)
    if not order:
        raise not_found("未找到该订单，请确认订单号，并且是当前账号下的订单", "ORDER_NOT_FOUND")
    snap = snapshot(order)
    reason = problem(kind, snap)
    if not reason:
        dup = active_duplicate(db, PURPOSES[kind], [out_trade_no])
        reason = _duplicate_message(PURPOSES[kind], dup) if dup else None
    return {"order": snap, "problem": reason}


def verify_orders(user: CurrentUser, kind: str, nos: list[str]) -> list[dict]:
    """Check each order exists, belongs to the user and suits the ticket kind.

    Returns rows for ``attach``. Without an admin key the orders are accepted unverified.
    """
    client = get_admin_client()
    if client is None:
        return [{"out_trade_no": no, "sub2api_order_id": None, "snapshot": None} for no in nos]
    _rate_limit(user.id, len(nos))
    rows = []
    for no in nos:
        order = _user_call(client.find_user_order, user.sub2api_user_id, no)
        if not order:
            raise AppError(422, f"未找到订单 {no}，请确认订单号，并且是当前账号下的订单", "ORDER_NOT_FOUND")
        snap = snapshot(order)
        reason = problem(kind, snap)
        if reason:
            raise AppError(422, f"订单 {no}：{reason}", "ORDER_NOT_ELIGIBLE")
        rows.append({"out_trade_no": no, "sub2api_order_id": int(order["id"]), "snapshot": snap})
    if len({r["snapshot"].get("currency") for r in rows}) > 1:
        raise AppError(422, "不同币种的订单请分开申请", "ORDER_CURRENCY_MIXED")
    return rows


def lock_and_check_duplicates(db: Session, kind: str, nos: list[str]) -> None:
    """Serialise submissions for the same orders, then refuse duplicates (call inside the insert transaction)."""
    purpose = PURPOSES[kind]
    if purpose == "PAYMENT":
        return
    if db.get_bind().dialect.name == "postgresql":
        for no in sorted(nos):
            key = int(hashlib.sha256(f"ticket-order:{purpose}:{no}".encode()).hexdigest()[:15], 16)
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    dup = active_duplicate(db, purpose, nos)
    if dup:
        raise conflict(_duplicate_message(purpose, dup), "ORDER_DUPLICATE")


def attach(db: Session, ticket: Ticket, kind: str, rows: list[dict]) -> None:
    for row in rows:
        db.add(TicketOrder(ticket_id=ticket.id, purpose=PURPOSES[kind], **row))


def live_orders(db: Session, ticket: Ticket) -> list[dict]:
    """Current state of the ticket's orders, read from Sub2API (admin view)."""
    client = get_admin_client()
    if client is None:
        raise bad_request("未配置 Sub2API Admin API Key，无法查询订单实时状态", "ORDER_LOOKUP_DISABLED")
    creator = db.get(ExtensionUser, ticket.creator_user_id)
    out = []
    try:
        for row in ticket.orders:
            if row.sub2api_order_id:
                order = client.get_order(row.sub2api_order_id)
            else:
                order = client.find_user_order(creator.sub2api_user_id, row.out_trade_no) if creator else None
            out.append({"id": row.id, "out_trade_no": row.out_trade_no,
                        "order": snapshot(order) if order else None})
    except (Sub2APIUnavailable, Sub2APIError) as exc:
        raise AppError(503, admin_reason(exc), "ORDER_SERVICE_UNAVAILABLE") from exc
    return out
