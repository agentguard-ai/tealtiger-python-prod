"""TEEC v2.1 Governance Contract — verify_contiguity (Python SDK).

Verifies that a sequence of governance decisions forms a valid,
tamper-evident chain with no gaps, reorderings, or modifications.

The function checks:
1. Version compatibility — all decisions have TEEC v2.1 fields (seq, receipt_ref)
2. Sequence continuity — seq values increment by exactly 1 with no gaps
3. Running count monotonicity — running_count is strictly increasing
4. Receipt chain integrity — each decision's receipt_ref chains to the prior

Module: core/engine/v2_1/verify_contiguity
Requirements: 7.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import dataclasses
from typing import Any, List, Optional, Union

from .crypto_service import CryptoService
from .types import ContiguityFailure, ContiguitySuccess


def verify_contiguity(
    decisions: List[Any],
    *,
    agent_id: Optional[str] = None,
) -> Union[ContiguitySuccess, ContiguityFailure]:
    """Verify that a sequence of governance decisions is contiguous.

    Performs four sequential checks on the filtered decision list:
    1. Version compatibility — each decision has seq and receipt_ref fields
    2. Sequence gap detection — seq values form a gap-free sequence
    3. Running count monotonicity — running_count is strictly increasing
    4. Receipt chain integrity — receipt_ref hash-chains are self-consistent

    Args:
        decisions: A list of DecisionV21 dataclass instances or dicts.
                   Accepts List[Any] to allow version checking to produce
                   clear errors for non-v2.1 decisions.
        agent_id: Optional filter — when provided, only decisions from
                  this agent_id are verified. Decisions are filtered by
                  governance_seal.agent_id.

    Returns:
        ContiguitySuccess if the chain is valid, ContiguityFailure otherwise.
    """
    # Convert all decisions to dicts for uniform processing
    decision_dicts = [_to_dict(d) for d in decisions]

    # Filter by agent_id if provided
    if agent_id is not None:
        filtered = [
            d for d in decision_dicts
            if _get_agent_id(d) == agent_id
        ]
    else:
        filtered = decision_dicts

    # Trivially contiguous: 0 or 1 decisions
    if len(filtered) <= 1:
        return ContiguitySuccess(count=len(filtered))

    # ── 1. Version compatibility check ────────────────────────────
    for i, d in enumerate(filtered):
        if not _has_v21_fields(d):
            return ContiguityFailure(
                index=i,
                check="version_incompatible",
                message=f"Decision at index {i} lacks TEEC v2.1 fields",
            )

    # ── 2–4. Sequential verification ─────────────────────────────
    for i in range(1, len(filtered)):
        prev = filtered[i - 1]
        curr = filtered[i]

        # Check seq gap
        expected_seq = prev["seq"] + 1
        if curr["seq"] != expected_seq:
            return ContiguityFailure(
                index=i,
                check="seq_gap",
                message=f"Expected seq {expected_seq}, got {curr['seq']}",
            )

        # Check running_count monotonicity
        if curr["running_count"] <= prev["running_count"]:
            return ContiguityFailure(
                index=i,
                check="count_regression",
                message="running_count must be strictly increasing",
            )

        # Check receipt chain integrity
        curr_for_receipt = {
            k: v for k, v in curr.items()
            if k not in ("receipt_ref", "governance_seal")
        }
        payload = CryptoService.deterministic_serialize(curr_for_receipt)
        expected_receipt_ref = CryptoService.sha256(payload + prev["receipt_ref"])
        if expected_receipt_ref != curr["receipt_ref"]:
            return ContiguityFailure(
                index=i,
                check="chain_break",
                message=f"receipt_ref chain verification failed at index {i}",
            )

    return ContiguitySuccess(count=len(filtered))


def _to_dict(decision: Any) -> dict:
    """Convert a decision to a plain dict.

    Handles DecisionV21 dataclass instances, dicts, and other objects.
    """
    if isinstance(decision, dict):
        return decision
    if dataclasses.is_dataclass(decision) and not isinstance(decision, type):
        return dataclasses.asdict(decision)
    if hasattr(decision, "__dict__"):
        return dict(decision.__dict__)
    return {}


def _get_agent_id(decision_dict: dict) -> Optional[str]:
    """Extract agent_id from a decision dict's governance_seal."""
    seal = decision_dict.get("governance_seal")
    if seal is None:
        return None
    if isinstance(seal, dict):
        return seal.get("agent_id")
    # Handle case where seal is still a dataclass (shouldn't happen after _to_dict)
    return getattr(seal, "agent_id", None)


def _has_v21_fields(decision_dict: dict) -> bool:
    """Check that a decision dict has the required TEEC v2.1 fields.

    A decision is considered version-incompatible if:
    - seq is missing, None, or zero
    - receipt_ref is missing, None, or empty string
    """
    seq = decision_dict.get("seq")
    receipt_ref = decision_dict.get("receipt_ref")

    # seq must be a positive integer
    if seq is None or not isinstance(seq, int) or seq == 0:
        return False

    # receipt_ref must be a non-empty string
    if receipt_ref is None or not isinstance(receipt_ref, str) or receipt_ref == "":
        return False

    return True
