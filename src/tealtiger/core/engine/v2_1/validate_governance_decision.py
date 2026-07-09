"""TEEC v2.1 Governance Contract — validate_governance_decision (Python SDK).

Validates a single governance decision for schema correctness,
cryptographic seal integrity, intent binding, and timestamp freshness.

The function accepts any decision object (DecisionV21 dataclass or dict)
and verifies:
1. Schema — all six v2.1 fields present and correctly typed
2. Timestamp drift — seal timestamp within acceptable window
3. Intent ref — SHA-256 of request payload matches stored intent_ref
4. Seal — HMAC recomputation matches stored governance_seal.hmac

Module: core/engine/v2_1/validate_governance_decision
Requirements: 7.3, 7.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Union

from .crypto_service import CryptoService
from .types import ValidationContext, ValidationFailure, ValidationSuccess


# v2.1 required fields and their expected types
_V21_REQUIRED_FIELDS = {
    "intent_ref": str,
    "receipt_ref": str,
    "seq": int,
    "running_count": int,
    "normalization_id": str,
    "governance_seal": dict,  # Will be dict after conversion
}

# v1.2 indicator fields — if these exist but v2.1 fields are missing,
# the decision is likely a v1.2 decision.
_V12_INDICATOR_FIELDS = {"action", "reason_codes", "risk_score", "mode", "policy_id"}


def validate_governance_decision(
    decision: Any,
    context: ValidationContext,
) -> Union[ValidationSuccess, ValidationFailure]:
    """Validate a single governance decision for correctness and integrity.

    Performs four sequential checks:
    1. Schema validation — ensures all six v2.1 fields are present and typed
    2. Timestamp drift — seal timestamp within tolerance of reference time
    3. Intent ref verification — recomputes SHA-256 of request payload
    4. Seal verification — recomputes HMAC and compares to stored seal

    Args:
        decision: A DecisionV21 dataclass instance or a dict representation.
                  Accepts Any to allow schema validation to produce clear errors.
        context: ValidationContext with request_payload, seal_secret, and
                 optional reference_time and timestamp_tolerance_ms.

    Returns:
        ValidationSuccess if all checks pass, ValidationFailure otherwise.
    """
    # Convert decision to dict for uniform processing
    decision_dict = _to_dict(decision)

    # Resolve tolerance and reference time
    tolerance = context.timestamp_tolerance_ms if context.timestamp_tolerance_ms is not None else 60000
    ref_time = context.reference_time if context.reference_time is not None else int(time.time() * 1000)

    # ── 1. Schema check ────────────────────────────────────────────
    schema_error = _check_schema(decision_dict)
    if schema_error is not None:
        return schema_error

    # ── 2. Timestamp drift check ──────────────────────────────────
    seal = decision_dict["governance_seal"]
    seal_timestamp = seal["timestamp"]
    drift = abs(seal_timestamp - ref_time)
    if drift > tolerance:
        return ValidationFailure(
            error_type="timestamp_drift",
            message=(
                f"GovernanceSeal timestamp drift of {drift}ms exceeds "
                f"tolerance of {tolerance}ms"
            ),
        )

    # ── 3. Intent ref verification ────────────────────────────────
    serialized_payload = CryptoService.deterministic_serialize(context.request_payload)
    expected_intent_ref = CryptoService.sha256(serialized_payload)
    if expected_intent_ref != decision_dict["intent_ref"]:
        return ValidationFailure(
            error_type="intent_mismatch",
            message=(
                "Intent ref mismatch — the request payload does not match "
                "the intent_ref in the decision. Possible TOCTOU violation."
            ),
        )

    # ── 4. Seal verification ──────────────────────────────────────
    decision_for_seal = {k: v for k, v in decision_dict.items() if k != "governance_seal"}
    payload = CryptoService.deterministic_serialize(decision_for_seal)
    hmac_input = payload + str(seal["timestamp"]) + seal["agent_id"]
    expected_hmac = CryptoService.hmac_sha256(context.seal_secret, hmac_input)
    if expected_hmac != seal["hmac"]:
        return ValidationFailure(
            error_type="seal_mismatch",
            message=(
                "GovernanceSeal HMAC mismatch — the seal could not be verified. "
                "The decision may have been tampered with or the seal_secret is incorrect."
            ),
        )

    # ── All checks passed ─────────────────────────────────────────
    return ValidationSuccess(
        receipt_ref=decision_dict["receipt_ref"],
        intent_ref=decision_dict["intent_ref"],
    )


def _to_dict(decision: Any) -> dict:
    """Convert a decision to a plain dict.

    Handles DecisionV21 dataclass instances, dicts, and other objects.
    """
    if isinstance(decision, dict):
        return decision
    if dataclasses.is_dataclass(decision) and not isinstance(decision, type):
        return dataclasses.asdict(decision)
    # Fallback: try to convert via __dict__
    if hasattr(decision, "__dict__"):
        return dict(decision.__dict__)
    return {}


def _check_schema(decision_dict: dict) -> Union[ValidationFailure, None]:
    """Check that all six v2.1 fields are present and correctly typed.

    Returns a ValidationFailure if schema is invalid, None if valid.
    """
    # Check for governance_seal first (special handling for nested object)
    governance_seal = decision_dict.get("governance_seal")

    # Check all required v2.1 fields
    missing_fields = []
    type_errors = []

    for field_name, expected_type in _V21_REQUIRED_FIELDS.items():
        value = decision_dict.get(field_name)
        if value is None or (isinstance(value, str) and value == "" and field_name != "governance_seal"):
            # For string fields, empty string counts as missing for schema purposes
            # EXCEPT governance_seal which is checked differently
            if field_name in ("intent_ref", "receipt_ref", "normalization_id") and value == "":
                missing_fields.append(field_name)
            elif value is None:
                missing_fields.append(field_name)
        elif not isinstance(value, expected_type):
            type_errors.append(f"{field_name} (expected {expected_type.__name__}, got {type(value).__name__})")

    # Special check for governance_seal sub-fields
    if governance_seal is not None and isinstance(governance_seal, dict):
        seal_required = {"hmac": str, "timestamp": int, "agent_id": str}
        for seal_field, seal_type in seal_required.items():
            seal_value = governance_seal.get(seal_field)
            if seal_value is None:
                missing_fields.append(f"governance_seal.{seal_field}")
            elif not isinstance(seal_value, seal_type):
                type_errors.append(
                    f"governance_seal.{seal_field} (expected {seal_type.__name__}, "
                    f"got {type(seal_value).__name__})"
                )

    # Check seq and running_count are valid (non-zero positive integers)
    seq_val = decision_dict.get("seq")
    running_count_val = decision_dict.get("running_count")
    if isinstance(seq_val, int) and seq_val == 0:
        missing_fields.append("seq")
    if isinstance(running_count_val, int) and running_count_val == 0:
        missing_fields.append("running_count")

    if missing_fields or type_errors:
        # Determine if this looks like a v1.2 decision
        has_v12_fields = _V12_INDICATOR_FIELDS.issubset(decision_dict.keys())
        if has_v12_fields and governance_seal is None:
            return ValidationFailure(
                error_type="schema_violation",
                message=(
                    "Decision is TEEC v1.2 — use TEECValidator.validateDecision() "
                    "for v1.2 validation"
                ),
            )

        details = []
        if missing_fields:
            details.append(f"missing fields: {', '.join(missing_fields)}")
        if type_errors:
            details.append(f"type errors: {', '.join(type_errors)}")

        return ValidationFailure(
            error_type="schema_violation",
            message=f"Decision does not conform to TEEC v2.1 schema — {'; '.join(details)}",
        )

    return None
