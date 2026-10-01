"""Tests for policy utilities."""

import pytest

from tealtiger import PolicyBuilder, PolicyTester


def test_policy_builder():
    """Test policy builder."""
    policy = (
        PolicyBuilder()
        .name("test-policy")
        .description("Test policy description")
        .add_rule(
            condition={"tool_name": "file-write"},
            action="deny",
            reason="File writes not allowed"
        )
        .build()
    )

    assert policy.name == "test-policy"
    assert policy.description == "Test policy description"
    assert len(policy.rules) == 1
    assert policy.rules[0]["action"] == "deny"


def test_policy_builder_chaining():
    """Test policy builder method chaining."""
    policy = (
        PolicyBuilder()
        .name("multi-rule-policy")
        .description("Policy with multiple rules")
        .add_rule(
            condition={"tool_name": "file-write"},
            action="deny",
            reason="No writes"
        )
        .add_rule(
            condition={"tool_name": "file-read"},
            action="allow",
            reason="Reads allowed"
        )
        .build()
    )

    assert len(policy.rules) == 2


def test_policy_tester_raises_not_implemented():
    """PolicyTester.test_policy must fail loudly, not return a false pass.

    This method never evaluated the policy it was handed: it returned
    decision="allow" for every input. The previous version of this test only
    asserted `result.decision is not None` and `result.reason is not None`,
    which the hardcoded "allow" satisfied trivially — so the test passed while
    the feature did nothing.

    A governance check that cannot fail is worse than one that is absent, so the
    method now raises, and this test pins that contract.
    """
    tester = PolicyTester()
    policy = (
        PolicyBuilder()
        .name("test-policy")
        .description("Test")
        .add_rule(
            condition={"tool_name": "test"},
            action="deny",
            reason="Denied by rule"
        )
        .build()
    )

    with pytest.raises(NotImplementedError) as excinfo:
        tester.test_policy(
            policy=policy,
            request={"tool_name": "test", "parameters": {}}
        )

    # The error must point the caller at the working implementation.
    assert "PolicyTestRunner" in str(excinfo.value)


def test_policy_test_runner_is_a_different_class_from_the_stub():
    """The working tester is exported, and is not the stub.

    `tealtiger.PolicyTestRunner` is `tealtiger.core.engine.testing.PolicyTester`
    re-exported under a clearer name. Guard against the two being confused
    again: the stub takes no engine, the real one requires one.
    """
    from tealtiger import PolicyTestRunner

    assert PolicyTestRunner is not PolicyTester

    # The real runner is engine-backed; constructing it without one is an error.
    with pytest.raises(TypeError):
        PolicyTestRunner()

