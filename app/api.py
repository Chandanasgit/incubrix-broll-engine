import os
import shutil
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import logging_setup as ls
from .apierrors import ApiError, from_pipeline
from .errors import PipelineError
from .jobs import IdempotencyConflict, JobStore
from .netcheck import check_url
from .render import RATIOS
from .storage import build_storage
from .text_input import prepare_text
from .worker import Worker

log = ls.get_logger("api")


class Captions(BaseModel):
    burn_in: bool = True
    srt: bool = True


class JobRequest(BaseModel):
    audio_url: Optional[str] = None
    script: Optional[str] = None
    scenes: Optional[List[Dict[str, Any]]] = None
    voice: str = "default"
    aspect_ratios: List[str] = Field(default_factory=lambda: ["16:9"])
    style: Optional[str] = None
    avoid: List[str] = Field(default_factory=list)
    captions: Captions = Field(default_factory=Captions)


def _error_response(status, code, message, retryable=False, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={
        "error": {"code": code, "message": message, "retryable": retryable, "details": details or {}}})


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def job_view(job, storage=None):
    jid = job["id"]
    view = {"job_id": jid, "status": job["status"], "progress": job["progress"],
            "message": job["message"], "created_at": _iso(job["created_at"]),
            "updated_at": _iso(job["updated_at"]), "links": {"self": "/api/v1/jobs/%s" % jid}}
    if job["status"] == "succeeded" and job["result"]:
        names = job["result"]["files"]
        files = {n: "/api/v1/jobs/%s/files/%s" % (jid, n) for n in names}
        where = "local"
        if job["result"].get("storage") == "s3" and storage is not None:
            try:
                files = {n: storage.presign("jobs/%s/%s" % (jid, n)) for n in names}
                where = "s3"
            except Exception:
                pass
        view["result"] = {"files": files, "storage": where,
                          "warnings": job["result"].get("warnings", [])}
    if job["status"] == "failed" and job["error"]:
        view["error"] = job["error"]
    return view


def validate_request(body):
    given = [k for k in ("audio_url", "script", "scenes") if getattr(body, k) is not None]
    if len(given) != 1:
        raise ApiError(400, "INVALID_INPUT", "Provide exactly one of audio_url, script or scenes.",
                       details={"provided": given})
    if body.scenes is not None:
        raise ApiError(400, "SCENES_NOT_SUPPORTED", "Scene-list input is not supported yet.")
    if not body.aspect_ratios:
        raise ApiError(400, "INVALID_ASPECT_RATIO", "At least one aspect ratio is required.",
                       details={"allowed": sorted(RATIOS)})
    for r in body.aspect_ratios:
        if r not in RATIOS:
            raise ApiError(400, "INVALID_ASPECT_RATIO", "Unsupported aspect ratio: %s" % r,
                           details={"allowed": sorted(RATIOS)})
    if body.script is not None:
        try:
            prepare_text(body.script)
        except PipelineError as exc:
            raise from_pipeline(exc, 400)
    if body.audio_url is not None:
        check_url(body.audio_url)


def create_app(store=None, worker=None, storage=None):
    ls.setup_logging()
    store = store or JobStore()
    storage = storage if storage is not None else build_storage()
    worker = worker or Worker(store, storage=storage)
    hits = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        n = store.fail_unfinished()
        if n:
            log.warning("marked %d unfinished jobs as failed after restart" % n)
        yield

    app = FastAPI(title="IncuBrix B-roll Engine", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.worker = store, worker

    @app.middleware("http")
    async def guard(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]
        ls.correlation_id.set(cid)
        path = request.url.path
        if path.startswith("/api/"):
            token = os.getenv("API_TOKEN", "")
            if token:
                auth = request.headers.get("authorization", "")
                supplied = auth[7:] if auth.lower().startswith("bearer ") else request.headers.get("x-api-key", "")
                if supplied != token:
                    return _error_response(401, "UNAUTHORIZED", "A valid API token is required.",
                                           headers={"X-Correlation-Id": cid})
            if request.method == "POST":
                limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
                ip = request.client.host if request.client else "unknown"
                now = time.time()
                q = hits[ip]
                while q and now - q[0] > 60:
                    q.popleft()
                if len(q) >= limit:
                    return _error_response(429, "RATE_LIMITED", "Too many requests. Try again later.",
                                           retryable=True, headers={"Retry-After": "60", "X-Correlation-Id": cid})
                q.append(now)
        started = time.time()
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        log.info("%s %s -> %d" % (request.method, path, response.status_code),
                 extra={"fields": {"duration_ms": int((time.time() - started) * 1000)}})
        return response

    @app.exception_handler(PipelineError)
    async def pipeline_error(request, exc):
        return _error_response(getattr(exc, "status", 400), exc.code, exc.message, exc.retryable, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = {"fields": [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]}
        return _error_response(422, "VALIDATION_ERROR", "The request body is not valid.", False, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return _error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.exception("unhandled error")
        return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        checks = {}
        try:
            store.ping()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "failed"
        checks["ffmpeg"] = "ok" if shutil.which("ffmpeg") else "missing"
        try:
            worker.root.mkdir(parents=True, exist_ok=True)
            probe = worker.root / ".write_test"
            probe.write_text("x")
            probe.unlink()
            checks["storage"] = "ok"
        except OSError:
            checks["storage"] = "failed"
        if storage is not None:
            try:
                storage.ping()
                checks["object_storage"] = "ok"
            except Exception:
                checks["object_storage"] = "unavailable (API serves files itself)"
        ok = all(v == "ok" for k, v in checks.items() if k != "object_storage")
        return JSONResponse(status_code=200 if ok else 503,
                            content={"status": "ready" if ok else "not_ready", "checks": checks})

    @app.post("/api/v1/broll/jobs", status_code=202)
    def create_job(body: JobRequest, response: Response, request: Request,
                   idempotency_key: Optional[str] = Header(default=None)):
        validate_request(body)
        payload = body.model_dump()
        try:
            job, created = store.create(payload, idem_key=idempotency_key,
                                        correlation_id=ls.correlation_id.get())
        except IdempotencyConflict:
            raise ApiError(409, "IDEMPOTENCY_KEY_REUSED",
                           "This Idempotency-Key was already used with a different request.")
        if created:
            worker.submit(job["id"])
            log.info("job created", extra={"job_id": job["id"]})
        else:
            response.headers["Idempotent-Replayed"] = "true"
        return job_view(job, storage)

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise ApiError(404, "JOB_NOT_FOUND", "No job with this id.")
        return job_view(job, storage)

    @app.get("/api/v1/jobs/{job_id}/files/{name}")
    def get_file(job_id: str, name: str):
        job = store.get(job_id)
        if job is None:
            raise ApiError(404, "JOB_NOT_FOUND", "No job with this id.")
        if job["status"] != "succeeded" or name not in (job["result"] or {}).get("files", []):
            raise ApiError(404, "FILE_NOT_FOUND", "No such result file for this job.")
        return FileResponse(worker.out_dir(job_id) / name)

    return app
