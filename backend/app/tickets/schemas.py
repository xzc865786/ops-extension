from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    category: str
    ref_ticket_no: str | None = None
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
    closed_by: str | None
    closed_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    messages: list[TicketMessageOut] = []
    attachments: list[TicketAttachmentOut] = []
    events: list[TicketEventOut] = []

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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
