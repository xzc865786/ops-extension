from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO, StringIO

from openpyxl import Workbook
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.enums import ExpenseStatus
from app.db.models.expense import CostCenter, ExpenseClaim, Supplier


def _period_range(period: str, year: int, month: int | None) -> tuple[date, date]:
    if period == "year":
        return date(year, 1, 1), date(year, 12, 31)
    if month is None:
        month = 1
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _base_filter(q, start: date, end: date, category=None, supplier_id=None, cost_center_id=None):
    q = q.where(ExpenseClaim.expense_date >= start, ExpenseClaim.expense_date <= end)
    q = q.where(ExpenseClaim.status.notin_([ExpenseStatus.CANCELLED.value, ExpenseStatus.DRAFT.value]))
    if category:
        q = q.where(ExpenseClaim.category == category)
    if supplier_id:
        q = q.where(ExpenseClaim.supplier_id == supplier_id)
    if cost_center_id:
        q = q.where(ExpenseClaim.cost_center_id == cost_center_id)
    return q


def summary(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> dict:
    start, end = _period_range(period, year, month)
    q = _base_filter(select(ExpenseClaim), start, end, **filters)
    rows = db.scalars(q).all()
    total = sum((r.amount_tax_included for r in rows), Decimal("0"))
    by_status: dict[str, Decimal] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, Decimal("0")) + r.amount_tax_included
    return {
        "period": period,
        "year": year,
        "month": month,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "count": len(rows),
        "total_amount": float(total),
        "by_status": {k: float(v) for k, v in by_status.items()},
        "currency_note": "amounts summed as-is (multi-currency not converted)",
    }


def by_dimension(db: Session, dim: str, *, period: str, year: int, month: int | None = None, **filters) -> list[dict]:
    start, end = _period_range(period, year, month)
    if dim == "category":
        col = ExpenseClaim.category
        label_map = None
    elif dim == "supplier":
        col = ExpenseClaim.supplier_id
    elif dim == "cost_center":
        col = ExpenseClaim.cost_center_id
    else:
        raise ValueError(dim)

    q = select(
        col.label("key"),
        func.count().label("count"),
        func.coalesce(func.sum(ExpenseClaim.amount_tax_included), 0).label("amount"),
    ).where(
        ExpenseClaim.expense_date >= start,
        ExpenseClaim.expense_date <= end,
        ExpenseClaim.status.notin_([ExpenseStatus.CANCELLED.value, ExpenseStatus.DRAFT.value]),
    )
    if filters.get("category"):
        q = q.where(ExpenseClaim.category == filters["category"])
    if filters.get("supplier_id"):
        q = q.where(ExpenseClaim.supplier_id == filters["supplier_id"])
    if filters.get("cost_center_id"):
        q = q.where(ExpenseClaim.cost_center_id == filters["cost_center_id"])
    q = q.group_by(col)
    rows = db.execute(q).all()

    names = {}
    if dim == "supplier":
        ids = [r.key for r in rows if r.key]
        if ids:
            for s in db.scalars(select(Supplier).where(Supplier.id.in_(ids))).all():
                names[s.id] = s.name
    elif dim == "cost_center":
        ids = [r.key for r in rows if r.key]
        if ids:
            for c in db.scalars(select(CostCenter).where(CostCenter.id.in_(ids))).all():
                names[c.id] = c.name

    out = []
    for r in rows:
        key = r.key
        label = str(key) if key is not None else "(未指定)"
        if dim == "supplier":
            label = names.get(key, label)
        elif dim == "cost_center":
            label = names.get(key, label)
        out.append({"key": key, "label": label, "count": r.count, "amount": float(r.amount)})
    out.sort(key=lambda x: x["amount"], reverse=True)
    return out


def payment_status(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> dict:
    start, end = _period_range(period, year, month)
    q = _base_filter(select(ExpenseClaim), start, end, **filters)
    rows = db.scalars(q).all()
    paid = [r for r in rows if r.status == ExpenseStatus.PAID.value]
    unpaid = [r for r in rows if r.status == ExpenseStatus.APPROVED.value]
    return {
        "paid": {
            "count": len(paid),
            "amount": float(sum((r.amount_tax_included for r in paid), Decimal("0"))),
        },
        "unpaid_approved": {
            "count": len(unpaid),
            "amount": float(sum((r.amount_tax_included for r in unpaid), Decimal("0"))),
        },
    }


def invoice_tax(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> dict:
    start, end = _period_range(period, year, month)
    q = _base_filter(select(ExpenseClaim), start, end, **filters)
    rows = db.scalars(q).all()
    with_invoice = [r for r in rows if r.invoice_status == "RECEIVED"]
    without = [r for r in rows if r.invoice_status in ("NONE", "PENDING", None)]
    tax = sum((r.tax_amount or Decimal("0") for r in with_invoice), Decimal("0"))
    deductible = sum(
        (r.tax_amount or Decimal("0") for r in with_invoice if r.deductible),
        Decimal("0"),
    )
    return {
        "with_invoice": {
            "count": len(with_invoice),
            "amount": float(sum((r.amount_tax_included for r in with_invoice), Decimal("0"))),
            "tax_amount": float(tax),
            "deductible_tax": float(deductible),
        },
        "without_invoice": {
            "count": len(without),
            "amount": float(sum((r.amount_tax_included for r in without), Decimal("0"))),
        },
    }


def export_rows(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> list[dict]:
    start, end = _period_range(period, year, month)
    q = _base_filter(select(ExpenseClaim), start, end, **filters)
    rows = db.scalars(q.order_by(ExpenseClaim.expense_date)).all()
    return [
        {
            "claim_no": r.claim_no,
            "expense_date": r.expense_date.isoformat(),
            "category": r.category,
            "status": r.status,
            "currency": r.currency,
            "amount_tax_included": float(r.amount_tax_included),
            "tax_amount": float(r.tax_amount or 0),
            "pay_type": r.pay_type,
            "invoice_status": r.invoice_status,
            "supplier_id": r.supplier_id,
            "cost_center_id": r.cost_center_id,
        }
        for r in rows
    ]


def to_csv(rows: list[dict]) -> bytes:
    import csv

    buf = StringIO()
    if not rows:
        buf.write("claim_no\n")
        return buf.getvalue().encode("utf-8-sig")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "expenses"
    if not rows:
        ws.append(["claim_no"])
    else:
        headers = list(rows[0].keys())
        ws.append(headers)
        for r in rows:
            ws.append([r[h] for h in headers])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
