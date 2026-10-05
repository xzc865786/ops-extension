"""Versioned storage for the ticket form configuration (same scheme as the manual configuration)."""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.errors import AppError, bad_request, conflict, not_found
from app.db.models.ticket import Ticket, TicketFormConfigVersion
from app.deps import CurrentUser
from app.tickets.form_schema import TicketFormConfig, load_default_form_config


ATTR_NAMES = {
    "key": "标识", "label": "名称", "description": "一句话说明", "notice": "分类提示", "help": "提示文字",
    "placeholder": "占位文字", "title_template": "标题模板", "attachment_hint": "附件提示", "type": "类型",
    "max_length": "长度上限", "min": "最小值", "max": "最大值", "options": "选项", "value": "选项值",
    "fields": "字段", "categories": "分类", "title_mode": "标题方式", "description_mode": "描述框",
}


def _where(raw: dict, loc: tuple) -> str:
    """Turn a pydantic location such as ('categories', 3, 'fields', 1, 'label') into Chinese."""
    parts: list[str] = []
    node: object = raw
    for index, part in enumerate(loc):
        if isinstance(part, int) and isinstance(node, list) and part < len(node):
            node = node[part]
            name = node.get("label") if isinstance(node, dict) else None
            kind = {"categories": "分类", "fields": "字段", "options": "选项"}.get(str(loc[index - 1]), "")
            if kind:
                parts[-1:] = [f"{kind}“{name}”" if name else f"第 {part + 1} 个{kind}"]
        elif isinstance(part, str):
            parts.append(ATTR_NAMES.get(part, part))
            node = node.get(part) if isinstance(node, dict) else None
    return "的".join(parts)


def _message(error: dict) -> str:
    ctx = error.get("ctx") or {}
    kind = error.get("type", "")
    if kind in ("missing", "string_too_short"):
        return "不能为空"
    if kind == "string_too_long":
        return f"不能超过 {ctx.get('max_length')} 个字"
    if kind == "too_long":
        return f"最多 {ctx.get('max_length')} 项"
    if kind == "too_short":
        return f"至少 {ctx.get('min_length')} 项"
    if kind == "literal_error":
        return "取值无效"
    if kind == "extra_forbidden":
        return "是不支持的配置项"
    if kind.startswith(("int_", "float_")):
        return "须为数字"
    return str(error.get("msg", ""))


def validation_error(exc: ValidationError, raw: dict) -> AppError:
    messages = []
    for error in exc.errors():
        if error.get("type") == "value_error":
            # Our own rules already name the category and field.
            messages.append(str(error.get("msg", "")).removeprefix("Value error, "))
        else:
            where = _where(raw, tuple(error.get("loc", ())))
            messages.append(f"{where}{_message(error)}" if where else _message(error))
    return AppError(422, "；".join(messages[:5]) or "配置格式不正确", "TICKET_FORM_CONFIG_INVALID")


def _latest(db: Session) -> TicketFormConfigVersion | None:
    return db.scalar(select(TicketFormConfigVersion).order_by(TicketFormConfigVersion.version.desc()).limit(1))


def get_live(db: Session) -> TicketFormConfigVersion:
    """Return the live configuration, seeding version 1 from the bundled defaults on first use."""
    row = _latest(db)
    if row:
        return row
    row = TicketFormConfigVersion(version=1, config=load_default_form_config().dump(), note="初始默认配置")
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


def live_config(db: Session) -> tuple[int, TicketFormConfig]:
    row = get_live(db)
    return row.version, TicketFormConfig.model_validate(row.config)


def _check_categories_in_use(db: Session, config: TicketFormConfig) -> None:
    used = set(db.scalars(select(Ticket.category).distinct()))
    missing = sorted(used - {c.key for c in config.categories})
    if missing:
        raise bad_request(f"这些分类已有工单，不能删除，只能停用：{'、'.join(missing)}", "TICKET_CATEGORY_IN_USE")


def _insert_version(db: Session, *, base_version: int, config: TicketFormConfig, note: str | None,
                    user: CurrentUser, restored_from: int | None = None) -> TicketFormConfigVersion:
    live = get_live(db)
    if base_version != live.version:
        raise conflict(f"配置已被其他人更新到版本 {live.version}，请刷新后再保存", "TICKET_FORM_CONFIG_STALE")
    _check_categories_in_use(db, config)
    row = TicketFormConfigVersion(
        version=live.version + 1,
        config=config.dump(),
        note=(note or "").strip()[:200] or None,
        restored_from=restored_from,
        created_by_user_id=user.id,
        created_by_name=user.username_snapshot or user.email_snapshot,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("配置刚被其他人更新，请刷新后再保存", "TICKET_FORM_CONFIG_STALE") from exc
    db.refresh(row)
    return row


def _parse(raw: dict) -> TicketFormConfig:
    try:
        return TicketFormConfig.model_validate(raw)
    except ValidationError as exc:
        raise validation_error(exc, raw if isinstance(raw, dict) else {}) from exc


def save(db: Session, *, user: CurrentUser, raw_config: dict, base_version: int,
         note: str | None) -> TicketFormConfigVersion:
    return _insert_version(db, base_version=base_version, config=_parse(raw_config), note=note, user=user)


def restore(db: Session, *, user: CurrentUser, version: int, base_version: int) -> TicketFormConfigVersion:
    source = get_version(db, version)
    return _insert_version(db, base_version=base_version, config=_parse(source.config),
                           note=f"恢复到版本 {version}", user=user, restored_from=version)


def list_versions(db: Session, limit: int = 50) -> list[TicketFormConfigVersion]:
    get_live(db)
    return list(db.scalars(
        select(TicketFormConfigVersion).order_by(TicketFormConfigVersion.version.desc()).limit(limit)
    ))


def get_version(db: Session, version: int) -> TicketFormConfigVersion:
    row = db.scalar(select(TicketFormConfigVersion).where(TicketFormConfigVersion.version == version))
    if not row:
        raise not_found("版本不存在")
    return row
