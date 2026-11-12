from __future__ import annotations


class DomainError(Exception):
    """Business-rule failure rendered as the canonical error contract (spec §3.8)."""

    def __init__(self, status: int, code: str, message: str, details: dict | list | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def not_found(what: str) -> DomainError:
    return DomainError(404, "NOT_FOUND", f"{what} was not found.")
