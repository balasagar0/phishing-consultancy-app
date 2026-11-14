"""The web server: the API under /api, the website and the web app from frontend/dist, security headers, the mailbox connectors, and the
scheduled retention purge.
  uvicorn server.main:app --app-dir backend --port 8765 --no-access-log --timeout-graceful-shutdown 3
(--timeout-graceful-shutdown: open live streams would otherwise keep the server waiting when it is stopped.)"""
import logging, threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from starlette.datastructures import MutableHeaders
from . import db as M, engine
from .config import APP_DIR, get_settings
from .connectors import manager
from .security import SECURITY_HEADERS
from .services import purge_org
from . import routes_admin, routes_auth, routes_connectors, routes_ingest, routes_live, routes_public, routes_super, routes_work

log = logging.getLogger("mcpd")
DIST = APP_DIR / "frontend" / "dist"
MAX_BODY = 2 * 1024 * 1024
MAX_EMAIL = 11 * 1024 * 1024          # the email webhook takes one raw message of up to 10 MB


def _purge_loop(stop: threading.Event, every_h: float):
    if stop.wait(60): return
    while not stop.is_set():
        db = M.session()
        try:
            for o in db.scalars(select(M.Org).where(M.Org.active.is_(True))): purge_org(db, o)
        except Exception as e:      # the loop must survive a bad day; the failure is visible in the server log
            log.error("scheduled purge failed: %s", type(e).__name__)
        finally:
            db.close()
        if stop.wait(every_h * 3600): return


@asynccontextmanager
async def lifespan(app: FastAPI):
    M.init_db(); stop = threading.Event(); s = get_settings(); every = s.purge_interval_hours
    t = threading.Thread(target=_purge_loop, args=(stop, every), daemon=True) if every > 0 else None
    if t: t.start()
    if s.run_connectors: manager.start_all()
    yield
    stop.set(); manager.stop_all(); engine.close_stores()


class Guard:
    """Plain ASGI middleware (it passes streamed responses, such as the live event stream, through untouched): refuses oversized bodies and
    adds the security headers; nothing under /api is cached."""
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        path = scope.get("path", "")
        try: size = int(dict(scope["headers"]).get(b"content-length") or 0)
        except ValueError: size = 0
        if size > (MAX_EMAIL if path == "/api/v1/hooks/email" else MAX_BODY):
            return await JSONResponse({"detail": "request too large"}, status_code=413, headers=SECURITY_HEADERS)(scope, receive, send)

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                for k, v in SECURITY_HEADERS.items():
                    if k not in h: h[k] = v
                if path.startswith("/api"): h["Cache-Control"] = "no-store"
            await send(msg)
        await self.app(scope, receive, send_with_headers)


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", lifespan=lifespan)
    app.add_middleware(Guard)
    for r in (routes_public, routes_auth, routes_work, routes_live, routes_admin, routes_connectors, routes_super, routes_ingest): app.include_router(r.router)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        """Website and web app: a real file from frontend/dist if there is one, else the single-page app."""
        if path.startswith("api/"): return JSONResponse({"detail": "not found"}, status_code=404)
        if not DIST.exists(): return JSONResponse({"detail": "The frontend is not built. Run `npm install` and `npm run build` in frontend/."}, status_code=503)
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            r = FileResponse(f)
            if "/assets/" in f.as_posix(): r.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return r
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
