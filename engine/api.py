"""Local API for the console:  uvicorn api:app --port 8000
POST /score        {"channel":"email|sms|url","text":"...","subject":"(email only, optional)"}
POST /score/batch  {"items":[{...},{...}]}
POST /correlate    {"events":[{"channel","text","subject","identity","time"},...], "window_minutes": 60}   (window optional; events further apart are not combined or linked)
Calls, voice and video have no detector. /score answers HTTP 501 for them. /correlate accepts them, returns them as "not assessed" and keeps them out of
the bundle risk; when no event can be assessed it answers status CANNOT_ASSESS with no risk, never a low score.
Event store (R2-05): POST /events {"recipient": "...", "events": [...]} stores a recipient's events and groups them into campaigns with the same window and
model as /correlate; GET /campaigns[?recipient=], GET /campaigns/{id}, GET /alerts[?recipient=&include_acked=], POST /alerts/{id}/ack, POST /purge {"older_than_days": 30}."""
import sys, math, os, time, hashlib
from pathlib import Path
from typing import List, Optional
sys.path.insert(0, str(Path(__file__).parent / "src"))
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from predict import Detectors, extract_ids, ModelUnavailable, SCORED, NOT_ASSESSED
from fusion import Fusion
from event_store import EventStore, load_key
from url_features import check_url
from datetime import datetime

CHANNELS = SCORED + NOT_ASSESSED
NOT_BUILT = "no detector for this channel (not built in CP1)"
# CORS for the console's development server only (R2-04, D-06). The built console is served from this app, so it needs no CORS.
# CP1_CORS_ORIGINS="http://host:port,..." replaces the list. Never '*'.
ORIGINS = [o.strip() for o in os.environ.get("CP1_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip() and o.strip() != "*"]

app = FastAPI(title="CP1 per-channel phishing detectors", version="0.3", docs_url=None, redoc_url=None)   # /docs and /redoc load Swagger UI from a CDN; offline demo, so off (the schema stays at /openapi.json)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])
D = Detectors()
_real = Path(__file__).parent / "models" / "fusion_model_real.joblib"   # written by src/refit_fusion.py --save
F = Fusion(_real if _real.exists() else Path(__file__).parent / "models" / "fusion_model.joblib")
ROOT = Path(__file__).parent
MODEL_VERSION = {ch: f"{f}:{hashlib.sha256((ROOT / 'models' / f).read_bytes()).hexdigest()[:12]}" for ch, f in
                 (("email", "email_model.joblib"), ("sms", "sms_model.joblib"), ("url", "url_string_model.joblib")) if D.available(ch)}
_store = None


def store():
    """The event store, opened on first use: CP1_EVENT_DB (default data/events.db), HMAC key from CP1_HMAC_KEY or .cp1_hmac_key."""
    global _store
    if _store is None: _store = EventStore(os.environ.get("CP1_EVENT_DB", str(ROOT / "data" / "events.db")), load_key(), F.model, F.window)
    return _store


class Item(BaseModel):
    channel: str
    text: str = Field(min_length=1)
    subject: Optional[str] = ""


class Event(BaseModel):
    channel: str
    text: str = Field(min_length=1)
    subject: Optional[str] = ""
    identity: Optional[str] = ""          # sender number / address / domain, if known
    time: Optional[str] = None            # ISO timestamp, or minutes as a number string; only differences matter


class Bundle(BaseModel):
    events: List[Event]
    window_minutes: Optional[float] = Field(default=None, gt=0, le=10080)   # None = the model's window (60 minutes unless a refit stored another)


def _minutes(t, i, default=None):
    bad = HTTPException(status_code=422, detail=f"event {i}: 'time' must be a number of minutes or an ISO timestamp, got '{t}'")
    if t in (None, ""): return float(i) if default is None else default
    try: v = float(t)
    except ValueError:
        try: v = datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp() / 60.0
        except ValueError: raise bad
    if not math.isfinite(v): raise bad
    return v


def _check(channel, text, where=""):
    """Refuses an unknown channel or a malformed URL with HTTP 422 and a clear message (R2-06, D-02)."""
    if channel not in CHANNELS: raise HTTPException(status_code=422, detail=f"{where}'channel' must be one of {', '.join(CHANNELS)}, got '{channel}'")
    if channel == "url":
        why = check_url(text)
        if why: raise HTTPException(status_code=422, detail=f"{where}'{text[:80]}' is not a valid URL: {why}")


class Batch(BaseModel):
    items: List[Item]


def _run(it: Item):
    ch = it.channel.lower(); _check(ch, it.text)
    if ch in NOT_ASSESSED: raise HTTPException(status_code=501, detail=f"channel '{ch}' is not assessed: {NOT_BUILT}")
    try:
        return D.score(ch, it.text, it.subject or "")
    except ModelUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok" if not D.unavailable else "degraded", "channels": [c for c in SCORED if D.available(c)], "not_trained": ["voice", "video"],
            "not_assessed_channels": list(NOT_ASSESSED), "not_available": D.unavailable, "fusion_trained_on": F.trained_on, "window_minutes": F.window}


@app.post("/score")
def score(it: Item):
    return _run(it)


@app.post("/score/batch")
def score_batch(b: Batch):
    return [_run(i) for i in b.items]


def _assess(events, default_time=None):
    """Checks and scores every event once; shared by /correlate and /events. Returns (per-event output, assessed events, their indices, not-assessed list)."""
    out, ev, idx, skipped = [], [], [], []
    for i, e in enumerate(events):
        ch = e.channel.lower(); _check(ch, e.text, f"event {i}: ")
        ids = extract_ids(ch, e.text, e.identity or ""); t = _minutes(e.time, i, default_time)
        reason = NOT_BUILT if ch in NOT_ASSESSED else (f"the {ch} model is not loaded: {D.unavailable[ch]}" if not D.available(ch) else None)
        if reason:
            out.append({"channel": ch, "assessed": False, "score": None, "label": "not assessed", "reason": reason, "identity_tokens": ids, "t_minutes": t})
            skipped.append({"index": i, "channel": ch, "reason": reason}); continue
        r = D.score(ch, e.text, e.subject or "")
        out.append({**r, "assessed": True, "identity_tokens": ids, "t_minutes": t}); ev.append({"channel": r["channel"], "score": r["score"], "ids": ids, "t": t}); idx.append(i)
    return out, ev, idx, skipped


@app.post("/correlate")
def correlate(b: Bundle):
    """Scores every event with its channel detector, then scores the bundle with the correlation model.
    Events further apart than the time window are not combined or linked; each window is scored on its own and the bundle takes the highest.
    Events that cannot be assessed (calls, voice, video, or a channel whose model is not loaded) are listed but kept out of the bundle risk."""
    if not b.events: raise HTTPException(status_code=422, detail="no events")
    out, ev, idx, skipped = _assess(b.events)
    if not ev:
        for o in out: o["in_window"] = False
        return {"status": "CANNOT_ASSESS", "events": out, "not_assessed": skipped, "single_channel_alert": None, "bundle_risk": None,
                "bundle_risk_without_correlation": None, "alert_threshold": 0.5, "bundle_label": "cannot assess",
                "reason": "no event in this bundle can be assessed, so no risk is given (this is not a 'safe' verdict)",
                "shared_identity_tokens": [], "window_minutes": F.window if b.window_minutes is None else b.window_minutes,
                "fusion_trained_on": F.trained_on, "note": f"correlation model trained on {F.trained_on}"}
    f = F.risk(ev, b.window_minutes)
    win = [idx[k] for k in f["window_events"]]                      # indices into the request's events
    for i, o in enumerate(out): o["in_window"] = i in win
    cnt = {}
    for k in f["window_events"]:
        for tok in set(ev[k]["ids"]): cnt[tok] = cnt.get(tok, 0) + 1
    ts = [e["t"] for e in ev]; tw = [ev[k]["t"] for k in f["window_events"]]
    return {"status": "ASSESSED", "events": out, "not_assessed": skipped, "single_channel_alert": any(e["score"] >= D.threshold for e in ev), "bundle_risk": f["risk"],
            "bundle_risk_without_correlation": f["risk_without_correlation"], "alert_threshold": 0.5,
            "bundle_label": "elevated risk" if f["risk"] >= 0.5 else "low risk",
            "shared_identity_tokens": sorted(t for t, c in cnt.items() if c >= 2), "time_span_minutes": round(max(ts) - min(ts), 2),
            "window_minutes": f["window_minutes"], "n_windows": f["n_windows"], "window_event_indices": win,
            "window_time_span_minutes": round(max(tw) - min(tw), 2),
            "features": f["features"], "fusion_trained_on": F.trained_on, "note": f"correlation model trained on {F.trained_on}"}


# ---------------------------------------------------------------- event store (R2-05)
class EventsIn(BaseModel):
    recipient: str = Field(min_length=1, max_length=320)       # whose inbox or phone the events arrived on; stored only as an HMAC
    events: List[Event] = Field(min_length=1)


class PurgeIn(BaseModel):
    older_than_days: float = Field(default_factory=lambda: float(os.environ.get("CP1_RETENTION_DAYS", "30")), ge=0)


@app.post("/events")
def add_events(b: EventsIn):
    """Stores one or many events for one recipient and regroups the recipient's campaigns. An event with no 'time' gets the server's clock
    (minutes since 1970). Calls and video are stored and shown in the timeline but never scored."""
    out, ev, idx, skipped = _assess(b.events, default_time=time.time() / 60.0)
    rows = [{"channel": o["channel"], "assessed": o["assessed"], "score": o["score"], "label": o["label"], "ids": o["identity_tokens"], "t": o["t_minutes"],
             "model_version": MODEL_VERSION.get(o["channel"], "none"), "text": e.text, "subject": e.subject} for o, e in zip(out, b.events)]
    S = store(); ids, rh, alerts = S.add(b.recipient, rows)
    plain = {S.htok(t): t for o in out for t in o["identity_tokens"]}              # this request's own tokens, shown in clear in its own answer only
    for a in alerts: a["shared_identity_tokens"] = [plain.get(t, t) for t in a.pop("shared_tokens_h")]
    camps = S.campaigns(b.recipient)
    for o, i in zip(out, ids): o["event_id"] = i
    return {"status": "ASSESSED" if ev else "CANNOT_ASSESS", "recipient": rh[:12], "events": out, "not_assessed": skipped, "campaigns": camps,
            "highest_campaign_risk": max((c["risk"] for c in camps), default=None), "new_alerts": alerts, "window_minutes": S.window,
            "content_stored": S.store_content}


@app.get("/campaigns")
def list_campaigns(recipient: Optional[str] = None, include_inactive: bool = False):
    return store().campaigns(recipient, active_only=not include_inactive)


@app.get("/campaigns/{cid}")
def get_campaign(cid: int):
    c = store().campaign(cid)
    if c is None: raise HTTPException(status_code=404, detail=f"no campaign {cid}")
    return c


@app.get("/alerts")
def list_alerts(recipient: Optional[str] = None, include_acked: bool = False):
    return store().alerts(recipient, include_acked)


@app.post("/alerts/{aid}/ack")
def ack_alert(aid: int):
    if not store().ack(aid): raise HTTPException(status_code=404, detail=f"no alert {aid}")
    return {"id": aid, "acked": True}


@app.post("/purge")
def purge(b: Optional[PurgeIn] = None):
    """Retention purge: deletes events stored more than older_than_days ago (default CP1_RETENTION_DAYS, 30) and the alerts and campaigns that go with them."""
    return store().purge((b or PurgeIn()).older_than_days)


# ---------------------------------------------------------------- console (R2-04, R3-13)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@app.get("/presets")
def get_presets():
    """One-click console presets: TC-01 to TC-08 and four Indian stories. HAND-WRITTEN, NOT A TEST SET."""
    from demo_cases import presets
    return presets()


@app.get("/lite", include_in_schema=False)
def lite():
    """The one-file console (console.html), served here so it needs no CORS."""
    return FileResponse(ROOT / "console.html")


_DIST = ROOT / "console" / "dist"            # the built React console: one command, one address (uvicorn api:app, then http://127.0.0.1:8000/)
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="console")
else:
    @app.get("/", include_in_schema=False)
    def no_console():
        return {"detail": "The console is not built. Run `npm install` and `npm run build` in console/, or open /lite."}
