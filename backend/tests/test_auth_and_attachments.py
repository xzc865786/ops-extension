import json
from unittest.mock import MagicMock, patch

from app.attachments.minio_client import validate_attachment
from app.common.errors import AppError
from app.identity.provider import Sub2APIUser
from tests.conftest import login_as, make_user


def test_validate_attachment_whitelist():
    validate_attachment("a.png", "image/png", 100)
    validate_attachment("a.pdf", "application/pdf", 100)
    validate_attachment("a.log", "text/plain", 100)
    try:
        validate_attachment("a.exe", "application/octet-stream", 100)
        assert False
    except AppError as e:
        assert e.status_code == 400
    try:
        validate_attachment("big.png", "image/png", 21 * 1024 * 1024)
        assert False
    except AppError as e:
        assert e.status_code == 400


def test_bootstrap_uses_data_id_and_requires_active(client, db):
    fake = Sub2APIUser(id=888, username="x", email="x@e.com", role="user", status="active")
    with patch("app.auth.bridge.get_identity_provider") as gp:
        provider = MagicMock()
        provider.verify_and_get_user.return_value = fake
        gp.return_value = provider
        resp = client.get(
            "/ext/auth/bootstrap",
            params={"token": "secret-token", "user_id": 888, "next": "/ext/app/tickets"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
    assert "token" not in resp.headers["location"]
    assert resp.headers["location"].startswith("/ext/app/tickets")
    assert "ops_session" in resp.cookies
    # ensure provider got token (not logged — just called)
    provider.verify_and_get_user.assert_called_once_with("secret-token")

    # inactive
    fake2 = Sub2APIUser(id=889, username="y", email="y@e.com", role="user", status="disabled")
    with patch("app.auth.bridge.get_identity_provider") as gp:
        provider = MagicMock()
        provider.verify_and_get_user.return_value = fake2
        gp.return_value = provider
        resp = client.get(
            "/ext/auth/bootstrap",
            params={"token": "t", "next": "/ext/app/tickets"},
            follow_redirects=False,
        )
    assert resp.status_code == 403


def test_auth_me(client, db):
    user = make_user(db, sub2api_id=9, role="admin", username="me")
    login_as(client, db, user)
    r = client.get("/ext/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["sub2api_user_id"] == 9
    assert r.json()["sub2api_role"] == "admin"
