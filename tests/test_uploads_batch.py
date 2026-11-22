import json
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from app import worker as worker_mod
from app.api import create_app
from app.jobs import JobStore
from app.render import probe
from app.worker import Worker
from scripts.batch import load_items, run_batch

WORDS = ["Money", "matters", "today.", "Banks", "keep", "cash", "safe."]


def fake_asr(path):
    d = float(probe(path)["format"]["duration"])
    step = d / len(WORDS)
    return {"duration": d, "words": [{"word": " " + w, "start": i * step, "end": (i + 1) * step}
                                     for i, w in enumerate(WORDS)]}


def make_wav(path, seconds=3):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=%d" % seconds, str(path)], check=True)
    return path


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTAGE_PROVIDERS", "mock")
    monkeypatch.setenv("SCORER", "tag")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("QUERY_LLM_PROVIDER", "none")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(worker_mod, "ASR_OVERRIDE", fake_asr)
    store = JobStore(str(tmp_path / "jobs.db"))
    worker = Worker(store, jobs_dir=str(tmp_path / "jobs"))
    with TestClient(create_app(store, worker)) as c:
        yield c


def wait_done(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        body = client.get("/api/v1/jobs/" + job_id).json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_upload_then_job(client, tmp_path):
    wav = make_wav(tmp_path / "a.wav")
    r = client.post("/api/v1/uploads", files={"file": ("a.wav", wav.read_bytes())})
    assert r.status_code == 201 and r.json()["audio_url"].startswith("upload://")
    job = client.post("/api/v1/broll/jobs", json={"audio_url": r.json()["audio_url"]}).json()
    assert wait_done(client, job["job_id"])["status"] == "succeeded"


def test_upload_idempotency(client, tmp_path):
    wav = make_wav(tmp_path / "a.wav")
    data = wav.read_bytes()
    a = client.post("/api/v1/uploads", files={"file": ("a.wav", data)}, headers={"Idempotency-Key": "u1"})
    b = client.post("/api/v1/uploads", files={"file": ("a.wav", data)}, headers={"Idempotency-Key": "u1"})
    assert a.json()["upload_id"] == b.json()["upload_id"]
    assert b.headers["Idempotent-Replayed"] == "true"
    c = client.post("/api/v1/uploads", files={"file": ("b.wav", data + b"zz")}, headers={"Idempotency-Key": "u1"})
    assert c.status_code == 409 and c.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_upload_errors(client, monkeypatch):
    r = client.post("/api/v1/uploads", files={"file": ("e.wav", b"")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "EMPTY_FILE"
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.0001")
    r = client.post("/api/v1/uploads", files={"file": ("big.wav", b"x" * 5000)})
    assert r.status_code == 413 and r.json()["error"]["code"] == "INPUT_TOO_LARGE"
    r = client.post("/api/v1/broll/jobs", json={"audio_url": "upload://doesnotexist"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


def test_load_items_from_folder(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    (d / "one.txt").write_text("Money matters today.")
    (d / "two.wav").write_bytes(b"x")
    (d / "three.json").write_text(json.dumps({"script": "Hi there.", "aspect_ratios": ["9:16"]}))
    (d / "ignored.md").write_text("x")
    items = load_items(d)
    assert [i["name"] for i in items] == ["one", "three", "two"]
    assert items[1]["request"]["aspect_ratios"] == ["9:16"]
    assert items[2]["audio_file"].endswith("two.wav")


def test_batch_end_to_end(client, tmp_path):
    wav = make_wav(tmp_path / "talk.wav")
    items = [
        {"name": "ok", "audio_file": None, "request": {"script": "Money matters today. Banks keep cash safe."}},
        {"name": "empty", "audio_file": None, "request": {"script": "   "}},
        {"name": "talk", "audio_file": str(wav), "request": {}},
    ]
    rows = run_batch(client, items, tmp_path / "res", {"aspect_ratios": ["16:9"]},
                     timeout=120, poll=0.2, log=lambda *a: None)
    by = {r["name"]: r for r in rows}
    assert by["ok"]["status"] == "succeeded" and "video_16x9.mp4" in by["ok"]["files"]
    assert (tmp_path / "res" / "ok" / "video_16x9.mp4").stat().st_size > 1000
    assert by["talk"]["status"] == "succeeded"
    assert by["empty"]["status"] == "rejected" and by["empty"]["error_code"] == "EMPTY_SCRIPT"
    assert (tmp_path / "res" / "summary.json").exists() and (tmp_path / "res" / "summary.csv").exists()
