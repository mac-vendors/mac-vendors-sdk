"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from mac_vendors_sdk import MacVendorsAPI

BASE_URL = "https://api.example.com"
API_KEY = "test-key-123"


@pytest.fixture
async def api() -> AsyncIterator[MacVendorsAPI]:
    """A client configured with an API key against a fake base URL."""
    async with MacVendorsAPI(BASE_URL, api_key=API_KEY) as client:
        yield client
