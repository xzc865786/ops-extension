from datetime import date

from tests.conftest import login_as, make_user


def test_reports_summary_and_export(client, db):
    admin = make_user(db, sub2api_id=60, role="admin", username="rep")
    login_as(client, db, admin)
    today = date.today()
    # create & pay one expense
    c = client.post(
        "/ext/api/v1/admin/expenses",
        json={
            "expense_date": today.isoformat(),
            "category": "CDN",
            "currency": "CNY",
            "pay_type": "PERSONAL_ADVANCE",
            "items": [{"description": "cdn", "quantity": 1, "unit_price": "50"}],
        },
    ).json()
    cid = c["id"]
    client.post(f"/ext/api/v1/admin/expenses/{cid}/submit")
    client.post(f"/ext/api/v1/admin/expenses/{cid}/approve")
    client.post(f"/ext/api/v1/admin/expenses/{cid}/payments", json={"amount": "50", "mark_paid": True})

    s = client.get(
        "/ext/api/v1/admin/reports/summary",
        params={"period": "year", "year": today.year},
    )
    assert s.status_code == 200
    assert s.json()["count"] >= 1

    byc = client.get(
        "/ext/api/v1/admin/reports/by-category",
        params={"period": "year", "year": today.year},
    )
    assert byc.status_code == 200
    assert any(i["key"] == "CDN" for i in byc.json())

    csv_r = client.get(
        "/ext/api/v1/admin/reports/export",
        params={"format": "csv", "period": "year", "year": today.year},
    )
    assert csv_r.status_code == 200
    assert "claim_no" in csv_r.text

    xlsx_r = client.get(
        "/ext/api/v1/admin/reports/export",
        params={"format": "xlsx", "period": "year", "year": today.year},
    )
    assert xlsx_r.status_code == 200
    assert xlsx_r.content[:2] == b"PK"
