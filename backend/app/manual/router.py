import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage
from app.attachments.router import _content_disposition
from app.common.errors import AppError
from app.db.session import get_db
from app.deps import CurrentUser, require_admin
from app.manual import service
from app.manual.schema import load_default_config

logger = logging.getLogger(__name__)
public_router = APIRouter(prefix="/ext/api/v1/public", tags=["manual"])
admin_router = APIRouter(prefix="/ext/api/v1/admin/manual", tags=["manual"])


class SaveBody(BaseModel):
    config: dict
    base_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=200)
    touch_updated_on: bool = True


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


# ---- public ----------------------------------------------------------------

@public_router.get("/manual-config")
def public_manual_config(request: Request, db: Session = Depends(get_db)):
    payload = service.public_payload(db)
    etag = f'W/"manual-{payload["version"]}"'
    headers = {"Cache-Control": "public, max-age=60", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(jsonable_encoder(payload), headers=headers)


@public_router.get("/manual-files/{file_id}/{file_name}")
def public_manual_file(file_id: int, file_name: str, db: Session = Depends(get_db)):
    record = service.get_public_file(db, file_id, file_name)
    try:
        stream = get_storage().open_stream(record.object_key)
    except Exception as exc:
        logger.error("manual file storage error file_id=%s error_type=%s", file_id, type(exc).__name__)
        raise AppError(503, "下载暂不可用，请稍后重试", "MANUAL_FILE_UNAVAILABLE") from exc

    def chunks():
        try:
            yield from stream.stream(1024 * 1024)
        finally:
            stream.close()
            stream.release_conn()

    return StreamingResponse(chunks(), media_type=record.mime_type, headers={
        "Content-Disposition": _content_disposition(record.file_name),
        "Content-Length": str(record.file_size),
        # A file id never changes content, so browsers and proxies may cache it.
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    })


# ---- admin -----------------------------------------------------------------

@admin_router.get("/config")
def admin_get_config(db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    live = service.get_live(db)
    out = _version_out(live, with_config=True)
    out["config"] = service.normalized_config(live.config)
    return {**out, "defaults": load_default_config().dump()}


@admin_router.put("/config")
def admin_save_config(body: SaveBody, db: Session = Depends(get_db), admin: CurrentUser = Depends(require_admin)):
    row = service.save(db, user=admin, raw_config=body.config, base_version=body.base_version,
                       note=body.note, touch_updated_on=body.touch_updated_on)
    return _version_out(row, with_config=True)


@admin_router.get("/versions")
def admin_versions(db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    return [_version_out(row) for row in service.list_versions(db)]


@admin_router.get("/versions/{version}")
def admin_version(version: int, db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    return _version_out(service.get_version(db, version), with_config=True)


@admin_router.post("/versions/{version}/restore")
def admin_restore(version: int, body: RestoreBody, db: Session = Depends(get_db),
                  admin: CurrentUser = Depends(require_admin)):
    row = service.restore(db, user=admin, version=version, base_version=body.base_version)
    return _version_out(row, with_config=True)


@admin_router.get("/sub2api-groups")
def admin_sub2api_groups(_admin: CurrentUser = Depends(require_admin)):
    return service.list_sub2api_groups()


@admin_router.get("/files")
def admin_files(db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    return [service.file_out(record) for record in service.list_files(db)]


@admin_router.post("/files")
async def admin_upload_file(
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    data = await file.read()
    record = service.upload_file(db, user=admin, filename=file.filename or "file", data=data, description=description)
    return service.file_out(record)


@admin_router.delete("/files/{file_id}")
def admin_delete_file(file_id: int, db: Session = Depends(get_db), _admin: CurrentUser = Depends(require_admin)):
    service.delete_file(db, file_id)
    return {"ok": True}
