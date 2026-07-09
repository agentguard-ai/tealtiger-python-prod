"""
FreezeRegistry — Global in-memory singleton that tracks frozen agent IDs.

Provides the kill switch mechanism: freeze() immediately blocks all
subsequent requests for a given agent (or all agents with '*').
unfreeze() restores normal operation.

- In-memory only (persists for process lifetime, resets on restart)
- No external service or database dependency
- Idempotent: freeze(id) called N times ≡ called once
- No-error: unfreeze(id) on non-frozen agent is a no-op
- Thread-safe via threading.Lock
"""

import threading


class FreezeRegistry:
    """Singleton registry tracking which agents are frozen.

    Uses a class-level ``_instance`` and a ``threading.Lock`` to ensure
    thread-safe singleton access and mutation of the frozen-agents set.
    """

    _instance: "FreezeRegistry | None" = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._frozen_agents: set[str] = set()
        self._wildcard_frozen: bool = False
        self._lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "FreezeRegistry":
        """Get the singleton FreezeRegistry instance (thread-safe)."""
        if cls._instance is None:
            with cls._instance_lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def freeze(self, agent_id: str) -> None:
        """Register an agent as frozen. Idempotent.

        Use ``'*'`` to freeze all agents globally.

        Args:
            agent_id: The agent identifier to freeze, or ``'*'`` for all agents.
        """
        with self._lock:
            if agent_id == "*":
                self._wildcard_frozen = True
            else:
                self._frozen_agents.add(agent_id)

    def unfreeze(self, agent_id: str) -> None:
        """Remove an agent from frozen state. No-op if not frozen.

        Use ``'*'`` to unfreeze the global wildcard.

        Args:
            agent_id: The agent identifier to unfreeze, or ``'*'`` for all.
        """
        with self._lock:
            if agent_id == "*":
                self._wildcard_frozen = False
            else:
                self._frozen_agents.discard(agent_id)

    def is_frozen(self, agent_id: str) -> bool:
        """Check if a specific agent is frozen.

        Returns ``True`` if the agent is individually frozen OR
        the wildcard freeze is active.

        Args:
            agent_id: The agent identifier to check.

        Returns:
            True if the agent is currently frozen, False otherwise.
        """
        with self._lock:
            return self._wildcard_frozen or agent_id in self._frozen_agents

    def is_wildcard_freeze(self) -> bool:
        """Check whether the current freeze state includes a wildcard freeze.

        Returns:
            True if ``freeze('*')`` has been called and not yet unfrozen.
        """
        with self._lock:
            return self._wildcard_frozen

    def _reset(self) -> None:
        """Reset registry state. Used for testing only."""
        with self._lock:
            self._frozen_agents.clear()
            self._wildcard_frozen = False


# --- Top-level convenience functions ---


def freeze(agent_id: str) -> None:
    """Immediately freeze an agent, blocking all subsequent requests.

    Use ``'*'`` to freeze all agents globally.

    Example::

        from tealtiger.observe.freeze_registry import freeze
        freeze('research-agent')  # blocks this agent
        freeze('*')               # blocks ALL agents

    Args:
        agent_id: The agent identifier to freeze, or ``'*'`` for all agents.
    """
    FreezeRegistry.get_instance().freeze(agent_id)


def unfreeze(agent_id: str) -> None:
    """Unfreeze an agent, restoring normal operation.

    No-op if the agent is not currently frozen.

    Example::

        from tealtiger.observe.freeze_registry import unfreeze
        unfreeze('research-agent')  # restores this agent
        unfreeze('*')               # removes global freeze

    Args:
        agent_id: The agent identifier to unfreeze, or ``'*'`` for all.
    """
    FreezeRegistry.get_instance().unfreeze(agent_id)
