from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage
from app.common.enums import EXPENSE_CATEGORY_LABELS, ExpenseAttachmentType, ExpenseCategory, ExpenseEventType
from app.db.models.expense import CostCenter, ExpenseAttachment, PaymentAccount, Supplier
from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.expenses import service
from app.expenses.schemas import (
    CostCenterIn,
    CostCenterOut,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    InvoiceUpdate,
    PaymentAccountIn,
    PaymentAccountOut,
    PaymentCreate,
    RejectBody,
    SupplierIn,
    SupplierOut,
)

router = APIRouter(prefix="/ext/api/v1/admin", tags=["expenses"])


# ---- meta / masters ----

@router.get("/expenses/meta")
def expense_meta(admin: CurrentUser = Depends(require_admin)):
    return {
        "categories": [{"value": c.value, "label": EXPENSE_CATEGORY_LABELS[c]} for c in ExpenseCategory],
        "pay_types": [
            {"value": "COMPANY_DIRECT", "label": "公司直付"},
            {"value": "PERSONAL_ADVANCE", "label": "个人垫付"},
        ],
        "statuses": ["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "PAID", "CANCELLED"],
        "currencies": ["CNY", "USD", "HKD", "EUR", "JPY"],
        "invoice_statuses": ["NONE", "PENDING", "RECEIVED", "NOT_REQUIRED"],
        "invoice_types": ["VAT_SPECIAL", "VAT_NORMAL", "RECEIPT", "OTHER"],
        "account_types": ["COMPANY_BANK", "ALIPAY", "WECHAT", "PERSONAL_BANK", "OTHER"],
    }


@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    rows = db.query(Supplier).order_by(Supplier.id.desc()).all()
    return [SupplierOut.model_validate(r).model_dump() for r in rows]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    row = Supplier(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return SupplierOut.model_validate(row).model_dump()


@router.patch("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int, body: SupplierIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    row = db.get(Supplier, supplier_id)
    if not row:
        from app.common.errors import not_found
        raise not_found()
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return SupplierOut.model_validate(row).model_dump()


@router.get("/cost-centers")
def list_cost_centers(db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    rows = db.query(CostCenter).order_by(CostCenter.code).all()
    return [CostCenterOut.model_validate(r).model_dump() for r in rows]


@router.post("/cost-centers", status_code=201)
def create_cost_center(body: CostCenterIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    row = CostCenter(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return CostCenterOut.model_validate(row).model_dump()


@router.patch("/cost-centers/{cc_id}")
def update_cost_center(
    cc_id: int, body: CostCenterIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    row = db.get(CostCenter, cc_id)
    if not row:
        from app.common.errors import not_found
        raise not_found()
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return CostCenterOut.model_validate(row).model_dump()


@router.get("/payment-accounts")
def list_payment_accounts(db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    rows = db.query(PaymentAccount).order_by(PaymentAccount.id).all()
    return [PaymentAccountOut.model_validate(r).model_dump() for r in rows]


@router.post("/payment-accounts", status_code=201)
def create_payment_account(
    body: PaymentAccountIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    row = PaymentAccount(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return PaymentAccountOut.model_validate(row).model_dump()


@router.patch("/payment-accounts/{account_id}")
def update_payment_account(
    account_id: int, body: PaymentAccountIn, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    row = db.get(PaymentAccount, account_id)
    if not row:
        from app.common.errors import not_found
        raise not_found()
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return PaymentAccountOut.model_validate(row).model_dump()


# ---- claims ----

@router.get("/expenses")
def list_expenses(
    status: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    items, total = service.list_claims(db, status=status, category=category, page=page, page_size=page_size)
    return {
        "items": [ExpenseOut.model_validate(i).model_dump() for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/expenses", status_code=201)
def create_expense(
    body: ExpenseCreate, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    claim = service.create_claim(db, admin, body)
    return ExpenseOut.model_validate(claim).model_dump()


@router.get("/expenses/{claim_id}")
def get_expense(claim_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    claim = service.load_claim(db, claim_id)
    return ExpenseOut.model_validate(claim).model_dump()


@router.patch("/expenses/{claim_id}")
def patch_expense(
    claim_id: int, body: ExpenseUpdate, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    claim = service.load_claim(db, claim_id)
    claim = service.update_claim(db, claim, admin, body)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/submit")
def submit_expense(claim_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    claim = service.load_claim(db, claim_id)
    claim = service.submit_claim(db, claim, admin)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/approve")
def approve_expense(claim_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    claim = service.load_claim(db, claim_id)
    claim = service.approve_claim(db, claim, admin)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/reject")
def reject_expense(
    claim_id: int, body: RejectBody, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    claim = service.load_claim(db, claim_id)
    claim = service.reject_claim(db, claim, admin, body.reason)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/cancel")
def cancel_expense(claim_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    claim = service.load_claim(db, claim_id)
    claim = service.cancel_claim(db, claim, admin)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/payments", status_code=201)
def add_payment(
    claim_id: int, body: PaymentCreate, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    claim = service.load_claim(db, claim_id)
    claim = service.add_payment(db, claim, admin, body)
    return ExpenseOut.model_validate(claim).model_dump()


@router.put("/expenses/{claim_id}/invoice")
def put_invoice(
    claim_id: int, body: InvoiceUpdate, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)
):
    claim = service.load_claim(db, claim_id)
    claim = service.update_invoice(db, claim, admin, body)
    return ExpenseOut.model_validate(claim).model_dump()


@router.post("/expenses/{claim_id}/attachments", status_code=201)
async def upload_expense_attachment(
    claim_id: int,
    file: UploadFile = File(...),
    attachment_type: str = "OTHER",
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    claim = service.load_claim(db, claim_id)
    data = await file.read()
    stored = get_storage().upload(
        prefix="expenses",
        entity_id=claim.id,
        filename=file.filename or "file",
        content_type=file.content_type,
        data=data,
    )
    try:
        atype = ExpenseAttachmentType(attachment_type).value
    except ValueError:
        atype = ExpenseAttachmentType.OTHER.value
    att = ExpenseAttachment(
        claim_id=claim.id,
        uploader_user_id=admin.id,
        attachment_type=atype,
        file_name=stored.file_name,
        object_key=stored.object_key,
        mime_type=stored.mime_type,
        file_size=stored.file_size,
        sha256=stored.sha256,
    )
    db.add(att)
    service.add_event(db, claim.id, admin.id, ExpenseEventType.ATTACHMENT_ADDED.value, new={"file_name": stored.file_name})
    db.commit()
    db.refresh(att)
    return {
        "id": att.id,
        "file_name": att.file_name,
        "mime_type": att.mime_type,
        "file_size": att.file_size,
        "attachment_type": att.attachment_type,
    }


@router.get("/expenses/{claim_id}/events")
def expense_events(claim_id: int, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    claim = service.load_claim(db, claim_id)
    return [
        {
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "event_type": e.event_type,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "created_at": e.created_at,
        }
        for e in claim.events
    ]
