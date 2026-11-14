"""Sign-in, sessions, CSRF, lockout, password rules, and what each role may do."""
from conftest import PW
from server import db as M
from server.security import hash_password, limiter


def test_wrong_password_and_unknown_user_look_the_same(anon):
    limiter.reset()
    a = anon.post("/api/auth/login", json={"email": "analyst@a.example", "password": "nope-nope-nope"})
    b = anon.post("/api/auth/login", json={"email": "nobody@a.example", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_session_cookie_is_http_only_and_strict(anon):
    limiter.reset(); r = anon.post("/api/auth/login", json={"email": "viewer@a.example", "password": PW})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc


def test_state_change_needs_the_csrf_token(login):
    c = login("analyst@a.example"); good = c.headers.pop("X-CSRF-Token")
    assert c.post("/api/scan", json={"channel": "sms", "text": "hi"}).status_code == 403
    c.headers["X-CSRF-Token"] = good
    assert c.post("/api/scan", json={"channel": "sms", "text": "hi"}).status_code == 200


def test_lockout_after_repeated_failures(anon):
    db = M.session(); db.add(M.User(org_id=1, email="lock@a.example", role="analyst", password_hash=hash_password(PW))); db.commit(); db.close()
    limiter.reset()
    for _ in range(5): anon.post("/api/auth/login", json={"email": "lock@a.example", "password": "wrong-password-x"})
    assert anon.post("/api/auth/login", json={"email": "lock@a.example", "password": PW}).status_code == 423


def test_logout_ends_the_session(login):
    c = login("viewer@a.example")
    assert c.get("/api/auth/me").json()["signed_in"] is True
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").json() == {"signed_in": False}
    assert c.get("/api/dashboard").status_code == 401


def test_weak_passwords_are_refused(login):
    c = login("admin@a.example")
    r = c.post("/api/admin/users", json={"email": "new@a.example", "role": "analyst", "password": "short"})
    assert r.status_code == 422


def test_roles(login, world):
    v, an, ad, su = login("viewer@a.example"), login("analyst@a.example"), login("admin@a.example"), login("consultant@test.example")
    assert v.get("/api/dashboard").status_code == 200
    assert v.post("/api/scan", json={"channel": "sms", "text": "hello"}).status_code == 403          # viewers read only
    assert an.post("/api/scan", json={"channel": "sms", "text": "hello"}).status_code == 200
    assert an.get("/api/admin/users").status_code == 403                                             # analysts do not manage people
    assert ad.get("/api/admin/users").status_code == 200
    assert ad.get("/api/super/orgs").status_code == 403                                              # client admins never see other clients
    assert su.get("/api/super/orgs").status_code == 200
    assert su.get("/api/alerts").status_code == 409                                                  # the consultant picks an organisation first
    su.post("/api/auth/switch-org", json={"org_id": world["org_a"]})
    assert su.get("/api/alerts").status_code == 200


def test_admin_cannot_promote_to_superadmin_or_lock_themselves_out(login, world):
    ad = login("admin@a.example")
    assert ad.post("/api/admin/users", json={"email": "x@a.example", "role": "superadmin", "password": "a-good-passw0rd"}).status_code == 422
    assert ad.patch(f"/api/admin/users/{world['admin_a']}", json={"role": "viewer"}).status_code == 409
