from app.common.enums import TicketPriority, TicketStatus
from app.db.models.ticket import Ticket, TicketMessage
from tests.conftest import login_as, make_user


def test_create_ticket_forces_p2(client, db):
    user = make_user(db, sub2api_id=1, role="user", username="alice")
    login_as(client, db, user)
    resp = client.post(
        "/ext/api/v1/tickets",
        json={
            "title": "API 报错",
            "description": "详细描述",
            "category": "API_ERROR",
            "ref_ticket_no": "T202601010001",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["priority"] == "P2"
    assert data["status"] == "OPEN"
    assert data["title"] == "API 报错"
    assert data["ref_ticket_no"] == "T202601010001"


def test_user_cannot_see_internal_notes(client, db):
    user = make_user(db, sub2api_id=2, role="user", username="bob")
    admin = make_user(db, sub2api_id=99, role="admin", username="admin")
    login_as(client, db, user)
    created = client.post(
        "/ext/api/v1/tickets",
        json={"title": "t", "description": "d", "category": "OTHER"},
    ).json()
    ticket_id = created["id"]

    # admin adds internal note
    client.cookies.clear()
    login_as(client, db, admin)
    r = client.post(
        f"/ext/api/v1/admin/tickets/{ticket_id}/replies",
        json={"content": "内部备注机密", "is_internal": True},
    )
    assert r.status_code == 201

    # user view
    client.cookies.clear()
    login_as(client, db, user)
    detail = client.get(f"/ext/api/v1/tickets/{ticket_id}").json()
    assert all(not m["is_internal"] for m in detail["messages"])
    assert not any(m["content"] == "内部备注机密" for m in detail["messages"])
    assert not any(e["event_type"] == "INTERNAL_NOTE_ADDED" for e in detail["events"])


def test_closed_cannot_reopen_or_reply(client, db):
    user = make_user(db, sub2api_id=3, role="user", username="c")
    login_as(client, db, user)
    tid = client.post(
        "/ext/api/v1/tickets",
        json={"title": "t", "description": "d", "category": "OTHER"},
    ).json()["id"]
    assert client.post(f"/ext/api/v1/tickets/{tid}/close").status_code == 200
    r = client.post(f"/ext/api/v1/tickets/{tid}/replies", json={"content": "hi"})
    assert r.status_code == 400
    # admin cannot reopen via patch to OPEN from CLOSED
    admin = make_user(db, sub2api_id=100, role="admin", username="a2")
    client.cookies.clear()
    login_as(client, db, admin)
    r2 = client.patch(f"/ext/api/v1/admin/tickets/{tid}", json={"status": "OPEN"})
    assert r2.status_code == 400


def test_claim_atomic_conflict(client, db):
    user = make_user(db, sub2api_id=4, role="user", username="u4")
    a1 = make_user(db, sub2api_id=101, role="admin", username="a1")
    a2 = make_user(db, sub2api_id=102, role="admin", username="a2")
    login_as(client, db, user)
    tid = client.post(
        "/ext/api/v1/tickets",
        json={"title": "t", "description": "d", "category": "OTHER"},
    ).json()["id"]

    client.cookies.clear()
    login_as(client, db, a1)
    assert client.post(f"/ext/api/v1/admin/tickets/{tid}/claim").status_code == 200

    client.cookies.clear()
    login_as(client, db, a2)
    r = client.post(f"/ext/api/v1/admin/tickets/{tid}/claim")
    assert r.status_code == 409
    body = r.json()
    assert body.get("code") == "TICKET_ALREADY_CLAIMED" or "认领" in str(body)


def test_takeover(client, db):
    user = make_user(db, sub2api_id=5, role="user", username="u5")
    a1 = make_user(db, sub2api_id=201, role="admin", username="aa1")
    a2 = make_user(db, sub2api_id=202, role="admin", username="aa2")
    login_as(client, db, user)
    tid = client.post(
        "/ext/api/v1/tickets",
        json={"title": "t", "description": "d", "category": "OTHER"},
    ).json()["id"]
    client.cookies.clear()
    login_as(client, db, a1)
    client.post(f"/ext/api/v1/admin/tickets/{tid}/claim")
    client.cookies.clear()
    login_as(client, db, a2)
    r = client.post(f"/ext/api/v1/admin/tickets/{tid}/takeover")
    assert r.status_code == 200
    assert r.json()["claimed_by_user_id"] == a2.id


def test_user_forbidden_admin_api(client, db):
    user = make_user(db, sub2api_id=6, role="user", username="u6")
    login_as(client, db, user)
    assert client.get("/ext/api/v1/admin/tickets").status_code == 403
