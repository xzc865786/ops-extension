import json
from datetime import date

import httpx
import pytest

from app.db.models.ticket import Ticket, TicketAttachment
from app.orders.sub2api import Sub2APIAdminClient
from tests.conftest import login_as, make_user
from tests.test_ticket_orders import KEY, FakeSub2API

BASE = "/ext/api/v1"


class RefundingSub2API(FakeSub2API):
    """Adds the refund endpoints; ``refund_mode`` picks how the next refunds behave."""

    def __init__(self):
        super().__init__()
        self.refund_mode = "ok"  # ok | require_force | pending | timeout | disabled | gateway_fail
        self.refund_bodies: list[dict] = []

    def _done(self, order, amount):
        order["refund_amount"] = amount
        order["status"] = "REFUNDED" if amount >= order["amount"] else "PARTIALLY_REFUNDED"

    def handler(self, request):
        path = request.url.path
        if request.method == "POST" and path.endswith("/refund/query"):
            order = self.orders[int(path.split("/")[-3])]
            if order["status"] != "REFUND_PENDING":
                return httpx.Response(400, json={"code": 400, "message": "only pending", "reason": "INVALID_STATUS"})
            self._done(order, order["refund_amount"])
            return httpx.Response(200, json={"code": 0, "message": "success", "data": {"success": True}})
        if request.method == "POST" and path.endswith("/refund"):
            order = self.orders[int(path.split("/")[-2])]
            body = json.loads(request.content)
            self.refund_bodies.append(body)
            mode, amount = self.refund_mode, body["amount"]
            if mode == "disabled":
                return httpx.Response(403, json={"code": 403, "message": "refund is not enabled", "reason": "REFUND_DISABLED"})
            if mode == "require_force" and not body["force"]:
                return httpx.Response(200, json={"code": 0, "message": "success", "data": {
                    "success": False, "require_force": True,
                    "warning": "user balance is insufficient for deduction, use force"}})
            if mode == "pending":
                order["status"], order["refund_amount"] = "REFUND_PENDING", amount
                return httpx.Response(200, json={"code": 0, "message": "success", "data": {
                    "success": False, "warning": "gateway refund is pending confirmation"}})
            if mode == "gateway_fail":
                return httpx.Response(200, json={"code": 0, "message": "success", "data": {
                    "success": False, "warning": "gateway failed: alipay error, rolled back"}})
            self._done(order, amount)
            if mode == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            return httpx.Response(200, json={"code": 0, "message": "success", "data": {
                "success": True, "balance_deducted": amount}})
        return super().handler(request)


@pytest.fixture()
def fake(monkeypatch):
    fake = RefundingSub2API()
    client = Sub2APIAdminClient("http://sub2api.test", KEY, transport=httpx.MockTransport(fake.handler))
    for target in ("app.orders.service.get_admin_client", "app.tickets.service.get_admin_client",
                   "app.tickets.handling.get_admin_client"):
        monkeypatch.setattr(target, lambda: client)
    return fake


@pytest.fixture(autouse=True)
def reset_rate_limit():
    from app.orders import service
    service._hits.clear()


def _as(client, db, sub2api_id, role="user"):
    user = make_user(db, sub2api_id=sub2api_id, role=role, username=f"{role}{sub2api_id}")
    client.cookies.clear()
    login_as(client, db, user)
    return user


def _refund_ticket(client, db, order_no="PAY1001", expected=None):
    _as(client, db, 1)
    form = {"order_no": order_no, "reason": "MISTAKE", "policy_ack": True}
    if expected:
        form["expected_amount"] = expected
    resp = client.post(f"{BASE}/tickets", json={"category": "REFUND", "form_version": 1, "form_data": form})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _refund(client, tid, amount, **extra):
    return client.post(f"{BASE}/admin/tickets/{tid}/refund", json={"amount": amount, **extra})


def test_partial_refund_resolves_and_replies(client, db, fake):
    fake.add(11, 1, "PAY1001", amount=100, pay_amount=101)
    ticket = _refund_ticket(client, db, expected="30")
    _as(client, db, 90, role="admin")
    resp = _refund(client, ticket["id"], "30", reason="用户误充")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["operation"]["result"] == "SUCCESS"
    detail = body["ticket"]
    assert detail["status"] == "RESOLVED"
    res = detail["resolution"]
    assert res["outcome"] == "REFUNDED" and res["source"] == "SUB2API"
    assert res["refund_amount"] == "30.00" and res["gateway_amount"] == "30.30"
    assert res["balance_deducted"] == "30.00" and res["operator_name"] == "admin90"

    sent = fake.refund_bodies[0]
    assert sent["amount"] == 30.0 and sent["deduct_balance"] is True and sent["force"] is False
    assert ticket["ticket_no"] in sent["reason"] and "用户误充" in sent["reason"]

    assert _refund(client, ticket["id"], "10").json()["code"] == "TICKET_ALREADY_RESOLVED"

    _as(client, db, 1)
    mine = client.get(f"{BASE}/tickets/{ticket['id']}").json()
    assert mine["refund_operations"] == []
    assert not any(k.startswith("operator_") for k in mine["resolution"])
    assert "原路退回 ¥30.30" in mine["messages"][-1]["content"]
    assert "扣减 30.00" in mine["messages"][-1]["content"]


def test_require_force_then_force(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    fake.refund_mode = "require_force"
    first = _refund(client, ticket["id"], "100").json()
    assert first["operation"]["result"] == "REQUIRE_FORCE"
    assert "余额不足" in first["operation"]["message"]
    assert first["ticket"]["status"] == "OPEN"
    second = _refund(client, ticket["id"], "100", force=True).json()
    assert second["operation"]["result"] == "SUCCESS"
    assert second["ticket"]["resolution"]["refund_amount"] == "100.00"


def test_pending_refund_blocks_until_synced(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    fake.refund_mode = "pending"
    body = _refund(client, ticket["id"], "50").json()
    assert body["operation"]["result"] == "PENDING"
    assert body["ticket"]["status"] == "PROCESSING"
    assert _refund(client, ticket["id"], "50").json()["code"] == "REFUND_IN_PROGRESS"
    assert client.post(f"{BASE}/admin/tickets/{ticket['id']}/reject",
                       json={"reason": "x"}).json()["code"] == "REFUND_IN_PROGRESS"
    synced = client.post(f"{BASE}/admin/tickets/{ticket['id']}/refund/sync").json()
    assert synced["outcome"] == "REFUNDED"
    assert synced["ticket"]["status"] == "RESOLVED"
    assert synced["ticket"]["refund_operations"][-1]["result"] == "SUCCESS"


def test_timeout_is_unknown_until_synced(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    fake.refund_mode = "timeout"
    op = _refund(client, ticket["id"], "100").json()["operation"]
    assert op["result"] == "UNKNOWN" and "不要重复退款" in op["message"]
    assert _refund(client, ticket["id"], "100").json()["code"] == "REFUND_IN_PROGRESS"
    assert len(fake.refund_bodies) == 1
    synced = client.post(f"{BASE}/admin/tickets/{ticket['id']}/refund/sync").json()
    assert synced["ticket"]["resolution"]["outcome"] == "REFUNDED"


def test_failures_can_be_retried(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    fake.refund_mode = "disabled"
    op = _refund(client, ticket["id"], "100").json()["operation"]
    assert op["result"] == "FAILED" and "允许退款" in op["message"]
    fake.refund_mode = "gateway_fail"
    op = _refund(client, ticket["id"], "100").json()["operation"]
    assert op["result"] == "FAILED" and "已自动回滚" in op["message"]
    fake.refund_mode = "ok"
    assert _refund(client, ticket["id"], "100").json()["operation"]["result"] == "SUCCESS"


def test_refund_amount_and_order_checks(client, db, fake):
    fake.add(11, 1, "PAY1001", amount=100)
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    assert _refund(client, ticket["id"], "100.01").json()["code"] == "REFUND_AMOUNT_EXCEEDED"
    assert _refund(client, ticket["id"], "0").status_code == 422
    fake.orders[11]["status"] = "REFUNDED"
    assert _refund(client, ticket["id"], "10").json()["code"] == "ORDER_NOT_ELIGIBLE"
    assert fake.refund_bodies == []


def test_reject_allows_new_application(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    assert client.post(f"{BASE}/admin/tickets/{ticket['id']}/reject", json={"reason": ""}).status_code == 422
    detail = client.post(f"{BASE}/admin/tickets/{ticket['id']}/reject", json={"reason": "已消耗超过一半"}).json()
    assert detail["resolution"]["outcome"] == "REJECTED"
    assert detail["status"] == "RESOLVED"
    assert detail["messages"][-1]["content"] == "您的退款申请未通过：已消耗超过一半"
    # a rejected request does not block applying again
    again = _refund_ticket(client, db)
    assert again["id"] != ticket["id"]


def test_status_and_category_guards(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    resp = client.patch(f"{BASE}/admin/tickets/{ticket['id']}", json={"status": "RESOLVED"})
    assert resp.status_code == 400 and resp.json()["code"] == "RESOLUTION_REQUIRED"
    _refund(client, ticket["id"], "100")
    resp = client.patch(f"{BASE}/admin/tickets/{ticket['id']}", json={"category": "OTHER"})
    assert resp.status_code == 400 and resp.json()["code"] == "CATEGORY_LOCKED"
    # non-form tickets are not affected
    other = client.post(f"{BASE}/tickets", json={"title": "t", "description": "d", "category": "OTHER"}).json()
    assert client.patch(f"{BASE}/admin/tickets/{other['id']}", json={"status": "RESOLVED"}).status_code == 200


def test_sync_records_refund_done_in_sub2api(client, db, fake):
    fake.add(11, 1, "PAY1001", amount=100, pay_amount=100)
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    not_yet = client.post(f"{BASE}/admin/tickets/{ticket['id']}/refund/sync").json()
    assert not_yet["outcome"] == "NOT_REFUNDED" and not_yet["ticket"]["resolution"] is None
    fake.orders[11].update(status="PARTIALLY_REFUNDED", refund_amount=40)
    synced = client.post(f"{BASE}/admin/tickets/{ticket['id']}/refund/sync").json()
    res = synced["ticket"]["resolution"]
    assert res["source"] == "SYNC" and res["refund_amount"] == "40.00" and res["balance_deducted"] is None


def test_manual_refund_only_without_key(client, db, fake, monkeypatch):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    _as(client, db, 90, role="admin")
    url = f"{BASE}/admin/tickets/{ticket['id']}/refund/manual"
    assert client.post(url, json={"amount": "20"}).json()["code"] == "USE_SYNC"
    monkeypatch.setattr("app.tickets.handling.get_admin_client", lambda: None)
    assert _refund(client, ticket["id"], "20").json()["code"] == "ORDER_LOOKUP_DISABLED"
    detail = client.post(url, json={"amount": "20", "note": "支付宝后台退款"}).json()
    assert detail["resolution"]["source"] == "MANUAL" and detail["resolution"]["gateway_amount"] == "20.00"


def test_invoice_issue(client, db, fake):
    fake.add(21, 1, "INV0001", amount=100, pay_amount=102, refund_amount=50, status="PARTIALLY_REFUNDED")
    fake.add(22, 1, "INV0002", amount=50, pay_amount=50)
    _as(client, db, 1)
    created = client.post(f"{BASE}/tickets", json={"category": "INVOICE", "form_version": 1, "form_data": {
        "order_nos": ["INV0001", "INV0002"], "title_type": "PERSONAL", "title": "张三", "email": "a@example.com"}})
    tid = created.json()["id"]
    admin = _as(client, db, 90, role="admin")

    def attach(name, mime):
        att = TicketAttachment(ticket_id=tid, uploader_user_id=admin.id, file_name=name, object_key=f"k/{name}",
                               mime_type=mime, file_size=10, sha256="0" * 64)
        db.add(att)
        db.commit()
        return att.id

    pdf, png = attach("invoice.pdf", "application/pdf"), attach("shot.png", "image/png")
    url = f"{BASE}/admin/tickets/{tid}/invoice"
    body = {"invoice_no": "26110000000012345678", "issued_on": date.today().isoformat(), "amount": "101.00",
            "attachment_id": pdf, "emailed": True}
    assert client.post(url, json={**body, "amount": "101.01"}).json()["code"] == "INVOICE_AMOUNT_EXCEEDED"
    assert client.post(url, json={**body, "emailed": False}).json()["code"] == "INVOICE_NOT_EMAILED"
    assert client.post(url, json={**body, "attachment_id": png}).json()["code"] == "INVOICE_FILE_REQUIRED"
    assert client.post(url, json={**body, "invoice_no": "bad no"}).json()["code"] == "INVALID_INVOICE_NO"
    detail = client.post(url, json=body)
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert detail["resolution"]["outcome"] == "ISSUED" and detail["resolution"]["amount"] == "101.00"
    assert detail["status"] == "RESOLVED"
    assert next(a for a in detail["attachments"] if a["id"] == pdf)["kind"] == "INVOICE_FILE"
    assert "a@example.com" in detail["messages"][-1]["content"]
    assert _refund(client, tid, "10").json()["code"] == "WRONG_TICKET_KIND"

    # invoiced orders stay blocked even after the ticket is closed
    client.post(f"{BASE}/admin/tickets/{tid}/close")
    _as(client, db, 1)
    again = client.post(f"{BASE}/tickets", json={"category": "INVOICE", "form_version": 1, "form_data": {
        "order_nos": ["INV0002"], "title_type": "PERSONAL", "title": "张三", "email": "a@example.com"}})
    assert again.json()["code"] == "ORDER_DUPLICATE"


def test_handling_requires_admin(client, db, fake):
    fake.add(11, 1, "PAY1001")
    ticket = _refund_ticket(client, db)
    for path in ("refund", "refund/sync", "reject", "invoice", "refund/manual"):
        assert client.post(f"{BASE}/admin/tickets/{ticket['id']}/{path}", json={}).status_code == 403
    assert db.get(Ticket, ticket["id"]).resolution is None
