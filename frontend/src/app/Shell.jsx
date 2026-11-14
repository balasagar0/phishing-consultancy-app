import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { can, useAuth } from "../auth.jsx";
import { ErrorBox } from "../ui.jsx";

export function Login() {
  const { me, login } = useAuth(); const nav = useNavigate(); const loc = useLocation();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [state, setState] = useState({ busy: false, error: null });
  if (me) return <Navigate to={loc.state?.from || "/app"} replace />;
  const submit = async (e) => {
    e.preventDefault(); setState({ busy: true, error: null });
    try { await login(email, password); nav(loc.state?.from || "/app", { replace: true }); }
    catch (err) { setState({ busy: false, error: err }); }
  };
  return (
    <div className="login-page">
      <form className="card" onSubmit={submit}>
        <Link to="/" className="brand" style={{ marginBottom: 16 }}><img src="/icon.svg" alt="" />Phishing detection</Link>
        <h1 style={{ fontSize: "1.4rem" }}>Sign in</h1>
        <label className="field">Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" autoFocus /></label>
        <label className="field">Password<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
        <ErrorBox error={state.error} />
        <button className="btn primary" style={{ width: "100%", justifyContent: "center", marginTop: 10 }} disabled={state.busy}>{state.busy ? "Signing in…" : "Sign in"}</button>
        <p className="small muted" style={{ marginTop: 14 }}>Accounts are created by your organisation's admin. Forgotten password: ask your admin to reset it.</p>
      </form>
    </div>
  );
}

export function RequireAuth() {
  const { me, loading } = useAuth(); const loc = useLocation();
  if (loading) return <p className="muted" style={{ padding: 24 }}>Loading…</p>;
  if (!me) return <Navigate to="/app/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <Outlet />;
}

function OrgPicker() {
  const { me, switchOrg } = useAuth(); const nav = useNavigate(); const [err, setErr] = useState(null);
  if (me.user.role !== "superadmin") return <strong>{me.org?.name}</strong>;
  return (
    <span className="row">
      <label className="sr" htmlFor="org">Organisation</label>
      <select id="org" value={me.org?.id || ""} style={{ width: "auto" }}
        onChange={async (e) => { try { await switchOrg(e.target.value ? Number(e.target.value) : null); nav(e.target.value ? "/app" : "/app/consultant"); } catch (x) { setErr(x); } }}>
        <option value="">— no organisation (consultant view) —</option>
        {me.orgs.map((o) => <option key={o.id} value={o.id}>{o.name}{o.active ? "" : " (disabled)"}</option>)}
      </select>
      <ErrorBox error={err} />
    </span>
  );
}

export function Shell() {
  const { me, logout } = useAuth(); const [open, setOpen] = useState(false); const loc = useLocation(); const nav = useNavigate();
  useEffect(() => setOpen(false), [loc.pathname]);
  const hasOrg = !!me.org;
  const L = (to, label, end) => <NavLink to={to} end={end}>{label}</NavLink>;
  return (
    <div className="shell">
      <aside className={`side ${open ? "open" : ""}`}>
        <Link to="/app" className="brand"><img src="/icon.svg" alt="" />Phishing detection</Link>
        <nav aria-label="App">
          {hasOrg && (<>
            {L("/app", "Dashboard", true)}
            {can(me, "analyst") && L("/app/scan", "Scan a message")}
            {can(me, "analyst") && L("/app/investigate", "Investigate")}
            {L("/app/alerts", "Alerts")}
            {L("/app/campaigns", "Campaigns")}
            {L("/app/reports", "Reports")}
          </>)}
          {hasOrg && can(me, "admin") && (<><div className="group">Organisation</div>{L("/app/integrations", "Integrations & API")}{L("/app/settings", "Settings & people")}</>)}
          {me.user.role === "superadmin" && (<><div className="group">Consultant</div>{L("/app/consultant", "Client organisations")}</>)}
          <div className="group">Help</div>
          {L("/app/model", "What the models can do")}
          {L("/app/account", "My account")}
          <Link to="/">Website</Link>
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <span className="row">
            <button className="btn small menu-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu">☰ Menu</button>
            <OrgPicker />
          </span>
          <span className="row small">
            <span>{me.user.name || me.user.email} · <span className="badge neutral">{me.user.role}</span></span>
            <button className="btn small" onClick={async () => { await logout(); nav("/app/login"); }}>Sign out</button>
          </span>
        </header>
        <div className="content">
          {!hasOrg && !loc.pathname.startsWith("/app/consultant") && !loc.pathname.startsWith("/app/model") && !loc.pathname.startsWith("/app/account")
            ? <Navigate to="/app/consultant" replace /> : <Outlet />}
        </div>
      </div>
    </div>
  );
}

export function PageHead({ title, children, actions }) {
  return <div className="page-head"><div><h1>{title}</h1>{children && <p>{children}</p>}</div>{actions && <div className="row">{actions}</div>}</div>;
}
