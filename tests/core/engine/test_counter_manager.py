"""Unit tests for TEEC v2.1 CounterManager.

Tests cover:
- Per-agent sequence counter behavior (Req 4.1, 4.3)
- Global running count behavior (Req 4.2, 4.4)
- Thread safety under concurrent access (Req 4.5, 4.6)
- Receipt ref tracking
- Reset functionality (Req 4.7)
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from tealtiger.core.engine.v2_1.counter_manager import CounterManager
from tealtiger.core.engine.v2_1.types import GENESIS_RECEIPT_REF


class TestNextSeq:
    """Tests for next_seq() — per-agent sequence counters."""

    def test_first_call_returns_1(self) -> None:
        cm = CounterManager()
        assert cm.next_seq("agent-a") == 1

    def test_subsequent_calls_increment_by_1(self) -> None:
        cm = CounterManager()
        assert cm.next_seq("agent-a") == 1
        assert cm.next_seq("agent-a") == 2
        assert cm.next_seq("agent-a") == 3

    def test_independent_per_agent(self) -> None:
        cm = CounterManager()
        assert cm.next_seq("agent-a") == 1
        assert cm.next_seq("agent-b") == 1
        assert cm.next_seq("agent-a") == 2
        assert cm.next_seq("agent-b") == 2

    def test_many_agents(self) -> None:
        cm = CounterManager()
        for i in range(10):
            agent_id = f"agent-{i}"
            assert cm.next_seq(agent_id) == 1
            assert cm.next_seq(agent_id) == 2


class TestNextRunningCount:
    """Tests for next_running_count() — global counter."""

    def test_first_call_returns_1(self) -> None:
        cm = CounterManager()
        assert cm.next_running_count() == 1

    def test_subsequent_calls_increment_by_1(self) -> None:
        cm = CounterManager()
        assert cm.next_running_count() == 1
        assert cm.next_running_count() == 2
        assert cm.next_running_count() == 3

    def test_shared_across_agents(self) -> None:
        cm = CounterManager()
        cm.next_seq("agent-a")  # seq doesn't affect running_count
        assert cm.next_running_count() == 1
        cm.next_seq("agent-b")
        assert cm.next_running_count() == 2


class TestCurrentSeq:
    """Tests for current_seq() — read-only accessor."""

    def test_returns_0_when_never_incremented(self) -> None:
        cm = CounterManager()
        assert cm.current_seq("agent-a") == 0

    def test_returns_current_value_after_increments(self) -> None:
        cm = CounterManager()
        cm.next_seq("agent-a")
        cm.next_seq("agent-a")
        assert cm.current_seq("agent-a") == 2

    def test_does_not_increment(self) -> None:
        cm = CounterManager()
        cm.next_seq("agent-a")
        cm.current_seq("agent-a")
        cm.current_seq("agent-a")
        assert cm.current_seq("agent-a") == 1


class TestCurrentRunningCount:
    """Tests for current_running_count() — read-only accessor."""

    def test_returns_0_when_never_incremented(self) -> None:
        cm = CounterManager()
        assert cm.current_running_count() == 0

    def test_returns_current_value_after_increments(self) -> None:
        cm = CounterManager()
        cm.next_running_count()
        cm.next_running_count()
        assert cm.current_running_count() == 2

    def test_does_not_increment(self) -> None:
        cm = CounterManager()
        cm.next_running_count()
        cm.current_running_count()
        cm.current_running_count()
        assert cm.current_running_count() == 1


class TestReceiptRef:
    """Tests for get_last_receipt_ref() and set_last_receipt_ref()."""

    def test_returns_genesis_when_no_receipt_stored(self) -> None:
        cm = CounterManager()
        assert cm.get_last_receipt_ref("agent-a") == GENESIS_RECEIPT_REF

    def test_returns_stored_receipt_ref(self) -> None:
        cm = CounterManager()
        cm.set_last_receipt_ref("agent-a", "abc123")
        assert cm.get_last_receipt_ref("agent-a") == "abc123"

    def test_independent_per_agent(self) -> None:
        cm = CounterManager()
        cm.set_last_receipt_ref("agent-a", "ref-a")
        cm.set_last_receipt_ref("agent-b", "ref-b")
        assert cm.get_last_receipt_ref("agent-a") == "ref-a"
        assert cm.get_last_receipt_ref("agent-b") == "ref-b"

    def test_overwrites_previous_value(self) -> None:
        cm = CounterManager()
        cm.set_last_receipt_ref("agent-a", "first")
        cm.set_last_receipt_ref("agent-a", "second")
        assert cm.get_last_receipt_ref("agent-a") == "second"


class TestReset:
    """Tests for reset() — clears all state."""

    def test_resets_seq_counters(self) -> None:
        cm = CounterManager()
        cm.next_seq("agent-a")
        cm.next_seq("agent-b")
        cm.reset()
        assert cm.current_seq("agent-a") == 0
        assert cm.current_seq("agent-b") == 0

    def test_resets_running_count(self) -> None:
        cm = CounterManager()
        cm.next_running_count()
        cm.next_running_count()
        cm.reset()
        assert cm.current_running_count() == 0

    def test_resets_receipt_refs(self) -> None:
        cm = CounterManager()
        cm.set_last_receipt_ref("agent-a", "some-ref")
        cm.reset()
        assert cm.get_last_receipt_ref("agent-a") == GENESIS_RECEIPT_REF

    def test_counters_restart_at_1_after_reset(self) -> None:
        cm = CounterManager()
        cm.next_seq("agent-a")
        cm.next_seq("agent-a")
        cm.next_running_count()
        cm.reset()
        assert cm.next_seq("agent-a") == 1
        assert cm.next_running_count() == 1


class TestThreadSafety:
    """Tests for thread safety under concurrent access."""

    def test_concurrent_next_seq_no_duplicates(self) -> None:
        """Req 4.5: concurrent requests for same agent produce unique seqs."""
        cm = CounterManager()
        num_threads = 50
        results: list[int] = []
        lock = threading.Lock()

        def increment() -> None:
            val = cm.next_seq("agent-a")
            with lock:
                results.append(val)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        assert sorted(results) == list(range(1, num_threads + 1))

    def test_concurrent_next_running_count_no_duplicates(self) -> None:
        """Req 4.6: concurrent running_count assignments are unique."""
        cm = CounterManager()
        num_threads = 50
        results: list[int] = []
        lock = threading.Lock()

        def increment() -> None:
            val = cm.next_running_count()
            with lock:
                results.append(val)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(num_threads)]
            for f in as_completed(futures):
                f.result()

        assert sorted(results) == list(range(1, num_threads + 1))
