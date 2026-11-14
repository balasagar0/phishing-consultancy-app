"""Event store (R2-05): keeps each recipient's scored events in SQLite and groups them into campaigns with v2's own window and
correlation code (fusion.window_risks). It is not a second scorer: for the same events, a recipient's highest campaign risk equals the
bundle risk /correlate returns.

- Every event belongs to one recipient. Nothing links across recipients.
- A campaign is one time window of a recipient's assessed events (fusion.time_windows), keyed by the window's first event.
  As events arrive a window can grow, or be absorbed by an earlier, larger one (it is then marked inactive, never deleted while an alert points at it).
- One alert is raised when a campaign first reaches the alert line (0.5), with the events and the shared identity tokens that explain it.
- Calls, voice and video are stored and shown in the campaign timeline, but never change a score (they are not assessed).
- Privacy by default: the recipient and every identity token are stored only as HMAC-SHA256. The key comes from CP1_HMAC_KEY or, failing that,
  is generated once into the gitignored file .cp1_hmac_key. Message text is stored only when CP1_STORE_CONTENT=1. Nothing is logged.
- Stored per event: channel, time, score, label, model version, hashed tokens, and the time it was stored (for the retention purge)."""
import hmac, hashlib, json, os, secrets, sqlite3, threading, time
from pathlib import Path
from fusion import window_risks

ROOT = Path(__file__).resolve().parents[1]
ALERT_LINE = 0.5
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_h TEXT NOT NULL, channel TEXT NOT NULL, t_minutes REAL NOT NULL,
    assessed INTEGER NOT NULL, score REAL, label TEXT NOT NULL, model_version TEXT NOT NULL, tokens_h TEXT NOT NULL, content TEXT, subject TEXT, stored_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS events_recipient ON events (recipient_h, t_minutes);
CREATE TABLE IF NOT EXISTS campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_h TEXT NOT NULL, start_event_id INTEGER NOT NULL, event_ids TEXT NOT NULL,
    first_t REAL NOT NULL, last_t REAL NOT NULL, risk REAL NOT NULL, n_events INTEGER NOT NULL, shared_tokens_h TEXT NOT NULL, active INTEGER NOT NULL,
    alerted INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL, UNIQUE (recipient_h, start_event_id));
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL, recipient_h TEXT NOT NULL, risk REAL NOT NULL,
    event_ids TEXT NOT NULL, shared_tokens_h TEXT NOT NULL, reason TEXT NOT NULL, raised_at REAL NOT NULL, acked_at REAL);
"""


def load_key(path=ROOT / ".cp1_hmac_key"):
    """The HMAC key: CP1_HMAC_KEY if set, else the key file, created once with a random 256-bit key."""
    env = os.environ.get("CP1_HMAC_KEY")
    if env: return env.encode()
    p = Path(path)
    if not p.exists():
        p.write_text(secrets.token_hex(32))
        try: os.chmod(p, 0o600)
        except OSError: pass
    return p.read_text().strip().encode()


def show_token(h):
    """A hashed token for display: its kind (dom, tel, id) and the first 8 hex digits of its HMAC."""
    kind, _, digest = h.partition(":")
    return f"{kind}:#{digest[:8]}"


class EventStore:
    def __init__(self, path, key, model, window, store_content=None):
        """path: SQLite file. key: HMAC key (bytes). model: Fusion.model (the deployed scorer). window: minutes (Fusion.window)."""
        self.path, self.key, self.model, self.window = Path(path), key, model, float(window)
        self.store_content = (os.environ.get("CP1_STORE_CONTENT") == "1") if store_content is None else bool(store_content)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False); self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA); self.lock = threading.Lock()

    def close(self): self.db.close()

    # ---- hashing
    def h(self, s): return hmac.new(self.key, str(s).encode("utf-8"), hashlib.sha256).hexdigest()
    def htok(self, tok):
        kind, _, value = tok.partition(":")
        return f"{kind}:{self.h(tok)}"

    # ---- writing
    def add(self, recipient, events, now=None):
        """events: dicts with channel, assessed, score (None if not assessed), label, ids (plain identity tokens), t (minutes), model_version,
        and optionally text, subject. Returns (stored ids, recipient hash, new alerts)."""
        now = time.time() if now is None else now; rh = self.h(recipient); ids = []
        with self.lock, self.db:
            for e in events:
                keep = self.store_content
                cur = self.db.execute("INSERT INTO events (recipient_h, channel, t_minutes, assessed, score, label, model_version, tokens_h, content, subject, stored_at) "
                                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                      (rh, e["channel"], float(e["t"]), int(bool(e["assessed"])), e.get("score"), e["label"], e.get("model_version", "none"),
                                       json.dumps(sorted({self.htok(t) for t in e.get("ids", [])})), e.get("text") if keep else None, e.get("subject") if keep else None, now))
                ids.append(cur.lastrowid)
            alerts = self._regroup(rh, now)
        return ids, rh, alerts

    def _regroup(self, rh, now):
        """Rebuilds the recipient's campaigns from all their assessed events with fusion.window_risks. Raises an alert for each campaign that
        reaches the alert line for the first time. Must run inside the lock and a transaction."""
        rows = self.db.execute("SELECT id, channel, t_minutes, score, tokens_h FROM events WHERE recipient_h=? AND assessed=1 ORDER BY t_minutes, id", (rh,)).fetchall()
        ev = [{"channel": r["channel"], "score": r["score"], "ids": json.loads(r["tokens_h"]), "t": r["t_minutes"]} for r in rows]
        keep, alerts = set(), []
        for g, risk, _ in (window_risks(self.model, ev, self.window) if ev else []):
            eids = [rows[i]["id"] for i in g]; start = eids[0]; keep.add(start)
            cnt = {}
            for i in g:
                for tok in set(ev[i]["ids"]): cnt[tok] = cnt.get(tok, 0) + 1
            shared = sorted(t for t, c in cnt.items() if c >= 2); ts = [ev[i]["t"] for i in g]
            self.db.execute("INSERT INTO campaigns (recipient_h, start_event_id, event_ids, first_t, last_t, risk, n_events, shared_tokens_h, active, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,1,?) ON CONFLICT (recipient_h, start_event_id) DO UPDATE SET event_ids=excluded.event_ids, first_t=excluded.first_t, "
                            "last_t=excluded.last_t, risk=excluded.risk, n_events=excluded.n_events, shared_tokens_h=excluded.shared_tokens_h, active=1, updated_at=excluded.updated_at",
                            (rh, start, json.dumps(eids), min(ts), max(ts), risk, len(eids), json.dumps(shared), now))
            c = self.db.execute("SELECT id, alerted FROM campaigns WHERE recipient_h=? AND start_event_id=?", (rh, start)).fetchone()
            if risk >= ALERT_LINE and not c["alerted"]:
                chans = [f"event {rows[i]['id']} {rows[i]['channel']} {rows[i]['score']:.3f}" for i in g]
                reason = (f"campaign risk {risk:.3f} reached the alert line {ALERT_LINE} with {len(g)} event(s) in one {self.window:g}-minute window: " + "; ".join(chans)
                          + (f"; shared identity tokens: {', '.join(show_token(t) for t in shared)}" if shared else "; no shared identity token"))
                cur = self.db.execute("INSERT INTO alerts (campaign_id, recipient_h, risk, event_ids, shared_tokens_h, reason, raised_at) VALUES (?,?,?,?,?,?,?)",
                                      (c["id"], rh, risk, json.dumps(eids), json.dumps(shared), reason, now))
                self.db.execute("UPDATE campaigns SET alerted=1 WHERE id=?", (c["id"],))
                alerts.append({"id": cur.lastrowid, "campaign_id": c["id"], "risk": risk, "event_ids": eids, "shared_tokens_h": shared, "reason": reason})
        for r in self.db.execute("SELECT id, start_event_id FROM campaigns WHERE recipient_h=? AND active=1", (rh,)).fetchall():
            if r["start_event_id"] not in keep: self.db.execute("UPDATE campaigns SET active=0, updated_at=? WHERE id=?", (now, r["id"]))
        return alerts

    def ack(self, alert_id, now=None):
        with self.lock, self.db:
            cur = self.db.execute("UPDATE alerts SET acked_at=? WHERE id=? AND acked_at IS NULL", (time.time() if now is None else now, alert_id))
            return cur.rowcount == 1 or self.db.execute("SELECT 1 FROM alerts WHERE id=?", (alert_id,)).fetchone() is not None

    def purge(self, older_than_days, now=None):
        """Retention: deletes events stored more than `older_than_days` ago and alerts raised before then, then rebuilds the campaigns of the
        recipients affected. Campaigns left with no events, or inactive with no alert, are deleted."""
        now = time.time() if now is None else now; cut = now - float(older_than_days) * 86400
        with self.lock, self.db:
            hit = [r[0] for r in self.db.execute("SELECT DISTINCT recipient_h FROM events WHERE stored_at < ?", (cut,))]
            n_ev = self.db.execute("DELETE FROM events WHERE stored_at < ?", (cut,)).rowcount
            n_al = self.db.execute("DELETE FROM alerts WHERE raised_at < ?", (cut,)).rowcount
            for rh in hit: self._regroup(rh, now)
            live = {r[0] for r in self.db.execute("SELECT id FROM events")}
            gone = 0
            for c in self.db.execute("SELECT id, event_ids, active FROM campaigns").fetchall():
                left = [i for i in json.loads(c["event_ids"]) if i in live]
                has_alert = self.db.execute("SELECT 1 FROM alerts WHERE campaign_id=?", (c["id"],)).fetchone()
                if not left or (not c["active"] and not has_alert):
                    self.db.execute("DELETE FROM alerts WHERE campaign_id=?", (c["id"],)); self.db.execute("DELETE FROM campaigns WHERE id=?", (c["id"],)); gone += 1
        return {"events_deleted": n_ev, "alerts_deleted": n_al, "campaigns_deleted": gone, "cutoff_epoch_s": cut}

    # ---- reading (hashes are shown shortened; plain text appears only if it was stored)
    def _campaign(self, r):
        return {"id": r["id"], "recipient": r["recipient_h"][:12], "risk": round(r["risk"], 4), "alert": r["risk"] >= ALERT_LINE, "n_events": r["n_events"],
                "event_ids": json.loads(r["event_ids"]), "first_t_minutes": r["first_t"], "last_t_minutes": r["last_t"],
                "shared_identity_tokens": [show_token(t) for t in json.loads(r["shared_tokens_h"])], "active": bool(r["active"]), "alerted": bool(r["alerted"])}

    def campaigns(self, recipient=None, active_only=True):
        q, a = "SELECT * FROM campaigns WHERE 1=1", []
        if recipient is not None: q += " AND recipient_h=?"; a.append(self.h(recipient))
        if active_only: q += " AND active=1"
        return [self._campaign(r) for r in self.db.execute(q + " ORDER BY first_t, id", a)]

    def campaign(self, cid):
        r = self.db.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
        if r is None: return None
        c = self._campaign(r)
        evs = self.db.execute("SELECT * FROM events WHERE recipient_h=? AND t_minutes BETWEEN ? AND ? ORDER BY t_minutes, id",
                              (r["recipient_h"], r["first_t"], r["first_t"] + self.window)).fetchall()
        inside = set(c["event_ids"])
        c["timeline"] = [{"id": e["id"], "channel": e["channel"], "t_minutes": e["t_minutes"], "assessed": bool(e["assessed"]), "score": e["score"], "label": e["label"],
                          "model_version": e["model_version"], "identity_tokens": [show_token(t) for t in json.loads(e["tokens_h"])], "in_campaign": e["id"] in inside,
                          **({"subject": e["subject"], "text": e["content"]} if e["content"] is not None else {})} for e in evs]
        c["window_minutes"] = self.window
        return c

    def alerts(self, recipient=None, include_acked=False):
        q, a = "SELECT * FROM alerts WHERE 1=1", []
        if recipient is not None: q += " AND recipient_h=?"; a.append(self.h(recipient))
        if not include_acked: q += " AND acked_at IS NULL"
        return [{"id": r["id"], "campaign_id": r["campaign_id"], "recipient": r["recipient_h"][:12], "risk": round(r["risk"], 4), "event_ids": json.loads(r["event_ids"]),
                 "shared_identity_tokens": [show_token(t) for t in json.loads(r["shared_tokens_h"])], "reason": r["reason"], "raised_at": r["raised_at"],
                 "acked": r["acked_at"] is not None} for r in self.db.execute(q + " ORDER BY id", a)]
