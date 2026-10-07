import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.manual.schema import DEFAULT_CONFIG_PATH, load_default_config
from app.orders.sub2api import Sub2APIAdminClient
from tests.conftest import login_as, make_user

MANUAL_DEFAULT = Path(__file__).resolve().parents[2] / "frontend" / "manual" / "assets" / "manual-config.default.json"


def admin_client(client, db):
    login_as(client, db, make_user(db, sub2api_id=9001, role="admin", username="boss"))
    return client


def live(client):
    return client.get("/ext/api/v1/admin/manual/config").json()


def save(client, config, base_version, **extra):
    return client.put("/ext/api/v1/admin/manual/config",
                      json={"config": config, "base_version": base_version, **extra})


def test_manual_bundles_the_same_defaults_as_backend():
    # The manual falls back to its bundled copy when the API is unreachable; both must match.
    assert json.loads(MANUAL_DEFAULT.read_text(encoding="utf-8")) == json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_public_config_seeds_defaults_without_login(client):
    res = client.get("/ext/api/v1/public/manual-config")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 1
    assert body["config"]["contact"]["qq"] == load_default_config().contact.qq
    assert body["config"]["ccswitch"]["windows"]["download_url"] == "assets/downloads/CC-Switch-v3.20.4-Windows.msi"
    assert res.headers["cache-control"] == "public, max-age=60"
    again = client.get("/ext/api/v1/public/manual-config", headers={"If-None-Match": res.headers["etag"]})
    assert again.status_code == 304


def test_admin_endpoints_require_admin(client, db):
    assert client.get("/ext/api/v1/admin/manual/config").status_code == 401
    login_as(client, db, make_user(db, sub2api_id=9002, role="user", username="normal"))
    assert client.get("/ext/api/v1/admin/manual/config").status_code == 403
    assert client.put("/ext/api/v1/admin/manual/config", json={"config": {}, "base_version": 1}).status_code == 403


def test_save_creates_version_and_updates_public_config(client, db):
    admin_client(client, db)
    current = live(client)
    config = copy.deepcopy(current["config"])
    config["models"]["codex"]["recommend"] = ["gpt-6-luna", "gpt-6.1-sol"]
    config["announcement"] = {"enabled": True, "level": "warning", "text": "gpt-6.1-sol 维护中"}
    res = save(client, config, current["version"], note="切换推荐模型")
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["version"] == 2
    assert saved["created_by_name"] == "boss"
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    assert saved["config"]["updated_on"] == today
    public = client.get("/ext/api/v1/public/manual-config").json()
    assert public["version"] == 2
    assert public["config"]["models"]["codex"]["recommend"][0] == "gpt-6-luna"
    assert public["config"]["announcement"]["text"] == "gpt-6.1-sol 维护中"


def test_save_can_keep_manual_update_date(client, db):
    admin_client(client, db)
    current = live(client)
    config = copy.deepcopy(current["config"])
    config["updated_on"] = "2026-09-30"
    res = save(client, config, current["version"], touch_updated_on=False)
    assert res.json()["config"]["updated_on"] == "2026-09-30"


def test_stale_base_version_is_rejected(client, db):
    admin_client(client, db)
    current = live(client)
    assert save(client, current["config"], current["version"]).status_code == 200
    stale = save(client, current["config"], current["version"])
    assert stale.status_code == 409
    assert stale.json()["code"] == "MANUAL_CONFIG_STALE"


@pytest.mark.parametrize("path,value", [
    (("models", "codex", "recommend"), ['gpt"; calc.exe; "']),
    (("models", "claude", "include"), ["claude* & del"]),
    (("models", "claude", "include"), []),
    (("claude_roles", "haiku"), ["$(whoami)"]),
    (("install", "claude_package"), ["@anthropic-ai/claude-code && calc"]),
    (("install", "claude_package"), "@Anthropic/Bad Name"),
    (("install", "codex_store_id"), "9plm9xgg6vks"),
    (("install", "workbuddy_winget_id"), "Tencent WorkBuddy"),
    (("install", "npm_registry"), "http://registry.npmmirror.com"),
    (("install", "npm_registry"), "https://registry.npmmirror.com/%25"),
    (("install", "node_mirror"), "https://example.com/?x=1"),
    (("install", "workbuddy_site"), 'https://evil.example/"&calc'),
    (("install", "node_min_major"), 30),
    (("site", "url"), "https://api.tysy.top/path"),
    (("contact", "qq"), "abc123"),
    (("announcement",), {"enabled": True, "level": "info", "text": ""}),
    (("announcement",), {"enabled": True, "level": "info", "text": "bad\x07bell"}),
    (("ccswitch", "version"), "3.20"),
    (("ccswitch", "windows"), {"source": "url", "file_id": None, "url": "assets/downloads/../../etc/passwd"}),
    (("ccswitch", "windows"), {"source": "file", "file_id": None, "url": ""}),
    (("workbuddy", "max_input_tokens"), 10),
    (("unknown_section",), {"a": 1}),
    (("groups", "items"), [{"name": "A"}, {"name": "A"}]),
    (("groups", "items"), [{"name": ""}]),
    (("groups", "items"), [{"name": "two\nlines"}]),
    (("groups", "items"), [{"name": "A", "models": ['gpt"; calc']}]),
    (("groups", "items"), [{"name": "A", "clients": ["cursor"]}]),
    (("groups", "items"), [{"name": "A", "badge": "<b>hot</b>"}]),
    (("groups", "items"), [{"name": "A", "platform": "Open AI"}]),
    (("groups", "items"), [{"name": "A", "rate_multiplier": -1}]),
    (("groups", "items"), [{"name": "A", "summary": "bad\x07bell"}]),
    (("groups", "items"), [{"name": "A", "unknown": 1}]),
    (("groups", "faq"), [{"q": "问题", "a": " "}]),
    (("groups", "intro"), "x" * 501),
])
def test_unsafe_or_invalid_values_are_rejected(client, db, path, value):
    admin_client(client, db)
    current = live(client)
    config = copy.deepcopy(current["config"])
    target = config
    for key in path[:-1]:
        target = target[key]
    if path[0] == "install" and path[-1] == "claude_package" and isinstance(value, list):
        value = value[0]
    target[path[-1]] = value
    res = save(client, config, current["version"])
    assert res.status_code == 422, (path, value, res.text)
    assert res.json()["code"] == "MANUAL_CONFIG_INVALID"
    assert live(client)["version"] == current["version"]


def test_restore_creates_a_new_version(client, db):
    admin_client(client, db)
    v1 = live(client)
    changed = copy.deepcopy(v1["config"])
    changed["contact"]["qq"] = "123456"
    assert save(client, changed, 1).status_code == 200
    res = client.post("/ext/api/v1/admin/manual/versions/1/restore", json={"base_version": 2})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["version"] == 3
    assert body["restored_from"] == 1
    assert body["config"]["contact"]["qq"] == v1["config"]["contact"]["qq"]
    versions = client.get("/ext/api/v1/admin/manual/versions").json()
    assert [v["version"] for v in versions] == [3, 2, 1]


def _mock_storage():
    storage = MagicMock()
    stream = MagicMock()
    stream.stream.return_value = iter([b"MSI-BYTES"])
    storage.open_stream.return_value = stream
    return storage, stream


def test_file_upload_reference_download_and_delete(client, db):
    admin_client(client, db)
    storage, stream = _mock_storage()
    with patch("app.manual.service.get_storage", return_value=storage), \
            patch("app.manual.router.get_storage", return_value=storage):
        bad = client.post("/ext/api/v1/admin/manual/files", files={"file": ("evil.cmd", b"@echo off", "text/plain")})
        assert bad.status_code == 400
        res = client.post("/ext/api/v1/admin/manual/files",
                          files={"file": ("CC-Switch-v3.21.0-Windows.msi", b"MSI-BYTES", "application/octet-stream")},
                          data={"description": "CC Switch 3.21.0"})
        assert res.status_code == 200, res.text
        uploaded = res.json()
        assert uploaded["sha256"] and uploaded["file_size"] == 9
        storage.put_bytes.assert_called_once()

        current = live(client)
        config = copy.deepcopy(current["config"])
        config["ccswitch"]["version"] = "3.21.0"
        config["ccswitch"]["windows"] = {"source": "file", "file_id": uploaded["id"], "url": ""}
        assert save(client, config, current["version"]).status_code == 200

        public = client.get("/ext/api/v1/public/manual-config").json()
        windows = public["config"]["ccswitch"]["windows"]
        assert windows["download_url"] == uploaded["download_path"]
        assert windows["sha256"] == uploaded["sha256"]

        download = client.get(uploaded["download_path"])
        assert download.status_code == 200
        assert download.content == b"MSI-BYTES"
        assert "CC-Switch-v3.21.0-Windows.msi" in download.headers["content-disposition"]
        stream.close.assert_called()
        assert client.get(f"/ext/api/v1/public/manual-files/{uploaded['id']}/other.msi").status_code == 404

        in_use = client.delete(f"/ext/api/v1/admin/manual/files/{uploaded['id']}")
        assert in_use.status_code == 409
        current = live(client)
        config = copy.deepcopy(current["config"])
        config["ccswitch"]["windows"] = {"source": "url", "file_id": None, "url": "assets/downloads/CC-Switch-v3.20.4-Windows.msi"}
        assert save(client, config, current["version"]).status_code == 200
        assert client.delete(f"/ext/api/v1/admin/manual/files/{uploaded['id']}").status_code == 200
        assert client.get(uploaded["download_path"]).status_code == 404
        assert client.get("/ext/api/v1/admin/manual/files").json() == []

        # Restoring the version that used the deleted file is refused instead of breaking the download.
        stale = client.post(f"/ext/api/v1/admin/manual/versions/{current['version']}/restore",
                            json={"base_version": current["version"] + 1})
        assert stale.status_code == 400
        assert stale.json()["code"] == "MANUAL_FILE_MISSING"


def test_referencing_unknown_file_is_rejected(client, db):
    admin_client(client, db)
    current = live(client)
    config = copy.deepcopy(current["config"])
    config["ccswitch"]["windows"] = {"source": "file", "file_id": 999, "url": ""}
    res = save(client, config, current["version"])
    assert res.status_code == 400
    assert res.json()["code"] == "MANUAL_FILE_MISSING"


GROUP = {
    "name": "Claude 稳定", "sub2api_id": 3, "visible": True, "platform": "anthropic", "clients": ["claude"],
    "badge": "recommended", "rate_multiplier": 0.8, "billing_note": "性价比高", "summary": "日常编码首选",
    "suitable_for": ["日常写代码", "长对话"], "models": ["claude-sonnet-5-5", "claude-opus-*"], "notes": "高峰期可能排队",
}


def test_groups_are_saved_and_hidden_groups_stay_private(client, db):
    admin_client(client, db)
    current = live(client)
    config = copy.deepcopy(current["config"])
    hidden = {**GROUP, "name": "内部测试", "sub2api_id": 9, "visible": False}
    config["groups"]["items"] = [GROUP, hidden]
    config["groups"]["notice"] = "新分组上线"
    res = save(client, config, current["version"])
    assert res.status_code == 200, res.text
    assert [g["name"] for g in live(client)["config"]["groups"]["items"]] == ["Claude 稳定", "内部测试"]
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]["groups"]
    assert public["notice"] == "新分组上线"
    assert [g["name"] for g in public["items"]] == ["Claude 稳定"]
    assert "sub2api_id" not in public["items"][0] and "visible" not in public["items"][0]
    assert public["items"][0]["rate_multiplier"] == 0.8


def test_versions_saved_before_groups_existed_still_work(client, db):
    from app.db.models.manual import ManualConfigVersion

    old = load_default_config().dump()
    del old["groups"]
    db.add(ManualConfigVersion(version=1, config=old, note="旧版本"))
    db.commit()
    public = client.get("/ext/api/v1/public/manual-config").json()
    assert public["config"]["groups"]["faq"] == load_default_config().groups.public()["faq"]
    admin_client(client, db)
    current = live(client)
    assert current["config"]["groups"]["items"] == []
    assert save(client, current["config"], 1).status_code == 200
    res = client.post("/ext/api/v1/admin/manual/versions/1/restore", json={"base_version": 2})
    assert res.status_code == 200, res.text


SUB2API_GROUPS = [
    {"id": 3, "name": "Claude 稳定", "description": "官方直连", "platform": "anthropic", "rate_multiplier": 0.8,
     "is_exclusive": False, "status": "active", "subscription_type": "standard", "peak_rate_enabled": True,
     "peak_start": "09:00", "peak_end": "18:00", "peak_rate_multiplier": 1.2,
     "model_allowlist": {"enabled": True, "models": ["claude-sonnet-5-5", "bad model"]},
     "profit_control_enabled": True, "profit_min_margin": 0.3, "model_routing": {"x": [1]}},
    {"id": 4, "name": "GPT", "platform": "openai", "rate_multiplier": 1, "allow_messages_dispatch": True,
     "model_allowlist": {"enabled": False, "models": ["gpt-6.1-sol"]}},
    {"id": 0, "name": "broken"},
]


def _fake_sub2api(monkeypatch, handler):
    fake = Sub2APIAdminClient("http://sub2api.test", "admin-key", transport=httpx.MockTransport(handler))
    monkeypatch.setattr("app.manual.service.get_admin_client", lambda: fake)


def test_sub2api_groups_are_listed_without_internal_fields(client, db, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "message": "success", "data": SUB2API_GROUPS})

    _fake_sub2api(monkeypatch, handler)
    assert client.get("/ext/api/v1/admin/manual/sub2api-groups").status_code == 401
    admin_client(client, db)
    res = client.get("/ext/api/v1/admin/manual/sub2api-groups")
    assert res.status_code == 200, res.text
    assert seen[-1].url.path == "/api/v1/admin/groups/all"
    assert seen[-1].headers["x-api-key"] == "admin-key"
    groups = res.json()
    assert [g["id"] for g in groups] == [3, 4]
    assert groups[0]["models"] == ["claude-sonnet-5-5"]
    assert groups[0]["peak"] == {"start": "09:00", "end": "18:00", "multiplier": 1.2}
    assert groups[1]["models"] == [] and groups[1]["allow_messages_dispatch"] is True
    assert not {"profit_control_enabled", "profit_min_margin", "model_routing"} & set(groups[0])


def test_sub2api_groups_report_missing_key_and_upstream_errors(client, db, monkeypatch):
    admin_client(client, db)
    monkeypatch.setattr("app.manual.service.get_admin_client", lambda: None)
    res = client.get("/ext/api/v1/admin/manual/sub2api-groups")
    assert res.status_code == 503
    assert res.json()["code"] == "SUB2API_NOT_CONFIGURED"
    _fake_sub2api(monkeypatch, lambda request: httpx.Response(401, json={"code": 401, "message": "bad key"}))
    res = client.get("/ext/api/v1/admin/manual/sub2api-groups")
    assert res.status_code == 502
    assert "SUB2API_ADMIN_API_KEY" in res.json()["detail"]
