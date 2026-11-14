"""Security headers, request limits, the public routes, the dashboard and the reports."""
from server.security import csv_safe, limiter


def test_security_headers(anon):
    h = anon.get("/api/health").headers
    assert "default-src 'self'" in h["content-security-policy"] and h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert h["cache-control"] == "no-store"


def test_large_bodies_are_refused(anon):
    assert anon.post("/api/public/contact", content=b"x" * (3 * 1024 * 1024), headers={"content-type": "application/json"}).status_code == 413


def test_model_card_states_limits_and_simulation(anon):
    j = anon.get("/api/public/model-card").json()
    assert j["correlation"]["simulated"] is True and "simulated" in j["correlation"]["note"]
    assert "voice calls" in j["not_assessed"] and any("not as safe" in x or "never as safe" in x for x in j["limitations"])


def test_contact_form_validates_and_is_rate_limited(anon):
    limiter.reset()
    assert anon.post("/api/public/contact", json={"name": "A", "email": "not-an-email"}).status_code == 422
    limiter.reset()                                  # every attempt counts, a refused one too
    codes = [anon.post("/api/public/contact", json={"name": "A", "email": "a@b.example", "message": "pilot?"}).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_dashboard_and_csv_report(login):
    c = login("analyst@a.example")
    evs = {p["id"]: p for p in c.get("/api/presets").json()}["TC-06"]["events"]
    c.post("/api/events", json={"recipient": "=HYPERLINK(\"http://x\")", "events": evs})
    d = c.get("/api/dashboard").json()
    assert d["alerts_open"] >= 1 and len(d["alerts_per_day"]) == 14
    assert sum(d["messages_by_channel_30d"].values()) == d["messages_checked_30d"]        # per-channel counts add up to the total
    csv = c.get("/api/reports/alerts.csv?days=30").text
    assert csv.splitlines()[0].startswith("case_id,") and "'=HYPERLINK" in csv
    s = c.get("/api/reports/summary?days=30").json()
    assert s["alerts"] >= 1 and s["limitations"]


def test_csv_safe():
    assert csv_safe("=1+1") == "'=1+1" and csv_safe("plain") == "plain" and csv_safe(None) == ""


def test_unknown_api_route_is_404_not_the_app(anon):
    assert anon.get("/api/does-not-exist").status_code == 404
