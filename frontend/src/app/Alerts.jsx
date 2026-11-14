import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, download } from "../api.js";
import { can, useAuth } from "../auth.jsx";
import { CopyButton, Empty, ErrorBox, HBars, Loading, RiskBadge, StatusBadge, Tiles, fmtMinutes, fmtTime, score3, statusLabel, useLoad } from "../ui.jsx";
import { PageHead } from "./Shell.jsx";

const ALL = ["new", "investigating", "confirmed", "false_alarm", "closed"];

export function AlertsList() {
  const [sp, setSp] = useSearchParams(); const nav = useNavigate();
  const status = sp.getAll("status"); const days = sp.get("days") || "90"; const [q, setQ] = useState(sp.get("q") || "");
  const qs = new URLSearchParams([...status.map((s) => ["status", s]), ["days", days], ...(sp.get("q") ? [["q", sp.get("q")]] : [])]).toString();
  const list = useLoad(() => api(`/api/alerts?${qs}`), [qs]);
  const toggle = (s) => { const n = new URLSearchParams(sp); const cur = n.getAll("status"); n.delete("status"); (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]).forEach((x) => n.append("status", x)); setSp(n); };
  return (
    <>
      <PageHead title="Alerts">One alert per campaign that reached the alert line. Work them from new to closed.</PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <span className="small muted">Status:</span>
          {ALL.map((s) => <button key={s} className={`btn small ${status.includes(s) ? "primary" : ""}`} onClick={() => toggle(s)} aria-pressed={status.includes(s)}>{statusLabel(s)}</button>)}
          <select value={days} onChange={(e) => { const n = new URLSearchParams(sp); n.set("days", e.target.value); setSp(n); }} style={{ width: "auto" }} aria-label="Period">
            {[7, 30, 90, 365].map((d) => <option key={d} value={d}>last {d} days</option>)}
          </select>
          <form className="row grow" onSubmit={(e) => { e.preventDefault(); const n = new URLSearchParams(sp); q ? n.set("q", q) : n.delete("q"); setSp(n); }}>
            <input placeholder="Search a recipient or indicator" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} aria-label="Search" />
            <button className="btn small">Search</button>
          </form>
        </div>
      </div>
      <div className="card table-wrap">
        {list.loading && !list.data ? <Loading /> : <ErrorBox error={list.error} />}
        {list.data && (list.data.length === 0 ? <Empty>No alerts match.</Empty> : (
          <table>
            <thead><tr><th>Raised</th><th>Risk</th><th>Recipient</th><th>Channels</th><th>Indicators</th><th>Status</th><th>Assigned to</th></tr></thead>
            <tbody>{list.data.map((a) => (
              <tr key={a.id} className="click" tabIndex={0} onClick={() => nav(`/app/alerts/${a.id}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/app/alerts/${a.id}`)}>
                <td className="small">{fmtTime(a.created_at)}</td><td><RiskBadge score={a.risk} /></td><td>{a.recipient}</td><td>{a.channels.join(", ")}</td>
                <td>{a.indicators.slice(0, 3).map((i) => <span className="chip mono" key={i}>{i}</span>)}</td><td><StatusBadge status={a.status} /></td>
                <td>{a.assignee?.name || <span className="muted">nobody</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        ))}
      </div>
    </>
  );
}

export function AlertDetail() {
  const { id } = useParams(); const { me } = useAuth(); const a = useLoad(() => api(`/api/alerts/${id}`), [id]);
  const people = useLoad(() => api("/api/assignees"), []); const [note, setNote] = useState(""); const [err, setErr] = useState(null);
  const patch = async (body) => { setErr(null); try { await api(`/api/alerts/${id}`, { method: "PATCH", body }); a.reload(); } catch (e) { setErr(e); } };
  const addNote = async (e) => { e.preventDefault(); setErr(null); try { await api(`/api/alerts/${id}/notes`, { method: "POST", body: { text: note } }); setNote(""); a.reload(); } catch (x) { setErr(x); } };
  if (a.loading && !a.data) return <Loading />;
  if (a.error) return <ErrorBox error={a.error} />;
  const x = a.data; const edit = can(me, "analyst");
  return (
    <>
      <p><Link to="/app/alerts">← All alerts</Link></p>
      <PageHead title={`Alert ${x.id}: ${x.recipient}`}>Raised {fmtTime(x.created_at)} from {x.source === "api" ? "a connector" : x.source === "demo" ? "demo data" : "the web app"}.</PageHead>
      <ErrorBox error={err} />
      <div className="grid two">
        <div className="card stack">
          <div className="row"><RiskBadge score={x.risk} /><StatusBadge status={x.status} /></div>
          <div><h3>Why it was raised</h3><p className="small">{x.reason}</p></div>
          <div><h3>Indicators</h3>
            {x.indicators.length ? x.indicators.map((i) => <span key={i} className="row" style={{ display: "inline-flex", marginRight: 6 }}><span className="chip mono">{i}</span></span>) : <Empty>No shared indicator.</Empty>}
            {x.indicators.length > 0 && <div style={{ marginTop: 6 }}><CopyButton text={x.indicators.join("\n")} label="Copy indicators" /></div>}
          </div>
        </div>
        <div className="card stack">
          <h3>Triage</h3>
          {edit ? (
            <>
              <label className="field">Status<select value={x.status} onChange={(e) => patch({ status: e.target.value })}>{ALL.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></label>
              <label className="field">Assigned to<select value={x.assignee?.id || ""} onChange={(e) => patch(e.target.value ? { assignee_id: Number(e.target.value) } : { unassign: true })}>
                <option value="">nobody</option>{(people.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            </>
          ) : <p className="muted">Viewers can read alerts but not change them.</p>}
          <h3>Notes</h3>
          {x.notes.length ? <ul className="timeline">{x.notes.map((n) => <li key={n.id} style={{ gridTemplateColumns: "1fr" }}><span className="small muted">{n.by}, {fmtTime(n.at)}</span><span>{n.text}</span></li>)}</ul> : <Empty>No notes yet.</Empty>}
          {edit && <form onSubmit={addNote}><textarea style={{ minHeight: 70 }} value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} placeholder="What did you find or do?" />
            <button className="btn small" disabled={!note.trim()} style={{ marginTop: 6 }}>Add note</button></form>}
        </div>
      </div>
      <Timeline c={x.campaign} />
    </>
  );
}

export function Timeline({ c }) {
  if (!c) return <div className="card" style={{ marginTop: 16 }}><Empty>The campaign's events were deleted by the retention purge.</Empty></div>;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>Campaign {c.id} timeline</h3>
      <p className="small muted">Events in this {c.window_minutes}-minute window. Faded rows are nearby events that were not part of the campaign. Message text is shown only if your organisation stores it.</p>
      <ul className="timeline">{c.timeline.map((e) => (
        <li key={e.id} className={e.in_campaign ? "" : "out"}>
          <span className="small muted">{fmtMinutes(e.t_minutes)}</span><span>{e.channel}</span>
          <span><RiskBadge score={e.assessed ? e.score : null} /> {e.identity_tokens.map((t) => <span className="chip mono" key={t}>{t}</span>)}
            {e.text && <div className="small" style={{ marginTop: 4 }}>{e.subject && <strong>{e.subject}: </strong>}{e.text}</div>}</span>
        </li>
      ))}</ul>
    </div>
  );
}

export function Campaigns() {
  const [inactive, setInactive] = useState(false); const list = useLoad(() => api(`/api/campaigns?include_inactive=${inactive}`), [inactive]); const nav = useNavigate();
  return (
    <>
      <PageHead title="Campaigns">Each person's messages, grouped by time window. A campaign at or above the alert line opened an alert.</PageHead>
      <label className="check"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> Show campaigns that were merged into larger ones</label>
      <div className="card table-wrap">
        {list.loading && !list.data ? <Loading /> : <ErrorBox error={list.error} />}
        {list.data && (list.data.length === 0 ? <Empty>No campaigns yet.</Empty> : (
          <table>
            <thead><tr><th>Campaign</th><th>Risk</th><th>Recipient</th><th>Messages</th><th>First seen</th><th>Shared indicators</th></tr></thead>
            <tbody>{[...list.data].reverse().map((c) => (
              <tr key={c.id} className="click" onClick={() => nav(`/app/campaigns/${c.id}`)}>
                <td>{c.id}{!c.active && <span className="muted small"> (merged)</span>}</td><td><RiskBadge score={c.risk} /></td><td className="mono small">{c.recipient}</td>
                <td>{c.n_events}</td><td className="small">{fmtMinutes(c.first_t_minutes)}</td><td>{c.shared_identity_tokens.map((t) => <span className="chip mono" key={t}>{t}</span>)}</td>
              </tr>
            ))}</tbody>
          </table>
        ))}
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>Recipients are shown as the first digits of their keyed hash. Alert cases show names when your organisation keeps labels.</p>
    </>
  );
}

export function CampaignDetail() {
  const { id } = useParams(); const c = useLoad(() => api(`/api/campaigns/${id}`), [id]);
  if (c.loading && !c.data) return <Loading />;
  if (c.error) return <ErrorBox error={c.error} />;
  return (<><p><Link to="/app/campaigns">← All campaigns</Link></p><PageHead title={`Campaign ${id}`}>Risk {score3(c.data.risk)}; {c.data.n_events} message(s).</PageHead><Timeline c={c.data} /></>);
}

export function Reports() {
  const [days, setDays] = useState(30); const s = useLoad(() => api(`/api/reports/summary?days=${days}`), [days]); const [err, setErr] = useState(null);
  return (
    <>
      <PageHead title="Reports" actions={<>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: "auto" }} aria-label="Period">{[7, 30, 90, 365].map((d) => <option key={d} value={d}>last {d} days</option>)}</select>
        <button className="btn" onClick={async () => { setErr(null); try { await download(`/api/reports/alerts.csv?days=${days}`, "alerts.csv"); } catch (e) { setErr(e); } }}>Download CSV</button>
        <Link className="btn primary" to={`/app/reports/print?days=${days}`}>Printable report</Link></>}>
        What happened in this organisation, for the client meeting.
      </PageHead>
      <ErrorBox error={err} />
      {s.loading && !s.data ? <Loading /> : <ErrorBox error={s.error} />}
      {s.data && <ReportBody r={s.data} />}
    </>
  );
}

function ReportBody({ r }) {
  return (
    <div className="stack">
      <Tiles items={[["Messages checked", r.messages_checked], ["Alerts", r.alerts], ["Confirmed phishing", r.by_status.confirmed || 0], ["False alarms", r.by_status.false_alarm || 0]]} />
      <div className="grid two">
        <div className="card"><h3>Alerts by channel</h3><HBars items={Object.entries(r.by_channel)} /></div>
        <div className="card"><h3>Top indicators</h3>{r.top_indicators.length ? <ul>{r.top_indicators.map(([k, v]) => <li key={k}><span className="mono">{k}</span> · {v}</li>)}</ul> : <Empty>None.</Empty>}</div>
      </div>
      <div className="card table-wrap"><h3>Alert cases</h3>
        {r.cases.length ? (
          <table><thead><tr><th>Case</th><th>Raised</th><th>Recipient</th><th>Risk</th><th>Status</th><th>Indicators</th></tr></thead>
            <tbody>{r.cases.map((c) => <tr key={c.id}><td>{c.id}</td><td className="small">{fmtTime(c.created_at)}</td><td>{c.recipient}</td><td>{score3(c.risk)}</td><td>{statusLabel(c.status)}</td><td className="mono small">{c.indicators.join(" ")}</td></tr>)}</tbody></table>
        ) : <Empty>No alerts in this period.</Empty>}
      </div>
      <div className="card"><h3>Read these numbers with care</h3><ul>{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="small muted">Detection engine {r.engine.tag} ({r.engine.commit}).</p></div>
    </div>
  );
}

export function ReportPrint() {
  const [sp] = useSearchParams(); const days = Number(sp.get("days") || 30); const s = useLoad(() => api(`/api/reports/summary?days=${days}`), [days]);
  if (s.loading && !s.data) return <Loading />;
  if (s.error) return <ErrorBox error={s.error} />;
  return (
    <div>
      <div className="row no-print" style={{ marginBottom: 12 }}><Link to="/app/reports" className="btn">← Back</Link><button className="btn primary" onClick={() => window.print()}>Print or save as PDF</button></div>
      <h1>Phishing report: {s.data.org}</h1>
      <p className="muted">The last {s.data.days} days, generated {fmtTime(s.data.generated_at)}.</p>
      <ReportBody r={s.data} />
    </div>
  );
}
