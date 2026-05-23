# mac-vendors-sdk

Async HTTP client SDK for the [mac-vendors](https://github.com/lizardsystems) public REST API.

It is a thin, typed wrapper over the FastAPI backend at `{base_url}/api/v1`. Every
endpoint maps to one async method that returns a Pydantic v2 model.

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

api = MacVendorsAPI("https://mac-vendors.example.com", api_key="your-api-key")
# or
api = MacVendorsAPI("https://mac-vendors.example.com", token="your-jwt")
```

## Usage

```python
import asyncio
from mac_vendors_sdk import MacVendorsAPI

async def main() -> None:
    async with MacVendorsAPI("https://mac-vendors.example.com", api_key="key") as api:
        # Single lookup
        result = await api.lookup("00:50:56:AA:BB:CC")
        print(result.vendor, result.found)

        # Historical lookup
        old = await api.lookup("005056AABBCC", as_of="2020-01-01T00:00:00Z")

        # MAC assignment history
        history = await api.lookup_history("00:50:56:AA:BB:CC")

        # Batch lookup (requires a plan with the batch_lookup feature)
        batch = await api.batch_lookup(["005056AABBCC", "001122334455"])

        # List / search vendors
        page = await api.list_vendors(name="VMware", page=1, page_size=50)
        matches = await api.search_vendors("apple", limit=10)
        top = await api.top_vendors(limit=15)

        # Vendor detail / history / point-in-time
        assignments = await api.vendor_assignments("VMware, Inc.")
        vhist = await api.vendor_history("VMware, Inc.")
        version = await api.vendor_at("VMware, Inc.", as_of="2022-06-01T00:00:00Z")

        # Reference data and stats
        countries = await api.countries()
        stats = await api.database_stats()

        # Exports
        exports = await api.list_exports()
        await api.download_export("sqlite", "vendors.sqlite")

asyncio.run(main())
```

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

async with MacVendorsAPI("https://mac-vendors.example.com", api_key="key") as api:
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
base URL and auth headers yourself:

```python
import httpx
from mac_vendors_sdk import MacVendorsAPI

client = httpx.AsyncClient(
    base_url="https://mac-vendors.example.com/api/v1",
    headers={"X-API-Key": "key"},
)
api = MacVendorsAPI("https://mac-vendors.example.com", client=client)
# api.aclose() will NOT close an injected client.
```

## License

MIT
