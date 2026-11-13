import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from docintel.api import app as app_mod
from docintel.api.app import create_app
from docintel.api.jobs import InlineExecutor, JobRunner
from docintel.storage.store import DuckDBStore
from tests.test_pipeline_store import _result

PDF = b"%PDF-1.4 fake contract bytes"


class FakePipeline:
    """Stands in for process_pdf: records calls, returns a canned result."""

    def __init__(self, status="ok", error=None, exc=None):
        self.calls = []
        self.status, self.error, self.exc = status, error, exc

    def __call__(self, pdf, *, doc_id):
        self.calls.append((pdf, doc_id))
        assert pdf.read_bytes().startswith(b"%PDF")  # upload was written before processing
        if self.exc:
            raise self.exc
        r = _result(doc_id)
        r.text = "contract text"
        r.status, r.error = self.status, self.error
        return r


def client(tmp_path, fake=None, executor=None):
    store = DuckDBStore()
    fake = fake or FakePipeline()
    runner = JobRunner(store, fake, executor or InlineExecutor())
    app = create_app(store=store, process=fake, runner=runner, upload_dir=tmp_path, seed_dir=None)
    return TestClient(app), store, fake


def upload(c, data=PDF, name="msa.pdf"):
    return c.post("/v1/jobs", files={"file": (name, data, "application/pdf")})


def test_job_lifecycle_and_result(tmp_path):
    c, store, fake = client(tmp_path)
    with c:
        r = upload(c)
        assert r.status_code == 202 and r.headers["location"] == r.json()["status_url"]
        job = c.get(r.json()["status_url"]).json()
        assert job["status"] == "done" and job["filename"] == "msa.pdf"
        assert job["result"]["record"]["governing_law"]["value"]["region"] == "New York"
        assert "needs_review" in job["result"]  # computed field is serialized
        assert job["result"]["text"] is None  # text only on request
        full = c.get(job["result_url"], params={"include_text": True}).json()
        assert full["text"] == "contract text"
    assert list(tmp_path.iterdir()) == []  # uploaded PDF deleted after processing


def test_same_file_twice_is_free(tmp_path):
    c, _, fake = client(tmp_path)
    with c:
        upload(c)
        r = upload(c, name="renamed.pdf")
        assert r.status_code == 200 and r.json()["status"] == "done"
    assert len(fake.calls) == 1  # processed once: content hash, not filename


def test_in_flight_duplicate_reuses_job(tmp_path):
    gate = threading.Event()

    class Slow(FakePipeline):
        def __call__(self, pdf, *, doc_id):
            gate.wait(5)
            return super().__call__(pdf, doc_id=doc_id)

    fake = Slow()
    c, _, _ = client(tmp_path, fake, ThreadPoolExecutor(max_workers=2))
    with c:
        a, b = upload(c), upload(c)
        assert a.json()["job_id"] == b.json()["job_id"] and b.status_code == 202
        gate.set()
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "data, code",
    [
        (b"hello, not a pdf", 415),
        (b"%PDF-" + b"0" * (app_mod.MAX_UPLOAD_BYTES), 413),
    ],
)
def test_upload_rejected(tmp_path, data, code):
    c, _, fake = client(tmp_path)
    with c:
        assert upload(c, data).status_code == code
    assert fake.calls == []


def test_pipeline_error_becomes_job_error(tmp_path):
    c, _, _ = client(tmp_path, FakePipeline(status="error", error="61 pages exceeds the limit"))
    with c:
        job = c.get(upload(c).json()["status_url"]).json()
    assert job["status"] == "error" and "61 pages" in job["error"]
    assert job["result"] is None


def test_crash_never_leaves_job_running(tmp_path):
    c, _, _ = client(tmp_path, FakePipeline(exc=RuntimeError("secret internals")))
    with c:
        job = c.get(upload(c).json()["status_url"]).json()
    assert job["status"] == "error"
    assert "secret internals" not in job["error"]  # no internal details leak to clients


def test_interrupted_jobs_failed_on_startup(tmp_path):
    store = DuckDBStore()
    store.create_job("j1", "d", "x.pdf", "running")
    app = create_app(store=store, process=FakePipeline(), upload_dir=tmp_path, seed_dir=None)
    with TestClient(app) as c:
        job = c.get("/v1/jobs/j1").json()
    assert job["status"] == "error" and "restart" in job["error"]


def test_not_found(tmp_path):
    c, _, _ = client(tmp_path)
    with c:
        assert c.get("/v1/jobs/nope").status_code == 404
        assert c.get("/v1/contracts/nope").status_code == 404
        assert c.get("/v1/queries/drop_table").status_code == 404


def test_queries(tmp_path):
    c, store, _ = client(tmp_path)
    with c:
        upload(c)
        assert "expiring_soon" in c.get("/v1/queries").json()
        r = c.get("/v1/queries/expiring_soon", params={"as_of": "2024-10-01", "days": 60})
        assert r.status_code == 200 and len(r.json()["rows"]) == 1
        assert c.get("/v1/queries/expiring_soon", params={"days": "abc"}).status_code == 422
        assert c.get("/v1/queries/governing_law_mix", params={"x": "1"}).status_code == 422


def test_healthz_and_openapi(tmp_path):
    c, _, _ = client(tmp_path)
    with c:
        assert c.get("/healthz").json() == {"status": "ok"}
        paths = c.get("/openapi.json").json()["paths"]
        assert {"/v1/jobs", "/v1/jobs/{job_id}", "/v1/contracts/{doc_id}"} <= set(paths)


def test_seeds_from_demo_export_when_empty(tmp_path):
    r = _result("seeded")
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "a.json").write_text(
        '{"result": ' + r.model_dump_json() + ', "truth": {}}'
    )
    store = DuckDBStore()
    app = create_app(store=store, process=FakePipeline(), upload_dir=tmp_path / "u",
                     seed_dir=tmp_path)  # fmt: skip
    with TestClient(app) as c:
        assert c.get("/v1/contracts/seeded").status_code == 200
    with TestClient(app):  # second startup: store not empty -> no re-seed, no duplicates
        pass
    assert store.con.execute("SELECT count(*) FROM contracts").fetchone()[0] == 1
