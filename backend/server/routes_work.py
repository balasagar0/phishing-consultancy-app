"""The analyst's work inside one organisation: scan a message, investigate a bundle, record events, triage alerts, dashboard and reports."""
import csv, io, json, time
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DB
from . import db as M, engine
from .deps import Ctx, need
from .security import csv_safe
from .services import CorrelateIn, EventsIn, ScanIn, log_bundle, log_scan, record_events

router = APIRouter(prefix="/api")
OPEN = ("new", "investigating")


@router.get("/presets")
def presets(ctx: Ctx = Depends(need("viewer"))):
    return engine.presets()


@router.post("/scan")
def scan(body: ScanIn, ctx: Ctx = Depends(need("analyst")), db: DB = Depends(M.get_db)):
    r = engine.score(body.channel.lower(), body.text, body.subject or "")
    log_scan(db, ctx, "scan", r["channel"], 1, r["score"], r["score"] >= engine.ALERT_LINE); db.commit()
    return {**r, "alert_line": engine.ALERT_LINE, "alert": r["score"] >= engine.ALERT_LINE}


@router.post("/correlate")
def correlate(body: CorrelateIn, ctx: Ctx = Depends(need("analyst")), db: DB = Depends(M.get_db)):
    r = engine.correlate([e.engine_dict() for e in body.events], body.window_minutes)
    br = r.get("bundle_risk")
    log_bundle(db, ctx, "correlate", [e["channel"] for e in r["events"]], br, None if br is None else br >= engine.ALERT_LINE)
    db.commit()
    return r


@router.post("/events")
def events(body: EventsIn, ctx: Ctx = Depends(need("analyst")), db: DB = Depends(M.get_db)):
    return record_events(db, ctx, body, "web")


@router.get("/campaigns")
def campaigns(include_inactive: bool = False, ctx: Ctx = Depends(need("viewer"))):
    return engine.store(ctx.org).campaigns(None, active_only=not include_inactive)


@router.get("/campaigns/{cid}")
def campaign(cid: int, ctx: Ctx = Depends(need("viewer"))):
    c = engine.store(ctx.org).campaign(cid)
    if c is None: raise HTTPException(404, "no such campaign in this organisation")
    return c


def _users(db, org_id):
    return {u.id: u for u in db.scalars(select(M.User).where(M.User.org_id == org_id))}


def case_out(c: M.AlertCase, users):
    a = users.get(c.assignee_id)
    return {"id": c.id, "engine_alert_id": c.engine_alert_id, "campaign_id": c.campaign_id, "recipient": c.recipient_label or f"recipient {c.recipient_ref}",
            "recipient_ref": c.recipient_ref, "risk": round(c.risk, 3), "reason": c.reason, "indicators": json.loads(c.indicators or "[]"),
            "channels": [x for x in c.channels.split(",") if x], "status": c.status, "assignee": {"id": a.id, "name": a.name or a.email} if a else None,
            "source": c.source, "created_at": c.created_at, "updated_at": c.updated_at}


@router.get("/alerts")
def alerts(status: list[str] = Query(default=[]), days: int = Query(default=90, ge=1, le=3650), q: str = Query(default="", max_length=200),
           ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    st = select(M.AlertCase).where(M.AlertCase.org_id == ctx.org.id, M.AlertCase.created_at >= time.time() - days * 86400)
    if status: st = st.where(M.AlertCase.status.in_([s for s in status if s in M.CASE_STATUSES]))
    if q.strip(): st = st.where((M.AlertCase.recipient_label.ilike(f"%{q.strip()}%")) | (M.AlertCase.indicators.ilike(f"%{q.strip()}%")))
    users = _users(db, ctx.org.id)
    return [case_out(c, users) for c in db.scalars(st.order_by(M.AlertCase.created_at.desc()).limit(500))]


def _case(db, ctx, cid) -> M.AlertCase:
    c = db.get(M.AlertCase, cid)
    if c is None or c.org_id != ctx.org.id: raise HTTPException(404, "no such alert in this organisation")
    return c


@router.get("/alerts/{cid}")
def alert(cid: int, ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    c = _case(db, ctx, cid); users = _users(db, ctx.org.id)
    notes = [{"id": n.id, "text": n.text, "by": (users[n.user_id].name or users[n.user_id].email) if n.user_id in users else "a former user", "at": n.created_at}
             for n in db.scalars(select(M.AlertNote).where(M.AlertNote.case_id == c.id).order_by(M.AlertNote.created_at))]
    return {**case_out(c, users), "notes": notes, "campaign": engine.store(ctx.org).campaign(c.campaign_id)}


class CasePatch(BaseModel):
    status: str | None = None
    assignee_id: int | None = Field(default=None)
    unassign: bool = False


@router.patch("/alerts/{cid}")
def update_alert(cid: int, body: CasePatch, ctx: Ctx = Depends(need("analyst")), db: DB = Depends(M.get_db)):
    c = _case(db, ctx, cid); changes = []
    if body.status is not None:
        if body.status not in M.CASE_STATUSES: raise HTTPException(422, f"status must be one of {', '.join(M.CASE_STATUSES)}")
        changes.append(f"status {c.status} -> {body.status}"); c.status = body.status
        if body.status not in OPEN: engine.store(ctx.org).ack(c.engine_alert_id)
    if body.unassign: c.assignee_id = None; changes.append("unassigned")
    elif body.assignee_id is not None:
        u = db.get(M.User, body.assignee_id)
        if u is None or u.org_id != ctx.org.id or not u.active or M.RANK[u.role] < M.RANK["analyst"]:
            raise HTTPException(422, "assign the alert to an active analyst or admin of this organisation")
        c.assignee_id = u.id; changes.append(f"assigned to {u.email}")
    c.updated_at = M.now(); M.audit(db, "alert.updated", ctx.user, ctx.org.id, f"alert case {c.id}: " + "; ".join(changes)); db.commit()
    return case_out(c, _users(db, ctx.org.id))


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/alerts/{cid}/notes")
def add_note(cid: int, body: NoteIn, ctx: Ctx = Depends(need("analyst")), db: DB = Depends(M.get_db)):
    c = _case(db, ctx, cid); n = M.AlertNote(case_id=c.id, user_id=ctx.user.id, text=body.text.strip()); db.add(n)
    c.updated_at = M.now(); M.audit(db, "alert.note", ctx.user, ctx.org.id, f"alert case {c.id}"); db.commit()
    return {"id": n.id, "text": n.text, "by": ctx.user.name or ctx.user.email, "at": n.created_at}


@router.get("/assignees")
def assignees(ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    return [{"id": u.id, "name": u.name or u.email} for u in db.scalars(select(M.User).where(M.User.org_id == ctx.org.id, M.User.active.is_(True)))
            if M.RANK[u.role] >= M.RANK["analyst"]]


def _day(ts): return time.strftime("%Y-%m-%d", time.gmtime(ts))


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    t = time.time(); org = ctx.org
    scans = list(db.scalars(select(M.ScanLog).where(M.ScanLog.org_id == org.id, M.ScanLog.created_at >= t - 30 * 86400)))
    cases = list(db.scalars(select(M.AlertCase).where(M.AlertCase.org_id == org.id, M.AlertCase.created_at >= t - 30 * 86400)))
    days = [_day(t - i * 86400) for i in range(13, -1, -1)]; per_day = Counter(_day(c.created_at) for c in cases)
    chan = Counter()
    for s in scans:
        if s.channel: chan[s.channel] += s.n_events          # one row per channel (log_bundle), so the counts add up
    ind = Counter(i for c in cases for i in json.loads(c.indicators or "[]") if "(hidden)" not in i)
    open_all = db.scalar(select(func.count()).select_from(M.AlertCase).where(M.AlertCase.org_id == org.id, M.AlertCase.status.in_(OPEN)))
    return {"org": org.name, "messages_checked_7d": sum(s.n_events for s in scans if s.created_at >= t - 7 * 86400),
            "messages_checked_30d": sum(s.n_events for s in scans), "alerts_open": open_all, "alerts_30d": len(cases),
            "alerts_by_status_30d": dict(Counter(c.status for c in cases)), "alerts_per_day": [{"day": d, "n": per_day.get(d, 0)} for d in days],
            "messages_by_channel_30d": dict(chan), "top_indicators_30d": ind.most_common(8),
            "active_campaigns": len(engine.store(org).campaigns(None, active_only=True)), "engine": engine.info()}


def _report(db, ctx, days):
    t = time.time(); users = _users(db, ctx.org.id)
    cases = [case_out(c, users) for c in db.scalars(select(M.AlertCase).where(M.AlertCase.org_id == ctx.org.id, M.AlertCase.created_at >= t - days * 86400)
                                                       .order_by(M.AlertCase.created_at))]
    scans = list(db.scalars(select(M.ScanLog).where(M.ScanLog.org_id == ctx.org.id, M.ScanLog.created_at >= t - days * 86400)))
    return cases, scans


@router.get("/reports/summary")
def report_summary(days: int = Query(default=30, ge=1, le=3650), ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    cases, scans = _report(db, ctx, days); card = engine.model_card()
    return {"org": ctx.org.name, "days": days, "generated_at": time.time(), "engine": card["engine"],
            "messages_checked": sum(s.n_events for s in scans), "alerts": len(cases),
            "by_status": dict(Counter(c["status"] for c in cases)), "by_channel": dict(Counter(ch for c in cases for ch in c["channels"])),
            "top_indicators": Counter(i for c in cases for i in c["indicators"] if "(hidden)" not in i).most_common(10),
            "cases": cases, "limitations": card["limitations"], "not_assessed": card["not_assessed"]}


@router.get("/reports/alerts.csv")
def report_csv(days: int = Query(default=30, ge=1, le=3650), ctx: Ctx = Depends(need("viewer")), db: DB = Depends(M.get_db)):
    cases, _ = _report(db, ctx, days); buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["case_id", "raised_utc", "recipient", "risk", "status", "channels", "indicators", "assignee", "source", "reason"])
    for c in cases:
        w.writerow([csv_safe(x) for x in (c["id"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(c["created_at"])), c["recipient"], c["risk"], c["status"],
                                           " ".join(c["channels"]), " ".join(c["indicators"]), (c["assignee"] or {}).get("name", ""), c["source"], c["reason"])])
    M.audit(db, "report.csv", ctx.user, ctx.org.id, f"{len(cases)} alert cases, {days} days"); db.commit()
    name = f"alerts_{ctx.org.slug}_{time.strftime('%Y%m%d')}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})
