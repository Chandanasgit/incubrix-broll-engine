import os
from pathlib import Path
from urllib.parse import urljoin

import httpx

from .apierrors import ApiError
from .errors import PipelineError
from .netcheck import check_url


def download_audio(url, dest):
    """Download an input file with a size limit. Redirects are followed manually and re-checked."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(float(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024)
    timeout = float(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "60"))
    current = url
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for _ in range(4):
                try:
                    check_url(current)
                except ApiError as exc:
                    raise PipelineError("AUDIO_DOWNLOAD_FAILED", exc.message, details={"url_error": exc.code})
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    resp.raise_for_status()
                    size = 0
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_bytes(65536):
                            size += len(chunk)
                            if size > max_bytes:
                                raise PipelineError("INPUT_TOO_LARGE", "The input file is larger than allowed.",
                                                    details={"max_mb": max_bytes // (1024 * 1024)})
                            f.write(chunk)
                    return dest
            raise PipelineError("AUDIO_DOWNLOAD_FAILED", "Too many redirects.")
    except httpx.HTTPError as exc:
        dest.unlink(missing_ok=True)
        raise PipelineError("AUDIO_DOWNLOAD_FAILED", "Could not download the audio: %s" % type(exc).__name__,
                            retryable=True)
    except PipelineError:
        dest.unlink(missing_ok=True)
        raise
