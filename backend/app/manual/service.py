from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.attachments.minio_client import get_storage, safe_filename
from app.common.errors import AppError, bad_request, conflict, not_found
from app.config import get_settings
from app.db.models.manual import ManualConfigVersion, ManualFile
from app.deps import CurrentUser
from app.manual.schema import MODEL_PATTERN_RE, Groups, ManualConfig, load_default_config
from app.orders.sub2api import Sub2APIError, Sub2APIUnavailable, admin_reason, get_admin_client

# The manual is read in China; "today" for the update date follows Beijing time.
CHINA_TZ = timezone(timedelta(hours=8))

MANUAL_FILE_TYPES = {
    ".msi": "application/x-msi",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".dmg": "application/x-apple-diskimage",
    ".pkg": "application/octet-stream",
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def validation_error(exc: ValidationError) -> AppError:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__")
        message = str(error.get("msg", "")).removeprefix("Value error, ")
        messages.append(f"{location}：{message}" if location else message)
    return AppError(422, "；".join(messages[:5]) or "配置格式不正确", "MANUAL_CONFIG_INVALID")


def _user_name(user: CurrentUser) -> str | None:
    return user.username_snapshot or user.email_snapshot


def _latest(db: Session) -> ManualConfigVersion | None:
    return db.scalar(select(ManualConfigVersion).order_by(ManualConfigVersion.version.desc()).limit(1))


def get_live(db: Session) -> ManualConfigVersion:
    """Return the live configuration, seeding version 1 from the bundled defaults on first use."""
    row = _latest(db)
    if row:
        return row
    row = ManualConfigVersion(version=1, config=load_default_config().dump(), note="初始默认配置")
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = _latest(db)
        if not row:
            raise
    db.refresh(row)
    return row


def _check_files(db: Session, config: ManualConfig) -> None:
    for file_id in config.referenced_file_ids():
        record = db.get(ManualFile, file_id)
        if not record or record.deleted:
            raise bad_request(f"引用的下载文件（编号 {file_id}）不存在或已删除", "MANUAL_FILE_MISSING")


def _insert_version(db: Session, *, base_version: int, config: ManualConfig, note: str | None,
                    user: CurrentUser, restored_from: int | None = None) -> ManualConfigVersion:
    live = get_live(db)
    if base_version != live.version:
        raise conflict(f"配置已被其他人更新到版本 {live.version}，请刷新后再保存", "MANUAL_CONFIG_STALE")
    _check_files(db, config)
    row = ManualConfigVersion(
        version=live.version + 1,
        config=config.dump(),
        note=(note or "").strip()[:200] or None,
        restored_from=restored_from,
        created_by_user_id=user.id,
        created_by_name=_user_name(user),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("配置刚被其他人更新，请刷新后再保存", "MANUAL_CONFIG_STALE") from exc
    db.refresh(row)
    return row


def save(db: Session, *, user: CurrentUser, raw_config: dict, base_version: int, note: str | None,
         touch_updated_on: bool) -> ManualConfigVersion:
    if touch_updated_on and isinstance(raw_config, dict):
        raw_config = {**raw_config, "updated_on": datetime.now(CHINA_TZ).date().isoformat()}
    try:
        config = ManualConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise validation_error(exc) from exc
    return _insert_version(db, base_version=base_version, config=config, note=note, user=user)


def restore(db: Session, *, user: CurrentUser, version: int, base_version: int) -> ManualConfigVersion:
    source = db.scalar(select(ManualConfigVersion).where(ManualConfigVersion.version == version))
    if not source:
        raise not_found("版本不存在")
    try:
        config = ManualConfig.model_validate(source.config)
    except ValidationError as exc:
        raise validation_error(exc) from exc
    return _insert_version(db, base_version=base_version, config=config, note=f"恢复到版本 {version}",
                           user=user, restored_from=version)


def list_versions(db: Session, limit: int = 50) -> list[ManualConfigVersion]:
    get_live(db)
    return list(db.scalars(select(ManualConfigVersion).order_by(ManualConfigVersion.version.desc()).limit(limit)))


def get_version(db: Session, version: int) -> ManualConfigVersion:
    row = db.scalar(select(ManualConfigVersion).where(ManualConfigVersion.version == version))
    if not row:
        raise not_found("版本不存在")
    return row


# ---- files -----------------------------------------------------------------

def file_download_path(record: ManualFile) -> str:
    return f"/ext/api/v1/public/manual-files/{record.id}/{quote(record.file_name, safe='')}"


def file_out(record: ManualFile) -> dict:
    return {
        "id": record.id,
        "file_name": record.file_name,
        "mime_type": record.mime_type,
        "file_size": record.file_size,
        "sha256": record.sha256,
        "description": record.description,
        "uploaded_by_name": record.uploaded_by_name,
        "created_at": record.created_at,
        "download_path": file_download_path(record),
    }


def upload_file(db: Session, *, user: CurrentUser, filename: str, data: bytes, description: str | None) -> ManualFile:
    settings = get_settings()
    if not data:
        raise bad_request("空文件", "EMPTY_FILE")
    if len(data) > settings.manual_file_max_bytes:
        raise bad_request(f"文件超过 {settings.manual_file_max_bytes // (1024 * 1024)}MB 限制", "FILE_TOO_LARGE")
    name = safe_filename(filename)
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    mime = MANUAL_FILE_TYPES.get(ext)
    if not mime:
        raise bad_request("不支持的文件类型（支持安装包、压缩包、PDF 和图片）", "INVALID_FILE_TYPE")
    key = f"manual/{uuid.uuid4().hex}/{name}"
    get_storage().put_bytes(key=key, data=data, content_type=mime)
    record = ManualFile(
        file_name=name,
        mime_type=mime,
        file_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        object_key=key,
        description=(description or "").strip()[:200] or None,
        uploaded_by_user_id=user.id,
        uploaded_by_name=_user_name(user),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_files(db: Session) -> list[ManualFile]:
    return list(db.scalars(select(ManualFile).where(ManualFile.deleted.is_(False)).order_by(ManualFile.id.desc())))


def delete_file(db: Session, file_id: int) -> None:
    record = db.get(ManualFile, file_id)
    if not record or record.deleted:
        raise not_found("文件不存在")
    live = ManualConfig.model_validate(get_live(db).config)
    if file_id in live.referenced_file_ids():
        raise conflict("当前配置正在使用这个文件，请先改用其他下载来源再删除", "MANUAL_FILE_IN_USE")
    # Soft delete keeps old versions explainable; restoring one that uses this file is then refused.
    record.deleted = True
    db.commit()


def get_public_file(db: Session, file_id: int, file_name: str) -> ManualFile:
    record = db.get(ManualFile, file_id)
    if not record or record.deleted or record.file_name != file_name:
        raise not_found("文件不存在")
    return record


# ---- Sub2API groups --------------------------------------------------------

def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _sub2api_group(raw: dict) -> dict | None:
    """Only the fields the group page can use; profit control, routing and accounts never leave here."""
    group_id, name = raw.get("id"), str(raw.get("name") or "").strip()
    if not isinstance(group_id, int) or group_id <= 0 or not name:
        return None
    allowlist = raw.get("model_allowlist") or {}
    models = []
    if isinstance(allowlist, dict) and allowlist.get("enabled"):
        models = [m for m in allowlist.get("models") or [] if isinstance(m, str) and MODEL_PATTERN_RE.match(m)][:30]
    peak = None
    if raw.get("peak_rate_enabled") and _number(raw.get("peak_rate_multiplier")) is not None:
        peak = {"start": str(raw.get("peak_start") or "")[:5], "end": str(raw.get("peak_end") or "")[:5],
                "multiplier": _number(raw.get("peak_rate_multiplier"))}
    return {
        "id": group_id,
        "name": name[:64],
        "description": str(raw.get("description") or "").strip()[:200],
        "platform": str(raw.get("platform") or "")[:32],
        "status": str(raw.get("status") or "")[:16],
        "rate_multiplier": _number(raw.get("rate_multiplier")),
        "is_exclusive": bool(raw.get("is_exclusive")),
        "subscription_type": str(raw.get("subscription_type") or "")[:32],
        "allow_messages_dispatch": bool(raw.get("allow_messages_dispatch")),
        "claude_code_only": bool(raw.get("claude_code_only")),
        "peak": peak,
        "models": models,
    }


def list_sub2api_groups() -> list[dict]:
    client = get_admin_client()
    if not client:
        raise AppError(503, "Ops 未配置 SUB2API_ADMIN_API_KEY，无法从 Sub2API 读取分组", "SUB2API_NOT_CONFIGURED")
    try:
        raw_groups = client.list_groups()
    except (Sub2APIError, Sub2APIUnavailable) as exc:
        raise AppError(502, admin_reason(exc), "SUB2API_GROUPS_UNAVAILABLE") from exc
    return [group for group in map(_sub2api_group, raw_groups) if group]


# ---- public payload --------------------------------------------------------

def normalized_config(config: dict) -> dict:
    """The stored config with sections added since it was saved filled in with their defaults."""
    try:
        return ManualConfig.model_validate(config).dump()
    except ValidationError:
        return dict(config)


def public_payload(db: Session) -> dict:
    live = get_live(db)
    config = normalized_config(live.config)
    try:
        config["groups"] = Groups.model_validate(config.get("groups") or {}).public()
    except ValidationError:
        config["groups"] = load_default_config().groups.public()
    windows = dict(config["ccswitch"]["windows"])
    if windows["source"] == "file" and windows.get("file_id"):
        record = db.get(ManualFile, windows["file_id"])
        if record and not record.deleted:
            windows.update(download_url=file_download_path(record), file_name=record.file_name,
                           file_size=record.file_size, sha256=record.sha256)
        else:
            # Never point the manual at a missing file; fall back to the bundled installer.
            default_windows = load_default_config().ccswitch.windows
            windows.update(source="url", file_id=None, url=default_windows.url, download_url=default_windows.url)
    else:
        windows["download_url"] = windows["url"]
    config["ccswitch"] = {**config["ccswitch"], "windows": windows}
    return {"version": live.version, "updated_at": live.created_at, "config": config}

