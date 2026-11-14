"""The web server: the API under /api, the website and the web app from frontend/dist, security headers, and the scheduled retention purge.
  uvicorn server.main:app --app-dir backend --port 8080 --no-access-log"""
import logging, threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from . import db as M, engine
from .config import APP_DIR, get_settings
from .security import SECURITY_HEADERS
from .services import purge_org
from . import routes_admin, routes_auth, routes_ingest, routes_public, routes_super, routes_work

log = logging.getLogger("mcpd")
DIST = APP_DIR / "frontend" / "dist"
MAX_BODY = 2 * 1024 * 1024


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
    M.init_db(); stop = threading.Event(); every = get_settings().purge_interval_hours
    t = threading.Thread(target=_purge_loop, args=(stop, every), daemon=True) if every > 0 else None
    if t: t.start()
    yield
    stop.set(); engine.close_stores()


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", lifespan=lifespan)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if int(request.headers.get("content-length") or 0) > MAX_BODY: return JSONResponse({"detail": "request too large"}, status_code=413)
        resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items(): resp.headers.setdefault(k, v)
        if request.url.path.startswith("/api"): resp.headers["Cache-Control"] = "no-store"
        return resp

    for r in (routes_public, routes_auth, routes_work, routes_admin, routes_super, routes_ingest): app.include_router(r.router)

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
