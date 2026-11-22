import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class IdempotencyConflict(Exception):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    idem_key TEXT UNIQUE,
    request_hash TEXT,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    request TEXT,
    result TEXT,
    error TEXT,
    correlation_id TEXT,
    created_at REAL,
    updated_at REAL
)
"""
_JSON_COLS = ("request", "result", "error")
_UPDATABLE = {"status", "progress", "message", "result", "error"}


def request_hash(request):
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


class JobStore:
    def __init__(self, path=None):
        self.path = path or os.getenv("DB_PATH", "data/jobs.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    @staticmethod
    def _row(row):
        if row is None:
            return None
        d = dict(row)
        for col in _JSON_COLS:
            d[col] = json.loads(d[col]) if d.get(col) else None
        return d

    def create(self, request, idem_key=None, correlation_id=None):
        """Returns (job, created). Same key and same request returns the existing job."""
        h = request_hash(request)
        with self._lock:
            if idem_key:
                row = self._conn.execute("SELECT * FROM jobs WHERE idem_key = ?", (idem_key,)).fetchone()
                if row is not None:
                    if row["request_hash"] != h:
                        raise IdempotencyConflict(idem_key)
                    return self._row(row), False
            job_id = uuid.uuid4().hex[:16]
            now = time.time()
            self._conn.execute(
                "INSERT INTO jobs (id, idem_key, request_hash, status, progress, message, request,"
                " correlation_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, idem_key, h, "queued", 0, "queued", json.dumps(request),
                 correlation_id, now, now))
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row(row), True

    def get(self, job_id):
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row)

    def update(self, job_id, **fields):
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError("cannot update: %s" % sorted(bad))
        cols, vals = [], []
        for k, v in fields.items():
            cols.append("%s = ?" % k)
            vals.append(json.dumps(v) if k in _JSON_COLS else v)
        cols.append("updated_at = ?")
        vals.append(time.time())
        vals.append(job_id)
        with self._lock:
            self._conn.execute("UPDATE jobs SET %s WHERE id = ?" % ", ".join(cols), vals)
            self._conn.commit()

    def fail_unfinished(self):
        """Jobs left queued or running by a crashed or restarted server cannot continue."""
        err = json.dumps({"code": "SERVER_RESTARTED", "message": "The server restarted before this job finished.",
                          "retryable": True, "details": {}})
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status='failed', error=?, message='failed', updated_at=? "
                "WHERE status IN ('queued','running')", (err, time.time()))
            self._conn.commit()
            return cur.rowcount

    def count(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def ping(self):
        with self._lock:
            self._conn.execute("SELECT 1")
