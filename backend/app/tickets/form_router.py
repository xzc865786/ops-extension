from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.tickets import form_config
from app.tickets.form_schema import load_default_form_config

# Registered before the ticket router so "/admin/tickets/form-config" is not taken for a ticket id.
router = APIRouter(prefix="/ext/api/v1/admin/tickets/form-config", tags=["tickets"])


class SaveBody(BaseModel):
    config: dict
    base_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=200)


class RestoreBody(BaseModel):
    base_version: int = Field(ge=1)


def _version_out(row, with_config: bool = False) -> dict:
    out = {
        "version": row.version,
        "note": row.note,
        "restored_from": row.restored_from,
        "created_by_name": row.created_by_name,
        "created_at": row.created_at,
    }
    if with_config:
        out["config"] = row.config
    return out


@router.get("")
def get_config(db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    live = form_config.get_live(db)
    return {**_version_out(live, with_config=True), "defaults": load_default_form_config().dump()}


@router.put("")
def save_config(body: SaveBody, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    row = form_config.save(db, user=admin, raw_config=body.config, base_version=body.base_version, note=body.note)
    return _version_out(row, with_config=True)


@router.get("/versions")
def list_versions(db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    return [_version_out(row) for row in form_config.list_versions(db)]


@router.get("/versions/{version}")
def get_version(version: int, db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    return _version_out(form_config.get_version(db, version), with_config=True)


@router.post("/versions/{version}/restore")
def restore(version: int, body: RestoreBody, db: Session = Depends(get_db),
            admin: CurrentUser = Depends(require_admin)):
    row = form_config.restore(db, user=admin, version=version, base_version=body.base_version)
    return _version_out(row, with_config=True)
