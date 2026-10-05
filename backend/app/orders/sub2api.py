"""Sub2API admin payment API, called with the Admin API Key.

The key carries full Sub2API admin power, so this client exposes only the few endpoints the ticket
flows need and never logs the key, request headers or response bodies.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class Sub2APIUnavailable(Exception):
    """Network failure, timeout, 5xx or an unreadable response."""


class Sub2APIError(Exception):
    """Sub2API answered with a 4xx; ``code`` is Sub2API's error code when it sent one."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message


ERROR_CODES = {
    "REFUND_DISABLED": "该订单的支付渠道未开启退款，请在 Sub2API 支付服务商设置中打开“允许退款”",
    "INVALID_STATUS": "订单当前状态不允许这个操作",
    "REFUND_AMOUNT_EXCEEDED": "退款金额超过订单到账额度",
    "INVALID_AMOUNT": "退款金额无效",
    "CONFLICT": "订单状态刚刚发生变化，请先同步结果再操作",
    "PROVIDER_LOOKUP_FAILED": "Sub2API 查找该订单的支付渠道失败",
    "REFUND_QUERY_UNSUPPORTED": "该支付渠道不支持查询退款结果，请到支付平台核实",
    "NOT_FOUND": "Sub2API 中找不到该订单",
}


def admin_reason(exc: Exception) -> str:
    """Explanation for admins (users only ever see a generic message)."""
    if isinstance(exc, Sub2APIError):
        if exc.status == 401:
            return "Sub2API Admin API Key 无效，请检查 Ops 的 SUB2API_ADMIN_API_KEY 配置"
        if exc.status == 423:
            return "Sub2API 第一个管理员账号尚未完成“管理员合规确认”"
        if exc.code in ERROR_CODES:
            return ERROR_CODES[exc.code]
        return f"Sub2API 返回错误：{exc.code or exc.status} {exc.message}".strip()
    return "无法连接 Sub2API，请检查 SUB2API_BASE_URL 和网络"


class Sub2APIAdminClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None):
        try:
            with httpx.Client(base_url=self._base_url, timeout=self._timeout, transport=self._transport) as client:
                resp = client.request(method, path, params=params, json=json, headers={"x-api-key": self._api_key})
        except httpx.HTTPError as exc:
            logger.warning("sub2api admin %s %s failed: %s", method, path, type(exc).__name__)
            raise Sub2APIUnavailable() from exc
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code >= 500 or not isinstance(body, dict):
            logger.warning("sub2api admin %s %s status=%s", method, path, resp.status_code)
            raise Sub2APIUnavailable()
        if resp.status_code >= 400 or body.get("code", 0) != 0:
            code = str(body.get("reason") or body.get("code") or "")
            logger.warning("sub2api admin %s %s status=%s code=%s", method, path, resp.status_code, code)
            raise Sub2APIError(resp.status_code, code, str(body.get("message") or "")[:200])
        return body.get("data")

    def find_user_order(self, user_id: int, out_trade_no: str) -> dict | None:
        """The order with exactly this out_trade_no belonging to the user, or None."""
        data = self._request("GET", "/api/v1/admin/payment/orders",
                             params={"user_id": user_id, "keyword": out_trade_no, "page_size": 50})
        items = (data or {}).get("items") or []
        for order in items:
            # keyword is a fuzzy match on out_trade_no / email / name; the user filter is server side,
            # but check both again so a changed upstream behaviour cannot leak another user's order.
            if order.get("out_trade_no") == out_trade_no and int(order.get("user_id") or 0) == int(user_id):
                return order
        return None

    def get_order(self, order_id: int) -> dict | None:
        try:
            data = self._request("GET", f"/api/v1/admin/payment/orders/{int(order_id)}")
        except Sub2APIError as exc:
            if exc.status == 404:
                return None
            raise
        return (data or {}).get("order")

    def refund(self, order_id: int, *, amount, reason: str, deduct_balance: bool, force: bool) -> dict:
        """Original-route refund. ``amount`` is in credited units and always explicit: 0 would mean a full refund."""
        if not amount or amount <= 0:
            raise ValueError("refund amount must be positive")
        data = self._request("POST", f"/api/v1/admin/payment/orders/{int(order_id)}/refund", json={
            "amount": float(amount), "reason": reason, "force": force, "deduct_balance": deduct_balance,
        })
        return data or {}

    def query_refund(self, order_id: int) -> dict:
        """Ask the gateway about a REFUND_PENDING order and finalise it in Sub2API."""
        data = self._request("POST", f"/api/v1/admin/payment/orders/{int(order_id)}/refund/query")
        return data or {}


def get_admin_client() -> Sub2APIAdminClient | None:
    settings = get_settings()
    if not settings.sub2api_admin_api_key:
        return None
    return Sub2APIAdminClient(settings.sub2api_base_url, settings.sub2api_admin_api_key,
                              timeout=settings.sub2api_admin_timeout)
