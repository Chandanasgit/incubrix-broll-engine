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


def silent_asr(path):
    return {"duration": 3.0, "words": []}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTAGE_PROVIDERS", "mock")
    monkeypatch.setenv("SCORER", "tag")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("QUERY_LLM_PROVIDER", "none")
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "1")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(worker_mod, "ASR_OVERRIDE", fake_asr)
    store = JobStore(str(tmp_path / "jobs.db"))
    worker = Worker(store, jobs_dir=str(tmp_path / "jobs"))
    with TestClient(create_app(store, worker)) as c:
        c.store = store
        yield c


def wait_done(client, job_id, timeout=60, headers=None):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get("/api/v1/jobs/" + job_id, headers=headers)
        assert r.status_code == 200
        if r.json()["status"] in ("succeeded", "failed"):
            return r.json()
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def error_shape_ok(body):
    e = body["error"]
    assert set(e) == {"code", "message", "retryable", "details"}
    assert e["code"] == e["code"].upper()


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_script_job_end_to_end(client):
    r = client.post("/api/v1/broll/jobs", json={"script": SCRIPT, "aspect_ratios": ["16:9", "9:16"]},
                    headers={"X-Correlation-Id": "abc-123"})
    assert r.status_code == 202
    assert r.headers["X-Correlation-Id"] == "abc-123"
    job = wait_done(client, r.json()["job_id"])
    assert job["status"] == "succeeded" and job["progress"] == 100
    files = job["result"]["files"]
    assert {"video_16x9.mp4", "video_9x16.mp4", "timeline.json", "manifest.json"} <= set(files)
    d = client.get(files["video_16x9.mp4"])
    assert d.status_code == 200 and len(d.content) > 1000


def test_idempotency_same_key_same_job(client):
    body = {"script": SCRIPT}
    a = client.post("/api/v1/broll/jobs", json=body, headers={"Idempotency-Key": "k1"})
    b = client.post("/api/v1/broll/jobs", json=body, headers={"Idempotency-Key": "k1"})
    assert a.json()["job_id"] == b.json()["job_id"]
    assert b.headers["Idempotent-Replayed"] == "true"
    assert client.store.count() == 1
    wait_done(client, a.json()["job_id"])


def test_idempotency_key_with_different_body_conflicts(client):
    client.post("/api/v1/broll/jobs", json={"script": SCRIPT}, headers={"Idempotency-Key": "k2"})
    r = client.post("/api/v1/broll/jobs", json={"script": "Something else entirely."},
                    headers={"Idempotency-Key": "k2"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize("body,code,status", [
    ({}, "INVALID_INPUT", 400),
    ({"script": "hi", "audio_url": "http://x.test/a.mp3"}, "INVALID_INPUT", 400),
    ({"script": "   "}, "EMPTY_SCRIPT", 400),
    ({"script": SCRIPT, "aspect_ratios": ["4:3"]}, "INVALID_ASPECT_RATIO", 400),
    ({"audio_url": "ftp://x.test/a.mp3"}, "INVALID_URL", 400),
    ({"scenes": [{"text": "hi"}]}, "SCENES_NOT_SUPPORTED", 400),
    ({"script": SCRIPT, "aspect_ratios": "16:9"}, "VALIDATION_ERROR", 422),
])
def test_clear_errors(client, body, code, status):
    r = client.post("/api/v1/broll/jobs", json=body)
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    error_shape_ok(r.json())


def test_unknown_job_and_route(client):
    r = client.get("/api/v1/jobs/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "JOB_NOT_FOUND"
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_failed_job_reports_error(client, monkeypatch):
    monkeypatch.setattr(worker_mod, "ASR_OVERRIDE", silent_asr)
    r = client.post("/api/v1/broll/jobs", json={"script": SCRIPT})
    job = wait_done(client, r.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "NO_SPEECH_DETECTED"
    assert client.get("/api/v1/jobs/%s/files/video_16x9.mp4" % job["job_id"]).status_code == 404


def test_private_urls_blocked_when_not_allowed(client, monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_URLS", "0")
    r = client.post("/api/v1/broll/jobs", json={"audio_url": "http://127.0.0.1/a.mp3"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "URL_NOT_ALLOWED"


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "s3cret")
    assert client.get("/health").status_code == 200
    r = client.post("/api/v1/broll/jobs", json={"script": SCRIPT})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    r = client.post("/api/v1/broll/jobs", json={"script": SCRIPT}, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 202
    wait_done(client, r.json()["job_id"], headers={"Authorization": "Bearer s3cret"})


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    codes = [client.post("/api/v1/broll/jobs", json={"script": SCRIPT + " %d" % i}).status_code for i in range(3)]
    assert codes == [202, 202, 429]


def test_unfinished_jobs_fail_after_restart(tmp_path):
    store = JobStore(str(tmp_path / "x.db"))
    job, _ = store.create({"script": "a"}, None, "c")
    assert store.fail_unfinished() == 1
    assert store.get(job["id"])["error"]["code"] == "SERVER_RESTARTED"
