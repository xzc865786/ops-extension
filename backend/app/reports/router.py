from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.common.errors import bad_request
from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.reports import service

router = APIRouter(prefix="/ext/api/v1/admin/reports", tags=["reports"])


def report_params(
    start_date: date | None = None,
    end_date: date | None = None,
    # Legacy month/year selector, superseded by start_date/end_date.
    period: str | None = Query(None, pattern="^(month|year)$"),
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None, supplier_id: int | None = None,
    cost_center_id: int | None = None, currency: str | None = None,
) -> dict:
    try:
        start, end = service.resolve_range(start_date, end_date, period, year, month)
    except ValueError as exc:
        raise bad_request(str(exc), "INVALID_REPORT_RANGE")
    return dict(start=start, end=end, category=category, supplier_id=supplier_id,
                cost_center_id=cost_center_id, currency=currency)


@router.get("/summary")
def summary(params: dict = Depends(report_params), db: Session = Depends(get_db),
            admin: CurrentUser = Depends(require_admin)):
    return service.summary(db, **params)


@router.get("/by-category")
def by_category(params: dict = Depends(report_params), db: Session = Depends(get_db),
                admin: CurrentUser = Depends(require_admin)):
    return service.by_dimension(db, "category", **params)


@router.get("/by-supplier")
def by_supplier(params: dict = Depends(report_params), db: Session = Depends(get_db),
                admin: CurrentUser = Depends(require_admin)):
    return service.by_dimension(db, "supplier", **params)


@router.get("/by-cost-center")
def by_cost_center(params: dict = Depends(report_params), db: Session = Depends(get_db),
                   admin: CurrentUser = Depends(require_admin)):
    return service.by_dimension(db, "cost_center", **params)


@router.get("/by-month")
def by_month(params: dict = Depends(report_params), db: Session = Depends(get_db),
             admin: CurrentUser = Depends(require_admin)):
    return service.by_month(db, **params)


@router.get("/payment-status")
def payment_status(params: dict = Depends(report_params), db: Session = Depends(get_db),
                   admin: CurrentUser = Depends(require_admin)):
    return service.payment_status(db, **params)


@router.get("/invoice-tax")
def invoice_tax(params: dict = Depends(report_params), db: Session = Depends(get_db),
                admin: CurrentUser = Depends(require_admin)):
    return service.invoice_tax(db, **params)


@router.get("/export")
def export_report(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    view: str = Query("detail", pattern="^(detail|summary|month|category|supplier|cost_center|payment|invoice|all)$"),
    params: dict = Depends(report_params),
    db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin),
):
    if format == "csv" and view == "all":
        raise bad_request("CSV 每次只能导出一种报表", "INVALID_EXPORT_VIEW")
    span = f"{params['start'].isoformat()}_{params['end'].isoformat()}"
    sheets = service.export_sheets(db, **params)
    if format == "xlsx":
        selected = sheets if view == "all" else {view: sheets[view]}
        return Response(
            content=service.to_xlsx(selected),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=expense-report-{span}.xlsx"},
        )
    return Response(
        content=service.to_csv(sheets[view], service.EXPORT_HEADERS[view]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=expense-{view}-{span}.csv"},
    )
