import time

import pytest
from fastapi.testclient import TestClient

from app import worker as worker_mod
from app.api import create_app
from app.jobs import JobStore
from app.render import probe
from app.worker import Worker

WORDS = ["Money", "matters", "today.", "Banks", "keep", "cash", "safe."]
SCRIPT = "Money matters today. Banks keep cash safe."


def fake_asr(path):
    d = float(probe(path)["format"]["duration"])
    step = d / len(WORDS)
    return {"duration": d, "words": [{"word": " " + w, "start": i * step, "end": (i + 1) * step}
                                     for i, w in enumerate(WORDS)]}


class FakeStorage:
    name = "fake"

    def __init__(self, fail=False):
        self.objects, self.fail = {}, fail

    def upload_file(self, path, key):
        if self.fail:
            raise RuntimeError("storage down")
        with open(path, "rb") as f:
            self.objects[key] = f.read()

    def presign(self, key, expires=None):
        return "http://files.test/" + key + "?sig=1"

    def ping(self):
        pass


def make_client(tmp_path, monkeypatch, storage):
    monkeypatch.setenv("FOOTAGE_PROVIDERS", "mock")
    monkeypatch.setenv("SCORER", "tag")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("QUERY_LLM_PROVIDER", "none")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(worker_mod, "ASR_OVERRIDE", fake_asr)
    store = JobStore(str(tmp_path / "jobs.db"))
    worker = Worker(store, jobs_dir=str(tmp_path / "jobs"), storage=storage)
    return TestClient(create_app(store, worker, storage))


def wait_done(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get("/api/v1/jobs/" + job_id).json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_results_are_uploaded_and_linked(tmp_path, monkeypatch):
    storage = FakeStorage()
    with make_client(tmp_path, monkeypatch, storage) as c:
        jid = c.post("/api/v1/broll/jobs", json={"script": SCRIPT}).json()["job_id"]
        job = wait_done(c, jid)
        assert job["status"] == "succeeded"
        assert job["result"]["storage"] == "s3"
        for name, url in job["result"]["files"].items():
            assert url.startswith("http://files.test/jobs/%s/" % jid)
            assert ("jobs/%s/%s" % (jid, name)) in storage.objects
        assert len(storage.objects["jobs/%s/video_16x9.mp4" % jid]) > 1000


def test_upload_failure_falls_back_to_api_links(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, FakeStorage(fail=True)) as c:
        jid = c.post("/api/v1/broll/jobs", json={"script": SCRIPT}).json()["job_id"]
        job = wait_done(c, jid)
        assert job["status"] == "succeeded"
        assert job["result"]["storage"] == "local"
        assert any("Object storage upload failed" in w for w in job["result"]["warnings"])
        url = job["result"]["files"]["video_16x9.mp4"]
        assert url.startswith("/api/v1/jobs/")
        assert c.get(url).status_code == 200


def test_ready_reports_object_storage(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, FakeStorage()) as c:
        body = c.get("/ready").json()
        assert body["status"] == "ready" and body["checks"]["object_storage"] == "ok"
