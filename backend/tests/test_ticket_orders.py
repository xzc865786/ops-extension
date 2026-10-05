import logging

import httpx
import pytest

from app.common.enums import TicketStatus
from app.db.models.ticket import Ticket, TicketOrder
from app.orders import service as orders_service
from app.orders.sub2api import Sub2APIAdminClient
from tests.conftest import login_as, make_user

BASE = "/ext/api/v1"
KEY = "admin-key-should-never-leak"


class FakeSub2API:
    def __init__(self):
        self.orders: dict[int, dict] = {}
        self.mode = "ok"  # ok | down | badkey
        self.calls: list[httpx.Request] = []

    def add(self, id, user_id, out_trade_no, *, status="COMPLETED", amount=100, pay_amount=100,
            refund_amount=0, currency="CNY", order_type="balance"):
        self.orders[id] = {
            "id": id, "user_id": user_id, "out_trade_no": out_trade_no, "amount": amount,
            "pay_amount": pay_amount, "bonus_amount": 0, "refund_amount": refund_amount, "currency": currency,
            "status": status, "order_type": order_type, "payment_type": "alipay",
            "user_email": "payer@example.com", "pay_url": "https://pay.example/secret",
            "created_at": "2026-10-01T10:00:00Z", "paid_at": "2026-10-01T10:01:00Z",
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.mode == "down":
            raise httpx.ConnectError("boom", request=request)
        if request.headers.get("x-api-key") != KEY or self.mode == "badkey":
            return httpx.Response(401, json={"code": 401, "message": "Invalid admin API key", "reason": "INVALID_ADMIN_KEY"})
        path = request.url.path
        if path == "/api/v1/admin/payment/orders":
            uid = int(request.url.params["user_id"])
            kw = request.url.params["keyword"].lower()
            items = [o for o in self.orders.values() if o["user_id"] == uid and kw in o["out_trade_no"].lower()]
            return httpx.Response(200, json={"code": 0, "message": "success",
                                             "data": {"items": items, "total": len(items), "page": 1, "page_size": 50}})
        if path.startswith("/api/v1/admin/payment/orders/"):
            order = self.orders.get(int(path.rsplit("/", 1)[1]))
            if not order:
                return httpx.Response(404, json={"code": 404, "message": "order not found", "reason": "NOT_FOUND"})
            return httpx.Response(200, json={"code": 0, "message": "success", "data": {"order": order, "auditLogs": []}})
        return httpx.Response(404, json={"code": 404, "message": "not found"})


@pytest.fixture(autouse=True)
def reset_rate_limit():
    orders_service._hits.clear()
    yield
    orders_service._hits.clear()


@pytest.fixture()
def fake(monkeypatch):
    fake = FakeSub2API()
    client = Sub2APIAdminClient("http://sub2api.test", KEY, transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr("app.orders.service.get_admin_client", lambda: client)
    monkeypatch.setattr("app.tickets.service.get_admin_client", lambda: client)
    return fake


def _login(client, db, sub2api_id, role="user"):
    user = make_user(db, sub2api_id=sub2api_id, role=role, username=f"{role}{sub2api_id}")
    client.cookies.clear()
    login_as(client, db, user)
    return user


def _refund(client, order_no, **extra):
    return client.post(f"{BASE}/tickets", json={"category": "REFUND", "form_version": 1, "form_data": {
        "order_no": order_no, "reason": "MISTAKE", "policy_ack": True, **extra}})


def _invoice(client, order_nos):
    return client.post(f"{BASE}/tickets", json={"category": "INVOICE", "form_version": 1, "form_data": {
        "order_nos": order_nos, "title_type": "PERSONAL", "title": "张三", "email": "a@example.com"}})


def test_without_admin_key_orders_are_unverified(client, db):
    _login(client, db, 1)
    assert client.get(f"{BASE}/tickets/meta").json()["order_lookup"] is False
    lookup = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY0001"})
    assert lookup.status_code == 400 and lookup.json()["code"] == "ORDER_LOOKUP_DISABLED"
    resp = _refund(client, "PAY0001")
    assert resp.status_code == 201, resp.text
    assert resp.json()["orders"] == [{"id": 1, "purpose": "REFUND", "out_trade_no": "PAY0001",
                                      "sub2api_order_id": None, "snapshot": None}]
    # duplicates are still refused by order number
    assert _refund(client, "PAY0001").json()["code"] == "ORDER_DUPLICATE"


def test_lookup_only_finds_own_orders(client, db, fake):
    fake.add(11, 1, "PAY1001", amount=100, pay_amount=101.5)
    fake.add(12, 2, "PAY2001")
    _login(client, db, 1)
    assert client.get(f"{BASE}/tickets/meta").json()["order_lookup"] is True
    ok = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY1001"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["problem"] is None
    assert body["order"]["pay_amount"] == "101.50"
    assert "user_email" not in body["order"] and "pay_url" not in body["order"]
    other = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY2001"})
    assert other.status_code == 404 and other.json()["code"] == "ORDER_NOT_FOUND"
    # substring matches are not treated as the order
    partial = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY10"})
    assert partial.status_code == 404


def test_refund_ticket_records_verified_order(client, db, fake):
    fake.add(11, 1, "PAY1001")
    fake.add(12, 2, "PAY2001")
    fake.add(13, 1, "PAY1003", status="REFUNDED", refund_amount=100)
    _login(client, db, 1)
    resp = _refund(client, "PAY1001")
    assert resp.status_code == 201, resp.text
    order = resp.json()["orders"][0]
    assert order["sub2api_order_id"] == 11
    assert order["snapshot"]["status"] == "COMPLETED"
    assert "user_email" not in order["snapshot"]

    not_mine = _refund(client, "PAY2001")
    assert not_mine.status_code == 422 and not_mine.json()["code"] == "ORDER_NOT_FOUND"
    refunded = _refund(client, "PAY1003")
    assert refunded.status_code == 422 and refunded.json()["code"] == "ORDER_NOT_ELIGIBLE"
    assert "已退款" in refunded.json()["detail"]


def test_duplicate_refund_blocked_until_closed_unresolved(client, db, fake):
    fake.add(11, 1, "PAY1001")
    _login(client, db, 1)
    first = _refund(client, "PAY1001").json()
    dup = _refund(client, "PAY1001")
    assert dup.status_code == 409 and dup.json()["code"] == "ORDER_DUPLICATE"
    assert first["ticket_no"] in dup.json()["detail"]
    lookup = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY1001"}).json()
    assert first["ticket_no"] in lookup["problem"]

    # closed without being resolved: may apply again
    assert client.post(f"{BASE}/tickets/{first['id']}/close").status_code == 200
    second = _refund(client, "PAY1001")
    assert second.status_code == 201, second.text

    # resolved then closed: blocked for good
    ticket = db.get(Ticket, second.json()["id"])
    db.refresh(ticket)
    ticket.status = TicketStatus.CLOSED.value
    from datetime import datetime, timezone
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    assert _refund(client, "PAY1001").json()["code"] == "ORDER_DUPLICATE"


def test_invoice_amount_and_checks(client, db, fake):
    fake.add(21, 1, "INV0001", amount=100, pay_amount=102, refund_amount=50, status="PARTIALLY_REFUNDED")
    fake.add(22, 1, "INV0002", amount=50, pay_amount=50)
    fake.add(23, 1, "INV0003", currency="USD")
    fake.add(24, 1, "INV0004", status="PENDING")
    _login(client, db, 1)
    lookup = client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "invoice", "out_trade_no": "INV0001"}).json()
    assert lookup["order"]["invoiceable_amount"] == "51.00"
    assert lookup["problem"] is None

    resp = _invoice(client, ["INV0001", "INV0002"])
    assert resp.status_code == 201, resp.text
    assert [o["snapshot"]["invoiceable_amount"] for o in resp.json()["orders"]] == ["51.00", "50.00"]

    assert _invoice(client, ["INV0002"]).json()["code"] == "ORDER_DUPLICATE"
    assert _invoice(client, ["INV0003", "INV0004"]).json()["code"] == "ORDER_NOT_ELIGIBLE"
    fake.orders[24]["status"] = "COMPLETED"
    assert _invoice(client, ["INV0003", "INV0004"]).json()["code"] == "ORDER_CURRENCY_MIXED"


def test_payment_ticket_allows_repeats_and_any_status(client, db, fake):
    fake.add(31, 1, "PAY3001", status="PENDING")
    _login(client, db, 1)
    form = {"issue_type": "NOT_CREDITED", "order_no": "PAY3001", "pay_channel": "ALIPAY"}
    for _ in range(2):
        resp = client.post(f"{BASE}/tickets", json={"category": "RECHARGE_PAYMENT", "form_version": 1, "form_data": form})
        assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == "充值问题 · 已付款未到账 · PAY3001"


def test_sub2api_failures_do_not_create_tickets(client, db, fake, caplog):
    fake.add(11, 1, "PAY1001")
    user = _login(client, db, 1)
    fake.mode = "down"
    resp = _refund(client, "PAY1001")
    assert resp.status_code == 503 and resp.json()["code"] == "ORDER_SERVICE_UNAVAILABLE"
    fake.mode = "badkey"
    with caplog.at_level(logging.INFO):
        resp = _refund(client, "PAY1001")
    assert resp.status_code == 503
    assert "Admin API Key" not in resp.text
    assert "Admin API Key 无效" in caplog.text
    assert KEY not in caplog.text and KEY not in resp.text
    assert db.query(Ticket).filter_by(creator_user_id=user.id).count() == 0


def test_admin_list_search_and_live_orders(client, db, fake):
    fake.add(11, 1, "PAY1001")
    _login(client, db, 1)
    tid = _refund(client, "PAY1001").json()["id"]
    client.post(f"{BASE}/tickets", json={"category": "OTHER", "form_version": 1, "form_data": {},
                                         "title": "t", "description": "d"})

    _login(client, db, 90, role="admin")
    found = client.get(f"{BASE}/admin/tickets", params={"keyword": "PAY1001"}).json()
    assert [i["id"] for i in found["items"]] == [tid]
    assert found["items"][0]["order_nos"] == ["PAY1001"]
    active = client.get(f"{BASE}/admin/tickets", params={"category": "REFUND", "active": True}).json()
    assert [i["id"] for i in active["items"]] == [tid]

    fake.orders[11]["status"] = "REFUNDED"
    live = client.get(f"{BASE}/admin/tickets/{tid}/orders/live")
    assert live.status_code == 200, live.text
    assert live.json()[0]["order"]["status"] == "REFUNDED"
    # the stored snapshot still shows the state at submission
    assert db.query(TicketOrder).filter_by(ticket_id=tid).one().snapshot["status"] == "COMPLETED"

    fake.mode = "badkey"
    live = client.get(f"{BASE}/admin/tickets/{tid}/orders/live")
    assert live.status_code == 503
    assert "Admin API Key 无效" in live.json()["detail"]

    _login(client, db, 1)
    assert client.get(f"{BASE}/admin/tickets/{tid}/orders/live").status_code == 403


def test_lookup_rate_limit(client, db, fake):
    fake.add(11, 1, "PAY1001")
    _login(client, db, 1)
    codes = [client.get(f"{BASE}/tickets/orders/lookup", params={"kind": "refund", "out_trade_no": "PAY1001"}).status_code
             for _ in range(orders_service.LOOKUPS_PER_MINUTE + 1)]
    assert codes[:-1] == [200] * orders_service.LOOKUPS_PER_MINUTE
    assert codes[-1] == 429
