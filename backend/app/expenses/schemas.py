from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierIn(BaseModel):
    name: str
    supplier_type: str | None = None
    tax_number: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    notes: str | None = None
    enabled: bool = True


class SupplierOut(SupplierIn):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class CostCenterIn(BaseModel):
    code: str
    name: str
    description: str | None = None
    enabled: bool = True


class CostCenterOut(CostCenterIn):
    id: int
    model_config = {"from_attributes": True}


class PaymentAccountIn(BaseModel):
    name: str
    account_type: str
    account_no_masked: str | None = None
    owner_label: str | None = None
    enabled: bool = True


class PaymentAccountOut(PaymentAccountIn):
    id: int
    model_config = {"from_attributes": True}


class ExpenseItemIn(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal
    amount: Decimal | None = None


class ExpenseCreate(BaseModel):
    expense_date: date
    category: str
    supplier_id: int | None = None
    cost_center_id: int | None = None
    currency: str = "CNY"
    amount_tax_included: Decimal | None = None
    amount_tax_excluded: Decimal | None = None
    tax_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    description: str | None = None
    pay_type: str
    payment_method: str | None = None
    payment_account_id: int | None = None
    invoice_required: bool = True
    items: list[ExpenseItemIn] = []


class ExpenseUpdate(ExpenseCreate):
    pass


class InvoiceUpdate(BaseModel):
    invoice_status: str | None = None
    invoice_type: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    seller_name: str | None = None
    seller_tax_no: str | None = None
    buyer_name: str | None = None
    buyer_tax_no: str | None = None
    deductible: bool | None = None
    tax_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    amount_tax_excluded: Decimal | None = None


class PaymentCreate(BaseModel):
    amount: Decimal
    currency: str = "CNY"
    paid_at: datetime | None = None
    payment_account_id: int | None = None
    reference_no: str | None = None
    notes: str | None = None
    mark_paid: bool = True


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1)


class ExpenseItemOut(BaseModel):
    id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    model_config = {"from_attributes": True}


class ExpenseOut(BaseModel):
    id: int
    claim_no: str
    applicant_user_id: int
    expense_date: date
    category: str
    supplier_id: int | None
    cost_center_id: int | None
    currency: str
    amount_tax_included: Decimal
    amount_tax_excluded: Decimal | None
    tax_amount: Decimal | None
    tax_rate: Decimal | None
    description: str | None
    pay_type: str
    payment_method: str | None
    payment_account_id: int | None
    status: str
    invoice_required: bool
    invoice_status: str
    invoice_type: str | None
    invoice_number: str | None
    invoice_date: date | None
    seller_name: str | None
    seller_tax_no: str | None
    buyer_name: str | None
    buyer_tax_no: str | None
    deductible: bool | None
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    paid_at: datetime | None
    paid_by_user_id: int | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ExpenseItemOut] = []
    model_config = {"from_attributes": True}
