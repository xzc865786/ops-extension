from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    # Required or not depends on the category's form config.
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category: str
    form_version: int | None = None  # None: client predates per-category forms
    form_data: dict[str, Any] = Field(default_factory=dict)
    ref_ticket_no: str | None = None
    # Fixed troubleshooting fields sent by pre-form clients.
    request_id: str | None = None
    model_name: str | None = None
    api_endpoint: str | None = None
    occurred_at: datetime | None = None
    error_message: str | None = None


class TicketReply(BaseModel):
    content: str = Field(..., min_length=1)
    is_internal: bool = False


class TicketAdminPatch(BaseModel):
    status: str | None = None
    category: str | None = None
    priority: str | None = None


class TicketMessageOut(BaseModel):
    id: int
    sender_user_id: int
    sender_role: str
    content: str
    is_internal: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketAttachmentOut(BaseModel):
    id: int
    file_name: str
    mime_type: str
    file_size: int
    kind: str = "GENERAL"
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketEventOut(BaseModel):
    id: int
    actor_user_id: int | None
    event_type: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketOrderOut(BaseModel):
    id: int
    purpose: str
    out_trade_no: str
    sub2api_order_id: int | None
    snapshot: dict | None

    model_config = {"from_attributes": True}


class RefundOperationOut(BaseModel):
    id: int
    out_trade_no: str
    amount: Decimal
    deduct_balance: bool
    force: bool
    reason: str
    result: str
    message: str | None
    response_summary: dict | None
    operator_name: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class RefundBody(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    deduct_balance: bool = True
    force: bool = False
    reason: str = Field(default="", max_length=100)


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class ManualRefundBody(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class InvoiceIssueBody(BaseModel):
    invoice_no: str = Field(..., max_length=40)
    issued_on: date
    amount: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    attachment_id: int
    emailed: bool = False


class TicketOut(BaseModel):
    id: int
    ticket_no: str
    creator_user_id: int
    title: str
    description: str
    category: str
    priority: str
    status: str
    claimed_by_user_id: int | None
    claimed_at: datetime | None
    ref_ticket_no: str | None
    request_id: str | None
    model_name: str | None
    api_endpoint: str | None
    occurred_at: datetime | None
    error_message: str | None
    form_version: int | None = None
    form_schema: dict | None = None
    form_data: dict = {}
    closed_by: str | None
    closed_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    messages: list[TicketMessageOut] = []
    attachments: list[TicketAttachmentOut] = []
    events: list[TicketEventOut] = []
    orders: list[TicketOrderOut] = []
    resolution: dict | None = None
    refund_operations: list[RefundOperationOut] = []

    model_config = {"from_attributes": True}


class TicketListItem(BaseModel):
    id: int
    ticket_no: str
    title: str
    category: str
    priority: str
    status: str
    claimed_by_user_id: int | None
    creator_user_id: int
    order_nos: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
