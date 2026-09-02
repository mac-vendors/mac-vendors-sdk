"""Tests for MacVendorsAPI against a mocked HTTP backend (no live network)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from mac_vendors_sdk import (
    EXPORT_FORMATS,
    AuthError,
    BatchLookupResponse,
    CountryItem,
    DatabaseInfoResponse,
    DatabaseStatsResponse,
    ExportListResponse,
    HealthResponse,
    MacHistory,
    MacVendorsAPI,
    MacVendorsApiError,
    NotFoundError,
    RateLimitError,
    TopVendorItem,
    VendorAssignmentsResponse,
    VendorHistory,
    VendorItem,
    VendorListResponse,
    VendorResponse,
    VendorVersionItem,
)

from .conftest import API_KEY, BASE_URL

API = f"{BASE_URL}/api/v1"


def _last(httpx_mock: HTTPXMock) -> httpx.Request:
    requests = httpx_mock.get_requests()
    assert requests, "expected at least one request"
    return requests[-1]


# --- auth header ---------------------------------------------------------


async def test_api_key_header_sent(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(json={"mac": "005056AABBCC", "found": False})
    await api.lookup("00:50:56:AA:BB:CC")
    req = _last(httpx_mock)
    assert req.headers["X-API-Key"] == API_KEY
    assert "Authorization" not in req.headers


async def test_bearer_token_header_sent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "005056AABBCC", "found": False})
    async with MacVendorsAPI(token="jwt-abc") as api:
        await api.lookup("005056AABBCC")
    req = _last(httpx_mock)
    assert req.headers["Authorization"] == "Bearer jwt-abc"
    assert "X-API-Key" not in req.headers


async def test_both_credentials_sent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    async with MacVendorsAPI(api_key="k", token="t") as api:
        await api.lookup("X")
    req = _last(httpx_mock)
    assert req.headers["X-API-Key"] == "k"
    assert req.headers["Authorization"] == "Bearer t"


# --- lookup endpoints ----------------------------------------------------


async def test_lookup(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "mac": "005056AABBCC",
        "vendor": "VMware, Inc.",
        "address": "3401 Hillview Ave. Palo Alto CA 94304 US",
        "registry": "MA-L",
        "assignment": "005056",
        "found": True,
        "valid_from": "2024-01-01T00:00:00",
    }
    httpx_mock.add_response(json=payload)
    result = await api.lookup("00:50:56:AA:BB:CC")
    req = _last(httpx_mock)
    assert req.method == "GET"
    assert str(req.url) == f"{API}/lookup/00%3A50%3A56%3AAA%3ABB%3ACC"
    assert isinstance(result, VendorResponse)
    assert result.vendor == "VMware, Inc."
    assert result.found is True
    assert result.valid_from is not None and result.valid_from.year == 2024


async def test_lookup_as_of(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(json={"mac": "005056AABBCC", "found": False})
    await api.lookup("005056AABBCC", as_of="2020-01-01T00:00:00Z")
    req = _last(httpx_mock)
    assert req.url.params["as_of"] == "2020-01-01T00:00:00Z"


async def test_lookup_as_of_datetime(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    from datetime import datetime

    httpx_mock.add_response(json={"mac": "005056AABBCC", "found": False})
    # A naive datetime is assumed to be UTC and rendered with an explicit offset.
    await api.lookup("005056AABBCC", as_of=datetime(2020, 1, 1, 0, 0, 0))
    req = _last(httpx_mock)
    assert req.url.params["as_of"] == "2020-01-01T00:00:00+00:00"


async def test_lookup_as_of_aware_datetime_converts_to_utc(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    from datetime import datetime, timedelta, timezone

    httpx_mock.add_response(json={"mac": "005056AABBCC", "found": False})
    # 02:00 at +02:00 == 00:00 UTC.
    aware = datetime(2020, 1, 1, 2, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    await api.lookup("005056AABBCC", as_of=aware)
    req = _last(httpx_mock)
    assert req.url.params["as_of"] == "2020-01-01T00:00:00+00:00"


async def test_lookup_history(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "mac": "005056AABBCC",
        "assignment": "005056",
        "registry": "MA-L",
        "history": [
            {
                "organization_name": "VMware, Inc.",
                "organization_address": "Palo Alto CA US",
                "valid_from": "2020-01-01T00:00:00",
                "valid_to": None,
                "is_current": True,
            }
        ],
    }
    httpx_mock.add_response(json=payload)
    result = await api.lookup_history("00:50:56:AA:BB:CC")
    req = _last(httpx_mock)
    assert str(req.url) == f"{API}/lookup/00%3A50%3A56%3AAA%3ABB%3ACC/history"
    assert isinstance(result, MacHistory)
    assert len(result.history) == 1
    assert result.history[0].is_current is True


async def test_batch_lookup(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "results": [
            {"mac": "005056AABBCC", "vendor": "VMware, Inc.", "found": True},
            {"mac": "001122334455", "vendor": None, "found": False},
        ],
        "total": 2,
        "found": 1,
        "not_found": 1,
    }
    httpx_mock.add_response(json=payload)
    result = await api.batch_lookup(["005056AABBCC", "001122334455"])
    req = _last(httpx_mock)
    assert req.method == "POST"
    assert str(req.url) == f"{API}/lookup/batch"
    import json as _json

    assert _json.loads(req.content) == {"mac_addresses": ["005056AABBCC", "001122334455"]}
    assert isinstance(result, BatchLookupResponse)
    assert result.total == 2
    assert result.found == 1


# --- vendors endpoints ---------------------------------------------------


async def test_list_vendors(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "vendors": [
            {
                "assignment": "005056",
                "organization_name": "VMware, Inc.",
                "organization_address": "Palo Alto CA US",
                "registry": "MA-L",
                "valid_from": "2024-01-01T00:00:00",
            }
        ],
        "pagination": {
            "page": 2,
            "page_size": 10,
            "total_items": 100,
            "total_pages": 10,
            "has_next": True,
            "has_prev": True,
        },
    }
    httpx_mock.add_response(json=payload)
    result = await api.list_vendors(
        name="VMware", letter="V", registry="MA-L", page=2, page_size=10
    )
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/vendors"
    params = req.url.params
    assert params["name"] == "VMware"
    assert params["letter"] == "V"
    assert params["registry"] == "MA-L"
    assert params["page"] == "2"
    assert params["page_size"] == "10"
    assert params["sort_by"] == "organization_name"
    assert params["sort_order"] == "asc"
    assert isinstance(result, VendorListResponse)
    assert result.pagination.page == 2
    assert result.vendors[0].organization_name == "VMware, Inc."


async def test_list_vendors_defaults_no_optional_params(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    payload = {
        "vendors": [],
        "pagination": {
            "page": 1,
            "page_size": 50,
            "total_items": 0,
            "total_pages": 0,
            "has_next": False,
            "has_prev": False,
        },
    }
    httpx_mock.add_response(json=payload)
    await api.list_vendors()
    req = _last(httpx_mock)
    assert "name" not in req.url.params
    assert "letter" not in req.url.params
    assert "registry" not in req.url.params
    assert req.url.params["page"] == "1"


async def test_top_vendors(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = [
        {
            "organization_name": "Apple, Inc.",
            "organization_address": "Cupertino CA US",
            "country_code": "US",
            "assignment_count": 772,
            "registries": ["MA-L", "MA-M"],
        }
    ]
    httpx_mock.add_response(json=payload)
    result = await api.top_vendors(limit=5)
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/vendors/top"
    assert req.url.params["limit"] == "5"
    assert isinstance(result, list)
    assert isinstance(result[0], TopVendorItem)
    assert result[0].assignment_count == 772
    assert result[0].registries == ["MA-L", "MA-M"]


async def test_search_vendors(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = [
        {
            "assignment": "005056",
            "organization_name": "VMware, Inc.",
            "registry": "MA-L",
        }
    ]
    httpx_mock.add_response(json=payload)
    result = await api.search_vendors("vmware", limit=10)
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/vendors/search"
    assert req.url.params["q"] == "vmware"
    assert req.url.params["limit"] == "10"
    assert isinstance(result[0], VendorItem)
    assert result[0].assignment == "005056"


async def test_vendor_assignments(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "organization_name": "VMware, Inc.",
        "organization_address": "Palo Alto CA US",
        "country_code": "US",
        "total_assignments": 2,
        "registries": ["MA-L"],
        "assignments": [
            {"assignment": "005056", "registry": "MA-L", "valid_from": "2024-01-01T00:00:00"},
            {"assignment": "000C29", "registry": "MA-L", "valid_from": None},
        ],
    }
    httpx_mock.add_response(json=payload)
    result = await api.vendor_assignments("VMware, Inc.")
    req = _last(httpx_mock)
    assert str(req.url) == f"{API}/vendors/VMware%2C%20Inc./assignments?page=1"
    assert isinstance(result, VendorAssignmentsResponse)
    assert result.total_assignments == 2
    assert len(result.assignments) == 2


async def test_vendor_history(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "organization_name": "VMware, Inc.",
        "total_versions": 1,
        "versions": [
            {
                "organization_name": "VMware, Inc.",
                "organization_address": "Palo Alto CA US",
                "country_code": "US",
                "assignment_count": 5,
                "registries": ["MA-L"],
                "first_seen": "2010-01-01T00:00:00",
                "last_seen": "2024-01-01T00:00:00",
                "valid_from": "2010-01-01T00:00:00",
                "valid_to": None,
                "is_current": True,
            }
        ],
    }
    httpx_mock.add_response(json=payload)
    result = await api.vendor_history("VMware, Inc.")
    req = _last(httpx_mock)
    assert str(req.url) == f"{API}/vendors/VMware%2C%20Inc./history"
    assert isinstance(result, VendorHistory)
    assert result.total_versions == 1
    assert result.versions[0].is_current is True


async def test_vendor_at(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "organization_name": "VMware, Inc.",
        "organization_address": "Palo Alto CA US",
        "country_code": "US",
        "assignment_count": 3,
        "registries": ["MA-L"],
        "first_seen": "2010-01-01T00:00:00",
        "last_seen": "2018-01-01T00:00:00",
        "valid_from": "2010-01-01T00:00:00",
        "valid_to": "2019-01-01T00:00:00",
        "is_current": False,
    }
    httpx_mock.add_response(json=payload)
    result = await api.vendor_at("VMware, Inc.", as_of="2015-01-01T00:00:00Z")
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/vendors/VMware, Inc./at"
    assert req.url.params["as_of"] == "2015-01-01T00:00:00Z"
    assert isinstance(result, VendorVersionItem)
    assert result.is_current is False


async def test_vendor_name_with_slash(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(
        json={
            "organization_name": "A/B Corp",
            "total_assignments": 0,
            "registries": [],
            "assignments": [],
        }
    )
    await api.vendor_assignments("A/B Corp")
    req = _last(httpx_mock)
    # The server route is {name:path}: '/' stays a literal path separator (not
    # %2F, which proxies/ASGI servers often reject); other chars are encoded.
    assert req.url.path == "/api/v1/vendors/A/B Corp/assignments"
    assert "%2F" not in str(req.url)


async def test_countries(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = [
        {"code": "US", "code3": "USA", "numeric": "840", "name": "United States"},
        {"code": "ZZ", "code3": None, "numeric": None, "name": "Unknown"},
    ]
    httpx_mock.add_response(json=payload)
    result = await api.countries()
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/countries"
    assert isinstance(result[0], CountryItem)
    assert result[1].code == "ZZ"
    assert result[1].code3 is None


async def test_database_stats(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "total_vendors": 50000,
        "registry_counts": [
            {"registry": "MA-L", "count": 35000},
            {"registry": "MA-M", "count": 10000},
        ],
        "last_update": "2024-01-15T12:00:00",
    }
    httpx_mock.add_response(json=payload)
    result = await api.database_stats()
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/database/stats"
    assert isinstance(result, DatabaseStatsResponse)
    assert result.total_vendors == 50000
    assert result.registry_counts[0].registry == "MA-L"


# --- export endpoints ----------------------------------------------------


async def test_list_exports(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "items": [
            {
                "format": "sqlite",
                "label": "SQLite database",
                "file_size": 1024,
                "record_count": 50000,
                "generated_at": "2024-01-15T12:00:00",
                "download_url": "/api/v1/export/sqlite/download",
                "available": True,
                "allowed": True,
                "required_feature": "export_sqlite",
            }
        ]
    }
    httpx_mock.add_response(json=payload)
    result = await api.list_exports()
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/export"
    assert isinstance(result, ExportListResponse)
    assert result.items[0].format == "sqlite"
    assert result.items[0].file_size == 1024


async def test_download_export(httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path) -> None:
    blob = b"\x00\x01SQLite binary payload\xff"
    httpx_mock.add_response(content=blob, headers={"Content-Type": "application/vnd.sqlite3"})
    dest = tmp_path / "vendors.sqlite"
    returned = await api.download_export("sqlite", dest)
    req = _last(httpx_mock)
    assert req.method == "GET"
    assert req.url.path == "/api/v1/export/sqlite/download"
    assert req.headers["X-API-Key"] == API_KEY
    assert returned == dest
    assert dest.read_bytes() == blob


async def test_download_export_str_dest(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    blob = b"csv,data\n1,2\n"
    httpx_mock.add_response(content=blob)
    dest = str(tmp_path / "out.csv")
    returned = await api.download_export("csv", dest)
    assert str(returned) == dest
    assert returned.read_bytes() == blob


async def test_download_export_error(httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path) -> None:
    httpx_mock.add_response(status_code=404, json={"detail": "No export available"})
    with pytest.raises(NotFoundError) as exc_info:
        await api.download_export("sqlite", tmp_path / "x.sqlite")
    assert exc_info.value.detail == "No export available"


# --- error mapping -------------------------------------------------------


async def test_auth_error_401(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(status_code=401, json={"detail": "Invalid API key"})
    with pytest.raises(AuthError) as exc_info:
        await api.lookup("005056AABBCC")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"


async def test_auth_error_403(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(status_code=403, json={"detail": "Forbidden"})
    with pytest.raises(AuthError):
        await api.batch_lookup(["005056AABBCC"])


async def test_not_found_404(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(status_code=404, json={"detail": "Vendor not found"})
    with pytest.raises(NotFoundError) as exc_info:
        await api.vendor_assignments("Nope")
    assert exc_info.value.detail == "Vendor not found"


async def test_rate_limit_429_with_retry_after(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(
        status_code=429,
        json={"detail": "Rate limit reached"},
        headers={"Retry-After": "60"},
    )
    with pytest.raises(RateLimitError) as exc_info:
        await api.batch_lookup(["005056AABBCC"])
    assert exc_info.value.retry_after == 60
    assert exc_info.value.detail == "Rate limit reached"


async def test_rate_limit_429_without_retry_after(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(status_code=429, json={"detail": "slow down"})
    with pytest.raises(RateLimitError) as exc_info:
        await api.lookup("005056AABBCC")
    assert exc_info.value.retry_after is None


async def test_rate_limit_429_http_date_retry_after(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    # Retry-After as an HTTP-date (far future) is parsed into a positive seconds value.
    httpx_mock.add_response(
        status_code=429,
        json={"detail": "slow down"},
        headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"},
    )
    with pytest.raises(RateLimitError) as exc_info:
        await api.lookup("005056AABBCC")
    assert exc_info.value.retry_after is not None
    assert exc_info.value.retry_after > 0


async def test_rate_limit_429_unparseable_retry_after(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(
        status_code=429,
        json={"detail": "slow down"},
        headers={"Retry-After": "soon-ish"},
    )
    with pytest.raises(RateLimitError) as exc_info:
        await api.lookup("005056AABBCC")
    assert exc_info.value.retry_after is None


async def test_generic_error_500(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(status_code=500, json={"detail": "boom"})
    with pytest.raises(MacVendorsApiError) as exc_info:
        await api.database_stats()
    assert exc_info.value.status_code == 500
    # not one of the specialized subclasses
    assert type(exc_info.value) is MacVendorsApiError


async def test_error_non_json_body(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(status_code=500, content=b"Internal Server Error")
    with pytest.raises(MacVendorsApiError) as exc_info:
        await api.database_stats()
    assert exc_info.value.detail == "Internal Server Error"


async def test_error_json_list_body(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    # FastAPI 422 validation errors put a list under detail; a top-level list is
    # also handled gracefully.
    httpx_mock.add_response(status_code=400, json=["weird"])
    with pytest.raises(MacVendorsApiError) as exc_info:
        await api.database_stats()
    assert exc_info.value.detail == ["weird"]


# --- lifecycle / injected client -----------------------------------------


async def test_injected_client_not_closed(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    client = httpx.AsyncClient(base_url=f"{BASE_URL}/api/v1", headers={"X-API-Key": "k"})
    api = MacVendorsAPI(client=client)
    await api.lookup("X")
    await api.aclose()
    # injected client is left open for the caller to manage
    assert not client.is_closed
    await client.aclose()


async def test_owned_client_is_closed_on_exit(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    async with MacVendorsAPI(api_key="k") as api:
        await api.lookup("X")
        inner = api._client
    assert inner.is_closed  # an owned client is closed by __aexit__


async def test_injected_client_with_credentials_raises() -> None:
    client = httpx.AsyncClient(base_url=f"{BASE_URL}/api/v1")
    with pytest.raises(ValueError, match="not both"):
        MacVendorsAPI(api_key="k", client=client)
    await client.aclose()


async def test_download_error_preserves_existing_file(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path: Path
) -> None:
    dest = tmp_path / "vendors.sqlite"
    dest.write_bytes(b"OLD-GOOD-DATA")
    httpx_mock.add_response(status_code=404, json={"detail": "no such export"})
    with pytest.raises(MacVendorsApiError):
        await api.download_export("sqlite", dest)
    # The pre-existing file is untouched and no .part temp file is left behind.
    assert dest.read_bytes() == b"OLD-GOOD-DATA"
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.glob(".*")) == []


async def test_targets_pinned_host(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    await api.lookup("X")
    req = _last(httpx_mock)
    assert str(req.url) == "https://mac-vendors.lizardsystems.com/api/v1/lookup/X"


def test_base_url_is_not_configurable() -> None:
    # The base URL is pinned; a positional URL arg must be rejected.
    with pytest.raises(TypeError):
        MacVendorsAPI("https://evil.example.com", api_key="k")  # type: ignore[misc]


# --- 2.0 additions: search / assignment paging ----------------------------


async def test_search_vendors_prefixes(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = [
        {
            "assignment": "005056",
            "organization_name": "VMware, Inc.",
            "registry": "MA-L",
            "assignment_count": 4,
        }
    ]
    httpx_mock.add_response(json=payload)
    result = await api.search_vendors("vmware", limit=5, prefixes=2)
    req = _last(httpx_mock)
    assert req.url.params["prefixes"] == "2"
    # The sample is what came back; assignment_count is the vendor's true total.
    assert len(result) == 1
    assert result[0].assignment_count == 4


async def test_search_vendors_omits_prefixes_by_default(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(json=[])
    await api.search_vendors("vmware")
    req = _last(httpx_mock)
    # Left out entirely rather than guessed at, so the server's default applies.
    assert "prefixes" not in req.url.params
    assert req.url.params["limit"] == "20"


async def test_vendor_assignments_paging(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "organization_name": "Apple, Inc.",
        "total_assignments": 2500,
        "registries": ["MA-L"],
        "assignments": [
            {
                "assignment": "005056",
                "registry": "MA-L",
                "first_registered": "2010-05-04T00:00:00",
                "valid_from": "2024-01-01T00:00:00",
            }
        ],
        "truncated": True,
    }
    httpx_mock.add_response(json=payload)
    result = await api.vendor_assignments("Apple, Inc.", page=2, page_size=1000)
    req = _last(httpx_mock)
    assert req.url.params["page"] == "2"
    assert req.url.params["page_size"] == "1000"
    assert result.truncated is True
    assert result.total_assignments == 2500
    # first_registered is when the prefix entered the registry, which is not
    # valid_from - the start of the record's current version.
    assert result.assignments[0].first_registered == datetime(2010, 5, 4)
    assert result.assignments[0].valid_from == datetime(2024, 1, 1)


async def test_vendor_assignments_defaults_omit_page_size(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(
        json={
            "organization_name": "VMware, Inc.",
            "total_assignments": 1,
            "assignments": [{"assignment": "005056", "registry": "MA-L"}],
        }
    )
    result = await api.vendor_assignments("VMware, Inc.")
    req = _last(httpx_mock)
    assert req.url.params["page"] == "1"
    assert "page_size" not in req.url.params
    # Absent in the payload, and the API only sets it when a page is short.
    assert result.truncated is False


async def test_vendor_history_trimmed_without_history_feature(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    payload = {
        "organization_name": "VMware, Inc.",
        "first_seen": "1998-03-01T00:00:00",
        "last_seen": "2024-01-01T00:00:00",
        "total_versions": 4,
        "versions": [
            {
                "organization_name": "VMware, Inc.",
                "assignment_count": 12,
                "registries": ["MA-L"],
                "valid_from": "2024-01-01T00:00:00",
                "valid_to": None,
                "is_current": True,
            }
        ],
        "truncated": True,
    }
    httpx_mock.add_response(json=payload)
    result = await api.vendor_history("VMware, Inc.")
    assert isinstance(result, VendorHistory)
    # The true count survives the trim; only the list is shortened.
    assert result.total_versions == 4
    assert len(result.versions) == 1
    assert result.truncated is True
    # Vendor-level dates live on the response, not on a version.
    assert result.first_seen == datetime(1998, 3, 1)
    assert result.last_seen == datetime(2024, 1, 1)
    assert not hasattr(result.versions[0], "first_seen")


# --- 2.0 additions: database info and health ------------------------------


async def test_database_info(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    payload = {
        "total_blocks": 51234,
        "unique_vendors": 38210,
        "last_updated": "2026-07-20T17:21:56Z",
        "first_updated": "2021-03-01T00:00:00Z",
        "total_updates": 742,
        "database_version": "1.0.0",
        "records_by_registry": {"MA-L": 35000, "MA-M": 10000},
        "vendors_by_registry": {"MA-L": 30000, "MA-M": 6000},
        "recently_added": [
            {
                "assignment": "8C1F643A5",
                "organization_name": "Techmovers Systems India",
                "registry": "MA-S",
                "date": "2026-07-20T16:01:26Z",
            }
        ],
        "recently_changed": [],
        "recently_removed": [],
    }
    httpx_mock.add_response(json=payload)
    result = await api.database_info()
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/database/info"
    assert isinstance(result, DatabaseInfoResponse)
    assert result.total_blocks == 51234
    assert result.records_by_registry["MA-L"] == 35000
    assert result.recently_added[0].registry == "MA-S"
    assert result.recently_removed == []


async def test_health_is_outside_the_versioned_prefix(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(
        json={"status": "healthy", "version": "1.2.3", "environment": "production"}
    )
    result = await api.health()
    req = _last(httpx_mock)
    # The root of the pinned host, NOT /api/v1/health.
    assert str(req.url) == f"{BASE_URL}/health"
    assert isinstance(result, HealthResponse)
    assert result.status == "healthy"
    assert result.version == "1.2.3"


async def test_health_root_follows_an_injected_client(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"status": "healthy"})
    async with httpx.AsyncClient(base_url="https://staging.example.com/api/v1") as client:
        async with MacVendorsAPI(client=client) as api:
            result = await api.health()
    req = _last(httpx_mock)
    # Derived from the injected base URL, not from the pinned host.
    assert str(req.url) == "https://staging.example.com/health"
    assert result.status == "healthy"
    # The optional fields tolerate a minimal payload.
    assert result.version is None


# --- 2.0 additions: as-of export ------------------------------------------


async def test_list_exports_asof_allowed(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(json={"items": [], "asof_allowed": True})
    result = await api.list_exports()
    assert result.asof_allowed is True


async def test_list_exports_asof_allowed_defaults_false(
    httpx_mock: HTTPXMock, api: MacVendorsAPI
) -> None:
    httpx_mock.add_response(json={"items": []})
    result = await api.list_exports()
    assert result.asof_allowed is False


async def test_download_export_as_of(httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path) -> None:
    blob = b"assignment,organization_name\n005056,VMware\n"
    httpx_mock.add_response(content=blob)
    dest = tmp_path / "snapshot.csv"
    returned = await api.download_export_as_of(date(2025, 1, 1), dest)
    req = _last(httpx_mock)
    assert req.url.path == "/api/v1/export/as-of"
    assert req.url.params["date"] == "2025-01-01"
    assert req.url.params["format"] == "csv"
    assert req.headers["X-API-Key"] == API_KEY
    assert returned == dest
    assert dest.read_bytes() == blob


async def test_download_export_as_of_sqlite(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    httpx_mock.add_response(content=b"SQLite format 3\x00")
    await api.download_export_as_of("2025-06-30", tmp_path / "snap.sqlite", format="sqlite")
    req = _last(httpx_mock)
    # A string is passed through as given.
    assert req.url.params["date"] == "2025-06-30"
    assert req.url.params["format"] == "sqlite"


async def test_download_export_as_of_datetime_uses_the_utc_date(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    httpx_mock.add_response(content=b"x")
    # 01:00 on the 2nd at +05:00 is 20:00 on the 1st in UTC. The snapshot must
    # follow the same UTC rule as every other point-in-time parameter, or it
    # silently shifts by a day for callers east of Greenwich.
    aware = datetime(2025, 1, 2, 1, 0, tzinfo=timezone(timedelta(hours=5)))
    await api.download_export_as_of(aware, tmp_path / "snap.csv")
    req = _last(httpx_mock)
    assert req.url.params["date"] == "2025-01-01"


async def test_download_export_as_of_naive_datetime_is_utc(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    httpx_mock.add_response(content=b"x")
    await api.download_export_as_of(datetime(2025, 3, 9, 23, 59), tmp_path / "snap.csv")
    req = _last(httpx_mock)
    assert req.url.params["date"] == "2025-03-09"


async def test_download_export_as_of_utc_datetime(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    httpx_mock.add_response(content=b"x")
    await api.download_export_as_of(datetime(2025, 3, 9, 23, 59, tzinfo=UTC), tmp_path / "s.csv")
    req = _last(httpx_mock)
    assert req.url.params["date"] == "2025-03-09"


async def test_download_export_as_of_forbidden_without_feature(
    httpx_mock: HTTPXMock, api: MacVendorsAPI, tmp_path
) -> None:
    httpx_mock.add_response(
        status_code=403,
        json={"detail": "Your plan does not include this feature (export_asof)."},
    )
    dest = tmp_path / "snap.csv"
    with pytest.raises(AuthError) as exc_info:
        await api.download_export_as_of("2025-01-01", dest)
    assert "export_asof" in str(exc_info.value.detail)
    # A refused download leaves nothing behind.
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_export_formats_covers_the_documented_families() -> None:
    # A reference snapshot, so it is checked for shape rather than pinned
    # exactly: every base format, its zip twin, and the SCD-2 history dumps.
    assert "sqlite" in EXPORT_FORMATS
    assert "wireshark_legacy" in EXPORT_FORMATS
    assert "ieee_oui_txt" in EXPORT_FORMATS
    assert "csv_history" in EXPORT_FORMATS
    for base in ("sqlite", "csv", "json", "nmap", "csv_history"):
        assert f"{base}_zip" in EXPORT_FORMATS
    assert len(set(EXPORT_FORMATS)) == len(EXPORT_FORMATS)
