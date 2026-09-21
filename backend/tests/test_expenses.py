from datetime import date
from decimal import Decimal

from tests.conftest import login_as, make_user


def test_expense_flow_self_approve(client, db):
    admin = make_user(db, sub2api_id=50, role="admin", username="fin")
    login_as(client, db, admin)

    # seed cost center via API
    cc = client.post(
        "/ext/api/v1/admin/cost-centers",
        json={"code": "RND", "name": "研发"},
    ).json()
    pa = client.post(
        "/ext/api/v1/admin/payment-accounts",
        json={"name": "公户", "account_type": "COMPANY_BANK", "account_no_masked": "****1"},
    ).json()

    created = client.post(
        "/ext/api/v1/admin/expenses",
        json={
            "expense_date": date.today().isoformat(),
            "category": "CLOUD_SERVER",
            "cost_center_id": cc["id"],
            "currency": "CNY",
            "pay_type": "COMPANY_DIRECT",
            "payment_account_id": pa["id"],
            "description": "云主机",
            "items": [{"description": "ECS", "quantity": 1, "unit_price": "100.00"}],
        },
    )
    assert created.status_code == 201, created.text
    claim_id = created.json()["id"]
    assert created.json()["status"] == "DRAFT"
    assert float(created.json()["amount_tax_included"]) == 100.0

    assert client.post(f"/ext/api/v1/admin/expenses/{claim_id}/submit").status_code == 200
    # applicant == approver allowed
    approved = client.post(f"/ext/api/v1/admin/expenses/{claim_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by_user_id"] == admin.id

    paid = client.post(
        f"/ext/api/v1/admin/expenses/{claim_id}/payments",
        json={"amount": "100.00", "mark_paid": True},
    )
    assert paid.status_code == 201
    assert paid.json()["status"] == "PAID"


def test_user_cannot_access_expenses(client, db):
    user = make_user(db, sub2api_id=7, role="user", username="u7")
    login_as(client, db, user)
    assert client.get("/ext/api/v1/admin/expenses").status_code == 403
