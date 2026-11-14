import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api } from "./api.js";
import { ErrorBox, Loading, useLoad } from "./ui.jsx";

function useCard() { return useLoad(() => api("/api/public/model-card"), []); }

export function SiteLayout() {
  const h = useLoad(() => api("/api/health"), []);
  const name = h.data?.app_name || "Multi-Channel Phishing Detection";
  return (
    <>
      <header className="site-header">
        <div className="wrap nav">
          <Link to="/" className="brand"><img src="/icon.svg" alt="" />{name}</Link>
          <nav className="nav-links" aria-label="Website">
            <NavLink to="/how-it-works">How it works</NavLink>
            <NavLink to="/results">Results</NavLink>
            <NavLink to="/privacy">Privacy</NavLink>
            <NavLink to="/pilot">Request a pilot</NavLink>
            <Link to="/app" className="btn primary small">Sign in</Link>
          </nav>
        </div>
      </header>
      <main><Outlet /></main>
      <footer className="site-footer">
        <div className="wrap">
          <p><strong>{name}</strong>. A research prototype from a KL University capstone project, offered for consultancy pilots.
            Its correlation results come from simulated campaigns; it has not yet been validated on real coordinated attacks.</p>
          <p className="small">Detection engine {h.data ? `${h.data.engine_tag} (${h.data.engine_commit})` : ""}. Calls and video are not assessed.</p>
        </div>
      </footer>
    </>
  );
}

export function Home() {
  const card = useCard(); const c = card.data;
  return (
    <>
      <section className="hero wrap">
        <div className="eyebrow">Email · SMS · Links</div>
        <h1>Find the phishing campaign, not just the phishing message.</h1>
        <p className="lead">Attackers send an SMS, then a link, then an email, to the same person within minutes. Each one alone can look harmless.
          This service scores every message and links the ones that belong together, so your analysts see the campaign.</p>
        <div className="row"><Link to="/pilot" className="btn primary">Request a pilot</Link><Link to="/how-it-works" className="btn">See how it works</Link></div>
      </section>
      <section className="section wrap">
        <div className="grid">
          <div className="card feature"><h3>Three trained detectors</h3><p>Email, SMS and URL models score each message from its text alone. No link is ever opened or looked up.</p></div>
          <div className="card feature"><h3>Campaign correlation</h3><p>Messages to one person that share a domain or a phone number, inside a {c?.window_minutes || "short"}-minute window, are scored together.</p></div>
          <div className="card feature"><h3>Alerts your team can work</h3><p>One alert per campaign, with its reason, its indicators and a timeline. Assign, note, confirm or dismiss, and report.</p></div>
          <div className="card feature"><h3>Private by design</h3><p>People and identifiers are stored as keyed hashes. Message text is not kept unless you switch it on. Each client has its own key.</p></div>
        </div>
      </section>
      <section className="section wrap">
        <div className="card">
          <div className="eyebrow">Honest numbers</div>
          <h2>We quote the hard test, not the easy one.</h2>
          {card.loading ? <Loading /> : <ErrorBox error={card.error} />}
          {c && (
            <div className="tiles" style={{ marginTop: 12 }}>
              {c.detectors.map((d) => <div className="tile" key={d.channel}><div className="v">{d.honest}</div><div className="k"><strong>{d.channel.toUpperCase()}</strong> · {d.measure}</div></div>)}
            </div>
          )}
          <p style={{ marginTop: 14 }}><Link to="/results">All results, with their limits →</Link></p>
        </div>
      </section>
      <section className="section wrap">
        <div className="card">
          <h2>What it does not do</h2>
          <ul>
            <li>It does not assess voice calls or video. They are shown as "not assessed", never as safe.</li>
            <li>Its correlation numbers come from simulated campaigns of real messages. Real campaigns have not tested them yet.</li>
            <li>It advises analysts. It does not block mail on its own: the email model raises false alarms on real legitimate mail.</li>
          </ul>
        </div>
      </section>
    </>
  );
}

export function HowItWorks() {
  return (
    <section className="section wrap stack">
      <h1>How it works</h1>
      <div className="steps">
        <div className="card"><h3>Messages arrive by themselves</h3><p>The service reads your reporting mailbox or a watched inbox as mail arrives (IMAP or Microsoft 365), and your SMS gateway and mail server push each message in. Nobody has to paste anything.</p></div>
        <div className="card"><h3>Each one is scored</h3><p>The email, SMS or URL detector gives a score from 0 to 1 and the words that moved it. Calls and video are stored but not scored.</p></div>
        <div className="card"><h3>Campaigns are linked</h3><p>A recipient's messages that fall in one time window are scored together, using shared domains and phone numbers and the timing.</p></div>
        <div className="card"><h3>Your team acts at once</h3><p>A campaign that reaches the alert line opens one alert case, shown on every analyst's screen within seconds and sent to Slack or your SIEM if you wish. Analysts triage it and report.</p></div>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Ways to use it</h2>
          <ul>
            <li><strong>Mailbox connectors</strong>: the server reads a reporting mailbox or a watched inbox itself, over IMAP (with IDLE, so new mail is seen in seconds) or Microsoft 365. Read-only: it never changes the mailbox.</li>
            <li><strong>Webhooks</strong>: an SMS gateway, a phone forwarding app or a mail server pushes each message in as it arrives.</li>
            <li><strong>Live web app</strong>: a live feed of every message, alerts that appear by themselves, triage, campaigns and reports. Pasting a message by hand is still there for a quick check.</li>
            <li><strong>API</strong>: <code>POST /api/v1/events</code> with an organisation's key; pull alerts from <code>GET /api/v1/alerts</code>, or receive them by alert webhook.</li>
            <li><strong>Installable</strong>: add the app to a phone or desktop home screen from the browser, with desktop notifications for new alerts.</li>
          </ul>
        </div>
        <div className="card">
          <h2>For consultants</h2>
          <p>One installation serves several client organisations. Each has its own users, roles, API keys, event store and encryption key,
            and none can see another's data. The consultant account opens each client's workspace to help and to report.</p>
        </div>
      </div>
    </section>
  );
}

export function Results() {
  const card = useCard(); const c = card.data;
  return (
    <section className="section wrap stack">
      <h1>Results, with their limits</h1>
      <p className="lead muted">Every figure here comes from the build the service runs ({c ? `${c.engine.tag}, ${c.engine.commit}` : "loading"}). Each is quoted with the test it comes from.</p>
      {card.loading ? <Loading /> : <ErrorBox error={card.error} />}
      {c && (
        <>
          <div className="card table-wrap">
            <h2>Detectors</h2>
            <table>
              <thead><tr><th>Channel</th><th>Honest F1</th><th>How it was measured</th><th>Easier figure (never quoted alone)</th></tr></thead>
              <tbody>{c.detectors.map((d) => (
                <tr key={d.channel}><td><strong>{d.channel.toUpperCase()}</strong></td><td className="big" style={{ fontSize: "1.3rem" }}>{d.honest}</td><td>{d.measure}</td><td>{d.flattering} <span className="muted small">({d.flattering_measure})</span></td></tr>
              ))}</tbody>
            </table>
          </div>
          <div className="card">
            <h2>Campaign correlation <span className="badge na">Simulated</span></h2>
            <p>On {c.correlation.n_test_bundles} simulated test campaigns, the deployed {c.window_minutes}-minute engine reached F1 <strong>{c.correlation.engine_f1}</strong> with a
              false-positive rate of <strong>{c.correlation.engine_fpr}</strong>, against {c.correlation.single_f1} and {c.correlation.single_fpr} for alerting on single messages.</p>
            <p className="note warn">{c.correlation.note}</p>
          </div>
          <div className="card">
            <h2>Speed</h2>
            <p>Median time per request on a laptop, over real HTTP: email {c.latency.email}, SMS {c.latency.sms}, URL {c.latency.url}, a full multi-message case {c.latency.full_case}.</p>
          </div>
          <div className="card">
            <h2>Limitations</h2>
            <ul>{c.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </div>
        </>
      )}
    </section>
  );
}

export function Privacy() {
  return (
    <section className="section wrap stack">
      <h1>Privacy</h1>
      <div className="grid two">
        <div className="card"><h2>What is stored</h2>
          <ul>
            <li>For each message: its channel, time, score, label and the model version.</li>
            <li>The recipient and every identifier (domain, phone number, sender) as an HMAC-SHA256 keyed hash.</li>
            <li>Message text only if the client organisation switches it on.</li>
            <li>For alert cases: the recipient's name and the shared indicators, unless the organisation turns labels off.</li>
          </ul>
        </div>
        <div className="card"><h2>How long</h2>
          <p>Each organisation sets a retention period. Older events, alerts and logs are deleted automatically every day, and an admin can purge sooner.</p>
          <h2>Who can see it</h2>
          <p>Only that organisation's users, by role, and the consultant account that supports them. Each organisation has its own key; one client's hashes do not match another's.</p>
        </div>
        <div className="card"><h2>What never happens</h2>
          <ul>
            <li>No link in a message is opened, fetched or looked up.</li>
            <li>No message is sent to an outside service or model provider. The server contacts only the mailboxes and webhook addresses your admin sets up.</li>
            <li>Mailbox passwords and secrets are stored encrypted and never shown again; mailboxes are opened read-only.</li>
            <li>Nothing is used to train models without a separate written agreement.</li>
          </ul>
        </div>
        <div className="card"><h2>Law</h2>
          <p>Pilots in India follow the Digital Personal Data Protection Act, 2023: a written agreement on purpose, retention and deletion comes before any real data.</p>
        </div>
      </div>
    </section>
  );
}

export function Pilot() {
  const [f, setF] = useState({ name: "", email: "", organisation: "", message: "", website: "" });
  const [state, setState] = useState({ busy: false, error: null, done: false });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setState({ busy: true, error: null, done: false });
    try { await api("/api/public/contact", { method: "POST", body: f }); setState({ busy: false, error: null, done: true }); }
    catch (err) { setState({ busy: false, error: err, done: false }); }
  };
  return (
    <section className="section wrap" style={{ maxWidth: 640 }}>
      <h1>Request a pilot</h1>
      <p className="muted">Tell us about your organisation. We use these details only to reply to you.</p>
      {state.done ? <div className="success">Thank you. We will be in touch.</div> : (
        <form className="card" onSubmit={submit}>
          <label className="field">Your name<input required maxLength={200} value={f.name} onChange={set("name")} autoComplete="name" /></label>
          <label className="field">Work email<input required type="email" maxLength={320} value={f.email} onChange={set("email")} autoComplete="email" /></label>
          <label className="field">Organisation<input maxLength={200} value={f.organisation} onChange={set("organisation")} autoComplete="organization" /></label>
          <label className="field">What would you like to check?<textarea maxLength={4000} value={f.message} onChange={set("message")} /></label>
          <label className="sr" aria-hidden="true">Leave this empty<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} /></label>
          <ErrorBox error={state.error} />
          <button className="btn primary" disabled={state.busy} style={{ marginTop: 10 }}>{state.busy ? "Sending…" : "Send"}</button>
        </form>
      )}
    </section>
  );
}

export function NotFound() {
  return <section className="section wrap"><h1>Page not found</h1><p><Link to="/">Back to the home page</Link></p></section>;
}
