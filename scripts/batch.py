"""Batch runner: send a folder or file of test inputs to the API and collect every result in one folder.

Folder input:  *.txt = script, *.mp3/*.wav/*.m4a = audio (uploaded), *.json = a raw job request.
File input:    a .jsonl file (one request per line) or a .json file (a list of requests).
A request may carry "name" and, for audio, "audio_file" (a local path).

    python -m scripts.batch samples/inputs results --api http://localhost:8000
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx

AUDIO_EXT = {".mp3", ".wav", ".m4a"}
FINAL = ("succeeded", "failed")


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name)) or "item"


def _from_dict(d, index):
    d = dict(d)
    name = _safe(d.pop("name", "item_%03d" % index))
    audio = d.pop("audio_file", None)
    return {"name": name, "audio_file": audio, "request": d}


def load_items(path):
    path = Path(path)
    items = []
    if path.is_dir():
        for i, f in enumerate(sorted(path.iterdir())):
            ext = f.suffix.lower()
            if ext == ".txt":
                items.append({"name": _safe(f.stem), "audio_file": None,
                              "request": {"script": f.read_text(encoding="utf-8")}})
            elif ext in AUDIO_EXT:
                items.append({"name": _safe(f.stem), "audio_file": str(f), "request": {}})
            elif ext == ".json":
                d = json.loads(f.read_text(encoding="utf-8"))
                d.setdefault("name", f.stem)
                items.append(_from_dict(d, i))
    elif path.suffix.lower() == ".jsonl":
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        items = [_from_dict(json.loads(ln), i) for i, ln in enumerate(lines)]
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data if isinstance(data, list) else [data]
        items = [_from_dict(d, i) for i, d in enumerate(data)]
    elif path.suffix.lower() == ".txt":
        items = [{"name": _safe(path.stem), "audio_file": None,
                  "request": {"script": path.read_text(encoding="utf-8")}}]
    elif path.suffix.lower() in AUDIO_EXT:
        items = [{"name": _safe(path.stem), "audio_file": str(path), "request": {}}]
    else:
        raise SystemExit("Unsupported input: %s" % path)
    seen = {}
    for it in items:  # keep folder names unique
        n = seen.get(it["name"], 0)
        seen[it["name"]] = n + 1
        if n:
            it["name"] = "%s_%d" % (it["name"], n + 1)
    return items


def _error_from(resp):
    try:
        err = resp.json()["error"]
        return {"code": err.get("code", "HTTP_%d" % resp.status_code), "message": err.get("message", ""),
                "retryable": bool(err.get("retryable"))}
    except Exception:
        return {"code": "HTTP_%d" % resp.status_code, "message": resp.text[:200], "retryable": False}


def _post(client, url, tries=3, **kw):
    """POST with retries. This is safe because every request carries an Idempotency-Key."""
    last = None
    for attempt in range(tries):
        try:
            resp = client.post(url, **kw)
            if resp.status_code < 500:
                return resp, None
            last = _error_from(resp)
        except httpx.HTTPError as exc:
            last = {"code": "CLIENT_NETWORK_ERROR", "message": type(exc).__name__, "retryable": True}
        time.sleep(1 + attempt)
    return None, last


def submit(client, item, run_id, defaults):
    req = dict(defaults)
    req.update(item["request"])
    key = "batch-%s-%s" % (run_id, hashlib.sha1(item["name"].encode()).hexdigest()[:10])
    if item.get("audio_file"):
        path = Path(item["audio_file"])
        if not path.is_file():
            return {"error": {"code": "INPUT_FILE_MISSING", "message": str(path), "retryable": False}}
        with open(path, "rb") as f:
            resp, err = _post(client, "/api/v1/uploads", files={"file": (path.name, f)},
                              headers={"Idempotency-Key": key + "-upload"})
        if resp is None:
            return {"error": err}
        if resp.status_code >= 400:
            return {"error": _error_from(resp)}
        req["audio_url"] = resp.json()["audio_url"]
    resp, err = _post(client, "/api/v1/broll/jobs", json=req, headers={"Idempotency-Key": key})
    if resp is None:
        return {"error": err}
    if resp.status_code != 202:
        return {"error": _error_from(resp)}
    return {"job_id": resp.json()["job_id"]}


def download(client, url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(url, timeout=300) if url.startswith("http") else client.get(url)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def run_batch(client, items, out_dir, defaults, timeout=900, poll=2.0, log=print):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d%H%M%S")
    rows, pending, started = {}, {}, {}
    for it in items:
        t0 = time.time()
        res = submit(client, it, run_id, defaults)
        if "job_id" in res:
            pending[it["name"]] = res["job_id"]
            started[it["name"]] = t0
            log("submitted %s -> %s" % (it["name"], res["job_id"]))
        else:
            rows[it["name"]] = {"name": it["name"], "job_id": "", "status": "rejected", "seconds": 0,
                                "error_code": res["error"]["code"], "retryable": res["error"]["retryable"],
                                "warnings": 0, "files": []}
            log("rejected  %s: %s" % (it["name"], res["error"]["code"]))
    deadline = time.time() + timeout
    jobs = {}
    while pending and time.time() < deadline:
        for name, jid in list(pending.items()):
            try:
                job = client.get("/api/v1/jobs/" + jid).json()
            except (httpx.HTTPError, ValueError):
                continue
            if job.get("status") in FINAL:
                jobs[name] = job
                del pending[name]
                log("%-9s %s (%.0fs)" % (job["status"], name, time.time() - started[name]))
        if pending:
            time.sleep(poll)
    for name, jid in pending.items():
        rows[name] = {"name": name, "job_id": jid, "status": "timeout", "seconds": round(time.time() - started[name]),
                      "error_code": "BATCH_TIMEOUT", "retryable": True, "warnings": 0, "files": []}
    for name, job in jobs.items():
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        files, err_code, retryable = [], "", False
        if job["status"] == "succeeded":
            for fname, url in job["result"]["files"].items():
                try:
                    download(client, url, folder / fname)
                    files.append(fname)
                except (httpx.HTTPError, OSError):
                    log("could not download %s/%s" % (name, fname))
        else:
            err = job.get("error") or {}
            err_code, retryable = err.get("code", ""), bool(err.get("retryable"))
        rows[name] = {"name": name, "job_id": job["job_id"], "status": job["status"],
                      "seconds": round(time.time() - started[name]), "error_code": err_code,
                      "retryable": retryable, "warnings": len((job.get("result") or {}).get("warnings", [])),
                      "files": files}
    ordered = [rows[it["name"]] for it in items if it["name"] in rows]
    (out / "summary.json").write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "job_id", "status", "seconds", "error_code", "retryable", "warnings", "files"])
        for r in ordered:
            w.writerow([r["name"], r["job_id"], r["status"], r["seconds"], r["error_code"], r["retryable"],
                        r["warnings"], ";".join(r["files"])])
    return ordered


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("out")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--token", default=None)
    ap.add_argument("--ratios", default="16:9")
    ap.add_argument("--avoid", default="")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    headers = {"Authorization": "Bearer " + a.token} if a.token else {}
    items = load_items(a.input)
    if not items:
        sys.exit("No inputs found in %s" % a.input)
    defaults = {"aspect_ratios": [r for r in a.ratios.split(",") if r],
                "avoid": [x for x in a.avoid.split(",") if x]}
    with httpx.Client(base_url=a.api, headers=headers, timeout=60) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError:
            sys.exit("Cannot reach the API at %s" % a.api)
        rows = run_batch(client, items, a.out, defaults, timeout=a.timeout)
    ok = sum(1 for r in rows if r["status"] == "succeeded")
    print("\n%d of %d succeeded. Results: %s" % (ok, len(rows), Path(a.out).resolve()))


if __name__ == "__main__":
    main()
