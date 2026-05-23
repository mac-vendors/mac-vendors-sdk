"""Tests for MacVendorsAPI against a mocked HTTP backend (no live network)."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from mac_vendors_sdk import (
    AuthError,
    BatchLookupResponse,
    CountryItem,
    DatabaseStatsResponse,
    ExportListResponse,
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
    async with MacVendorsAPI(BASE_URL, token="jwt-abc") as api:
        await api.lookup("005056AABBCC")
    req = _last(httpx_mock)
    assert req.headers["Authorization"] == "Bearer jwt-abc"
    assert "X-API-Key" not in req.headers


async def test_both_credentials_sent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    async with MacVendorsAPI(BASE_URL, api_key="k", token="t") as api:
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
    await api.lookup("005056AABBCC", as_of=datetime(2020, 1, 1, 0, 0, 0))
    req = _last(httpx_mock)
    assert req.url.params["as_of"] == "2020-01-01T00:00:00"


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
    assert str(req.url) == f"{API}/vendors/VMware%2C%20Inc./assignments"
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
    # slash must be percent-encoded so it does not alter the path
    assert "A%2FB%20Corp" in str(req.url)


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


async def test_rate_limit_429_bad_retry_after(httpx_mock: HTTPXMock, api: MacVendorsAPI) -> None:
    httpx_mock.add_response(
        status_code=429,
        json={"detail": "slow down"},
        headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
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
    api = MacVendorsAPI(BASE_URL, client=client)
    await api.lookup("X")
    await api.aclose()
    # injected client is left open for the caller to manage
    assert not client.is_closed
    await client.aclose()


async def test_base_url_trailing_slash_stripped(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"mac": "X", "found": False})
    async with MacVendorsAPI(f"{BASE_URL}/", api_key="k") as api:
        await api.lookup("X")
    req = _last(httpx_mock)
    assert str(req.url) == f"{API}/lookup/X"
