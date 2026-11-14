"""The app scores exactly as cp1-final does: the eight demo cases (hand-written, not a test set) through the app's own routes give the scores
the CP1 project's tests/test_demo_cases.py expects, to three decimals, and the pinned engine matches its manifest."""
import ast, subprocess, sys
from pathlib import Path
from conftest import APP

src = (APP / "engine" / "tests" / "test_demo_cases.py").read_text(encoding="utf-8")
EXPECTED = ast.literal_eval(next(n.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "EXPECTED"))


def test_engine_files_match_cp1_final():
    r = subprocess.run([sys.executable, str(APP / "scripts" / "sync_engine.py"), "--verify"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_demo_cases_score_as_in_cp1_final(login):
    c = login("analyst@a.example"); P = {p["id"]: p for p in c.get("/api/presets").json()}
    for cid, (scores, alone, risk, n_win, shared) in EXPECTED.items():
        j = c.post("/api/correlate", json={"events": P[cid]["events"]}).json()
        assert [round(e["score"], 3) for e in j["events"]] == scores, cid
        assert j["single_channel_alert"] == alone, cid
        assert round(j["bundle_risk"], 3) == risk, cid
        assert j["n_windows"] == n_win, cid
        assert j["shared_identity_tokens"] == shared, cid


def test_a_call_is_never_safe(login):
    c = login("analyst@a.example"); P = {p["id"]: p for p in c.get("/api/presets").json()}
    j = c.post("/api/correlate", json={"events": P["TC-03"]["events"]}).json()
    assert j["status"] == "CANNOT_ASSESS" and j["bundle_risk"] is None
    assert c.post("/api/scan", json={"channel": "call", "text": "a call"}).status_code == 501
