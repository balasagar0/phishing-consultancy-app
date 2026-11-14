import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { CopyButton, Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui.jsx";
import { PageHead } from "./Shell.jsx";

export function useAction() {
  const [s, set] = useState({ busy: false, error: null, ok: null });
  const run = async (fn, ok = "Saved.") => { set({ busy: true, error: null, ok: null }); try { const r = await fn(); set({ busy: false, error: null, ok }); return r; } catch (e) { set({ busy: false, error: e, ok: null }); return null; } };
  return [s, run];
}

export function Integrations() {
  const keys = useLoad(() => api("/api/admin/api-keys"), []); const [name, setName] = useState(""); const [fresh, setFresh] = useState(null); const [s, run] = useAction();
  const origin = window.location.origin;
  const curl = `curl -X POST ${origin}/api/v1/events \\
  -H "Authorization: Bearer <your key>" -H "Content-Type: application/json" \\
  -d '{"recipient": "employee@client.example", "events": [
        {"channel": "sms", "text": "Your parcel is held. Pay at parcel-redelivery.info/confirm", "identity": "+91 90000 00000"},
        {"channel": "url", "text": "http://parcel-redelivery.info/track?id=1"}]}'`;
  return (
    <>
      <PageHead title="Integrations & API">Let a mailbox, an SMS gateway or a SIEM send messages in and pull alerts out, with an API key.</PageHead>
      <div className="grid two">
        <div className="card stack">
          <h3>API keys</h3>
          <form className="row" onSubmit={async (e) => { e.preventDefault(); const r = await run(() => api("/api/admin/api-keys", { method: "POST", body: { name } }), "Key created."); if (r) { setFresh(r); setName(""); keys.reload(); } }}>
            <input className="grow" placeholder="What will use it, e.g. Reporting mailbox" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} style={{ flex: "1 1 200px", width: "auto" }} />
            <button className="btn primary" disabled={!name.trim() || s.busy}>Create key</button>
          </form>
          <ErrorBox error={s.error} />
          {fresh && <div className="stack"><div className="note warn">{fresh.note}</div><div className="keybox mono">{fresh.key}</div><CopyButton text={fresh.key} label="Copy key" /></div>}
          {keys.loading && !keys.data ? <Loading /> : <ErrorBox error={keys.error} />}
          {keys.data && (keys.data.length ? (
            <div className="table-wrap"><table><thead><tr><th>Name</th><th>Starts with</th><th>Last used</th><th></th></tr></thead>
              <tbody>{keys.data.map((k) => <tr key={k.id}><td>{k.name}</td><td className="mono">{k.prefix}…</td><td className="small">{k.revoked ? <span className="badge neutral">revoked</span> : fmtTime(k.last_used_at)}</td>
                <td>{!k.revoked && <button className="btn small danger" onClick={async () => { if (window.confirm(`Revoke "${k.name}"? Anything using it stops working.`)) { await run(() => api(`/api/admin/api-keys/${k.id}`, { method: "DELETE" }), "Revoked."); keys.reload(); } }}>Revoke</button>}</td></tr>)}</tbody></table></div>
          ) : <Empty>No keys yet.</Empty>)}
        </div>
        <div className="card stack">
          <h3>Send messages in</h3>
          <p className="small">Each request is one person's messages. Up to 20 messages; the server's clock is used when no time is given. A campaign that reaches the alert line opens an alert case here.</p>
          <pre>{curl}</pre>
          <h3>Pull alerts out</h3>
          <pre>{`curl ${origin}/api/v1/alerts?status=new -H "Authorization: Bearer <your key>"`}</pre>
          <h3>Score one message</h3>
          <pre>{`curl -X POST ${origin}/api/v1/scan -H "Authorization: Bearer <your key>" \\
  -H "Content-Type: application/json" -d '{"channel": "url", "text": "http://example.test/login"}'`}</pre>
          <p className="small muted">To have messages arrive by themselves, as they are received, add a mailbox or set up the SMS and email webhooks
            under <Link to="/app/connectors">Connectors</Link>. For a mailbox the server cannot reach, <code>connectors/imap_connector.py</code> in the app folder
            reads it from inside your network and sends each message in. Keys allow 120 requests a minute (600 for webhooks).</p>
        </div>
      </div>
    </>
  );
}

const ROLES = ["viewer", "analyst", "admin"];

export function Settings() {
  const { me, refresh } = useAuth(); const st = useLoad(() => api("/api/admin/settings"), []); const users = useLoad(() => api("/api/admin/users"), []);
  const audit = useLoad(() => api("/api/admin/audit"), []); const [s, run] = useAction();
  const [nu, setNu] = useState({ email: "", name: "", role: "analyst", password: "" }); const [days, setDays] = useState("");
  const save = async (patch) => { await run(() => api("/api/admin/settings", { method: "PATCH", body: patch })); st.reload(); refresh(); };
  const editUser = async (u, patch, msg) => { await run(() => api(`/api/admin/users/${u.id}`, { method: "PATCH", body: patch }), msg); users.reload(); };
  return (
    <>
      <PageHead title="Settings & people">For {me.org.name}. Admins only.</PageHead>
      {s.ok && <div className="success" style={{ marginBottom: 12 }}>{s.ok}</div>}<ErrorBox error={s.error} />
      <div className="grid two">
        <div className="card stack">
          <h3>Privacy and retention</h3>
          {st.data ? (<>
            <label className="field">Keep data for (days)<input type="number" min={1} max={3650} defaultValue={st.data.retention_days} onBlur={(e) => Number(e.target.value) !== st.data.retention_days && save({ retention_days: Number(e.target.value) })} />
              <span className="hint">Older events, alerts and logs are deleted automatically every day.</span></label>
            <label className="check"><input type="checkbox" checked={st.data.keep_labels} onChange={(e) => save({ keep_labels: e.target.checked })} />
              <span>Show recipient names and plain indicators on alert cases<br /><span className="small muted">Off: alerts show only a hashed reference and hide indicators. Analysts lose context.</span></span></label>
            <label className="check"><input type="checkbox" checked={st.data.store_content} onChange={(e) => save({ store_content: e.target.checked })} />
              <span>Store message text in the event store<br /><span className="small muted">Off by default. On: analysts see the text in timelines, and the text is personal data you must protect and delete.</span></span></label>
            <div className="row"><input type="number" min={0} placeholder="days" value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 110 }} aria-label="Purge older than days" />
              <button className="btn danger" onClick={async () => { if (window.confirm(`Delete everything older than ${days || st.data.retention_days} days now? This cannot be undone.`)) { await run(() => api("/api/admin/purge", { method: "POST", body: days === "" ? {} : { older_than_days: Number(days) } }), "Purged."); audit.reload(); } }}>Purge now</button></div>
          </>) : <ErrorBox error={st.error} />}
        </div>
        <div className="card stack">
          <h3>Add a person</h3>
          <form onSubmit={async (e) => { e.preventDefault(); const r = await run(() => api("/api/admin/users", { method: "POST", body: nu }), "Person added. Share the password with them privately; they can change it under My account."); if (r) { setNu({ email: "", name: "", role: "analyst", password: "" }); users.reload(); } }}>
            <div className="row"><label className="field grow">Email<input type="email" required value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} /></label>
              <label className="field grow">Name<input value={nu.name} onChange={(e) => setNu({ ...nu, name: e.target.value })} /></label></div>
            <div className="row"><label className="field" style={{ width: 140 }}>Role<select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></label>
              <label className="field grow">First password <span className="hint">at least 10 characters</span><input type="password" required value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} autoComplete="new-password" /></label></div>
            <button className="btn primary" disabled={s.busy}>Add</button>
          </form>
          <p className="small muted">Viewers read. Analysts scan, investigate and triage. Admins also manage people, keys and settings.</p>
        </div>
      </div>
      <div className="card table-wrap" style={{ marginTop: 16 }}>
        <h3>People</h3>
        {users.data ? (
          <table><thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Last sign-in</th><th>State</th><th></th></tr></thead>
            <tbody>{users.data.map((u) => (
              <tr key={u.id}><td>{u.email}</td><td>{u.name}</td>
                <td><select value={u.role} disabled={u.id === me.user.id} onChange={(e) => editUser(u, { role: e.target.value }, "Role changed.")} style={{ width: "auto" }} aria-label={`Role of ${u.email}`}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></td>
                <td className="small">{fmtTime(u.last_login_at)}</td><td>{u.active ? <span className="badge low">active</span> : <span className="badge neutral">disabled</span>}</td>
                <td className="row">{u.id !== me.user.id && <button className="btn small" onClick={() => editUser(u, { active: !u.active }, u.active ? "Disabled." : "Enabled.")}>{u.active ? "Disable" : "Enable"}</button>}
                  <button className="btn small" onClick={() => { const p = window.prompt(`New password for ${u.email} (at least 10 characters)`); if (p) editUser(u, { password: p }, "Password reset."); }}>Reset password</button></td></tr>
            ))}</tbody></table>
        ) : <ErrorBox error={users.error} />}
      </div>
      <div className="card table-wrap" style={{ marginTop: 16 }}>
        <h3>Audit log</h3>
        {audit.data ? (audit.data.length ? (
          <table><thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead>
            <tbody>{audit.data.slice(0, 100).map((a) => <tr key={a.id}><td className="small">{fmtTime(a.at)}</td><td className="small">{a.by}</td><td className="mono small">{a.action}</td><td className="small">{a.detail}</td></tr>)}</tbody></table>
        ) : <Empty>Nothing yet.</Empty>) : <ErrorBox error={audit.error} />}
      </div>
    </>
  );
}

export function Consultant() {
  const { switchOrg, refresh } = useAuth(); const orgs = useLoad(() => api("/api/super/orgs"), []); const leads = useLoad(() => api("/api/super/leads"), []);
  const [s, run] = useAction(); const [name, setName] = useState(""); const [admin, setAdmin] = useState({ org: "", email: "", name: "", password: "" });
  return (
    <>
      <PageHead title="Client organisations">Each client has its own people, keys, data and encryption key. Open one to work in it.</PageHead>
      {s.ok && <div className="success" style={{ marginBottom: 12 }}>{s.ok}</div>}<ErrorBox error={s.error} />
      <div className="card table-wrap">
        <form className="row" style={{ marginBottom: 12 }} onSubmit={async (e) => { e.preventDefault(); if (await run(() => api("/api/super/orgs", { method: "POST", body: { name } }), "Organisation created. Add its first admin below.")) { setName(""); orgs.reload(); refresh(); } }}>
          <input placeholder="New client organisation name" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: "1 1 240px", width: "auto" }} />
          <button className="btn primary" disabled={name.trim().length < 2}>Create</button>
        </form>
        {orgs.loading && !orgs.data ? <Loading /> : <ErrorBox error={orgs.error} />}
        {orgs.data && (orgs.data.length ? (
          <table><thead><tr><th>Organisation</th><th>People</th><th>Open alerts</th><th>Retention</th><th>State</th><th></th></tr></thead>
            <tbody>{orgs.data.map((o) => (
              <tr key={o.id}><td><strong>{o.name}</strong><div className="small muted mono">{o.slug}</div></td><td>{o.users}</td><td>{o.open_alerts}</td><td>{o.retention_days} days</td>
                <td>{o.active ? <span className="badge low">active</span> : <span className="badge neutral">disabled</span>}</td>
                <td className="row"><button className="btn small primary" disabled={!o.active} onClick={() => switchOrg(o.id)}>Open</button>
                  <button className="btn small" onClick={async () => { await run(() => api(`/api/super/orgs/${o.id}`, { method: "PATCH", body: { active: !o.active } }), o.active ? "Disabled: its people cannot sign in." : "Enabled."); orgs.reload(); refresh(); }}>{o.active ? "Disable" : "Enable"}</button></td></tr>
            ))}</tbody></table>
        ) : <Empty>No client organisations yet.</Empty>)}
      </div>
      <div className="grid two" style={{ marginTop: 16 }}>
        <form className="card" onSubmit={async (e) => { e.preventDefault(); if (await run(() => api(`/api/super/orgs/${admin.org}/users`, { method: "POST", body: { email: admin.email, name: admin.name, role: "admin", password: admin.password } }), "Admin added. Share the password with them privately.")) { setAdmin({ org: "", email: "", name: "", password: "" }); orgs.reload(); } }}>
          <h3>Add a client's first admin</h3>
          <label className="field">Organisation<select required value={admin.org} onChange={(e) => setAdmin({ ...admin, org: e.target.value })}><option value="">— choose —</option>{(orgs.data || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
          <label className="field">Email<input type="email" required value={admin.email} onChange={(e) => setAdmin({ ...admin, email: e.target.value })} /></label>
          <label className="field">Name<input value={admin.name} onChange={(e) => setAdmin({ ...admin, name: e.target.value })} /></label>
          <label className="field">First password<input type="password" required value={admin.password} onChange={(e) => setAdmin({ ...admin, password: e.target.value })} autoComplete="new-password" /></label>
          <button className="btn primary">Add admin</button>
        </form>
        <div className="card table-wrap">
          <h3>Pilot requests from the website</h3>
          {leads.data ? (leads.data.length ? <table><tbody>{leads.data.map((l) => <tr key={l.id}><td className="small">{fmtTime(l.at)}</td><td><strong>{l.name}</strong> · {l.organisation}<div className="small">{l.email}</div><div className="small muted">{l.message}</div></td></tr>)}</tbody></table>
            : <Empty>None yet.</Empty>) : <ErrorBox error={leads.error} />}
        </div>
      </div>
    </>
  );
}

export function ModelCard() {
  const c = useLoad(() => api("/api/public/model-card"), []);
  if (c.loading && !c.data) return <Loading />;
  if (c.error) return <ErrorBox error={c.error} />;
  const m = c.data;
  return (
    <>
      <PageHead title="What the models can do">Engine {m.engine.tag} ({m.engine.commit}). Every figure is the honest one, with its condition.</PageHead>
      <div className="grid">{m.detectors.map((d) => <div className="card" key={d.channel}><h3>{d.channel.toUpperCase()}</h3><div className="big">{d.honest}</div><p className="small">{d.measure}</p>
        <p className="small muted">Easier figure, never quoted alone: {d.flattering} ({d.flattering_measure}).</p></div>)}</div>
      <div className="card" style={{ marginTop: 16 }}><h3>Campaign correlation <span className="badge na">Simulated</span></h3>
        <p>F1 {m.correlation.engine_f1} and false-positive rate {m.correlation.engine_fpr} on {m.correlation.n_test_bundles} simulated campaigns, against {m.correlation.single_f1} and {m.correlation.single_fpr} for single messages.</p>
        <p className="note warn">{m.correlation.note}</p></div>
      <div className="card" style={{ marginTop: 16 }}><h3>Limits to tell every client</h3><ul>{m.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p>Not assessed: {m.not_assessed.join(", ")}.</p></div>
    </>
  );
}

export function Account() {
  const { me } = useAuth(); const [f, setF] = useState({ current: "", new: "", again: "" }); const [s, run] = useAction();
  return (
    <>
      <PageHead title="My account">{me.user.email} · {me.user.role}{me.org ? ` · ${me.org.name}` : ""}</PageHead>
      <form className="card" style={{ maxWidth: 460 }} onSubmit={async (e) => { e.preventDefault(); if (f.new !== f.again) return; if (await run(() => api("/api/auth/password", { method: "POST", body: { current: f.current, new: f.new } }), "Password changed. Other sessions were signed out.")) setF({ current: "", new: "", again: "" }); }}>
        <h3>Change password</h3>
        <label className="field">Current password<input type="password" required value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} autoComplete="current-password" /></label>
        <label className="field">New password <span className="hint">at least 10 characters</span><input type="password" required value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} autoComplete="new-password" /></label>
        <label className="field">New password again<input type="password" required value={f.again} onChange={(e) => setF({ ...f, again: e.target.value })} autoComplete="new-password" /></label>
        {f.again && f.new !== f.again && <div className="error">The two new passwords differ.</div>}
        {s.ok && <div className="success">{s.ok}</div>}<ErrorBox error={s.error} />
        <button className="btn primary" style={{ marginTop: 10 }} disabled={s.busy}>Change password</button>
      </form>
    </>
  );
}
