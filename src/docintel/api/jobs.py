"""Run extraction jobs off the request path.

A bounded thread pool, not asyncio: the work is blocking (pypdf, the OpenAI SDK's sync
client), and threads let it run without blocking the event loop. Bounded, because every
job may call a paid API; the pool size caps concurrent spend.
Behind a small interface so a real queue (Cloud Tasks) can replace it at scale.
"""

import logging
from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from pathlib import Path

from docintel.pipeline import ContractResult
from docintel.storage.store import ResultStore
from docintel.tracing import stage

log = logging.getLogger("docintel.jobs")

ProcessFn = Callable[..., ContractResult]  # same signature as pipeline.process_pdf


class InlineExecutor(Executor):
    """Runs the job immediately in the caller's thread. For tests: deterministic."""

    def submit(self, fn, /, *args, **kwargs) -> Future:
        f: Future = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 - surfaced through the Future
            f.set_exception(e)
        return f


class JobRunner:
    def __init__(self, store: ResultStore, process: ProcessFn, executor: Executor | None = None):
        self.store = store
        self.process = process
        self.executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")

    def submit(self, job_id: str, pdf: Path, doc_id: str) -> None:
        self.executor.submit(self._run, job_id, pdf, doc_id)

    def _run(self, job_id: str, pdf: Path, doc_id: str) -> None:
        self.store.update_job(job_id, "running")
        try:
            result = self.process(pdf, doc_id=doc_id)
            if result.status != "ok":
                self.store.update_job(job_id, "error", result.error)
                log.info("job %s failed: %s", job_id, result.error)
                return
            with stage("store", "CHAIN", doc_id=doc_id, job_id=job_id):
                self.store.save(result)
            self.store.update_job(job_id, "done")
            log.info("job %s done: %s $%.4f %.1fs", job_id, result.parser, result.cost_usd,
                     result.seconds)  # fmt: skip
        except Exception as e:  # never leave a job stuck in 'running'
            log.exception("job %s crashed", job_id)
            self.store.update_job(job_id, "error", f"internal error: {type(e).__name__}")
        finally:
            pdf.unlink(missing_ok=True)  # don't keep uploaded contracts around

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)
