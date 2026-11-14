"""Alert webhooks: when an alert opens, POST a short JSON notice to the address the organisation's admin set (a Slack incoming webhook, a SIEM,
a ticketing system). The body has a Slack-style "text" line and the alert's fields. With a signing secret, the request carries
X-MCPD-Signature: sha256=<HMAC-SHA256 of "<timestamp>.<body>"> and X-MCPD-Timestamp, so the receiver can check it came from this service.

The notice never holds message text. It holds the recipient's name and the plain indicators only when the organisation keeps labels.
Sent from one background thread, three tries (now, after 5 s, after 30 s); the last result is shown on the Connectors page."""
import hashlib, hmac, json, logging, queue, threading, time, urllib.error, urllib.request
from . import db as M
from .config import get_settings
from .live import bus
from .secretbox import seal, unseal
from .security import no_redirect_opener, vet_url

log = logging.getLogger("mcpd")
_q: "queue.Queue[tuple[int, int | None, bool]]" = queue.Queue(maxsize=2000)
_thread = None
_lock = threading.Lock()
RETRY_S = (5, 30)


def aad(org_id: int) -> str: return f"org:{org_id}:alert-hook"


def seal_secret(org_id: int, secret: str) -> str: return seal(secret, aad(org_id))


def payload(org: M.Org, case: M.AlertCase | None) -> dict:
    base = get_settings().public_url
    if case is None:
        return {"type": "test", "org": org.name, "sent_at": time.time(), "text": f"Test notice from the phishing detection service for {org.name}."}
    chans = [x for x in case.channels.split(",") if x]; who = case.recipient_label or f"recipient {case.recipient_ref}"
    link = f"{base}/app/alerts/{case.id}" if base else ""
    return {"type": "alert.opened", "org": org.name, "case_id": case.id, "risk": round(case.risk, 3), "channels": chans, "recipient": who,
            "indicators": json.loads(case.indicators or "[]"), "reason": case.reason, "raised_at": case.created_at, "link": link,
            "text": f"Phishing alert {case.id} for {who}: campaign risk {case.risk:.3f} over {', '.join(chans) or 'no assessed channel'}."
                    + (f" {link}" if link else "") + " The risk is a score, not a probability."}


def send(url: str, secret: str, body: dict, timeout: float = 10.0) -> tuple[bool, str]:
    """One POST. Returns (delivered, a short status line)."""
    try: vet_url(url)
    except ValueError as e: return False, str(e)
    data = json.dumps(body).encode(); ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "User-Agent": "mcpd-alert-webhook/1", "X-MCPD-Timestamp": ts}
    if secret: headers["X-MCPD-Signature"] = "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + data, hashlib.sha256).hexdigest()
    try:
        with no_redirect_opener.open(urllib.request.Request(url, data=data, headers=headers, method="POST"), timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} from the receiver"
    except (urllib.error.URLError, OSError) as e:
        return False, f"could not reach the receiver ({type(getattr(e, 'reason', e)).__name__})"


def deliver(org_id: int, case_id: int | None, test: bool = False, retry: bool = True) -> tuple[bool, str]:
    db = M.session()
    try:
        h = db.query(M.AlertHook).filter_by(org_id=org_id).first()
        if h is None or (not h.active and not test): return False, "no active alert webhook"
        org = db.get(M.Org, org_id); case = db.get(M.AlertCase, case_id) if case_id else None
        if org is None or (case_id and (case is None or case.org_id != org_id)): return False, "nothing to send"
        body = payload(org, case); secret = unseal(h.secret, aad(org_id)) if h.secret else ""; url = h.url
    finally:
        db.close()
    ok, line = send(url, secret, body)
    for wait in (RETRY_S if retry and not ok else ()):
        time.sleep(wait); ok, line = send(url, secret, body)
        if ok: break
    db = M.session()
    try:
        h = db.query(M.AlertHook).filter_by(org_id=org_id).first()
        if h is not None:
            h.last_status = (("delivered: " if ok else "failed: ") + line)[:300]; h.last_at = time.time()
            if ok: h.n_sent += 1
            else: h.n_failed += 1
            db.commit(); bus.publish(org_id, "hook", ok=ok, status=h.last_status)
    finally:
        db.close()
    return ok, line


def _run():
    while True:
        org_id, case_id, _ = _q.get()
        try: deliver(org_id, case_id)
        except Exception as e:                       # one bad delivery must not stop the next
            log.error("alert webhook failed: %s", type(e).__name__)


def enqueue(org_id: int, case_id: int):
    """Queues a notice for a new alert; returns at once. Does nothing for an organisation without an alert webhook."""
    global _thread
    db = M.session()
    try:
        if db.query(M.AlertHook.id).filter_by(org_id=org_id, active=True).first() is None: return
    finally:
        db.close()
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="alert-webhooks", daemon=True); _thread.start()
    try: _q.put_nowait((org_id, case_id, False))
    except queue.Full: log.error("alert webhook queue full: a notice was dropped")
