from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.common.enums import (
    ExpenseCategory,
    ExpenseEventType,
    ExpenseStatus,
    PayType,
)
from app.common.errors import bad_request, not_found
from app.db.models.expense import (
    CostCenter,
    ExpenseAttachment,
    ExpenseClaim,
    ExpenseEvent,
    ExpenseItem,
    ExpensePayment,
    PaymentAccount,
    Supplier,
)
from app.deps import CurrentUser


def generate_claim_no(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"E{today}"
    count = db.scalar(
        select(func.count()).select_from(ExpenseClaim).where(ExpenseClaim.claim_no.like(f"{prefix}%"))
    ) or 0
    return f"{prefix}{count + 1:04d}"


def add_event(db, claim_id, actor_id, event_type, old=None, new=None):
    db.add(
        ExpenseEvent(
            claim_id=claim_id,
            actor_user_id=actor_id,
            event_type=event_type,
            old_value=old,
            new_value=new,
        )
    )


def _sum_items(items) -> Decimal:
    total = Decimal("0")
    for it in items:
        amt = it.amount if it.amount is not None else (Decimal(it.quantity) * Decimal(it.unit_price))
        total += Decimal(amt)
    return total


def create_claim(db: Session, user: CurrentUser, data) -> ExpenseClaim:
    try:
        ExpenseCategory(data.category)
    except ValueError as exc:
        raise bad_request("无效费用分类", "INVALID_CATEGORY") from exc
    try:
        PayType(data.pay_type)
    except ValueError as exc:
        raise bad_request("无效付款类型", "INVALID_PAY_TYPE") from exc

    amount = data.amount_tax_included
    if data.items:
        amount = _sum_items(data.items)
    if amount is None:
        amount = Decimal("0")

    claim = ExpenseClaim(
        claim_no=generate_claim_no(db),
        applicant_user_id=user.id,
        expense_date=data.expense_date,
        category=data.category,
        supplier_id=data.supplier_id,
        cost_center_id=data.cost_center_id,
        currency=(data.currency or "CNY").upper(),
        amount_tax_included=amount,
        amount_tax_excluded=data.amount_tax_excluded,
        tax_amount=data.tax_amount,
        tax_rate=data.tax_rate,
        description=data.description,
        pay_type=data.pay_type,
        payment_method=data.payment_method or data.pay_type,
        payment_account_id=data.payment_account_id,
        status=ExpenseStatus.DRAFT.value,
        invoice_required=data.invoice_required,
        invoice_status="NONE" if data.invoice_required else "NOT_REQUIRED",
    )
    db.add(claim)
    db.flush()
    for it in data.items:
        amt = it.amount if it.amount is not None else Decimal(it.quantity) * Decimal(it.unit_price)
        db.add(
            ExpenseItem(
                claim_id=claim.id,
                description=it.description,
                quantity=it.quantity,
                unit_price=it.unit_price,
                amount=amt,
            )
        )
    add_event(db, claim.id, user.id, ExpenseEventType.CREATED.value, new={"claim_no": claim.claim_no})
    db.commit()
    return load_claim(db, claim.id)


def load_claim(db: Session, claim_id: int) -> ExpenseClaim:
    claim = db.scalar(
        select(ExpenseClaim)
        .where(ExpenseClaim.id == claim_id)
        .options(
            selectinload(ExpenseClaim.items),
            selectinload(ExpenseClaim.attachments),
            selectinload(ExpenseClaim.payments),
            selectinload(ExpenseClaim.events),
        )
    )
    if not claim:
        raise not_found("报账单不存在", "EXPENSE_NOT_FOUND")
    return claim


def update_claim(db: Session, claim: ExpenseClaim, user: CurrentUser, data) -> ExpenseClaim:
    if claim.status not in (ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value):
        raise bad_request("仅草稿或已驳回可编辑", "NOT_EDITABLE")
    try:
        ExpenseCategory(data.category)
        PayType(data.pay_type)
    except ValueError as exc:
        raise bad_request(str(exc), "INVALID") from exc

    amount = data.amount_tax_included
    if data.items:
        amount = _sum_items(data.items)
    claim.expense_date = data.expense_date
    claim.category = data.category
    claim.supplier_id = data.supplier_id
    claim.cost_center_id = data.cost_center_id
    claim.currency = (data.currency or "CNY").upper()
    claim.amount_tax_included = amount or Decimal("0")
    claim.amount_tax_excluded = data.amount_tax_excluded
    claim.tax_amount = data.tax_amount
    claim.tax_rate = data.tax_rate
    claim.description = data.description
    claim.pay_type = data.pay_type
    claim.payment_method = data.payment_method or data.pay_type
    claim.payment_account_id = data.payment_account_id
    claim.invoice_required = data.invoice_required
    # replace items
    claim.items.clear()
    db.flush()
    for it in data.items:
        amt = it.amount if it.amount is not None else Decimal(it.quantity) * Decimal(it.unit_price)
        claim.items.append(
            ExpenseItem(
                description=it.description,
                quantity=it.quantity,
                unit_price=it.unit_price,
                amount=amt,
            )
        )
    if claim.status == ExpenseStatus.REJECTED.value:
        claim.status = ExpenseStatus.DRAFT.value
        claim.rejection_reason = None
    add_event(db, claim.id, user.id, ExpenseEventType.UPDATED.value)
    db.commit()
    return load_claim(db, claim.id)


def submit_claim(db: Session, claim: ExpenseClaim, user: CurrentUser) -> ExpenseClaim:
    if claim.status not in (ExpenseStatus.DRAFT.value, ExpenseStatus.REJECTED.value):
        raise bad_request("当前状态不可提交", "INVALID_STATUS")
    old = claim.status
    claim.status = ExpenseStatus.SUBMITTED.value
    claim.submitted_at = datetime.now(timezone.utc)
    claim.rejection_reason = None
    add_event(db, claim.id, user.id, ExpenseEventType.SUBMITTED.value, old={"status": old}, new={"status": claim.status})
    db.commit()
    return load_claim(db, claim.id)


def approve_claim(db: Session, claim: ExpenseClaim, user: CurrentUser) -> ExpenseClaim:
    # applicant may equal approver (product rule)
    if claim.status != ExpenseStatus.SUBMITTED.value:
        raise bad_request("仅已提交可审批", "INVALID_STATUS")
    claim.status = ExpenseStatus.APPROVED.value
    claim.approved_at = datetime.now(timezone.utc)
    claim.approved_by_user_id = user.id
    add_event(db, claim.id, user.id, ExpenseEventType.APPROVED.value)
    db.commit()
    return load_claim(db, claim.id)


def reject_claim(db: Session, claim: ExpenseClaim, user: CurrentUser, reason: str) -> ExpenseClaim:
    if claim.status != ExpenseStatus.SUBMITTED.value:
        raise bad_request("仅已提交可驳回", "INVALID_STATUS")
    claim.status = ExpenseStatus.REJECTED.value
    claim.rejection_reason = reason
    add_event(db, claim.id, user.id, ExpenseEventType.REJECTED.value, new={"reason": reason})
    db.commit()
    return load_claim(db, claim.id)


def cancel_claim(db: Session, claim: ExpenseClaim, user: CurrentUser) -> ExpenseClaim:
    if claim.status not in (ExpenseStatus.DRAFT.value, ExpenseStatus.SUBMITTED.value):
        raise bad_request("仅草稿/已提交可取消", "INVALID_STATUS")
    claim.status = ExpenseStatus.CANCELLED.value
    add_event(db, claim.id, user.id, ExpenseEventType.CANCELLED.value)
    db.commit()
    return load_claim(db, claim.id)


def add_payment(db: Session, claim: ExpenseClaim, user: CurrentUser, data) -> ExpenseClaim:
    # Serialize payments for one claim on PostgreSQL. Read the total after taking
    # the row lock; the previously loaded relationship may be stale.
    claim = db.scalar(
        select(ExpenseClaim).where(ExpenseClaim.id == claim.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if claim is None:
        raise not_found("报账单不存在", "EXPENSE_NOT_FOUND")
    if claim.status != ExpenseStatus.APPROVED.value:
        raise bad_request("仅已审批未付清可登记付款", "INVALID_STATUS")
    amount = data.amount
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise bad_request("付款金额必须大于零且精确到分", "INVALID_PAYMENT_AMOUNT")
    currency = (data.currency or claim.currency).upper()
    if currency != claim.currency:
        raise bad_request("付款币种与报账单不一致", "PAYMENT_CURRENCY_MISMATCH")
    payments = db.scalars(select(ExpensePayment).where(ExpensePayment.claim_id == claim.id)).all()
    if any(p.currency != claim.currency for p in payments):
        raise bad_request("历史付款币种不一致，请先核对", "PAYMENT_RECONCILIATION_REQUIRED")
    total_paid = sum((p.amount for p in payments), Decimal("0"))
    new_total = total_paid + amount
    if new_total > claim.amount_tax_included:
        raise bad_request("付款金额超过剩余应付", "PAYMENT_EXCEEDS_BALANCE")
    if data.mark_paid is True and new_total < claim.amount_tax_included:
        raise bad_request("未付清时不能标记已付", "PAYMENT_INCOMPLETE")
    paid_at = data.paid_at or datetime.now(timezone.utc)
    pay = ExpensePayment(
        claim_id=claim.id,
        payment_account_id=data.payment_account_id or claim.payment_account_id,
        amount=amount,
        currency=currency,
        paid_at=paid_at,
        reference_no=data.reference_no,
        notes=data.notes,
        created_by_user_id=user.id,
    )
    db.add(pay)
    add_event(db, claim.id, user.id, ExpenseEventType.PAYMENT_ADDED.value, new={"amount": str(amount), "currency": currency})
    if new_total == claim.amount_tax_included:
        claim.status = ExpenseStatus.PAID.value
        claim.paid_at = paid_at
        claim.paid_by_user_id = user.id
        add_event(db, claim.id, user.id, ExpenseEventType.PAID.value)
    db.commit()
    return load_claim(db, claim.id)


def update_invoice(db: Session, claim: ExpenseClaim, user: CurrentUser, data) -> ExpenseClaim:
    for field in (
        "invoice_status",
        "invoice_type",
        "invoice_number",
        "invoice_date",
        "seller_name",
        "seller_tax_no",
        "buyer_name",
        "buyer_tax_no",
        "deductible",
        "tax_amount",
        "tax_rate",
        "amount_tax_excluded",
    ):
        if field in data.model_fields_set:
            val = getattr(data, field)
            if field == "invoice_status" and val is None:
                raise bad_request("发票状态不可清空", "INVALID_INVOICE_STATUS")
            setattr(claim, field, val)
    add_event(db, claim.id, user.id, ExpenseEventType.INVOICE_ADDED.value)
    db.commit()
    return load_claim(db, claim.id)


def list_claims(db: Session, *, status=None, category=None, page=1, page_size=20):
    q = select(ExpenseClaim)
    if status:
        q = q.where(ExpenseClaim.status == status)
    if category:
        q = q.where(ExpenseClaim.category == category)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(
        q.order_by(ExpenseClaim.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total
