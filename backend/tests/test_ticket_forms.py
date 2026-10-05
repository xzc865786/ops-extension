import copy

from app.db.models.ticket import Ticket, TicketMessage
from tests.conftest import login_as, make_user

BASE = "/ext/api/v1"


def _user(client, db, sub2api_id=1, role="user"):
    user = make_user(db, sub2api_id=sub2api_id, role=role, username=f"{role}{sub2api_id}")
    client.cookies.clear()
    login_as(client, db, user)
    return user


def _meta(client):
    resp = client.get(f"{BASE}/tickets/meta")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create(client, category, form_data, version, **extra):
    return client.post(f"{BASE}/tickets", json={"category": category, "form_version": version,
                                                "form_data": form_data, **extra})


def _config(client):
    resp = client.get(f"{BASE}/admin/tickets/form-config")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _save(client, config, base_version, note=None):
    return client.put(f"{BASE}/admin/tickets/form-config",
                      json={"config": config, "base_version": base_version, "note": note})


def _category(config, key):
    return next(c for c in config["categories"] if c["key"] == key)


def test_meta_lists_configured_categories(client, db):
    _user(client, db)
    meta = _meta(client)
    assert meta["form_version"] == 1
    refund = next(c for c in meta["categories"] if c["value"] == "REFUND")
    assert refund["label"] == "退款"
    assert refund["kind"] == "refund"
    keys = [f["key"] for f in refund["fields"]]
    assert keys[0] == "order_no" and "policy_ack" in keys
    assert next(f for f in refund["fields"] if f["key"] == "order_no")["system"] is True


def test_refund_ticket_auto_title_and_snapshot(client, db):
    _user(client, db)
    version = _meta(client)["form_version"]
    resp = _create(client, "REFUND", {"order_no": " PAY20261005001 ", "expected_amount": "50",
                                      "reason": "MISTAKE", "policy_ack": True}, version)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "退款申请 · PAY20261005001"
    assert data["description"] == ""
    assert data["messages"] == []
    assert data["form_version"] == version
    assert data["form_data"] == {"order_no": "PAY20261005001", "expected_amount": "50.00",
                                 "reason": "MISTAKE", "policy_ack": True}
    assert data["form_schema"]["key"] == "REFUND"
    assert [f["key"] for f in data["form_schema"]["fields"]][:2] == ["order_no", "expected_amount"]


def test_required_and_unknown_fields_rejected(client, db):
    _user(client, db)
    version = _meta(client)["form_version"]
    resp = _create(client, "REFUND", {"reason": "MISTAKE", "policy_ack": False}, version)
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "TICKET_FORM_INVALID"
    assert "订单号" in body["detail"] and "请勾选" in body["detail"]

    resp = _create(client, "REFUND", {"order_no": "PAY1234", "reason": "MISTAKE", "policy_ack": True,
                                      "secret": "x"}, version)
    assert resp.status_code == 422
    assert "不认识的字段" in resp.json()["detail"]

    resp = _create(client, "REFUND", {"order_no": "PAY1234", "reason": "BOGUS", "policy_ack": True,
                                      "expected_amount": "1.234"}, version)
    assert resp.status_code == 422
    assert "选项无效" in resp.json()["detail"] and "两位小数" in resp.json()["detail"]


def test_invoice_show_if_and_order_list(client, db):
    _user(client, db)
    version = _meta(client)["form_version"]
    personal = _create(client, "INVOICE", {"order_nos": "A0001, A0002\nA0001", "title_type": "PERSONAL",
                                           "title": "张三", "tax_id": "IGNORED", "email": "a@example.com"}, version)
    assert personal.status_code == 201, personal.text
    assert personal.json()["form_data"] == {"order_nos": ["A0001", "A0002"], "title_type": "PERSONAL",
                                            "title": "张三", "email": "a@example.com"}
    assert personal.json()["title"] == "开票申请 · 张三"

    company = _create(client, "INVOICE", {"order_nos": ["A0003"], "title_type": "COMPANY",
                                          "title": "某某公司", "email": "a@example.com"}, version)
    assert company.status_code == 422
    assert "税号" in company.json()["detail"]

    too_many = _create(client, "INVOICE", {"order_nos": [f"ORDER{i:03d}" for i in range(11)],
                                           "title_type": "PERSONAL", "title": "张三",
                                           "email": "a@example.com"}, version)
    assert too_many.status_code == 422
    assert "最多填写 10 个" in too_many.json()["detail"]


def test_title_and_description_modes(client, db):
    _user(client, db)
    version = _meta(client)["form_version"]
    # FEATURE_REQUEST: title required, description hidden
    missing_title = _create(client, "FEATURE_REQUEST", {"scenario": "s", "expectation": "e"}, version)
    assert missing_title.status_code == 422
    ok = _create(client, "FEATURE_REQUEST", {"scenario": "s", "expectation": "e"}, version,
                 title="想要导出", description="会被忽略")
    assert ok.status_code == 201
    assert ok.json()["description"] == ""
    # OTHER: description required, mirrored as the first message
    other = _create(client, "OTHER", {}, version, title="t")
    assert other.status_code == 422
    other = _create(client, "OTHER", {}, version, title="t", description="详细描述")
    assert other.status_code == 201
    assert [m["content"] for m in other.json()["messages"]] == ["详细描述"]
    # ACCOUNT: optional title falls back to the template
    account = _create(client, "ACCOUNT", {"issue_type": "RECOVER"}, version, description="找不回")
    assert account.json()["title"] == "账户问题 · 找回账号"


def test_legacy_clients_still_work(client, db):
    _user(client, db)
    resp = client.post(f"{BASE}/tickets", json={"title": "旧版", "description": "d", "category": "API_ERROR",
                                                "model_name": "m1", "occurred_at": "2026-10-05T08:30:00+08:00"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["model_name"] == "m1"
    assert data["form_version"] is None
    assert data["form_data"]["model_name"] == "m1"
    assert data["form_data"]["occurred_at"].startswith("2026-10-05T08:30")
    assert [f["key"] for f in data["form_schema"]["fields"]] == [
        "request_id", "model_name", "api_endpoint", "occurred_at", "error_message"]


def test_admin_config_edit_and_disabled_category(client, db):
    _user(client, db)
    user_ticket = _create(client, "OTHER", {}, 1, title="t", description="d").json()

    _user(client, db, sub2api_id=90, role="admin")
    cfg = _config(client)
    config = cfg["config"]
    other = _category(config, "OTHER")
    other["enabled"] = False
    refund = _category(config, "REFUND")
    refund["fields"][1]["label"] = "希望退多少"
    config["categories"].append({"key": "CUSTOM_Q", "label": "自定义", "fields": [
        {"key": "q", "label": "问题", "type": "text", "required": True}]})
    saved = _save(client, config, cfg["version"], note="停用其他")
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2

    # stale base version
    assert _save(client, config, 1).status_code == 409

    _user(client, db)
    meta = _meta(client)
    assert meta["form_version"] == 2
    assert next(c for c in meta["categories"] if c["value"] == "OTHER")["enabled"] is False
    assert _create(client, "OTHER", {}, 2, title="t", description="d").json()["code"] == "INVALID_CATEGORY"
    # the earlier ticket keeps its snapshot
    detail = client.get(f"{BASE}/tickets/{user_ticket['id']}").json()
    assert detail["form_schema"]["key"] == "OTHER"

    _user(client, db, sub2api_id=90, role="admin")
    moved = client.patch(f"{BASE}/admin/tickets/{user_ticket['id']}", json={"category": "CUSTOM_Q"})
    assert moved.status_code == 200
    assert client.patch(f"{BASE}/admin/tickets/{user_ticket['id']}", json={"category": "NOPE"}).status_code == 400

    # categories with tickets cannot be removed
    cfg = _config(client)
    config = copy.deepcopy(cfg["config"])
    config["categories"] = [c for c in config["categories"] if c["key"] != "CUSTOM_Q"]
    resp = _save(client, config, cfg["version"])
    assert resp.status_code == 400
    assert resp.json()["code"] == "TICKET_CATEGORY_IN_USE"

    # restore version 1 is refused too while CUSTOM_Q has tickets
    assert client.post(f"{BASE}/admin/tickets/form-config/versions/1/restore",
                       json={"base_version": cfg["version"]}).status_code == 400
    versions = client.get(f"{BASE}/admin/tickets/form-config/versions").json()
    assert [v["version"] for v in versions] == [2, 1]


def test_config_rules(client, db):
    _user(client, db, sub2api_id=91, role="admin")
    cfg = _config(client)

    def rejects(mutate, fragment):
        config = copy.deepcopy(cfg["config"])
        mutate(config)
        resp = _save(client, config, cfg["version"])
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "TICKET_FORM_CONFIG_INVALID"
        assert fragment in resp.json()["detail"], resp.json()["detail"]

    rejects(lambda c: _category(c, "REFUND")["fields"].pop(0), "缺少系统字段")
    rejects(lambda c: _category(c, "REFUND")["fields"][0].update(required=False), "不能修改类型或取消必填")
    rejects(lambda c: _category(c, "INVOICE")["fields"][1]["options"][0].update(value="PERSON"), "选项值不能修改")
    rejects(lambda c: c["categories"].remove(_category(c, "ACCOUNT")), "内置分类不能删除")
    rejects(lambda c: _category(c, "OTHER").update(kind="refund"), "业务类型固定")
    rejects(lambda c: _category(c, "OTHER")["fields"].extend([
        {"key": "a", "label": "A", "type": "text", "show_if": {"field": "b", "equals": "X"}},
        {"key": "b", "label": "B", "type": "select", "options": [{"value": "X", "label": "x"}]},
    ]), "排在它前面")
    rejects(lambda c: _category(c, "OTHER")["fields"].extend([
        {"key": "a", "label": "A", "type": "text"}, {"key": "a", "label": "B", "type": "text"}]), "字段标识重复")
    rejects(lambda c: _category(c, "OTHER").update(title_mode="auto", title_template="{nope}"), "标题模板")
    rejects(lambda c: [cat.update(enabled=False) for cat in c["categories"]], "至少要启用一个分类")
    rejects(lambda c: _category(c, "REFUND")["fields"][1].update(label=""), "分类“退款”的第 2 个字段的名称不能为空")
    rejects(lambda c: _category(c, "OTHER")["fields"].append({"key": "z", "label": "Z", "type": "bogus"}),
            "分类“其他”的字段“Z”的类型取值无效")

    # system flag cannot be forged on ordinary fields
    config = copy.deepcopy(cfg["config"])
    _category(config, "OTHER")["fields"].append({"key": "x", "label": "X", "type": "text", "system": True})
    resp = _save(client, config, cfg["version"])
    assert resp.status_code == 200, resp.text
    other = _category(resp.json()["config"], "OTHER")
    assert other["fields"][0]["system"] is False


def test_user_cannot_edit_config(client, db):
    _user(client, db)
    assert client.get(f"{BASE}/admin/tickets/form-config").status_code == 403
    assert _save(client, {}, 1).status_code == 403


def test_message_not_created_without_description(db, client):
    _user(client, db)
    resp = _create(client, "REFUND", {"order_no": "PAY9999", "reason": "OTHER", "policy_ack": True}, 1)
    ticket = db.get(Ticket, resp.json()["id"])
    assert ticket.form_data["order_no"] == "PAY9999"
    assert db.query(TicketMessage).filter_by(ticket_id=ticket.id).count() == 0
