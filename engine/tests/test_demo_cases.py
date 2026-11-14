"""TC-01 to TC-08, the eight demo cases. HAND-WRITTEN, NOT A TEST SET: these check that the demo reproduces, nothing more.
The expected values are the ones recorded for v2 in PROJECT_STATE.md (15 Oct) and CP1_FINISH_TASK.md section 1.3; scores must match to 3 decimals.
Run:  python tests/test_demo_cases.py          (in-process, FastAPI TestClient)
      pytest tests/test_demo_cases.py
Set CP1_API_URL=http://127.0.0.1:8000 to run the same checks over real HTTP against a running uvicorn."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
from demo_cases import CASES

# case: (event scores, alerts alone, bundle risk, windows, shared identity tokens)
EXPECTED = {
    "TC-01": ([0.998], True, 0.998, 1, []),
    "TC-02": ([1.000], True, 1.000, 1, []),
    "TC-04": ([1.000, 0.995, 0.998], True, 1.000, 1, ["dom:sbi-kyc-update.top"]),
    "TC-05": ([0.002, 0.000, 0.000], False, 0.000, 1, ["dom:wikipedia.org"]),
    "TC-06": ([0.421, 0.451, 0.204], False, 0.595, 1, ["dom:parcel-redelivery.info"]),
    "TC-07": ([0.421, 0.451, 0.204], False, 0.451, 3, []),
    "TC-08": ([0.970, 0.031], True, 1.000, 1, ["dom:fedex.com"]),
}

_client = None
def client():
    global _client
    if _client is None:
        url = os.environ.get("CP1_API_URL")
        if url:
            import httpx
            _client = httpx.Client(base_url=url.rstrip("/"), timeout=60)
        else:
            from fastapi.testclient import TestClient
            import api
            _client = TestClient(api.app)
    return _client


def correlate(cid):
    return client().post("/correlate", json={"events": CASES[cid]["events"]})


def check(cid):
    scores, alone, risk, n_win, shared = EXPECTED[cid]
    r = correlate(cid); assert r.status_code == 200, (cid, r.status_code, r.text[:200])
    j = r.json()
    got = [round(e["score"], 3) for e in j["events"]]
    assert got == scores, (cid, "event scores", got, scores)
    assert j["single_channel_alert"] is alone, (cid, "alerts alone", j["single_channel_alert"])
    assert round(j["bundle_risk"], 3) == risk, (cid, "bundle risk", j["bundle_risk"], risk)
    assert (j["bundle_risk"] >= 0.5) is (risk >= 0.5), (cid, "alert outcome")
    assert j["n_windows"] == n_win and j["shared_identity_tokens"] == shared, (cid, j["n_windows"], j["shared_identity_tokens"])


def test_tc01_phishing_email_alone(): check("TC-01")
def test_tc02_smishing_sms_alone(): check("TC-02")
def test_tc04_kyc_campaign_one_domain(): check("TC-04")
def test_tc05_colleague_shares_an_article(): check("TC-05")
def test_tc06_weak_parcel_campaign_alerts_only_as_a_bundle(): check("TC-06")
def test_tc07_same_messages_days_apart_do_not_combine(): check("TC-07")
def test_tc08_courier_tracking_number(): check("TC-08")


def test_tc03_voice_call_is_not_assessed():
    call = CASES["TC-03"]["events"][0]
    r = client().post("/score", json={"channel": call["channel"], "text": call["text"]})
    assert r.status_code == 501, (r.status_code, r.text[:200])
    # v2 answered HTTP 501 here too. Since R2-07 (D-03) /correlate answers CANNOT_ASSESS with no risk: a call alone is never a low score.
    r = correlate("TC-03"); j = r.json()
    assert r.status_code == 200 and j["status"] == "CANNOT_ASSESS" and j["bundle_risk"] is None and j["events"][0]["assessed"] is False, (r.status_code, r.text[:200])


if __name__ == "__main__":
    ok = True
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try: fn(); print("PASS", name)
        except Exception as e: ok = False; print("FAIL", name, "-", repr(e)[:400])
    print("ALL PASSED" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
