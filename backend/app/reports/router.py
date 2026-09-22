from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.reports import service

router = APIRouter(prefix="/ext/api/v1/admin/reports", tags=["reports"])


def _params(period: str, year: int, month: int | None, category: str | None,
            supplier_id: int | None, cost_center_id: int | None, currency: str | None) -> dict:
    return dict(period=period, year=year, month=month, category=category,
                supplier_id=supplier_id, cost_center_id=cost_center_id, currency=currency)


@router.get("/summary")
def summary(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.summary(db, **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/by-category")
def by_category(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(db, "category", **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/by-supplier")
def by_supplier(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(db, "supplier", **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/by-cost-center")
def by_cost_center(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.by_dimension(db, "cost_center", **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/by-month")
def by_month(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.by_month(db, **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/payment-status")
def payment_status(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.payment_status(db, **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/invoice-tax")
def invoice_tax(
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    return service.invoice_tax(db, **_params(period, year, month, category, supplier_id, cost_center_id, currency))


@router.get("/export")
def export_report(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    view: str = Query("detail", pattern="^(detail|summary|month|category|supplier|cost_center|payment|invoice|all)$"),
    period: str = Query("month", pattern="^(month|year)$"),
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    params = _params(period, year, month, category, supplier_id, cost_center_id, currency)
    if format == "csv" and view == "all":
        from app.common.errors import bad_request
        raise bad_request("CSV 每次只能导出一种报表", "INVALID_EXPORT_VIEW")
    sheets = service.export_sheets(db, **params)
    if format == "xlsx":
        selected = sheets if view == "all" else {view: sheets[view]}
        return Response(
            content=service.to_xlsx(selected),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=expense-report.xlsx"},
        )
    return Response(
        content=service.to_csv(sheets[view], service.EXPORT_HEADERS[view]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=expense-{view}.csv"},
    )
