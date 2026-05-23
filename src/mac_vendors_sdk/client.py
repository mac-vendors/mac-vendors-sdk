"""Async HTTP client for the mac-vendors public REST API."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from .errors import AuthError, MacVendorsApiError, NotFoundError, RateLimitError
from .models import (
    BatchLookupResponse,
    CountryItem,
    DatabaseStatsResponse,
    ExportListResponse,
    MacHistory,
    TopVendorItem,
    VendorAssignmentsResponse,
    VendorHistory,
    VendorItem,
    VendorListResponse,
    VendorResponse,
    VendorVersionItem,
)

__all__ = ["DEFAULT_BASE_URL", "MacVendorsAPI"]

#: The official hosted API. The SDK targets this host; it is not configurable.
DEFAULT_BASE_URL = "https://mac-vendors.lizardsystems.com"


def _to_iso(value: datetime | str) -> str:
    """Render an ``as_of`` parameter as a UTC ISO 8601 string.

    A naive datetime is assumed to be UTC; an aware datetime is converted to
    UTC, so point-in-time queries are never silently shifted by the caller's
    local offset. A string is passed through unchanged.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value


def _parse_retry_after(raw: str | None) -> int | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date) into seconds."""
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0, int((when - datetime.now(timezone.utc)).total_seconds()))


class MacVendorsAPI:
    """Async client for the hosted mac-vendors REST API.

    The client always targets the official service
    (``https://mac-vendors.lizardsystems.com/api/v1``); the base URL is not
    configurable. Advanced/testing callers may inject their own
    pre-configured ``httpx.AsyncClient``.

    Example:
        async with MacVendorsAPI(api_key="...") as api:
            result = await api.lookup("00:50:56:AA:BB:CC")
            print(result.vendor)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout
        self._owns_client = client is None
        if client is not None:
            if api_key is not None or token is not None:
                raise ValueError(
                    "Pass api_key/token OR an injected client (with its own auth "
                    "headers), not both - credentials are ignored on an injected client."
                )
            self._client = client
        else:
            headers: dict[str, str] = {}
            if api_key is not None:
                headers["X-API-Key"] = api_key
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            self._client = httpx.AsyncClient(
                base_url=f"{DEFAULT_BASE_URL}/api/v1",
                headers=headers,
                timeout=timeout,
            )

    # --- lifecycle -------------------------------------------------------

    async def __aenter__(self) -> MacVendorsAPI:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if it is owned by this instance."""
        if self._owns_client:
            await self._client.aclose()

    # --- internals -------------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Raise a typed error for a non-2xx response."""
        if response.is_success:
            return

        detail: Any
        try:
            body = response.json()
        except (ValueError, httpx.DecodingError):
            detail = response.text or None
        else:
            detail = body.get("detail", body) if isinstance(body, dict) else body

        status = response.status_code
        if status in (401, 403):
            raise AuthError(status, detail, response)
        if status == 404:
            raise NotFoundError(status, detail, response)
        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(status, detail, response, retry_after=retry_after)
        raise MacVendorsApiError(status, detail, response)

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        response = await self._client.request(method, url, params=params, json=json)
        self._raise_for_status(response)
        return response.json()

    # --- lookup endpoints ------------------------------------------------

    async def lookup(
        self,
        mac: str,
        *,
        as_of: datetime | str | None = None,
    ) -> VendorResponse:
        """Look up the vendor for a single MAC address (GET /lookup/{mac})."""
        params: dict[str, Any] = {}
        if as_of is not None:
            params["as_of"] = _to_iso(as_of)
        data = await self._request_json(
            "GET", f"/lookup/{quote(mac, safe='')}", params=params or None
        )
        return VendorResponse.model_validate(data)

    async def lookup_history(self, mac: str) -> MacHistory:
        """Get the SCD2 history for a MAC assignment (GET /lookup/{mac}/history)."""
        data = await self._request_json("GET", f"/lookup/{quote(mac, safe='')}/history")
        return MacHistory.model_validate(data)

    async def batch_lookup(self, mac_addresses: list[str]) -> BatchLookupResponse:
        """Look up multiple MAC addresses at once (POST /lookup/batch)."""
        data = await self._request_json(
            "POST", "/lookup/batch", json={"mac_addresses": mac_addresses}
        )
        return BatchLookupResponse.model_validate(data)

    # --- vendors endpoints -----------------------------------------------

    async def list_vendors(
        self,
        *,
        name: str | None = None,
        letter: str | None = None,
        registry: str | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "organization_name",
        sort_order: str = "asc",
    ) -> VendorListResponse:
        """List vendors with pagination and filtering (GET /vendors)."""
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if name is not None:
            params["name"] = name
        if letter is not None:
            params["letter"] = letter
        if registry is not None:
            params["registry"] = registry
        data = await self._request_json("GET", "/vendors", params=params)
        return VendorListResponse.model_validate(data)

    async def top_vendors(self, *, limit: int = 15) -> list[TopVendorItem]:
        """Get top vendors by assignment count (GET /vendors/top)."""
        data = await self._request_json("GET", "/vendors/top", params={"limit": limit})
        return [TopVendorItem.model_validate(item) for item in data]

    async def search_vendors(self, q: str, *, limit: int = 20) -> list[VendorItem]:
        """Search vendors by name (GET /vendors/search)."""
        data = await self._request_json("GET", "/vendors/search", params={"q": q, "limit": limit})
        return [VendorItem.model_validate(item) for item in data]

    async def vendor_assignments(self, name: str) -> VendorAssignmentsResponse:
        """Get all assignments for a vendor (GET /vendors/{name}/assignments)."""
        data = await self._request_json("GET", f"/vendors/{quote(name, safe='/')}/assignments")
        return VendorAssignmentsResponse.model_validate(data)

    async def vendor_history(self, name: str) -> VendorHistory:
        """Get the SCD2 history for a vendor (GET /vendors/{name}/history)."""
        data = await self._request_json("GET", f"/vendors/{quote(name, safe='/')}/history")
        return VendorHistory.model_validate(data)

    async def vendor_at(self, name: str, *, as_of: datetime | str) -> VendorVersionItem:
        """Get the vendor version current at a point in time (GET /vendors/{name}/at)."""
        data = await self._request_json(
            "GET",
            f"/vendors/{quote(name, safe='/')}/at",
            params={"as_of": _to_iso(as_of)},
        )
        return VendorVersionItem.model_validate(data)

    async def countries(self) -> list[CountryItem]:
        """List ISO 3166-1 countries (GET /countries)."""
        data = await self._request_json("GET", "/countries")
        return [CountryItem.model_validate(item) for item in data]

    async def database_stats(self) -> DatabaseStatsResponse:
        """Get database statistics (GET /database/stats)."""
        data = await self._request_json("GET", "/database/stats")
        return DatabaseStatsResponse.model_validate(data)

    # --- export endpoints ------------------------------------------------

    async def list_exports(self) -> ExportListResponse:
        """List available pre-generated exports (GET /export)."""
        data = await self._request_json("GET", "/export")
        return ExportListResponse.model_validate(data)

    async def download_export(self, format: str, dest: str | Path) -> Path:
        """Download a pre-generated export to ``dest`` atomically.

        Streams the binary response (GET /export/{format}/download) to a
        temporary file in the destination directory and renames it into place
        only on full success, so an interrupted download never leaves a partial
        file at ``dest`` nor destroys an existing file there. Raises a typed
        error on a non-2xx response.
        """
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=dest_path.parent, prefix=f".{dest_path.name}.", suffix=".part"
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        # Large exports may stream slowly; don't let the default read timeout
        # abort a legitimately long download.
        timeout = httpx.Timeout(self._timeout, read=None)
        try:
            async with self._client.stream(
                "GET",
                f"/export/{quote(format, safe='')}/download",
                follow_redirects=True,
                timeout=timeout,
            ) as response:
                if not response.is_success:
                    await response.aread()
                    self._raise_for_status(response)
                with tmp_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)
            os.replace(tmp_path, dest_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return dest_path
