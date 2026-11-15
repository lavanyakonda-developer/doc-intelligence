"""HTTP API: upload a contract, poll the job, read the validated result.

    POST /v1/jobs                      upload PDF -> 202 {job} (or 200 if already processed)
    GET  /v1/jobs/{job_id}             queued | running | done (+ result) | error (+ reason)
    GET  /v1/contracts/{doc_id}        ContractResult (?include_text=true for highlighting)
    GET  /v1/queries/{name}?k=v        named analytics queries (whitelist, bound params)
    GET  /healthz

The API is thin on purpose: validation of the upload, job lifecycle, serialization.
All the real work is pipeline.process_pdf, shared with the CLI and the evals.

  uv run uvicorn docintel.api.app:app --reload
"""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from docintel.api.jobs import JobRunner, ProcessFn
from docintel.config import PROJECT_ROOT, get_settings
from docintel.pipeline import ContractResult, content_id, process_pdf
from docintel.storage.store import QUERIES, DuckDBStore, ResultStore, seed_from_export
from docintel.tracing import flush, maybe_setup_tracing

DEMO_DATA = PROJECT_ROOT / "web" / "public" / "data"  # committed export (scripts/export_demo.py)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB: the largest CUAD contract is ~2 MB
PDF_MAGIC = b"%PDF-"

log = logging.getLogger("docintel.api")


class JobOut(BaseModel):
    job_id: str
    status: str  # queued | running | done | error
    doc_id: str
    filename: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    status_url: str
    result_url: str | None = None
    result: ContractResult | None = None  # included once done


def _job_out(job: dict, store: ResultStore) -> JobOut:
    done = job["status"] == "done"
    return JobOut(
        **job,
        status_url=f"/v1/jobs/{job['job_id']}",
        result_url=f"/v1/contracts/{job['doc_id']}" if done else None,
        result=store.get(job["doc_id"]) if done else None,
    )


def create_app(
    store: ResultStore | None = None,
    process: ProcessFn = process_pdf,
    runner: JobRunner | None = None,
    upload_dir: Path | None = None,
    seed_dir: Path | None = DEMO_DATA,
) -> FastAPI:
    """App factory: tests pass an in-memory store and a fake `process`; production uses
    the defaults. No globals, so every test gets a fresh, isolated app."""
    settings = get_settings()
    store = store or DuckDBStore(settings.duckdb_path)
    runner = runner or JobRunner(store, process)
    upload_dir = upload_dir or settings.data_dir / "uploads"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        maybe_setup_tracing()  # DOCINTEL_TRACING=1 -> spans to Phoenix
        n = store.fail_interrupted_jobs()
        if n:
            log.warning("marked %d interrupted jobs as failed", n)
        upload_dir.mkdir(parents=True, exist_ok=True)
        if seed_dir is not None and (seeded := seed_from_export(store, seed_dir)):
            log.info("seeded %d demo contracts from %s", seeded, seed_dir)
        yield
        runner.shutdown()
        flush()

    app = FastAPI(
        title="docintel",
        version="0.1.0",
        summary="Contracts in, validated JSON out: every field with evidence and a status.",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/v1/jobs", response_model=JobOut, status_code=202)
    async def create_job(file: UploadFile) -> JSONResponse:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"file larger than {MAX_UPLOAD_BYTES // 2**20} MB")
        if not data.startswith(PDF_MAGIC):  # don't trust the declared content type
            raise HTTPException(415, "not a PDF")
        doc_id = content_id(data)
        filename = Path(file.filename or "upload.pdf").name  # strip any client path

        if store.get(doc_id) is not None:  # same bytes already processed: free and instant
            job = store.create_job(uuid.uuid4().hex, doc_id, filename, "done")
            return JSONResponse(_job_out(job, store).model_dump(mode="json"), status_code=200)
        if active := store.active_job(doc_id):  # same file already in flight: don't pay twice
            return JSONResponse(_job_out(active, store).model_dump(mode="json"), status_code=202)

        job = store.create_job(uuid.uuid4().hex, doc_id, filename, "queued")
        pdf = upload_dir / f"{job['job_id']}.pdf"
        pdf.write_bytes(data)
        runner.submit(job["job_id"], pdf, doc_id)
        job = store.get_job(job["job_id"])  # may already be done (inline executor in tests)
        out = _job_out(job, store)
        return JSONResponse(
            out.model_dump(mode="json"), status_code=202, headers={"Location": out.status_url}
        )

    @app.get("/v1/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str) -> JobOut:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return _job_out(job, store)

    @app.get("/v1/contracts/{doc_id}", response_model=ContractResult)
    def get_contract(doc_id: str, include_text: bool = False) -> ContractResult:
        result = store.get(doc_id, include_text=include_text)
        if result is None:
            raise HTTPException(404, "contract not found")
        return result

    @app.get("/v1/queries")
    def list_queries() -> dict:
        return {name: sorted(defaults) for name, (_, defaults) in QUERIES.items()}

    @app.get("/v1/queries/{name}")
    def run_query(name: str, request: Request) -> dict:
        if name not in QUERIES:
            raise HTTPException(404, f"unknown query; available: {sorted(QUERIES)}")
        params = dict(request.query_params)
        try:
            rows = store.query(name, **params)
        except KeyError as e:  # unknown parameter
            raise HTTPException(422, str(e).strip('"')) from None
        except ValueError as e:  # e.g. days=abc
            raise HTTPException(422, str(e)) from None
        return {"query": name, "params": params, "rows": rows}

    return app


def __getattr__(name: str):
    """`uvicorn docintel.api.app:app` builds the production app lazily, so importing this
    module (e.g. in tests) doesn't open the real database."""
    if name == "app":
        return create_app()
    raise AttributeError(name)
