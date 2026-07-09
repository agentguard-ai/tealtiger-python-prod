"""TEEC v2.1 Governance Contract — Core Types (Python SDK).

Extends the v1.2 Decision type with cryptographic verifiability and
tamper-evidence fields: intent_ref, receipt_ref, seq, running_count,
normalization_id, and governance_seal.

All v1.2 fields are preserved as a strict superset. When no seal_secret
is configured, v1.2 behavior is unchanged.

Module: core/engine/v2_1/types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

GENESIS_RECEIPT_REF: str = "0" * 64
"""Well-known genesis value (64 hex zero characters) used as the previous
receipt_ref for the first decision in a chain (seq=1)."""


@dataclass
class GovernanceSeal:
    """Cryptographic seal for a governance decision.

    Combines HMAC-SHA256 of the decision payload with a timestamp
    and agent identity. Reproducible given the same inputs.
    """

    hmac: str
    """Hex-encoded HMAC-SHA256 of the decision payload."""

    timestamp: int
    """Unix milliseconds timestamp when the seal was computed."""

    agent_id: str
    """Identity of the agent that produced the sealed decision."""


@dataclass
class DecisionV21:
    """TEEC v2.1 Decision — extends v1.2 with cryptographic fields.

    All v1.2 base fields are preserved unchanged. The six new v2.1 fields
    (intent_ref, receipt_ref, seq, running_count, normalization_id,
    governance_seal) provide cryptographic provenance and ordering.
    """

    # v1.2 base fields
    action: str = "ALLOW"
    reason_codes: List[str] = field(default_factory=list)
    risk_score: int = 0
    mode: str = "ENFORCE"
    policy_id: str = ""
    policy_version: str = ""
    component_versions: Dict[str, str] = field(default_factory=dict)
    correlation_id: str = ""
    reason: str = ""
    event_type: str = ""
    timestamp: int = 0
    module: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # v1.2 optional fields preserved
    trace_id: Optional[str] = None
    workflow_id: Optional[str] = None
    run_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    provider: Optional[str] = None
    registry_refs: Optional[List[Dict[str, str]]] = None
    findings: Optional[List[Dict[str, Any]]] = None

    # v2.1 cryptographic fields
    intent_ref: str = ""
    """SHA-256 hash of the serialized request payload (TOCTOU closure)."""

    receipt_ref: str = ""
    """SHA-256 hash linking this decision to the prior decision in the chain."""

    seq: int = 0
    """Per-agent monotonically increasing sequence number (starts at 1)."""

    running_count: int = 0
    """Global decision counter across all agents (starts at 1)."""

    normalization_id: str = ""
    """SHA-256 hash of the canonically normalized request payload."""

    governance_seal: Optional[GovernanceSeal] = None
    """Cryptographic seal binding all decision fields."""

    teec_version: str = "2.1"
    """TEEC schema version identifier."""


@dataclass
class ValidationContext:
    """Context required for validating a governance decision.

    Provides the original request payload and seal_secret needed
    to recompute and verify the decision's cryptographic fields.
    """

    request_payload: Dict[str, Any]
    """The original request payload that was evaluated."""

    seal_secret: str
    """The seal_secret used to compute the GovernanceSeal HMAC."""

    reference_time: Optional[int] = None
    """Reference timestamp (Unix ms) for drift checking. Defaults to now."""

    timestamp_tolerance_ms: Optional[int] = None
    """Acceptable timestamp drift in milliseconds. Defaults to 60000."""


@dataclass
class ValidationSuccess:
    """Result returned when validate_governance_decision passes all checks."""

    valid: Literal[True] = True
    receipt_ref: str = ""
    """Recomputed receipt_ref for the validated decision."""

    intent_ref: str = ""
    """Verified intent_ref from the decision."""


@dataclass
class ValidationFailure:
    """Result returned when validate_governance_decision detects an issue."""

    valid: Literal[False] = False
    error_type: str = ""
    """Error category: 'seal_mismatch' | 'intent_mismatch' | 'schema_violation' | 'timestamp_drift'"""

    message: str = ""
    """Human-readable description of the validation failure."""


@dataclass
class ContiguitySuccess:
    """Result returned when verify_contiguity confirms a valid chain."""

    valid: Literal[True] = True
    count: int = 0
    """Number of decisions in the verified chain."""


@dataclass
class ContiguityFailure:
    """Result returned when verify_contiguity detects a chain integrity issue."""

    valid: Literal[False] = False
    index: int = 0
    """Index of the first decision that failed verification."""

    check: str = ""
    """Failed check type: 'seq_gap' | 'chain_break' | 'count_regression' | 'version_incompatible'"""

    message: str = ""
    """Human-readable description of the contiguity failure."""
