"""Web runtime and periodic ingestion; run a single Uvicorn worker."""
import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.common.config import Settings
from app.web.database import Database
from app.web.ingestion import Importer

ROOT = Path(__file__).resolve().parents[2]


def create_app(settings=None):
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir / 'sentinel.sqlite', settings.max_db_bytes)
    importer = Importer(db, settings.event_dir, settings.retention_days, settings.max_db_events,
                        settings.max_event_storage_bytes, settings.max_spool_files)

    async def ingest(app):
        while True:
            try:
                await asyncio.to_thread(importer.run)
                app.state.import_ok = not importer.had_errors
                app.state.last_import = time.monotonic()
            except Exception:
                app.state.import_ok = False
                logging.exception('Event import failed')
            await asyncio.sleep(settings.import_seconds)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ingest(app))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title='SSH Sentinel', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db, app.state.settings = db, settings
    app.state.import_ok, app.state.last_import = True, time.monotonic()
    app.state.login_slots = asyncio.Semaphore(2)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts.split(','))

    @app.middleware('http')
    async def security(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method == 'POST' and origin and origin != f'{request.url.scheme}://{request.url.netloc}':
            return PlainTextResponse('Origin rejected', status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        # no-referrer makes Chromium serialize form POST Origin as "null".
        # same-origin preserves valid Origin/CSRF checks without cross-site referrer leakage.
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.get('/healthz')
    def health():
        ok = app.state.import_ok and time.monotonic() - app.state.last_import < max(60, settings.import_seconds * 3)
        return PlainTextResponse('ok' if ok else 'import failed', status_code=200 if ok else 503)

    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
    from app.web.routes import router
    app.include_router(router)
    return app
