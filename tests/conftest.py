"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from mac_vendors_sdk import MacVendorsAPI

# The SDK pins this host; tests assert against it (HTTP is mocked, no network).
BASE_URL = "https://mac-vendors.lizardsystems.com"
API_KEY = "test-key-123"


@pytest.fixture
async def api() -> AsyncIterator[MacVendorsAPI]:
    """A client configured with an API key (targets the pinned host)."""
    async with MacVendorsAPI(api_key=API_KEY) as client:
        yield client
