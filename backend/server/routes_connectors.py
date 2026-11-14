"""An organisation admin's message sources: mailbox connectors the server reads by itself (connectors.py), and the alert webhook that tells
another system when an alert opens (hooks_out.py). Secrets are write-only: the API says whether one is set, never what it is."""
import json, time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from . import db as M, hooks_out
from .connectors import aad, manager, public, test_connection
from .deps import Ctx, need
from .secretbox import seal, unseal
from .security import EMAIL, limiter, vet_host, vet_url

router = APIRouter(prefix="/api/admin")


class ImapCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=993, ge=1, le=65535)
    security: Literal["ssl", "starttls", "none"] = "ssl"
    username: str = Field(min_length=1, max_length=320)
    folder: str = Field(default="INBOX", min_length=1, max_length=200, pattern=r"^[\x20-\x7e]+$")
    mode: Literal["reports", "inbox"] = "reports"
    mailbox_address: str = Field(default="", max_length=320)
    poll_seconds: int = Field(default=30, ge=10, le=3600)
    use_idle: bool = True
    backfill: int = Field(default=0, ge=0, le=50)


class GraphCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(pattern=r"^[A-Za-z0-9.-]{1,100}$")
    client_id: str = Field(pattern=r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
    mailbox: str = Field(min_length=3, max_length=320)
    folder: str = Field(default="inbox", pattern=r"^[A-Za-z0-9=_-]{1,300}$")
    mode: Literal["reports", "inbox"] = "reports"
    poll_seconds: int = Field(default=30, ge=15, le=3600)
    backfill: int = Field(default=0, ge=0, le=50)


CFG = {"imap": ImapCfg, "graph": GraphCfg}
WHERE = {"imap": ("host", "port", "username", "folder"), "graph": ("tenant_id", "client_id", "mailbox", "folder")}   # a change here starts afresh


def clean_config(kind: str, d: dict) -> dict:
    if kind not in CFG: raise HTTPException(422, "kind must be imap or graph")
    try: cfg = CFG[kind](**(d or {})).model_dump()
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()))
    if kind == "imap":
        cfg["host"] = cfg["host"].strip().lower()
        try: vet_host(cfg["host"], cfg["port"])
        except ValueError as e: raise HTTPException(422, str(e))
        if cfg["mode"] == "inbox" and not cfg["mailbox_address"]:
            if not EMAIL.match(cfg["username"]): raise HTTPException(422, "watching an inbox: give the mailbox's email address (its owner is the recipient)")
            cfg["mailbox_address"] = cfg["username"]
        cfg["mailbox_address"] = cfg["mailbox_address"].strip().lower()
    else:
        if not EMAIL.match(cfg["mailbox"]): raise HTTPException(422, "mailbox: give the mailbox's email address")
        cfg["mailbox"] = cfg["mailbox"].strip().lower()
    return cfg


class ConnectorIn(BaseModel):
    kind: Literal["imap", "graph"]
    name: str = Field(min_length=1, max_length=200)
    config: dict
    secret: str = Field(default="", max_length=2000)


class ConnectorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict | None = None
    secret: str | None = Field(default=None, max_length=2000)
    active: bool | None = None


class TestIn(BaseModel):
    kind: Literal["imap", "graph"]
    config: dict
    secret: str = Field(default="", max_length=2000)
    id: int | None = None


def _get(db, ctx, cid) -> M.Connector:
    c = db.get(M.Connector, cid)
    if c is None or c.org_id != ctx.org.id: raise HTTPException(404, "no such connector in this organisation")
    return c


@router.get("/connectors")
def list_connectors(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    return [public(c) for c in db.scalars(select(M.Connector).where(M.Connector.org_id == ctx.org.id).order_by(M.Connector.id))]


@router.post("/connectors")
def add_connector(body: ConnectorIn, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    cfg = clean_config(body.kind, body.config)
    if not body.secret: raise HTTPException(422, "give the password or client secret")
    c = M.Connector(org_id=ctx.org.id, kind=body.kind, name=body.name.strip(), config=json.dumps(cfg), secret=seal(body.secret, aad(ctx.org.id, body.kind)),
                    status="new", detail="starting", created_by=ctx.user.id)
    db.add(c); db.flush(); M.audit(db, "connector.created", ctx.user, ctx.org.id, f"{c.name} ({c.kind}, {cfg['mode']})"); db.commit()
    manager.start(c.id)
    return public(c)


@router.patch("/connectors/{cid}")
def edit_connector(cid: int, body: ConnectorPatch, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    c = _get(db, ctx, cid); ch = []
    if c.kind == "demo" and (body.config is not None or body.secret):
        raise HTTPException(422, "the demo replay can only be played or paused")
    if body.name is not None: c.name = body.name.strip(); ch.append("name")
    if body.config is not None:
        old = json.loads(c.config or "{}"); cfg = clean_config(c.kind, body.config)
        if any(old.get(k) != cfg.get(k) for k in WHERE[c.kind]): c.state = "{}"; ch.append("mailbox changed: reading starts afresh")
        c.config = json.dumps(cfg); ch.append("settings")
    if body.secret: c.secret = seal(body.secret, aad(ctx.org.id, c.kind)); ch.append("secret replaced")
    if body.active is not None and body.active != c.active:
        c.active = body.active; ch.append("resumed" if body.active else "paused")
        if not body.active: c.status, c.detail = "paused", f"paused by {ctx.user.email}"
        else: c.status, c.detail = "new", "starting"
    c.updated_at = time.time(); M.audit(db, "connector.updated", ctx.user, ctx.org.id, f"{c.name}: " + (", ".join(ch) or "no change")); db.commit()
    manager.stop(c.id)
    if c.active: manager.start(c.id)
    from .live import bus
    from .connectors import brief
    bus.publish(ctx.org.id, "connector", **brief(c))
    return public(c)


@router.delete("/connectors/{cid}")
def delete_connector(cid: int, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    c = _get(db, ctx, cid); manager.stop(c.id)
    M.audit(db, "connector.deleted", ctx.user, ctx.org.id, f"{c.name} ({c.kind})"); db.delete(c); db.commit()
    return {"deleted": cid}


@router.post("/connectors/{cid}/check")
def check_now(cid: int, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    c = _get(db, ctx, cid)
    if not c.active: raise HTTPException(409, "the connector is paused: resume it first")
    if not manager.wake(c.id): manager.start(c.id)
    return public(c)


@router.post("/connectors/test")
def test_connector(body: TestIn, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    if not limiter.allow(f"conntest:{ctx.user.id}", 10, 60): raise HTTPException(429, "at most 10 tests a minute")
    cfg = clean_config(body.kind, body.config); secret = body.secret
    if not secret and body.id is not None:
        c = _get(db, ctx, body.id)
        if c.kind != body.kind: raise HTTPException(422, "the kind does not match the saved connector")
        secret = unseal(c.secret, aad(ctx.org.id, c.kind))
    if not secret: raise HTTPException(422, "give the password or client secret")
    return test_connection(body.kind, cfg, secret)


# ---------------------------------------------------------------- alert webhook

class HookIn(BaseModel):
    url: str = Field(min_length=8, max_length=1000)
    secret: str | None = Field(default=None, max_length=500)
    active: bool = True


def hook_out(h: M.AlertHook | None):
    if h is None: return None
    return {"url": h.url, "active": h.active, "has_secret": bool(h.secret), "last_status": h.last_status, "last_at": h.last_at, "n_sent": h.n_sent, "n_failed": h.n_failed}


@router.get("/alert-webhook")
def get_hook(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    return hook_out(db.scalar(select(M.AlertHook).where(M.AlertHook.org_id == ctx.org.id)))


@router.put("/alert-webhook")
def put_hook(body: HookIn, ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    try: vet_url(body.url.strip())
    except ValueError as e: raise HTTPException(422, str(e))
    h = db.scalar(select(M.AlertHook).where(M.AlertHook.org_id == ctx.org.id))
    if h is None: h = M.AlertHook(org_id=ctx.org.id, url=body.url.strip()); db.add(h)
    h.url, h.active = body.url.strip(), body.active
    if body.secret is not None: h.secret = hooks_out.seal_secret(ctx.org.id, body.secret) if body.secret else ""
    M.audit(db, "alert_webhook.saved", ctx.user, ctx.org.id, f"{'on' if h.active else 'off'}, signed: {'yes' if h.secret else 'no'}"); db.commit()
    return hook_out(h)


@router.delete("/alert-webhook")
def delete_hook(ctx: Ctx = Depends(need("admin")), db: DB = Depends(M.get_db)):
    h = db.scalar(select(M.AlertHook).where(M.AlertHook.org_id == ctx.org.id))
    if h is not None: db.delete(h); M.audit(db, "alert_webhook.deleted", ctx.user, ctx.org.id); db.commit()
    return None


@router.post("/alert-webhook/test")
def test_hook(ctx: Ctx = Depends(need("admin"))):
    if not limiter.allow(f"hooktest:{ctx.user.id}", 10, 60): raise HTTPException(429, "at most 10 tests a minute")
    ok, line = hooks_out.deliver(ctx.org.id, None, test=True, retry=False)
    return {"ok": ok, "detail": line}
