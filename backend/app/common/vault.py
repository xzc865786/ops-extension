"""AES-256-GCM field encryption for stored account secrets.

The key lives only in ACCOUNT_VAULT_KEY, never in the database, so a database backup alone
does not expose secrets. Losing the key makes every stored secret unrecoverable.
"""
import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.common.errors import AppError
from app.config import get_settings

# Stored as "v1:<base64(nonce | ciphertext)>"; the prefix leaves room for key rotation.
VERSION = "v1"


def vault_error(detail: str, code: str) -> AppError:
    return AppError(503, detail, code)


def _cipher() -> AESGCM:
    raw = get_settings().account_vault_key.strip()
    if not raw:
        raise vault_error("未配置账号加密密钥 ACCOUNT_VAULT_KEY，暂不能保存或查看密码", "VAULT_NOT_CONFIGURED")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        key = b""
    if len(key) != 32:
        raise vault_error("ACCOUNT_VAULT_KEY 须为 32 字节随机值的 base64 编码", "VAULT_KEY_INVALID")
    return AESGCM(key)


def require() -> None:
    """Raises the configuration error up front, before anything is written."""
    _cipher()


def ready() -> bool:
    try:
        _cipher()
        return True
    except AppError:
        return False


def encrypt(plaintext: str, context: str) -> str:
    """`context` (e.g. "account:12:password") is authenticated, so ciphertext cannot be moved between rows or fields."""
    nonce = os.urandom(12)
    sealed = _cipher().encrypt(nonce, plaintext.encode(), context.encode())
    return f"{VERSION}:{base64.b64encode(nonce + sealed).decode()}"


def decrypt(token: str, context: str) -> str:
    version, _, payload = token.partition(":")
    if version != VERSION:
        raise vault_error("不支持的密文版本", "VAULT_VERSION_UNSUPPORTED")
    data = base64.b64decode(payload)
    try:
        return _cipher().decrypt(data[:12], data[12:], context.encode()).decode()
    except InvalidTag:
        raise vault_error("当前加密密钥无法解开已保存的内容，请确认 ACCOUNT_VAULT_KEY 未被更换", "VAULT_DECRYPT_FAILED") from None
