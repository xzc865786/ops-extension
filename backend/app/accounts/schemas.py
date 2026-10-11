from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Status = Literal["ACTIVE", "STANDBY", "BANNED", "DISABLED"]
# Plain fields are trimmed per field; secrets are kept byte-for-byte (spaces can be part of a password).
def text(max_length: int, min_length: int = 0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client: text(50, 1)
    login: text(255, 1)
    status: Status = "STANDBY"
    plan: text(50) = ""
    expires_on: date | None = None
    owner: text(100) = ""
    phone: text(50) = ""
    recovery_email: text(255) = ""
    notes: text(10000) = ""
    # On update, omit a secret to keep it unchanged; send null or "" to clear it.
    password: str | None = Field(default=None, max_length=1000)
    secret_notes: str | None = Field(default=None, max_length=10000)


class AccountUpdate(AccountCreate):
    version: int = Field(ge=1)


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
    version: int = Field(ge=1)


class VersionOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


class Reveal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["password", "secret_notes"]
    purpose: Literal["view", "copy"] = "view"
