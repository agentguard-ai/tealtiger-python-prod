"""Tests for the v1.3 policy bundle hot-swap manager."""

import pytest

from tealtiger.core.engine.v1_3.policy_hotswap import (
    SDK_CAPABILITIES,
    HotSwapEventType,
    PolicyHotSwapManager,
)
from tealtiger.core.engine.v1_3.types import (
    FreezeRule,
    PolicyBundle,
    PolicyMatcher,
    PolicyRule,
)


def _rule(rule_id: str = "r1", action: str = "DENY") -> PolicyRule:
    return PolicyRule(
        id=rule_id,
        control_id="D.C.S.1",
        match=PolicyMatcher(action_class="TOOL_INVOKE", tool="write"),
        action=action,
    )


def _freeze(rule_id: str, tool: str, reason: str) -> FreezeRule:
    return FreezeRule(
        id=rule_id,
        match=PolicyMatcher(tool=tool),
        reason=reason,
        created_at=1_700_000_000_000,
        created_by="test",
    )


def _bundle(manager: PolicyHotSwapManager, **overrides) -> PolicyBundle:
    """Build a valid bundle with a correctly computed integrity hash."""
    kwargs = {
        "bundle_version": "1.0.0",
        "requires_sdk": "^1.3.0",
        "requires_teec": "^2.0.0",
        "required_capabilities": ["freeze_rules"],
        "policies": [_rule()],
    }
    kwargs.update(overrides)
    bundle = PolicyBundle(**kwargs)
    bundle.hash = manager.compute_bundle_hash(bundle)
    return bundle


# ── Cross-language interop ───────────────────────────────────────


def test_bundle_hash_matches_typescript_core():
    """Pin the digest so bundle interop cannot regress silently.

    This exact value was verified against Node's `JSON.stringify` +
    `crypto.createHash('sha256')`, reproducing what the TypeScript core's
    `computeBundleHash()` produces for an identical bundle. Both sides emitted
    byte-identical JSON.

    If this test starts failing, the Python and TypeScript cores no longer agree
    on bundle hashes, and a bundle signed or hashed by one will be rejected as
    tampered by the other. Likely causes: changed key order, `json.dumps`
    separators reverted to defaults, `sort_keys=True` introduced, `None` values
    emitted as `null` instead of being omitted, or `ensure_ascii` flipped.
    """
    manager = PolicyHotSwapManager()
    bundle = PolicyBundle(
        bundle_version="1.0.0",
        requires_sdk="^1.3.0",
        requires_teec="^2.0.0",
        required_capabilities=["freeze_rules"],
        policies=[_rule()],
    )

    assert manager.compute_bundle_hash(bundle) == (
        "08a27bd0e4da4d24046438d22123ea766254c35dd8fc6fa89a043c4872900dbf"
    )


def test_hash_excludes_hash_and_signature_fields():
    """The digest must not cover `hash` or `signature`, else it is unstable."""
    manager = PolicyHotSwapManager()
    bundle = _bundle(manager)
    original = manager.compute_bundle_hash(bundle)

    bundle.signature = "s" * 64
    assert manager.compute_bundle_hash(bundle) == original


def test_optional_none_fields_are_omitted_not_nulled():
    """Setting an optional field to None must hash the same as omitting it.

    Guards the JSON.stringify-undefined parity that interop depends on.
    """
    manager = PolicyHotSwapManager()
    without = PolicyBundle(
        bundle_version="1.0.0",
        requires_sdk="^1.3.0",
        requires_teec="^2.0.0",
        policies=[_rule()],
    )
    with_none = PolicyBundle(
        bundle_version="1.0.0",
        requires_sdk="^1.3.0",
        requires_teec="^2.0.0",
        policies=[_rule()],
        cost_limits=None,
        freeze_rules=None,
    )

    assert manager.compute_bundle_hash(without) == manager.compute_bundle_hash(with_none)


# ── Validation ───────────────────────────────────────────────────


def test_valid_bundle_passes():
    manager = PolicyHotSwapManager()
    result = manager.validate_bundle(_bundle(manager))

    assert result.valid is True
    assert result.errors == []


def test_tampered_bundle_fails_integrity_check():
    manager = PolicyHotSwapManager()
    bundle = _bundle(manager)

    bundle.bundle_version = "9.9.9"  # hash no longer matches contents

    result = manager.validate_bundle(bundle)
    assert result.valid is False
    assert any("Integrity hash mismatch" in e for e in result.errors)


def test_missing_required_fields_are_all_reported():
    """Validation reports every problem, not just the first."""
    manager = PolicyHotSwapManager()
    bundle = PolicyBundle(bundle_version="", requires_sdk="", requires_teec="")

    result = manager.validate_bundle(bundle)

    assert result.valid is False
    assert any("bundle_version" in e for e in result.errors)
    assert any("requires_sdk" in e for e in result.errors)
    assert any("requires_teec" in e for e in result.errors)
    assert any("hash" in e for e in result.errors)


def test_policy_missing_fields_reported_with_index():
    manager = PolicyHotSwapManager()
    incomplete = PolicyRule(id="", control_id="", match=None, action="")
    bundle = _bundle(manager, policies=[_rule(), incomplete])

    result = manager.validate_bundle(bundle)

    assert result.valid is False
    assert any("Policy at index 1 missing 'id'" in e for e in result.errors)
    assert any("Policy at index 1 missing 'control_id'" in e for e in result.errors)
    assert any("Policy at index 1 missing 'match'" in e for e in result.errors)
    assert any("Policy at index 1 missing 'action'" in e for e in result.errors)


def test_unsupported_capability_is_rejected():
    manager = PolicyHotSwapManager()
    bundle = _bundle(manager, required_capabilities=["freeze_rules", "time_travel"])

    result = manager.validate_bundle(bundle)

    assert result.valid is False
    assert any("time_travel" in e for e in result.errors)


def test_custom_capability_list_is_honoured():
    manager = PolicyHotSwapManager(sdk_capabilities=["only_this"])
    bundle = _bundle(manager, required_capabilities=["only_this"])

    assert manager.validate_bundle(bundle).valid is True


def test_every_advertised_capability_is_accepted():
    manager = PolicyHotSwapManager()
    bundle = _bundle(manager, required_capabilities=list(SDK_CAPABILITIES))

    assert manager.validate_bundle(bundle).valid is True


def test_invalid_fail_behavior_is_rejected():
    manager = PolicyHotSwapManager()
    bundle = _bundle(manager)
    bundle.fail_behavior = "fail_sideways"
    bundle.hash = manager.compute_bundle_hash(bundle)

    result = manager.validate_bundle(bundle)
    assert result.valid is False
    assert any("fail_behavior" in e for e in result.errors)


def test_short_signature_is_rejected_and_absent_signature_is_fine():
    manager = PolicyHotSwapManager()

    short = _bundle(manager)
    short.signature = "tooshort"
    assert any("signature" in e.lower() for e in manager.validate_bundle(short).errors)

    long_enough = _bundle(manager)
    long_enough.signature = "s" * 64
    assert manager.validate_bundle(long_enough).valid is True

    unsigned = _bundle(manager)
    assert unsigned.signature is None
    assert manager.validate_bundle(unsigned).valid is True


# ── Loading and hot-swap ─────────────────────────────────────────


def test_load_valid_bundle_becomes_active_and_emits_event():
    manager = PolicyHotSwapManager()
    events = []
    manager.on_event(events.append)

    bundle = _bundle(manager)
    result = manager.load_policy(bundle)

    assert result.success is True
    assert result.error is None
    assert manager.get_active_bundle() is bundle
    assert len(events) == 1
    assert events[0].type == HotSwapEventType.POLICY_BUNDLE_LOADED
    assert events[0].details["policy_count"] == 1


def test_failed_load_retains_previous_bundle_and_emits_failure():
    manager = PolicyHotSwapManager()
    good = _bundle(manager)
    manager.load_policy(good)

    events = []
    manager.on_event(events.append)

    bad = _bundle(manager, required_capabilities=["time_travel"])
    result = manager.load_policy(bad)

    assert result.success is False
    assert result.error is not None
    # The previous bundle must survive a failed swap.
    assert manager.get_active_bundle() is good
    assert events[0].type == HotSwapEventType.POLICY_BUNDLE_SWAP_FAILED


def test_freeze_rules_accumulate_and_are_never_removed():
    """The core guarantee: a new bundle cannot drop an existing FREEZE rule."""
    manager = PolicyHotSwapManager()

    first = _bundle(
        manager,
        freeze_rules=[_freeze("f1", "rm", "no rm")],
    )
    manager.load_policy(first)
    assert [r.id for r in manager.get_accumulated_freeze_rules()] == ["f1"]

    # Second bundle carries a DIFFERENT freeze rule and omits f1 entirely.
    second = _bundle(
        manager,
        bundle_version="2.0.0",
        freeze_rules=[_freeze("f2", "curl", "no curl")],
    )
    manager.load_policy(second)

    ids = [r.id for r in manager.get_accumulated_freeze_rules()]
    assert ids == ["f1", "f2"], "f1 must survive a bundle that does not mention it"


def test_duplicate_freeze_rule_ids_are_not_added_twice():
    manager = PolicyHotSwapManager()
    rule = _freeze("f1", "rm", "no rm")

    manager.load_policy(_bundle(manager, freeze_rules=[rule]))
    manager.load_policy(_bundle(manager, bundle_version="2.0.0", freeze_rules=[rule]))

    assert len(manager.get_accumulated_freeze_rules()) == 1


def test_accumulated_freeze_rules_list_is_a_copy():
    manager = PolicyHotSwapManager()
    manager.load_policy(
        _bundle(
            manager,
            freeze_rules=[_freeze("f1", "rm", "no")],
        )
    )

    manager.get_accumulated_freeze_rules().clear()

    assert len(manager.get_accumulated_freeze_rules()) == 1


def test_no_active_bundle_before_first_load():
    assert PolicyHotSwapManager().get_active_bundle() is None


# ── Event listener isolation ─────────────────────────────────────


def test_throwing_listener_does_not_break_the_manager():
    manager = PolicyHotSwapManager()
    seen = []

    def explodes(_event):
        raise RuntimeError("listener blew up")

    manager.on_event(explodes)
    manager.on_event(seen.append)

    result = manager.load_policy(_bundle(manager))

    assert result.success is True
    assert len(seen) == 1, "a failing listener must not stop later listeners"


@pytest.mark.parametrize(
    "event_type",
    [HotSwapEventType.POLICY_BUNDLE_LOADED, HotSwapEventType.POLICY_BUNDLE_SWAP_FAILED],
)
def test_event_type_constants_are_stable_strings(event_type):
    """These strings cross process boundaries into SIEM exports; pin them."""
    assert isinstance(event_type, str)
    assert event_type == event_type.upper()
