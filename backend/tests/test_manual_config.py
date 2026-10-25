import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.manual.schema import DEFAULT_CONFIG_PATH, ManualConfig, load_default_config
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


def test_workbuddy_defaults_and_historical_versions():
    cfg = load_default_config().dump()
    wb = cfg["workbuddy"]
    assert wb["max_input_tokens"] is None and wb["max_output_tokens"] is None
    assert wb["default_effort"] == "high"
    assert wb["supported_efforts"] == ["low", "medium", "high"]
    for field in ["capability_rules", "default_effort", "supported_efforts"]:
        wb.pop(field)
    wb.update(supports_reasoning=False, max_input_tokens=128000, max_output_tokens=8192)
    restored = ManualConfig.model_validate(cfg).workbuddy
    assert restored.supports_reasoning is False
    assert restored.max_output_tokens == 8192
    assert restored.default_effort == "high"
    assert restored.capability_rules == []


def test_workbuddy_rules_may_follow_defaults():
    cfg = load_default_config().dump()
    assert cfg["workbuddy"]["supports_images"] is True and cfg["workbuddy"]["supports_reasoning"] is True
    assert {"gpt-6.1-sol", "deepseek-v4.1-flash", "glm-5.3-flash"} <= set(cfg["models"]["workbuddy"]["include"])
    assert not any("*" in pattern for pattern in cfg["models"]["workbuddy"]["include"])
    cfg["workbuddy"]["capability_rules"] = [{"models": ["glm*"], "supports_images": False}]
    rule = ManualConfig.model_validate(cfg).workbuddy.capability_rules[0]
    assert rule.supports_images is False and rule.supports_reasoning is None


@pytest.mark.parametrize("field,value", [
    ("default_effort", "max"),
    ("supported_efforts", ["high", "high"]),
    ("supported_efforts", ["low", "medium"]),
    ("max_input_tokens", 0),
    ("capability_rules", [{"models": ["*"], "supports_reasoning": True}]),
    ("capability_rules", [{"models": ["gpt-x"]}, {"models": ["GPT-X"]}]),
])
def test_invalid_workbuddy_capabilities_are_rejected(field, value):
    from pydantic import ValidationError
    cfg = load_default_config().dump()
    cfg["workbuddy"][field] = value
    with pytest.raises(ValidationError):
        ManualConfig.model_validate(cfg)


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


def test_public_etag_refreshes_legacy_cached_payload_without_publishing(client):
    response = client.get("/ext/api/v1/public/manual-config", headers={"If-None-Match": 'W/"manual-1"'})
    assert response.status_code == 200
    assert "image_mcp" in response.json()["config"]
    assert response.headers["etag"] != 'W/"manual-1"'
    assert client.get("/ext/api/v1/public/manual-config", headers={"If-None-Match": response.headers["etag"]}).status_code == 304


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
    stream.stream.side_effect = lambda _size: iter([b"MSI-BYTES"])
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


# AI image configuration uses only isolated SQLite and mocked object storage.
def test_image_default_and_old_restore(client, db):
    from app.db.models.manual import ManualConfigVersion
    old = load_default_config().dump()
    old.pop("image_mcp")
    db.add(ManualConfigVersion(version=1, config=old))
    db.commit()
    admin_client(client, db)
    current = live(client)
    assert current["image_mcp_compat_default"] is True
    image = current["config"]["image_mcp"]
    assert image["downloads"]["windows_x64"]["file_size"] == 127966065
    assert image["downloads"]["windows_x64"]["sha256"] == "cebbe26b4286a0ade27284e5f17369c8254257214c914ede09ba4de3045bda66"
    assert not image["downloads"]["macos_arm64"]["enabled"]
    image["downloads"]["windows_x64"]["enabled"] = False
    assert save(client, current["config"], 1).status_code == 200
    restored = client.post("/ext/api/v1/admin/manual/versions/1/restore", json={"base_version": 2})
    assert restored.status_code == 200
    assert restored.json()["config"]["image_mcp"]["downloads"]["windows_x64"]["enabled"] is True


def test_image_group_public_rename_and_cancel(client, db):
    admin_client(client, db)
    cfg = live(client)["config"]
    cfg["groups"]["items"] = [copy.deepcopy(GROUP)]
    cfg["image_mcp"]["recommended_group_id"] = GROUP["sub2api_id"]
    cfg["image_mcp"]["key_note"] = "请先开通"
    with patch("app.manual.service.get_admin_client") as external:
        assert save(client, cfg, 1).status_code == 200
        external.assert_not_called()
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]
    image = public["image_mcp"]
    assert image["recommended_group"]["name"] == GROUP["name"]
    assert "recommended_group_id" not in image
    assert "sub2api_id" not in json.dumps(public)
    assert "file_id" not in image["downloads"]["windows_x64"]
    cfg["groups"]["items"][0]["name"] = "新生图名称"
    assert save(client, cfg, 2).status_code == 200
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]
    assert public["image_mcp"]["recommended_group"]["name"] == public["groups"]["items"][0]["name"] == "新生图名称"
    cfg["image_mcp"]["recommended_group_id"] = None
    assert save(client, cfg, 3).status_code == 200
    assert client.get("/ext/api/v1/public/manual-config").json()["config"]["image_mcp"]["recommended_group"] is None


@pytest.mark.parametrize("action", ["hide", "delete", "duplicate", "unlinked"])
def test_image_group_reference_must_stay_unique_and_public(client, db, action):
    admin_client(client, db)
    cfg = live(client)["config"]
    cfg["groups"]["items"] = [copy.deepcopy(GROUP)]
    cfg["image_mcp"]["recommended_group_id"] = GROUP["sub2api_id"]
    assert save(client, cfg, 1).status_code == 200
    if action == "hide": cfg["groups"]["items"][0]["visible"] = False
    if action == "delete": cfg["groups"]["items"] = []
    if action == "duplicate": cfg["groups"]["items"].append({**GROUP, "name": "重复关联"})
    if action == "unlinked": cfg["groups"]["items"][0]["sub2api_id"] = None
    assert save(client, cfg, 2).status_code == 422
    assert live(client)["version"] == 2


@pytest.mark.parametrize("field,value", [("url", "http://bad/setup.exe"), ("url", "assets/downloads/../a.exe"),
    ("url", "/ext/api/v1/public/manual-files/1/%2e%2e%2fsetup.exe"), ("sha256", "bad"),
    ("file_size", 0), ("version", "guess"), ("system", ""), ("signing", "unsigned-local"),
    ("url", "https://example.com/setup.dmg"), ("file_name", "wrong.exe")])
def test_image_invalid_release(client, db, field, value):
    admin_client(client, db)
    cfg = live(client)["config"]
    cfg["image_mcp"]["downloads"]["windows_x64"][field] = value
    assert save(client, cfg, 1).status_code == 422


def test_image_url_release_and_pause_do_not_fetch_or_fallback(client, db):
    admin_client(client, db)
    cfg = live(client)["config"]
    win = cfg["image_mcp"]["downloads"]["windows_x64"]
    win.update(url="https://example.com/setup.exe", file_name="setup.exe")
    with patch("httpx.get", side_effect=AssertionError("no network")), patch("httpx.head", side_effect=AssertionError("no network")):
        assert save(client, cfg, 1).status_code == 200
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]["image_mcp"]
    assert public["downloads"]["windows_x64"]["download_url"] == win["url"]
    win["enabled"] = False
    assert save(client, cfg, 2).status_code == 200
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]["image_mcp"]
    assert public["downloads"]["windows_x64"]["download_url"] == ""


@pytest.mark.parametrize("source", ["file", "url"])
def test_image_file_metadata_reference_head_and_restore(client, db, source):
    from app.db.models.manual import ManualFile
    admin_client(client, db)
    storage, stream = _mock_storage()
    with patch("app.manual.service.get_storage", return_value=storage), patch("app.manual.router.get_storage", return_value=storage):
        uploaded = client.post("/ext/api/v1/admin/manual/files", files={"file": ("生图 setup.exe", b"MSI-BYTES")}).json()
        cfg = live(client)["config"]
        win = cfg["image_mcp"]["downloads"]["windows_x64"]
        win.update(source=source, file_id=uploaded["id"], url=uploaded["download_path"] if source == "url" else "",
                   file_name=uploaded["file_name"] if source == "url" else "forged.exe", file_size=1, sha256="a" * 64)
        assert save(client, cfg, 1).status_code == 200
        win_saved = live(client)["config"]["image_mcp"]["downloads"]["windows_x64"]
        assert win_saved["file_name"] == uploaded["file_name"]
        assert win_saved["file_size"] == 9 and win_saved["sha256"] == uploaded["sha256"]
        head = client.head(uploaded["download_path"])
        assert head.status_code == 200 and head.content == b"" and head.headers["content-length"] == "9"
        storage.stat_object.assert_called_once()
        assert client.get(uploaded["download_path"]).content == b"MSI-BYTES"
        # Uploaded files currently stream the full object; they do not advertise Range support.
        ranged = client.get(uploaded["download_path"], headers={"Range": "bytes=0-1"})
        assert ranged.status_code == 200 and ranged.content == b"MSI-BYTES"
        assert "accept-ranges" not in ranged.headers
        assert client.delete(f"/ext/api/v1/admin/manual/files/{uploaded['id']}").status_code == 409
        # Missing storage is detected by HEAD; deleted records never fall back to static downloads.
        storage.stat_object.side_effect = RuntimeError("missing object")
        assert client.head(uploaded["download_path"]).status_code == 503
        record = db.get(ManualFile, uploaded["id"])
        record.deleted = True
        db.commit()
        public = client.get("/ext/api/v1/public/manual-config").json()["config"]["image_mcp"]
        assert public["downloads"]["windows_x64"]["enabled"] is False
        assert public["downloads"]["windows_x64"]["download_url"] == ""
        cfg["image_mcp"] = load_default_config().image_mcp.model_dump(mode="json")
        assert save(client, cfg, 2).status_code == 200
        restored = client.post("/ext/api/v1/admin/manual/versions/2/restore", json={"base_version": 3})
        assert restored.status_code == 400 and restored.json()["code"] == "MANUAL_FILE_MISSING"


def test_image_corruption_only_disables_image_section(client, db):
    from app.db.models.manual import ManualConfigVersion
    cfg = load_default_config().dump()
    cfg["image_mcp"]["downloads"]["windows_x64"]["sha256"] = "corrupt"
    cfg["contact"]["qq"] = "123456789"
    db.add(ManualConfigVersion(version=1, config=cfg))
    db.commit()
    public = client.get("/ext/api/v1/public/manual-config").json()["config"]
    assert public["contact"]["qq"] == "123456789"
    assert public["ccswitch"]["windows"]["download_url"].endswith(".msi")
    assert not public["image_mcp"]["downloads"]["windows_x64"]["enabled"]


def test_manual_upload_limit_is_256_mib(client, db, monkeypatch):
    from app.config import get_settings
    assert get_settings().manual_file_max_bytes == 256 * 1024 * 1024
    admin_client(client, db)
    monkeypatch.setattr(get_settings(), "manual_file_max_bytes", 10)
    with patch("app.manual.service.get_storage") as storage:
        response = client.post("/ext/api/v1/admin/manual/files", files={"file": ("large.exe", b"x" * 11)})
        assert response.status_code == 400 and response.json()["code"] == "FILE_TOO_LARGE"
        storage.assert_not_called()
