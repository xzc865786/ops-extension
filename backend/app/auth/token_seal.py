"""Seal Sub2API bearer tokens at rest for session revalidation only.

Tokens are never logged or returned via API. Key is derived from SESSION_SECRET.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(f"ops-ext-token-seal:{secret}".encode("utf-8")).digest()


def seal_token(secret: str, token: str) -> str:
    key = _derive_key(secret)
    nonce = os.urandom(16)
    raw = token.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < len(raw):
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(raw, out[: len(raw)]))
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def unseal_token(secret: str, blob: str) -> str | None:
    try:
        data = base64.urlsafe_b64decode(blob.encode("ascii"))
    except Exception:
        return None
    if len(data) < 16 + 32:
        return None
    key = _derive_key(secret)
    nonce, mac, cipher = data[:16], data[16:48], data[48:]
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return None
    out = bytearray()
    counter = 0
    while len(out) < len(cipher):
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    plain = bytes(a ^ b for a, b in zip(cipher, out[: len(cipher)]))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None
