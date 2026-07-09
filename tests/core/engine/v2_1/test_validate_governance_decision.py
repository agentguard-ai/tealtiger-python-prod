"""Unit tests for validate_governance_decision (Python SDK).

Tests the validation function against:
- Valid v2.1 decisions (produced by GovernanceEngineV21)
- Schema violations (missing/maltyped v2.1 fields)
- v1.2 decisions (helpful error message)
- Timestamp drift detection
- Intent ref mismatch (TOCTOU detection)
- Seal mismatch (tamper detection)

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.3, 7.5, 9.3, 9.7
"""

from __future__ import annotations

import time
from dataclasses import asdict

import pytest

from tealtiger.core.engine.v2_1.crypto_service import CryptoService
from tealtiger.core.engine.v2_1.governance_engine import (
    GovernanceEngineV21,
    GovernanceEngineV21Options,
)
from tealtiger.core.engine.v2_1.types import (
    DecisionV21,
    GovernanceSeal,
    ValidationContext,
    ValidationFailure,
    ValidationSuccess,
)
from tealtiger.core.engine.v2_1.validate_governance_decision import (
    validate_governance_decision,
)


# ── Helpers ────────────────────────────────────────────────────────


SEAL_SECRET = "test-secret-key-for-validation"
AGENT_ID = "agent-validator"


@pytest.fixture
def request_payload():
    """Standard request payload for testing."""
    return {"action": "tool.execute", "tool": "read_file", "args": {"path": "/tmp/test"}}


@pytest.fixture
def engine():
    """GovernanceEngineV21 configured for testing."""
    opts = GovernanceEngineV21Options(
        seal_secret=SEAL_SECRET,
        agent_id=AGENT_ID,
    )
    return GovernanceEngineV21(opts)


@pytest.fixture
async def valid_decision(engine, request_payload):
    """A valid v2.1 decision produced by the engine."""
    ctx = {"correlation_id": "test-corr-001"}
    return await engine.evaluate(request_payload, ctx)


@pytest.fixture
def validation_context(request_payload, valid_decision):
    """Validation context with correct secret and matching payload."""
    return ValidationContext(
        request_payload=request_payload,
        seal_secret=SEAL_SECRET,
        reference_time=valid_decision.governance_seal.timestamp,
        timestamp_tolerance_ms=60000,
    )


# ── Success Cases ──────────────────────────────────────────────────


class TestValidationSuccess:
    """Test that valid decisions pass validation."""

    @pytest.mark.asyncio
    async def test_valid_decision_passes(self, valid_decision, validation_context):
        """A freshly produced v2.1 decision should pass validation."""
        result = validate_governance_decision(valid_decision, validation_context)

        assert isinstance(result, ValidationSuccess)
        assert result.valid is True
        assert result.receipt_ref == valid_decision.receipt_ref
        assert result.intent_ref == valid_decision.intent_ref

    @pytest.mark.asyncio
    async def test_valid_decision_as_dict_passes(self, valid_decision, validation_context):
        """Validation also works when decision is passed as a plain dict."""
        decision_dict = asdict(valid_decision)
        result = validate_governance_decision(decision_dict, validation_context)

        assert isinstance(result, ValidationSuccess)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_decision_with_default_tolerance(
        self, engine, request_payload
    ):
        """Validation passes with default tolerance when decision is fresh."""
        ctx = {"correlation_id": "c1"}
        decision = await engine.evaluate(request_payload, ctx)

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationSuccess)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_multiple_decisions_each_pass(self, engine, request_payload):
        """Multiple sequentially produced decisions each pass validation independently."""
        ctx = {"correlation_id": "c1"}
        decisions = []
        for _ in range(3):
            d = await engine.evaluate(request_payload, ctx)
            decisions.append(d)

        for d in decisions:
            context = ValidationContext(
                request_payload=request_payload,
                seal_secret=SEAL_SECRET,
                reference_time=d.governance_seal.timestamp,
            )
            result = validate_governance_decision(d, context)
            assert isinstance(result, ValidationSuccess)


# ── Schema Violation Cases ─────────────────────────────────────────


class TestSchemaViolation:
    """Test schema validation catches missing or maltyped v2.1 fields."""

    def test_v12_decision_returns_schema_violation_with_helpful_message(
        self, request_payload
    ):
        """A v1.2 decision (no v2.1 fields) gets a clear error message."""
        v12_decision = {
            "action": "ALLOW",
            "reason_codes": ["POLICY_COMPLIANT"],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "v1.2-governance",
            "policy_version": "1.2.0",
            "correlation_id": "test",
            "reason": "Allowed",
            "event_type": "policy.evaluation",
            "timestamp": int(time.time() * 1000),
            "module": "TealEngineV12",
        }

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision(v12_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.valid is False
        assert result.error_type == "schema_violation"
        assert "TEEC v1.2" in result.message
        assert "TEECValidator.validateDecision()" in result.message

    def test_missing_governance_seal_returns_schema_violation(self, request_payload):
        """Decision with v2.1 fields but missing governance_seal fails."""
        decision = {
            "action": "ALLOW",
            "reason_codes": ["POLICY_COMPLIANT"],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "v1.2-governance",
            "intent_ref": "a" * 64,
            "receipt_ref": "b" * 64,
            "seq": 1,
            "running_count": 1,
            "normalization_id": "c" * 64,
            "governance_seal": None,
        }

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "schema_violation"

    def test_missing_intent_ref_returns_schema_violation(self, request_payload):
        """Decision missing intent_ref fails schema validation."""
        decision = {
            "action": "ALLOW",
            "reason_codes": [],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "test",
            "intent_ref": "",
            "receipt_ref": "b" * 64,
            "seq": 1,
            "running_count": 1,
            "normalization_id": "c" * 64,
            "governance_seal": {"hmac": "d" * 64, "timestamp": 1000, "agent_id": "a"},
        }

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "schema_violation"

    def test_wrong_type_seq_returns_schema_violation(self, request_payload):
        """Decision with wrong type for seq fails schema validation."""
        decision = {
            "action": "ALLOW",
            "reason_codes": [],
            "risk_score": 0,
            "mode": "ENFORCE",
            "policy_id": "test",
            "intent_ref": "a" * 64,
            "receipt_ref": "b" * 64,
            "seq": "not-an-int",
            "running_count": 1,
            "normalization_id": "c" * 64,
            "governance_seal": {"hmac": "d" * 64, "timestamp": 1000, "agent_id": "a"},
        }

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "schema_violation"

    def test_empty_dict_returns_schema_violation(self, request_payload):
        """An empty dict fails schema validation."""
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
        )
        result = validate_governance_decision({}, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "schema_violation"


# ── Timestamp Drift Cases ──────────────────────────────────────────


class TestTimestampDrift:
    """Test timestamp drift detection."""

    @pytest.mark.asyncio
    async def test_expired_timestamp_returns_drift_error(
        self, valid_decision, request_payload
    ):
        """Seal timestamp far in the past fails drift check."""
        # Set reference_time far in the future (>60s after seal timestamp)
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp + 120000,
            timestamp_tolerance_ms=60000,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "timestamp_drift"
        assert "drift" in result.message.lower()

    @pytest.mark.asyncio
    async def test_future_timestamp_returns_drift_error(
        self, valid_decision, request_payload
    ):
        """Seal timestamp far in the future fails drift check."""
        # Set reference_time far in the past (>60s before seal timestamp)
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp - 120000,
            timestamp_tolerance_ms=60000,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "timestamp_drift"

    @pytest.mark.asyncio
    async def test_custom_tolerance_allows_larger_drift(
        self, valid_decision, request_payload
    ):
        """Custom tolerance_ms can allow larger drift windows."""
        # Set reference 90s away, but tolerance is 120s
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp + 90000,
            timestamp_tolerance_ms=120000,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationSuccess)

    @pytest.mark.asyncio
    async def test_exact_boundary_passes(self, valid_decision, request_payload):
        """Drift exactly at the tolerance boundary passes."""
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp + 60000,
            timestamp_tolerance_ms=60000,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationSuccess)

    @pytest.mark.asyncio
    async def test_one_over_boundary_fails(self, valid_decision, request_payload):
        """Drift one ms over the tolerance boundary fails."""
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp + 60001,
            timestamp_tolerance_ms=60000,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "timestamp_drift"


# ── Intent Mismatch Cases ──────────────────────────────────────────


class TestIntentMismatch:
    """Test intent_ref verification catches payload differences."""

    @pytest.mark.asyncio
    async def test_different_payload_returns_intent_mismatch(
        self, valid_decision
    ):
        """A different request payload causes intent_mismatch."""
        wrong_payload = {"action": "DIFFERENT", "modified": True}
        context = ValidationContext(
            request_payload=wrong_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "intent_mismatch"
        assert "TOCTOU" in result.message

    @pytest.mark.asyncio
    async def test_slightly_modified_payload_returns_intent_mismatch(
        self, valid_decision, request_payload
    ):
        """Even a small modification to the payload is detected."""
        modified_payload = dict(request_payload)
        modified_payload["extra_field"] = "injected"

        context = ValidationContext(
            request_payload=modified_payload,
            seal_secret=SEAL_SECRET,
            reference_time=valid_decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "intent_mismatch"


# ── Seal Mismatch Cases ────────────────────────────────────────────


class TestSealMismatch:
    """Test seal verification catches tampered decisions."""

    @pytest.mark.asyncio
    async def test_wrong_seal_secret_returns_seal_mismatch(
        self, valid_decision, request_payload
    ):
        """Validation with wrong seal_secret fails with seal_mismatch."""
        context = ValidationContext(
            request_payload=request_payload,
            seal_secret="wrong-secret-key",
            reference_time=valid_decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(valid_decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "seal_mismatch"

    @pytest.mark.asyncio
    async def test_tampered_action_field_returns_seal_mismatch(
        self, valid_decision, request_payload
    ):
        """Modifying action field after production causes seal_mismatch."""
        decision_dict = asdict(valid_decision)
        decision_dict["action"] = "DENY"

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision_dict["governance_seal"]["timestamp"],
        )
        result = validate_governance_decision(decision_dict, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "seal_mismatch"

    @pytest.mark.asyncio
    async def test_tampered_seq_returns_seal_mismatch(
        self, valid_decision, request_payload
    ):
        """Modifying seq after production causes seal_mismatch."""
        decision_dict = asdict(valid_decision)
        decision_dict["seq"] = 999

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision_dict["governance_seal"]["timestamp"],
        )
        result = validate_governance_decision(decision_dict, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "seal_mismatch"

    @pytest.mark.asyncio
    async def test_tampered_receipt_ref_returns_seal_mismatch(
        self, valid_decision, request_payload
    ):
        """Modifying receipt_ref after production causes seal_mismatch."""
        decision_dict = asdict(valid_decision)
        decision_dict["receipt_ref"] = "f" * 64

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision_dict["governance_seal"]["timestamp"],
        )
        result = validate_governance_decision(decision_dict, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "seal_mismatch"

    @pytest.mark.asyncio
    async def test_tampered_hmac_returns_seal_mismatch(
        self, valid_decision, request_payload
    ):
        """Directly modifying the HMAC value causes seal_mismatch."""
        decision_dict = asdict(valid_decision)
        decision_dict["governance_seal"]["hmac"] = "0" * 64

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision_dict["governance_seal"]["timestamp"],
        )
        result = validate_governance_decision(decision_dict, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "seal_mismatch"


# ── Edge Cases ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_payload_decision_validates(self, engine):
        """A decision produced from an empty payload validates correctly."""
        empty_payload = {}
        ctx = {"correlation_id": "c1"}
        decision = await engine.evaluate(empty_payload, ctx)

        context = ValidationContext(
            request_payload=empty_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationSuccess)

    @pytest.mark.asyncio
    async def test_nested_payload_decision_validates(self, engine):
        """A decision produced from a deeply nested payload validates."""
        nested_payload = {
            "level1": {
                "level2": {
                    "level3": {"data": "deep-value", "numbers": [1, 2, 3]}
                }
            }
        }
        ctx = {"correlation_id": "c1"}
        decision = await engine.evaluate(nested_payload, ctx)

        context = ValidationContext(
            request_payload=nested_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationSuccess)

    @pytest.mark.asyncio
    async def test_unicode_payload_decision_validates(self, engine):
        """A decision produced from a unicode payload validates."""
        unicode_payload = {"message": "Héllo wörld! 你好世界 🌍", "data": "café"}
        ctx = {"correlation_id": "c1"}
        decision = await engine.evaluate(unicode_payload, ctx)

        context = ValidationContext(
            request_payload=unicode_payload,
            seal_secret=SEAL_SECRET,
            reference_time=decision.governance_seal.timestamp,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationSuccess)

    def test_zero_tolerance_rejects_any_drift(self, request_payload):
        """With tolerance=0, even 1ms drift is rejected."""
        # Create a minimal valid decision for this test
        seal_ts = 1000000000000
        decision = _make_valid_decision(request_payload, SEAL_SECRET, "agent-1", seal_ts)

        context = ValidationContext(
            request_payload=request_payload,
            seal_secret=SEAL_SECRET,
            reference_time=seal_ts + 1,
            timestamp_tolerance_ms=0,
        )
        result = validate_governance_decision(decision, context)

        assert isinstance(result, ValidationFailure)
        assert result.error_type == "timestamp_drift"


# ── Helper to build a valid decision manually ─────────────────────


def _make_valid_decision(
    request_payload: dict,
    seal_secret: str,
    agent_id: str,
    seal_timestamp: int,
) -> dict:
    """Build a valid v2.1 decision dict for testing purposes."""
    serialized = CryptoService.deterministic_serialize(request_payload)
    intent_ref = CryptoService.sha256(serialized)
    normalized = CryptoService.normalize_payload(request_payload)
    normalization_id = CryptoService.sha256(normalized)

    decision_without_seal = {
        "action": "ALLOW",
        "reason_codes": ["POLICY_COMPLIANT"],
        "risk_score": 0,
        "mode": "ENFORCE",
        "policy_id": "v1.2-governance",
        "policy_version": "1.2.0",
        "component_versions": {},
        "correlation_id": "test-corr",
        "reason": "Request allowed — all governance checks passed",
        "event_type": "policy.evaluation",
        "timestamp": seal_timestamp,
        "module": "GovernanceEngineV21",
        "metadata": {},
        "trace_id": None,
        "workflow_id": None,
        "run_id": None,
        "span_id": None,
        "parent_span_id": None,
        "provider": None,
        "registry_refs": None,
        "findings": None,
        "intent_ref": intent_ref,
        "receipt_ref": "a" * 64,  # Placeholder
        "seq": 1,
        "running_count": 1,
        "normalization_id": normalization_id,
        "teec_version": "2.1",
    }

    # Compute receipt_ref properly
    from tealtiger.core.engine.v2_1.types import GENESIS_RECEIPT_REF

    receipt_dict = dict(decision_without_seal)
    receipt_dict.pop("receipt_ref", None)
    receipt_payload = CryptoService.deterministic_serialize(receipt_dict)
    receipt_ref = CryptoService.sha256(receipt_payload + GENESIS_RECEIPT_REF)
    decision_without_seal["receipt_ref"] = receipt_ref

    # Compute seal
    payload = CryptoService.deterministic_serialize(decision_without_seal)
    hmac_input = payload + str(seal_timestamp) + agent_id
    hmac_value = CryptoService.hmac_sha256(seal_secret, hmac_input)

    decision_without_seal["governance_seal"] = {
        "hmac": hmac_value,
        "timestamp": seal_timestamp,
        "agent_id": agent_id,
    }

    return decision_without_seal
