"""Tests for tealtiger client."""

import pytest

from tealtiger import TealTiger


def test_client_initialization():
    """Test client initialization."""
    guard = TealTiger(
        api_key="test-key",
        ssa_url="http://localhost:3000"
    )

    assert guard.api_key == "test-key"
    assert guard.ssa_url == "http://localhost:3000"
    assert guard.timeout == 5.0


def test_client_with_custom_config():
    """Test client with custom configuration."""
    guard = TealTiger(
        api_key="test-key",
        ssa_url="http://localhost:3000",
        timeout=10.0,
        max_retries=5
    )

    assert guard.timeout == 10.0
    assert guard.max_retries == 5


@pytest.mark.asyncio
async def test_async_context_manager():
    """Test async context manager."""
    async with TealTiger(
        api_key="test-key",
        ssa_url="http://localhost:3000"
    ) as guard:
        assert guard is not None


def test_sync_context_manager():
    """Test sync context manager."""
    with TealTiger(
        api_key="test-key",
        ssa_url="http://localhost:3000"
    ) as guard:
        assert guard is not None

