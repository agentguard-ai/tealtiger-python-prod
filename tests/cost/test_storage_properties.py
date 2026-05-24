"""Property-based tests for cost storage."""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime, timedelta, timezone
from tealtiger.cost.storage import InMemoryCostStorage
from tealtiger.cost.types import CostRecord, TokenUsage, CostBreakdown


# Strategy for generating valid cost records
@st.composite
def cost_record_strategy(draw, request_id=None, agent_id=None, timestamp=None):
    """Generate a valid CostRecord with unique ID."""
    import uuid
    return CostRecord(
        id=str(uuid.uuid4())[:8],  # Generate unique ID
        request_id=request_id or draw(st.text(min_size=8, max_size=8, alphabet='0123456789abcdef')),
        agent_id=agent_id or draw(st.text(min_size=5, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz-')),
        model=draw(st.sampled_from(['gpt-4', 'gpt-3.5-turbo', 'claude-3-opus-20240229', 'claude-3-sonnet-20240229'])),
        provider=draw(st.sampled_from(['openai', 'anthropic', 'google', 'cohere'])),
        actual_tokens=TokenUsage(
            input_tokens=draw(st.integers(min_value=1, max_value=10000)),
            output_tokens=draw(st.integers(min_value=1, max_value=10000)),
            total_tokens=draw(st.integers(min_value=2, max_value=20000))
        ),
        actual_cost=draw(st.floats(min_value=0.0001, max_value=10.0)),
        breakdown=CostBreakdown(
            input_cost=draw(st.floats(min_value=0.0001, max_value=5.0)),
            output_cost=draw(st.floats(min_value=0.0001, max_value=5.0))
        ),
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        metadata=None
    )


@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(records=st.lists(cost_record_strategy(), min_size=1, max_size=20))
async def test_unique_id_assignment(records):
    """
    Feature: python-sdk-feature-parity, Property 5: Unique ID assignment
    For any cost record stored, retrieving it by ID should return a record 
    with a unique ID that matches the stored record.
    **Validates: Requirements 2.3**
    """
    storage = InMemoryCostStorage()
    
    # Store all records
    for record in records:
        await storage.store(record)
    
    # Verify each record can be retrieved by its unique ID
    for record in records:
        retrieved = await storage.get(record.id)
        assert retrieved is not None, f"Record with ID {record.id} should be retrievable"
        assert retrieved.id == record.id, "Retrieved record should have the same ID"
        assert retrieved.request_id == record.request_id
        assert retrieved.agent_id == record.agent_id
        assert retrieved.model == record.model


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    data=st.data(),
    num_records=st.integers(min_value=5, max_value=20),
    target_request_id=st.text(min_size=8, max_size=8, alphabet='0123456789abcdef')
)
async def test_request_id_query_correctness(data, num_records, target_request_id):
    """
    Feature: python-sdk-feature-parity, Property 6: Request ID query correctness
    For any set of cost records with various request IDs, querying by a specific 
    request ID should return only records matching that request ID.
    **Validates: Requirements 2.4**
    """
    storage = InMemoryCostStorage()
    
    # Generate records with different request IDs
    records = []
    for i in range(num_records):
        # Some records have the target request ID, others don't
        request_id = target_request_id if i % 3 == 0 else f"other-{i:08x}"
        record = data.draw(cost_record_strategy(request_id=request_id))
        records.append(record)
        await storage.store(record)
    
    # Query by target request ID
    results = await storage.get_by_request_id(target_request_id)
    
    # Verify all results have the target request ID
    for result in results:
        assert result.request_id == target_request_id, "All results should have the target request ID"
    
    # Verify we got all records with the target request ID
    expected_count = sum(1 for r in records if r.request_id == target_request_id)
    assert len(results) == expected_count, f"Should return exactly {expected_count} records"


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    data=st.data(),
    num_records=st.integers(min_value=5, max_value=20),
    target_agent_id=st.text(min_size=5, max_size=20, alphabet='abcdefghijklmnopqrstuvwxyz-')
)
async def test_agent_id_query_correctness(data, num_records, target_agent_id):
    """
    Feature: python-sdk-feature-parity, Property 7: Agent ID query correctness
    For any set of cost records with various agent IDs, querying by a specific 
    agent ID should return only records matching that agent ID.
    **Validates: Requirements 2.5**
    """
    storage = InMemoryCostStorage()
    
    # Generate records with different agent IDs
    records = []
    for i in range(num_records):
        # Some records have the target agent ID, others don't
        agent_id = target_agent_id if i % 3 == 0 else f"agent-{i}"
        record = data.draw(cost_record_strategy(agent_id=agent_id))
        records.append(record)
        await storage.store(record)
    
    # Query by target agent ID
    results = await storage.get_by_agent_id(target_agent_id)
    
    # Verify all results have the target agent ID
    for result in results:
        assert result.agent_id == target_agent_id, "All results should have the target agent ID"
    
    # Verify we got all records with the target agent ID
    expected_count = sum(1 for r in records if r.agent_id == target_agent_id)
    assert len(results) == expected_count, f"Should return exactly {expected_count} records"


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    data=st.data(),
    num_records=st.integers(min_value=5, max_value=20),
    days_offset=st.integers(min_value=1, max_value=15)
)
async def test_date_range_query_correctness(data, num_records, days_offset):
    """
    Feature: python-sdk-feature-parity, Property 8: Date range query correctness
    For any set of cost records with various timestamps, querying by a date range 
    should return only records with timestamps within that range.
    **Validates: Requirements 2.6**
    """
    storage = InMemoryCostStorage()
    
    # Define a date range
    base_date = datetime(2024, 1, 15, 12, 0, 0)
    start_date = base_date
    end_date = base_date + timedelta(days=days_offset)
    
    # Generate records with timestamps inside and outside the range
    records = []
    for i in range(num_records):
        # Distribute records across different time periods
        if i % 3 == 0:
            # Inside range
            timestamp = (start_date + timedelta(days=i % max(1, days_offset), hours=i % 24)).isoformat()
        elif i % 3 == 1:
            # Before range
            timestamp = (start_date - timedelta(days=i + 1)).isoformat()
        else:
            # After range
            timestamp = (end_date + timedelta(days=i + 1)).isoformat()
        
        record = data.draw(cost_record_strategy(timestamp=timestamp))
        records.append(record)
        await storage.store(record)
    
    # Query by date range
    results = await storage.get_by_date_range(start_date, end_date)
    
    # Verify all results are within the date range
    for result in results:
        result_date = datetime.fromisoformat(result.timestamp)
        assert start_date <= result_date <= end_date, \
            f"Result timestamp {result.timestamp} should be within range [{start_date}, {end_date}]"
    
    # Verify we got all records within the range
    expected_count = sum(
        1 for r in records 
        if start_date <= datetime.fromisoformat(r.timestamp) <= end_date
    )
    assert len(results) == expected_count, f"Should return exactly {expected_count} records"


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    data=st.data(),
    num_records=st.integers(min_value=5, max_value=20),
    days_range=st.integers(min_value=1, max_value=10)
)
async def test_cost_summary_accuracy(data, num_records, days_range):
    """
    Feature: python-sdk-feature-parity, Property 9: Cost summary accuracy
    For any set of cost records, the summary total cost should equal the sum 
    of all individual record costs.
    **Validates: Requirements 2.7**
    """
    storage = InMemoryCostStorage()
    
    # Define a date range
    start_date = datetime(2024, 1, 1, 0, 0, 0)
    end_date = start_date + timedelta(days=days_range)
    
    # Generate records within the date range
    records = []
    for i in range(num_records):
        timestamp = (start_date + timedelta(days=i % days_range, hours=i % 24)).isoformat()
        record = data.draw(cost_record_strategy(timestamp=timestamp))
        records.append(record)
        await storage.store(record)
    
    # Get summary
    summary = await storage.get_summary(start_date, end_date)
    
    # Verify total cost equals sum of individual costs
    expected_total = sum(r.actual_cost for r in records)
    assert abs(summary.total_cost - expected_total) < 0.0001, \
        f"Summary total cost {summary.total_cost} should equal sum of individual costs {expected_total}"
    
    # Verify total requests count
    assert summary.total_requests == len(records), \
        f"Summary should report {len(records)} total requests"
    
    # Verify average cost calculation
    expected_avg = expected_total / len(records) if len(records) > 0 else 0.0
    assert abs(summary.average_cost_per_request - expected_avg) < 0.0001, \
        f"Average cost should be {expected_avg}"
    
    # Verify by_model aggregation
    expected_by_model = {}
    for r in records:
        expected_by_model[r.model] = expected_by_model.get(r.model, 0.0) + r.actual_cost
    
    for model, cost in expected_by_model.items():
        assert abs(summary.by_model.get(model, 0.0) - cost) < 0.0001, \
            f"Model {model} cost should be {cost}"


@pytest.mark.asyncio
@settings(max_examples=100)
@given(
    data=st.data(),
    num_records=st.integers(min_value=5, max_value=20),
    cutoff_days=st.integers(min_value=1, max_value=15)
)
async def test_old_record_deletion(data, num_records, cutoff_days):
    """
    Feature: python-sdk-feature-parity, Property 10: Old record deletion
    For any set of cost records with various timestamps, deleting records older 
    than a date should remove only records with timestamps before that date.
    **Validates: Requirements 2.8**
    """
    storage = InMemoryCostStorage()
    
    # Define cutoff date
    base_date = datetime(2024, 1, 15, 12, 0, 0)
    cutoff_date = base_date
    
    # Generate records with timestamps before and after cutoff
    records = []
    for i in range(num_records):
        # Half before cutoff, half after
        if i % 2 == 0:
            timestamp = (cutoff_date - timedelta(days=i + 1)).isoformat()
        else:
            timestamp = (cutoff_date + timedelta(days=i + 1)).isoformat()
        
        record = data.draw(cost_record_strategy(timestamp=timestamp))
        records.append(record)
        await storage.store(record)
    
    # Count records before and after cutoff
    records_before_cutoff = [
        r for r in records 
        if datetime.fromisoformat(r.timestamp) < cutoff_date
    ]
    records_after_cutoff = [
        r for r in records 
        if datetime.fromisoformat(r.timestamp) >= cutoff_date
    ]
    
    # Delete old records
    deleted_count = await storage.delete_older_than(cutoff_date)
    
    # Verify correct number of records were deleted
    assert deleted_count == len(records_before_cutoff), \
        f"Should delete {len(records_before_cutoff)} records, deleted {deleted_count}"
    
    # Verify old records are gone
    for record in records_before_cutoff:
        retrieved = await storage.get(record.id)
        assert retrieved is None, f"Old record {record.id} should be deleted"
    
    # Verify recent records remain
    for record in records_after_cutoff:
        retrieved = await storage.get(record.id)
        assert retrieved is not None, f"Recent record {record.id} should remain"
    
    # Verify storage size
    assert storage.size() == len(records_after_cutoff), \
        f"Storage should contain {len(records_after_cutoff)} records"

