"""Multi-Stage Defense Pipeline — Stage Decision Builder (Python SDK).

Produces StageDecision objects from merged evaluation results,
optionally enriched with TEEC v2.1 cryptographic fields
(intent_ref, receipt_ref, seq, running_count, normalization_id, governance_seal).

Uses hashlib for SHA-256 hashing and hmac for HMAC-SHA256 computation.
Deterministic serialization via json.dumps(sort_keys=True, separators=(',', ':')).

Module: pipeline/stage_decision_builder
Requirements: 11.2, 11.5, 11.6
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .types import ModuleEvalDetail, PipelineStage, StageDecision


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENESIS_RECEIPT_REF: str = "0" * 64
"""The initial receipt reference used as the base of the receipt chain.

A 64-character hex string of all zeros, representing the genesis (first)
entry in the contiguity chain before any decisions have been produced.
"""


# ---------------------------------------------------------------------------
# Contiguity Result
# ---------------------------------------------------------------------------


@dataclass
class ContiguityResult:
    """Result of verifying contiguity across a chain of StageDecisions.

    Attributes:
        valid: Whether the chain is valid (monotonic seq, correct receipt chaining).
        error: Human-readable error message when the chain is invalid.
    """

    valid: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Build Parameters
# ---------------------------------------------------------------------------


@dataclass
class StageDecisionBuildParams:
    """Parameters for building a StageDecision.

    Attributes:
        action: The merged action for the stage (e.g., ALLOW, DENY, MONITOR).
        reason_codes: All reason codes from evaluated modules.
        stage: Which pipeline stage produced this decision.
        latency_ms: Stage evaluation duration in milliseconds.
        module_details: Per-module evaluation details.
        payload: The request or response payload used for intent binding.
        remediation: Remediation details (PostExecution only).
    """

    action: str
    reason_codes: List[str]
    stage: PipelineStage
    latency_ms: float
    module_details: List[ModuleEvalDetail]
    payload: Dict[str, Any]
    remediation: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Stage Decision Builder
# ---------------------------------------------------------------------------


class StageDecisionBuilder:
    """Builds StageDecision objects, optionally enriched with TEEC v2.1
    cryptographic provenance fields when a seal secret is configured.

    When ``seal_secret`` is provided:
    - ``intent_ref`` = SHA-256 of deterministically serialized payload
    - ``receipt_ref`` = SHA-256 chain linking to the previous decision's receipt
    - ``seq`` = monotonically increasing per-agent counter
    - ``running_count`` = global counter across all agents
    - ``normalization_id`` = SHA-256 of canonically normalized payload
    - ``governance_seal`` = { hmac: HMAC-SHA256 of decision fields, timestamp, agent_id }

    Args:
        seal_secret: Optional TEEC v2.1 seal secret. When set, enables
            cryptographic provenance on all produced decisions.
        agent_id: Agent identifier for TEEC v2.1 scoping. Defaults to 'default'.
    """

    def __init__(
        self,
        seal_secret: Optional[str] = None,
        agent_id: str = "default",
    ) -> None:
        self._seal_secret = seal_secret
        self._agent_id = agent_id

        # Internal counters mirroring CounterManager behavior
        self._seq_counters: Dict[str, int] = {}
        self._running_count: int = 0
        self._last_receipt_refs: Dict[str, str] = {}

    def build(self, params: StageDecisionBuildParams) -> StageDecision:
        """Build a StageDecision from merged evaluation results.

        When seal_secret is configured, computes all TEEC v2.1 fields.

        Args:
            params: Build parameters containing the merged action,
                reason codes, stage, timing, module details, and payload.

        Returns:
            A fully constructed StageDecision, optionally enriched
            with TEEC v2.1 cryptographic provenance fields.
        """
        decision = StageDecision(
            action=params.action,
            reason_codes=params.reason_codes,
            stage=params.stage,
            latency_ms=params.latency_ms,
            module_details=params.module_details,
        )

        if params.remediation is not None:
            decision.remediation = params.remediation

        if self._seal_secret is not None:
            self._apply_teec_fields(decision, params.payload)

        return decision

    def verify_contiguity(self, decisions: List[StageDecision]) -> ContiguityResult:
        """Verify that a chain of StageDecisions has valid contiguity.

        Checks:
        1. All decisions have TEEC v2.1 fields (seq, receipt_ref).
        2. ``seq`` values are monotonically increasing (each > previous).
        3. Each decision's ``receipt_ref`` correctly chains to the previous decision.

        Args:
            decisions: Chronologically ordered StageDecisions to verify.

        Returns:
            ContiguityResult indicating whether the chain is valid.
        """
        if not decisions:
            return ContiguityResult(valid=True)

        # All decisions must have TEEC v2.1 fields to verify contiguity
        for i, d in enumerate(decisions):
            if d.seq is None or d.receipt_ref is None:
                return ContiguityResult(
                    valid=False,
                    error=(
                        f"Decision at index {i} is missing TEEC v2.1 fields "
                        f"(seq or receipt_ref)"
                    ),
                )

        # Check seq monotonicity
        for i in range(1, len(decisions)):
            if decisions[i].seq <= decisions[i - 1].seq:  # type: ignore[operator]
                return ContiguityResult(
                    valid=False,
                    error=(
                        f"seq is not monotonically increasing at index {i}: "
                        f"{decisions[i].seq} <= {decisions[i - 1].seq}"
                    ),
                )

        # Check receipt_ref chaining
        # First decision's receipt_ref should chain from GENESIS_RECEIPT_REF
        first_expected = self._compute_receipt_ref(decisions[0], GENESIS_RECEIPT_REF)
        if decisions[0].receipt_ref != first_expected:
            return ContiguityResult(
                valid=False,
                error=(
                    f"receipt_ref chain break at index 0: "
                    f"expected {first_expected}, got {decisions[0].receipt_ref}"
                ),
            )

        # Subsequent decisions chain from the previous decision's receipt_ref
        for i in range(1, len(decisions)):
            expected = self._compute_receipt_ref(
                decisions[i],
                decisions[i - 1].receipt_ref,  # type: ignore[arg-type]
            )
            if decisions[i].receipt_ref != expected:
                return ContiguityResult(
                    valid=False,
                    error=(
                        f"receipt_ref chain break at index {i}: "
                        f"expected {expected}, got {decisions[i].receipt_ref}"
                    ),
                )

        return ContiguityResult(valid=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_teec_fields(
        self, decision: StageDecision, payload: Dict[str, Any]
    ) -> None:
        """Apply TEEC v2.1 cryptographic fields to a StageDecision.

        Computes and assigns:
        - intent_ref: SHA-256 of deterministically serialized payload
        - seq: monotonically increasing per-agent counter
        - running_count: global decision counter
        - normalization_id: SHA-256 of canonically normalized payload
        - receipt_ref: SHA-256 chain linking to previous decision
        - governance_seal: HMAC-SHA256 seal over decision fields

        Args:
            decision: The StageDecision to enrich with TEEC fields.
            payload: The request/response payload for intent binding.
        """
        # intent_ref = SHA-256 of deterministically serialized payload
        serialized_payload = self._deterministic_serialize(payload)
        decision.intent_ref = self._sha256(serialized_payload)

        # seq = monotonically increasing per agent
        decision.seq = self._next_seq()

        # running_count = global counter
        decision.running_count = self._next_running_count()

        # normalization_id = SHA-256 of canonically normalized payload
        decision.normalization_id = self._sha256(
            self._normalize_payload(payload)
        )

        # receipt_ref = SHA-256 chain linking to the previous decision
        previous_receipt_ref = self._get_last_receipt_ref()
        decision.receipt_ref = self._compute_receipt_ref(
            decision, previous_receipt_ref
        )

        # Store the new receipt_ref for the next decision in the chain
        self._set_last_receipt_ref(decision.receipt_ref)

        # governance_seal = HMAC-SHA256 of decision fields + timestamp + agent_id
        timestamp = int(time.time() * 1000)  # Unix milliseconds
        decision.governance_seal = {
            "hmac": self._compute_seal_hmac(decision, timestamp),
            "timestamp": timestamp,
            "agent_id": self._agent_id,
        }

    def _compute_receipt_ref(
        self, decision: StageDecision, previous_receipt_ref: str
    ) -> str:
        """Compute receipt_ref as SHA-256(intent_ref:previous_receipt_ref:seq).

        Creates a hash chain linking each decision to its predecessor.

        Args:
            decision: The decision whose receipt_ref is being computed.
            previous_receipt_ref: The receipt_ref of the preceding decision.

        Returns:
            Hex-encoded SHA-256 hash forming the receipt chain link.
        """
        chain_input = f"{decision.intent_ref}:{previous_receipt_ref}:{decision.seq}"
        return self._sha256(chain_input)

    def _compute_seal_hmac(self, decision: StageDecision, timestamp: int) -> str:
        """Compute the HMAC-SHA256 governance seal over decision key fields.

        The HMAC covers: action, stage, seq, intent_ref, receipt_ref,
        running_count, normalization_id, timestamp, agent_id.

        Args:
            decision: The decision to seal.
            timestamp: Unix milliseconds timestamp for the seal.

        Returns:
            Hex-encoded HMAC-SHA256 string.
        """
        seal_data = self._deterministic_serialize({
            "action": decision.action,
            "stage": decision.stage.value if isinstance(decision.stage, PipelineStage) else decision.stage,
            "seq": decision.seq,
            "intent_ref": decision.intent_ref,
            "receipt_ref": decision.receipt_ref,
            "running_count": decision.running_count,
            "normalization_id": decision.normalization_id,
            "timestamp": timestamp,
            "agent_id": self._agent_id,
        })
        return self._hmac_sha256(self._seal_secret, seal_data)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Counter management
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        """Get the next monotonically increasing sequence number for this agent.

        Returns:
            The next seq value (starts at 1).
        """
        current = self._seq_counters.get(self._agent_id, 0)
        next_val = current + 1
        self._seq_counters[self._agent_id] = next_val
        return next_val

    def _next_running_count(self) -> int:
        """Get the next global running count across all agents.

        Returns:
            The next running_count value (starts at 1).
        """
        self._running_count += 1
        return self._running_count

    def _get_last_receipt_ref(self) -> str:
        """Get the last receipt_ref for this agent.

        Returns GENESIS_RECEIPT_REF if no prior decision exists.

        Returns:
            The last receipt_ref for the current agent.
        """
        return self._last_receipt_refs.get(self._agent_id, GENESIS_RECEIPT_REF)

    def _set_last_receipt_ref(self, receipt_ref: str) -> None:
        """Store the latest receipt_ref for this agent.

        Args:
            receipt_ref: The receipt_ref to store.
        """
        self._last_receipt_refs[self._agent_id] = receipt_ref

    # ------------------------------------------------------------------
    # Cryptographic utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _sha256(data: str) -> str:
        """Compute SHA-256 hash of a string.

        Args:
            data: The input string to hash.

        Returns:
            Hex-encoded SHA-256 hash (64 characters).
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def _hmac_sha256(key: str, message: str) -> str:
        """Compute HMAC-SHA256 of a message with the given key.

        Args:
            key: The HMAC secret key.
            message: The message to authenticate.

        Returns:
            Hex-encoded HMAC-SHA256 string (64 characters).
        """
        return hmac.new(
            key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _deterministic_serialize(obj: Any) -> str:
        """Deterministically serialize an object to JSON.

        Uses sorted keys and compact separators to ensure identical
        serialization across invocations and platforms.

        Args:
            obj: The object to serialize.

        Returns:
            A deterministic JSON string.
        """
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _normalize_payload(payload: Dict[str, Any]) -> str:
        """Canonically normalize a payload for normalization_id computation.

        Uses the same deterministic serialization as intent_ref computation.
        This provides a canonical form for payload comparison.

        Args:
            payload: The payload dict to normalize.

        Returns:
            The canonically normalized payload as a JSON string.
        """
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
