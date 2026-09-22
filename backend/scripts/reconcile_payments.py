"""Read-only payment audit; explicit, reviewed CSV repair for legacy PAID claims.

Run from backend: python -m scripts.reconcile_payments audit
Repair CSV columns: claim_no,expected_amount,expected_paid,action,reason,reference_no,payment_date
Actions: restore_approved or record_payment. The latter requires reference_no and payment_date.
"""

import argparse
import csv
import sys
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.common.enums import ExpenseEventType, ExpenseStatus
from app.db.models.expense import ExpenseClaim, ExpensePayment
from app.db.models.user import ExtensionUser
from app.db.session import SessionLocal
from app.expenses.service import add_event


def inspect_claim(claim: ExpenseClaim) -> dict:
    paid = sum((p.amount for p in claim.payments if p.currency == claim.currency), Decimal("0"))
    mismatch = any(p.currency != claim.currency for p in claim.payments)
    reasons = []
    if mismatch:
        reasons.append("currency_mismatch")
    if any(p.amount <= 0 for p in claim.payments):
        reasons.append("invalid_payment_amount")
    if paid > claim.amount_tax_included:
        reasons.append("overpaid")
    if claim.status == ExpenseStatus.PAID.value and paid < claim.amount_tax_included:
        reasons.append("paid_without_full_payment")
    if claim.status == ExpenseStatus.APPROVED.value and paid == claim.amount_tax_included:
        reasons.append("approved_but_fully_paid")
    return {
        "claim_no": claim.claim_no,
        "status": claim.status,
        "currency": claim.currency,
        "amount": str(claim.amount_tax_included),
        "paid": str(paid),
        "reason": "+".join(reasons),
    }


def audit(db: Session) -> list[dict]:
    claims = db.scalars(select(ExpenseClaim).options(selectinload(ExpenseClaim.payments)))
    return [row for claim in claims if (row := inspect_claim(claim))["reason"]]


def repair(db: Session, rows: list[dict], actor_id: int) -> None:
    actor = db.get(ExtensionUser, actor_id)
    if actor is None or actor.sub2api_role != "admin":
        raise ValueError("actor-user-id must identify an extension admin")
    seen: set[str] = set()
    for row in rows:
        number = row["claim_no"].strip()
        if number in seen:
            raise ValueError(f"duplicate claim_no: {number}")
        seen.add(number)
        claim = db.scalar(select(ExpenseClaim).where(ExpenseClaim.claim_no == number)
                          .with_for_update().execution_options(populate_existing=True))
        if claim is None or claim.status != ExpenseStatus.PAID.value:
            raise ValueError(f"{number}: claim is not PAID")
        payments = db.scalars(select(ExpensePayment).where(ExpensePayment.claim_id == claim.id)).all()
        if any(p.currency != claim.currency for p in payments):
            raise ValueError(f"{number}: currency mismatch requires separate investigation")
        if any(p.amount <= 0 for p in payments):
            raise ValueError(f"{number}: invalid payment amount requires separate investigation")
        paid = sum((p.amount for p in payments), Decimal("0"))
        if (claim.amount_tax_included != Decimal(row["expected_amount"])
                or paid != Decimal(row["expected_paid"])):
            raise ValueError(f"{number}: expected amounts changed; re-audit")
        if paid >= claim.amount_tax_included:
            raise ValueError(f"{number}: not underpaid")
        reason = row["reason"].strip()
        if not reason:
            raise ValueError(f"{number}: reason required")
        action = row["action"].strip()
        if action == "restore_approved":
            claim.status = ExpenseStatus.APPROVED.value
            claim.paid_at = None
            claim.paid_by_user_id = None
        elif action == "record_payment":
            reference = row["reference_no"].strip()
            payment_date = row["payment_date"].strip()
            if not reference or not payment_date:
                raise ValueError(f"{number}: external payment reference and date required")
            paid_at = datetime.fromisoformat(payment_date)
            if paid_at.tzinfo is None:
                raise ValueError(f"{number}: payment_date must include timezone")
            remaining = claim.amount_tax_included - paid
            db.add(ExpensePayment(
                claim_id=claim.id, payment_account_id=claim.payment_account_id,
                amount=remaining, currency=claim.currency,
                paid_at=paid_at,
                reference_no=reference, notes=f"Legacy reconciliation: {reason}",
                created_by_user_id=actor.id,
            ))
            if claim.paid_at is None:
                claim.paid_at = paid_at
                claim.paid_by_user_id = actor.id
            add_event(db, claim.id, actor.id, ExpenseEventType.PAYMENT_ADDED.value,
                      new={"amount": str(remaining), "currency": claim.currency, "reference_no": reference})
        else:
            raise ValueError(f"{number}: invalid action")
        add_event(db, claim.id, actor.id, ExpenseEventType.PAYMENT_RECONCILED.value,
                  old={"status": "PAID", "paid": str(paid)},
                  new={"status": claim.status,
                       "paid": str(claim.amount_tax_included if action == "record_payment" else paid),
                       "action": action, "reason": reason,
                       "reference_no": row["reference_no"].strip() if action == "record_payment" else None})
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    apply = sub.add_parser("apply")
    apply.add_argument("--approved-list", required=True)
    apply.add_argument("--actor-user-id", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "audit":
            writer = csv.DictWriter(sys.stdout, fieldnames=["claim_no", "status", "currency", "amount", "paid", "reason"])
            writer.writeheader()
            writer.writerows(audit(db))
        else:
            with open(args.approved_list, newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            if not rows:
                raise ValueError("approved list is empty")
            try:
                repair(db, rows, args.actor_user_id)
            except Exception:
                db.rollback()
                raise
            print(f"reconciled {len(rows)} claims")


if __name__ == "__main__":
    main()
