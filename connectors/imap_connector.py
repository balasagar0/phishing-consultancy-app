"""Stand-alone mail connector, for a mailbox the server cannot reach (for example one inside the client's own network): reads a "report
phishing" mailbox over IMAP and sends each reported message to the service with an API key.
  python connectors/imap_connector.py --host imap.client.example --user report-phishing@client.example [--folder INBOX] [--interval 60]
  environment: MCPD_URL (e.g. https://phishing.example.com), MCPD_API_KEY (from Integrations & API), MCPD_IMAP_PASSWORD
When the server can reach the mailbox, add it under Connectors in the app instead: the server then reads it itself, live (IMAP IDLE).
How a message becomes events is in backend/server/mailparse.py (shared with the server): a message forwarded as an attachment is the suspicious
one and the person who forwarded it is the recipient; otherwise its first To address is. The email is one event, with its sender as identity,
and up to five links in it become URL events. Only unread messages are read; each one is marked read after the service accepts it. Standard
library only. Nothing about message content is printed or logged: only counts and the service's answer status."""
import argparse, imaplib, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from server.mailparse import events_from_message      # noqa: E402  standard library only


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
