"""Pydantic models mirroring the mac-vendors public REST API responses.

All models use ``extra="ignore"`` so that additive, non-breaking API changes do
not break older clients.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BatchLookupResponse",
    "CountryItem",
    "DatabaseStatsResponse",
    "ExportItem",
    "ExportListResponse",
    "MacHistory",
    "MacHistoryItem",
    "PaginationMeta",
    "RegistryStats",
    "TopVendorItem",
    "VendorAssignmentItem",
    "VendorAssignmentsResponse",
    "VendorHistory",
    "VendorItem",
    "VendorListResponse",
    "VendorResponse",
    "VendorVersionItem",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- lookup module -------------------------------------------------------


class VendorResponse(_Base):
    """Result of a single MAC lookup (GET /lookup/{mac})."""

    mac: str
    vendor: str | None = None
    address: str | None = None
    registry: str | None = None
    assignment: str | None = None
    found: bool
    valid_from: datetime | None = None


class MacHistoryItem(_Base):
    """One SCD2 record in a MAC assignment's history."""

    organization_name: str
    organization_address: str | None = None
    valid_from: datetime
    valid_to: datetime | None = None
    is_current: bool


class MacHistory(_Base):
    """History for a MAC assignment (GET /lookup/{mac}/history)."""

    mac: str
    assignment: str
    registry: str
    history: list[MacHistoryItem]


class BatchLookupResponse(_Base):
    """Result of a batch MAC lookup (POST /lookup/batch)."""

    results: list[VendorResponse]
    total: int
    found: int
    not_found: int


# --- vendors module ------------------------------------------------------


class VendorItem(_Base):
    """A single vendor entry in a list / search result."""

    assignment: str
    organization_name: str
    organization_address: str | None = None
    registry: str
    valid_from: datetime | None = None


class PaginationMeta(_Base):
    """Pagination metadata for paginated list responses."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class VendorListResponse(_Base):
    """Paginated vendor list (GET /vendors)."""

    vendors: list[VendorItem]
    pagination: PaginationMeta


class TopVendorItem(_Base):
    """A vendor ranked by assignment count (GET /vendors/top)."""

    organization_name: str
    organization_address: str | None = None
    country_code: str | None = None
    assignment_count: int
    registries: list[str] = []


class VendorAssignmentItem(_Base):
    """A single MAC assignment within a vendor's portfolio."""

    assignment: str
    registry: str
    valid_from: datetime | None = None


class VendorAssignmentsResponse(_Base):
    """All assignments for a vendor (GET /vendors/{name}/assignments)."""

    organization_name: str
    organization_address: str | None = None
    country_code: str | None = None
    total_assignments: int
    registries: list[str] = []
    assignments: list[VendorAssignmentItem]


class VendorVersionItem(_Base):
    """A single SCD2 version of a vendor.

    Returned directly by GET /vendors/{name}/at and as elements of
    :class:`VendorHistory.versions`.
    """

    organization_name: str
    organization_address: str | None = None
    country_code: str | None = None
    assignment_count: int
    registries: list[str] = []
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    valid_from: datetime
    valid_to: datetime | None = None
    is_current: bool


class VendorHistory(_Base):
    """Full SCD2 history of a vendor (GET /vendors/{name}/history)."""

    organization_name: str
    total_versions: int
    versions: list[VendorVersionItem]


class CountryItem(_Base):
    """ISO 3166-1 country reference entry (GET /countries)."""

    code: str
    code3: str | None = None
    numeric: str | None = None
    name: str


class RegistryStats(_Base):
    """Vendor count for a single registry."""

    registry: str
    count: int


class DatabaseStatsResponse(_Base):
    """Database statistics (GET /database/stats)."""

    total_vendors: int
    registry_counts: list[RegistryStats]
    last_update: datetime | None = None


# --- export module -------------------------------------------------------


class ExportItem(_Base):
    """A single available export format (element of ExportListResponse)."""

    format: str
    label: str
    file_size: int | None = None
    record_count: int | None = None
    generated_at: datetime | None = None
    download_url: str
    available: bool
    allowed: bool
    required_feature: str


class ExportListResponse(_Base):
    """Available exports (GET /export)."""

    items: list[ExportItem]
