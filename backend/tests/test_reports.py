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
    assert s.json()["currencies"][0]["count"] >= 1

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


def _approved_claim(client, expense_date: str, amount: str = "10"):
    claim = client.post("/ext/api/v1/admin/expenses", json={
        "expense_date": expense_date, "category": "CDN", "currency": "CNY",
        "pay_type": "COMPANY_DIRECT",
        "items": [{"description": "cdn", "quantity": 1, "unit_price": amount}],
    })
    assert claim.status_code == 201, claim.text
    cid = claim.json()["id"]
    assert client.post(f"/ext/api/v1/admin/expenses/{cid}/submit").status_code == 200
    assert client.post(f"/ext/api/v1/admin/expenses/{cid}/approve").status_code == 200


def test_reports_date_range_is_inclusive(client, db):
    admin = make_user(db, sub2api_id=61, role="admin", username="range")
    login_as(client, db, admin)
    for day in ("2025-08-31", "2025-09-01", "2025-09-30", "2025-10-01"):
        _approved_claim(client, day)

    s = client.get("/ext/api/v1/admin/reports/summary",
                   params={"start_date": "2025-09-01", "end_date": "2025-09-30"})
    assert s.status_code == 200
    body = s.json()
    assert (body["start"], body["end"]) == ("2025-09-01", "2025-09-30")
    assert body["currencies"][0]["count"] == 2

    months = client.get("/ext/api/v1/admin/reports/by-month",
                        params={"start_date": "2025-08-01", "end_date": "2025-10-31"}).json()
    assert [(r["month"], r["count"]) for r in months] == [("2025-08", 1), ("2025-09", 2), ("2025-10", 1)]

    legacy = client.get("/ext/api/v1/admin/reports/summary",
                        params={"period": "month", "year": 2025, "month": 9}).json()
    assert legacy["currencies"][0]["count"] == 2

    export = client.get("/ext/api/v1/admin/reports/export", params={
        "format": "csv", "view": "summary", "start_date": "2025-09-01", "end_date": "2025-09-30",
    })
    assert export.status_code == 200
    assert "expense-summary-2025-09-01_2025-09-30.csv" in export.headers["content-disposition"]


def test_reports_reject_invalid_ranges(client, db):
    admin = make_user(db, sub2api_id=62, role="admin", username="badrange")
    login_as(client, db, admin)
    url = "/ext/api/v1/admin/reports/summary"
    for params in (
        {},
        {"start_date": "2025-09-01"},
        {"start_date": "2025-09-30", "end_date": "2025-09-01"},
        {"start_date": "2020-01-01", "end_date": "2025-12-31"},
        {"period": "month", "year": 2025},
    ):
        r = client.get(url, params=params)
        assert r.status_code == 400, params
        assert r.json()["code"] == "INVALID_REPORT_RANGE"
    assert client.get(url, params={"start_date": "2025-13-01", "end_date": "2025-12-31"}).status_code == 422
    assert client.get(url, params={"start_date": "2023-01-01", "end_date": "2025-12-31"}).status_code == 200
