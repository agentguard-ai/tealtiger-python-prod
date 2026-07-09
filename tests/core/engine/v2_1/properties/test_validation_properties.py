"""Property-based tests for validate_governance_decision (Python SDK).

Tests verify:
- Property 9: Tamper Detection — single-field mutations always detected
- Property 11: Backward Compatibility Preservation — v1.2 decisions gracefully rejected

**Validates: Requirements 6.2, 6.8, 9.1, 9.2**

Uses Hypothesis library for property-based testing.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from hypothesis import given, settings, HealthCheck, assume
import hypothesis.strategies as st

from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.validate_governance_decision import (
    validate_governance_decision,
)
from tealtiger.core.engine.v2_1.types import (
    ValidationContext,
    ValidationFailure,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Payload strategy: dict with simple lowercase alpha keys and mixed values
payload_strategy = st.dictionaries(
    keys=st.text(
        min_size=1,
        max_size=10,
        alphabet="abcdefghijklmnopqrstuvwxyz",
    ),
    values=st.one_of(
        st.text(min_size=1, max_size=50),
        st.integers(min_value=-1000, max_value=1000),
        st.booleans(),
    ),
    min_size=1,
    max_size=5,
)

# Tamperable fields in a decision (excluding governance_seal)
TAMPERABLE_FIELDS = [
    "action",
    "reason_codes",
    "risk_score",
    "seq",
    "running_count",
    "receipt_ref",
    "intent_ref",
    "normalization_id",
    "correlation_id",
    "reason",
    "mode",
]

tamperable_field_strategy = st.sampled_from(TAMPERABLE_FIELDS)


# ---------------------------------------------------------------------------
# Property 9: Tamper Detection
# For any valid Decision, modifying any field (other than governance_seal)
# and then calling validate_governance_decision() SHALL return valid: false
# with a 'seal_mismatch' or 'intent_mismatch' error.
#
# ∀ valid Decision D, ∀ field f ∈ D (f ≠ governance_seal):
#   D' = tamper(D, f)
#   validate_governance_decision(D', original_payload, K).valid === false
# ---------------------------------------------------------------------------


def _tamper_field(decision_dict: dict, field_name: str) -> dict:
    """Modify a single field in the decision dict to a different value."""
    tampered = dict(decision_dict)

    if field_name == "action":
        tampered["action"] = "DENY" if decision_dict["action"] != "DENY" else "BLOCK"
    elif field_name == "reason_codes":
        tampered["reason_codes"] = ["TAMPERED_CODE"]
    elif field_name == "risk_score":
        tampered["risk_score"] = decision_dict["risk_score"] + 42
    elif field_name == "seq":
        tampered["seq"] = decision_dict["seq"] + 1
    elif field_name == "running_count":
        tampered["running_count"] = decision_dict["running_count"] + 1
    elif field_name == "receipt_ref":
        tampered["receipt_ref"] = "a" * 64
    elif field_name == "intent_ref":
        tampered["intent_ref"] = "b" * 64
    elif field_name == "normalization_id":
        tampered["normalization_id"] = "c" * 64
    elif field_name == "correlation_id":
        tampered["correlation_id"] = "tampered-correlation-id"
    elif field_name == "reason":
        tampered["reason"] = "tampered reason string"
    elif field_name == "mode":
        tampered["mode"] = "MONITOR" if decision_dict["mode"] != "MONITOR" else "REPORT_ONLY"

    return tampered


class TestTamperDetection:
    """Property 9: Tamper Detection.

    Verifies that for any valid decision produced by GovernanceEngineV21,
    modifying any single field (other than governance_seal) causes
    validate_governance_decision to return a validation failure.

    **Validates: Requirements 6.2, 6.8**
    """

    @given(
        payload=payload_strategy,
        field_to_tamper=tamperable_field_strategy,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_single_field_tamper_detected(
        self, payload: dict, field_to_tamper: str
    ) -> None:
        """Single-field mutations are always detected by validate_governance_decision."""

        async def _run():
            seal_secret = "tamper-test-secret"
            engine = GovernanceEngineV21(
                GovernanceEngineV21Options(seal_secret=seal_secret)
            )
            ctx = {"correlation_id": "corr-1"}

            # Produce a valid decision
            decision = await engine.evaluate(payload, ctx)

            # Convert to dict for tampering
            decision_dict = asdict(decision)

            # Tamper with a single field
            tampered_dict = _tamper_field(decision_dict, field_to_tamper)

            # Ensure the tampered value is actually different
            assume(tampered_dict[field_to_tamper] != decision_dict[field_to_tamper])

            # Validate the tampered decision — should fail
            context = ValidationContext(
                request_payload=payload,
                seal_secret=seal_secret,
                reference_time=decision.governance_seal.timestamp,
                timestamp_tolerance_ms=60000,
            )
            result = validate_governance_decision(tampered_dict, context)

            assert isinstance(result, ValidationFailure)
            assert result.valid is False
            assert result.error_type in ("seal_mismatch", "intent_mismatch")

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Property 11: Backward Compatibility Preservation
# For any v1.2-like decision dict (with v1.2 fields but without v2.1 fields),
# calling validate_governance_decision SHALL return a ValidationFailure with
# error_type='schema_violation' and a message containing "TEEC v1.2".
# This proves v1.2 decisions are gracefully rejected with helpful guidance.
#
# ∀ D where D is a valid v1.2 Decision (no v2.1 fields):
#   validate_governance_decision(D).error_type === 'schema_violation'
#   "v1.2" in validate_governance_decision(D).message
# ---------------------------------------------------------------------------

# Strategy for v1.2-like decision dicts
v12_action_strategy = st.sampled_from(["ALLOW", "DENY", "MONITOR", "BLOCK"])
v12_mode_strategy = st.sampled_from(["ENFORCE", "MONITOR", "REPORT_ONLY"])

v12_decision_strategy = st.fixed_dictionaries(
    {
        "action": v12_action_strategy,
        "reason_codes": st.lists(
            st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_"),
            min_size=1,
            max_size=3,
        ),
        "risk_score": st.integers(min_value=0, max_value=100),
        "mode": v12_mode_strategy,
        "policy_id": st.text(min_size=1, max_size=30),
        "policy_version": st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
        "correlation_id": st.text(min_size=1, max_size=40),
        "reason": st.text(min_size=1, max_size=100),
        "event_type": st.text(min_size=1, max_size=30),
        "timestamp": st.integers(min_value=1000000000000, max_value=2000000000000),
        "module": st.text(min_size=1, max_size=30),
    },
)


class TestBackwardCompatibilityPreservation:
    """Property 11: Backward Compatibility Preservation.

    Verifies that v1.2-like decisions (with standard v1.2 fields but without
    v2.1 cryptographic fields) are gracefully rejected by
    validate_governance_decision with a schema_violation error type and a
    helpful message mentioning "TEEC v1.2".

    **Validates: Requirements 9.1, 9.2**
    """

    @given(decision=v12_decision_strategy)
    @settings(max_examples=50, deadline=None)
    def test_v12_decisions_rejected_with_helpful_guidance(
        self, decision: dict
    ) -> None:
        """v1.2 decisions receive schema_violation with message mentioning TEEC v1.2."""

        # v1.2 decisions don't have v2.1 fields — validate_governance_decision
        # should detect this and return a helpful error
        context = ValidationContext(
            request_payload={"some": "payload"},
            seal_secret="any-secret",
            reference_time=decision["timestamp"],
            timestamp_tolerance_ms=120000,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.valid is False
        assert result.error_type == "schema_violation"
        # The error message should mention v1.2 to guide the user
        assert "v1.2" in result.message
