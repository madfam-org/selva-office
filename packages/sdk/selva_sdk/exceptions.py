"""Exception classes for the AutoSwarm SDK."""


class AutoSwarmError(Exception):
    """Base exception for AutoSwarm SDK."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(AutoSwarmError):
    """Raised when authentication fails (401/403)."""


class TaskTimeoutError(AutoSwarmError):
    """Raised when wait_for_task exceeds timeout."""


class NotFoundError(AutoSwarmError):
    """Raised when a resource is not found (404)."""
