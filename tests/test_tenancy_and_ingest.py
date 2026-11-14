"""Client organisations never see each other's data; API keys work only for their own organisation; alerts become triage cases."""
import sqlite3
from conftest import TMP
from server import engine


def weak_campaign(c):
    return {p["id"]: p for p in c.get("/api/presets").json()}["TC-06"]["events"]


def test_events_raise_one_alert_case_with_its_indicator(login):
    c = login("analyst@a.example")
    r = c.post("/api/events", json={"recipient": "ops@a.example", "events": weak_campaign(c)}).json()
    assert len(r["new_alerts"]) == 1 and r["new_alerts"][0]["shared_identity_tokens"] == ["dom:parcel-redelivery.info"]
    case = c.get(f"/api/alerts/{r['new_alerts'][0]['case_id']}").json()
    assert case["status"] == "new" and case["recipient"] == "ops@a.example" and "dom:parcel-redelivery.info" in case["indicators"]
    assert len(case["campaign"]["timeline"]) == 3


def test_organisations_are_separate(login):
    a, b = login("analyst@a.example"), login("admin@b.example")
    r = a.post("/api/events", json={"recipient": "same.person@x.example", "events": weak_campaign(a)}).json()
    cid = r["new_alerts"][0]["case_id"]
    assert b.get(f"/api/alerts/{cid}").status_code == 404
    assert all(x["recipient"] != "same.person@x.example" for x in b.get("/api/alerts").json())
    rb = b.post("/api/events", json={"recipient": "same.person@x.example", "events": weak_campaign(b)}).json()
    assert rb["recipient_ref"] != r["recipient_ref"]                        # each organisation has its own HMAC key
    assert engine.org_key(1) != engine.org_key(2)


def test_api_key_ingest_and_revoke(login, anon):
    ad = login("admin@a.example")
    k = ad.post("/api/admin/api-keys", json={"name": "mail connector"}).json()
    hdr = {"Authorization": f"Bearer {k['key']}"}
    r = anon.post("/api/v1/events", headers=hdr, json={"recipient": "api.user@a.example", "events": weak_campaign(ad)})
    assert r.status_code == 200 and r.json()["new_alerts"]
    pulled = anon.get("/api/v1/alerts", headers=hdr).json()
    assert any(x["recipient"] == "api.user@a.example" for x in pulled)
    other = login("admin@b.example").post("/api/admin/api-keys", json={"name": "b"}).json()["key"]
    assert all(x["recipient"] != "api.user@a.example" for x in anon.get("/api/v1/alerts", headers={"Authorization": f"Bearer {other}"}).json())
    ad.delete(f"/api/admin/api-keys/{k['id']}")
    assert anon.post("/api/v1/scan", headers=hdr, json={"channel": "sms", "text": "hi"}).status_code == 401
    assert anon.post("/api/v1/scan", json={"channel": "sms", "text": "hi"}).status_code == 401


def test_triage_assign_note_and_close(login, world):
    an = login("analyst@a.example")
    cid = an.post("/api/events", json={"recipient": "triage@a.example", "events": weak_campaign(an)}).json()["new_alerts"][0]["case_id"]
    assert an.patch(f"/api/alerts/{cid}", json={"assignee_id": world["viewer_a"]}).status_code == 422      # viewers cannot own alerts
    assert an.patch(f"/api/alerts/{cid}", json={"assignee_id": world["analyst_b"]}).status_code == 422     # nor can another client's analyst
    assert an.patch(f"/api/alerts/{cid}", json={"assignee_id": world["analyst_a"], "status": "investigating"}).json()["status"] == "investigating"
    assert an.post(f"/api/alerts/{cid}/notes", json={"text": "Domain registered yesterday; blocking."}).status_code == 200
    assert an.patch(f"/api/alerts/{cid}", json={"status": "confirmed"}).status_code == 200
    j = an.get(f"/api/alerts/{cid}").json()
    assert j["status"] == "confirmed" and j["notes"][0]["text"].startswith("Domain") and j["assignee"]["id"] == world["analyst_a"]


def test_nothing_readable_is_kept_in_the_event_store(login):
    c = login("analyst@a.example"); secret = "unique-marker-7781 parcel-redelivery.info/confirm"
    evs = weak_campaign(c); evs[0] = {**evs[0], "text": evs[0]["text"] + " " + secret}
    c.post("/api/events", json={"recipient": "private.person@a.example", "events": evs})
    raw = b"".join(p.read_bytes() for p in (__import__("pathlib").Path(TMP) / "orgs").rglob("*.db"))
    assert b"private.person@a.example" not in raw and b"unique-marker-7781" not in raw and b"parcel-redelivery.info" not in raw
    db = sqlite3.connect(str(__import__("pathlib").Path(TMP) / "app.db"))
    assert not any("unique-marker-7781" in str(row) for row in db.execute("SELECT * FROM scan_log"))


def test_without_labels_the_case_keeps_no_name_or_indicator(login):
    ad = login("admin@b.example"); ad.patch("/api/admin/settings", json={"keep_labels": False})
    r = ad.post("/api/events", json={"recipient": "hidden@b.example", "events": weak_campaign(ad)}).json()
    case = ad.get(f"/api/alerts/{r['new_alerts'][0]['case_id']}").json()
    assert case["recipient"].startswith("recipient ") and all("(hidden)" in i for i in case["indicators"])
    ad.patch("/api/admin/settings", json={"keep_labels": True})


def test_purge_removes_old_cases_and_events(login):
    ad = login("admin@a.example")
    ad.post("/api/events", json={"recipient": "purge.me@a.example", "events": weak_campaign(ad)})
    r = ad.post("/api/admin/purge", json={"older_than_days": 0}).json()
    assert r["events_deleted"] >= 3 and r["alert_cases_deleted"] >= 1
    assert ad.get("/api/alerts").json() == []
