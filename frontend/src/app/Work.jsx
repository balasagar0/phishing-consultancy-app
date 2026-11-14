import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { can, useAuth } from "../auth.jsx";
import { Bars, Empty, ErrorBox, Explanation, HBars, Loading, RiskBadge, ScoreBar, Tiles, fmtMinutes, score3, useLoad } from "../ui.jsx";
import { PageHead } from "./Shell.jsx";

export function Dashboard() {
  const { me } = useAuth(); const d = useLoad(() => api("/api/dashboard"), [me.org?.id]);
  if (d.loading && !d.data) return <Loading />;
  if (d.error) return <ErrorBox error={d.error} />;
  const x = d.data;
  return (
    <>
      <PageHead title="Dashboard" actions={can(me, "analyst") && <Link className="btn primary" to="/app/scan">Scan a message</Link>}>{x.org}: the last 30 days.</PageHead>
      <Tiles items={[["Messages checked, 7 days", x.messages_checked_7d], ["Messages checked, 30 days", x.messages_checked_30d], ["Open alerts", x.alerts_open],
        ["Alerts, 30 days", x.alerts_30d], ["Active campaigns", x.active_campaigns]]} />
      <div className="grid two" style={{ marginTop: 16 }}>
        <div className="card"><h3>Alerts raised per day (14 days)</h3><Bars data={x.alerts_per_day} label="Alerts raised per day" /></div>
        <div className="card"><h3>Messages by channel (30 days)</h3><HBars items={Object.entries(x.messages_by_channel_30d).sort((a, b) => b[1] - a[1])} /></div>
        <div className="card"><h3>Alerts by status (30 days)</h3><HBars items={Object.entries(x.alerts_by_status_30d)} /></div>
        <div className="card"><h3>Most seen indicators (30 days)</h3>
          {x.top_indicators_30d.length ? <ul>{x.top_indicators_30d.map(([k, v]) => <li key={k}><span className="mono">{k}</span> <span className="muted">· {v} alert{v > 1 ? "s" : ""}</span></li>)}</ul>
            : <Empty>No shared indicators yet.</Empty>}
        </div>
      </div>
      <div className="note" style={{ marginTop: 16 }}>
        Engine {x.engine.engine_tag} ({x.engine.engine_commit}): channels {x.engine.channels.join(", ")}. Calls and video are <strong>not assessed</strong>.
        Campaign scoring was trained on <strong>{x.engine.fusion_trained_on}</strong>; treat its risk as a score, not a probability.
      </div>
    </>
  );
}

const SAMPLES = {
  email: { subject: "Action required: account suspended", text: "Dear customer, your account has been suspended. Verify your password within 24 hours at http://secure-account-verify.xyz/login or it will be closed." },
  sms: { text: "Your parcel is held at the depot. Pay the redelivery fee today at parcel-redelivery.info/confirm" },
  url: { text: "http://paypal-secure-login.verify-account.xyz/signin" },
};

export function Scan() {
  const [channel, setChannel] = useState("email"); const [subject, setSubject] = useState(""); const [text, setText] = useState("");
  const [state, setState] = useState({ busy: false, error: null, result: null });
  const run = async (e) => {
    e.preventDefault(); setState({ busy: true, error: null, result: null });
    try { setState({ busy: false, error: null, result: await api("/api/scan", { method: "POST", body: { channel, text, subject } }) }); }
    catch (err) { setState({ busy: false, error: err, result: null }); }
  };
  const r = state.result;
  return (
    <>
      <PageHead title="Scan a message">One email, SMS or link, scored by its detector. Nothing you paste is stored.</PageHead>
      <div className="grid two">
        <form className="card" onSubmit={run}>
          <div className="row" role="tablist" aria-label="Channel" style={{ marginBottom: 12 }}>
            {["email", "sms", "url"].map((c) => <button type="button" key={c} role="tab" aria-selected={channel === c} className={`btn small ${channel === c ? "primary" : ""}`}
              onClick={() => { setChannel(c); setState({ busy: false, error: null, result: null }); }}>{c === "url" ? "Link (URL)" : c.toUpperCase()}</button>)}
          </div>
          {channel === "email" && <label className="field">Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={2000} /></label>}
          <label className="field">{channel === "url" ? "The link" : "The message"}
            {channel === "url" ? <input required value={text} onChange={(e) => setText(e.target.value)} placeholder="https://…" /> : <textarea required value={text} onChange={(e) => setText(e.target.value)} maxLength={100000} />}
          </label>
          <div className="row">
            <button className="btn primary" disabled={state.busy || !text.trim()}>{state.busy ? "Scoring…" : "Score it"}</button>
            <button type="button" className="btn" onClick={() => { setSubject(SAMPLES[channel].subject || ""); setText(SAMPLES[channel].text); }}>Use a sample</button>
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>The link is never opened. Calls and video cannot be scored: there is no detector for them.</p>
        </form>
        <div className="card">
          <ErrorBox error={state.error} />
          {!r && !state.error && <Empty>The result appears here.</Empty>}
          {r && (
            <div className="stack">
              <div className="row"><RiskBadge score={r.score} /><span className="muted">{r.alert ? "At or above the alert line: treat it as suspicious." : "Below the alert line."}</span></div>
              <ScoreBar score={r.score} />
              {r.class_probabilities && <p className="small">SMS classes: ham {score3(r.class_probabilities.ham)}, spam {score3(r.class_probabilities.spam)}, smishing {score3(r.class_probabilities.smishing)}.</p>}
              {r.domain_reputation && <p className="small">Registered domain <span className="mono">{r.domain_reputation.registered_domain || "none"}</span>; popularity rank {r.domain_reputation.popularity_rank ?? "not in the top 10,000"}.</p>}
              <Explanation result={r} />
              {r.channel === "email" && <p className="note warn small">Email verdicts are advice for an analyst. The email model also flags some real legitimate mail; see "What the models can do".</p>}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const blank = () => ({ channel: "sms", text: "", subject: "", identity: "", time: "" });

export function Investigate() {
  const presets = useLoad(() => api("/api/presets"), []); const nav = useNavigate();
  const [events, setEvents] = useState([blank()]); const [recipient, setRecipient] = useState(""); const [pid, setPid] = useState("");
  const [state, setState] = useState({ busy: false, error: null, result: null, recorded: null });
  const upd = (i, k) => (e) => setEvents(events.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)));
  const load = (id) => {
    setPid(id); const p = (presets.data || []).find((x) => x.id === id);
    if (p) setEvents(p.events.map((e) => ({ ...blank(), ...e, time: e.time ?? "" })));
    setState({ busy: false, error: null, result: null, recorded: null });
  };
  const analyze = async () => {
    setState({ busy: true, error: null, result: null, recorded: null });
    try { setState({ busy: false, error: null, result: await api("/api/correlate", { method: "POST", body: { events } }), recorded: null }); }
    catch (err) { setState({ busy: false, error: err, result: null, recorded: null }); }
  };
  const record = async () => {
    setState((s) => ({ ...s, busy: true, error: null }));
    const now = Date.now() / 60000; const ts = events.map((e, i) => (e.time === "" ? i : Number(e.time)));
    const mx = Math.max(...ts.filter((t) => !Number.isNaN(t)));
    const body = { recipient, events: events.map((e, i) => ({ ...e, time: Number.isNaN(ts[i]) ? e.time : String(now - (mx - ts[i])) })) };
    try { const r = await api("/api/events", { method: "POST", body }); setState((s) => ({ ...s, busy: false, recorded: r })); }
    catch (err) { setState((s) => ({ ...s, busy: false, error: err })); }
  };
  const r = state.result;
  return (
    <>
      <PageHead title="Investigate a set of messages">Messages one person received. They are scored one by one, then together if they fall in one time window.</PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row">
          <label className="field grow" style={{ margin: 0 }}>Load an example <span className="hint">hand-written demo cases, not real messages</span>
            <select value={pid} onChange={(e) => load(e.target.value)}>
              <option value="">— choose —</option>
              {(presets.data || []).map((p) => <option key={p.id} value={p.id}>{p.id}: {p.name}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="stack">
        {events.map((e, i) => (
          <div className="event-card" key={i}>
            <div className="row" style={{ justifyContent: "space-between" }}><strong>Message {i + 1}</strong>
              {events.length > 1 && <button className="btn small danger" type="button" onClick={() => setEvents(events.filter((_, j) => j !== i))}>Remove</button>}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <label className="field" style={{ width: 130 }}>Channel<select value={e.channel} onChange={upd(i, "channel")}>
                {["email", "sms", "url", "call", "video"].map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
              <label className="field grow">Sender <span className="hint">number, address or domain, if known</span><input value={e.identity || ""} onChange={upd(i, "identity")} maxLength={320} /></label>
              <label className="field" style={{ width: 150 }}>Time <span className="hint">minutes</span><input value={e.time ?? ""} onChange={upd(i, "time")} placeholder={String(i)} /></label>
            </div>
            {e.channel === "email" && <label className="field">Subject<input value={e.subject || ""} onChange={upd(i, "subject")} /></label>}
            <label className="field" style={{ marginBottom: 0 }}>{e.channel === "url" ? "Link" : "Text"}<textarea style={{ minHeight: 70 }} value={e.text} onChange={upd(i, "text")} /></label>
            {(e.channel === "call" || e.channel === "video") && <p className="note warn small" style={{ marginTop: 8 }}>Calls and video are kept in the timeline but not scored: there is no detector for them.</p>}
          </div>
        ))}
        <div className="row">
          {events.length < 20 && <button className="btn" type="button" onClick={() => setEvents([...events, blank()])}>+ Add a message</button>}
          <button className="btn primary" type="button" onClick={analyze} disabled={state.busy || events.some((e) => !e.text.trim())}>{state.busy ? "Working…" : "Analyze"}</button>
        </div>
        <ErrorBox error={state.error} />
        {r && (
          <div className="grid two">
            <div className="card">
              <h3>Each message alone</h3>
              <p>{r.single_channel_alert === null ? "Nothing could be assessed." : r.single_channel_alert ? "At least one message reaches the alert line on its own." : "No message reaches the alert line on its own."}</p>
              <ul className="timeline">{r.events.map((ev, i) => (
                <li key={i} className={ev.in_window ? "" : "out"}><span className="muted small">{fmtMinutes(ev.t_minutes)}</span><span>{ev.channel}</span><span><RiskBadge score={ev.score} /> {ev.in_window && <span className="badge brand">in the scored window</span>}</span></li>
              ))}</ul>
            </div>
            <div className="card">
              <h3>Together</h3>
              {r.status === "CANNOT_ASSESS" ? <div className="note warn">{r.reason}</div> : (
                <div className="stack">
                  <ScoreBar score={r.bundle_risk} label="Campaign risk" />
                  <p>{r.bundle_risk >= 0.5 ? "The campaign reaches the alert line." : "The campaign stays below the alert line."}
                    {" "}Scored together without link or timing evidence: {score3(r.bundle_risk_without_correlation)}.</p>
                  <p>Shared indicators: {r.shared_identity_tokens.length ? r.shared_identity_tokens.map((t) => <span className="chip mono" key={t}>{t}</span>) : <span className="muted">none</span>}</p>
                  <p className="small muted">{r.n_windows} time window(s) of {r.window_minutes} minutes. {r.note}.</p>
                </div>
              )}
            </div>
          </div>
        )}
        {r && r.status !== "CANNOT_ASSESS" && (
          <div className="card">
            <h3>Record these messages for a person</h3>
            <p className="small muted">Adds them to the person's history, so later messages are linked to them and an alert opens if a campaign reaches the line. The person is stored only as a keyed hash.</p>
            <div className="row">
              <input className="grow" placeholder="their email address or phone number" value={recipient} onChange={(e) => setRecipient(e.target.value)} maxLength={320} style={{ flex: "1 1 260px", width: "auto" }} />
              <button className="btn primary" type="button" disabled={!recipient.trim() || state.busy} onClick={record}>Record</button>
            </div>
            {state.recorded && (
              <div className="success" style={{ marginTop: 10 }}>
                Recorded {state.recorded.events.length} message(s). {state.recorded.new_alerts.length ? `${state.recorded.new_alerts.length} new alert(s).` : "No new alert."}{" "}
                {state.recorded.new_alerts[0] && <button className="btn small" type="button" onClick={() => nav(`/app/alerts/${state.recorded.new_alerts[0].case_id}`)}>Open the alert</button>}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
