from __future__ import annotations

import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings
from .security import request_id_var
from .services.errors import DomainError

log = logging.getLogger("decisionflow")
access = logging.getLogger("decisionflow.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"level": record.levelname, "logger": record.name, "msg": record.getMessage(),
                "request_id": request_id_var.get()}
        base.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            base["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(base, ensure_ascii=False)


def _configure_logging() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    for name in ("decisionflow", "decisionflow.access", "decisionflow.worker"):
        lg = logging.getLogger(name)
        lg.handlers = [h]
        lg.setLevel(logging.INFO)
        lg.propagate = False


def create_app(start_worker: bool | None = None) -> FastAPI:
    settings = get_settings()
    _configure_logging()
    run_worker = settings.worker_enabled if start_worker is None else start_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = None
        if run_worker:
            from .worker import BackgroundWorker

            worker = BackgroundWorker()
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="Karsa API (portfolio demo, synthetic data)", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", "")[:40] or "req_" + secrets.token_hex(6)
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            rec = logging.LogRecord("decisionflow.access", logging.INFO, "", 0, "request", None, None)
            rec.extra_fields = {"method": request.method, "path": request.url.path, "status": response.status_code,
                                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                                "user": getattr(request.state, "user_id", None)}
            token = request_id_var.set(rid)
            access.handle(rec)  # no request bodies, briefs or secrets are logged
            request_id_var.reset(token)
        return response

    def err(status: int, code: str, message: str, details=None) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "request_id": request_id_var.get(), "retryable": status >= 500,
            "details": details or {}}})

    @app.exception_handler(DomainError)
    async def _domain(_: Request, e: DomainError):
        return err(e.status, e.code, e.message, e.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        fields = [{"field": ".".join(str(x) for x in d["loc"][1:]), "message": d["msg"]} for d in e.errors()]
        return err(422, "VALIDATION_ERROR", "Some fields need attention.", {"fields": fields})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("unhandled error")  # details stay in server logs; nothing sensitive in the response
        return err(500, "INTERNAL_ERROR", "Something went wrong on the server. Try again.")

    app.include_router(router)

    if settings.static_dir and Path(settings.static_dir).is_dir():  # single-container deployment
        static = Path(settings.static_dir)
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            f = static / path
            return FileResponse(f if path and f.is_file() else static / "index.html")

    return app


app = create_app()
