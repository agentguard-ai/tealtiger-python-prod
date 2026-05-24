"""Unit tests for cost storage."""

import pytest
from datetime import datetime, timedelta, timezone
from tealtiger.cost.storage import InMemoryCostStorage
from tealtiger.cost.types import CostRecord, TokenUsage, CostBreakdown


@pytest.mark.asyncio
async def test_clear_operation():
    """
    Test clearing all records from storage.
    **Validates: Requirements 2.9**
    """
    storage = InMemoryCostStorage()
    
    # Create and store multiple records
    records = []
    for i in range(10):
        record = CostRecord(
            id=f"record-{i:02d}",
            request_id=f"req-{i:02d}",
            agent_id=f"agent-{i % 3}",
            model="gpt-4",
            provider="openai",
            actual_tokens=TokenUsage(
                input_tokens=100 + i,
                output_tokens=50 + i,
                total_tokens=150 + i
            ),
            actual_cost=0.01 * (i + 1),
            breakdown=CostBreakdown(
                input_cost=0.006 * (i + 1),
                output_cost=0.004 * (i + 1)
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=None
        )
        records.append(record)
        await storage.store(record)
    
    # Verify records are stored
    assert storage.size() == 10, "Should have 10 records"
    
    # Clear all records
    await storage.clear()
    
    # Verify storage is empty
    assert storage.size() == 0, "Storage should be empty after clear"
    
    # Verify records cannot be retrieved
    for record in records:
        retrieved = await storage.get(record.id)
        assert retrieved is None, f"Record {record.id} should not be retrievable after clear"
    
    # Verify queries return empty results
    all_records = await storage.get_by_date_range(
        datetime(2020, 1, 1),
        datetime(2030, 1, 1)
    )
    assert len(all_records) == 0, "Date range query should return empty list"


@pytest.mark.asyncio
async def test_get_by_agent_id_with_date_filters():
    """Test agent ID query with optional date filters."""
    storage = InMemoryCostStorage()
    
    base_date = datetime(2024, 1, 15, 12, 0, 0)
    agent_id = "test-agent"
    
    # Create records for the agent across different dates
    for i in range(10):
        timestamp = (base_date + timedelta(days=i)).isoformat()
        record = CostRecord(
            id=f"record-{i:02d}",
            request_id=f"req-{i:02d}",
            agent_id=agent_id,
            model="gpt-4",
            provider="openai",
            actual_tokens=TokenUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150
            ),
            actual_cost=0.01,
            breakdown=CostBreakdown(
                input_cost=0.006,
                output_cost=0.004
            ),
            timestamp=timestamp,
            metadata=None
        )
        await storage.store(record)
    
    # Query without date filters
    all_records = await storage.get_by_agent_id(agent_id)
    assert len(all_records) == 10, "Should return all 10 records"
    
    # Query with start date filter
    start_date = base_date + timedelta(days=5)
    filtered_records = await storage.get_by_agent_id(agent_id, start_date=start_date)
    assert len(filtered_records) == 5, "Should return 5 records from day 5 onwards"
    
    # Query with end date filter
    end_date = base_date + timedelta(days=4)
    filtered_records = await storage.get_by_agent_id(agent_id, end_date=end_date)
    assert len(filtered_records) == 5, "Should return 5 records up to day 4"
    
    # Query with both filters
    start_date = base_date + timedelta(days=3)
    end_date = base_date + timedelta(days=6)
    filtered_records = await storage.get_by_agent_id(agent_id, start_date=start_date, end_date=end_date)
    assert len(filtered_records) == 4, "Should return 4 records between days 3-6"


@pytest.mark.asyncio
async def test_get_summary_with_agent_filter():
    """Test cost summary with optional agent filter."""
    storage = InMemoryCostStorage()
    
    start_date = datetime(2024, 1, 1, 0, 0, 0)
    end_date = datetime(2024, 1, 31, 23, 59, 59)
    
    # Create records for multiple agents
    for agent_num in range(3):
        agent_id = f"agent-{agent_num}"
        for i in range(5):
            record = CostRecord(
                id=f"record-{agent_num}-{i:02d}",
                request_id=f"req-{agent_num}-{i:02d}",
                agent_id=agent_id,
                model="gpt-4",
                provider="openai",
                actual_tokens=TokenUsage(
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150
                ),
                actual_cost=0.01 * (agent_num + 1),  # Different costs per agent
                breakdown=CostBreakdown(
                    input_cost=0.006 * (agent_num + 1),
                    output_cost=0.004 * (agent_num + 1)
                ),
                timestamp=(start_date + timedelta(days=i)).isoformat(),
                metadata=None
            )
            await storage.store(record)
    
    # Get summary for all agents
    summary_all = await storage.get_summary(start_date, end_date)
    assert summary_all.total_requests == 15, "Should have 15 total requests"
    expected_total = 0.01 * 5 + 0.02 * 5 + 0.03 * 5  # 0.30
    assert abs(summary_all.total_cost - expected_total) < 0.0001
    
    # Get summary for specific agent
    summary_agent1 = await storage.get_summary(start_date, end_date, agent_id="agent-1")
    assert summary_agent1.total_requests == 5, "Should have 5 requests for agent-1"
    assert abs(summary_agent1.total_cost - 0.10) < 0.0001, "Agent-1 should have cost 0.10"


@pytest.mark.asyncio
async def test_storage_with_empty_results():
    """Test storage operations with empty results."""
    storage = InMemoryCostStorage()
    
    # Query empty storage
    result = await storage.get("nonexistent-id")
    assert result is None, "Should return None for nonexistent ID"
    
    results = await storage.get_by_request_id("nonexistent-request")
    assert results == [], "Should return empty list for nonexistent request ID"
    
    results = await storage.get_by_agent_id("nonexistent-agent")
    assert results == [], "Should return empty list for nonexistent agent ID"
    
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 1, 31)
    results = await storage.get_by_date_range(start_date, end_date)
    assert results == [], "Should return empty list for date range with no records"
    
    summary = await storage.get_summary(start_date, end_date)
    assert summary.total_cost == 0.0, "Summary should have zero cost"
    assert summary.total_requests == 0, "Summary should have zero requests"
    assert summary.average_cost_per_request == 0.0, "Average should be zero"
    
    deleted = await storage.delete_older_than(datetime(2024, 1, 1))
    assert deleted == 0, "Should delete zero records from empty storage"

