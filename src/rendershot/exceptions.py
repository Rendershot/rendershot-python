from __future__ import annotations


class RenderShotError(Exception):
    """Base exception for all rendershot SDK errors."""


class APIError(RenderShotError):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f'HTTP {status_code}: {detail}')


class AuthenticationError(APIError):
    """Raised on 401 — invalid or missing API key."""


class RateLimitError(APIError):
    """Raised on 429 — per-minute rate limit exceeded."""

    def __init__(self, status_code: int, detail: str, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(status_code, detail)


class JobFailedError(RenderShotError):
    """Raised when a queued render job reaches the 'failed' status."""

    def __init__(self, job_id: str, message: str) -> None:
        self.job_id = job_id
        super().__init__(f'Job {job_id} failed: {message}')


class JobTimeoutError(RenderShotError):
    """Raised when polling a job exceeds the configured timeout."""

    def __init__(self, job_id: str, timeout: float) -> None:
        self.job_id = job_id
        self.timeout = timeout
        super().__init__(f'Job {job_id} did not complete within {timeout}s')
