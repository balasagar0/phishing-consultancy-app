"""Browser check of the website and the web app in the installed Chrome (Playwright, channel "chrome"), against a running server.
  python scripts/ui_check.py [--url http://127.0.0.1:8765]
Signs in with the demo accounts in data/demo_credentials.txt (run `python -m server.cli seed-demo` first), opens every page at a laptop and a phone
size, and checks: the page shows its heading, nothing runs off the screen sideways, the browser console has no errors (apart from the expected
401 of 'who am I' before signing in), and the service worker that makes the app installable registers. At laptop size it also plays the
demo replay (hand-written messages) and checks that they appear in the open Live feed without a reload and that a new alert pops up.
Screenshots go to data/screenshots/ (outside git). Exit code 0 when every check passes."""
import argparse, json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1]; SHOTS = APP / "data" / "screenshots"
SITE = [("/", "Find the phishing campaign"), ("/how-it-works", "How it works"), ("/results", "Results, with their limits"), ("/privacy", "Privacy"), ("/pilot", "Request a pilot")]
APPP = [("/app", "Dashboard"), ("/app/scan", "Scan a message"), ("/app/investigate", "Investigate a set of messages"), ("/app/alerts", "Alerts"), ("/app/alerts/1", "Alert 1"),
        ("/app/campaigns", "Campaigns"), ("/app/reports", "Reports"), ("/app/reports/print?days=30", "Phishing report"), ("/app/model", "What the models can do"), ("/app/account", "My account"),
        ("/app/live", "Live feed")]
ADMIN = [("/app/connectors", "Connectors"), ("/app/integrations", "Integrations & API"), ("/app/settings", "Settings & people")]


def creds():
    p = APP / "data" / "demo_credentials.txt"
    if not p.exists(): sys.exit("data/demo_credentials.txt is missing: run `python -m server.cli seed-demo` in backend/ first")
    return {m.group(1): m.group(2) for m in re.finditer(r"^(\S+@demo\.test)\s+(\S+)", p.read_text(encoding="utf-8"), re.M)}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8765"); a = ap.parse_args()
    C = creds(); SHOTS.mkdir(parents=True, exist_ok=True); results = []
    def check(name, ok, detail=""): results.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail else ""))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for size, (w, h) in (("laptop", (1366, 800)), ("phone", (390, 844))):
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=size == "phone", has_touch=size == "phone")
            page = ctx.new_page(); errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 500 or (r.status == 401 and "/api/auth/me" not in r.url) else None)
            def visit(path, heading, user):
                page.goto(a.url + path, wait_until="domcontentloaded")      # not "networkidle": app pages keep the live stream open
                try: page.get_by_text(heading, exact=False).first.wait_for(timeout=15000); ok = True
                except Exception: ok = False
                page.wait_for_timeout(700)
                over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                fn = f"{size}_{user}_{path.strip('/').replace('/', '_').split('?')[0] or 'home'}.png"; page.screenshot(path=str(SHOTS / fn), full_page=True)
                check(f"{size} {path}: heading shown, no sideways overflow", ok and over <= 1, f"overflow {over}px" if over > 1 else "")
            for path, hd in SITE: visit(path, hd, "public")
            sw = page.evaluate("navigator.serviceWorker ? Promise.race([navigator.serviceWorker.ready.then(() => true), new Promise(r => setTimeout(() => r(false), 6000))]) : false")
            check(f"{size}: service worker registers (installable app)", sw)
            page.goto(a.url + "/app"); page.wait_for_url("**/app/login")
            page.fill("input[type=email]", "analyst@demo.test"); page.fill("input[type=password]", C["analyst@demo.test"]); page.click("button:has-text('Sign in')")
            page.wait_for_url(re.compile(r".*/app/?$")); check(f"{size}: analyst signs in", True)
            for path, hd in APPP: visit(path, hd, "analyst")
            page.goto(a.url + "/app/scan"); page.click("button:has-text('Use a sample')"); page.click("button:has-text('Score it')")
            page.wait_for_selector(".score-head .num"); check(f"{size}: a scan returns a score", True, page.inner_text(".score-head .num"))
            page.goto(a.url + "/app/investigate"); page.select_option("select", "TC-06"); page.click("button:has-text('Analyze')")
            page.wait_for_selector("text=Together"); risk = page.inner_text(".card:has-text('Together') .num")
            check(f"{size}: investigating TC-06 gives the cp1-final bundle risk", risk == "0.595", risk)
            page.click("button:has-text('Sign out')"); page.wait_for_url("**/app/login")
            page.fill("input[type=email]", "admin@demo.test"); page.fill("input[type=password]", C["admin@demo.test"]); page.click("button:has-text('Sign in')")
            page.wait_for_url(re.compile(r".*/app/?$"))
            for path, hd in ADMIN: visit(path, hd, "admin")
            if size == "laptop":                     # live: hand-written demo messages appear in the open feed without a reload
                page.goto(a.url + "/app/live", wait_until="domcontentloaded")
                try: page.locator(".live-pill.ok").wait_for(timeout=15000); live = True
                except Exception: live = False
                check("laptop: the live stream connects (the page shows Live)", live)
                if page.locator("button:has-text('Stop the demo')").count(): page.click("button:has-text('Stop the demo')"); page.wait_for_timeout(1000)
                page.locator("table.feed").or_(page.get_by_text("No message yet")).first.wait_for(timeout=15000)
                before = page.locator("table.feed tbody tr").count()
                page.click("button:has-text('Play the demo feed')"); t0 = time.monotonic(); seen_flash = 0
                while time.monotonic() - t0 < 45:          # polled from here: the app's CSP (rightly) refuses the page-side string eval of wait_for_function
                    seen_flash = max(seen_flash, page.locator("table.feed tbody tr.flash").count())
                    if page.locator("table.feed tbody tr").count() >= before + 3 or seen_flash >= 3: break
                    page.wait_for_timeout(250)
                after = page.locator("table.feed tbody tr").count(); grew = after >= before + 3 or seen_flash >= 3
                check("laptop: new messages appear in the live feed without a reload", grew, f"{before} rows before, {after} after, {time.monotonic() - t0:.0f} s")
                try: page.locator(".toast").first.wait_for(timeout=60000); toast = page.locator(".toast").first.inner_text()
                except Exception: toast = ""
                check("laptop: a new alert pops up while the page is open", "New alert" in toast, " ".join(toast.split())[:80])
                page.screenshot(path=str(SHOTS / "laptop_admin_live_playing.png"), full_page=True)
                page.click("button:has-text('Stop the demo')"); page.wait_for_timeout(800)
                page.goto(a.url + "/app", wait_until="domcontentloaded"); page.get_by_text("Last message").first.wait_for(timeout=15000)
                check("laptop: the dashboard shows the live status", page.locator(".live-pill").count() >= 1)
            check(f"{size}: no console errors", not errors, "; ".join(errors[:5]))
            ctx.close()
        browser.close()
    bad = [r for r in results if not r[1]]
    (APP / "data" / "ui_check.json").write_text(json.dumps([{"check": n, "ok": o, "detail": d} for n, o, d in results], indent=1), encoding="utf-8")
    print(f"{len(results) - len(bad)} of {len(results)} checks passed; screenshots in {SHOTS}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
