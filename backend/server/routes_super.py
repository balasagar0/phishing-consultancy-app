"""The consultant's routes: client organisations, their first admins, and the website's pilot requests."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB
from . import db as M
from .deps import Ctx, need
from .routes_admin import NewUser, create_user, slugify, user_out

router = APIRouter(prefix="/api/super")


def org_out(db, o: M.Org):
    n_users = db.scalar(select(func.count()).select_from(M.User).where(M.User.org_id == o.id))
    n_open = db.scalar(select(func.count()).select_from(M.AlertCase).where(M.AlertCase.org_id == o.id, M.AlertCase.status.in_(("new", "investigating"))))
    return {"id": o.id, "name": o.name, "slug": o.slug, "active": o.active, "created_at": o.created_at, "users": n_users, "open_alerts": n_open,
            "retention_days": o.retention_days}


@router.get("/orgs")
def orgs(ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    return [org_out(db, o) for o in db.scalars(select(M.Org).order_by(M.Org.name))]


class NewOrg(BaseModel):
    name: str = Field(min_length=2, max_length=200)


def create_org(db, name, actor=None):
    base = slugify(name); slug, i = base, 2
    while db.scalar(select(M.Org).where(M.Org.slug == slug)): slug = f"{base}-{i}"; i += 1
    o = M.Org(name=name.strip(), slug=slug); db.add(o); db.flush(); M.audit(db, "org.created", actor, o.id, o.name); db.commit()
    return o


@router.post("/orgs")
def add_org(body: NewOrg, ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    return org_out(db, create_org(db, body.name, ctx.user))


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    active: bool | None = None


@router.patch("/orgs/{oid}")
def edit_org(oid: int, body: OrgPatch, ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    o = db.get(M.Org, oid)
    if o is None: raise HTTPException(404, "no such organisation")
    if body.name is not None: o.name = body.name.strip()
    if body.active is not None: o.active = body.active
    M.audit(db, "org.updated", ctx.user, o.id, f"name={o.name}, active={o.active}"); db.commit()
    from .connectors import manager                  # a disabled client's mailboxes stop being read at once
    if o.active: manager.start_all(o.id)
    else: manager.stop_org(o.id)
    return org_out(db, o)


@router.get("/orgs/{oid}/users")
def org_users(oid: int, ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    if db.get(M.Org, oid) is None: raise HTTPException(404, "no such organisation")
    return [user_out(u) for u in db.scalars(select(M.User).where(M.User.org_id == oid).order_by(M.User.email))]


@router.post("/orgs/{oid}/users")
def add_org_user(oid: int, body: NewUser, ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    if db.get(M.Org, oid) is None: raise HTTPException(404, "no such organisation")
    return user_out(create_user(db, oid, body, ctx.user))


@router.get("/leads")
def leads(ctx: Ctx = Depends(need("superadmin", org=False)), db: DB = Depends(M.get_db)):
    return [{"id": l.id, "name": l.name, "email": l.email, "organisation": l.organisation, "message": l.message, "at": l.created_at}
            for l in db.scalars(select(M.Lead).order_by(M.Lead.created_at.desc()).limit(500))]
