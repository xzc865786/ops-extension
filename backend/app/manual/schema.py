"""Manual configuration schema.

Values here are embedded into scripts that run on users' Windows machines (install / config CMD),
into CC Switch import links and into the public manual pages. Every field is therefore restricted
to a narrow whitelist format; anything else is rejected before it can be saved.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).with_name("default_config.json")

# Model ID or wildcard pattern: letters, digits and . _ : / - plus * as wildcard.
MODEL_PATTERN_RE = re.compile(r"^[A-Za-z0-9.*_:/-]{1,128}$")
# https URL without query, fragment, credentials, %-escapes or quotes (safe inside cmd `set "X=..."`).
HTTPS_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?$")
SITE_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d{1,5})?$")
MANUAL_ASSET_RE = re.compile(r"^assets/downloads/[A-Za-z0-9._-]{1,120}$")
NPM_PACKAGE_RE = re.compile(r"^(@[a-z0-9][a-z0-9._-]{0,100}/)?[a-z0-9][a-z0-9._-]{0,100}$")
STORE_ID_RE = re.compile(r"^[A-Z0-9]{12}$")
WINGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}(\.[A-Za-z0-9][A-Za-z0-9-]{0,63}){1,3}$")
VERSION_RE = re.compile(r"^\d{1,4}\.\d{1,4}\.\d{1,6}$")
QQ_RE = re.compile(r"^(\d{5,12})?$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _patterns(values: list[str], field: str) -> list[str]:
    cleaned = []
    for value in values:
        value = value.strip()
        if not MODEL_PATTERN_RE.match(value) or not re.search(r"[A-Za-z0-9]", value):
            raise ValueError(f"“{value}” 不是合法的模型 ID 或通配符（只能用字母、数字和 . _ : / - *）")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _https(value: str, field: str, pattern: re.Pattern[str] = HTTPS_URL_RE) -> str:
    value = value.strip()
    if not pattern.match(value):
        raise ValueError("必须是 https 地址，且不能包含空格、引号、%、? 或 #")
    return value


class Site(Strict):
    url: str

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return _https(value.rstrip("/"), "站点地址", SITE_URL_RE)


class Contact(Strict):
    qq: str = ""

    @field_validator("qq")
    @classmethod
    def check_qq(cls, value: str) -> str:
        value = value.strip()
        if not QQ_RE.match(value):
            raise ValueError("客服 QQ 只能是 5 到 12 位数字，或留空")
        return value


class Announcement(Strict):
    enabled: bool = False
    level: Literal["info", "warning"] = "info"
    text: str = Field(default="", max_length=300)

    @field_validator("text")
    @classmethod
    def check_text(cls, value: str) -> str:
        value = value.strip()
        if CONTROL_CHARS_RE.search(value):
            raise ValueError("公告不能包含控制字符")
        return value

    @model_validator(mode="after")
    def need_text_when_enabled(self) -> "Announcement":
        if self.enabled and not self.text:
            raise ValueError("开启公告时必须填写公告内容")
        return self


class ClientModels(Strict):
    include: list[str] = Field(min_length=1, max_length=30)
    exclude: list[str] = Field(default_factory=list, max_length=30)
    recommend: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("include", "exclude", "recommend")
    @classmethod
    def check_patterns(cls, values: list[str], info) -> list[str]:
        return _patterns(values, info.field_name)


class Models(Strict):
    claude: ClientModels
    codex: ClientModels
    workbuddy: ClientModels


class ClaudeRoles(Strict):
    fable: list[str] = Field(max_length=10)
    opus: list[str] = Field(max_length=10)
    sonnet: list[str] = Field(max_length=10)
    haiku: list[str] = Field(max_length=10)
    subagent: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("fable", "opus", "sonnet", "haiku", "subagent")
    @classmethod
    def check_patterns(cls, values: list[str], info) -> list[str]:
        return _patterns(values, info.field_name)


class WorkBuddy(Strict):
    max_input_tokens: int = Field(ge=1024, le=2_000_000)
    max_output_tokens: int = Field(ge=256, le=1_000_000)
    supports_tool_call: bool
    supports_images: bool
    supports_reasoning: bool


class Install(Strict):
    npm_registry: str
    npm_registry_fallback: str
    node_mirror: str
    node_min_major: int = Field(ge=18, le=60)
    node_lts_major: int = Field(ge=18, le=60)
    claude_package: str
    codex_package: str
    codex_store_id: str
    workbuddy_winget_id: str
    workbuddy_site: str
    workbuddy_size_mb: int = Field(ge=1, le=10_000)

    @field_validator("npm_registry", "npm_registry_fallback", "node_mirror", "workbuddy_site")
    @classmethod
    def check_urls(cls, value: str, info) -> str:
        return _https(value.rstrip("/") if info.field_name != "workbuddy_site" else value, info.field_name)

    @field_validator("claude_package", "codex_package")
    @classmethod
    def check_package(cls, value: str) -> str:
        value = value.strip()
        if not NPM_PACKAGE_RE.match(value):
            raise ValueError(f"“{value}” 不是合法的 npm 包名")
        return value

    @field_validator("codex_store_id")
    @classmethod
    def check_store_id(cls, value: str) -> str:
        value = value.strip()
        if not STORE_ID_RE.match(value):
            raise ValueError("微软商店 ID 必须是 12 位大写字母或数字")
        return value

    @field_validator("workbuddy_winget_id")
    @classmethod
    def check_winget_id(cls, value: str) -> str:
        value = value.strip()
        if not WINGET_ID_RE.match(value):
            raise ValueError("winget ID 格式应为“厂商.名称”，只能包含字母、数字、- 和 .")
        return value

    @model_validator(mode="after")
    def check_node_versions(self) -> "Install":
        if self.node_min_major > self.node_lts_major:
            raise ValueError("Node.js 最低版本不能高于安装版本")
        return self


class DownloadSource(Strict):
    source: Literal["url", "file"]
    file_id: int | None = None
    url: str = ""

    @model_validator(mode="after")
    def check_source(self) -> "DownloadSource":
        if self.source == "file":
            if not self.file_id or self.file_id <= 0:
                raise ValueError("选择上传文件时必须指定文件")
        else:
            value = self.url.strip()
            if not (HTTPS_URL_RE.match(value) or MANUAL_ASSET_RE.match(value)):
                raise ValueError("下载地址必须是 https 地址，或手册内的 assets/downloads/ 文件")
            self.url = value
            self.file_id = None
        return self


class CCSwitch(Strict):
    version: str
    windows: DownloadSource
    releases_url: str

    @field_validator("version")
    @classmethod
    def check_version(cls, value: str) -> str:
        value = value.strip().lstrip("vV")
        if not VERSION_RE.match(value):
            raise ValueError("版本号格式应为 3.20.4")
        return value

    @field_validator("releases_url")
    @classmethod
    def check_releases(cls, value: str) -> str:
        return _https(value, "GitHub 发布页地址")


class ManualConfig(Strict):
    schema_: int = Field(1, alias="schema")
    updated_on: date
    site: Site
    contact: Contact
    announcement: Announcement
    models: Models
    claude_roles: ClaudeRoles
    workbuddy: WorkBuddy
    install: Install
    ccswitch: CCSwitch

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("schema_")
    @classmethod
    def check_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("不支持的配置版本")
        return value

    def dump(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)

    def referenced_file_ids(self) -> set[int]:
        ids = set()
        if self.ccswitch.windows.source == "file" and self.ccswitch.windows.file_id:
            ids.add(self.ccswitch.windows.file_id)
        return ids


def load_default_config() -> ManualConfig:
    return ManualConfig.model_validate(json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")))
