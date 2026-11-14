"""Sign in, sign out, who am I, change password, and (for the consultant) choose which client organisation to work in."""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DB
from . import db as M
from .config import get_settings
from .deps import COOKIE, Ctx, client_ip, session_ctx
from .security import hash_password, hash_token, limiter, new_token, password_problem, verify_password

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=500)


def me_payload(db, u: M.User, s: M.AuthSession):
    org_id = s.active_org_id if u.role == "superadmin" else u.org_id
    org = db.get(M.Org, org_id) if org_id else None
    out = {"signed_in": True, "user": {"id": u.id, "email": u.email, "name": u.name, "role": u.role}, "csrf": s.csrf,
           "org": {"id": org.id, "name": org.name, "slug": org.slug, "retention_days": org.retention_days, "keep_labels": org.keep_labels,
                   "store_content": org.store_content} if org else None, "app_name": get_settings().app_name}
    if u.role == "superadmin":
        out["orgs"] = [{"id": o.id, "name": o.name, "active": o.active} for o in db.scalars(select(M.Org).order_by(M.Org.name))]
    return out


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB = Depends(M.get_db)):
    st = get_settings(); ip = client_ip(request)
    if not limiter.allow(f"login:{ip}", 10, 60): raise HTTPException(429, "too many sign-in attempts: wait a minute")
    u = db.scalar(select(M.User).where(func.lower(M.User.email) == body.email.strip().lower()))
    bad = HTTPException(401, "wrong email or password")
    if u is None or not u.active:
        verify_password(body.password, hash_password("timing-equaliser"))     # same work whether or not the account exists
        raise bad
    if u.locked_until > M.now(): raise HTTPException(423, "too many failed attempts: this account is locked for a few minutes")
    if not verify_password(body.password, u.password_hash):
        u.failed_logins += 1
        if u.failed_logins >= st.login_attempts_before_lock: u.locked_until = M.now() + st.lock_minutes * 60; u.failed_logins = 0
        M.audit(db, "auth.login_failed", u); db.commit(); raise bad
    if u.org_id is not None:
        org = db.get(M.Org, u.org_id)
        if org is None or not org.active: raise HTTPException(403, "this organisation is disabled")
    u.failed_logins = 0; u.last_login_at = M.now()
    tok = new_token(); s = M.AuthSession(token_hash=hash_token(tok), user_id=u.id, csrf=secrets.token_urlsafe(24), expires_at=M.now() + st.session_hours * 3600)
    db.add(s); M.audit(db, "auth.login", u); db.commit()
    response.set_cookie(COOKIE, tok, httponly=True, secure=st.secure_cookies, samesite="strict", max_age=int(st.session_hours * 3600), path="/")
    return me_payload(db, u, s)


@router.post("/logout")
def logout(response: Response, ctx: Ctx = Depends(session_ctx), db: DB = Depends(M.get_db)):
    db.execute(delete(M.AuthSession).where(M.AuthSession.id == ctx.session.id)); M.audit(db, "auth.logout", ctx.user); db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: DB = Depends(M.get_db)):
    """Who is signed in. Not being signed in is a normal answer here (the website asks on every page), not an error."""
    try: ctx = session_ctx(request, db)
    except HTTPException: return {"signed_in": False}
    return me_payload(db, ctx.user, ctx.session)


class PasswordIn(BaseModel):
    current: str = Field(min_length=1, max_length=500)
    new: str = Field(min_length=1, max_length=500)


@router.post("/password")
def change_password(body: PasswordIn, ctx: Ctx = Depends(session_ctx), db: DB = Depends(M.get_db)):
    u = db.get(M.User, ctx.user.id)
    if not verify_password(body.current, u.password_hash): raise HTTPException(403, "the current password is wrong")
    why = password_problem(body.new, u.email)
    if why: raise HTTPException(422, f"choose another password: {why}")
    u.password_hash = hash_password(body.new)
    db.execute(delete(M.AuthSession).where(M.AuthSession.user_id == u.id, M.AuthSession.id != ctx.session.id))   # sign out everywhere else
    M.audit(db, "auth.password_changed", u); db.commit()
    return {"ok": True}


class SwitchIn(BaseModel):
    org_id: int | None = None


@router.post("/switch-org")
def switch_org(body: SwitchIn, ctx: Ctx = Depends(session_ctx), db: DB = Depends(M.get_db)):
    if ctx.user.role != "superadmin": raise HTTPException(403, "only the consultant account works across organisations")
    if body.org_id is not None and db.get(M.Org, body.org_id) is None: raise HTTPException(404, "no such organisation")
    s = db.get(M.AuthSession, ctx.session.id); s.active_org_id = body.org_id
    M.audit(db, "auth.switch_org", ctx.user, body.org_id, ""); db.commit()
    return me_payload(db, ctx.user, s)
