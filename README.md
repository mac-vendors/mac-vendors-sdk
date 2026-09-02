# mac-vendors-sdk

[![PyPI](https://img.shields.io/pypi/v/mac-vendors-sdk.svg)](https://pypi.org/project/mac-vendors-sdk/)
[![Python versions](https://img.shields.io/pypi/pyversions/mac-vendors-sdk.svg)](https://pypi.org/project/mac-vendors-sdk/)
[![CI](https://github.com/mac-vendors/mac-vendors-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/mac-vendors/mac-vendors-sdk/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Async HTTP client SDK for the [MAC Vendors](https://mac-vendors.lizardsystems.com) public REST API.

It is a thin, typed wrapper over the hosted service at
`https://mac-vendors.lizardsystems.com/api/v1`. The base URL is fixed (not
configurable). Every endpoint maps to one async method that returns a
Pydantic v2 model.

## Install

```bash
pip install mac-vendors-sdk
```

## Authentication

The API accepts either an API key (sent as the `X-API-Key` header) or a JWT
bearer token (sent as `Authorization: Bearer <token>`). Provide whichever you
have:

```python
from mac_vendors_sdk import MacVendorsAPI

api = MacVendorsAPI(api_key="your-api-key")
# or
api = MacVendorsAPI(token="your-jwt")
```

## Usage

```python
import asyncio
from mac_vendors_sdk import MacVendorsAPI


async def main() -> None:
    async with MacVendorsAPI(api_key="key") as api:
        # Single lookup
        result = await api.lookup("00:50:56:AA:BB:CC")
        print(result.vendor, result.found)

        # Historical lookup
        old = await api.lookup("005056AABBCC", as_of="2020-01-01T00:00:00Z")

        # MAC assignment history (requires a plan with the history feature)
        history = await api.lookup_history("00:50:56:AA:BB:CC")

        # Batch lookup (requires a plan with the batch_lookup feature)
        batch = await api.batch_lookup(["005056AABBCC", "001122334455"])

        # List / search vendors
        page = await api.list_vendors(name="VMware", page=1, page_size=50)
        matches = await api.search_vendors("apple", limit=10, prefixes=4)
        top = await api.top_vendors(limit=15)

        # Vendor detail / history / point-in-time
        assignments = await api.vendor_assignments("VMware, Inc.", page=1)
        if assignments.truncated:
            more = await api.vendor_assignments("VMware, Inc.", page=2)
        vhist = await api.vendor_history("VMware, Inc.")
        version = await api.vendor_at("VMware, Inc.", as_of="2022-06-01T00:00:00Z")

        # Reference data and stats
        countries = await api.countries()
        stats = await api.database_stats()
        info = await api.database_info()
        alive = await api.health()

        # Exports
        exports = await api.list_exports()
        await api.download_export("sqlite", "vendors.sqlite")

        # Point-in-time export (requires a plan with the export_asof feature)
        if exports.asof_allowed:
            await api.download_export_as_of("2025-01-01", "vendors-2025.csv")


asyncio.run(main())
```

### Plan-gated endpoints

Some calls need a subscription feature and raise `AuthError` (403) without it:
`lookup(as_of=...)`, `lookup_history`, `vendor_at` and the full
`vendor_history` timeline need `history`; `batch_lookup` needs `batch_lookup`;
each export format needs its own feature, and `download_export_as_of` needs
`export_asof`. `list_exports()` reports per-format `allowed` and `asof_allowed`
so you can check before calling.

`vendor_history` is trimmed rather than refused without `history`: it returns
only the current version, sets `truncated`, and still reports the true
`total_versions`.

### Export formats

`download_export` accepts any identifier in `EXPORT_FORMATS`: `sqlite`, `csv`,
`json`, `wireshark`, `wireshark_legacy`, `nmap`, `ieee_oui_txt`, the
`csv_history` / `sqlite_history` SCD-2 dumps, and a `_zip` variant of each.

## Errors

Non-2xx responses raise a typed exception (all subclasses of
`MacVendorsApiError`):

| Status | Exception |
| ------ | --------- |
| 401, 403 | `AuthError` |
| 404 | `NotFoundError` |
| 429 | `RateLimitError` (exposes `.retry_after` from the `Retry-After` header) |
| other | `MacVendorsApiError` |

Each carries `.status_code`, `.detail` (parsed from FastAPI's `{"detail": ...}`
body when present), and `.response`.

```python
from mac_vendors_sdk import MacVendorsAPI, NotFoundError, RateLimitError

async with MacVendorsAPI(api_key="key") as api:
    try:
        await api.lookup_history("00:00:00:00:00:00")
    except NotFoundError as exc:
        print("not found:", exc.detail)
    except RateLimitError as exc:
        print("retry after", exc.retry_after, "seconds")
```

## Custom HTTP client

You can inject your own `httpx.AsyncClient` (for custom transports, proxies, or
shared connection pools). When you do, you own its lifecycle and must set the
base URL (`https://mac-vendors.lizardsystems.com/api/v1`) and auth headers
yourself:

```python
import httpx
from mac_vendors_sdk import MacVendorsAPI

client = httpx.AsyncClient(
    base_url="https://mac-vendors.lizardsystems.com/api/v1",
    headers={"X-API-Key": "key"},
)
api = MacVendorsAPI(client=client)
# api.aclose() will NOT close an injected client.
```

## License

MIT
