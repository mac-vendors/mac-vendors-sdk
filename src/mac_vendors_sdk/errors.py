"""Exception types raised by :class:`mac_vendors_sdk.MacVendorsAPI`."""

from __future__ import annotations

from typing import Any

import httpx

__all__ = [
    "AuthError",
    "MacVendorsApiError",
    "NotFoundError",
    "RateLimitError",
]


class MacVendorsApiError(Exception):
    """Base error for a non-2xx response from the mac-vendors API.

    Attributes:
        status_code: HTTP status code of the failing response.
        detail: Parsed ``detail`` field from a FastAPI error body, or the raw
            response text when the body was not JSON / had no ``detail`` key.
        response: The originating :class:`httpx.Response`.
    """

    def __init__(
        self,
        status_code: int,
        detail: Any,
        response: httpx.Response,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.response = response
        super().__init__(f"HTTP {status_code}: {detail}")


class AuthError(MacVendorsApiError):
    """Raised for 401 / 403 responses (missing or insufficient credentials)."""


class NotFoundError(MacVendorsApiError):
    """Raised for 404 responses (resource does not exist)."""


class RateLimitError(MacVendorsApiError):
    """Raised for 429 responses.

    Attributes:
        retry_after: Value of the ``Retry-After`` header as an int (seconds),
            or ``None`` when the header was absent or not an integer.
    """

    def __init__(
        self,
        status_code: int,
        detail: Any,
        response: httpx.Response,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(status_code, detail, response)
