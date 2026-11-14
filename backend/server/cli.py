"""Administration from the command line (run from the app folder):
  python -m server.cli init                                   create the database and the master key
  python -m server.cli create-superadmin --email you@firm.example [--name "..."]      the consultant's account (asks for a password)
  python -m server.cli create-org --name "Client Ltd"
  python -m server.cli create-user --org client-ltd --email admin@client.example --role admin
  python -m server.cli seed-demo                              a demo organisation with demo users and hand-written demo cases (not real data)
  python -m server.cli purge                                  run the retention purge for every organisation now
Passwords are read from the terminal (never from arguments), or from MCPD_INIT_PASSWORD for unattended installs."""
import argparse, getpass, os, secrets, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from server import db as M
from server.config import get_settings
from server.routes_admin import NewUser, create_user
from server.routes_super import create_org
from server.security import hash_password, password_problem


def _password(email):
    pw = os.environ.get("MCPD_INIT_PASSWORD")
    if pw is None:
        pw = getpass.getpass(f"Password for {email}: ")
        if pw != getpass.getpass("Again: "): sys.exit("the two passwords differ")
    why = password_problem(pw, email)
    if why: sys.exit(f"choose another password: {why}")
    return pw


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("create-superadmin"); p.add_argument("--email", required=True); p.add_argument("--name", default="")
    p = sub.add_parser("create-org"); p.add_argument("--name", required=True)
    p = sub.add_parser("create-user"); p.add_argument("--org", required=True); p.add_argument("--email", required=True); p.add_argument("--name", default="")
    p.add_argument("--role", default="analyst", choices=("viewer", "analyst", "admin"))
    sub.add_parser("seed-demo"); sub.add_parser("purge")
    a = ap.parse_args()
    M.init_db(); get_settings().master_key; db = M.session()
    if a.cmd == "init":
        print(f"database ready ({get_settings().database_url.split('://')[0]}), data folder {get_settings().data_dir}")
    elif a.cmd == "create-superadmin":
        email = a.email.strip().lower()
        if db.scalar(select(M.User).where(M.User.email == email)): sys.exit("an account with this email already exists")
        db.add(M.User(org_id=None, email=email, name=a.name, role="superadmin", password_hash=hash_password(_password(email)))); db.commit()
        print(f"consultant account created: {email}")
    elif a.cmd == "create-org":
        o = create_org(db, a.name); print(f"organisation created: {o.name} (slug {o.slug}, id {o.id})")
    elif a.cmd == "create-user":
        o = db.scalar(select(M.Org).where(M.Org.slug == a.org))
        if o is None: sys.exit(f"no organisation with slug {a.org}")
        u = create_user(db, o.id, NewUser(email=a.email, name=a.name, role=a.role, password=_password(a.email)), None)
        print(f"user created: {u.email} ({u.role}) in {o.name}")
    elif a.cmd == "seed-demo":
        seed_demo(db)
    elif a.cmd == "purge":
        from server.services import purge_org
        for o in db.scalars(select(M.Org)): print(o.slug, purge_org(db, o))


def seed_demo(db):
    """A demo organisation for showing the app. Its events are the CP1 demo cases and Indian stories: hand-written, not real messages, not a
    test set. The demo passwords are random and written to data/demo_credentials.txt (outside git)."""
    from server import engine
    from server.deps import Ctx
    from server.services import EventsIn, record_events
    if db.scalar(select(M.Org).where(M.Org.slug == "demo-client")): sys.exit("the demo organisation already exists")
    o = create_org(db, "Demo Client"); lines = ["Demo accounts (local demo only; delete with the data folder)."]
    su = db.scalar(select(M.User).where(M.User.role == "superadmin"))
    if su is None:
        pw = secrets.token_urlsafe(12); db.add(M.User(org_id=None, email="consultant@demo.test", name="Demo Consultant", role="superadmin", password_hash=hash_password(pw)))
        db.commit(); lines.append(f"consultant@demo.test  {pw}  (consultant: all organisations)")
    for email, name, role in (("admin@demo.test", "Asha (admin)", "admin"), ("analyst@demo.test", "Ravi (analyst)", "analyst"), ("viewer@demo.test", "Meera (viewer)", "viewer")):
        pw = secrets.token_urlsafe(12); create_user(db, o.id, NewUser(email=email, name=name, role=role, password=pw), None); lines.append(f"{email}  {pw}  ({role})")
    P = {p["id"]: p for p in engine.presets()}; ctx = Ctx(user=None, org=o)
    for rec, pid in (("finance.desk@demo.test", "TC-04"), ("ops.lead@demo.test", "TC-06"), ("hr.team@demo.test", "IN-01"), ("sales.rep@demo.test", "IN-02"),
                     ("intern@demo.test", "IN-03"), ("ops.lead@demo.test", "IN-04"), ("research@demo.test", "TC-05")):
        import time as _t
        ts = [float(e.get("time") or i) for i, e in enumerate(P[pid]["events"])]; now_min = _t.time() / 60.0
        evs = [{**{k: e.get(k) for k in ("channel", "text", "subject", "identity")}, "time": str(now_min - (max(ts) - t))} for e, t in zip(P[pid]["events"], ts)]
        record_events(db, ctx, EventsIn(recipient=rec, events=evs), "demo")
    p = get_settings().data_dir / "demo_credentials.txt"; p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"demo organisation created with users and hand-written demo events; passwords in {p}")


if __name__ == "__main__":
    main()
