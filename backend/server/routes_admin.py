"""An organisation admin's settings: people and roles, API keys for connectors, retention and privacy settings, purge, and the audit log."""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB
from . import db as M, engine
from .deps import Ctx, need
from .security import EMAIL, hash_password, new_api_key, password_problem
from .services import purge_org

router = APIRouter(prefix="/api/admin")
ORG_ROLES = ("viewer", "analyst", "admin")


def user_out(u: M.User):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "active": u.active, "created_at": u.created_at, "last_login_at": u.last_login_at}


class NewUser(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(default="", max_length=200)
    role: str = "analyst"
    password: str = Field(min_length=1, max_length=500)


def create_user(db, org_id, body: NewUser, actor, allowed_roles=ORG_ROLES):
    email = body.email.strip().lower()
    if not EMAIL.match(email): raise HTTPException(422, "that email address does not look right")
    if body.role not in allowed_roles: raise HTTPException(422, f"role must be one of {', '.join(allowed_roles)}")
    if db.scalar(select(M.User).where(func.lower(M.User.email) == email)): raise HTTPException(409, "an account with this email already exists")
    why = password_problem(body.password, email)
    if why: raise HTTPException(422, f"choose another password: {why}")
    u = M.User(org_id=org_id, email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(u); db.flush(); M.audit(db, "user.created", actor, org_id, f"{email} as {body.role}"); db.commit()
    return u


@router.get("/users")
def users(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    return [user_out(u) for u in db.scalars(select(M.User).where(M.User.org_id == ctx.org.id).order_by(M.User.email))]


@router.post("/users")
def add_user(body: NewUser, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    return user_out(create_user(db, ctx.org.id, body, ctx.user))


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)


@router.patch("/users/{uid}")
def edit_user(uid: int, body: UserPatch, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    u = db.get(M.User, uid)
    if u is None or u.org_id != ctx.org.id: raise HTTPException(404, "no such user in this organisation")
    if u.id == ctx.user.id and (body.role not in (None, u.role) or body.active is False): raise HTTPException(409, "you cannot change your own role or disable yourself")
    if body.role is not None and body.role not in ORG_ROLES: raise HTTPException(422, f"role must be one of {', '.join(ORG_ROLES)}")
    demoting = u.role == "admin" and ((body.role is not None and body.role != "admin") or body.active is False)
    if demoting and db.scalar(select(func.count()).select_from(M.User).where(M.User.org_id == ctx.org.id, M.User.role == "admin", M.User.active.is_(True))) <= 1:
        raise HTTPException(409, "the organisation needs at least one active admin")
    changes = []
    if body.role is not None: u.role = body.role; changes.append(f"role {body.role}")
    if body.active is not None: u.active = body.active; changes.append("enabled" if body.active else "disabled")
    if body.name is not None: u.name = body.name.strip(); changes.append("name")
    if body.password:
        why = password_problem(body.password, u.email)
        if why: raise HTTPException(422, f"choose another password: {why}")
        u.password_hash = hash_password(body.password); u.failed_logins = 0; u.locked_until = 0; changes.append("password reset")
    M.audit(db, "user.updated", ctx.user, ctx.org.id, f"{u.email}: " + ", ".join(changes)); db.commit()
    return user_out(u)


class NewKey(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def key_out(k: M.ApiKey):
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "created_at": k.created_at, "last_used_at": k.last_used_at, "revoked": k.revoked_at is not None}


@router.get("/api-keys")
def api_keys(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    return [key_out(k) for k in db.scalars(select(M.ApiKey).where(M.ApiKey.org_id == ctx.org.id).order_by(M.ApiKey.created_at.desc()))]


@router.post("/api-keys")
def add_api_key(body: NewKey, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    key, prefix, h = new_api_key()
    k = M.ApiKey(org_id=ctx.org.id, name=body.name.strip(), prefix=prefix, key_hash=h, created_by=ctx.user.id); db.add(k); db.flush()
    M.audit(db, "api_key.created", ctx.user, ctx.org.id, f"{body.name.strip()} ({prefix}...)"); db.commit()
    return {**key_out(k), "key": key, "note": "Copy this key now. It is shown only once; only its hash is kept."}


@router.delete("/api-keys/{kid}")
def revoke_api_key(kid: int, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    k = db.get(M.ApiKey, kid)
    if k is None or k.org_id != ctx.org.id: raise HTTPException(404, "no such key in this organisation")
    if k.revoked_at is None: k.revoked_at = M.now(); M.audit(db, "api_key.revoked", ctx.user, ctx.org.id, f"{k.name} ({k.prefix}...)"); db.commit()
    return key_out(k)


class SettingsIn(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    keep_labels: bool | None = None
    store_content: bool | None = None


def settings_out(o: M.Org):
    return {"name": o.name, "retention_days": o.retention_days, "keep_labels": o.keep_labels, "store_content": o.store_content}


@router.get("/settings")
def get_settings_(ctx: Ctx = Depends(need("admin"))):
    return settings_out(ctx.org)


@router.patch("/settings")
def set_settings(body: SettingsIn, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    o = db.get(M.Org, ctx.org.id); ch = []
    for f in ("retention_days", "keep_labels", "store_content"):
        v = getattr(body, f)
        if v is not None and v != getattr(o, f): setattr(o, f, v); ch.append(f"{f}={v}")
    if ch: M.audit(db, "settings.updated", ctx.user, o.id, ", ".join(ch)); db.commit()
    engine.store(o)                                  # applies store_content to the open store
    return settings_out(o)


class PurgeIn(BaseModel):
    older_than_days: float | None = Field(default=None, ge=0, le=3650)


@router.post("/purge")
def purge(body: PurgeIn, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    r = purge_org(db, db.get(M.Org, ctx.org.id), body.older_than_days)
    M.audit(db, "retention.purge_manual", ctx.user, ctx.org.id, f"older than {r['older_than_days']:g} days"); db.commit()
    return r


@router.get("/audit")
def audit_log(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    users = {u.id: u.email for u in db.scalars(select(M.User))}
    return [{"id": a.id, "at": a.created_at, "action": a.action, "detail": a.detail, "by": users.get(a.user_id, "system") if a.user_id else "system"}
            for a in db.scalars(select(M.AuditLog).where(M.AuditLog.org_id == ctx.org.id).order_by(M.AuditLog.id.desc()).limit(300))]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
