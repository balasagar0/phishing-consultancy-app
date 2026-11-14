"""Message sources the server reads by itself, so nobody has to paste messages in.

- 'imap': any IMAP mailbox (Gmail or Google Workspace with an app password, Zoho, an on-premises Exchange, Dovecot...). When the mail server
  offers IMAP IDLE, it tells us about new mail as it arrives and the message is scored within seconds; otherwise the folder is checked every
  poll_seconds. Even while idling, the folder is searched at least every IDLE_CAP_S seconds, in case a server's notice was missed.
- 'graph': a Microsoft 365 mailbox through Microsoft Graph with an app registration (client credentials, Mail.Read application permission).
  Exchange Online no longer accepts IMAP passwords, so this is the way in for Microsoft 365. The folder is checked every poll_seconds.
- 'demo': replays the hand-written demo messages with the current time, one every few seconds, to show the live feed in a demo. They are not
  real messages and are labelled 'demo' everywhere.

Each active connector runs in its own thread (Manager). It reads only mail that arrives after it is switched on (unless asked to take the last
few), opens the folder read-only and never changes the mailbox (no flag is set, nothing is moved or deleted), scores every message through the
same path as the API (services.record_mail), and stores where it got to, so a restart neither skips nor repeats messages. Message content is
never logged; problems are kept as one short line on the connector, and the thread retries with a growing pause."""
import imaplib, ipaddress, json, logging, re, select, socket, ssl, threading, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from sqlalchemy import select as sql_select
from . import db as M, engine
from .deps import Ctx
from .live import bus
from .mailparse import MAX_RAW
from .secretbox import unseal
from .security import no_redirect_opener, vet_host
from .services import EventsIn, record_events, record_mail

log = logging.getLogger("mcpd")
KINDS = ("imap", "graph", "demo")
IDLE_CAP_S = 120
TIMEOUT = 60
LOGIN_BASE = "https://login.microsoftonline.com"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class ConnectorError(Exception):
    pass


def aad(org_id: int, kind: str) -> str: return f"org:{org_id}:connector:{kind}"


def brief(c: M.Connector) -> dict:
    return {"id": c.id, "kind": c.kind, "name": c.name, "active": c.active, "status": c.status, "detail": c.detail, "last_checked_at": c.last_checked_at,
            "last_message_at": c.last_message_at, "n_messages": c.n_messages, "n_alerts": c.n_alerts, "n_skipped": c.n_skipped}


def public(c: M.Connector) -> dict:
    return {**brief(c), "config": json.loads(c.config or "{}"), "has_secret": bool(c.secret), "created_at": c.created_at, "updated_at": c.updated_at}


def _graph_error(e: urllib.error.HTTPError) -> str:
    try: j = json.loads(e.read().decode("utf-8", "replace") or "{}")
    except (ValueError, OSError): j = {}
    err = j.get("error"); code = err.get("code") if isinstance(err, dict) else err
    hint = {401: "check the tenant, the client ID and the secret", 403: "the app registration needs the Mail.Read application permission, with admin consent",
            404: "check the mailbox address and the folder"}.get(e.code, "")
    return f"Microsoft answered HTTP {e.code}" + (f" ({code})" if code else "") + (f": {hint}" if hint else "")


def safe_error(e: BaseException) -> str:
    """One short line for the connector's status. Never message content."""
    if isinstance(e, (ConnectorError, ValueError)): return str(e)[:300]
    if isinstance(e, imaplib.IMAP4.error):
        m = e.args[0] if e.args else ""
        return "the mail server said: " + (m.decode("utf-8", "replace") if isinstance(m, bytes) else str(m))[:250]
    if isinstance(e, ssl.SSLCertVerificationError): return f"the server's certificate did not verify ({e.verify_message})"
    if isinstance(e, ssl.SSLError): return "the secure connection failed: check the port and the security setting"
    if isinstance(e, TimeoutError): return "the server did not answer in time"
    if isinstance(e, ConnectionRefusedError): return "the server refused the connection: check the host and the port"
    if isinstance(e, urllib.error.HTTPError): return _graph_error(e)
    if isinstance(e, (urllib.error.URLError, OSError)): return f"network problem ({type(getattr(e, 'reason', e)).__name__})"
    return f"unexpected problem ({type(e).__name__})"


# ---------------------------------------------------------------- IMAP

def _open_imap(cfg: dict, timeout: float = TIMEOUT):
    host = cfg["host"].strip(); port = int(cfg.get("port") or 993); sec = cfg.get("security", "ssl")
    ip = vet_host(host, port)
    if sec == "none" and ipaddress.ip_address(ip.split("%")[0]).is_global:
        raise ConnectorError("IMAP without TLS sends the password in clear; it is allowed only inside a private network")
    ctx = ssl.create_default_context()

    class _Pinned:                       # connect to the address vet_host checked; TLS still checks the certificate against the host name
        def _create_socket(self, t):
            s = socket.create_connection((ip, self.port), t)
            return ctx.wrap_socket(s, server_hostname=host) if sec == "ssl" else s

    if sec == "ssl": m = type("PinnedIMAP4SSL", (_Pinned, imaplib.IMAP4_SSL), {})(host, port, ssl_context=ctx, timeout=timeout)
    else: m = type("PinnedIMAP4", (_Pinned, imaplib.IMAP4), {})(host, port, timeout=timeout)
    if sec == "starttls": m.starttls(ssl_context=ctx)
    return m


def _mbox(name: str) -> str:
    name = name or "INBOX"
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"' if re.search(r'[\s"\\(){%*]', name) else name


def _caps(m) -> set:
    typ, dat = m.capability()
    return {x.upper() for x in (dat[0] or b"").decode("ascii", "replace").split()} if typ == "OK" and dat else {c.upper() for c in m.capabilities}


def _resp_int(m, code):
    v = (m.response(code)[1] or [None])[0]
    try: return int(v)
    except (TypeError, ValueError): return None


def _start_point(m, uidnext, backfill: int) -> int:
    if not backfill and uidnext: return uidnext - 1
    typ, data = m.uid("search", None, "ALL")
    uids = sorted(int(x) for x in (data[0] or b"").split()) if typ == "OK" and data else []
    if not backfill: return uids[-1] if uids else 0
    return uids[-backfill - 1] if len(uids) > backfill else 0


def _new_uids(m, last: int) -> list[int]:
    typ, data = m.uid("search", None, f"UID {last + 1}:*")
    if typ != "OK": raise ConnectorError("the mail server refused a search")
    return sorted(u for u in (int(x) for x in (data[0] or b"").split()) if u > last)


def _meta(m, uid: int):
    typ, d = m.uid("fetch", str(uid), "(UID RFC822.SIZE INTERNALDATE)")
    meta = b" ".join(x[0] if isinstance(x, tuple) else x for x in (d or []) if x)
    sz = re.search(rb"RFC822\.SIZE (\d+)", meta); tt = imaplib.Internaldate2tuple(meta) if b"INTERNALDATE" in meta else None
    return (int(sz.group(1)) if sz else 0), (time.mktime(tt) if tt else None)


def _body(m, uid: int):
    typ, d = m.uid("fetch", str(uid), "(BODY.PEEK[])")
    return next((x[1] for x in (d or []) if isinstance(x, tuple) and len(x) > 1), None) if typ == "OK" else None


def _idle(m, w) -> bool:
    """IMAP IDLE (RFC 2177) until the server reports new mail, 'Check now' is pressed, the connector stops, or IDLE_CAP_S passes. Python 3.13's
    imaplib has no idle(), so this speaks the two lines of protocol itself. Returns True when the server reported new mail."""
    tag = m._new_tag(); m.send(tag + b" IDLE\r\n")
    try:
        first = m.readline()
        if not first.startswith(b"+"): raise ConnectorError("the mail server refused IDLE")
        sock, end, got = m.sock, time.monotonic() + IDLE_CAP_S, False
        while not w.stop_ev.is_set() and not w.wake.is_set() and time.monotonic() < end:
            if not (getattr(sock, "pending", None) and sock.pending()):
                if not select.select([sock], [], [], 1.0)[0]: continue
            line = m.readline()
            if not line: raise ConnectionError("the mail server closed the connection")
            if re.match(rb"\* \d+ (EXISTS|RECENT)", line): got = True; break
        m.send(b"DONE\r\n")
        while True:
            line = m.readline()
            if not line: raise ConnectionError("the mail server closed the connection")
            if line.startswith(tag + b" "):
                if not line[len(tag) + 1:].upper().startswith(b"OK"): raise ConnectorError("the mail server ended IDLE with an error")
                break
        w.wake.clear()
        return got
    finally:
        m.tagged_commands.pop(tag, None)


def imap_session(w, c):
    cfg, st = c["config"], c["state"]; poll = max(10, int(cfg.get("poll_seconds") or 30)); folder = cfg.get("folder") or "INBOX"
    w.update(status="connecting", detail=f"connecting to {cfg['host']}")
    m = _open_imap(cfg)
    try:
        m.login(cfg["username"], unseal(c["secret"], aad(c["org_id"], "imap")))
        caps = _caps(m)
        typ, _ = m.select(_mbox(folder), readonly=True)
        if typ != "OK": raise ConnectorError(f"cannot open the folder {folder}")
        uv, un = _resp_int(m, "UIDVALIDITY"), _resp_int(m, "UIDNEXT")
        last = st.get("last_uid") if st.get("uidvalidity") == uv and st.get("last_uid") is not None else None
        if last is None:
            last = _start_point(m, un, int(cfg.get("backfill") or 0)); w.update(state={"uidvalidity": uv, "last_uid": last})
        idle = bool(cfg.get("use_idle", True)) and "IDLE" in caps
        w.update(status="live" if idle else "polling",
                 detail="live: the mail server reports new mail as it arrives (IMAP IDLE)" if idle else f"checking the folder every {poll} s")
        while not w.stop_ev.is_set():
            for uid in _new_uids(m, last):
                if w.stop_ev.is_set(): break
                size, received = _meta(m, uid)
                if size > MAX_RAW: w.bump({"status": "too_large"})
                else:
                    raw = _body(m, uid)
                    if raw: w.one(c, raw, received)
                last = uid; w.update(state={"uidvalidity": uv, "last_uid": last})
            w.update(last_checked_at=time.time())
            if w.stop_ev.is_set(): break
            if idle: _idle(m, w)
            else:
                w.wake.wait(poll); w.wake.clear()
                if not w.stop_ev.is_set(): m.noop()
    finally:
        try: m.logout()
        except Exception: pass


# ---------------------------------------------------------------- Microsoft 365 (Graph)

class _TooLarge(Exception):
    pass


def _http(method, url, *, token=None, form=None, raw=False, limit=None):
    headers = {"User-Agent": "mcpd-connector/1", "Accept": "application/json"}; data = None
    if token: headers["Authorization"] = f"Bearer {token}"
    if form is not None: data = urllib.parse.urlencode(form).encode(); headers["Content-Type"] = "application/x-www-form-urlencoded"
    with no_redirect_opener.open(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=TIMEOUT) as r:
        body = r.read(limit + 1) if limit else r.read()
    if limit and len(body) > limit: raise _TooLarge()
    return body if raw else json.loads(body.decode("utf-8"))


class Graph:
    def __init__(self, cfg, secret):
        self.cfg, self.secret, self.token, self.exp = cfg, secret, None, 0.0

    def _tok(self):
        if not self.token or time.time() > self.exp - 120:
            j = _http("POST", f"{LOGIN_BASE}/{urllib.parse.quote(self.cfg['tenant_id'], safe='')}/oauth2/v2.0/token",
                      form={"client_id": self.cfg["client_id"], "client_secret": self.secret, "scope": "https://graph.microsoft.com/.default",
                            "grant_type": "client_credentials"})
            self.token, self.exp = j["access_token"], time.time() + float(j.get("expires_in", 3600))
        return self.token

    def get(self, url, **kw):
        if not url.startswith(GRAPH_BASE): raise ConnectorError("refused a link that does not point to Microsoft Graph")
        try: return _http("GET", url, token=self._tok(), **kw)
        except urllib.error.HTTPError as e:
            if e.code != 401: raise
            self.token = None
            return _http("GET", url, token=self._tok(), **kw)

    def base(self):
        mb = urllib.parse.quote(self.cfg["mailbox"], safe="@."); folder = urllib.parse.quote(self.cfg.get("folder") or "inbox", safe="")
        return f"{GRAPH_BASE}/users/{mb}", f"{GRAPH_BASE}/users/{mb}/mailFolders/{folder}"


def _iso(t: float) -> str: return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _from_iso(s: str) -> float: return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def graph_session(w, c):
    cfg, st = c["config"], c["state"]; poll = max(15, int(cfg.get("poll_seconds") or 30))
    w.update(status="connecting", detail="signing in to Microsoft 365")
    g = Graph(cfg, unseal(c["secret"], aad(c["org_id"], "graph"))); user, folder = g.base()
    g.get(f"{folder}?$select=id")                                   # can we read this mailbox and folder?
    since, seen = st.get("since"), set(st.get("seen", []))
    if since is None:
        since, n = _iso(time.time()), int(cfg.get("backfill") or 0)
        if n:
            j = g.get(f"{folder}/messages?" + urllib.parse.urlencode({"$select": "id,receivedDateTime", "$orderby": "receivedDateTime desc", "$top": str(n)}))
            if j.get("value"): since = j["value"][-1]["receivedDateTime"]
        w.update(state={"since": since, "seen": []})
    w.update(status="polling", detail=f"checking the folder every {poll} s")
    while not w.stop_ev.is_set():
        url, pages = f"{folder}/messages?" + urllib.parse.urlencode({"$select": "id,receivedDateTime", "$filter": f"receivedDateTime ge {since}",
                                                                      "$orderby": "receivedDateTime asc", "$top": "50"}), 0
        while url and pages < 10 and not w.stop_ev.is_set():
            j = g.get(url); pages += 1
            for it in j.get("value", []):
                if it["id"] in seen: continue
                rt = it.get("receivedDateTime") or since
                try: raw = g.get(f"{user}/messages/{urllib.parse.quote(it['id'], safe='')}/$value", raw=True, limit=MAX_RAW)
                except _TooLarge: raw = None; w.bump({"status": "too_large"})
                if raw: w.one(c, raw, _from_iso(rt))
                if rt != since: since, seen = rt, set()
                seen.add(it["id"]); w.update(state={"since": since, "seen": sorted(seen)[-200:]})
            url = j.get("@odata.nextLink")
        w.update(last_checked_at=time.time())
        w.wake.wait(poll); w.wake.clear()


# ---------------------------------------------------------------- demo replay

DEMO = (("TC-04", "accounts.payable@demo.test"), ("TC-06", "stores.manager@demo.test"), ("IN-01", "branch.cashier@demo.test"),
        ("TC-05", "research.lead@demo.test"), ("IN-02", "logistics@demo.test"), ("TC-08", "front.desk@demo.test"), ("IN-03", "new.joiner@demo.test"),
        ("TC-03", "ceo.office@demo.test"), ("IN-04", "procurement@demo.test"), ("TC-01", "hr.desk@demo.test"), ("TC-02", "field.agent@demo.test"))


def demo_plan():
    """The hand-written stories, interleaved the way mail from several campaigns arrives: each story's messages in their own order."""
    P = {p["id"]: p for p in engine.presets()}; queues = []
    for sid, person in DEMO:
        if sid in P: queues.append([(person, sid, e) for e in sorted(P[sid]["events"], key=lambda e: float(e.get("time") or 0))])
    plan = []
    while any(queues):
        for q in queues:
            if q: plan.append(q.pop(0))
    return plan


def demo_session(w, c):
    """Each run uses its own made-up people (run 2 sends to accounts.payable.r2@demo.test, ...), so a replay within the hour opens its own
    campaigns and alerts instead of joining the last run's, which have already alerted."""
    gap = max(0.05, float(c["config"].get("seconds_between", 4))); plan = demo_plan()
    pos, run = int(c["state"].get("pos", 0)), int(c["state"].get("run", 1))
    if pos >= len(plan): pos = 0
    w.update(status="live", detail=f"replaying hand-written demo messages, one every {gap:g} s ({pos} of {len(plan)})")
    for i in range(pos, len(plan)):
        if w.stop_ev.wait(gap): return
        person, sid, e = plan[i]
        if run > 1: person = person.replace("@", f".r{run}@")
        ev = {k: e.get(k) for k in ("channel", "text", "subject", "identity")}; ev["time"] = str(time.time() / 60.0)
        db = M.session()
        try:
            org = db.get(M.Org, c["org_id"])
            r = record_events(db, Ctx(user=None, org=org), EventsIn(recipient=person, events=[ev]), "demo", audit=False, origin=f"story {sid}")
        finally:
            db.close()
        w.bump({"status": "recorded", "alerts": len(r["new_alerts"])})
        w.update(state={"pos": i + 1, "run": run}, detail=f"replaying hand-written demo messages, one every {gap:g} s ({i + 1} of {len(plan)})")
    w.update(active=False, status="finished", detail=f"replayed all {len(plan)} hand-written demo messages; press Play to run them again",
             state={"pos": 0, "run": run + 1})


SESSIONS = {"imap": imap_session, "graph": graph_session, "demo": demo_session}


# ---------------------------------------------------------------- threads

class Worker(threading.Thread):
    def __init__(self, cid: int):
        super().__init__(name=f"connector-{cid}", daemon=True)
        self.cid, self.stop_ev, self.wake = cid, threading.Event(), threading.Event()

    def load(self):
        db = M.session()
        try:
            c = db.get(M.Connector, self.cid)
            if c is None: return None
            org = db.get(M.Org, c.org_id)
            return {"id": c.id, "org_id": c.org_id, "kind": c.kind, "name": c.name, "active": bool(c.active and org is not None and org.active),
                    "config": json.loads(c.config or "{}"), "secret": c.secret, "state": json.loads(c.state or "{}")}
        finally:
            db.close()

    def update(self, **f):
        """Saves status, detail, counters or state on the connector and tells open pages. Does nothing once the connector is stopped or deleted."""
        if self.stop_ev.is_set() and "state" not in f: return
        db = M.session()
        try:
            c = db.get(M.Connector, self.cid)
            if c is None: return
            if "state" in f: f["state"] = json.dumps(f["state"])
            for k, v in f.items(): setattr(c, k, v)
            c.updated_at = time.time(); db.commit()
            if set(f) - {"state"}: bus.publish(c.org_id, "connector", **brief(c))
        finally:
            db.close()

    def bump(self, res: dict):
        db = M.session()
        try:
            c = db.get(M.Connector, self.cid)
            if c is None: return
            if res["status"] == "recorded": c.n_messages += 1; c.n_alerts += int(res.get("alerts", 0)); c.last_message_at = time.time()
            elif res["status"] != "duplicate": c.n_skipped += 1
            db.commit(); bus.publish(c.org_id, "connector", **brief(c))
        finally:
            db.close()

    def one(self, c: dict, raw: bytes, received_at):
        cfg = c["config"]
        try:
            res = record_mail(c["org_id"], raw, mode=cfg.get("mode", "reports"), mailbox=cfg.get("mailbox_address") or cfg.get("mailbox") or "",
                              received_at=received_at, source="mailbox", origin=c["name"])
        except Exception as e:                   # one bad message is counted as skipped; the next one is still read
            log.error("connector %s: a message could not be recorded (%s)", self.cid, type(e).__name__); res = {"status": "failed"}
        self.bump(res)
        return res

    def run(self):
        backoff = 5
        while not self.stop_ev.is_set():
            c = self.load()
            if c is None or not c["active"]: break
            try:
                SESSIONS[c["kind"]](self, c)
                if c["kind"] == "demo": break
                backoff = 5
            except Exception as e:
                if self.stop_ev.is_set(): break
                self.update(status="error", detail=f"{safe_error(e)} (trying again in {backoff} s)")
                log.error("connector %s: %s", self.cid, type(e).__name__)
                if self.stop_ev.wait(backoff): break
                backoff = min(backoff * 2, 300)


class Manager:
    """Starts, stops and wakes the connector threads of one server process."""
    def __init__(self):
        self._w, self._lock = {}, threading.Lock()

    def start(self, cid: int):
        with self._lock:
            w = self._w.get(cid)
            if w is not None and w.is_alive() and not w.stop_ev.is_set(): return
            w = self._w[cid] = Worker(cid); w.start()

    def stop(self, cid: int, wait: float = 3.0):
        with self._lock: w = self._w.pop(cid, None)
        if w is not None:
            w.stop_ev.set(); w.wake.set(); w.join(wait)

    def restart(self, cid: int):
        self.stop(cid); self.start(cid)

    def wake(self, cid: int) -> bool:
        with self._lock: w = self._w.get(cid)
        if w is None or not w.is_alive(): return False
        w.wake.set(); return True

    def running(self, cid: int) -> bool:
        with self._lock: w = self._w.get(cid)
        return w is not None and w.is_alive()

    def _ids(self, org_id=None, active_only=True):
        db = M.session()
        try:
            q = sql_select(M.Connector.id).join(M.Org, M.Org.id == M.Connector.org_id)
            if active_only: q = q.where(M.Connector.active.is_(True), M.Org.active.is_(True))
            if org_id is not None: q = q.where(M.Connector.org_id == org_id)
            return list(db.scalars(q))
        finally:
            db.close()

    def start_all(self, org_id=None):
        for i in self._ids(org_id): self.start(i)

    def stop_org(self, org_id: int):
        for i in self._ids(org_id, active_only=False): self.stop(i, wait=1.0)

    def stop_all(self):
        with self._lock: ids = list(self._w)
        for i in ids: self.stop(i, wait=2.0)


manager = Manager()


def test_connection(kind: str, cfg: dict, secret: str) -> dict:
    """Signs in and opens the folder, reads no message. For the 'Test connection' button."""
    try:
        if kind == "imap":
            m = _open_imap(cfg, timeout=15)
            try:
                m.login(cfg["username"], secret); caps = _caps(m); folder = cfg.get("folder") or "INBOX"
                typ, data = m.select(_mbox(folder), readonly=True)
                if typ != "OK": raise ConnectorError(f"signed in, but cannot open the folder {folder}")
                n = int((data or [b"0"])[0] or 0)
                how = "it supports IMAP IDLE, so new mail is seen within seconds" if "IDLE" in caps else f"no IMAP IDLE: it will be checked every {cfg.get('poll_seconds', 30)} s"
                return {"ok": True, "detail": f"Signed in. The folder {folder} holds {n} message(s); only new ones will be read. The server {how}."}
            finally:
                try: m.logout()
                except Exception: pass
        if kind == "graph":
            g = Graph(cfg, secret); _, folder = g.base(); j = g.get(f"{folder}?$select=displayName,totalItemCount")
            return {"ok": True, "detail": f"Signed in to Microsoft 365. The folder {j.get('displayName', '')} holds {j.get('totalItemCount', '?')} message(s); "
                                          "only new ones will be read."}
        return {"ok": False, "detail": "nothing to test for this kind"}
    except Exception as e:
        return {"ok": False, "detail": safe_error(e)}
