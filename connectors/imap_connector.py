"""Mail connector: reads a "report phishing" mailbox over IMAP and sends each reported message to the service with an API key.
  python connectors/imap_connector.py --host imap.client.example --user report-phishing@client.example [--folder INBOX] [--interval 60]
  environment: MCPD_URL (e.g. https://phishing.example.com), MCPD_API_KEY (from Integrations & API), MCPD_IMAP_PASSWORD
How a message becomes events:
- If staff forward a suspicious email as an attachment (message/rfc822), the attached email is the suspicious one, and the person who forwarded
  it is the recipient. Otherwise the message itself is the suspicious one and its first To address is the recipient.
- The email (subject and text) is one event, with its sender as identity. Up to five distinct links found in it become URL events.
Only unread messages are read; each one is marked read after the service accepts it. Standard library only. Nothing about message content is
printed or logged: only counts and the service's answer status."""
import argparse, email, imaplib, json, os, re, sys, time, urllib.error, urllib.request
from email import policy
from email.utils import getaddresses, parseaddr

URL = re.compile(r"""https?://[^\s<>"')\]]+""", re.I)


def _text(msg) -> str:
    """The message's plain text, or its HTML if it has no plain text (the service cleans HTML)."""
    plain, html = [], []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_maintype() == "multipart" or part.get_content_type() == "message/rfc822" or part.get_filename(): continue
        try: body = part.get_content()
        except (LookupError, ValueError): body = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        if not isinstance(body, str): continue
        (plain if part.get_content_type() == "text/plain" else html if part.get_content_type() == "text/html" else []).append(body)
    return "\n".join(plain or html).strip()


def events_from_message(raw: bytes):
    """Returns (recipient, events) for one mailbox message, or (None, []) when it holds nothing to check."""
    outer = email.message_from_bytes(raw, policy=policy.default); inner = None
    for part in outer.walk():
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            inner = payload[0] if isinstance(payload, list) and payload else payload if isinstance(payload, email.message.Message) else None
            break
    if inner is not None: suspicious, recipient = inner, parseaddr(str(outer.get("From", "")))[1]
    else:
        suspicious = outer; tos = [a for _, a in getaddresses([str(x) for x in outer.get_all("To", [])]) if a]
        recipient = tos[0] if tos else parseaddr(str(outer.get("From", "")))[1]
    text = _text(suspicious); subject = str(suspicious.get("Subject", "") or "")[:2000]
    if not recipient or not (text or subject): return None, []
    sender = parseaddr(str(suspicious.get("From", "")))[1]
    events = [{"channel": "email", "text": (text or subject)[:100000], "subject": subject, "identity": sender}]
    seen = []
    for u in URL.findall(text):
        u = u.rstrip(".,;:")
        if u not in seen: seen.append(u)
        if len(seen) == 5: break
    events += [{"channel": "url", "text": u} for u in seen]
    return recipient.strip().lower(), events


def send(base, key, recipient, events):
    req = urllib.request.Request(base.rstrip("/") + "/api/v1/events", data=json.dumps({"recipient": recipient, "events": events}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())


def run_once(a, key, password):
    n_ok = n_skip = n_alerts = 0
    with imaplib.IMAP4_SSL(a.host, a.port) as M:
        M.login(a.user, password); M.select(a.folder)
        typ, data = M.uid("search", None, "UNSEEN")
        for uid in (data[0].split() if typ == "OK" and data and data[0] else []):
            typ, msg = M.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg or not isinstance(msg[0], tuple): continue
            recipient, events = events_from_message(msg[0][1])
            if not events: n_skip += 1; M.uid("store", uid, "+FLAGS", "(\\Seen)"); continue
            try: r = send(a.url, key, recipient, events)
            except urllib.error.HTTPError as e:
                print(f"message refused by the service: HTTP {e.code}"); continue        # left unread, retried next time
            n_ok += 1; n_alerts += len(r.get("new_alerts", [])); M.uid("store", uid, "+FLAGS", "(\\Seen)")
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: {n_ok} message(s) sent, {n_skip} skipped, {n_alerts} new alert(s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", required=True); ap.add_argument("--port", type=int, default=993); ap.add_argument("--user", required=True)
    ap.add_argument("--folder", default="INBOX"); ap.add_argument("--url", default=os.environ.get("MCPD_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--interval", type=int, default=0, help="seconds between checks; 0 checks once")
    a = ap.parse_args(); key = os.environ.get("MCPD_API_KEY"); password = os.environ.get("MCPD_IMAP_PASSWORD")
    if not key or not password: sys.exit("set MCPD_API_KEY and MCPD_IMAP_PASSWORD in the environment (never on the command line)")
    while True:
        try: run_once(a, key, password)
        except (imaplib.IMAP4.error, OSError) as e: print(f"mailbox or network problem: {type(e).__name__}")
        if a.interval <= 0: break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
