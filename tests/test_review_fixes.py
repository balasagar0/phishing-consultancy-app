"""Regression tests for the faults found while preparing the end-semester review (24 Nov 2026). Every message here is made up."""
import time
from server import db as M

HALF_A_CHARACTER = b'"hello \\ud800 please pay the fee"'          # valid JSON, but not a valid Unicode string


def _json(c, path, raw): return c.post(path, content=raw, headers={"Content-Type": "application/json"})


def _key(login):
    ad = login("admin@a.example"); return ad.post("/api/admin/api-keys", json={"name": "review fixes"}).json()["key"]


def test_an_absurd_event_time_is_refused_and_the_live_feed_keeps_working(login):
    c = login("analyst@a.example")
    for path, body in (("/api/events", {"recipient": "huge.time@a.example", "events": [{"channel": "sms", "text": "Your parcel is held", "time": "1e308"}]}),
                       ("/api/correlate", {"events": [{"channel": "sms", "text": "one", "time": "1e308"}, {"channel": "sms", "text": "two", "time": "-1e308"}]})):
        assert c.post(path, json=body).status_code == 422, path
    assert c.get("/api/live/recent").status_code == 200


def test_normal_event_times_are_still_accepted(login):
    c = login("analyst@a.example"); now = time.time() / 60.0
    for t in ("0", "15", str(now), "2026-11-24T10:00:00+05:30"):
        assert c.post("/api/correlate", json={"events": [{"channel": "sms", "text": "Lunch at one?", "time": t}]}).status_code == 200, t


def test_a_feed_row_with_an_infinite_time_cannot_break_the_feed(login, world):
    c = login("analyst@a.example"); db = M.session()
    row = M.MessageLog(org_id=world["org_a"], at=float("inf"), received_at=time.time(), channel="sms", source="test", origin="", recipient_label="inf.row@a.example",
                       recipient_ref="infrow", score=0.1, label="ham", assessed=True, indicators="[]")
    db.add(row); db.commit(); rid = row.id
    try:
        r = c.get("/api/live/recent?limit=500"); assert r.status_code == 200
        got = next(m for m in r.json() if m["id"] == rid); assert abs(got["at"] - time.time()) < 60        # shows when it was received
    finally:
        db.delete(db.get(M.MessageLog, rid)); db.commit(); db.close()


def test_half_a_unicode_character_is_scored_not_a_server_error(login):
    c = login("analyst@a.example")
    r = _json(c, "/api/scan", b'{"channel":"sms","text":' + HALF_A_CHARACTER + b'}'); assert r.status_code == 200 and 0 <= r.json()["score"] <= 1
    r = _json(c, "/api/correlate", b'{"events":[{"channel":"sms","text":' + HALF_A_CHARACTER + b'}]}'); assert r.status_code == 200 and r.json()["status"] == "ASSESSED"
    r = _json(c, "/api/events", b'{"recipient":"half\\ud800char@a.example","events":[{"channel":"sms","text":' + HALF_A_CHARACTER + b'}]}'); assert r.status_code == 200
    assert c.get("/api/live/recent").status_code == 200


def test_half_a_unicode_character_through_the_sms_webhook(login, anon):
    key = _key(login)
    r = anon.post("/api/v1/hooks/sms", content=b'{"from":"+919000044444","to":"hook.half@a.example","text":' + HALF_A_CHARACTER + b'}',
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    assert r.status_code == 200, r.text


def test_an_email_with_broken_header_bytes_is_recorded(login, anon):
    key = _key(login)
    raw = (b"From: Broken \xff\xfe <sender@bad-mail.example>\r\nTo: broken.headers@a.example\r\nSubject: Parcel \xff held\r\nMessage-ID: <\xff\xfe-1@bad-mail.example>\r\n"
           b"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\nPay the fee \xff\xfe at http://parcel-redelivery.info/confirm\r\n")
    r = anon.post("/api/v1/hooks/email?recipient=broken.headers@a.example", content=raw, headers={"Authorization": f"Bearer {key}", "Content-Type": "message/rfc822"})
    assert r.status_code == 200 and r.json()["status"] == "recorded", r.text


def _chunks(n):
    sent = 0
    while sent < n:
        yield b"x" * 65536; sent += 65536


def test_a_chunked_body_over_the_limit_is_refused(anon):
    r = anon.post("/api/auth/login", content=_chunks(3_000_000), headers={"Content-Type": "application/json"})
    assert "content-length" not in r.request.headers and r.status_code == 413


def test_a_small_chunked_body_is_still_read(anon):
    def small(): yield b'{"email":"nobody@a.example",'; yield b'"password":"wrong-password"}'
    assert anon.post("/api/auth/login", content=small(), headers={"Content-Type": "application/json"}).status_code == 401
