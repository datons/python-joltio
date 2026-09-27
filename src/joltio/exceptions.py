"""Joltio client exceptions, including the legacy DatonsError alias."""


class JoltioError(Exception):
    """Base exception for all Joltio client errors."""


DatonsError = JoltioError


class AuthenticationError(DatonsError):
    """Invalid or missing API key."""

    def __init__(self, message: str = "Invalid or missing API key."):
        super().__init__(message)


class QueryError(DatonsError):
    """Query execution failed (bad SQL, timeout, read-only violation, etc.)."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        super().__init__(f"Query error ({status_code}): {detail}")


class RateLimitError(DatonsError):
    """Rate limit exceeded.

    Attributes:
        retry_after: Seconds until the limit resets.
        tier: Current API key tier (e.g. 'explorer', 'professional').
        detail: Full error detail from the server.
    """

    def __init__(
        self,
        retry_after: int | None = None,
        *,
        tier: str | None = None,
        detail: dict | str | None = None,
    ):
        self.retry_after = retry_after
        self.tier = tier
        self.detail = detail

        # Build a human-readable message from the server response
        if isinstance(detail, dict):
            msg = detail.get("error", "Rate limit exceeded.")
            upgrade = detail.get("upgrade")
            if upgrade:
                msg += f" {upgrade}"
        else:
            msg = "Rate limit exceeded."
            if retry_after:
                msg += f" Retry after {retry_after}s."

        super().__init__(msg)
