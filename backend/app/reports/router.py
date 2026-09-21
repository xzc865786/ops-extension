from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.reports import service

router = APIRouter(prefix="/ext/api/v1/admin/reports", tags=["reports"])


def _filters(
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
):
    return {"category": category, "supplier_id": supplier_id, "cost_center_id": cost_center_id}


@router.get("/summary")
def report_summary(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.summary(db, period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id))


@router.get("/by-category")
def by_category(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(
        db, "category", period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )


@router.get("/by-supplier")
def by_supplier(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(
        db, "supplier", period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )


@router.get("/by-cost-center")
def by_cost_center(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(
        db, "cost_center", period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )


@router.get("/payment-status")
def payment_status(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.payment_status(
        db, period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )


@router.get("/invoice-tax")
def invoice_tax(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    return service.invoice_tax(
        db, period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )


@router.get("/export")
def export_report(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = None,
    category: str | None = None,
    supplier_id: int | None = None,
    cost_center_id: int | None = None,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    rows = service.export_rows(
        db, period=period, year=year, month=month, **_filters(category, supplier_id, cost_center_id)
    )
    if format == "xlsx":
        data = service.to_xlsx(rows)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=expense-report.xlsx"},
        )
    data = service.to_csv(rows)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=expense-report.csv"},
    )
