import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, field_validator
from app.common.enums import EXPENSE_CATEGORY_LABELS


def money_string(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,16}(\.\d{1,2})?", value):
        raise ValueError("金额请使用十进制字符串，最多两位小数")
    amount = Decimal(value)
    if amount <= 0 or amount > Decimal("9999999999999999.99"):
        raise ValueError("金额须大于零且不超过 16 位整数")
    return amount


Money = Annotated[Decimal, BeforeValidator(money_string)]
Key = Annotated[str, Field(min_length=8, max_length=100)]


class RecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    expense_date: date
    category: str = "CLOUD_SERVER"
    payer: str = Field(min_length=1, max_length=100)
    merchant: str = Field(default="", max_length=200)
    currency: Literal["CNY", "USD"] = "CNY"
    amount: Money
    rmb_amount: Money | None = None
    amount_mode: Literal["AUTO", "MANUAL"] = "AUTO"
    quote_id: str | None = Field(None, max_length=36)
    needs_reimbursement: bool = True
    notes: str = Field(default="", max_length=10000)

    @field_validator("category")
    @classmethod
    def category_allowed(cls, v):
        if v not in EXPENSE_CATEGORY_LABELS or v == "STAFF_ADVANCE":
            raise ValueError("请选择用途分类")
        return v


class RecordCreate(RecordInput):
    idempotency_key: Key


class RecordUpdate(RecordInput):
    version: int = Field(ge=1)


class VersionReason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=1)
    version: int = Field(ge=1)


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    records: list[Selection] = Field(min_length=1, max_length=100)
    actual_amount: Money
    reimbursement_date: date
    notes: str = Field(default="", max_length=10000)
    difference_reason: str = Field(default="", max_length=2000)
    idempotency_key: Key


class HistoryConfirm(RecordCreate):
    # Explicit human decision; legacy approval/payment status is never inferred.
    history_settled: bool
    actual_reimbursement: Money | None = None
    reimbursement_date: date | None = None
    difference_reason: str = Field(default="", max_length=2000)
