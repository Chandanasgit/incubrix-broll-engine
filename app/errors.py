class PipelineError(Exception):
    """A job-level failure with a stable error code (UPPER_SNAKE_CASE)."""

    def __init__(self, code, message, retryable=False, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self):
        return {"error": {"code": self.code, "message": self.message,
                          "retryable": self.retryable, "details": self.details}}
