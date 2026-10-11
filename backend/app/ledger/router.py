from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage, validate_attachment
from app.common.errors import AppError, conflict, not_found
from app.db.models.ledger import ExpenseRecord, Reimbursement, LedgerAttachment, ReimbursementItem
from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.ledger import service, rates, reports
from app.ledger.schemas import RecordCreate, RecordUpdate, VersionReason, BatchInput, HistoryConfirm

router = APIRouter(prefix="/ext/api/v1/admin", tags=["expense-ledger"], dependencies=[Depends(require_admin)])


def filters(month: str | None = Query(None, pattern=r"^(\d{4}-\d{2})?$"),
            payer: str | None = Query(None, max_length=100), category: str | None = None,
            status: str | None = Query(None, pattern="^(PENDING|REIMBURSED|NOT_REQUIRED)$"),
            keyword: str | None = Query(None, max_length=200), mine: bool = False, voided: bool = False):
    return dict(month=rates.today().strftime("%Y-%m") if month is None else month,
                payer=payer, category=category, status=status, keyword=keyword, mine=mine, voided=voided)


def mutate(db, operation):
    try:
        return operation()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("记录已被其他操作处理，请刷新后重试", "CONCURRENT_CONFLICT") from exc
    except Exception:
        db.rollback()
        raise


@router.get("/expense-records/meta")
def meta(db: Session = Depends(get_db)):
    return {"categories": [{"value": k, "label": v} for k, v in service.EXPENSE_CATEGORY_LABELS.items() if k != "STAFF_ADVANCE"],
            "payers": db.scalars(select(ExpenseRecord.payer).distinct().order_by(ExpenseRecord.payer)).all(),
            "merchants": db.scalars(select(ExpenseRecord.merchant).where(ExpenseRecord.merchant != "").distinct().order_by(ExpenseRecord.merchant)).all(),
            "today": rates.today().isoformat()}


@router.get("/expense-records/rate")
def rate(refresh: bool = False, db: Session = Depends(get_db)):
    return service.serialize(rates.latest_quote(db, refresh=refresh))


@router.get("/expense-records/history")
def history(db: Session = Depends(get_db)):
    return service.history_inventory(db)


@router.post("/expense-records/history/{claim_id}/confirm", status_code=201)
def confirm(claim_id: int, body: HistoryConfirm, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    row = mutate(db, lambda: service.confirm_history(db, actor, claim_id, body))
    return service.detail(db, row.id)


@router.get("/expense-records/monthly")
def monthly(params: dict = Depends(filters), db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    params["voided"] = False
    return reports.monthly(db, params, actor)


@router.get("/expense-records/export")
def export(params: dict = Depends(filters), db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    params["voided"] = False
    return Response(reports.excel(reports.monthly(db, params, actor)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="monthly-expenses.xlsx"'})


@router.get("/expense-records")
def listing(params: dict = Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    query = service.query_records(params, actor)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.execute(query.offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [service.record_output(*r) for r in rows], "total": total, "page": page, "page_size": page_size,
            "filters": params, "unconfirmed_count": service.unconfirmed_count(db)}


@router.post("/expense-records", status_code=201)
def create(body: RecordCreate, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    row = mutate(db, lambda: service.create_record(db, actor, body))
    return service.detail(db, row.id)


@router.get("/expense-records/{record_id}")
def detail(record_id: int, db: Session = Depends(get_db)):
    return service.detail(db, record_id)


@router.patch("/expense-records/{record_id}")
def edit(record_id: int, body: RecordUpdate, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    mutate(db, lambda: service.edit_record(db, actor, record_id, body))
    return service.detail(db, record_id)


@router.post("/expense-records/{record_id}/void")
def void(record_id: int, body: VersionReason, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    mutate(db, lambda: service.void_record(db, actor, record_id, body))
    return service.detail(db, record_id)


@router.post("/reimbursements/preview")
def preview(body: BatchInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: service.batch_preview(db, body))


@router.post("/reimbursements", status_code=201)
def reimburse(body: BatchInput, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    row = mutate(db, lambda: service.create_batch(db, actor, body))
    return service.batch_detail(db, row)


@router.get("/reimbursements/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    row = db.get(Reimbursement, batch_id)
    if not row:
        raise not_found("报销批次不存在")
    return service.batch_detail(db, row)


@router.post("/reimbursements/{batch_id}/revoke")
def revoke(batch_id: int, body: VersionReason, db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    row = mutate(db, lambda: service.revoke_batch(db, actor, batch_id, body))
    return service.batch_detail(db, row)


async def upload(db, actor, file, *, record_id=None, batch_id=None):
    model, entity_id = (ExpenseRecord, record_id) if record_id else (Reimbursement, batch_id)
    if not db.get(model, entity_id):
        raise not_found()
    from app.config import get_settings
    content = await file.read(get_settings().attachment_max_bytes + 1)
    validate_attachment(file.filename or "file", file.content_type, len(content))
    try:
        stored = get_storage().upload(prefix="expense-records" if record_id else "reimbursements", entity_id=entity_id,
                                      filename=file.filename or "file", content_type=file.content_type, data=content)
    except Exception as exc:
        raise AppError(503, "记录已保存，凭证上传失败，请仅重试上传", "ATTACHMENT_STORAGE_UNAVAILABLE") from exc
    attachment = LedgerAttachment(record_id=record_id, batch_id=batch_id, uploader_user_id=actor.id,
                                  file_name=stored.file_name, object_key=stored.object_key, mime_type=stored.mime_type,
                                  file_size=stored.file_size, sha256=stored.sha256)
    db.add(attachment)
    ids = [record_id] if record_id else [i.record_id for i in db.scalars(select(ReimbursementItem).where(ReimbursementItem.batch_id == batch_id))]
    for rid in ids:
        service.event(db, db.get(ExpenseRecord, rid), actor, "ATTACHMENT_ADDED", new={"file_name": stored.file_name}, batch_id=batch_id)
    db.commit()
    return {"id": attachment.id, "file_name": attachment.file_name}


@router.post("/expense-records/{record_id}/attachments", status_code=201)
async def record_attachment(record_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    return await upload(db, actor, file, record_id=record_id)


@router.post("/reimbursements/{batch_id}/attachments", status_code=201)
async def batch_attachment(batch_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), actor: CurrentUser = Depends(require_admin)):
    return await upload(db, actor, file, batch_id=batch_id)
