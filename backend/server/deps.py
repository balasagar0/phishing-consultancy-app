"""Who is calling: a signed-in person (session cookie + CSRF header) or a connector (API key). Every data route is scoped to one organisation."""
import base64, binascii
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from . import db as M
from .security import hash_token, limiter

COOKIE = "mcpd_session"


@dataclass
class Ctx:
    user: M.User | None
    org: M.Org | None
    session: M.AuthSession | None = None
    api_key: M.ApiKey | None = None

    @property
    def role(self): return self.user.role if self.user else "connector"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def session_ctx(request: Request, db: DB = Depends(M.get_db)) -> Ctx:
    tok = request.cookies.get(COOKIE)
    if not tok: raise HTTPException(401, "sign in first")
    s = db.scalar(select(M.AuthSession).where(M.AuthSession.token_hash == hash_token(tok)))
    if s is None or s.expires_at < M.now(): raise HTTPException(401, "your session has ended: sign in again")
    u = db.get(M.User, s.user_id)
    if u is None or not u.active: raise HTTPException(401, "this account is disabled")
    org_id = s.active_org_id if u.role == "superadmin" else u.org_id
    org = db.get(M.Org, org_id) if org_id else None
    if u.role != "superadmin" and (org is None or not org.active): raise HTTPException(403, "this organisation is disabled")
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("x-csrf-token") != s.csrf:
        raise HTTPException(403, "missing or wrong CSRF token: reload the page")
    return Ctx(user=u, org=org, session=s)


def need(min_role: str, org: bool = True):
    """A dependency: the caller is signed in with at least `min_role`; with org=True an organisation must be in scope."""
    def dep(ctx: Ctx = Depends(session_ctx)) -> Ctx:
        if M.RANK[ctx.user.role] < M.RANK[min_role]: raise HTTPException(403, f"this needs the {min_role} role")
        if org and ctx.org is None: raise HTTPException(409, "choose an organisation first")
        return ctx
    return dep


def _key_of(request: Request) -> str:
    """'Authorization: Bearer <key>', 'X-API-Key: <key>', or HTTP Basic with the key as the password (for SMS gateways such as Twilio, which
    can put credentials in the webhook address but cannot add headers)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "): return auth[7:].strip()
    if auth.lower().startswith("basic "):
        try: return base64.b64decode(auth[6:].strip(), validate=True).decode("utf-8").split(":", 1)[1].strip()
        except (ValueError, IndexError, UnicodeDecodeError, binascii.Error): return ""
    return request.headers.get("x-api-key", "").strip()


def _key_ctx(request: Request, db: DB, per_minute: int) -> Ctx:
    key = _key_of(request)
    if not key: raise HTTPException(401, "send the API key as 'Authorization: Bearer <key>'")
    k = db.scalar(select(M.ApiKey).where(M.ApiKey.key_hash == hash_token(key)))
    if k is None or k.revoked_at is not None: raise HTTPException(401, "unknown or revoked API key")
    org = db.get(M.Org, k.org_id)
    if org is None or not org.active: raise HTTPException(403, "this organisation is disabled")
    if not limiter.allow(f"key:{k.id}", per_minute, 60): raise HTTPException(429, f"too many requests for this key: at most {per_minute} a minute")
    k.last_used_at = M.now(); db.commit()
    return Ctx(user=None, org=org, api_key=k)


def api_key_ctx(request: Request, db: DB = Depends(M.get_db)) -> Ctx:
    return _key_ctx(request, db, 120)


def hook_key_ctx(request: Request, db: DB = Depends(M.get_db)) -> Ctx:
    """Webhooks carry one message each and arrive as fast as messages do, so they get a larger allowance."""
    return _key_ctx(request, db, 600)
