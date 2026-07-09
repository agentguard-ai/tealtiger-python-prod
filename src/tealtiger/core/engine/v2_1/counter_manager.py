"""TEEC v2.1 Governance Contract — Counter Manager (Python SDK).

Provides thread-safe counter management for per-agent sequence numbers,
global running counts, and last receipt_ref tracking. Used internally
by the GovernanceEngine to maintain ordering invariants.

All methods are protected by a single threading.Lock to ensure
correct behavior under concurrent access.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7

Module: core/engine/v2_1/counter_manager
"""

from __future__ import annotations

import threading

from .types import GENESIS_RECEIPT_REF


class CounterManager:
    """Thread-safe counter manager for TEEC v2.1 governance decisions.

    Maintains:
    - Per-agent sequence counters (seq): independent monotonic counters
      starting at 1, scoped to each agent_id.
    - A single global running_count: shared across all agents within a
      GovernanceEngine instance, starting at 1.
    - Per-agent last receipt_ref: tracks the most recent receipt_ref
      for each agent, used for hash-chain linking.

    All public methods acquire a lock to guarantee thread safety under
    concurrent evaluation requests.
    """

    def __init__(self) -> None:
        """Initialize the counter manager with empty state."""
        self._lock = threading.Lock()
        self._seq_counters: dict[str, int] = {}
        self._running_count: int = 0
        self._last_receipt_refs: dict[str, str] = {}

    def next_seq(self, agent_id: str) -> int:
        """Get the next sequence number for an agent.

        The first call for a given agent_id returns 1. Each subsequent
        call increments by exactly 1. Counters are independent per agent.

        Args:
            agent_id: The identity of the agent requesting a sequence number.

        Returns:
            The next seq value (starts at 1, increments by 1).
        """
        with self._lock:
            current = self._seq_counters.get(agent_id, 0)
            new_seq = current + 1
            self._seq_counters[agent_id] = new_seq
            return new_seq

    def next_running_count(self) -> int:
        """Get the next global running count.

        A single counter shared across all agents. The first call returns 1,
        each subsequent call increments by exactly 1.

        Returns:
            The next running_count value (starts at 1, increments by 1).
        """
        with self._lock:
            self._running_count += 1
            return self._running_count

    def current_seq(self, agent_id: str) -> int:
        """Get the current sequence number for an agent without incrementing.

        Returns 0 if no sequence has been assigned to the agent yet.

        Args:
            agent_id: The identity of the agent to query.

        Returns:
            The current seq value (0 if never incremented).
        """
        with self._lock:
            return self._seq_counters.get(agent_id, 0)

    def current_running_count(self) -> int:
        """Get the current global running count without incrementing.

        Returns 0 if no decisions have been produced yet.

        Returns:
            The current running_count value (0 if never incremented).
        """
        with self._lock:
            return self._running_count

    def get_last_receipt_ref(self, agent_id: str) -> str:
        """Get the last receipt_ref for an agent.

        Used for hash-chain linking: each new decision's receipt_ref
        incorporates the prior decision's receipt_ref.

        Returns GENESIS_RECEIPT_REF (64 hex zeros) if no receipt has been
        stored for the agent yet (i.e., the next decision will be seq=1).

        Args:
            agent_id: The identity of the agent to query.

        Returns:
            The last stored receipt_ref, or GENESIS_RECEIPT_REF if none exists.
        """
        with self._lock:
            return self._last_receipt_refs.get(agent_id, GENESIS_RECEIPT_REF)

    def set_last_receipt_ref(self, agent_id: str, receipt_ref: str) -> None:
        """Store the receipt_ref after a decision is produced.

        Called by the GovernanceEngine after computing a decision's
        receipt_ref, so the next decision for this agent can chain to it.

        Args:
            agent_id: The identity of the agent that produced the decision.
            receipt_ref: The receipt_ref value of the produced decision.
        """
        with self._lock:
            self._last_receipt_refs[agent_id] = receipt_ref

    def reset(self) -> None:
        """Reset all counters to initial state.

        Clears per-agent sequence counters, the global running count,
        and all stored receipt_refs. Intended for testing purposes.
        """
        with self._lock:
            self._seq_counters.clear()
            self._running_count = 0
            self._last_receipt_refs.clear()
