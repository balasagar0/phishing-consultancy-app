"""Work shared by the signed-in routes and the API-key routes: request shapes, recording events with their alert cases, and the retention purge."""
import hashlib, hmac, json, time
from collections import Counter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from . import db as M, engine
from .deps import Ctx

MAX_TEXT = 100_000


class EventIn(BaseModel):
    channel: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    subject: str | None = Field(default="", max_length=2000)
    identity: str | None = Field(default="", max_length=320)
    time: str | float | int | None = None

    @field_validator("time")
    @classmethod
    def _t(cls, v): return None if v in (None, "") else str(v)[:40]

    def engine_dict(self): return {"channel": self.channel.lower(), "text": self.text, "subject": self.subject or "", "identity": self.identity or "", "time": self.time}


class ScanIn(BaseModel):
    channel: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    subject: str | None = Field(default="", max_length=2000)


class CorrelateIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=20)
    window_minutes: float | None = Field(default=None, gt=0, le=10080)


class EventsIn(BaseModel):
    recipient: str = Field(min_length=1, max_length=320)
    events: list[EventIn] = Field(min_length=1, max_length=20)


def log_scan(db, ctx, kind, channel="", n=1, score=None, alert=None):
    db.add(M.ScanLog(org_id=ctx.org.id, user_id=ctx.user.id if ctx.user else None, api_key_id=ctx.api_key.id if ctx.api_key else None,
                     kind=kind, channel=channel, n_events=n, score=score, alert=alert))


def log_bundle(db, ctx, kind, channels, score=None, alert=None):
    """A request with several messages: one row per channel with that channel's count, so per-channel totals add up."""
    for ch, n in sorted(Counter(channels).items()): log_scan(db, ctx, kind, ch, n, score, alert)


def _hide(tokens, keep):
    return list(tokens) if keep else [t.split(":")[0] + ":(hidden)" for t in tokens]


def message_out(m: M.MessageLog) -> dict:
    return {"id": m.id, "at": m.at, "received_at": m.received_at, "channel": m.channel, "source": m.source, "origin": m.origin,
            "recipient": m.recipient_label or f"recipient {m.recipient_ref}", "score": None if m.score is None else round(m.score, 3), "label": m.label,
            "assessed": m.assessed, "campaign_id": m.campaign_id, "campaign_risk": None if m.campaign_risk is None else round(m.campaign_risk, 3),
            "indicators": json.loads(m.indicators or "[]")}


def alert_brief(c: M.AlertCase) -> dict:
    return {"case_id": c.id, "risk": round(c.risk, 3), "channels": [x for x in c.channels.split(",") if x], "recipient": c.recipient_label or f"recipient {c.recipient_ref}",
            "indicators": json.loads(c.indicators or "[]"), "campaign_id": c.campaign_id, "source": c.source, "status": c.status, "created_at": c.created_at}


def record_events(db, ctx, body: EventsIn, source: str, *, audit: bool = True, origin: str = ""):
    """Stores the events in the organisation's event store, opens one alert case per new engine alert, keeps a feed row per message (never its
    text), then tells every open page (live.py) and the organisation's alert webhook (hooks_out.py). Connectors pass audit=False: a busy
    mailbox would bury the people's actions in the audit log; their counts are on the connector instead."""
    from . import hooks_out
    from .live import bus
    org = ctx.org; rec = body.recipient.strip(); keep = org.keep_labels
    r = engine.add_events(org, rec, [e.engine_dict() for e in body.events])
    cases, rows = [], []
    for a in r["new_alerts"]:
        case = M.AlertCase(org_id=org.id, engine_alert_id=a["id"], campaign_id=a["campaign_id"], recipient_label=rec if keep else "",
                           recipient_ref=r["recipient_ref"], risk=float(a["risk"]), reason=a["reason"], channels=",".join(a["channels"]),
                           indicators=json.dumps(_hide(a["shared_identity_tokens"], keep)), source=source)
        db.add(case); db.flush(); a["case_id"] = case.id; cases.append(case)
    camp_of = {eid: c for c in r["campaigns"] for eid in c["event_ids"]}; now = time.time()
    for o in r["events"]:
        c = camp_of.get(o.get("event_id")); t = o["t_minutes"] * 60.0
        m = M.MessageLog(org_id=org.id, at=t if t > 6e7 else now, received_at=now, channel=o["channel"], source=source, origin=origin[:200],
                         recipient_label=rec if keep else "", recipient_ref=r["recipient_ref"], score=o["score"], label=str(o["label"])[:40],
                         assessed=bool(o["assessed"]), event_id=o.get("event_id"), campaign_id=c["id"] if c else None,
                         campaign_risk=c["risk"] if c else None, indicators=json.dumps(_hide(o["identity_tokens"], keep)))
        db.add(m); rows.append(m)
    log_bundle(db, ctx, "events", [e["channel"] for e in r["events"]], r["highest_campaign_risk"], bool(r["new_alerts"]))
    if audit: M.audit(db, "events.recorded", ctx.user, org.id, f"{len(r['events'])} event(s) via {source}; {len(r['new_alerts'])} new alert(s)")
    db.commit()
    for m in rows: bus.publish(org.id, "message", **message_out(m))
    for c in cases:
        bus.publish(org.id, "alert", **alert_brief(c)); hooks_out.enqueue(org.id, c.id)
    return r


def record_mail(org_id: int, raw: bytes, *, mode: str, mailbox: str = "", received_at: float | None = None, source: str, origin: str = "") -> dict:
    """One email from a mailbox connector or the email webhook. Returns {"status": recorded | duplicate | empty | too_large, ...}."""
    from . import mailparse
    if len(raw) > mailparse.MAX_RAW: return {"status": "too_large"}
    p = mailparse.parse(raw, mode, mailbox, received_at)
    if p is None: return {"status": "empty"}
    db = M.session()
    try:
        org = db.get(M.Org, org_id)
        if org is None or not org.active: return {"status": "org_disabled"}
        key = hmac.new(engine.org_key(org.id), f"{p['message_id']}|{p['recipient']}".encode(), hashlib.sha256).hexdigest()
        if db.scalar(select(M.SeenMessage.id).where(M.SeenMessage.org_id == org.id, M.SeenMessage.key == key)): return {"status": "duplicate"}
        db.add(M.SeenMessage(org_id=org.id, key=key))
        events = [e for e in p["events"] if e["channel"] != "url" or engine.url_ok(e["text"])]
        r = record_events(db, Ctx(user=None, org=org), EventsIn(recipient=p["recipient"], events=events), source, audit=False, origin=origin)
        return {"status": "recorded", "events": len(r["events"]), "alerts": len(r["new_alerts"]), "recipient_ref": r["recipient_ref"],
                "new_alerts": [{"case_id": a["case_id"], "risk": round(a["risk"], 3)} for a in r["new_alerts"]]}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def purge_org(db, org, older_than_days=None):
    """Retention: the engine deletes old events, alerts and campaigns; the app deletes alert cases, notes and scan rows of the same age."""
    days = float(org.retention_days if older_than_days is None else older_than_days)
    res = engine.store(org).purge(days); cut = time.time() - days * 86400
    old = [c for c in db.scalars(select(M.AlertCase.id).where(M.AlertCase.org_id == org.id, M.AlertCase.created_at < cut))]
    if old: db.execute(delete(M.AlertNote).where(M.AlertNote.case_id.in_(old)))
    n_cases = db.execute(delete(M.AlertCase).where(M.AlertCase.org_id == org.id, M.AlertCase.created_at < cut)).rowcount
    n_scans = db.execute(delete(M.ScanLog).where(M.ScanLog.org_id == org.id, M.ScanLog.created_at < cut)).rowcount
    n_feed = db.execute(delete(M.MessageLog).where(M.MessageLog.org_id == org.id, M.MessageLog.received_at < cut)).rowcount
    db.execute(delete(M.SeenMessage).where(M.SeenMessage.org_id == org.id, M.SeenMessage.created_at < cut))
    M.audit(db, "retention.purge", None, org.id, f"older than {days:g} days: {res['events_deleted']} events, {n_cases} alert cases, {n_scans} scan rows, "
                                                 f"{n_feed} feed rows")
    db.commit()
    return {**res, "alert_cases_deleted": n_cases, "scan_rows_deleted": n_scans, "feed_rows_deleted": n_feed, "older_than_days": days}
