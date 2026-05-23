"""mac-vendors-sdk - async HTTP client for the mac-vendors public REST API.

Example:
    import asyncio
    from mac_vendors_sdk import MacVendorsAPI

    async def main() -> None:
        async with MacVendorsAPI(api_key="your-key") as api:
            result = await api.lookup("00:50:56:AA:BB:CC")
            print(result.vendor)

    asyncio.run(main())
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .client import MacVendorsAPI
from .errors import (
    AuthError,
    MacVendorsApiError,
    NotFoundError,
    RateLimitError,
)
from .models import (
    BatchLookupResponse,
    CountryItem,
    DatabaseStatsResponse,
    ExportItem,
    ExportListResponse,
    MacHistory,
    MacHistoryItem,
    PaginationMeta,
    RegistryStats,
    TopVendorItem,
    VendorAssignmentItem,
    VendorAssignmentsResponse,
    VendorHistory,
    VendorItem,
    VendorListResponse,
    VendorResponse,
    VendorVersionItem,
)

try:
    __version__ = _version("mac-vendors-sdk")
except PackageNotFoundError:  # pragma: no cover - not installed (source tree)
    __version__ = "0.0.0"

__all__ = [
    "AuthError",
    "BatchLookupResponse",
    "CountryItem",
    "DatabaseStatsResponse",
    "ExportItem",
    "ExportListResponse",
    "MacHistory",
    "MacHistoryItem",
    "MacVendorsAPI",
    "MacVendorsApiError",
    "NotFoundError",
    "PaginationMeta",
    "RateLimitError",
    "RegistryStats",
    "TopVendorItem",
    "VendorAssignmentItem",
    "VendorAssignmentsResponse",
    "VendorHistory",
    "VendorItem",
    "VendorListResponse",
    "VendorResponse",
    "VendorVersionItem",
    "__version__",
]
