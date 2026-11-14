"""Test setup: a throw-away data folder, the app, and a small world of two client organisations with users of every role.
The password below is a test value for this test database only."""
import os, sys, tempfile
from pathlib import Path
import pytest

APP = Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="mcpd_test_")
os.environ.update({"MCPD_DATA_DIR": TMP, "MCPD_PURGE_INTERVAL_HOURS": "0", "MCPD_IGNORE_ENV_FILE": "1"})
for k in ("MCPD_DATABASE_URL", "MCPD_MASTER_KEY", "MCPD_SECURE_COOKIES"): os.environ.pop(k, None)
sys.path.insert(0, str(APP / "backend"))

from fastapi.testclient import TestClient          # noqa: E402
from server import db as M                          # noqa: E402
from server.main import app                         # noqa: E402
from server.security import hash_password, limiter  # noqa: E402

PW = "test-only-Passw0rd"
M.init_db()


def _world():
    db = M.session(); h = hash_password(PW); w = {}
    db.add(M.User(org_id=None, email="consultant@test.example", name="Consultant", role="superadmin", password_hash=h))
    for tag in ("a", "b"):
        o = M.Org(name=f"Org {tag.upper()}", slug=f"org-{tag}"); db.add(o); db.flush(); w[f"org_{tag}"] = o.id
        for role in ("admin", "analyst", "viewer"):
            u = M.User(org_id=o.id, email=f"{role}@{tag}.example", name=f"{role} {tag}", role=role, password_hash=h); db.add(u); db.flush(); w[f"{role}_{tag}"] = u.id
    db.commit(); db.close(); return w


WORLD = _world()


@pytest.fixture
def world(): return WORLD


@pytest.fixture
def login():
    def go(email, password=PW):
        limiter.reset(); c = TestClient(app)
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]; c.me = r.json(); return c
    return go


@pytest.fixture
def anon(): return TestClient(app)
