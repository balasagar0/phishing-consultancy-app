import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { KIND, ago, useLive, useNow } from "../live.jsx";
import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui.jsx";
import { useAction } from "./Admin.jsx";
import { StatusDot } from "./Live.jsx";
import { PageHead } from "./Shell.jsx";

const IMAP0 = { host: "", port: 993, security: "ssl", username: "", folder: "INBOX", mailbox_address: "", poll_seconds: 30, use_idle: true, backfill: 0 };
const GRAPH0 = { tenant_id: "", client_id: "", mailbox: "", folder: "inbox", poll_seconds: 30, backfill: 0 };

function ConnectorForm({ initial, onDone }) {
  const editing = !!initial; const kind0 = initial?.kind || "imap"; const c0 = initial?.config || {};
  const [kind, setKind] = useState(kind0); const [name, setName] = useState(initial?.name || "");
  const [mode, setMode] = useState(c0.mode || "reports"); const [secret, setSecret] = useState("");
  const [imap, setImap] = useState({ ...IMAP0, ...(kind0 === "imap" ? c0 : {}) }); const [graph, setGraph] = useState({ ...GRAPH0, ...(kind0 === "graph" ? c0 : {}) });
  const [test, setTest] = useState(null); const [s, run] = useAction();
  const cfg = () => {
    const { mode: _m, ...base } = kind === "imap" ? imap : graph;
    const out = { ...base, mode };
    ["port", "poll_seconds", "backfill"].forEach((k) => { if (k in out) out[k] = Number(out[k]); });
    return out;
  };
  const I = (k) => (e) => setImap({ ...imap, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const G = (k) => (e) => setGraph({ ...graph, [k]: e.target.value });
  const doTest = async () => { setTest(null); const r = await run(() => api("/api/admin/connectors/test", { method: "POST", body: { kind, config: cfg(), secret, id: initial?.id } }), null); if (r) setTest(r); };
  const save = async (e) => {
    e.preventDefault();
    const body = editing ? { name, config: cfg(), ...(secret ? { secret } : {}) } : { kind, name, config: cfg(), secret };
    const r = await run(() => api(editing ? `/api/admin/connectors/${initial.id}` : "/api/admin/connectors", { method: editing ? "PATCH" : "POST", body }), "Saved.");
    if (r) onDone(r);
  };
  return (
    <form className="card stack" onSubmit={save}>
      <h3 style={{ margin: 0 }}>{editing ? `Edit ${initial.name}` : "Connect a mailbox"}</h3>
      {!editing && (
        <div className="row" role="group" aria-label="Kind of mailbox">
          <button type="button" className={`btn small ${kind === "imap" ? "primary" : ""}`} aria-pressed={kind === "imap"} onClick={() => { setKind("imap"); setTest(null); }}>IMAP mailbox</button>
          <button type="button" className={`btn small ${kind === "graph" ? "primary" : ""}`} aria-pressed={kind === "graph"} onClick={() => { setKind("graph"); setTest(null); }}>Microsoft 365</button>
        </div>
      )}
      <label className="field" style={{ margin: 0 }}>Name<input required value={name} onChange={(e) => setName(e.target.value)} maxLength={200} placeholder="e.g. Report-phishing mailbox" /></label>
      <fieldset className="plain">
        <legend className="small" style={{ fontWeight: 700 }}>What it reads</legend>
        <label className="check"><input type="radio" name="mode" checked={mode === "reports"} onChange={() => setMode("reports")} />
          <span>A reporting mailbox<br /><span className="small muted">Staff forward suspicious mail to it. A message forwarded as an attachment is checked, and the person who forwarded it is the recipient.</span></span></label>
        <label className="check"><input type="radio" name="mode" checked={mode === "inbox"} onChange={() => setMode("inbox")} />
          <span>Watch an inbox<br /><span className="small muted">Every new message in it is checked, and the mailbox's owner is the recipient.</span></span></label>
        {mode === "inbox" && <div className="note warn small">Watching a person's inbox reads all their new mail. Do it only under your organisation's written policy, with notice to the people
          concerned (India's DPDP Act, 2023). Message text is still not stored unless you switch that on under Settings.</div>}
      </fieldset>

      {kind === "imap" ? (<>
        <div className="row small"><span className="muted">Fill in for:</span>
          <button type="button" className="btn small" onClick={() => setImap({ ...imap, host: "imap.gmail.com", port: 993, security: "ssl" })}>Gmail or Google Workspace</button></div>
        <div className="row">
          <label className="field grow">Server<input required value={imap.host} onChange={I("host")} placeholder="imap.example.com" /></label>
          <label className="field" style={{ width: 100 }}>Port<input type="number" min={1} max={65535} value={imap.port} onChange={I("port")} /></label>
          <label className="field" style={{ width: 150 }}>Security<select value={imap.security} onChange={I("security")}>
            <option value="ssl">TLS (port 993)</option><option value="starttls">STARTTLS (143)</option><option value="none">None (private network only)</option></select></label>
        </div>
        <div className="row">
          <label className="field grow">User name<input required value={imap.username} onChange={I("username")} autoComplete="off" /></label>
          <label className="field grow">Password {editing && <span className="hint">leave empty to keep the saved one</span>}
            <input type="password" required={!editing} value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="new-password" /></label>
        </div>
        <div className="row">
          <label className="field grow">Folder<input value={imap.folder} onChange={I("folder")} /></label>
          {mode === "inbox" && <label className="field grow">Mailbox owner's address <span className="hint">if the user name is not an email address</span><input value={imap.mailbox_address} onChange={I("mailbox_address")} /></label>}
        </div>
        <div className="row">
          <label className="check" style={{ margin: 0 }}><input type="checkbox" checked={imap.use_idle} onChange={I("use_idle")} /> Ask the server to report new mail at once (IMAP IDLE)</label>
          <label className="field" style={{ width: 210, margin: 0 }}>Otherwise check every (seconds)<input type="number" min={10} max={3600} value={imap.poll_seconds} onChange={I("poll_seconds")} /></label>
        </div>
        <p className="small muted" style={{ margin: 0 }}>Gmail and Google Workspace need IMAP switched on and an app password (with 2-step verification), not the account password.
          Microsoft 365 no longer accepts IMAP passwords: use the Microsoft 365 option.</p>
      </>) : (<>
        <div className="row">
          <label className="field grow">Directory (tenant) ID or domain<input required value={graph.tenant_id} onChange={G("tenant_id")} placeholder="contoso.onmicrosoft.com" /></label>
          <label className="field grow">Application (client) ID<input required value={graph.client_id} onChange={G("client_id")} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" /></label>
        </div>
        <div className="row">
          <label className="field grow">Client secret {editing && <span className="hint">leave empty to keep the saved one</span>}
            <input type="password" required={!editing} value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="new-password" /></label>
          <label className="field grow">Mailbox address<input required type="email" value={graph.mailbox} onChange={G("mailbox")} /></label>
        </div>
        <div className="row">
          <label className="field grow">Folder <span className="hint">inbox, or a folder ID</span><input value={graph.folder} onChange={G("folder")} /></label>
          <label className="field" style={{ width: 190 }}>Check every (seconds)<input type="number" min={15} max={3600} value={graph.poll_seconds} onChange={G("poll_seconds")} /></label>
        </div>
        <p className="small muted" style={{ margin: 0 }}>In Microsoft Entra, register an app, give it the Mail.Read application permission with admin consent, and create a client
          secret. Limit it to this mailbox with an application access policy. The server reads only; it never changes, moves or deletes mail.</p>
      </>)}

      {test && <div className={test.ok ? "success" : "error"} role="status">{test.detail}</div>}
      {s.ok && <div className="success">{s.ok}</div>}<ErrorBox error={s.error} />
      <div className="row">
        <button type="button" className="btn" onClick={doTest} disabled={s.busy}>Test connection</button>
        <button className="btn primary" disabled={s.busy}>{editing ? "Save" : "Save and start"}</button>
        <button type="button" className="btn" onClick={() => onDone(null)}>Cancel</button>
      </div>
      <p className="small muted" style={{ margin: 0 }}>Only mail that arrives after the connector starts is read. The password or secret is stored encrypted and is never shown again.</p>
    </form>
  );
}

function AlertWebhook() {
  const h = useLoad(() => api("/api/admin/alert-webhook"), []); const [f, setF] = useState(null); const [s, run] = useAction(); const [test, setTest] = useState(null);
  useLive(["hook"], () => h.reload());
  useEffect(() => { if (h.data !== undefined && !h.loading) setF({ url: h.data?.url || "", secret: "", active: h.data ? h.data.active : true }); }, [h.data, h.loading]);
  if (!f) return <div className="card"><Loading /></div>;
  const save = async (e) => { e.preventDefault(); if (await run(() => api("/api/admin/alert-webhook", { method: "PUT", body: { url: f.url, active: f.active, ...(f.secret ? { secret: f.secret } : {}) } }))) h.reload(); };
  return (
    <form className="card stack" onSubmit={save}>
      <h3 style={{ margin: 0 }}>Tell another system when an alert opens</h3>
      <p className="small" style={{ margin: 0 }}>The service POSTs a short JSON notice to this address the moment an alert opens: a Slack incoming webhook, your SIEM or ticketing system.
        It has a Slack-style <code>text</code> line and the alert's fields, never message text. Names and indicators are left out when your organisation hides labels.</p>
      <label className="field" style={{ margin: 0 }}>Address<input type="url" required value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://hooks.example.com/..." /></label>
      <label className="field" style={{ margin: 0 }}>Signing secret <span className="hint">optional; {h.data?.has_secret ? "one is saved; type a new one to replace it" : "the receiver checks X-MCPD-Signature with it"}</span>
        <input type="password" value={f.secret} onChange={(e) => setF({ ...f, secret: e.target.value })} autoComplete="new-password" /></label>
      <label className="check" style={{ margin: 0 }}><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Send notices</label>
      {h.data && <p className="small muted" style={{ margin: 0 }}>Last: {h.data.last_status || "nothing sent yet"}{h.data.last_at ? `, ${fmtTime(h.data.last_at)}` : ""} · {h.data.n_sent} sent, {h.data.n_failed} failed</p>}
      {test && <div className={test.ok ? "success" : "error"}>{test.ok ? `Test notice delivered (${test.detail}).` : `Test failed: ${test.detail}`}</div>}
      {s.ok && <div className="success">{s.ok}</div>}<ErrorBox error={s.error} />
      <div className="row">
        <button className="btn primary" disabled={s.busy}>Save</button>
        {h.data && <button type="button" className="btn" disabled={s.busy} onClick={async () => { setTest(null); const r = await run(() => api("/api/admin/alert-webhook/test", { method: "POST" }), null); if (r) setTest(r); }}>Send a test</button>}
        {h.data && <button type="button" className="btn danger" onClick={async () => { if (window.confirm("Stop sending alert notices and remove this address?")) { await run(() => api("/api/admin/alert-webhook", { method: "DELETE" }), "Removed."); h.reload(); } }}>Remove</button>}
      </div>
    </form>
  );
}

function Webhooks() {
  const o = window.location.origin;
  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>SMS and mail servers: push each message as it arrives</h3>
      <p className="small" style={{ margin: 0 }}>Each request carries one message and needs an API key from <Link to="/app/integrations">Integrations & API</Link>. Webhooks allow 600 requests a minute per key.</p>
      <div><strong className="small">A phone or gateway that forwards each SMS a person receives</strong>
        <pre>{`POST ${o}/api/v1/hooks/sms
Authorization: Bearer <key>
{"from": "+91 90000 00000", "to": "employee@yourco.example", "text": "…", "time": 1763100000}`}</pre></div>
      <div><strong className="small">A "report smishing" number staff forward suspicious SMS to</strong> <span className="small muted">(Twilio or another gateway that posts a form)</span>
        <pre>{`${o.replace("://", "://report:<key>@")}/api/v1/hooks/sms?mode=reports`}</pre>
        <p className="small muted" style={{ margin: 0 }}>The person who forwarded the SMS is the recipient. The key goes in the address as a password because gateways cannot add headers.</p></div>
      <div><strong className="small">A mail server or mail-flow rule, as mail is delivered</strong>
        <pre>{`POST ${o}/api/v1/hooks/email?recipient=employee@yourco.example
Authorization: Bearer <key>
Content-Type: message/rfc822

<the raw email, up to 10 MB>`}</pre></div>
    </div>
  );
}

export function Connectors() {
  const now = useNow(5000); const list = useLoad(() => api("/api/admin/connectors"), []); const [conns, setConns] = useState([]);
  const [form, setForm] = useState(null); const [s, run] = useAction();
  useEffect(() => { if (list.data) setConns(list.data); }, [list.data]);
  useLive(["connector"], (t, d) => {
    if (t === "resync") return list.reload();
    setConns((cs) => (cs.some((c) => c.id === d.id) ? cs.map((c) => (c.id === d.id ? { ...c, ...d } : c)) : cs));
  });
  const act = async (fn, ok) => { const r = await run(fn, ok); if (r) list.reload(); };
  return (
    <>
      <PageHead title="Connectors" actions={!form && <button className="btn primary" type="button" onClick={() => setForm("new")}>Connect a mailbox</button>}>
        Message sources the server reads by itself. New mail is scored as it arrives; nobody has to paste it in.
      </PageHead>
      {s.ok && <div className="success" style={{ marginBottom: 12 }}>{s.ok}</div>}<ErrorBox error={s.error} />
      {form && <div style={{ marginBottom: 16 }}><ConnectorForm initial={form === "new" ? null : form} onDone={(r) => { setForm(null); if (r) list.reload(); }} /></div>}
      {list.loading && !list.data ? <Loading /> : <ErrorBox error={list.error} />}
      {list.data && (conns.length === 0 ? <div className="card"><Empty>No mailbox is connected yet. Connect one, or push messages in with the webhooks below.</Empty></div> : (
        <div className="source-grid">
          {conns.map((c) => (
            <div className="card stack" key={c.id}>
              <div className="row" style={{ justifyContent: "space-between" }}><strong>{c.name}</strong><StatusDot status={c.status} /></div>
              <div className="small muted">{KIND[c.kind] || c.kind}{c.config?.mode ? ` · ${c.config.mode === "inbox" ? "watches an inbox" : "reporting mailbox"}` : ""}
                {c.config?.host ? ` · ${c.config.host}` : ""}{c.config?.mailbox ? ` · ${c.config.mailbox}` : ""}</div>
              <p className="small" style={{ margin: 0 }}>{c.detail}</p>
              <div className="small muted">{c.n_messages} message(s), {c.n_alerts} alert(s){c.n_skipped ? `, ${c.n_skipped} skipped` : ""}.
                {c.kind !== "demo" && ` Last checked ${ago(c.last_checked_at, now)};`} Last message {ago(c.last_message_at, now)}.</div>
              <div className="row">
                {c.kind === "demo" ? (c.active ? <button className="btn small" type="button" onClick={() => act(() => api(`/api/admin/connectors/${c.id}`, { method: "PATCH", body: { active: false } }), "Stopped.")}>Stop</button>
                  : <button className="btn small primary" type="button" onClick={() => act(() => api(`/api/admin/connectors/${c.id}`, { method: "PATCH", body: { active: true } }), "Playing the hand-written demo messages.")}>Play</button>) : (<>
                  {c.active && <button className="btn small" type="button" onClick={() => act(() => api(`/api/admin/connectors/${c.id}/check`, { method: "POST" }), "Checking now.")}>Check now</button>}
                  <button className="btn small" type="button" onClick={() => act(() => api(`/api/admin/connectors/${c.id}`, { method: "PATCH", body: { active: !c.active } }), c.active ? "Paused." : "Resumed.")}>{c.active ? "Pause" : "Resume"}</button>
                  <button className="btn small" type="button" onClick={() => setForm(c)}>Edit</button>
                </>)}
                <button className="btn small danger" type="button" onClick={() => { if (window.confirm(`Remove "${c.name}"? Messages already recorded stay.`)) act(() => api(`/api/admin/connectors/${c.id}`, { method: "DELETE" }), "Removed."); }}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      ))}
      <div className="grid two" style={{ marginTop: 16 }}>
        <Webhooks />
        <AlertWebhook />
      </div>
    </>
  );
}
