"""Passwords, tokens, API keys, rate limits and security headers. Standard library only."""
import hashlib, hmac, re, secrets, threading, time
from collections import deque

_N, _R, _P = 2 ** 14, 8, 1
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt": return False
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(dk)))
        return hmac.compare_digest(got, bytes.fromhex(dk))
    except (ValueError, TypeError):
        return False


def password_problem(pw: str, email: str = "") -> str | None:
    """None when the password is acceptable, else the reason."""
    if len(pw) < 10: return "use at least 10 characters"
    if len(set(pw)) < 4: return "use more different characters"
    if email and pw.lower() == email.lower(): return "do not use your email address"
    return None


def new_token() -> str: return secrets.token_urlsafe(32)
def hash_token(t: str) -> str: return hashlib.sha256(t.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """Returns (the key, shown once; its prefix, kept to recognise it; its hash, kept to check it)."""
    key = "mcpd_" + secrets.token_urlsafe(32)
    return key, key[:12], hash_token(key)


class RateLimiter:
    """At most `limit` events per `per` seconds for each key, in memory (one process). Good enough for a single-server install."""
    def __init__(self): self.hits, self.lock = {}, threading.Lock()

    def allow(self, key: str, limit: int, per: float) -> bool:
        t = time.monotonic()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and t - q[0] > per: q.popleft()
            if len(q) >= limit: return False
            q.append(t); return True

    def reset(self):
        with self.lock: self.hits.clear()


limiter = RateLimiter()

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                               "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def csv_safe(v) -> str:
    """A spreadsheet must not run a cell as a formula (CSV injection)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
