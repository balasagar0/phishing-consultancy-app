"""The live event stream (Server-Sent Events) on a real port: a signed-in page hears about its own organisation's new messages and alerts within
seconds, nothing of another organisation's, and the stream ends when the person signs out."""
import json, time
import httpx, pytest
from conftest import PW


def _client(base, email, read=10.0):
    c = httpx.Client(base_url=base, timeout=httpx.Timeout(10.0, read=read))
    r = c.post("/api/auth/login", json={"email": email, "password": PW}); assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]; return c


def _read(lines, until, limit_s=10.0):
    out, kind, end = [], None, time.monotonic() + limit_s
    for line in lines:
        if line.startswith("event: "): kind = line[7:]
        elif line.startswith("data: ") and kind: out.append((kind, json.loads(line[6:]))); kind = None
        if until(out) or time.monotonic() > end: break
    return out


def _weak_campaign(c):
    return {p["id"]: p for p in c.get("/api/presets").json()}["TC-06"]["events"]


def test_a_page_hears_its_own_organisation_and_nothing_else(live_server):
    a, b = _client(live_server, "analyst@a.example"), _client(live_server, "admin@b.example", read=3.0)
    with a.stream("GET", "/api/live/stream") as sa, b.stream("GET", "/api/live/stream") as sb:
        assert sa.headers["content-type"].startswith("text/event-stream")
        la, lb = sa.iter_lines(), sb.iter_lines()
        assert _read(la, lambda o: any(k == "hello" for k, _ in o))[0][0] == "hello"
        assert _read(lb, lambda o: any(k == "hello" for k, _ in o))[0][0] == "hello"
        t0 = time.monotonic()
        assert a.post("/api/events", json={"recipient": "live.person@a.example", "events": _weak_campaign(a)}).status_code == 200
        got = _read(la, lambda o: any(k == "alert" for k, _ in o))
        assert time.monotonic() - t0 < 5
        msgs = [d for k, d in got if k == "message"]; alerts = [d for k, d in got if k == "alert"]
        assert [m["channel"] for m in msgs] == ["sms", "url", "email"] and all(m["recipient"] == "live.person@a.example" for m in msgs)
        assert alerts[0]["recipient"] == "live.person@a.example" and alerts[0]["risk"] == 0.595 and "text" not in json.dumps(msgs)
        cid = alerts[0]["case_id"]
        assert a.patch(f"/api/alerts/{cid}", json={"status": "investigating"}).status_code == 200
        upd = _read(la, lambda o: any(k == "alert_update" for k, _ in o))
        assert [d for k, d in upd if k == "alert_update"][0]["status"] == "investigating"
        seen_b = []
        try:
            for line in lb: seen_b.append(line)
        except httpx.ReadTimeout:
            pass
        assert not any(x.startswith(("event: message", "event: alert")) for x in seen_b), seen_b


def test_the_stream_needs_a_session_and_an_organisation(live_server):
    assert httpx.get(f"{live_server}/api/live/stream", timeout=5).status_code == 401
    su = _client(live_server, "consultant@test.example")
    assert su.get("/api/live/stream").status_code == 409            # the consultant must open an organisation first


def test_the_stream_ends_when_the_person_signs_out(live_server, monkeypatch):
    from server import routes_live
    monkeypatch.setattr(routes_live, "RECHECK_S", 0.3); monkeypatch.setattr(routes_live, "KEEPALIVE_S", 0.3)
    v = _client(live_server, "viewer@a.example"); other = httpx.Client(base_url=live_server, timeout=10, cookies=v.cookies, headers=v.headers)
    with v.stream("GET", "/api/live/stream") as s:
        lines = s.iter_lines(); _read(lines, lambda o: bool(o))
        assert other.post("/api/auth/logout").status_code == 200
        got = _read(lines, lambda o: any(k == "end" for k, _ in o), limit_s=8)
        assert any(k == "end" for k, _ in got)
