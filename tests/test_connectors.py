"""Mailbox connectors run by the server, against stand-in servers (tests/fakes.py): new mail is scored within seconds with IMAP IDLE, older mail
is left alone, the mailbox is never changed, secrets are never stored or returned in clear, and Microsoft 365 works through Graph."""
import json, time
from pathlib import Path
from conftest import TMP
from fakes import FakeGraph, FakeImap, forwarded_report, made_up_email, wait_for
from server import connectors as C


def _conn(c, cid): return next(x for x in c.get("/api/admin/connectors").json() if x["id"] == cid)
def _feed(c, recipient): return [m for m in c.get("/api/live/recent?limit=500").json() if m["recipient"] == recipient]


def _imap(f, **cfg):
    return {"host": "127.0.0.1", "port": f.port, "security": "none", "username": f.user, **cfg}


def _all_stored_bytes():
    return b"".join(p.read_bytes() for p in Path(TMP).rglob("*") if p.is_file())


def test_an_imap_inbox_is_read_live_and_never_changed(login):
    f = FakeImap(user="watch@a.example"); ad = login("admin@a.example")
    try:
        f.append(made_up_email(subject="already there before the connector"))
        r = ad.post("/api/admin/connectors", json={"kind": "imap", "name": "Watched inbox", "secret": f.password, "config": _imap(f, mode="inbox")})
        assert r.status_code == 200, r.text; cid = r.json()["id"]
        assert r.json()["has_secret"] and "secret" not in r.json() and r.json()["config"]["mailbox_address"] == "watch@a.example"
        assert wait_for(lambda: _conn(ad, cid)["status"] == "live"), _conn(ad, cid)
        t0 = time.monotonic(); f.append(made_up_email(to="someone.else@a.example", marker="unique-imap-marker-31"))
        rows = wait_for(lambda: _feed(ad, "watch@a.example"), timeout=10)
        assert rows, _conn(ad, cid)
        assert time.monotonic() - t0 < 5                                          # IMAP IDLE: seconds, not a polling interval
        assert sorted(m["channel"] for m in rows) == ["email", "url"] and {m["source"] for m in rows} == {"mailbox"} and rows[0]["origin"] == "Watched inbox"
        assert _conn(ad, cid)["n_messages"] == 1                                  # the older message was not read
        assert "EXAMINE" in f.commands and not f.changed_mailbox()                 # opened read-only; no flag set, nothing moved or deleted
        stored = _all_stored_bytes()
        assert f.password.encode() not in stored and b"unique-imap-marker-31" not in stored

        ad.patch(f"/api/admin/connectors/{cid}", json={"active": False}); assert _conn(ad, cid)["status"] == "paused"
        f.append(made_up_email(subject="arrives while paused")); time.sleep(1.0)
        assert _conn(ad, cid)["n_messages"] == 1
        ad.patch(f"/api/admin/connectors/{cid}", json={"active": True})
        assert wait_for(lambda: _conn(ad, cid)["n_messages"] == 2, timeout=10), _conn(ad, cid)   # read after resuming: nothing skipped
    finally:
        ad.delete(f"/api/admin/connectors/{cid}"); f.close()


def test_a_server_without_idle_is_polled_and_reports_use_the_reporter(login):
    f = FakeImap(user="reports@a.example", idle=False); ad = login("admin@a.example")
    try:
        cid = ad.post("/api/admin/connectors", json={"kind": "imap", "name": "Reporting mailbox", "secret": f.password,
                                                     "config": _imap(f, mode="reports", poll_seconds=10)}).json()["id"]
        assert wait_for(lambda: _conn(ad, cid)["status"] == "polling"), _conn(ad, cid)
        f.append(forwarded_report(reporter="ravi.k@a.example"))
        ad.post(f"/api/admin/connectors/{cid}/check")
        rows = wait_for(lambda: _feed(ad, "ravi.k@a.example"), timeout=10)
        assert rows and rows[0]["source"] == "mailbox", _conn(ad, cid)
    finally:
        ad.delete(f"/api/admin/connectors/{cid}"); f.close()


def test_connection_test_wrong_password_and_access(login):
    f = FakeImap(user="check@a.example"); ad = login("admin@a.example")
    try:
        ok = ad.post("/api/admin/connectors/test", json={"kind": "imap", "config": _imap(f), "secret": f.password}).json()
        assert ok["ok"] and "IDLE" in ok["detail"], ok
        bad = ad.post("/api/admin/connectors/test", json={"kind": "imap", "config": _imap(f), "secret": "wrong-password-1"}).json()
        assert not bad["ok"] and "Invalid credentials" in bad["detail"]
        cid = ad.post("/api/admin/connectors", json={"kind": "imap", "name": "Wrong password", "secret": "wrong-password-1", "config": _imap(f)}).json()["id"]
        err = wait_for(lambda: (lambda c: c if c["status"] == "error" else None)(_conn(ad, cid)))
        assert err and "Invalid credentials" in err["detail"]
        assert login("analyst@a.example").get("/api/admin/connectors").status_code == 403
        assert login("admin@b.example").patch(f"/api/admin/connectors/{cid}", json={"active": False}).status_code == 404
        assert ad.post("/api/admin/connectors", json={"kind": "imap", "name": "x", "secret": "", "config": _imap(f)}).status_code == 422
        ad.delete(f"/api/admin/connectors/{cid}")
    finally:
        f.close()


def test_a_microsoft_365_mailbox_through_graph(login, monkeypatch):
    g = FakeGraph(mailbox="m365.watch@a.example"); ad = login("admin@a.example")
    monkeypatch.setattr(C, "LOGIN_BASE", f"http://127.0.0.1:{g.port}"); monkeypatch.setattr(C, "GRAPH_BASE", f"http://127.0.0.1:{g.port}/v1.0")
    cfg = {"tenant_id": g.tenant, "client_id": g.client_id, "mailbox": g.mailbox, "mode": "inbox"}
    try:
        g.add(made_up_email(subject="an hour old"), received=time.time() - 3600)
        assert ad.post("/api/admin/connectors/test", json={"kind": "graph", "config": cfg, "secret": g.secret}).json()["ok"]
        bad = ad.post("/api/admin/connectors/test", json={"kind": "graph", "config": cfg, "secret": "wrong-secret"}).json()
        assert not bad["ok"] and "401" in bad["detail"]
        cid = ad.post("/api/admin/connectors", json={"kind": "graph", "name": "Microsoft 365 inbox", "secret": g.secret, "config": cfg}).json()["id"]
        assert wait_for(lambda: _conn(ad, cid)["status"] == "polling"), _conn(ad, cid)
        g.add(made_up_email(), received=time.time() + 2)
        ad.post(f"/api/admin/connectors/{cid}/check")
        rows = wait_for(lambda: _feed(ad, "m365.watch@a.example"), timeout=10)
        assert rows and _conn(ad, cid)["n_messages"] == 1, _conn(ad, cid)
        assert g.secret.encode() not in _all_stored_bytes()
    finally:
        ad.delete(f"/api/admin/connectors/{cid}"); g.close()


def test_the_demo_replay_plays_once_then_stops(login, world):
    from server import db as M
    db = M.session(); c = M.Connector(org_id=world["org_b"], kind="demo", name="Demo replay", active=False, config=json.dumps({"seconds_between": 0.05}),
                                      status="paused"); db.add(c); db.commit(); cid = c.id; db.close()
    ad = login("admin@b.example")
    assert ad.patch(f"/api/admin/connectors/{cid}", json={"config": {}}).status_code == 422         # it can only be played or paused
    ad.patch(f"/api/admin/connectors/{cid}", json={"active": True})
    assert wait_for(lambda: _conn(ad, cid)["status"] == "finished", timeout=40), _conn(ad, cid)
    n = len(C.demo_plan()); c = _conn(ad, cid)
    assert c["n_messages"] == n and not c["active"] and c["n_alerts"] >= 3
    rows = [m for m in ad.get("/api/live/recent?limit=500").json() if m["source"] == "demo"]
    assert len(rows) == n and any(m["channel"] == "call" and m["score"] is None and m["label"] == "not assessed" for m in rows)
    ad.delete(f"/api/admin/connectors/{cid}")
