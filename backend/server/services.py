"""Work shared by the signed-in routes and the API-key routes: request shapes, recording events with their alert cases, and the retention purge."""
import json, time
from collections import Counter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from . import db as M, engine

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


def record_events(db, ctx, body: EventsIn, source: str):
    """Stores the events in the organisation's event store and opens one alert case per new engine alert."""
    org = ctx.org; r = engine.add_events(org, body.recipient.strip(), [e.engine_dict() for e in body.events])
    for a in r["new_alerts"]:
        case = M.AlertCase(org_id=org.id, engine_alert_id=a["id"], campaign_id=a["campaign_id"], recipient_label=body.recipient.strip() if org.keep_labels else "",
                           recipient_ref=r["recipient_ref"], risk=float(a["risk"]), reason=a["reason"], channels=",".join(a["channels"]),
                           indicators=json.dumps(a["shared_identity_tokens"] if org.keep_labels else [t.split(":")[0] + ":(hidden)" for t in a["shared_identity_tokens"]]),
                           source=source)
        db.add(case); db.flush(); a["case_id"] = case.id
    log_bundle(db, ctx, "events", [e["channel"] for e in r["events"]], r["highest_campaign_risk"], bool(r["new_alerts"]))
    M.audit(db, "events.recorded", ctx.user, org.id, f"{len(r['events'])} event(s) via {source}; {len(r['new_alerts'])} new alert(s)")
    db.commit()
    return r


def purge_org(db, org, older_than_days=None):
    """Retention: the engine deletes old events, alerts and campaigns; the app deletes alert cases, notes and scan rows of the same age."""
    days = float(org.retention_days if older_than_days is None else older_than_days)
    res = engine.store(org).purge(days); cut = time.time() - days * 86400
    old = [c for c in db.scalars(select(M.AlertCase.id).where(M.AlertCase.org_id == org.id, M.AlertCase.created_at < cut))]
    if old: db.execute(delete(M.AlertNote).where(M.AlertNote.case_id.in_(old)))
    n_cases = db.execute(delete(M.AlertCase).where(M.AlertCase.org_id == org.id, M.AlertCase.created_at < cut)).rowcount
    n_scans = db.execute(delete(M.ScanLog).where(M.ScanLog.org_id == org.id, M.ScanLog.created_at < cut)).rowcount
    M.audit(db, "retention.purge", None, org.id, f"older than {days:g} days: {res['events_deleted']} events, {n_cases} alert cases, {n_scans} scan rows")
    db.commit()
    return {**res, "alert_cases_deleted": n_cases, "scan_rows_deleted": n_scans, "older_than_days": days}
