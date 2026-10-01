"""Policy utilities for building and testing policies."""

from typing import Any, Dict

from tealtiger.types import Policy, PolicyTestResult


class PolicyBuilder:
    """Builder for creating security policies."""

    def __init__(self) -> None:
        """Initialize the policy builder."""
        self._policy: Dict[str, Any] = {
            "id": "",
            "name": "",
            "description": "",
            "rules": [],
            "enabled": True,
        }

    def name(self, name: str) -> "PolicyBuilder":
        """Set the policy name.

        Args:
            name: Policy name

        Returns:
            Self for chaining
        """
        self._policy["name"] = name
        return self

    def description(self, description: str) -> "PolicyBuilder":
        """Set the policy description.

        Args:
            description: Policy description

        Returns:
            Self for chaining
        """
        self._policy["description"] = description
        return self

    def add_rule(
        self,
        condition: Dict[str, Any],
        action: str,
        reason: str,
    ) -> "PolicyBuilder":
        """Add a rule to the policy.

        Args:
            condition: Rule condition
            action: Action to take (allow/deny/transform)
            reason: Reason for the action

        Returns:
            Self for chaining
        """
        self._policy["rules"].append(
            {
                "condition": condition,
                "action": action,
                "reason": reason,
            }
        )
        return self

    def build(self) -> Policy:
        """Build the policy.

        Returns:
            Constructed Policy object
        """
        # Generate ID if not set
        if not self._policy["id"]:
            self._policy["id"] = f"policy-{self._policy['name'].lower().replace(' ', '-')}"

        return Policy(**self._policy)


class PolicyTester:
    """Unimplemented placeholder. Use ``PolicyTestRunner`` instead.

    .. deprecated::
       This class never had a working implementation. Use
       :class:`tealtiger.PolicyTestRunner` (that is
       ``tealtiger.core.engine.testing.PolicyTester``, re-exported under the
       clearer name) which evaluates test cases against a real engine.
    """

    def test_policy(
        self,
        policy: Policy,
        request: Dict[str, Any],
    ) -> PolicyTestResult:
        """Not implemented. Raises :class:`NotImplementedError`.

        Args:
            policy: Policy to test
            request: Request to test against

        Raises:
            NotImplementedError: Always. This method never evaluated the policy
                it was given.

        .. note::
           Until this raised, it returned ``decision="allow"`` for **every**
           input, including policies whose rules denied the request. Any caller
           relying on that return value was receiving a false pass from a
           governance check — the most dangerous possible failure mode for this
           API, so it now fails loudly instead.

           Use :class:`tealtiger.PolicyTestRunner` for real policy testing::

               from tealtiger import PolicyTestRunner
               from tealtiger.core.engine.testing.types import PolicyTestCase

               runner = PolicyTestRunner(engine)
               result = runner.run_test(PolicyTestCase(...))
        """
        raise NotImplementedError(
            "PolicyTester.test_policy was never implemented and previously "
            "returned decision='allow' for every input, regardless of the "
            "policy. Use tealtiger.PolicyTestRunner instead, which evaluates "
            "test cases against a real engine: "
            "PolicyTestRunner(engine).run_test(PolicyTestCase(...)). "
            "See also run_suite() and run_from_file()."
        )
