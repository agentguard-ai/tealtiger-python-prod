"""Cross-agent policy federation protocol.

This module provides signed, transport-agnostic policy tokens and deterministic
most-restrictive-wins policy merging for parent/child agent systems.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from tealtiger.core.context import ContextManager, ExecutionContext, ExecutionContextOptions

TOKEN_PREFIX = "ttfp.v1"
CLASSIFICATION_RANKS = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


@dataclass(frozen=True)
class PolicyFederationVerificationResult:
    """Result returned after policy token verification."""

    valid: bool
    payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PolicyFederation:
    """Policy federation helpers shared by parent and child agents."""

    @staticmethod
    def create_token(payload: Dict[str, Any], secret: str) -> str:
        """Create a signed policy federation token."""

        encoded_payload = _base64_url_encode(_stable_json(payload).encode("utf-8"))
        signing_input = f"{TOKEN_PREFIX}.{encoded_payload}"
        signature = _sign(signing_input, secret)
        return f"{signing_input}.{signature}"

    @staticmethod
    def verify_token(
        token: str,
        secret: str,
        now_ms: Optional[int] = None,
    ) -> PolicyFederationVerificationResult:
        """Verify a policy federation token and decode its payload."""

        parts = token.split(".")
        if len(parts) != 4 or f"{parts[0]}.{parts[1]}" != TOKEN_PREFIX:
            return PolicyFederationVerificationResult(
                valid=False,
                error="Invalid policy federation token format",
            )

        signing_input = f"{parts[0]}.{parts[1]}.{parts[2]}"
        expected_signature = _sign(signing_input, secret)
        if not hmac.compare_digest(parts[3], expected_signature):
            return PolicyFederationVerificationResult(
                valid=False,
                error="Invalid policy federation token signature",
            )

        try:
            payload = json.loads(_base64_url_decode(parts[2]).decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            return PolicyFederationVerificationResult(
                valid=False,
                error="Invalid policy federation token payload",
            )

        current_time = int(time.time() * 1000) if now_ms is None else now_ms
        expires_at = payload.get("expiresAt")
        if expires_at is not None and int(expires_at) <= current_time:
            return PolicyFederationVerificationResult(
                valid=False,
                error="Policy federation token expired",
            )

        return PolicyFederationVerificationResult(valid=True, payload=payload)

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Decode a token without verifying its signature."""

        parts = token.split(".")
        if len(parts) != 4 or f"{parts[0]}.{parts[1]}" != TOKEN_PREFIX:
            raise ValueError("Invalid policy federation token format")

        return json.loads(_base64_url_decode(parts[2]).decode("utf-8"))

    @staticmethod
    def extract_constraints(federation: Dict[str, Any]) -> Dict[str, Any]:
        """Return constraints from either a payload or raw constraints dict."""

        constraints = federation.get("constraints")
        return dict(constraints) if isinstance(constraints, dict) else dict(federation)

    @staticmethod
    def merge_policies(
        child_policy: Dict[str, Any],
        federation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge parent constraints into child policy using most-restrictive-wins."""

        constraints = PolicyFederation.extract_constraints(federation)
        merged = copy.deepcopy(child_policy)

        if constraints.get("toolAllowlist") is not None or constraints.get("revokedTools"):
            merged["tools"] = _merge_tool_policies(
                merged.get("tools"),
                constraints.get("toolAllowlist"),
                constraints.get("revokedTools"),
            )

        if constraints.get("budget"):
            behavioral = dict(merged.get("behavioral") or {})
            behavioral["costLimit"] = _merge_cost_limit(
                behavioral.get("costLimit"),
                constraints["budget"],
            )
            behavioral.setdefault("rateLimit", {"requests": 9007199254740991, "window": "1d"})
            merged["behavioral"] = behavioral

            identity = merged.get("identity")
            if isinstance(identity, dict):
                identity = dict(identity)
                identity["costLimit"] = _merge_cost_limit(
                    identity.get("costLimit"),
                    constraints["budget"],
                )
                merged["identity"] = identity

        data_classification = constraints.get("dataClassification")
        if data_classification:
            content = dict(merged.get("content") or {})
            current = (content.get("dataClassification") or {}).get("maxLevel")
            max_level = (
                _most_restrictive_classification(current, data_classification)
                if current
                else data_classification
            )
            content["dataClassification"] = {"maxLevel": max_level}
            merged["content"] = content

        return merged

    @staticmethod
    def apply_revocation(
        constraints: Dict[str, Any],
        revoked_tools: List[str],
    ) -> Dict[str, Any]:
        """Return constraints with async parent tool revocations applied."""

        next_constraints = dict(constraints)
        revoked = set(next_constraints.get("revokedTools") or [])
        revoked.update(revoked_tools)
        next_constraints["revokedTools"] = sorted(revoked)

        allowlist = next_constraints.get("toolAllowlist")
        if allowlist is not None:
            next_constraints["toolAllowlist"] = [
                tool for tool in allowlist if tool not in revoked
            ]

        return next_constraints

    @staticmethod
    def create_child_context(
        payload: Dict[str, Any],
        child_correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> ExecutionContext:
        """Create a child execution context linked to the parent trace."""

        trace_chain = list(payload.get("traceChain") or [])
        parent_correlation_id = payload.get("parentCorrelationId")
        if parent_correlation_id:
            trace_chain.append(parent_correlation_id)

        options = ExecutionContextOptions(
            correlation_id=child_correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            metadata={
                "federation_issuer": payload.get("issuer"),
                "federation_revision": payload.get("revision"),
                "parent_correlation_id": parent_correlation_id,
                "trace_chain": trace_chain,
            },
        )
        return ContextManager.create_context(options)


def _merge_tool_policies(
    child_tools: Optional[Dict[str, Any]],
    allowlist: Optional[List[str]],
    revoked_tools: Optional[List[str]],
) -> Dict[str, Any]:
    result = copy.deepcopy(child_tools or {})
    revoked = set(revoked_tools or [])

    if allowlist is not None:
        allowed = set(allowlist)
        result["*"] = {"allowed": False}

        for tool in allowlist:
            child = dict(result.get(tool) or {})
            child["allowed"] = bool(child.get("allowed", True)) and tool not in revoked
            result[tool] = child

        for tool, config in list(result.items()):
            if tool != "*" and tool not in allowed:
                next_config = dict(config)
                next_config["allowed"] = False
                result[tool] = next_config
    elif not child_tools and revoked:
        result["*"] = {"allowed": True}

    for tool in revoked:
        next_config = dict(result.get(tool) or {})
        next_config["allowed"] = False
        result[tool] = next_config

    return result


def _merge_cost_limit(
    current: Optional[Dict[str, Any]],
    budget: Dict[str, Any],
) -> Dict[str, Any]:
    result = dict(current or {})
    daily_ceiling = _min_defined(budget.get("daily"), budget.get("remaining"))

    daily = _min_defined(result.get("daily"), daily_ceiling)
    if daily is not None:
        result["daily"] = daily

    hourly = _min_defined(result.get("hourly"), budget.get("hourly"))
    if hourly is not None:
        result["hourly"] = hourly

    monthly = _min_defined(result.get("monthly"), budget.get("monthly"))
    if monthly is not None:
        result["monthly"] = monthly

    return result


def _min_defined(left: Optional[float], right: Optional[float]) -> Optional[float]:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _most_restrictive_classification(left: str, right: str) -> str:
    return left if CLASSIFICATION_RANKS[left] <= CLASSIFICATION_RANKS[right] else right


def _sign(signing_input: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64_url_encode(digest)


def _stable_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _base64_url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
