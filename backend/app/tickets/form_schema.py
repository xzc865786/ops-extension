"""Ticket form configuration: per-category fields, edited by admins and versioned.

Every text in the configuration is shown to users as plain text, never as HTML. Business behaviour
(order checks, refunds, invoices) hangs off a category's ``kind``; those kinds belong to fixed
built-in categories and require a few locked "system" fields that the later phases rely on.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_FORM_CONFIG_PATH = Path(__file__).with_name("default_form_config.json")

CATEGORY_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
OPTION_VALUE_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
ORDER_NO_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,180}\.[A-Za-z]{2,24}$")
TEMPLATE_VAR_RE = re.compile(r"\{([a-z][a-z0-9_]{0,39})\}")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
TEXTAREA_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

FieldType = Literal[
    "text", "textarea", "number", "money", "select", "radio", "confirm",
    "date", "datetime", "email", "order_no", "order_no_list",
]
Kind = Literal["general", "refund", "invoice", "payment"]

MAX_ORDER_NOS = 10
MONEY_MAX = Decimal("1000000")
TEXT_LIMITS = {"text": (200, 500), "textarea": (2000, 5000)}  # (default, ceiling)

# Built-in categories are referenced by existing tickets and by code; they can be disabled but not removed.
BUILTIN_KINDS: dict[str, str] = {
    "API_ERROR": "general",
    "AUTH_ERROR": "general",
    "BILLING_ERROR": "general",
    "RECHARGE_PAYMENT": "payment",
    "INVOICE": "invoice",
    "REFUND": "refund",
    "MODEL_AVAILABILITY": "general",
    "RATE_LIMIT": "general",
    "ACCOUNT": "general",
    "FEATURE_REQUEST": "general",
    "OTHER": "general",
}

# Fields a kind depends on. Admins may reword them but not remove them or change how they validate.
SYSTEM_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "refund": {
        "order_no": {"type": "order_no"},
        "policy_ack": {"type": "confirm"},
    },
    "invoice": {
        "order_nos": {"type": "order_no_list"},
        "title_type": {"type": "radio", "options": ["PERSONAL", "COMPANY"]},
        "title": {"type": "text"},
        "tax_id": {"type": "text", "show_if": {"field": "title_type", "equals": "COMPANY"}},
        "email": {"type": "email"},
    },
    "payment": {
        "order_no": {"type": "order_no"},
    },
}


def _plain(value: str, what: str, *, multiline: bool = False) -> str:
    value = value.strip()
    if (TEXTAREA_CONTROL_RE if multiline else CONTROL_CHARS_RE).search(value):
        raise ValueError(f"{what}不能包含控制字符")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Option(Strict):
    value: str
    label: str = Field(min_length=1, max_length=60)

    @field_validator("value")
    @classmethod
    def check_value(cls, value: str) -> str:
        value = value.strip()
        if not OPTION_VALUE_RE.match(value):
            raise ValueError(f"选项值“{value}”只能包含字母、数字和下划线")
        return value

    @field_validator("label")
    @classmethod
    def check_label(cls, value: str) -> str:
        return _plain(value, "选项名称")


class ShowIf(Strict):
    field: str
    equals: str | bool | None = None
    in_: list[str] | None = Field(default=None, alias="in")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def one_condition(self) -> "ShowIf":
        if (self.equals is None) == (self.in_ is None):
            raise ValueError("显示条件需要且只能填写“等于”或“属于”其中一种")
        if self.in_ is not None and not self.in_:
            raise ValueError("显示条件“属于”至少要有一个值")
        return self

    def matches(self, value: Any) -> bool:
        if self.equals is not None:
            return value == self.equals
        return value in (self.in_ or [])


class FormField(Strict):
    key: str
    label: str = Field(min_length=1, max_length=60)
    type: FieldType
    required: bool = False
    system: bool = False  # recomputed on validation; clients cannot set it
    help: str = Field(default="", max_length=200)
    placeholder: str = Field(default="", max_length=100)
    max_length: int | None = None
    min: float | None = None
    max: float | None = None
    options: list[Option] = Field(default_factory=list, max_length=30)
    show_if: ShowIf | None = None

    @field_validator("key")
    @classmethod
    def check_key(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_KEY_RE.match(value):
            raise ValueError(f"字段标识“{value}”须以小写字母开头，只能包含小写字母、数字和下划线")
        return value

    @field_validator("label", "help", "placeholder")
    @classmethod
    def check_text(cls, value: str, info) -> str:
        return _plain(value, {"label": "字段名称", "help": "提示文字", "placeholder": "占位文字"}[info.field_name])

    @model_validator(mode="after")
    def check_shape(self) -> "FormField":
        if self.type in ("select", "radio"):
            if not self.options:
                raise ValueError(f"字段“{self.label}”是选择题，至少要有一个选项")
            values = [o.value for o in self.options]
            if len(set(values)) != len(values):
                raise ValueError(f"字段“{self.label}”的选项值重复")
        elif self.options:
            raise ValueError(f"只有下拉和单选字段可以设置选项（字段“{self.label}”）")
        if self.type in TEXT_LIMITS:
            default, ceiling = TEXT_LIMITS[self.type]
            if self.max_length is None:
                self.max_length = default
            if not 1 <= self.max_length <= ceiling:
                raise ValueError(f"字段“{self.label}”的长度上限须在 1 到 {ceiling} 之间")
        else:
            self.max_length = None
        if self.type in ("number", "money"):
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError(f"字段“{self.label}”的最小值不能大于最大值")
        else:
            self.min = self.max = None
        return self


class Category(Strict):
    key: str
    label: str = Field(min_length=1, max_length=30)
    description: str = Field(default="", max_length=100)
    kind: Kind = "general"
    enabled: bool = True
    notice: str = Field(default="", max_length=500)
    title_mode: Literal["required", "optional", "auto"] = "required"
    title_template: str = Field(default="", max_length=100)
    description_mode: Literal["required", "optional", "hidden"] = "required"
    require_attachment: bool = False
    attachment_hint: str = Field(default="", max_length=200)
    fields: list[FormField] = Field(default_factory=list, max_length=30)

    @field_validator("key")
    @classmethod
    def check_key(cls, value: str) -> str:
        value = value.strip()
        if not CATEGORY_KEY_RE.match(value):
            raise ValueError(f"分类标识“{value}”须以大写字母开头，只能包含大写字母、数字和下划线（2 到 40 位）")
        return value

    @field_validator("label", "description", "title_template", "attachment_hint")
    @classmethod
    def check_text(cls, value: str, info) -> str:
        names = {"label": "分类名称", "description": "分类说明", "title_template": "标题模板",
                 "attachment_hint": "附件提示"}
        return _plain(value, names[info.field_name])

    @field_validator("notice")
    @classmethod
    def check_notice(cls, value: str) -> str:
        return _plain(value, "分类提示", multiline=True)

    @model_validator(mode="after")
    def check_category(self) -> "Category":
        name = f"分类“{self.label}”"
        builtin_kind = BUILTIN_KINDS.get(self.key)
        if builtin_kind and self.kind != builtin_kind:
            raise ValueError(f"{name}的业务类型固定为 {builtin_kind}，不能修改")
        if not builtin_kind and self.kind != "general":
            raise ValueError(f"{name}是自定义分类，业务类型只能是普通（general）")

        keys = [f.key for f in self.fields]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"{name}的字段标识重复：{'、'.join(sorted(dupes))}")
        by_key = {f.key: f for f in self.fields}
        for index, f in enumerate(self.fields):
            if f.show_if:
                earlier = {g.key: g for g in self.fields[:index]}
                target = earlier.get(f.show_if.field)
                if not target:
                    raise ValueError(f"{name}的字段“{f.label}”的显示条件只能引用排在它前面的字段")
                if target.type not in ("select", "radio", "confirm"):
                    raise ValueError(f"{name}的字段“{f.label}”的显示条件只能引用下拉、单选或勾选字段")
                allowed = {o.value for o in target.options}
                wanted = f.show_if.in_ or ([f.show_if.equals] if f.show_if.equals is not None else [])
                if target.type == "confirm":
                    if f.show_if.in_ is not None or not isinstance(f.show_if.equals, bool):
                        raise ValueError(f"{name}的字段“{f.label}”引用勾选字段时只能判断是否勾选")
                elif any(not isinstance(v, str) or v not in allowed for v in wanted):
                    raise ValueError(f"{name}的字段“{f.label}”的显示条件引用了不存在的选项")

        system = SYSTEM_FIELDS.get(self.kind, {})
        for key, rule in system.items():
            f = by_key.get(key)
            if not f:
                raise ValueError(f"{name}缺少系统字段“{key}”，不能删除")
            if f.type != rule["type"] or not f.required:
                raise ValueError(f"{name}的系统字段“{f.label}”不能修改类型或取消必填")
            if "options" in rule and [o.value for o in f.options] != rule["options"]:
                raise ValueError(f"{name}的系统字段“{f.label}”的选项值不能修改（可以改选项名称）")
            want_show = rule.get("show_if")
            got_show = f.show_if.model_dump(by_alias=True, exclude_none=True) if f.show_if else None
            if want_show != got_show:
                raise ValueError(f"{name}的系统字段“{f.label}”的显示条件不能修改")
        for f in self.fields:
            f.system = f.key in system

        if self.title_mode == "auto" and not self.title_template:
            raise ValueError(f"{name}选择自动生成标题时必须填写标题模板")
        for var in TEMPLATE_VAR_RE.findall(self.title_template):
            if var != "category" and (var not in by_key or by_key[var].type == "textarea"):
                raise ValueError(f"{name}的标题模板引用了不存在或不适合的字段“{var}”")
        return self


class TicketFormConfig(Strict):
    schema_: int = Field(1, alias="schema")
    categories: list[Category] = Field(min_length=1, max_length=40)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("schema_")
    @classmethod
    def check_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("不支持的配置版本")
        return value

    @model_validator(mode="after")
    def check_categories(self) -> "TicketFormConfig":
        keys = [c.key for c in self.categories]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"分类标识重复：{'、'.join(sorted(dupes))}")
        missing = [k for k in BUILTIN_KINDS if k not in keys]
        if missing:
            raise ValueError(f"内置分类不能删除，只能停用：{'、'.join(missing)}")
        if not any(c.enabled for c in self.categories):
            raise ValueError("至少要启用一个分类")
        return self

    def dump(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def category(self, key: str) -> Category | None:
        return next((c for c in self.categories if c.key == key), None)


def load_default_form_config() -> TicketFormConfig:
    return TicketFormConfig.model_validate(json.loads(DEFAULT_FORM_CONFIG_PATH.read_text(encoding="utf-8")))


# ---- submitted data ----------------------------------------------------------

def _empty(value: Any) -> bool:
    return value is None or value is False or (isinstance(value, (str, list)) and not value)


def _number(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"“{label}”须为数字")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"“{label}”须为数字") from exc
    if not number.is_finite():
        raise ValueError(f"“{label}”须为数字")
    return number


def _clean(f: FormField, value: Any) -> Any:
    label = f.label
    if f.type in ("text", "textarea", "email", "order_no"):
        if not isinstance(value, str):
            raise ValueError(f"“{label}”须为文字")
        value = value.strip()
        if not value:
            return None
    if f.type in ("text", "textarea"):
        bad = TEXTAREA_CONTROL_RE if f.type == "textarea" else CONTROL_CHARS_RE
        if bad.search(value):
            raise ValueError(f"“{label}”包含不支持的字符")
        if len(value) > (f.max_length or 0):
            raise ValueError(f"“{label}”不能超过 {f.max_length} 个字")
        return value
    if f.type == "email":
        if len(value) > 254 or not EMAIL_RE.match(value):
            raise ValueError(f"“{label}”不是有效的邮箱地址")
        return value
    if f.type == "order_no":
        if not ORDER_NO_RE.match(value):
            raise ValueError(f"“{label}”格式不正确（4 到 64 位字母、数字、- 或 _）")
        return value
    if f.type == "order_no_list":
        items = re.split(r"[\s,，、;；]+", value) if isinstance(value, str) else value
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            raise ValueError(f"“{label}”格式不正确")
        cleaned: list[str] = []
        for item in (i.strip() for i in items):
            if not item:
                continue
            if not ORDER_NO_RE.match(item):
                raise ValueError(f"“{label}”中的订单号“{item[:64]}”格式不正确")
            if item not in cleaned:
                cleaned.append(item)
        if len(cleaned) > MAX_ORDER_NOS:
            raise ValueError(f"“{label}”最多填写 {MAX_ORDER_NOS} 个订单号")
        return cleaned or None
    if f.type in ("number", "money"):
        if isinstance(value, str) and not value.strip():
            return None
        number = _number(value, label)
        if f.type == "money":
            if number <= 0 or number > MONEY_MAX:
                raise ValueError(f"“{label}”须大于 0 且不超过 {MONEY_MAX}")
            if number != number.quantize(Decimal("0.01")):
                raise ValueError(f"“{label}”最多两位小数")
        if f.min is not None and number < Decimal(str(f.min)):
            raise ValueError(f"“{label}”不能小于 {f.min:g}")
        if f.max is not None and number > Decimal(str(f.max)):
            raise ValueError(f"“{label}”不能大于 {f.max:g}")
        if f.type == "money":
            return str(number.quantize(Decimal("0.01")))
        return int(number) if number == number.to_integral_value() else float(number)
    if f.type in ("select", "radio"):
        if value == "":
            return None
        if value not in {o.value for o in f.options}:
            raise ValueError(f"“{label}”的选项无效")
        return value
    if f.type == "confirm":
        if not isinstance(value, bool):
            raise ValueError(f"“{label}”须为勾选")
        return value or None
    if f.type == "date":
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as exc:
            raise ValueError(f"“{label}”不是有效的日期") from exc
    if f.type == "datetime":
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"“{label}”不是有效的时间") from exc
        # Local times from <input type="datetime-local"> are stored as typed (Beijing time).
        return parsed.isoformat(timespec="minutes")
    raise ValueError(f"“{label}”的类型不受支持")


def validate_form_data(category: Category, raw: dict[str, Any]) -> dict[str, Any]:
    """Return cleaned values for the visible fields. Raises ValueError with all problems joined by '；'."""
    if not isinstance(raw, dict):
        raise ValueError("表单数据格式不正确")
    known = {f.key for f in category.fields}
    unknown = [k for k in raw if k not in known]
    if unknown:
        raise ValueError(f"不认识的字段：{'、'.join(str(k)[:40] for k in unknown[:5])}")
    data: dict[str, Any] = {}
    errors: list[str] = []
    for f in category.fields:
        if f.show_if and not f.show_if.matches(data.get(f.show_if.field)):
            continue  # hidden: whatever was sent is dropped
        try:
            value = None if _empty(raw.get(f.key)) else _clean(f, raw.get(f.key))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if _empty(value):
            if f.required:
                errors.append(f"请勾选“{f.label}”" if f.type == "confirm" else f"“{f.label}”为必填项")
            continue
        data[f.key] = value
    if errors:
        raise ValueError("；".join(errors[:5]))
    return data


def display_value(f: FormField, value: Any) -> str:
    if f.type in ("select", "radio"):
        return next((o.label for o in f.options if o.value == value), str(value))
    if isinstance(value, list):
        return "、".join(value)
    if value is True:
        return "是"
    return str(value)


def render_title(category: Category, data: dict[str, Any]) -> str:
    fields = {f.key: f for f in category.fields}

    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key == "category":
            return category.label
        value = data.get(key)
        return display_value(fields[key], value) if key in fields and not _empty(value) else ""

    title = TEMPLATE_VAR_RE.sub(sub, category.title_template)
    title = re.sub(r"(\s*[·\-|:：]\s*)+$", "", title).strip()
    return (title or category.label)[:200]


def snapshot(category: Category) -> dict:
    """The category definition stored on each ticket, so later config edits never change how it reads."""
    return category.model_dump(mode="json", by_alias=True, exclude_none=True,
                               include={"key", "label", "kind", "fields"})


# Old tickets only had the fixed API troubleshooting columns.
LEGACY_FIELDS = [
    {"key": "request_id", "label": "Request ID", "type": "text"},
    {"key": "model_name", "label": "模型", "type": "text"},
    {"key": "api_endpoint", "label": "API 接口", "type": "text"},
    {"key": "occurred_at", "label": "发生时间", "type": "datetime"},
    {"key": "error_message", "label": "错误信息", "type": "textarea"},
]


def legacy_snapshot(key: str, label: str) -> dict:
    return {"key": key, "label": label, "kind": BUILTIN_KINDS.get(key, "general"),
            "fields": [{**f, "required": False, "system": False} for f in LEGACY_FIELDS]}
