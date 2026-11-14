"""Stand-ins for the outside systems the connectors talk to, so the tests run on one laptop without any real mailbox or account:
- FakeImap: a small IMAP4rev1 server (LOGIN, CAPABILITY, SELECT/EXAMINE, UID SEARCH/FETCH, NOOP, IDLE, LOGOUT) that records every command;
- FakeGraph: the few Microsoft Graph and sign-in endpoints the Microsoft 365 connector uses;
- Receiver: an HTTP endpoint that keeps what an alert webhook posts.
Every message they hold is made up by the test that adds it. The password and secret values are test values for these stand-ins only."""
import imaplib, json, shlex, socket, socketserver, threading, time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def made_up_email(to="watch@a.example", sender="Alerts <alerts@secure-bank-verify.example>", subject="Account locked: verify now", marker="") -> bytes:
    m = EmailMessage(); m["From"] = sender; m["To"] = to; m["Subject"] = subject
    m["Message-ID"] = f"<{time.time_ns()}@test.example>"
    m.set_content(f"Your account is locked. Verify your password within 24 hours at http://secure-bank-verify.example/login or it will be closed. {marker}")
    return m.as_bytes()


def forwarded_report(reporter="ravi@a.example", inner: bytes | None = None) -> bytes:
    outer = EmailMessage(); outer["From"] = f"Ravi <{reporter}>"; outer["To"] = "report-phishing@a.example"; outer["Subject"] = "Fwd: suspicious"
    outer["Message-ID"] = f"<{time.time_ns()}@test.example>"; outer.set_content("Please check the attached message.")
    import email
    from email import policy
    outer.add_attachment(email.message_from_bytes(inner or made_up_email(to=reporter), policy=policy.default)); return outer.as_bytes()


# ---------------------------------------------------------------- IMAP

class _ImapHandler(socketserver.StreamRequestHandler):
    def handle(self):
        f: "FakeImap" = self.server.fake; lock = threading.Lock()

        def w(b):
            with lock:
                self.wfile.write(b if isinstance(b, bytes) else (b + "\r\n").encode()); self.wfile.flush()
        caps = "IMAP4rev1" + (" IDLE" if f.idle else "")
        w(f"* OK [CAPABILITY {caps}] fake IMAP ready")
        while True:
            raw = self.rfile.readline()
            if not raw: return
            line = raw.rstrip(b"\r\n").decode("utf-8", "replace"); tag, _, rest = line.partition(" "); cmd, _, args = rest.partition(" "); cmd = cmd.upper()
            f.commands.append(cmd + (" " + args.split(" ")[0].upper() if cmd == "UID" else ""))
            if cmd == "CAPABILITY": w(f"* CAPABILITY {caps}"); w(f"{tag} OK done")
            elif cmd == "LOGIN":
                user, pw = shlex.split(args)[:2]
                if (user, pw) == (f.user, f.password): w(f"{tag} OK logged in")
                else: w(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
            elif cmd in ("SELECT", "EXAMINE"):
                with f.lock: n, nxt = len(f.msgs), f.next_uid
                w(f"* {n} EXISTS"); w("* 0 RECENT"); w(f"* OK [UIDVALIDITY {f.uidvalidity}] ok"); w(f"* OK [UIDNEXT {nxt}] ok")
                w(f"{tag} OK [{'READ-ONLY' if cmd == 'EXAMINE' else 'READ-WRITE'}] {cmd} done")
            elif cmd == "UID":
                sub, _, a2 = args.partition(" "); sub = sub.upper()
                with f.lock: msgs = list(f.msgs)
                if sub == "SEARCH":
                    if a2.upper().startswith("UID "):
                        lo = int(a2[4:].split(":")[0]); uids = [u for u, _, _ in msgs if u >= lo] or ([msgs[-1][0]] if msgs else [])   # RFC 3501: n:* includes the last
                    else: uids = [u for u, _, _ in msgs]
                    w("* SEARCH" + "".join(f" {u}" for u in uids)); w(f"{tag} OK search done")
                elif sub == "FETCH":
                    uid_s, _, items = a2.partition(" "); uid = int(uid_s)
                    hit = [(i + 1, m) for i, m in enumerate(msgs) if m[0] == uid]
                    if hit:
                        seq, (u, body, when) = hit[0]
                        if "BODY.PEEK[]" in items.upper(): w(f"* {seq} FETCH (UID {u} BODY[] {{{len(body)}}}\r\n".encode() + body + b")\r\n")
                        else: w(f"* {seq} FETCH (UID {u} RFC822.SIZE {len(body)} INTERNALDATE {imaplib.Time2Internaldate(when)})")
                    w(f"{tag} OK fetch done")
                else: w(f"{tag} OK {sub} done")
            elif cmd == "NOOP": w(f"{tag} OK noop")
            elif cmd == "IDLE":
                w("+ idling")
                with f.lock: f.idlers.add(w)
                done = self.rfile.readline()
                with f.lock: f.idlers.discard(w)
                if not done: return
                w(f"{tag} OK IDLE terminated")
            elif cmd == "LOGOUT": w("* BYE"); w(f"{tag} OK bye"); return
            else: w(f"{tag} BAD unknown command")


class FakeImap:
    def __init__(self, user="watch@a.example", password="test-only-imap-pw", idle=True):
        self.user, self.password, self.idle = user, password, idle
        self.msgs, self.next_uid, self.uidvalidity, self.commands, self.idlers, self.lock = [], 1, 7, [], set(), threading.Lock()
        self.srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _ImapHandler); self.srv.daemon_threads = True; self.srv.fake = self
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def append(self, raw: bytes, when: float | None = None) -> int:
        with self.lock:
            uid = self.next_uid; self.next_uid += 1; self.msgs.append((uid, raw, when or time.time())); n = len(self.msgs); idlers = list(self.idlers)
        for w in idlers:
            try: w(f"* {n} EXISTS")
            except OSError: pass
        return uid

    def changed_mailbox(self) -> list[str]:
        return [c for c in self.commands if c.split(" ")[-1] in ("STORE", "COPY", "MOVE", "EXPUNGE") or c in ("EXPUNGE", "DELETE", "APPEND")]

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


# ---------------------------------------------------------------- Microsoft Graph

def _iso(t): return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGraph:
    def __init__(self, tenant="contoso.example", client_id="11111111-2222-3333-4444-555555555555", secret="test-only-graph-secret", mailbox="watch@a.example"):
        self.tenant, self.client_id, self.secret, self.mailbox, self.token = tenant, client_id, secret, mailbox, "test-token-1"
        self.msgs, self.requests, self.lock = [], [], threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, code, body, ctype="application/json"):
                b = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0); form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
                fake.requests.append(("POST", self.path))
                if self.path == f"/{fake.tenant}/oauth2/v2.0/token" and form.get("client_id") == fake.client_id and form.get("client_secret") == fake.secret \
                        and form.get("grant_type") == "client_credentials":
                    return self._send(200, {"access_token": fake.token, "expires_in": 3600, "token_type": "Bearer"})
                return self._send(401, {"error": "invalid_client"})

            def do_GET(self):
                fake.requests.append(("GET", self.path))
                if self.headers.get("Authorization") != f"Bearer {fake.token}": return self._send(401, {"error": {"code": "InvalidAuthenticationToken"}})
                u = urlsplit(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; p = u.path
                base = f"/v1.0/users/{fake.mailbox}"
                with fake.lock: msgs = list(fake.msgs)
                if p == f"{base}/mailFolders/inbox": return self._send(200, {"id": "inbox-id", "displayName": "Inbox", "totalItemCount": len(msgs)})
                if p == f"{base}/mailFolders/inbox/messages":
                    rows = msgs
                    if "$filter" in q: since = q["$filter"].split(" ge ")[1]; rows = [m for m in rows if m[1] >= since]
                    rows = sorted(rows, key=lambda m: m[1], reverse=q.get("$orderby", "").endswith("desc"))[: int(q.get("$top", 10))]
                    return self._send(200, {"value": [{"id": m[0], "receivedDateTime": m[1]} for m in rows]})
                for mid, _, raw in msgs:
                    if p == f"{base}/messages/{mid}/$value": return self._send(200, raw, "message/rfc822")
                return self._send(404, {"error": {"code": "ErrorItemNotFound"}})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); self.srv.daemon_threads = True; self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def add(self, raw: bytes, received: float | None = None) -> str:
        with self.lock:
            mid = f"AAMkAG{len(self.msgs) + 1:04d}"; self.msgs.append((mid, _iso(received or time.time()), raw)); return mid

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


# ---------------------------------------------------------------- webhook receiver

class Receiver:
    def __init__(self):
        self.got, self.event = [], threading.Event(); fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n)
                fake.got.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body}); fake.event.set()
                self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); self.srv.daemon_threads = True; self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def url(self): return f"http://127.0.0.1:{self.port}/hook"

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def wait_for(fn, timeout=15.0, every=0.1):
    """Polls fn() until it returns something truthy; returns that, or None after the timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v: return v
        time.sleep(every)
    return None
