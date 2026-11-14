"""Secrets the server has to use again later (a mailbox password, a Microsoft 365 client secret, an alert webhook's signing secret), encrypted
with AES-256-GCM under a key derived from the master key. Each secret is bound to its organisation and purpose, so a copied value does not
decrypt anywhere else. The API never returns a secret, only whether one is set. Losing the master key means entering them again."""
import base64, hashlib, hmac, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .config import get_settings


def _key() -> bytes:
    return hmac.new(get_settings().master_key, b"secretbox:v1", hashlib.sha256).digest()


def seal(plain: str, aad: str) -> str:
    if not plain: return ""
    n = os.urandom(12)
    return "v1:" + base64.b64encode(n + AESGCM(_key()).encrypt(n, plain.encode(), aad.encode())).decode()


def unseal(token: str, aad: str) -> str:
    if not token: return ""
    if not token.startswith("v1:"): raise ValueError("unknown secret format")
    raw = base64.b64decode(token[3:])
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], aad.encode()).decode()
