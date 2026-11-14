"""Messages pushed in as they arrive (SMS gateway, mail server) and alerts pushed out (alert webhook). Every message here is made up."""
import base64, hashlib, hmac, json, time
from fakes import Receiver, made_up_email, wait_for


def _key(login, email="admin@a.example", name="SMS gateway"):
    ad = login(email); return ad, ad.post("/api/admin/api-keys", json={"name": name}).json()["key"]


def _feed(c, recipient): return [m for m in c.get("/api/live/recent?limit=500").json() if m["recipient"] == recipient]


def test_sms_webhook_takes_json_and_links(login, anon):
    ad, key = _key(login)
    r = anon.post("/api/v1/hooks/sms", headers={"Authorization": f"Bearer {key}"},
                  json={"from": "+91 90000 11111", "to": "field.agent@a.example", "timestamp": int(time.time() * 1000),
                        "text": "Your parcel is held at the depot. Pay the redelivery fee today at http://parcel-redelivery.info/confirm"})
    assert r.status_code == 200, r.text
    assert [e["channel"] for e in r.json()["events"]] == ["sms", "url"]
    rows = _feed(ad, "field.agent@a.example")
    assert {m["source"] for m in rows} == {"sms-hook"} and {m["origin"] for m in rows} == {"SMS gateway"} and abs(rows[0]["at"] - time.time()) < 60


def test_twilio_style_form_with_basic_auth(login, anon):
    ad, key = _key(login, name="Twilio number")
    auth = base64.b64encode(f"twilio:{key}".encode()).decode()
    r = anon.post("/api/v1/hooks/sms?recipient=desk@a.example", content="From=%2B919000022222&To=%2B14155550100&Body=Hi+team%2C+lunch+at+1%3F",
                  headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml") and "<Response>" in r.text
    row = _feed(ad, "desk@a.example")[0]
    assert row["channel"] == "sms" and row["origin"] == "Twilio number" and row["score"] < 0.5


def test_a_report_smishing_number_makes_the_reporter_the_recipient(login, anon):
    ad, key = _key(login, name="Report number")
    auth = base64.b64encode(f"report:{key}".encode()).decode()
    r = anon.post("/api/v1/hooks/sms?mode=reports", content="From=%2B919000033333&To=%2B14155550100&Body=Your+KYC+is+pending.+Update+now+at+http%3A%2F%2Fsbi-kyc-update.top%2Fkyc",
                  headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    rows = _feed(ad, "+919000033333")
    assert sorted(m["channel"] for m in rows) == ["sms", "url"] and not any(i.startswith("tel:+1415") for m in rows for i in m["indicators"])


def test_sms_webhook_refuses_what_it_cannot_use(login, anon):
    _, key = _key(login, name="refusals"); h = {"Authorization": f"Bearer {key}"}
    assert anon.post("/api/v1/hooks/sms", json={"text": "hi", "to": "x@a.example"}).status_code == 401
    assert anon.post("/api/v1/hooks/sms", headers=h, json={"text": "hi"}).status_code == 422                       # nobody received it
    assert anon.post("/api/v1/hooks/sms", headers={**h, "Content-Type": "text/plain"}, content="hi").status_code == 415


def test_email_webhook_records_once(login, anon):
    ad, key = _key(login, name="Mail server")
    raw = made_up_email(to="someone@a.example"); h = {"Authorization": f"Bearer {key}", "Content-Type": "message/rfc822"}
    r = anon.post("/api/v1/hooks/email?recipient=watch2@a.example", headers=h, content=raw).json()
    assert r["status"] == "recorded" and r["events"] == 2
    assert anon.post("/api/v1/hooks/email?recipient=watch2@a.example", headers=h, content=raw).json()["status"] == "duplicate"
    assert sorted(m["channel"] for m in _feed(ad, "watch2@a.example")) == ["email", "url"]
    assert anon.post("/api/v1/hooks/email?mode=inbox", headers=h, content=raw).status_code == 422                     # inbox mode needs a recipient


def test_alert_webhook_is_signed_and_holds_no_message_text(login):
    rec = Receiver(); ad = login("admin@a.example")
    try:
        assert ad.put("/api/admin/alert-webhook", json={"url": rec.url, "secret": "test-only-signing-secret"}).status_code == 200
        evs = {p["id"]: p for p in ad.get("/api/presets").json()}["TC-06"]["events"]
        evs = [{**evs[0], "text": evs[0]["text"] + " unique-hook-marker-55"}] + evs[1:]
        assert ad.post("/api/events", json={"recipient": "hooked@a.example", "events": evs}).json()["new_alerts"]
        assert rec.event.wait(10), "the alert webhook was not called"
        got = rec.got[-1]; body = got["body"]; ts = got["headers"]["x-mcpd-timestamp"]
        assert got["headers"]["x-mcpd-signature"] == "sha256=" + hmac.new(b"test-only-signing-secret", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        j = json.loads(body)
        assert j["type"] == "alert.opened" and j["recipient"] == "hooked@a.example" and j["risk"] >= 0.5 and "text" in j   # the marker changes the SMS score
        assert b"unique-hook-marker-55" not in body
        st = wait_for(lambda: (lambda s: s if s["n_sent"] >= 1 else None)(ad.get("/api/admin/alert-webhook").json()))
        assert st and st["has_secret"] and "secret" not in st and st["last_status"].startswith("delivered")
        t = ad.post("/api/admin/alert-webhook/test").json(); assert t["ok"], t
        assert json.loads(rec.got[-1]["body"])["type"] == "test"
    finally:
        ad.delete("/api/admin/alert-webhook"); rec.close()


def test_an_alert_webhook_does_not_follow_redirects():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from server.hooks_out import send

    class R(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            self.send_response(307); self.send_header("Location", "http://169.254.169.254/latest/"); self.send_header("Content-Length", "0"); self.end_headers()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), R); threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ok, line = send(f"http://127.0.0.1:{srv.server_address[1]}/hook", "", {"type": "test"})
        assert not ok and "307" in line
    finally:
        srv.shutdown(); srv.server_close()


def test_private_addresses_are_refused_unless_the_operator_allows_them(login, monkeypatch):
    monkeypatch.delenv("MCPD_ALLOW_PRIVATE_HOSTS")
    ad = login("admin@a.example")
    assert ad.put("/api/admin/alert-webhook", json={"url": "http://127.0.0.1:9/hook"}).status_code == 422
    assert ad.put("/api/admin/alert-webhook", json={"url": "https://10.0.0.5/hook"}).status_code == 422
    r = ad.post("/api/admin/connectors", json={"kind": "imap", "name": "x", "secret": "x", "config": {"host": "127.0.0.1", "username": "a@a.example"}})
    assert r.status_code == 422 and "private" in r.json()["detail"]
