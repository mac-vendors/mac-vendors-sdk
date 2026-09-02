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
    "DatabaseInfoRecord",
    "DatabaseInfoResponse",
    "DatabaseStatsResponse",
    "ExportItem",
    "ExportListResponse",
    "HealthResponse",
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
    #: Total prefixes the organization holds. Present on
    #: :meth:`MacVendorsAPI.search_vendors` results, which carry only a sample
    #: of each vendor's prefixes; ``None`` elsewhere, where the rows are the
    #: whole set.
    assignment_count: int | None = None


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
    #: When this prefix first appeared in the registry, across every version of
    #: the record - unlike ``valid_from``, which is when the current version
    #: began.
    first_registered: datetime | None = None
    valid_from: datetime | None = None


class VendorAssignmentsResponse(_Base):
    """One page of a vendor's assignments (GET /vendors/{name}/assignments)."""

    organization_name: str
    organization_address: str | None = None
    country_code: str | None = None
    total_assignments: int
    registries: list[str] = []
    assignments: list[VendorAssignmentItem]
    #: True when this page does not carry every assignment the vendor holds;
    #: use ``page`` to reach the rest.
    truncated: bool = False


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
    valid_from: datetime
    valid_to: datetime | None = None
    is_current: bool


class VendorHistory(_Base):
    """SCD2 history of a vendor (GET /vendors/{name}/history).

    ``versions`` is ordered oldest first. Without a plan that includes the
    ``history`` feature the API returns only the current version, sets
    ``truncated``, and still reports the true ``total_versions``.
    """

    organization_name: str
    #: When the oldest prefix this vendor holds first appeared in the registry.
    #: A property of the vendor rather than of any one version, which is why it
    #: sits here and not on :class:`VendorVersionItem`.
    first_seen: datetime | None = None
    #: When the newest prefix this vendor holds first appeared in the registry.
    last_seen: datetime | None = None
    total_versions: int
    versions: list[VendorVersionItem]
    #: True when the caller's plan lacks the ``history`` feature and only the
    #: current version was returned. Unlike
    #: :attr:`VendorAssignmentsResponse.truncated`, which is about paging, no
    #: page number reaches the withheld versions - the API name is shared, the
    #: remedy is not.
    truncated: bool = False


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


class DatabaseInfoRecord(_Base):
    """An assignment block in one of the recent-activity feeds."""

    assignment: str
    organization_name: str | None = None
    registry: str
    #: ``valid_from`` for added and changed blocks, ``valid_to`` for removed ones.
    date: datetime | None = None


class DatabaseInfoResponse(_Base):
    """Extended database information (GET /database/info).

    Totals, per-registry breakdowns of both assignment blocks and unique
    organizations, and up to ten most recent additions, changes and removals.
    """

    total_blocks: int
    unique_vendors: int
    last_updated: datetime | None = None
    first_updated: datetime | None = None
    total_updates: int
    database_version: str
    records_by_registry: dict[str, int]
    vendors_by_registry: dict[str, int]
    recently_added: list[DatabaseInfoRecord] = []
    recently_changed: list[DatabaseInfoRecord] = []
    recently_removed: list[DatabaseInfoRecord] = []


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
    #: Whether the current plan may use point-in-time (as-of) exports.
    asof_allowed: bool = False


# --- service -------------------------------------------------------------


class HealthResponse(_Base):
    """Service health (GET /health)."""

    status: str
    version: str | None = None
    environment: str | None = None
