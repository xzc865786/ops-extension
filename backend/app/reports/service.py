"""Expense reports. All monetary aggregates are partitioned by currency."""

import csv
from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.common.enums import ExpenseStatus
from app.db.models.expense import CostCenter, ExpenseClaim, Supplier

SPENDING = {ExpenseStatus.APPROVED.value, ExpenseStatus.PAID.value}
VISIBLE = SPENDING | {ExpenseStatus.SUBMITTED.value, ExpenseStatus.REJECTED.value}
DETAIL_HEADERS = [
    "claim_no", "expense_date", "category", "status", "currency",
    "amount_tax_included", "tax_amount", "paid_total", "remaining_amount",
    "payment_reconciliation_required",
    "pay_type", "invoice_status", "supplier_id", "cost_center_id",
]
EXPORT_HEADERS = {
    "detail": DETAIL_HEADERS,
    "summary": ["currency", "count", "total_amount", "tax_amount", "submitted_count", "submitted_amount",
                "rejected_count", "rejected_amount"],
    "month": ["month", "currency", "count", "amount", "tax_amount"],
    "category": ["currency", "key", "label", "count", "amount"],
    "supplier": ["currency", "key", "label", "count", "amount"],
    "cost_center": ["currency", "key", "label", "count", "amount"],
    "payment": ["currency", "paid_amount", "unpaid_approved_amount",
                "rejected_count", "rejected_amount", "anomaly_count"],
    "invoice": ["currency", "with_invoice_count", "with_invoice_amount",
                "tax_amount", "deductible_tax", "without_invoice_count",
                "without_invoice_amount"],
}


def _period_range(period: str, year: int, month: int | None) -> tuple[date, date]:
    if period == "year":
        return date(year, 1, 1), date(year, 12, 31)
    selected = month or 1
    return date(year, selected, 1), date(year, selected, monthrange(year, selected)[1])


def _rows(db: Session, *, period: str, year: int, month: int | None = None,
          category=None, supplier_id=None, cost_center_id=None, currency=None):
    start, end = _period_range(period, year, month)
    q = select(ExpenseClaim).options(selectinload(ExpenseClaim.payments)).where(
        ExpenseClaim.expense_date >= start,
        ExpenseClaim.expense_date <= end,
        ExpenseClaim.status.in_(VISIBLE),
    )
    if category:
        q = q.where(ExpenseClaim.category == category)
    if supplier_id:
        q = q.where(ExpenseClaim.supplier_id == supplier_id)
    if cost_center_id:
        q = q.where(ExpenseClaim.cost_center_id == cost_center_id)
    if currency:
        q = q.where(ExpenseClaim.currency == currency.upper())
    return db.scalars(q.order_by(ExpenseClaim.expense_date, ExpenseClaim.id)).all()


def _paid(claim: ExpenseClaim) -> Decimal:
    return sum((p.amount for p in claim.payments if p.currency == claim.currency), Decimal("0"))


def _anomalous(claim: ExpenseClaim) -> bool:
    paid = _paid(claim)
    return (
        any(p.currency != claim.currency for p in claim.payments)
        or any(p.amount <= 0 for p in claim.payments)
        or paid > claim.amount_tax_included
        or (claim.status == ExpenseStatus.APPROVED.value and paid == claim.amount_tax_included)
        or (claim.status == ExpenseStatus.PAID.value and paid != claim.amount_tax_included)
    )


def summary(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> dict:
    rows = _rows(db, period=period, year=year, month=month, **filters)
    groups: dict[str, dict] = {}
    for claim in rows:
        group = groups.setdefault(claim.currency, {
            "currency": claim.currency, "count": 0, "total_amount": Decimal("0"),
            "tax_amount": Decimal("0"),
            "by_status": {},
        })
        status = group["by_status"].setdefault(claim.status, {"count": 0, "amount": Decimal("0")})
        status["count"] += 1
        status["amount"] += claim.amount_tax_included
        if claim.status in SPENDING:
            group["count"] += 1
            group["total_amount"] += claim.amount_tax_included
            group["tax_amount"] += claim.tax_amount or Decimal("0")
    currencies = []
    for group in sorted(groups.values(), key=lambda g: g["currency"]):
        currencies.append({
            **group,
            "total_amount": float(group["total_amount"]),
            "tax_amount": float(group["tax_amount"]),
            "by_status": {
                status: {"count": value["count"], "amount": float(value["amount"])}
                for status, value in group["by_status"].items()
            },
        })
    start, end = _period_range(period, year, month)
    return {"period": period, "year": year, "month": month,
            "start": start.isoformat(), "end": end.isoformat(), "currencies": currencies}


def by_dimension(db: Session, dim: str, *, period: str, year: int,
                 month: int | None = None, **filters) -> list[dict]:
    if dim not in {"category", "supplier", "cost_center"}:
        raise ValueError(dim)
    claims = [r for r in _rows(db, period=period, year=year, month=month, **filters)
              if r.status in SPENDING]
    attr = {"category": "category", "supplier": "supplier_id",
            "cost_center": "cost_center_id"}[dim]
    grouped: dict[tuple[str, str | int | None], dict] = {}
    for claim in claims:
        key = getattr(claim, attr)
        row = grouped.setdefault((claim.currency, key), {
            "currency": claim.currency, "key": key, "count": 0, "amount": Decimal("0"),
        })
        row["count"] += 1
        row["amount"] += claim.amount_tax_included
    names: dict[int, str] = {}
    if dim in {"supplier", "cost_center"}:
        ids = {key for _, key in grouped if key is not None}
        if ids:
            model = Supplier if dim == "supplier" else CostCenter
            names = {x.id: x.name for x in db.scalars(select(model).where(model.id.in_(ids)))}
    result = []
    for row in grouped.values():
        key = row["key"]
        result.append({
            **row, "label": names.get(key, str(key) if key is not None else "(未指定)"),
            "amount": float(row["amount"]),
        })
    return sorted(result, key=lambda r: (r["currency"], -r["amount"], str(r["key"])))


def by_month(db: Session, *, period: str, year: int, month: int | None = None, **filters) -> list[dict]:
    groups: dict[tuple[str, str], dict] = {}
    for claim in _rows(db, period=period, year=year, month=month, **filters):
        if claim.status not in SPENDING:
            continue
        key = (claim.expense_date.strftime("%Y-%m"), claim.currency)
        row = groups.setdefault(key, {"month": key[0], "currency": key[1], "count": 0,
                                      "amount": Decimal("0"), "tax_amount": Decimal("0")})
        row["count"] += 1
        row["amount"] += claim.amount_tax_included
        row["tax_amount"] += claim.tax_amount or Decimal("0")
    return [{**r, "amount": float(r["amount"]), "tax_amount": float(r["tax_amount"])}
            for _, r in sorted(groups.items())]


def payment_status(db: Session, *, period: str, year: int,
                   month: int | None = None, **filters) -> dict:
    groups: dict[str, dict] = {}
    for claim in _rows(db, period=period, year=year, month=month, **filters):
        group = groups.setdefault(claim.currency, {
            "currency": claim.currency, "paid_amount": Decimal("0"),
            "unpaid_approved_amount": Decimal("0"), "rejected_count": 0,
            "rejected_amount": Decimal("0"), "anomalies": [],
        })
        if claim.status in SPENDING:
            if _anomalous(claim):
                group["anomalies"].append(claim.claim_no)
                continue
            paid = _paid(claim)
            group["paid_amount"] += paid
            if claim.status == ExpenseStatus.APPROVED.value:
                group["unpaid_approved_amount"] += claim.amount_tax_included - paid
        elif claim.status == ExpenseStatus.REJECTED.value:
            group["rejected_count"] += 1
            group["rejected_amount"] += claim.amount_tax_included
    return {"currencies": [
        {**g, "paid_amount": float(g["paid_amount"]),
         "unpaid_approved_amount": float(g["unpaid_approved_amount"]),
         "rejected_amount": float(g["rejected_amount"]),
         "anomaly_count": len(g["anomalies"])}
        for g in sorted(groups.values(), key=lambda x: x["currency"])
    ]}


def invoice_tax(db: Session, *, period: str, year: int,
                month: int | None = None, **filters) -> dict:
    groups: dict[str, dict] = {}
    for claim in _rows(db, period=period, year=year, month=month, **filters):
        if claim.status not in SPENDING:
            continue
        group = groups.setdefault(claim.currency, {
            "currency": claim.currency, "with_invoice_count": 0,
            "with_invoice_amount": Decimal("0"), "tax_amount": Decimal("0"),
            "deductible_tax": Decimal("0"), "without_invoice_count": 0,
            "without_invoice_amount": Decimal("0"),
        })
        if claim.invoice_status == "RECEIVED":
            group["with_invoice_count"] += 1
            group["with_invoice_amount"] += claim.amount_tax_included
            group["tax_amount"] += claim.tax_amount or Decimal("0")
            if claim.deductible:
                group["deductible_tax"] += claim.tax_amount or Decimal("0")
        else:
            group["without_invoice_count"] += 1
            group["without_invoice_amount"] += claim.amount_tax_included
    return {"currencies": [
        {k: float(v) if isinstance(v, Decimal) else v for k, v in group.items()}
        for group in sorted(groups.values(), key=lambda g: g["currency"])
    ]}


def export_rows(db: Session, *, period: str, year: int,
                month: int | None = None, **filters) -> list[dict]:
    return [{
        "claim_no": r.claim_no, "expense_date": r.expense_date.isoformat(),
        "category": r.category, "status": r.status, "currency": r.currency,
        "amount_tax_included": float(r.amount_tax_included),
        "tax_amount": float(r.tax_amount or 0), "paid_total": float(_paid(r)),
        "remaining_amount": float(r.amount_tax_included - _paid(r)) if r.status in SPENDING else 0,
        "payment_reconciliation_required": _anomalous(r) if r.status in SPENDING else False,
        "pay_type": r.pay_type, "invoice_status": r.invoice_status,
        "supplier_id": r.supplier_id, "cost_center_id": r.cost_center_id,
    } for r in _rows(db, period=period, year=year, month=month, **filters)]


def export_sheets(db: Session, *, period: str, year: int,
                  month: int | None = None, **filters) -> dict[str, list[dict]]:
    overview = summary(db, period=period, year=year, month=month, **filters)
    summary_rows = []
    for group in overview["currencies"]:
        submitted = group["by_status"].get(ExpenseStatus.SUBMITTED.value, {})
        rejected = group["by_status"].get(ExpenseStatus.REJECTED.value, {})
        summary_rows.append({
            "currency": group["currency"], "count": group["count"],
            "total_amount": group["total_amount"],
            "tax_amount": group["tax_amount"],
            "submitted_count": submitted.get("count", 0),
            "submitted_amount": submitted.get("amount", 0),
            "rejected_count": rejected.get("count", 0),
            "rejected_amount": rejected.get("amount", 0),
        })
    payments = payment_status(db, period=period, year=year, month=month, **filters)
    return {
        "detail": export_rows(db, period=period, year=year, month=month, **filters),
        "summary": summary_rows,
        "month": by_month(db, period=period, year=year, month=month, **filters),
        "category": by_dimension(db, "category", period=period, year=year, month=month, **filters),
        "supplier": by_dimension(db, "supplier", period=period, year=year, month=month, **filters),
        "cost_center": by_dimension(db, "cost_center", period=period, year=year, month=month, **filters),
        "payment": [{k: value for k, value in row.items() if k != "anomalies"}
                    for row in payments["currencies"]],
        "invoice": invoice_tax(db, period=period, year=year, month=month, **filters)["currencies"],
    }


def to_csv(rows: list[dict], headers: list[str] | None = None) -> bytes:
    columns = headers or (list(rows[0]) if rows else DETAIL_HEADERS)
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(sheets: dict[str, list[dict]] | list[dict]) -> bytes:
    if isinstance(sheets, list):
        sheets = {"detail": sheets}
    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = name
        columns = EXPORT_HEADERS[name]
        ws.append(columns)
        for row in rows:
            ws.append([row.get(column) for column in columns])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
