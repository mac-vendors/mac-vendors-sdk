"""Async HTTP client for the mac-vendors public REST API."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, date, datetime
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
    DatabaseInfoResponse,
    DatabaseStatsResponse,
    ExportListResponse,
    HealthResponse,
    MacHistory,
    TopVendorItem,
    VendorAssignmentsResponse,
    VendorHistory,
    VendorItem,
    VendorListResponse,
    VendorResponse,
    VendorVersionItem,
)

__all__ = ["DEFAULT_BASE_URL", "EXPORT_FORMATS", "MacVendorsAPI"]

#: The official hosted API. The SDK targets this host; it is not configurable.
DEFAULT_BASE_URL = "https://mac-vendors.lizardsystems.com"

#: Where the versioned API lives under the host. ``/health`` sits outside it.
_API_PREFIX = "/api/v1"

#: The export formats this release knows about, for building a picker or
#: validating input offline. A reference snapshot, not a gate: the SDK does not
#: check against it, so a format added server-side works before this list
#: catches up. :meth:`MacVendorsAPI.list_exports` is the authoritative,
#: per-plan answer.
EXPORT_FORMATS: tuple[str, ...] = (
    "sqlite",
    "csv",
    "json",
    "wireshark",
    "wireshark_legacy",
    "nmap",
    "ieee_oui_txt",
    "sqlite_zip",
    "csv_zip",
    "json_zip",
    "wireshark_zip",
    "wireshark_legacy_zip",
    "nmap_zip",
    "ieee_oui_txt_zip",
    "csv_history",
    "sqlite_history",
    "csv_history_zip",
    "sqlite_history_zip",
)

#: Read and written a megabyte at a time. Exports run to gigabytes, and the
#: default buffer would turn one into six figures' worth of blocking writes on
#: the caller's event loop.
_DOWNLOAD_CHUNK_SIZE = 1 << 20


def _to_iso(value: datetime | str) -> str:
    """Render an ``as_of`` parameter as a UTC ISO 8601 string.

    A naive datetime is assumed to be UTC; an aware datetime is converted to
    UTC, so point-in-time queries are never silently shifted by the caller's
    local offset. A string is passed through unchanged.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


def _to_date(value: date | datetime | str) -> str:
    """Render a calendar-date parameter as ``YYYY-MM-DD``.

    A datetime goes through :func:`_to_iso` first, so the date taken is the UTC
    one: an aware datetime near midnight otherwise contributes its *local*
    calendar date and the snapshot silently shifts by a day. A plain date has no
    offset to reconcile, and a string is passed through unchanged.
    """
    if isinstance(value, datetime):
        return _to_iso(value)[:10]
    if isinstance(value, date):
        return value.isoformat()
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
        when = when.replace(tzinfo=UTC)
    return max(0, int((when - datetime.now(UTC)).total_seconds()))


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
                base_url=f"{DEFAULT_BASE_URL}{_API_PREFIX}",
                headers=headers,
                timeout=timeout,
            )
        # `/health` sits outside the versioned prefix. Derived once, from
        # whatever base URL the client ended up with, so the layout is composed
        # in one place rather than composed here and picked apart per call.
        self._root_url = self._client.base_url.join("/")

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

    async def _download(
        self,
        url: str,
        dest: str | Path,
        *,
        params: dict[str, Any] | None = None,
    ) -> Path:
        """Stream a binary response to ``dest``, replacing it only on success.

        The binary counterpart to :meth:`_request_json`: same client, same error
        mapping, but the body goes to a file instead of being parsed. Written to
        a temporary file in the destination directory and renamed into place
        only once the whole body has arrived, so an interrupted download leaves
        neither a partial file at ``dest`` nor a damaged existing one.
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
                url,
                params=params,
                follow_redirects=True,
                timeout=timeout,
            ) as response:
                if not response.is_success:
                    await response.aread()
                    self._raise_for_status(response)
                # A full export runs to gigabytes, and every `write` blocks the
                # caller's event loop. Megabyte chunks and a matching buffer keep
                # that to a few hundred syscalls per gigabyte rather than a few
                # hundred thousand.
                with tmp_path.open("wb", buffering=_DOWNLOAD_CHUNK_SIZE) as fh:
                    async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_SIZE):
                        fh.write(chunk)
            os.replace(tmp_path, dest_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return dest_path

    # --- lookup endpoints ------------------------------------------------

    async def lookup(
        self,
        mac: str,
        *,
        as_of: datetime | str | None = None,
    ) -> VendorResponse:
        """Look up the vendor for a single MAC address (GET /lookup/{mac}).

        The plain current lookup is public. Passing ``as_of`` for a
        point-in-time answer requires a plan that includes the ``history``
        feature (Pro or Enterprise).
        """
        params: dict[str, Any] = {}
        if as_of is not None:
            params["as_of"] = _to_iso(as_of)
        data = await self._request_json(
            "GET", f"/lookup/{quote(mac, safe='')}", params=params or None
        )
        return VendorResponse.model_validate(data)

    async def lookup_history(self, mac: str) -> MacHistory:
        """Get the SCD2 history for a MAC assignment (GET /lookup/{mac}/history).

        Requires a plan that includes the ``history`` feature (Pro or
        Enterprise) and costs one request from that plan's quota.
        """
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

    async def search_vendors(
        self,
        q: str,
        *,
        limit: int = 20,
        prefixes: int | None = None,
    ) -> list[VendorItem]:
        """Search vendors by name (GET /vendors/search).

        Results are ranked best match first and each carries a *sample* of the
        vendor's prefixes plus ``assignment_count``, the true total. ``prefixes``
        sets how many to sample per vendor (server default 4, max 20); rows count
        against the daily directory budget, so raising it multiplies the cost of
        the call. Left unset, the server's default applies.
        """
        params: dict[str, Any] = {"q": q, "limit": limit}
        if prefixes is not None:
            params["prefixes"] = prefixes
        data = await self._request_json("GET", "/vendors/search", params=params)
        return [VendorItem.model_validate(item) for item in data]

    async def vendor_assignments(
        self,
        name: str,
        *,
        page: int = 1,
        page_size: int | None = None,
    ) -> VendorAssignmentsResponse:
        """Get a page of a vendor's assignments (GET /vendors/{name}/assignments).

        ``total_assignments`` is the vendor's whole holding and ``truncated``
        says whether this page is all of it; the rest is reachable with ``page``.
        ``page_size`` defaults server-side to the 2000 maximum.
        """
        params: dict[str, Any] = {"page": page}
        if page_size is not None:
            params["page_size"] = page_size
        data = await self._request_json(
            "GET", f"/vendors/{quote(name, safe='/')}/assignments", params=params
        )
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
        """Get database statistics (GET /database/stats).

        A strict subset of :meth:`database_info`, kept for callers that only
        need the per-registry vendor counts.
        """
        data = await self._request_json("GET", "/database/stats")
        return DatabaseStatsResponse.model_validate(data)

    async def database_info(self) -> DatabaseInfoResponse:
        """Get extended database information (GET /database/info).

        Totals, per-registry breakdowns of both assignment blocks and unique
        organizations, and the ten most recent additions, changes and removals.
        The server caches this for an hour.
        """
        data = await self._request_json("GET", "/database/info")
        return DatabaseInfoResponse.model_validate(data)

    # --- service ---------------------------------------------------------

    async def health(self) -> HealthResponse:
        """Check service health (GET /health).

        The only endpoint outside the versioned prefix, so it is addressed
        against :attr:`_root_url` rather than relative to the client's base URL.
        Unauthenticated: it answers without an API key.
        """
        data = await self._request_json("GET", str(self._root_url.join("health")))
        return HealthResponse.model_validate(data)

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

        ``format`` is one of :data:`EXPORT_FORMATS`; an unknown one is a 404.
        Each format is gated by a plan feature - :meth:`list_exports` reports
        which ones the current credentials may download.
        """
        return await self._download(f"/export/{quote(format, safe='')}/download", dest)

    async def download_export_as_of(
        self,
        as_of: date | datetime | str,
        dest: str | Path,
        *,
        format: str = "csv",
    ) -> Path:
        """Download a point-in-time export to ``dest`` (GET /export/as-of).

        The database as it looked on a past date, generated on demand. Requires
        a plan with the ``export_asof`` feature (Enterprise); the date must be
        in the past, and ``format`` is ``"csv"`` or ``"sqlite"``. Snapshots are
        immutable, so the server caches them and a cache hit does not count
        against the daily cap.

        ``as_of`` is a calendar date: a ``datetime`` contributes its UTC date,
        like every other point-in-time parameter here, and a string is passed
        through as given.
        """
        return await self._download(
            "/export/as-of", dest, params={"date": _to_date(as_of), "format": format}
        )
