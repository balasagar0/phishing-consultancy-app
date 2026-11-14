"""The detection engine: the pinned copy of the CP1 project's tag cp1-final in ../engine, used through its own functions so that every score is
the score cp1-final gives (tests/test_engine_parity.py). This module adds only what a multi-client service needs:
- one event store per organisation, in its own SQLite file, with its own HMAC key derived from the master key (no key is stored in a file per
  organisation and no data is shared between organisations);
- the model card the website shows, read from the pinned engine/final_numbers.json (numbers are never typed here)."""
import hashlib, hmac, json, sys, threading, time, warnings
from pathlib import Path
from .config import APP_DIR, get_settings

ENGINE_DIR = APP_DIR / "engine"
sys.path.insert(0, str(ENGINE_DIR / "src")); sys.path.insert(0, str(ENGINE_DIR))
warnings.filterwarnings("ignore", category=DeprecationWarning)
import api as cp1                       # noqa: E402  cp1-final's api.py: its functions are used, its own web app is never served
from event_store import EventStore, show_token   # noqa: E402
from demo_cases import presets as _presets   # noqa: E402

MANIFEST = json.loads((ENGINE_DIR / "ENGINE_MANIFEST.json").read_text(encoding="utf-8"))
NUMBERS = json.loads((ENGINE_DIR / "final_numbers.json").read_text(encoding="utf-8"))
ALERT_LINE = 0.5
_stores, _lock = {}, threading.Lock()


def info():
    h = cp1.health()
    return {**h, "engine_tag": MANIFEST["tag"], "engine_commit": MANIFEST["tag_commit"][:7], "alert_line": ALERT_LINE}


def score(channel, text, subject=""):
    return cp1._run(cp1.Item(channel=channel, text=text, subject=subject or ""))


def url_ok(u: str) -> bool:
    """True when cp1-final would accept this text as a URL event (links pulled out of a message are checked before they are sent)."""
    return not cp1.check_url(u)


def correlate(events, window_minutes=None):
    return cp1.correlate(cp1.Bundle(events=[cp1.Event(**e) for e in events], window_minutes=window_minutes))


def org_key(org_id: int) -> bytes:
    return hmac.new(get_settings().master_key, f"org:{org_id}".encode(), hashlib.sha256).hexdigest().encode()


def store(org):
    """The organisation's event store. Opened once per process; `store_content` follows the organisation's setting."""
    with _lock:
        s = _stores.get(org.id)
        if s is None:
            path = get_settings().data_dir / "orgs" / str(org.id) / "events.db"
            s = _stores[org.id] = EventStore(path, org_key(org.id), cp1.F.model, cp1.F.window, store_content=org.store_content)
        s.store_content = bool(org.store_content)
        return s


def close_stores():
    with _lock:
        for s in _stores.values(): s.close()
        _stores.clear()


def add_events(org, recipient, events):
    """cp1-final's POST /events, on this organisation's own store. Returns the same answer, plus the plain shared tokens of each new alert."""
    evs = [cp1.Event(**e) for e in events]
    out, ev, idx, skipped = cp1._assess(evs, default_time=time.time() / 60.0)
    rows = [{"channel": o["channel"], "assessed": o["assessed"], "score": o["score"], "label": o["label"], "ids": o["identity_tokens"], "t": o["t_minutes"],
             "model_version": cp1.MODEL_VERSION.get(o["channel"], "none"), "text": e.text, "subject": e.subject} for o, e in zip(out, evs)]
    S = store(org); ids, rh, alerts = S.add(recipient, rows)
    plain = {S.htok(t): t for o in out for t in o["identity_tokens"]}
    for a in alerts:
        a["shared_identity_tokens"] = [plain.get(t, show_token(t)) for t in a.pop("shared_tokens_h")]   # tokens of earlier requests stay hashed
        c = S.campaign(a["campaign_id"]) or {"timeline": []}
        a["channels"] = sorted({e["channel"] for e in c["timeline"] if e["in_campaign"]})
    camps = S.campaigns(recipient)
    for o, i in zip(out, ids): o["event_id"] = i
    return {"status": "ASSESSED" if ev else "CANNOT_ASSESS", "recipient_ref": rh[:12], "events": out, "not_assessed": skipped, "campaigns": camps,
            "highest_campaign_risk": max((c["risk"] for c in camps), default=None), "new_alerts": alerts, "window_minutes": S.window,
            "content_stored": S.store_content}


def presets():
    return _presets()


def model_card():
    """What the website and the app say about the models: honest figures only, each with its condition, plus what is not built."""
    V = NUMBERS["values"]; g = V.get
    return {
        "engine": {"tag": MANIFEST["tag"], "commit": MANIFEST["tag_commit"][:7], "synced_at": MANIFEST["synced_at"]},
        "window_minutes": g("window.minutes"), "alert_line": g("alert_line"),
        "detectors": [
            {"channel": "email", "honest": g("email.honest.f1"), "measure": "F1 on email corpora the model never saw (mean of three leave-one-corpus-out runs)",
             "flattering": g("email.flattering.f1"), "flattering_measure": "pooled random split (shown only beside the honest figure)",
             "real_mail_false_alarms": g("email.realmail.fpr"), "real_mail_n": g("email.realmail.n")},
            {"channel": "sms", "honest": g("sms.honest.f1"), "measure": f"smishing-vs-rest F1 (95% CI {g('sms.honest.f1_ci')})",
             "flattering": g("sms.flattering.f1"), "flattering_measure": "spam or smishing against ham"},
            {"channel": "url", "honest": g("url.honest.f1"), "measure": "F1 with web hosts held out of training",
             "flattering": g("url.flattering.f1"), "flattering_measure": "random split of a feature dataset",
             "login_false_alarms": f"{g('url.login_fpr.before')} to {g('url.login_fpr.after')}", "popular_domain_recall": f"{g('url.popular_recall.before')} to {g('url.popular_recall.after')}"},
        ],
        "correlation": {"simulated": True, "engine_f1": g("corr.engine.f1"), "engine_fpr": g("corr.engine.fpr"), "single_f1": g("corr.single.f1"),
                        "single_fpr": g("corr.single.fpr"), "n_test_bundles": g("corr.n_test"),
                        "note": "Measured on simulated bundles of real messages: the links between messages are constructed. No real coordinated campaign has tested it yet."},
        "latency": {"email": g("latency.email.median"), "sms": g("latency.sms.median"), "url": g("latency.url.median"), "full_case": g("latency.case.median")},
        "not_assessed": ["voice calls", "video"],
        "limitations": [
            f"The email model raised a false alarm on {g('email.realmail.fpr')} of {g('email.realmail.n')} real legitimate emails from one consenting user. Treat email verdicts as advice for an analyst, not as automatic blocking.",
            f"The URL model catches fewer bad links hosted on popular domains ({g('url.popular_recall.after')} recall there), in exchange for not flagging their login pages.",
            f"SMS smishing results rest on {g('sms.smishing_support')} test messages; the interval is wide ({g('sms.honest.f1_ci')}).",
            "Correlation results are simulated. The risk is a score, not a probability, and the alert line is tied to the simulation.",
            "Calls and video are shown as 'not assessed', never as safe.",
            "A false alarm from a detector stays a false alarm after correlation.",
        ],
    }
