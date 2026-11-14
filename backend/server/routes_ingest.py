"""Routes for connectors (a mail-forwarding script, an SMS gateway, a SIEM), authenticated with an organisation's API key.
  POST /api/v1/events   {"recipient": "...", "events": [{"channel","text","subject","identity","time"}, ...]}
  POST /api/v1/scan     {"channel": "email|sms|url", "text": "...", "subject": "..."}
  GET  /api/v1/alerts?status=new&since=<epoch seconds>"""
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from . import db as M, engine
from .deps import Ctx, api_key_ctx
from .services import EventsIn, ScanIn, log_scan, record_events

router = APIRouter(prefix="/api/v1")


@router.post("/events")
def ingest_events(body: EventsIn, ctx: Ctx = Depends(api_key_ctx), db: DB = Depends(M.get_db)):
    return record_events(db, ctx, body, "api")


@router.post("/scan")
def ingest_scan(body: ScanIn, ctx: Ctx = Depends(api_key_ctx), db: DB = Depends(M.get_db)):
    r = engine.score(body.channel.lower(), body.text, body.subject or "")
    log_scan(db, ctx, "scan", r["channel"], 1, r["score"], r["score"] >= engine.ALERT_LINE); db.commit()
    return {**r, "alert_line": engine.ALERT_LINE, "alert": r["score"] >= engine.ALERT_LINE}


@router.get("/alerts")
def ingest_alerts(status: list[str] = Query(default=["new"]), since: float = Query(default=0, ge=0), ctx: Ctx = Depends(api_key_ctx), db: DB = Depends(M.get_db)):
    st = select(M.AlertCase).where(M.AlertCase.org_id == ctx.org.id, M.AlertCase.created_at >= since, M.AlertCase.status.in_(status)).order_by(M.AlertCase.id).limit(500)
    return [{"case_id": c.id, "raised_at": c.created_at, "recipient": c.recipient_label or f"recipient {c.recipient_ref}", "risk": round(c.risk, 3), "status": c.status,
             "channels": [x for x in c.channels.split(",") if x], "indicators": json.loads(c.indicators or "[]"), "reason": c.reason} for c in db.scalars(st)]
