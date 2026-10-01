"""Policy Bundle Hot-Swap Manager.

Manages runtime loading and validation of governance policy bundles. Supports
hot-swapping bundles without a process restart while preserving FREEZE rule
immutability — FREEZE rules from new bundles are ADDED to existing rules but
never removed.

Python port of ``src/core/engine/v1.3/policy-hotswap.ts`` from the TypeScript
core. See "Cross-language hash compatibility" on
:meth:`PolicyHotSwapManager.compute_bundle_hash` for the one place where this
port needs care rather than a direct translation.

Module: core/engine/v1_3/policy_hotswap
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from tealtiger.core.engine.v1_3.engine import GovernanceEvent, GovernanceEventListener
from tealtiger.core.engine.v1_3.types import FreezeRule, PolicyBundle

__all__ = [
    "SDK_CAPABILITIES",
    "BundleValidationResult",
    "HotSwapEventType",
    "LoadPolicyResult",
    "PolicyHotSwapManager",
]


# ── Event Types ──────────────────────────────────────────────────


class HotSwapEventType:
    """Event type constants emitted by :class:`PolicyHotSwapManager`."""

    POLICY_BUNDLE_LOADED = "POLICY_BUNDLE_LOADED"
    POLICY_BUNDLE_SWAP_FAILED = "POLICY_BUNDLE_SWAP_FAILED"


# ── Validation Results ───────────────────────────────────────────


@dataclasses.dataclass
class BundleValidationResult:
    """Outcome of validating a policy bundle without loading it."""

    valid: bool
    """True when no errors were found."""

    errors: List[str] = dataclasses.field(default_factory=list)
    """Human-readable validation failures. Empty when ``valid`` is True."""


@dataclasses.dataclass
class LoadPolicyResult:
    """Outcome of attempting to load a policy bundle."""

    success: bool
    """True when the bundle validated and became the active bundle."""

    error: Optional[str] = None
    """Semicolon-joined validation errors when ``success`` is False."""


# ── SDK Capabilities (for capability negotiation) ────────────────

SDK_CAPABILITIES: List[str] = [
    "freeze_rules",
    "plan_only_mode",
    "nhi_governance",
    "zsp",
    "attestation",
    "automation_levels",
    "code_change_governance",
    "cost_governance",
    "proof_chain",
    "tealflow",
    "drift_detection",
    "state_governance",
    "temporal_governance",
    "siem_export",
    "otel_spans",
    "response_hooks",
    "classifier_ensemble",
    "unicode_normalization",
    "encoded_output_detection",
    "control_char_sanitization",
    "markdown_exfiltration_detection",
    "memory_provenance",
    "mcp_drift_detection",
]
"""Capabilities this SDK advertises during bundle capability negotiation.

Kept in the same order as the TypeScript core's ``SDK_CAPABILITIES`` so the two
lists can be diffed directly. Order does not affect validation.
"""


# ── JSON serialisation for hashing ───────────────────────────────


def _to_jsonable(value: Any) -> Any:
    """Convert a value into something ``json.dumps`` can serialise.

    Mirrors ``JSON.stringify`` semantics rather than Python's defaults, because
    the output feeds an integrity hash that must match the TypeScript core's.
    In particular, fields whose value is ``None`` are OMITTED, because
    ``JSON.stringify`` drops properties that are ``undefined``. Emitting
    ``"automation_level": null`` where TypeScript emits nothing would produce a
    different hash for an identical bundle.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        result: Dict[str, Any] = {}
        for f in dataclasses.fields(value):
            field_value = getattr(value, f.name)
            if field_value is None:
                # JSON.stringify omits undefined properties; match that.
                continue
            result[f.name] = _to_jsonable(field_value)
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items() if v is not None}
    return value


# ── PolicyHotSwapManager ─────────────────────────────────────────


class PolicyHotSwapManager:
    """Validates and hot-swaps governance policy bundles at runtime.

    FREEZE rules accumulate across swaps and are never removed by loading a new
    bundle, which is what makes them a durable control rather than a policy
    setting.
    """

    def __init__(self, sdk_capabilities: Optional[List[str]] = None) -> None:
        """Initialise the manager.

        Args:
            sdk_capabilities: Capabilities to advertise during negotiation.
                Defaults to :data:`SDK_CAPABILITIES`.
        """
        self._active_bundle: Optional[PolicyBundle] = None
        self._accumulated_freeze_rules: List[FreezeRule] = []
        self._event_listeners: List[GovernanceEventListener] = []
        self._sdk_capabilities: List[str] = (
            list(sdk_capabilities) if sdk_capabilities is not None else list(SDK_CAPABILITIES)
        )

    # ── Public API ───────────────────────────────────────────────

    def load_policy(self, new_bundle: PolicyBundle) -> LoadPolicyResult:
        """Validate and load a new policy bundle.

        On validation failure the previous bundle is retained and
        ``POLICY_BUNDLE_SWAP_FAILED`` is emitted. On success the active bundle
        is replaced, FREEZE rules are accumulated, and
        ``POLICY_BUNDLE_LOADED`` is emitted.

        Args:
            new_bundle: The bundle to validate and activate.

        Returns:
            :class:`LoadPolicyResult` describing the outcome.
        """
        validation = self.validate_bundle(new_bundle)

        if not validation.valid:
            error_message = "; ".join(validation.errors)

            self._emit_event(
                GovernanceEvent(
                    type=HotSwapEventType.POLICY_BUNDLE_SWAP_FAILED,
                    timestamp=_now_ms(),
                    details={
                        "errors": list(validation.errors),
                        "bundle_version": new_bundle.bundle_version,
                        "message": f"Policy bundle swap failed: {error_message}",
                    },
                )
            )

            return LoadPolicyResult(success=False, error=error_message)

        # Accumulate FREEZE rules; existing rules are never removed.
        if new_bundle.freeze_rules:
            existing_ids = {rule.id for rule in self._accumulated_freeze_rules}
            for rule in new_bundle.freeze_rules:
                if rule.id not in existing_ids:
                    self._accumulated_freeze_rules.append(dataclasses.replace(rule))
                    existing_ids.add(rule.id)

        self._active_bundle = new_bundle

        self._emit_event(
            GovernanceEvent(
                type=HotSwapEventType.POLICY_BUNDLE_LOADED,
                timestamp=_now_ms(),
                details={
                    "bundle_version": new_bundle.bundle_version,
                    "policy_count": len(new_bundle.policies),
                    "freeze_rules_total": len(self._accumulated_freeze_rules),
                    "message": (
                        f"Policy bundle v{new_bundle.bundle_version} loaded successfully."
                    ),
                },
            )
        )

        return LoadPolicyResult(success=True)

    def get_active_bundle(self) -> Optional[PolicyBundle]:
        """Return the currently active policy bundle, or None if none loaded."""
        return self._active_bundle

    def get_accumulated_freeze_rules(self) -> List[FreezeRule]:
        """Return all accumulated FREEZE rules, persisted across hot-swaps.

        Returns a shallow copy of the list so callers cannot append or remove
        rules. Note this differs from the TypeScript core, which additionally
        applies ``Object.freeze`` to each rule; ``FreezeRule`` is not a frozen
        dataclass, so individual rule objects remain mutable here. Treat them as
        read-only.
        """
        return list(self._accumulated_freeze_rules)

    def validate_bundle(self, bundle: PolicyBundle) -> BundleValidationResult:
        """Validate a policy bundle without loading it.

        Checks, in order:

        1. Schema validity — required fields present and well-typed
        2. Integrity hash — SHA-256 over bundle contents
        3. Capability requirements — satisfied by this SDK
        4. Signature — Ed25519 (placeholder, see :meth:`_validate_signature`)

        Args:
            bundle: The bundle to check.

        Returns:
            :class:`BundleValidationResult` with every error found, not just the
            first.
        """
        errors: List[str] = []

        self._validate_schema(bundle, errors)
        self._validate_integrity_hash(bundle, errors)
        self._validate_capabilities(bundle, errors)
        self._validate_signature(bundle, errors)

        return BundleValidationResult(valid=len(errors) == 0, errors=errors)

    def on_event(self, listener: GovernanceEventListener) -> None:
        """Register a listener for hot-swap events.

        Args:
            listener: Callable invoked with each :class:`GovernanceEvent`.
        """
        self._event_listeners.append(listener)

    def compute_bundle_hash(self, bundle: PolicyBundle) -> str:
        """Compute the SHA-256 integrity hash of a bundle's contents.

        The hash covers ``bundle_version``, ``requires_sdk``, ``requires_teec``,
        ``required_capabilities``, ``policies``, ``fail_behavior``,
        ``cost_limits`` and ``freeze_rules`` — deliberately excluding ``hash``
        itself and ``signature``.

        **Cross-language hash compatibility.** This must produce the same digest
        as the TypeScript core for an identical bundle, so the serialisation is
        pinned rather than left to defaults:

        * Key order matches the TypeScript object literal exactly. JSON object
          key order is significant to the digest even though it is not
          significant to JSON itself.
        * ``separators=(",", ":")`` reproduces ``JSON.stringify``'s compact
          output. Python's default ``json.dumps`` inserts a space after ``:``
          and ``,``, which would change the digest.
        * ``sort_keys`` is deliberately **not** used; it would reorder keys away
          from the TypeScript literal order.
        * ``None`` values are omitted, because ``JSON.stringify`` drops
          ``undefined`` properties. See :func:`_to_jsonable`.
        * ``ensure_ascii=False`` so non-ASCII characters are emitted as
          themselves, as ``JSON.stringify`` does, rather than as ``\\uXXXX``
          escapes.

        A bundle hashed by one core and validated by the other will only agree
        if all of the above hold. Changing any of them is a breaking change to
        bundle interop.

        Args:
            bundle: The bundle to hash.

        Returns:
            Lowercase hex SHA-256 digest.
        """
        content = {
            "bundle_version": bundle.bundle_version,
            "requires_sdk": bundle.requires_sdk,
            "requires_teec": bundle.requires_teec,
            "required_capabilities": _to_jsonable(bundle.required_capabilities),
            "policies": _to_jsonable(bundle.policies),
            "fail_behavior": bundle.fail_behavior,
        }
        # Omit when absent, matching JSON.stringify's treatment of undefined.
        if bundle.cost_limits is not None:
            content["cost_limits"] = _to_jsonable(bundle.cost_limits)
        if bundle.freeze_rules is not None:
            content["freeze_rules"] = _to_jsonable(bundle.freeze_rules)

        serialised = json.dumps(
            content,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    # ── Private validation ───────────────────────────────────────

    def _validate_schema(self, bundle: PolicyBundle, errors: List[str]) -> None:
        """Check required fields are present and of the right type."""
        if not bundle.bundle_version or not isinstance(bundle.bundle_version, str):
            errors.append("Missing or invalid bundle_version")

        if not bundle.requires_sdk or not isinstance(bundle.requires_sdk, str):
            errors.append("Missing or invalid requires_sdk")

        if not bundle.requires_teec or not isinstance(bundle.requires_teec, str):
            errors.append("Missing or invalid requires_teec")

        if not isinstance(bundle.required_capabilities, list):
            errors.append("Missing or invalid required_capabilities (must be array)")

        if not bundle.hash or not isinstance(bundle.hash, str):
            errors.append("Missing or invalid hash")

        if not isinstance(bundle.policies, list):
            errors.append("Missing or invalid policies (must be array)")

        if bundle.fail_behavior not in ("fail_closed", "fail_open"):
            errors.append(
                'Missing or invalid fail_behavior (must be "fail_closed" or "fail_open")'
            )

        if isinstance(bundle.policies, list):
            for index, policy in enumerate(bundle.policies):
                if not getattr(policy, "id", None):
                    errors.append(f"Policy at index {index} missing 'id'")
                if not getattr(policy, "control_id", None):
                    errors.append(f"Policy at index {index} missing 'control_id'")
                if not getattr(policy, "match", None):
                    errors.append(f"Policy at index {index} missing 'match'")
                if not getattr(policy, "action", None):
                    errors.append(f"Policy at index {index} missing 'action'")

    def _validate_integrity_hash(self, bundle: PolicyBundle, errors: List[str]) -> None:
        """Compare the declared hash against a freshly computed one."""
        if not bundle.hash:
            # Already reported by schema validation; don't report it twice.
            return

        computed = self.compute_bundle_hash(bundle)
        if computed != bundle.hash:
            errors.append(
                f"Integrity hash mismatch: expected {bundle.hash}, computed {computed}"
            )

    def _validate_capabilities(self, bundle: PolicyBundle, errors: List[str]) -> None:
        """Check every required capability is advertised by this SDK."""
        if not isinstance(bundle.required_capabilities, list):
            return

        missing = [
            cap for cap in bundle.required_capabilities if cap not in self._sdk_capabilities
        ]

        if missing:
            errors.append(f"Bundle requires unsupported capabilities: {', '.join(missing)}")

    def _validate_signature(self, bundle: PolicyBundle, errors: List[str]) -> None:
        """Check the bundle signature, when one is present.

        .. warning::
           This is a **placeholder**, ported as-is from the TypeScript core: it
           only checks that a present signature is at least 64 characters long.
           It does **not** verify the signature against a trusted public key, so
           it establishes nothing about authenticity. A signature is optional;
           an absent signature is not an error.

           Do not treat a passing signature check as authentication until real
           Ed25519 verification replaces this in both cores.
        """
        if bundle.signature:
            if len(bundle.signature) < 64:
                errors.append(
                    "Invalid signature: too short (minimum 64 characters for Ed25519)"
                )

    # ── Events ───────────────────────────────────────────────────

    def _emit_event(self, event: GovernanceEvent) -> None:
        """Deliver an event to every listener, isolating listener failures."""
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception:
                # Listeners must not be able to break the hot-swap manager.
                pass


def _now_ms() -> int:
    """Current wall-clock time in milliseconds, matching JS ``Date.now()``."""
    return int(time.time() * 1000)
