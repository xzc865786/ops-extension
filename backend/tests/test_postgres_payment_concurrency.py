"""Run with OPS_TEST_POSTGRES_URL against an isolated disposable PostgreSQL DB."""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.common.errors import AppError
from app.db.base import Base
from app.db.models.expense import ExpenseClaim, ExpensePayment
from app.db.models.user import ExtensionUser
from app.deps import CurrentUser
from app.expenses.schemas import PaymentCreate
from app.expenses.service import add_payment
import app.db.models  # noqa: F401


@pytest.mark.skipif(not os.getenv("OPS_TEST_POSTGRES_URL"), reason="no disposable PostgreSQL test URL")
def test_simultaneous_payments_cannot_overpay():
    url = os.environ["OPS_TEST_POSTGRES_URL"]
    schema = "ops_payment_" + uuid.uuid4().hex[:12]
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
        with factory() as db:
            user = ExtensionUser(sub2api_user_id=9001, sub2api_role="admin")
            db.add(user)
            db.flush()
            claim = ExpenseClaim(
                claim_no="E209901010001", applicant_user_id=user.id,
                expense_date=date.today(), category="CDN", currency="CNY",
                amount_tax_included=Decimal("100"), pay_type="COMPANY_DIRECT",
                status="APPROVED", invoice_status="NONE",
            )
            db.add(claim)
            db.commit()
            user_id, claim_id = user.id, claim.id
        barrier = threading.Barrier(2)

        def pay():
            with factory() as db:
                claim = db.get(ExpenseClaim, claim_id)
                actor = CurrentUser(id=user_id, sub2api_user_id=9001,
                                    username_snapshot=None, email_snapshot=None,
                                    sub2api_role="admin")
                barrier.wait(timeout=10)
                try:
                    add_payment(db, claim, actor, PaymentCreate(amount=Decimal("70")))
                    return "paid"
                except AppError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: pay(), range(2)))
        assert results.count("paid") == 1
        assert results.count("PAYMENT_EXCEEDS_BALANCE") == 1
        with factory() as db:
            payments = db.scalars(select(ExpensePayment)).all()
            assert len(payments) == 1
            assert payments[0].amount == Decimal("70")
            assert db.get(ExpenseClaim, claim_id).status == "APPROVED"
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin_engine.dispose()
