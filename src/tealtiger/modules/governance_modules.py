"""TealDrift, TealState, TealTemporal — Governance Modules (Python SDK).

Ports of the TypeScript governance modules to Python with identical semantics:
- TealDrift: Behavioral drift detection using rolling statistical baselines
- TealState: Context and state governance per agent
- TealTemporal: Session TTL, cooldown, and time-of-day restrictions

Module: modules/governance_modules
Requirements: 9.11, 18.1, 18.2, 18.5–18.9
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional


# ══════════════════════════════════════════════════════════════════
# TealDrift — Behavioral Drift Detection
# ══════════════════════════════════════════════════════════════════


@dataclass
class RollingStats:
    """Rolling statistics using Welford's online algorithm."""

    mean: float = 0.0
    variance: float = 0.0
    count: int = 0


@dataclass
class DriftBaseline:
    """Baseline for a specific agent/provider/model combination."""

    agent_id: str = ""
    provider: str = ""
    model: str = ""
    refusal_rate: RollingStats = field(default_factory=RollingStats)
    response_length: RollingStats = field(default_factory=RollingStats)
    topic_distribution: Dict[str, int] = field(default_factory=dict)
    sample_count: int = 0
    last_updated: float = 0.0


@dataclass
class DriftObservation:
    """A single behavioral observation for drift detection."""

    agent_id: str
    provider: str
    model: str
    refusal: bool = False
    response_length: int = 0
    topics: List[str] = field(default_factory=list)


@dataclass
class DriftConfig:
    """Configuration for TealDrift module."""

    baseline_window: int = 100
    threshold_sigma: float = 3.0
    min_samples: int = 50


def _update_rolling_stats(stats: RollingStats, value: float) -> RollingStats:
    """Update rolling stats using Welford's online algorithm."""
    new_count = stats.count + 1
    delta = value - stats.mean
    new_mean = stats.mean + delta / new_count
    delta2 = value - new_mean
    new_variance = (
        0.0
        if new_count == 1
        else (stats.variance * (stats.count - 1) + delta * delta2) / (new_count - 1)
    )
    return RollingStats(mean=new_mean, variance=new_variance, count=new_count)


def _stddev(variance: float) -> float:
    """Compute standard deviation from variance."""
    return math.sqrt(max(0.0, variance))


class TealDriftModule:
    """TealDrift — Behavioral Drift Detection Module.

    Maintains rolling statistical baselines per agent/provider/model and
    alerts when behavior diverges beyond a configurable threshold (sigma).

    Emits reason code: BEHAVIORAL_DRIFT_DETECTED
    """

    MODULE_NAME = "TealDrift"
    MODULE_VERSION = "1.3.0"
    REASON_CODE = "BEHAVIORAL_DRIFT_DETECTED"

    def __init__(self, config: Optional[DriftConfig] = None) -> None:
        self.config = config or DriftConfig()
        self._baselines: Dict[str, DriftBaseline] = {}

    def _baseline_key(self, agent_id: str, provider: str, model: str) -> str:
        return f"{agent_id}::{provider}::{model}"

    def update_baseline(self, observation: DriftObservation) -> None:
        """Update the rolling statistical baseline with a new observation."""
        key = self._baseline_key(
            observation.agent_id, observation.provider, observation.model
        )
        baseline = self._baselines.get(key)

        if baseline is None:
            baseline = DriftBaseline(
                agent_id=observation.agent_id,
                provider=observation.provider,
                model=observation.model,
            )
            self._baselines[key] = baseline

        # Update refusal_rate (boolean → 0 or 1)
        refusal_value = 1.0 if observation.refusal else 0.0
        baseline.refusal_rate = _update_rolling_stats(
            baseline.refusal_rate, refusal_value
        )

        # Update response_length
        baseline.response_length = _update_rolling_stats(
            baseline.response_length, float(observation.response_length)
        )

        # Update topic_distribution
        for topic in observation.topics:
            baseline.topic_distribution[topic] = (
                baseline.topic_distribution.get(topic, 0) + 1
            )

        baseline.sample_count += 1
        baseline.last_updated = time.time()

    def check_drift(
        self, observation: DriftObservation
    ) -> Optional[Dict[str, Any]]:
        """Check whether the observation represents behavioral drift.

        Returns None if no drift detected or insufficient samples.
        Returns a dict with drift info if behavior diverges beyond threshold_sigma.
        """
        key = self._baseline_key(
            observation.agent_id, observation.provider, observation.model
        )
        baseline = self._baselines.get(key)

        # No baseline established yet
        if baseline is None:
            return None

        # Not enough samples
        if baseline.sample_count < self.config.min_samples:
            return None

        # Check refusal_rate drift
        refusal_value = 1.0 if observation.refusal else 0.0
        refusal_std = _stddev(baseline.refusal_rate.variance)
        if refusal_std > 0:
            refusal_deviation = (
                abs(refusal_value - baseline.refusal_rate.mean) / refusal_std
            )
            if refusal_deviation > self.config.threshold_sigma:
                return {
                    "drifted": True,
                    "metric": "refusal_rate",
                    "deviation_sigma": refusal_deviation,
                }

        # Check response_length drift
        length_std = _stddev(baseline.response_length.variance)
        if length_std > 0:
            length_deviation = (
                abs(observation.response_length - baseline.response_length.mean)
                / length_std
            )
            if length_deviation > self.config.threshold_sigma:
                return {
                    "drifted": True,
                    "metric": "response_length",
                    "deviation_sigma": length_deviation,
                }

        # Check topic_distribution drift (all unseen topics = potential drift)
        if observation.topics and baseline.topic_distribution:
            total_topic_obs = sum(baseline.topic_distribution.values())
            unseen_topics = [
                t
                for t in observation.topics
                if t not in baseline.topic_distribution
            ]
            if (
                len(unseen_topics) == len(observation.topics)
                and total_topic_obs >= self.config.min_samples
            ):
                return {
                    "drifted": True,
                    "metric": "topic_distribution",
                    "deviation_sigma": self.config.threshold_sigma + 1,
                }

        return None

    def get_baseline(
        self, agent_id: str, provider: Optional[str] = None, model: Optional[str] = None
    ) -> Optional[DriftBaseline]:
        """Get the current baseline for a given agent/provider/model."""
        if provider and model:
            return self._baselines.get(
                self._baseline_key(agent_id, provider, model)
            )
        # Find first matching agent_id
        for baseline in self._baselines.values():
            if baseline.agent_id == agent_id:
                return baseline
        return None

    def reset(self) -> None:
        """Clear all baselines."""
        self._baselines.clear()


# ══════════════════════════════════════════════════════════════════
# TealState — Context and State Governance
# ══════════════════════════════════════════════════════════════════


@dataclass
class ContextEntry:
    """A single context entry with provenance metadata."""

    content: str
    source: str
    timestamp: float = 0.0
    trust_tier: str = "untrusted_document"


@dataclass
class StateConfig:
    """Configuration for TealState module."""

    max_context_size: int = 128_000  # bytes
    on_exceed: Literal["truncate", "deny", "alert"] = "deny"
    track_provenance: bool = True
    mutation_governance: bool = False


@dataclass
class _TrackedEntry:
    """Internal tracked entry with size metadata."""

    entry: ContextEntry
    size: int
    added_at: float


@dataclass
class _MutationRecord:
    """Internal mutation log record."""

    timestamp: float
    action: str
    source: str
    authorized: bool
    entry_summary: str


@dataclass
class _AgentContext:
    """Internal per-agent context state."""

    agent_id: str
    entries: List[_TrackedEntry] = field(default_factory=list)
    total_size: int = 0
    mutation_log: List[_MutationRecord] = field(default_factory=list)


class TealStateModule:
    """TealState — Context and State Governance Module.

    Tracks context entries per agent with provenance metadata and enforces
    configurable maximum context window size limits.

    Actions on exceed:
    - truncate: remove oldest entries until within limit
    - deny: reject new entry
    - alert: allow but emit warning event

    Emits reason code: CONTEXT_SIZE_EXCEEDED
    """

    MODULE_NAME = "TealState"
    MODULE_VERSION = "1.3.0"
    REASON_CODE_EXCEEDED = "CONTEXT_SIZE_EXCEEDED"
    REASON_CODE_MUTATION = "UNAUTHORIZED_STATE_MUTATION"

    def __init__(self, config: Optional[StateConfig] = None) -> None:
        self.config = config or StateConfig()
        self._contexts: Dict[str, _AgentContext] = {}
        self._events: List[Dict[str, Any]] = []

    def add_context(self, agent_id: str, entry: ContextEntry) -> Dict[str, Any]:
        """Add a context entry for the given agent.

        Enforces max_context_size and takes the configured action on exceed.
        Returns dict with 'allowed' bool and optional 'reason_code'.
        """
        agent_ctx = self._get_or_create_context(agent_id)
        entry_size = len(entry.content.encode("utf-8"))
        new_total = agent_ctx.total_size + entry_size

        if new_total > self.config.max_context_size:
            self._emit_event(
                "governance.state.context_exceeded",
                {
                    "agent_id": agent_id,
                    "current_size": agent_ctx.total_size,
                    "entry_size": entry_size,
                    "max_size": self.config.max_context_size,
                },
            )

            if self.config.on_exceed == "deny":
                return {"allowed": False, "reason_code": self.REASON_CODE_EXCEEDED}
            elif self.config.on_exceed == "truncate":
                self._truncate_oldest(agent_ctx, entry_size)
            # 'alert' — allow but event already emitted

        # Add the entry
        tracked = _TrackedEntry(entry=entry, size=entry_size, added_at=time.time())
        agent_ctx.entries.append(tracked)
        agent_ctx.total_size += entry_size

        # Log mutation if governance enabled
        if self.config.mutation_governance:
            agent_ctx.mutation_log.append(
                _MutationRecord(
                    timestamp=time.time(),
                    action="add",
                    source=entry.source,
                    authorized=True,
                    entry_summary=entry.content[:100],
                )
            )

        return {"allowed": True}

    def get_context(self, agent_id: str) -> List[ContextEntry]:
        """Get the current context entries for an agent."""
        agent_ctx = self._contexts.get(agent_id)
        if not agent_ctx:
            return []
        return [t.entry for t in agent_ctx.entries]

    def get_context_size(self, agent_id: str) -> int:
        """Get the current context size in bytes for an agent."""
        agent_ctx = self._contexts.get(agent_id)
        return agent_ctx.total_size if agent_ctx else 0

    def remove_context(
        self,
        agent_id: str,
        index: int,
        source: str,
        authorized: bool = True,
    ) -> Dict[str, Any]:
        """Remove a context entry by index. Logs as mutation if governance enabled."""
        agent_ctx = self._contexts.get(agent_id)
        if not agent_ctx or index < 0 or index >= len(agent_ctx.entries):
            return {"allowed": False, "reason_code": "INVALID_INDEX"}

        if self.config.mutation_governance and not authorized:
            agent_ctx.mutation_log.append(
                _MutationRecord(
                    timestamp=time.time(),
                    action="remove",
                    source=source,
                    authorized=False,
                    entry_summary=agent_ctx.entries[index].entry.content[:100],
                )
            )
            self._emit_event(
                "governance.state.unauthorized_mutation",
                {
                    "agent_id": agent_id,
                    "action": "remove",
                    "source": source,
                    "index": index,
                },
            )
            return {"allowed": False, "reason_code": self.REASON_CODE_MUTATION}

        removed = agent_ctx.entries.pop(index)
        agent_ctx.total_size -= removed.size

        if self.config.mutation_governance:
            agent_ctx.mutation_log.append(
                _MutationRecord(
                    timestamp=time.time(),
                    action="remove",
                    source=source,
                    authorized=True,
                    entry_summary=removed.entry.content[:100],
                )
            )

        return {"allowed": True}

    def get_mutation_log(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get the mutation log for an agent."""
        agent_ctx = self._contexts.get(agent_id)
        if not agent_ctx:
            return []
        return [
            {
                "timestamp": r.timestamp,
                "action": r.action,
                "source": r.source,
                "authorized": r.authorized,
                "entry_summary": r.entry_summary,
            }
            for r in agent_ctx.mutation_log
        ]

    def get_events(self) -> List[Dict[str, Any]]:
        """Get emitted events."""
        return list(self._events)

    def clear_context(self, agent_id: str) -> None:
        """Clear all context for an agent."""
        self._contexts.pop(agent_id, None)

    def _get_or_create_context(self, agent_id: str) -> _AgentContext:
        if agent_id not in self._contexts:
            self._contexts[agent_id] = _AgentContext(agent_id=agent_id)
        return self._contexts[agent_id]

    def _truncate_oldest(self, agent_ctx: _AgentContext, needed_space: int) -> None:
        """Remove oldest entries until there's enough space."""
        target_size = self.config.max_context_size - needed_space
        while agent_ctx.entries and agent_ctx.total_size > target_size:
            removed = agent_ctx.entries.pop(0)
            agent_ctx.total_size -= removed.size
            if self.config.mutation_governance:
                agent_ctx.mutation_log.append(
                    _MutationRecord(
                        timestamp=time.time(),
                        action="remove",
                        source="system:truncation",
                        authorized=True,
                        entry_summary=removed.entry.content[:100],
                    )
                )

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self._events.append({"type": event_type, "data": data})


# ══════════════════════════════════════════════════════════════════
# TealTemporal — Session and Time Governance
# ══════════════════════════════════════════════════════════════════


@dataclass
class CooldownRule:
    """Cooldown rule for minimum intervals between actions."""

    action_class: str
    min_interval_ms: int


@dataclass
class TimeRestriction:
    """Time-of-day restriction for an action class."""

    action_class: str
    allowed_hours: Dict[str, int]  # {"start": 9, "end": 17}
    timezone: str = "UTC"
    allowed_days: List[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])  # Mon-Fri


@dataclass
class TemporalConfig:
    """Configuration for TealTemporal module."""

    session_ttl_ms: int = 3_600_000  # 1 hour
    cooldown_rules: List[CooldownRule] = field(default_factory=list)
    time_restrictions: List[TimeRestriction] = field(default_factory=list)
    age_warning_threshold: int = 80  # warn at 80% of TTL


@dataclass
class _SessionRecord:
    """Internal session tracking record."""

    agent_id: str
    started_at: float  # ms timestamp
    last_activity: float  # ms timestamp


@dataclass
class _ActionRecord:
    """Internal action history record."""

    agent_id: str
    action_class: str
    executed_at: float  # ms timestamp


class TealTemporalModule:
    """TealTemporal — Session and Time Governance Module.

    Enforces temporal governance controls:
    - Session TTL: terminate sessions that exceed their time-to-live
    - Cooldown periods: enforce minimum intervals between same action class
    - Time-of-day restrictions: block actions outside allowed hours/days

    Emits reason codes:
    - SESSION_TTL_EXPIRED
    - SESSION_AGE_WARNING
    - COOLDOWN_PERIOD_ACTIVE
    - TIME_RESTRICTION_VIOLATED
    """

    MODULE_NAME = "TealTemporal"
    MODULE_VERSION = "1.3.0"

    REASON_SESSION_EXPIRED = "SESSION_TTL_EXPIRED"
    REASON_SESSION_WARNING = "SESSION_AGE_WARNING"
    REASON_COOLDOWN_ACTIVE = "COOLDOWN_PERIOD_ACTIVE"
    REASON_TIME_RESTRICTED = "TIME_RESTRICTION_VIOLATED"

    def __init__(
        self,
        config: Optional[TemporalConfig] = None,
        now_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        """Initialize TealTemporal.

        Args:
            config: Temporal governance configuration.
            now_fn: Injectable time source returning milliseconds since epoch.
                    Defaults to time.time() * 1000.
        """
        self.config = config or TemporalConfig()
        self._now_fn = now_fn or (lambda: time.time() * 1000)
        self._sessions: Dict[str, _SessionRecord] = {}
        self._action_history: Dict[str, List[_ActionRecord]] = {}
        self._events: List[Dict[str, Any]] = []

    def start_session(self, agent_id: str) -> None:
        """Start or retrieve a session for the given agent."""
        if agent_id not in self._sessions:
            now = self._now_fn()
            self._sessions[agent_id] = _SessionRecord(
                agent_id=agent_id, started_at=now, last_activity=now
            )

    def check_session(self, agent_id: str) -> Dict[str, Any]:
        """Check session status for the given agent.

        Returns dict with 'expired', 'warning', and optional 'reason_code'.
        """
        session = self._sessions.get(agent_id)
        if session is None:
            return {
                "expired": True,
                "warning": False,
                "reason_code": self.REASON_SESSION_EXPIRED,
            }

        now = self._now_fn()
        elapsed = now - session.started_at

        # Check if TTL exceeded
        if elapsed >= self.config.session_ttl_ms:
            self._emit_event(
                "governance.temporal.session_expired",
                {
                    "agent_id": agent_id,
                    "elapsed_ms": elapsed,
                    "ttl_ms": self.config.session_ttl_ms,
                },
            )
            return {
                "expired": True,
                "warning": False,
                "reason_code": self.REASON_SESSION_EXPIRED,
            }

        # Check if in warning zone
        warning_threshold_ms = (
            self.config.age_warning_threshold / 100
        ) * self.config.session_ttl_ms
        if elapsed >= warning_threshold_ms:
            self._emit_event(
                "governance.temporal.session_warning",
                {
                    "agent_id": agent_id,
                    "elapsed_ms": elapsed,
                    "ttl_ms": self.config.session_ttl_ms,
                    "threshold_percent": self.config.age_warning_threshold,
                },
            )
            return {
                "expired": False,
                "warning": True,
                "reason_code": self.REASON_SESSION_WARNING,
            }

        # Update last activity
        session.last_activity = now
        return {"expired": False, "warning": False}

    def check_cooldown(self, agent_id: str, action_class: str) -> Dict[str, Any]:
        """Check cooldown status for the given agent and action class.

        Returns dict with 'blocked', 'remaining_ms', and optional 'reason_code'.
        """
        rule = next(
            (r for r in self.config.cooldown_rules if r.action_class == action_class),
            None,
        )

        if rule is None:
            return {"blocked": False, "remaining_ms": 0}

        key = f"{agent_id}::{action_class}"
        history = self._action_history.get(key, [])
        now = self._now_fn()

        # Find the most recent execution
        if not history:
            return {"blocked": False, "remaining_ms": 0}

        last_execution = history[-1]
        elapsed = now - last_execution.executed_at
        remaining = rule.min_interval_ms - elapsed

        if remaining > 0:
            self._emit_event(
                "governance.temporal.cooldown_active",
                {
                    "agent_id": agent_id,
                    "action_class": action_class,
                    "remaining_ms": remaining,
                    "min_interval_ms": rule.min_interval_ms,
                },
            )
            return {
                "blocked": True,
                "remaining_ms": remaining,
                "reason_code": self.REASON_COOLDOWN_ACTIVE,
            }

        return {"blocked": False, "remaining_ms": 0}

    def record_action(self, agent_id: str, action_class: str) -> None:
        """Record an action execution for cooldown tracking."""
        key = f"{agent_id}::{action_class}"
        if key not in self._action_history:
            self._action_history[key] = []
        self._action_history[key].append(
            _ActionRecord(
                agent_id=agent_id,
                action_class=action_class,
                executed_at=self._now_fn(),
            )
        )

    def check_time_restriction(self, action_class: str) -> Dict[str, Any]:
        """Check time-of-day restrictions for the given action class.

        Returns dict with 'blocked' and optional 'reason_code'.
        """
        restriction = next(
            (
                r
                for r in self.config.time_restrictions
                if r.action_class == action_class
            ),
            None,
        )

        if restriction is None:
            return {"blocked": False}

        now = self._get_now_in_timezone(restriction.timezone)
        current_hour = now.hour
        current_day = now.weekday()  # 0=Mon in Python, but we'll use isoweekday-style
        # Convert to JS-style: 0=Sun, 1=Mon, ..., 6=Sat
        js_day = (now.weekday() + 1) % 7  # Python weekday: Mon=0 → JS: Mon=1

        # Check day restriction
        if js_day not in restriction.allowed_days:
            self._emit_event(
                "governance.temporal.time_restricted",
                {
                    "action_class": action_class,
                    "current_day": js_day,
                    "allowed_days": restriction.allowed_days,
                    "timezone": restriction.timezone,
                },
            )
            return {"blocked": True, "reason_code": self.REASON_TIME_RESTRICTED}

        # Check hour restriction
        start = restriction.allowed_hours.get("start", 0)
        end = restriction.allowed_hours.get("end", 24)

        if start <= end:
            within_hours = start <= current_hour < end
        else:
            # Overnight range (e.g., 22-6)
            within_hours = current_hour >= start or current_hour < end

        if not within_hours:
            self._emit_event(
                "governance.temporal.time_restricted",
                {
                    "action_class": action_class,
                    "current_hour": current_hour,
                    "allowed_hours": restriction.allowed_hours,
                    "timezone": restriction.timezone,
                },
            )
            return {"blocked": True, "reason_code": self.REASON_TIME_RESTRICTED}

        return {"blocked": False}

    def end_session(self, agent_id: str) -> None:
        """End a session for the given agent."""
        self._sessions.pop(agent_id, None)

    def get_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get session info for an agent."""
        session = self._sessions.get(agent_id)
        if session is None:
            return None
        return {
            "agent_id": session.agent_id,
            "started_at": session.started_at,
            "last_activity": session.last_activity,
        }

    def get_events(self) -> List[Dict[str, Any]]:
        """Get emitted events."""
        return list(self._events)

    def _get_now_in_timezone(self, tz_name: str) -> datetime:
        """Get current time in the specified timezone."""
        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(tz_name)
        except (ImportError, KeyError):
            tz = timezone.utc

        # Use the injectable time source
        now_ms = self._now_fn()
        now_utc = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
        return now_utc.astimezone(tz)

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self._events.append({"type": event_type, "data": data})
