import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import logging_setup as ls
from .errors import PipelineError
from .fetch import download_audio
from .llm import build_query_writer
from .pipeline import run_pipeline
from .providers import build_providers
from .ranker import ClipScorer, TagScorer
from .text_input import run_script
from .tts import build_tts

log = ls.get_logger("worker")

ASR_OVERRIDE = None  # tests replace this with a fake transcription function
RESULT_FILES = ("captions.srt", "timeline.json", "manifest.json")

_scorer = None
_scorer_lock = threading.Lock()


def get_scorer():
    global _scorer
    with _scorer_lock:
        if _scorer is None:
            _scorer = TagScorer() if os.getenv("SCORER", "clip") == "tag" else ClipScorer()
        return _scorer


def list_result_files(out_dir):
    out = Path(out_dir)
    names = [p.name for p in sorted(out.glob("video_*.mp4"))]
    names += [n for n in RESULT_FILES if (out / n).exists()]
    return names


class Worker:
    def __init__(self, store, jobs_dir=None, concurrency=None):
        self.store = store
        self.root = Path(jobs_dir or os.getenv("JOBS_DIR", "data/jobs"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=int(concurrency or os.getenv("JOB_CONCURRENCY", "1")))

    def out_dir(self, job_id):
        return self.root / job_id / "out"

    def submit(self, job_id):
        self.pool.submit(self._run, job_id)

    def _run(self, job_id):
        job = self.store.get(job_id)
        ls.job_id_var.set(job_id)
        ls.correlation_id.set((job or {}).get("correlation_id") or "-")
        if job is None:
            return
        req = job["request"]
        out = self.out_dir(job_id)
        self.store.update(job_id, status="running", progress=1, message="starting")
        log.info("job started")
        try:
            kw = dict(
                providers=build_providers(), scorer=get_scorer(), ratios=req["aspect_ratios"],
                avoid=req.get("avoid") or [], captions=req.get("captions") or {}, job_id=job_id,
                query_writer=build_query_writer(),
                progress=lambda pct, msg: self.store.update(job_id, progress=int(pct), message=msg))
            if ASR_OVERRIDE is not None:
                kw["transcribe_fn"] = ASR_OVERRIDE
            if req.get("audio_url"):
                audio = download_audio(req["audio_url"], self.root / job_id / "input_audio")
                res = run_pipeline(audio, out, **kw)
            else:
                res = run_script(req["script"], out, tts=build_tts(), **kw)
            self.store.update(job_id, status="succeeded", progress=100, message="done",
                              result={"files": list_result_files(out), "warnings": res.get("warnings", [])})
            log.info("job succeeded")
        except PipelineError as exc:
            self.store.update(job_id, status="failed", message="failed", error=exc.to_dict()["error"])
            log.warning("job failed: %s" % exc.code)
        except Exception:
            log.exception("job crashed")
            self.store.update(job_id, status="failed", message="failed", error={
                "code": "INTERNAL_ERROR", "message": "An unexpected error occurred.",
                "retryable": False, "details": {}})
