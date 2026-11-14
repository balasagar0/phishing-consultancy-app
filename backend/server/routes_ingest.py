"""Routes for systems that send messages in or pull alerts out, authenticated with an organisation's API key.
  POST /api/v1/events        {"recipient": "...", "events": [{"channel","text","subject","identity","time"}, ...]}
  POST /api/v1/scan          {"channel": "email|sms|url", "text": "...", "subject": "..."}
  GET  /api/v1/alerts?status=new&since=<epoch seconds>
Webhooks, one message per request, sent as it arrives (real time):
  POST /api/v1/hooks/sms     an SMS gateway or a phone forwarding app. JSON {"from", "to" or "recipient", "text", "time"}, or a form as Twilio
                             sends it (From, To, Body; answered with an empty TwiML reply). The key may come as HTTP Basic's password.
                             ?mode=reports: a "report smishing" number staff forward SMS to; the person who forwarded it is the recipient.
  POST /api/v1/hooks/email   one raw email (MIME, up to 10 MB) from a mail server, a mail-flow rule or an inbound-mail service.
                             ?recipient=<address> checks it as delivered to that person; without it, it is read as a staff report."""
import json, re, time
from typing import Literal
from urllib.parse import parse_qs
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DB
from starlette.concurrency import run_in_threadpool
from . import db as M, engine
from .deps import Ctx, api_key_ctx, hook_key_ctx
from .mailparse import links
from .services import MAX_TEXT, EventsIn, ScanIn, log_scan, record_events, record_mail

router = APIRouter(prefix="/api/v1")
TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@router.post("/events")
def ingest_events(body: EventsIn, ctx: Ctx = Depends(api_key_ctx), db: DB = Depends(M.get_db)):
    return record_events(db, ctx, body, "api", origin=ctx.api_key.name)


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


# ---------------------------------------------------------------- webhooks

def _first(d: dict, names):
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower())
        if v not in (None, ""): return v
    return None


def _when(v) -> str | None:
    """A gateway's time: epoch seconds or milliseconds, or an ISO timestamp. None (the server's clock) for anything else."""
    if v is None: return None
    try: x = float(v)
    except (TypeError, ValueError):
        return str(v)[:40] if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", str(v)) else None
    if x > 1e12: x /= 1000.0
    return str(x / 60.0) if 1e9 < x < time.time() + 86400 else None


def sms_body(d: dict, recipient: str, mode: str = "inbox") -> EventsIn:
    """'inbox': the SMS as a person received it (from = the sender, to = the person). 'reports': staff forward suspicious SMS to a reporting
    number; the person who forwarded it (from) is the recipient, and the original sender is unknown unless the text names it."""
    text = _first(d, ("text", "body", "message", "msg", "content", "sms"))
    sender = _first(d, ("from", "sender", "originator", "phone", "number", "msisdn"))
    rec = recipient or _first(d, ("recipient", "to", "receiver"))
    if mode == "reports": rec, sender = recipient or sender, ""
    if not text or not str(text).strip(): raise HTTPException(422, "no message text: send it as 'text' (or Body, message)")
    if not rec or not str(rec).strip(): raise HTTPException(422, "say who received the SMS: 'recipient' or 'to', or ?recipient= in the address")
    t = _when(_first(d, ("time", "received_at", "timestamp", "sent_at", "date", "receivedstamp", "sentstamp")))
    text = str(text)[:MAX_TEXT]
    ev = [{"channel": "sms", "text": text, "identity": str(sender or "")[:320], "time": t}]
    ev += [{"channel": "url", "text": u[:2000], "time": t} for u in links(text, 3) if engine.url_ok(u)]
    return EventsIn(recipient=str(rec).strip()[:320], events=ev)


@router.post("/hooks/sms")
async def hook_sms(request: Request, recipient: str = Query(default="", max_length=320), mode: Literal["inbox", "reports"] = "inbox",
                   ctx: Ctx = Depends(hook_key_ctx), db: DB = Depends(M.get_db)):
    raw = await request.body(); ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ct == "application/json":
        try: d = json.loads(raw or b"{}")
        except ValueError: raise HTTPException(422, "the body is not valid JSON")
        if not isinstance(d, dict): raise HTTPException(422, "send one JSON object per SMS")
    elif ct == "application/x-www-form-urlencoded":
        d = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
    else:
        raise HTTPException(415, "send JSON (application/json) or a form (application/x-www-form-urlencoded)")
    body = sms_body(d, recipient.strip(), mode)
    r = await run_in_threadpool(record_events, db, ctx, body, "sms-hook", audit=False, origin=ctx.api_key.name)
    if ct != "application/json": return Response(TWIML_EMPTY, media_type="application/xml")
    return {"status": r["status"], "recipient_ref": r["recipient_ref"], "events": [{"channel": e["channel"], "score": e["score"], "label": e["label"]} for e in r["events"]],
            "new_alerts": [{"case_id": a["case_id"], "risk": round(a["risk"], 3)} for a in r["new_alerts"]]}


@router.post("/hooks/email")
async def hook_email(request: Request, recipient: str = Query(default="", max_length=320), mode: Literal["reports", "inbox"] | None = None,
                     ctx: Ctx = Depends(hook_key_ctx)):
    raw = await request.body()
    if not raw.strip(): raise HTTPException(422, "send the raw email (MIME) as the request body")
    m = mode or ("inbox" if recipient.strip() else "reports")
    if m == "inbox" and not recipient.strip(): raise HTTPException(422, "inbox mode needs ?recipient=<the address it was delivered to>")
    res = await run_in_threadpool(record_mail, ctx.org.id, raw, mode=m, mailbox=recipient.strip().lower(), source="mail-hook", origin=ctx.api_key.name)
    if res["status"] == "too_large": raise HTTPException(413, "the email is larger than 10 MB")
    if res["status"] == "empty": raise HTTPException(422, "the email has no recipient or no text to check")
    return res
