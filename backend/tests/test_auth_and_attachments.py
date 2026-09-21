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


def test_token_seal_roundtrip():
    from app.auth.token_seal import seal_token, unseal_token

    sealed = seal_token("secret", "bearer-abc")
    assert sealed != "bearer-abc"
    assert unseal_token("secret", sealed) == "bearer-abc"
    assert unseal_token("wrong", sealed) is None


def test_resolve_public_minio_unset_by_default(monkeypatch):
    from app.attachments.minio_client import resolve_public_minio_target
    from app.config import get_settings

    monkeypatch.delenv("MINIO_PUBLIC_ENDPOINT", raising=False)
    monkeypatch.delenv("MINIO_PUBLIC_URL", raising=False)
    get_settings.cache_clear()
    assert resolve_public_minio_target() is None
    get_settings.cache_clear()


def test_download_streams_through_proxy_by_default(client, db, monkeypatch):
    from unittest.mock import MagicMock, patch

    from app.attachments.minio_client import reset_storage_for_tests
    from app.config import get_settings
    from app.db.models.ticket import Ticket, TicketAttachment

    monkeypatch.delenv("MINIO_PUBLIC_ENDPOINT", raising=False)
    monkeypatch.delenv("MINIO_PUBLIC_URL", raising=False)
    get_settings.cache_clear()
    reset_storage_for_tests()

    user = make_user(db, sub2api_id=40, role="user", username="dl")
    login_as(client, db, user)
    ticket = Ticket(
        ticket_no="T209901010001",
        creator_user_id=user.id,
        title="t",
        description="d",
        category="OTHER",
        priority="P2",
        status="OPEN",
    )
    db.add(ticket)
    db.flush()
    att = TicketAttachment(
        ticket_id=ticket.id,
        uploader_user_id=user.id,
        object_key="tickets/1/x/a.png",
        file_name="a.png",
        mime_type="image/png",
        file_size=4,
        sha256="abcd",
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    mock_storage = MagicMock()
    mock_storage.presigned_get_public.return_value = None
    mock_storage.get_bytes.return_value = b"PNG!"
    with patch("app.attachments.router.get_storage", return_value=mock_storage):
        r = client.get(f"/ext/api/v1/attachments/{att.id}/download")
    assert r.status_code == 200
    assert r.content == b"PNG!"
    mock_storage.get_bytes.assert_called_once_with("tickets/1/x/a.png")
    mock_storage.presigned_get_public.assert_called_once()
    assert not mock_storage.presigned_get.called


def test_download_presign_redirect_when_public_endpoint(client, db, monkeypatch):
    from unittest.mock import MagicMock, patch

    from app.attachments.minio_client import reset_storage_for_tests
    from app.config import get_settings
    from app.db.models.ticket import Ticket, TicketAttachment

    monkeypatch.setenv("MINIO_PUBLIC_ENDPOINT", "files.example.com:9000")
    get_settings.cache_clear()
    reset_storage_for_tests()

    user = make_user(db, sub2api_id=41, role="user", username="dl2")
    login_as(client, db, user)
    ticket = Ticket(
        ticket_no="T209901010002",
        creator_user_id=user.id,
        title="t",
        description="d",
        category="OTHER",
        priority="P2",
        status="OPEN",
    )
    db.add(ticket)
    db.flush()
    att = TicketAttachment(
        ticket_id=ticket.id,
        uploader_user_id=user.id,
        object_key="tickets/1/y/b.png",
        file_name="b.png",
        mime_type="image/png",
        file_size=4,
        sha256="abcd",
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    mock_storage = MagicMock()
    mock_storage.presigned_get_public.return_value = (
        "https://files.example.com:9000/qiyuan-ops/obj?X-Amz-Signature=x"
    )
    with patch("app.attachments.router.get_storage", return_value=mock_storage):
        r = client.get(
            f"/ext/api/v1/attachments/{att.id}/download",
            follow_redirects=False,
        )
    assert r.status_code in (302, 307)
    assert "files.example.com" in r.headers["location"]
    mock_storage.get_bytes.assert_not_called()
    get_settings.cache_clear()
    monkeypatch.delenv("MINIO_PUBLIC_ENDPOINT", raising=False)


def test_session_revalidate_clears_inactive(client, db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock, patch

    from app.auth.session import create_session
    from app.config import get_settings
    from app.db.models.user import Session as UserSession
    from app.identity.provider import Sub2APIUser

    monkeypatch.setenv("SESSION_REVALIDATE_SECONDS", "0")
    get_settings.cache_clear()

    user = make_user(db, sub2api_id=50, role="user", username="rv")
    sess = create_session(db, user, bearer_token="tok-50")
    sess.last_checked_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    client.cookies.set("ops_session", str(sess.id), path="/ext")

    inactive = Sub2APIUser(
        id=50, username="rv", email="rv@e.com", role="user", status="disabled"
    )
    with patch("app.identity.sub2api.get_identity_provider") as gp:
        provider = MagicMock()
        provider.verify_and_get_user.return_value = inactive
        gp.return_value = provider
        r = client.get("/ext/api/v1/auth/me")
    assert r.status_code == 401
    sid = sess.id
    db.expunge_all()
    assert db.get(UserSession, sid) is None
    get_settings.cache_clear()
    monkeypatch.delenv("SESSION_REVALIDATE_SECONDS", raising=False)


def test_session_revalidate_refreshes_role(client, db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock, patch

    from app.auth.session import create_session
    from app.config import get_settings
    from app.identity.provider import Sub2APIUser

    monkeypatch.setenv("SESSION_REVALIDATE_SECONDS", "0")
    get_settings.cache_clear()

    user = make_user(db, sub2api_id=51, role="user", username="promo")
    sess = create_session(db, user, bearer_token="tok-51")
    sess.last_checked_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    client.cookies.set("ops_session", str(sess.id), path="/ext")

    promoted = Sub2APIUser(
        id=51, username="promo", email="p@e.com", role="admin", status="active"
    )
    with patch("app.identity.sub2api.get_identity_provider") as gp:
        provider = MagicMock()
        provider.verify_and_get_user.return_value = promoted
        gp.return_value = provider
        r = client.get("/ext/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["sub2api_role"] == "admin"
    db.refresh(user)
    assert user.sub2api_role == "admin"
    get_settings.cache_clear()
    monkeypatch.delenv("SESSION_REVALIDATE_SECONDS", raising=False)
