import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, update, func, or_, text

from app.common.errors import bad_request, conflict, not_found
from app.common.enums import EXPENSE_CATEGORY_LABELS
from app.db.models.expense import ExpenseClaim, ExpenseAttachment, ExpensePayment
from app.db.models.ledger import ExpenseRecord, RateQuote, Reimbursement, ReimbursementItem, LedgerEvent, LedgerAttachment
from app.ledger import rates

CENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999999999.99")


def dec(value):
    return format(value, ".2f")


def request_hash(body):
    return hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def serialize(row):
    return {c.name: (str(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, (date, datetime)) else v)
            for c in row.__table__.columns for v in [getattr(row, c.name)]}


def event(db, record, actor, kind, old=None, new=None, batch_id=None):
    db.add(LedgerEvent(record_id=record.id, batch_id=batch_id, actor_user_id=actor.id,
                      actor_name=actor.username_snapshot, event_type=kind, old_value=old, new_value=new))


def idempotent_lock(db, namespace, key):
    # Serialize retries across workers before reading their durable unique keys.
    if db.bind.dialect.name == "postgresql":
        lock = int.from_bytes(hashlib.sha256((namespace + key).encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})


def existing_request(db, model, key, digest):
    row = db.scalar(select(model).where(model.idempotency_key == key))
    if row and row.request_hash != digest:
        raise conflict("此重试编号已用于不同内容，请重新操作", "IDEMPOTENCY_CONFLICT")
    return row


def locked_record(db, record_id):
    row = db.scalar(select(ExpenseRecord).where(ExpenseRecord.id == record_id)
                    .with_for_update().execution_options(populate_existing=True))
    if not row:
        raise not_found("支出记录不存在")
    return row


def active_item(db, record_id):
    return db.scalar(select(ReimbursementItem).where(ReimbursementItem.active_record_id == record_id))


def bump(db, row, expected, actor):
    now = datetime.now(timezone.utc)
    result = db.execute(update(ExpenseRecord).where(ExpenseRecord.id == row.id, ExpenseRecord.version == expected)
                        .values(version=expected + 1, updated_by=actor.id, updated_at=now)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise conflict("记录已被其他管理员修改，请刷新后重试", "VERSION_CONFLICT")
    row.version = expected + 1
    row.updated_by = actor.id
    row.updated_at = now


def amounts(db, body, existing=None):
    values = body.model_dump(exclude={"version", "idempotency_key", "history_settled", "actual_reimbursement", "reimbursement_date", "difference_reason"})
    values.update(reference_rate=None, rate_date=None, rate_fetched_at=None, rate_source=None)
    if (existing is not None and body.currency == existing.currency == "USD"
            and body.amount == existing.amount and body.amount_mode == existing.amount_mode
            and body.quote_id == existing.quote_id
            and (body.amount_mode == "AUTO" or body.rmb_amount == existing.rmb_amount)):
        # Non-monetary edits retain the complete saved valuation, without recalculation.
        for key in ("rmb_amount", "reference_rate", "rate_date", "rate_fetched_at", "rate_source"):
            values[key] = getattr(existing, key)
        return values
    if body.currency == "CNY":
        values.update(rmb_amount=body.amount, amount_mode="AUTO", quote_id=None)
    else:
        quote = db.get(RateQuote, body.quote_id) if body.quote_id else None
        if body.quote_id and not quote:
            raise bad_request("参考汇率编号无效，请重新获取", "INVALID_QUOTE")
        if quote:
            values.update(reference_rate=quote.rate, rate_date=quote.effective_date,
                          rate_fetched_at=quote.fetched_at, rate_source=quote.source)
        if body.amount_mode == "AUTO":
            if not quote:
                raise bad_request("自动换算须先获取参考汇率，也可手填人民币金额", "QUOTE_REQUIRED")
            values["rmb_amount"] = (body.amount * quote.rate).quantize(CENT, rounding=ROUND_HALF_UP)
        else:
            if body.rmb_amount is None:
                raise bad_request("请填写人民币金额", "RMB_REQUIRED")
            values["rmb_amount"] = body.rmb_amount
            if not quote:
                values["rate_source"] = "人工填写"
    if not Decimal(0) < values["rmb_amount"] <= MAX_MONEY:
        raise bad_request("折合人民币金额超出可记账范围", "AMOUNT_RANGE")
    return values


def create_record(db, actor, body, *, legacy_claim_id=None, commit=True, digest=None):
    digest = digest or request_hash(body)
    idempotent_lock(db, "record:", body.idempotency_key)
    existing = existing_request(db, ExpenseRecord, body.idempotency_key, digest)
    if existing:
        if existing.legacy_claim_id != legacy_claim_id:
            raise conflict("重试编号与历史单据不匹配", "IDEMPOTENCY_CONFLICT")
        return existing
    row = ExpenseRecord(**amounts(db, body), created_by=actor.id, updated_by=actor.id,
                        version=1, active=True, legacy_claim_id=legacy_claim_id,
                        idempotency_key=body.idempotency_key, request_hash=digest)
    db.add(row)
    db.flush()
    event(db, row, actor, "HISTORY_CONFIRMED" if legacy_claim_id else "CREATED", new=serialize(row))
    if commit:
        db.commit()
    return row


def edit_record(db, actor, record_id, body):
    row = locked_record(db, record_id)
    old = serialize(row)
    if not row.active:
        raise conflict("作废记录不可编辑")
    values = amounts(db, body, existing=row)
    core = {"amount", "currency", "rmb_amount", "payer", "expense_date", "needs_reimbursement", "amount_mode", "quote_id"}
    if active_item(db, row.id) and any(getattr(row, k) != values[k] for k in core):
        raise conflict("请先撤销所属报销批次，再修改金额、付款人或支出日期", "REIMBURSED_LOCKED")
    bump(db, row, body.version, actor)
    for k, v in values.items():
        setattr(row, k, v)
    event(db, row, actor, "UPDATED", old=old, new=serialize(row))
    db.commit()
    return row


def void_record(db, actor, record_id, body):
    row = locked_record(db, record_id)
    if not row.active or active_item(db, row.id):
        raise conflict("已报销记录须先撤销报销；作废记录不能重复作废", "RECORD_NOT_VOIDABLE")
    old = serialize(row)
    bump(db, row, body.version, actor)
    row.active = False
    event(db, row, actor, "VOIDED", old=old, new={**serialize(row), "reason": body.reason})
    db.commit()
    return row


def allocate(rows, actual):
    """Integer cents and largest remainder, deterministic tie break by record ID."""
    total = sum(int(r.rmb_amount * 100) for r in rows)
    cents = int(actual * 100)
    quotients = [divmod(cents * int(r.rmb_amount * 100), total) for r in rows]
    shares = [q[0] for q in quotients]
    order = sorted(range(len(rows)), key=lambda i: (-quotients[i][1], rows[i].id))
    for i in order[:cents - sum(shares)]:
        shares[i] += 1
    return [Decimal(v) / 100 for v in shares]


def prepare_batch(db, body):
    ids = [s.id for s in body.records]
    if len(set(ids)) != len(ids):
        raise bad_request("不能重复选择同一支出", "DUPLICATE_RECORD")
    rows = db.scalars(select(ExpenseRecord).where(ExpenseRecord.id.in_(ids)).order_by(ExpenseRecord.id)
                       .with_for_update().execution_options(populate_existing=True)).all()
    if len(rows) != len(ids):
        raise not_found("所选支出不存在")
    versions = {s.id: s.version for s in body.records}
    for row in rows:
        if row.version != versions[row.id]:
            raise conflict("所选支出已变化，请刷新后重试", "VERSION_CONFLICT")
        if not row.active or not row.needs_reimbursement or active_item(db, row.id):
            raise conflict("仅有效的待报销支出可登记报销", "NOT_PENDING")
    if len({r.payer for r in rows}) != 1:
        raise bad_request("所选支出的付款人必须精确相同", "PAYER_MISMATCH")
    expected = sum((r.rmb_amount for r in rows), Decimal(0))
    if body.actual_amount != expected and not body.difference_reason:
        raise bad_request("实报金额与应报销额不同，请填写差额说明；确认后整批结清", "DIFFERENCE_REASON_REQUIRED")
    shares = allocate(rows, body.actual_amount)
    return rows, shares


def batch_preview(db, body):
    rows, shares = prepare_batch(db, body)
    return [{"id": r.id, "title": r.title, "expected_amount": dec(r.rmb_amount),
             "actual_amount": dec(a), "difference": dec(a-r.rmb_amount)} for r, a in zip(rows, shares)]


def create_batch(db, actor, body, *, commit=True):
    digest = request_hash(body)
    idempotent_lock(db, "batch:", body.idempotency_key)
    existing = existing_request(db, Reimbursement, body.idempotency_key, digest)
    if existing:
        return existing
    rows, shares = prepare_batch(db, body)
    batch = Reimbursement(payer=rows[0].payer, actual_amount=body.actual_amount,
                          reimbursement_date=body.reimbursement_date, notes=body.notes,
                          difference_reason=body.difference_reason, created_by=actor.id,
                          idempotency_key=body.idempotency_key, request_hash=digest, version=1, active=True)
    db.add(batch)
    db.flush()
    for r, a in zip(rows, shares):
        old = {"status": "PENDING", "version": r.version}
        bump(db, r, r.version, actor)
        item = ReimbursementItem(record_id=r.id, active_record_id=r.id, batch_id=batch.id,
                                 expected_amount=r.rmb_amount, actual_amount=a, difference=a-r.rmb_amount)
        db.add(item)
        event(db, r, actor, "REIMBURSED", old=old,
              new={"status": "REIMBURSED", "actual_amount": dec(a), "difference": dec(a-r.rmb_amount), "version": r.version}, batch_id=batch.id)
    if commit:
        db.commit()
    else:
        db.flush()
    return batch


def revoke_batch(db, actor, batch_id, body):
    # Same record-first lock order as create/edit/void. Batch membership is immutable.
    items = db.scalars(select(ReimbursementItem).where(ReimbursementItem.batch_id == batch_id).order_by(ReimbursementItem.record_id)).all()
    rows = [locked_record(db, item.record_id) for item in items]
    batch = db.scalar(select(Reimbursement).where(Reimbursement.id == batch_id).with_for_update().execution_options(populate_existing=True))
    if not batch:
        raise not_found("报销批次不存在")
    if batch.version != body.version or not batch.active:
        raise conflict("报销批次已变化或已撤销，请刷新", "VERSION_CONFLICT")
    batch.active = False
    batch.version += 1
    batch.revoked_by = actor.id
    batch.revoke_reason = body.reason
    batch.revoked_at = datetime.now(timezone.utc)
    for item, row in zip(items, rows):
        item.active_record_id = None
        bump(db, row, row.version, actor)
        event(db, row, actor, "REIMBURSEMENT_REVOKED", old={"status": "REIMBURSED"},
              new={"status": "PENDING", "reason": body.reason, "version": row.version}, batch_id=batch.id)
    db.commit()
    return batch


def attachments(db, *, record_id=None, batch_id=None):
    predicate = LedgerAttachment.record_id == record_id if record_id is not None else LedgerAttachment.batch_id == batch_id
    return [{"id": a.id, "file_name": a.file_name, "file_size": a.file_size,
             "source": "expense-record" if a.record_id else "reimbursement"}
            for a in db.scalars(select(LedgerAttachment).where(predicate).order_by(LedgerAttachment.id))]


def batch_detail(db, batch):
    return {**serialize(batch), "attachments": attachments(db, batch_id=batch.id),
            "items": [serialize(i) for i in db.scalars(select(ReimbursementItem).where(ReimbursementItem.batch_id == batch.id).order_by(ReimbursementItem.record_id))]}


def query_records(filters, actor=None):
    q = select(ExpenseRecord, ReimbursementItem, Reimbursement).outerjoin(
        ReimbursementItem, ReimbursementItem.active_record_id == ExpenseRecord.id
    ).outerjoin(Reimbursement, Reimbursement.id == ReimbursementItem.batch_id)
    month = filters.get("month")
    if month:
        try:
            start = date.fromisoformat(month + "-01")
            end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        except ValueError:
            raise bad_request("月份无效", "INVALID_MONTH")
        q = q.where(ExpenseRecord.expense_date >= start, ExpenseRecord.expense_date < end)
    q = q.where(ExpenseRecord.active == (not filters.get("voided", False)))
    for key in ("payer", "category"):
        if filters.get(key):
            q = q.where(getattr(ExpenseRecord, key) == filters[key].strip())
    status = filters.get("status")
    if status == "PENDING":
        q = q.where(ExpenseRecord.needs_reimbursement.is_(True), ReimbursementItem.id.is_(None))
    elif status == "REIMBURSED":
        q = q.where(ReimbursementItem.id.is_not(None))
    elif status == "NOT_REQUIRED":
        q = q.where(ExpenseRecord.needs_reimbursement.is_(False))
    if filters.get("mine"):
        q = q.where(ExpenseRecord.created_by == actor.id)
    if filters.get("keyword"):
        # Escape LIKE metacharacters; keyword means literal substring.
        keyword = filters["keyword"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        q = q.where(or_(*(getattr(ExpenseRecord, k).ilike("%"+keyword+"%", escape="\\") for k in ("title", "merchant", "notes", "payer"))))
    return q.order_by(ExpenseRecord.expense_date.desc(), ExpenseRecord.id.desc())


def record_output(row, item=None, batch=None):
    result = serialize(row)
    # Keep API amounts as decimal strings, including whole-number values.
    result.update(amount=dec(row.amount), rmb_amount=dec(row.rmb_amount),
                  category_label=EXPENSE_CATEGORY_LABELS.get(row.category, row.category),
                  status="VOIDED" if not row.active else "NOT_REQUIRED" if not row.needs_reimbursement else "REIMBURSED" if item else "PENDING",
                  actual_reimbursement=dec(item.actual_amount) if item else None,
                  difference=dec(item.difference) if item else None,
                  reimbursement_date=batch.reimbursement_date.isoformat() if batch else None,
                  batch_id=batch.id if batch else None)
    result.pop("request_hash", None)
    result.pop("idempotency_key", None)
    return result


def unconfirmed_count(db):
    return db.scalar(select(func.count()).select_from(ExpenseClaim).where(
        ~select(ExpenseRecord.id).where(ExpenseRecord.legacy_claim_id == ExpenseClaim.id).exists()))


def detail(db, record_id):
    row = db.get(ExpenseRecord, record_id)
    if not row:
        raise not_found("支出记录不存在")
    item = active_item(db, row.id)
    batch = db.get(Reimbursement, item.batch_id) if item else None
    result = record_output(row, item, batch)
    result["attachments"] = attachments(db, record_id=row.id)
    if row.legacy_claim_id:
        result["attachments"] += [{"id": a.id, "file_name": a.file_name, "file_size": a.file_size, "source": "expense"}
                                  for a in db.scalars(select(ExpenseAttachment).where(ExpenseAttachment.claim_id == row.legacy_claim_id))]
    result["reimbursements"] = [batch_detail(db, b) for b in db.scalars(select(Reimbursement).join(ReimbursementItem, ReimbursementItem.batch_id == Reimbursement.id)
                                                                      .where(ReimbursementItem.record_id == row.id).order_by(Reimbursement.id))]
    result["events"] = [serialize(e) for e in db.scalars(select(LedgerEvent).where(LedgerEvent.record_id == row.id).order_by(LedgerEvent.id))]
    return result


def history_inventory(db):
    records = {r.legacy_claim_id: r.id for r in db.scalars(select(ExpenseRecord).where(ExpenseRecord.legacy_claim_id.is_not(None)))}
    result = []
    for claim in db.scalars(select(ExpenseClaim).order_by(ExpenseClaim.id.desc())):
        payments = db.scalars(select(ExpensePayment).where(ExpensePayment.claim_id == claim.id)).all()
        paid = sum((p.amount for p in payments if p.currency == claim.currency), Decimal(0))
        anomalies = []
        if claim.currency not in ("CNY", "USD"):
            anomalies.append("其他历史币种")
        if claim.amount_tax_included <= 0:
            anomalies.append("零或负金额")
        if claim.status == "CANCELLED":
            anomalies.append("原单已取消")
        if any(p.currency != claim.currency or p.amount <= 0 for p in payments):
            anomalies.append("跨币种或非正付款")
        if paid and paid != claim.amount_tax_included:
            anomalies.append("部分或超额付款")
        if claim.status == "PAID" and paid != claim.amount_tax_included:
            anomalies.append("已付状态与流水不一致")
        result.append({"id": claim.id, "claim_no": claim.claim_no, "expense_date": claim.expense_date.isoformat(),
                       "status": claim.status, "currency": claim.currency, "amount": dec(claim.amount_tax_included),
                       "description": claim.description, "category": claim.category,
                       "payment_count": len(payments), "paid_total": dec(paid), "anomalies": anomalies,
                       "attachment_count": db.scalar(select(func.count()).select_from(ExpenseAttachment).where(ExpenseAttachment.claim_id == claim.id)),
                       "record_id": records.get(claim.id)})
    return {"items": result, "unconfirmed_count": sum(r["record_id"] is None for r in result), "read_only": True}


def confirm_history(db, actor, claim_id, body):
    from app.ledger.schemas import BatchInput
    # Lock the original only for confirming its unique linkage; never update it.
    claim = db.scalar(select(ExpenseClaim).where(ExpenseClaim.id == claim_id).with_for_update())
    if not claim:
        raise not_found("历史单据不存在")
    existing = db.scalar(select(ExpenseRecord).where(ExpenseRecord.legacy_claim_id == claim_id))
    if existing:
        if existing.request_hash != request_hash(body):
            raise conflict("原单已确认迁入，请查看关联记录", "HISTORY_ALREADY_CONFIRMED")
        return existing
    if body.currency == "USD" and (body.amount_mode != "MANUAL" or body.quote_id):
        raise bad_request("历史美元账目须人工确认人民币金额，不自动采用今日汇率", "HISTORY_MANUAL_REQUIRED")
    if body.history_settled and (not body.needs_reimbursement or body.actual_reimbursement is None or body.reimbursement_date is None):
        raise bad_request("历史已报销须确认报销金额及有依据的日期", "HISTORY_EVIDENCE_REQUIRED")
    if not body.history_settled and (body.actual_reimbursement is not None or body.reimbursement_date is not None):
        raise bad_request("未确认报销时不能附带报销金额或日期")
    row = create_record(db, actor, body, legacy_claim_id=claim_id, commit=False)
    if body.history_settled:
        create_batch(db, actor, BatchInput(records=[{"id": row.id, "version": row.version}],
            actual_amount=dec(body.actual_reimbursement), reimbursement_date=body.reimbursement_date,
            notes="历史报销人工确认", difference_reason=body.difference_reason,
            idempotency_key="history:" + hashlib.sha256(body.idempotency_key.encode()).hexdigest()), commit=False)
    db.commit()
    return row
