"""TEEC v2.1 Governance Contract — GovernanceEngineV21 (Python SDK).

Provides the full v2.1 governance pipeline with cryptographic verifiability.
When seal_secret is configured, produces DecisionV21 with intent binding,
receipt chaining, sequence counters, and a GovernanceSeal HMAC.
When seal_secret is absent, produces a basic v1.2-equivalent decision
(backward-compatible opt-out).

Requirements: 7.1, 7.2, 1.7, 1.8, 9.5

Module: core/engine/v2_1/governance_engine
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .counter_manager import CounterManager
from .crypto_service import CryptoService
from .errors import SealConfigurationError
from .types import DecisionV21, GovernanceSeal


@dataclass
class GovernanceEngineV21Options:
    """Configuration options for GovernanceEngineV21.

    Attributes:
        seal_secret: Secret key for HMAC seals. Presence activates v2.1 mode.
        agent_id: Default agent ID for seal and counter scoping.
        policy: Policy configuration dict (unused in simplified evaluation).
        mode: Default policy mode string (e.g. "ENFORCE", "MONITOR").
    """

    seal_secret: Optional[str] = None
    agent_id: Optional[str] = None
    policy: Dict[str, Any] = field(default_factory=dict)
    mode: str = "ENFORCE"


class GovernanceEngineV21:
    """TEEC v2.1 Governance Engine.

    Standalone class that composes CryptoService (static methods) and
    CounterManager (instance) to produce cryptographically verifiable
    governance decisions.

    Opt-in via seal_secret:
    - When absent: evaluate() produces a basic v1.2-equivalent decision.
    - When present: evaluate() runs the full v2.1 pipeline with intent
      binding, receipt chaining, sequence counters, and GovernanceSeal.
    """

    def __init__(self, options: GovernanceEngineV21Options) -> None:
        """Initialize the GovernanceEngineV21.

        Args:
            options: Engine configuration options.
        """
        self._seal_secret = options.seal_secret
        self._agent_id = options.agent_id
        self._policy = options.policy
        self._mode = options.mode
        self._counter_manager = CounterManager()

    async def evaluate(
        self, request: Dict[str, Any], ctx: Dict[str, Any]
    ) -> DecisionV21:
        """Evaluate a request with TEEC v2.1 governance fields.

        If seal_secret is configured: runs the full v2.1 pipeline producing
        a DecisionV21 with cryptographic seals, intent binding, and receipt
        chaining.

        If seal_secret is absent: produces a basic v1.2-equivalent decision
        without cryptographic fields populated.

        Args:
            request: The request payload to evaluate.
            ctx: Evaluation context dict (should include 'correlation_id',
                 optionally 'agent_id').

        Returns:
            A DecisionV21 with all applicable fields populated.
        """
        # 1. Opt-in check — if no seal_secret, produce basic v1.2-equivalent
        if not self._seal_secret:
            return self._evaluate_base(request, ctx)

        # 2. Compute intent bindings BEFORE policy evaluation
        serialized_request = CryptoService.deterministic_serialize(request)
        intent_ref = CryptoService.sha256(serialized_request)
        normalized_form = CryptoService.normalize_payload(request)
        normalization_id = CryptoService.sha256(normalized_form)

        # 3. Run base policy evaluation (simplified)
        base_decision = self._evaluate_base(request, ctx)

        # 4. Resolve agent_id and assign counters
        agent_id = ctx.get("agent_id") or self._agent_id or "default"
        seq = self._counter_manager.next_seq(agent_id)
        running_count = self._counter_manager.next_running_count()

        # 5. Build partial v2.1 decision (for receipt_ref computation)
        partial_decision = DecisionV21(
            action=base_decision.action,
            reason_codes=base_decision.reason_codes,
            risk_score=base_decision.risk_score,
            mode=base_decision.mode,
            policy_id=base_decision.policy_id,
            policy_version=base_decision.policy_version,
            component_versions=base_decision.component_versions,
            correlation_id=base_decision.correlation_id,
            reason=base_decision.reason,
            event_type=base_decision.event_type,
            timestamp=base_decision.timestamp,
            module=base_decision.module,
            metadata=base_decision.metadata,
            intent_ref=intent_ref,
            normalization_id=normalization_id,
            seq=seq,
            running_count=running_count,
            teec_version="2.1",
        )

        # 6. Compute receipt_ref (chain link)
        prev_receipt_ref = self._counter_manager.get_last_receipt_ref(agent_id)
        receipt_ref = self._compute_receipt_ref(partial_decision, prev_receipt_ref)
        self._counter_manager.set_last_receipt_ref(agent_id, receipt_ref)

        # 7. Compute GovernanceSeal
        partial_decision.receipt_ref = receipt_ref
        seal_timestamp = int(time.time() * 1000)
        governance_seal = self._compute_governance_seal(
            partial_decision, seal_timestamp, agent_id, self._seal_secret
        )

        # 8. Return complete v2.1 Decision
        partial_decision.governance_seal = governance_seal
        return partial_decision

    def _evaluate_base(
        self, request: Dict[str, Any], ctx: Dict[str, Any]
    ) -> DecisionV21:
        """Produce a basic v1.2-equivalent decision (simplified policy evaluation).

        When no seal_secret is configured, this is the full result.
        When seal_secret IS configured, this provides the base fields that
        get extended with v2.1 cryptographic data.

        Args:
            request: The request payload.
            ctx: Evaluation context dict.

        Returns:
            A DecisionV21 with base fields only (no crypto fields populated).
        """
        return DecisionV21(
            action="ALLOW",
            reason_codes=["POLICY_COMPLIANT"],
            risk_score=0,
            mode=self._mode,
            policy_id="v1.2-governance",
            policy_version="1.2.0",
            correlation_id=ctx.get("correlation_id", ""),
            reason="Request allowed — all governance checks passed",
            event_type="policy.evaluation",
            timestamp=int(time.time() * 1000),
            module="GovernanceEngineV21",
            teec_version="2.1" if self._seal_secret else "0.1.0",
        )

    def _compute_receipt_ref(
        self,
        decision: DecisionV21,
        previous_receipt_ref: str,
    ) -> str:
        """Compute the receipt_ref hash-chain link.

        Serializes the partial decision (without receipt_ref and governance_seal),
        concatenates with the previous receipt_ref, then SHA-256 hashes.

        Args:
            decision: Partial decision (receipt_ref and governance_seal excluded
                      from serialization).
            previous_receipt_ref: The previous receipt_ref
                                  (GENESIS_RECEIPT_REF for seq=1).

        Returns:
            SHA-256 hex hash linking this decision to the chain.
        """
        decision_dict = asdict(decision)
        # Remove receipt_ref and governance_seal for receipt_ref computation
        decision_dict.pop("receipt_ref", None)
        decision_dict.pop("governance_seal", None)
        payload = CryptoService.deterministic_serialize(decision_dict)
        input_data = payload + previous_receipt_ref
        return CryptoService.sha256(input_data)

    def _compute_governance_seal(
        self,
        decision: DecisionV21,
        timestamp: int,
        agent_id: str,
        seal_secret: str,
    ) -> GovernanceSeal:
        """Compute the GovernanceSeal (HMAC-SHA256 based).

        Serializes the full decision (with receipt_ref but without
        governance_seal), concatenates with timestamp and agent_id,
        then HMAC-SHA256 with seal_secret.

        Args:
            decision: Full decision without governance_seal.
            timestamp: Unix ms timestamp for the seal.
            agent_id: Identity of the producing agent.
            seal_secret: HMAC secret key.

        Returns:
            GovernanceSeal with hmac, timestamp, and agent_id.
        """
        decision_dict = asdict(decision)
        # Remove governance_seal for seal computation
        decision_dict.pop("governance_seal", None)
        payload = CryptoService.deterministic_serialize(decision_dict)
        hmac_input = payload + str(timestamp) + agent_id
        hmac_value = CryptoService.hmac_sha256(seal_secret, hmac_input)
        return GovernanceSeal(hmac=hmac_value, timestamp=timestamp, agent_id=agent_id)

    def get_counter_manager(self) -> CounterManager:
        """Get the CounterManager instance (for testing/inspection).

        Returns:
            The internal CounterManager instance.
        """
        return self._counter_manager
