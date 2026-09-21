import logging

import httpx

from app.common.errors import unauthorized
from app.config import get_settings
from app.identity.provider import Sub2APIUser

logger = logging.getLogger(__name__)


class Sub2APIIdentityProvider:
    """Calls Sub2API GET /api/v1/auth/me with Bearer token. Never logs the token."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        settings = get_settings()
        self.base_url = (base_url or settings.sub2api_base_url).rstrip("/")
        self.timeout = timeout

    def verify_and_get_user(self, bearer_token: str) -> Sub2APIUser:
        if not bearer_token:
            raise unauthorized("缺少 token", "MISSING_TOKEN")
        url = f"{self.base_url}/api/v1/auth/me"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers={"Authorization": f"Bearer {bearer_token}"})
        except httpx.HTTPError as exc:
            logger.warning("Sub2API auth/me request failed: %s", type(exc).__name__)
            raise unauthorized("身份验证服务不可用", "IDENTITY_UNAVAILABLE") from exc

        if resp.status_code == 401:
            raise unauthorized("token 无效或已过期", "INVALID_TOKEN")
        if resp.status_code != 200:
            logger.warning("Sub2API auth/me status=%s", resp.status_code)
            raise unauthorized("身份验证失败", "IDENTITY_FAILED")

        body = resp.json()
        # Sub2API wraps as {code, message, data}
        if isinstance(body, dict) and "data" in body:
            if body.get("code", 0) != 0:
                raise unauthorized(body.get("message") or "身份验证失败", "IDENTITY_FAILED")
            data = body["data"]
        else:
            data = body

        try:
            user_id = int(data["id"])  # MUST use data.id, NOT user_id
        except (KeyError, TypeError, ValueError) as exc:
            raise unauthorized("身份响应缺少 id", "IDENTITY_MALFORMED") from exc

        return Sub2APIUser(
            id=user_id,
            username=str(data.get("username") or ""),
            email=str(data.get("email") or ""),
            role=str(data.get("role") or "user"),
            status=str(data.get("status") or ""),
        )


class DevBypassIdentityProvider:
    """Dev-only provider: token is 'dev:<json>' or uses fixed payload."""

    def verify_and_get_user(self, bearer_token: str) -> Sub2APIUser:
        import json

        raw = bearer_token
        if raw.startswith("dev:"):
            raw = raw[4:]
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise unauthorized("dev token 无效", "INVALID_TOKEN") from exc
        return Sub2APIUser(
            id=int(data["id"]),
            username=str(data.get("username") or "dev"),
            email=str(data.get("email") or "dev@example.com"),
            role=str(data.get("role") or "user"),
            status=str(data.get("status") or "active"),
        )


def get_identity_provider() -> Sub2APIIdentityProvider | DevBypassIdentityProvider:
    settings = get_settings()
    if settings.dev_auth_bypass:
        return DevBypassIdentityProvider()
    return Sub2APIIdentityProvider()
