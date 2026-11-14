"""Passwords, tokens, API keys, rate limits, security headers, and the checks on addresses the server connects to. Standard library only."""
import hashlib, hmac, ipaddress, os, re, secrets, socket, threading, time, urllib.error, urllib.request
from collections import deque
from urllib.parse import urlsplit

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


HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$")


def private_allowed() -> bool:
    """MCPD_ALLOW_PRIVATE_HOSTS=1 lets connectors and webhooks reach private and local addresses: for an install inside a client's network,
    and for tests. Off by default, so one client's admin cannot make the server probe the network it runs in."""
    return os.environ.get("MCPD_ALLOW_PRIVATE_HOSTS", "").strip().lower() in ("1", "true", "yes", "on")


def vet_host(host: str, port: int) -> str:
    """Resolves a host the server is about to connect to and returns the address to use. Refuses private, local and reserved addresses unless
    they are allowed. Connecting to the returned address (not the name again) keeps a second DNS answer from changing the target."""
    if not HOSTNAME.match(host or ""): raise ValueError("the host name does not look right")
    try: infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror: raise ValueError(f"cannot find the address of {host}")
    addrs = [i[4][0] for i in infos]
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global and not private_allowed():
            raise ValueError(f"{host} is a private or local address; the server's operator must set MCPD_ALLOW_PRIVATE_HOSTS=1 to allow it")
    return addrs[0]


def vet_url(url: str) -> str:
    """An outgoing webhook address: https (http only where private addresses are allowed), a proper host, a public address."""
    p = urlsplit(url or "")
    if p.scheme not in ("https", "http") or not p.hostname: raise ValueError("give a full address starting with https://")
    if p.scheme == "http" and not private_allowed(): raise ValueError("use https://; plain http is allowed only inside a private network")
    if p.username or p.password: raise ValueError("put no user name or password in the address; use the signing secret")
    vet_host(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect refused ({code})", headers, fp)


# For every request the server makes on its own (alert webhooks, Microsoft Graph): a redirect is refused, so it can neither lead the server
# past vet_url to a private address nor carry an access token to another host.
no_redirect_opener = urllib.request.build_opener(_NoRedirect)


def csv_safe(v) -> str:
    """A spreadsheet must not run a cell as a formula (CSV injection)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
