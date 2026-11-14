"""The live side of the web app: a Server-Sent Events stream of what happens in the organisation (new messages, new alerts, triage changes,
connector states), the recent messages for the live feed, and the state of every message source.
  GET /api/live/stream    text/event-stream; events: hello, message, alert, alert_update, connector, hook, resync, end
  GET /api/live/recent    the latest messages recorded (never their text)
  GET /api/live/sources   connectors, API keys and the alert webhook, with their last activity
The stream checks the session every 30 s and ends when the person signs out, loses access, or the organisation is disabled."""
import asyncio, json, time
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB
from starlette.concurrency import run_in_threadpool
from . import db as M
from .connectors import brief
from .deps import Ctx, need, session_ctx
from .live import bus
from .services import message_out

router = APIRouter(prefix="/api/live")
KEEPALIVE_S = 15
RECHECK_S = 30


def _auth(request: Request):
    db = M.session()
    try:
        ctx = session_ctx(request, db)
        if ctx.org is None: raise HTTPException(409, "choose an organisation first")
        return ctx.session.token_hash, ctx.org.id
    finally:
        db.close()


def _still_allowed(token_hash: str, org_id: int) -> bool:
    db = M.session()
    try:
        s = db.scalar(select(M.AuthSession).where(M.AuthSession.token_hash == token_hash))
        if s is None or s.expires_at < M.now(): return False
        u = db.get(M.User, s.user_id)
        if u is None or not u.active or (s.active_org_id if u.role == "superadmin" else u.org_id) != org_id: return False
        o = db.get(M.Org, org_id)
        return o is not None and o.active
    finally:
        db.close()


def _sse(kind: str, data: dict, eid=None) -> str:
    return (f"id: {eid}\n" if eid else "") + f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/stream")
async def stream(request: Request):
    token_hash, org_id = await run_in_threadpool(_auth, request)

    async def events():
        sub = bus.subscribe(org_id)
        try:
            yield "retry: 3000\n\n"
            yield _sse("hello", {"org_id": org_id, "at": time.time()})
            checked = time.monotonic()
            while True:
                try: msg = await asyncio.wait_for(sub.q.get(), timeout=KEEPALIVE_S)
                except asyncio.TimeoutError: msg = None
                if await request.is_disconnected(): return
                if time.monotonic() - checked > RECHECK_S:
                    checked = time.monotonic()
                    if not await run_in_threadpool(_still_allowed, token_hash, org_id):
                        yield _sse("end", {"reason": "your session ended or your access changed"}); return
                yield ": keep-alive\n\n" if msg is None else _sse(msg["type"], msg["data"], msg["seq"])
        finally:
            bus.unsubscribe(sub)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@router.get("/recent")
def recent(limit: int = Query(default=100, ge=1, le=500), before_id: int | None = Query(default=None, ge=1),
           ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    st = select(M.MessageLog).where(M.MessageLog.org_id == ctx.org.id)
    if before_id: st = st.where(M.MessageLog.id < before_id)
    return [message_out(m) for m in db.scalars(st.order_by(M.MessageLog.id.desc()).limit(limit))]


@router.get("/sources")
def sources(ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    o = ctx.org.id; t = time.time()
    conns = [brief(c) for c in db.scalars(select(M.Connector).where(M.Connector.org_id == o).order_by(M.Connector.id))]
    keys = [{"name": k.name, "prefix": k.prefix, "last_used_at": k.last_used_at}
            for k in db.scalars(select(M.ApiKey).where(M.ApiKey.org_id == o, M.ApiKey.revoked_at.is_(None)).order_by(M.ApiKey.id))]
    h = db.scalar(select(M.AlertHook).where(M.AlertHook.org_id == o))
    last = db.scalar(select(func.max(M.MessageLog.received_at)).where(M.MessageLog.org_id == o))
    n_hour = db.scalar(select(func.count()).select_from(M.MessageLog).where(M.MessageLog.org_id == o, M.MessageLog.received_at >= t - 3600))
    return {"connectors": conns, "api_keys": keys, "alert_webhook": {"active": h.active, "last_status": h.last_status, "last_at": h.last_at} if h else None,
            "last_message_at": last, "messages_last_hour": n_hour, "open_pages": bus.listeners(o)}
