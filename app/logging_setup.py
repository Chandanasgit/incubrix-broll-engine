import contextvars
import json
import logging
import os
import sys
import time

correlation_id = contextvars.ContextVar("correlation_id", default="-")
job_id_var = contextvars.ContextVar("job_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                         + ".%03dZ" % int(record.msecs),
            "level": record.levelname,
            "message": record.getMessage(),
            "job_id": getattr(record, "job_id", None) or job_id_var.get(),
            "correlation_id": correlation_id.get(),
            "logger": record.name,
        }
        extra = getattr(record, "fields", None)
        if extra:
            data.update(extra)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


class StdoutHandler(logging.Handler):
    """Writes to whatever sys.stdout is at the time of the call, and never raises."""

    def emit(self, record):
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def setup_logging():
    handler = StdoutHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def get_logger(name="app"):
    return logging.getLogger(name)
