# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-09-02

Catches the SDK up with the hosted API. Everything here is additive except the
one removal below, which is why this is a major.

### Added
- `health()` - `GET /health`, the service health check. The one endpoint outside
  `/api/v1`, and the one that answers without credentials.
- `database_info()` - `GET /api/v1/database/info`. Totals, per-registry counts of
  both assignment blocks and unique organizations, and the ten most recent
  additions, changes and removals. `database_stats()` is a strict subset of it
  and stays for callers that only want the registry counts.
- `download_export_as_of(as_of, dest, format="csv")` - `GET /api/v1/export/as-of`,
  the point-in-time export generated on demand. Requires the `export_asof`
  feature; streams to `dest` atomically like `download_export`. Accepts a
  `date`, a `datetime` or a string, and a datetime contributes its **UTC**
  calendar date, following the same rule as every other point-in-time parameter
  - taking the local date would shift the snapshot by a day for callers east of
  Greenwich.
- `search_vendors(..., prefixes=)` - how many of each vendor's prefixes to
  sample. Rows count against the daily directory budget, so raising it
  multiplies the cost of the call.
- `vendor_assignments(..., page=, page_size=)` - the endpoint is paginated now.
  A vendor over the page cap was previously reachable only in part.
- `EXPORT_FORMATS`, listing every format identifier `download_export` accepts:
  the Wireshark (`wireshark`, `wireshark_legacy`), `nmap` and `ieee_oui_txt`
  text formats, the `csv_history` / `sqlite_history` SCD-2 dumps, and a `_zip`
  variant of each. A reference snapshot, not a gate - nothing validates against
  it, so a format added server-side works before the list catches up, and
  `list_exports()` stays the authoritative per-plan answer. `DEFAULT_BASE_URL`
  is now exported from the package root too.
- New response fields: `VendorItem.assignment_count`,
  `VendorAssignmentItem.first_registered`, `VendorAssignmentsResponse.truncated`,
  `VendorHistory.first_seen` / `.last_seen` / `.truncated`, and
  `ExportListResponse.asof_allowed`.
- New models: `DatabaseInfoResponse`, `DatabaseInfoRecord`, `HealthResponse`.

### Removed
- `VendorVersionItem.first_seen` and `.last_seen`. The API never populated them
  on a version - they describe the vendor, not one of its versions - so they
  read as `None` on every response. They now sit on `VendorHistory`, where the
  API does return them. `vendor_at()` returns a `VendorVersionItem`, so code
  reading those two attributes from it was reading nothing.

### Changed
- `lookup_history()` now requires a plan with the `history` feature. It was
  public; the full history with its dates is strictly more than the
  point-in-time answer `lookup(as_of=...)` sells, so anyone could derive the
  paid answer from a free call. Documented, not enforced client-side: the server
  answers 403.
- `vendor_history()` is trimmed rather than refused for callers without
  `history` - the current version only, with `truncated` set and the true
  `total_versions` still reported.
- `VendorAssignmentsResponse.truncated` and `VendorHistory.truncated` share a
  name but not a remedy: the first means another `page` holds the rest, the
  second means the plan withholds it and no page number will reach it.
- Downloads read and write a megabyte at a time instead of using the default
  buffer, which on a multi-gigabyte export was six figures' worth of blocking
  writes on the caller's event loop.
- `vendor_assignments()` sends `page` on every call, as `list_vendors()` already
  did, so the request says which page it wants rather than relying on a
  server-side default.

## [1.0.0] - 2026-07-23

### Added
- Initial public release: async, typed client for the MAC Vendors REST API,
  covering lookup, historical lookup, MAC/vendor history, batch lookup, vendor
  search and listings, reference data, database stats, exports, and typed errors.

[2.0.0]: https://github.com/mac-vendors/mac-vendors-sdk/releases/tag/v2.0.0
[1.0.0]: https://github.com/mac-vendors/mac-vendors-sdk/releases/tag/v1.0.0
