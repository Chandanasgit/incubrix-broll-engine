from .errors import PipelineError


class ApiError(PipelineError):
    """An error that is returned to the HTTP caller with a status code."""

    def __init__(self, status, code, message, retryable=False, details=None):
        super().__init__(code, message, retryable=retryable, details=details)
        self.status = status


def from_pipeline(exc, status=400):
    return ApiError(status, exc.code, exc.message, retryable=exc.retryable, details=exc.details)
