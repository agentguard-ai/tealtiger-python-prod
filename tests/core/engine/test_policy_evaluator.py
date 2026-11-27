"""Tests for tool-allowlist evaluation, one per requirement of §6.2.

Each test names the requirement it covers (TA-1 … TA-8) and asserts the
``triggering_clause`` as well as the action, because asserting the action alone is the
mistake the conformance specification was written to stop. Corpus validity rule CV-2
makes clause assertion mandatory for exactly this reason: a verdict reached by the wrong
mechanism is not a pass.

The expectations here are taken from the published corpus
(``suites/tool-allowlist.v0.1.json`` in ``agentguard-ai/tealtiger-conformance``), so this
module and the external gate cannot drift apart silently.
"""

from dataclasses import FrozenInstanceError

import pytest

from tealtiger.core.engine.policy_evaluator import (
    SUPPORTED_RULE_TYPES,
    ClauseOutcome,
    aggregate_outcomes,
    evaluate_policies,
    evaluate_tools_section,
    unsupported_sections,
)
from tealtiger.core.engine.types import CLAUSE_NONE, ReasonCode

DENY_CODES = (ReasonCode.POLICY_VIOLATION, ReasonCode.TOOL_NOT_ALLOWED)


def _execute(tool=None, action="tool.execute", **extra):
    request = {"agentId": "agent-1", "action": action}
    if tool is not None:
        request["tool"] = tool
    request.update(extra)
    return request


class TestTA1TheToolFieldIsAPrecondition:
    """A `tool.execute` request must name a tool, and that is not a governance denial."""

    def test_missing_tool_is_reported_as_malformed_input(self):
        outcome = evaluate_tools_section(
            _execute(), {"search": {"allowed": True}}
        )

        assert outcome.allowed is False
        assert outcome.triggering_clause == "request.tool.missing"
        assert outcome.reason_codes == (
            ReasonCode.POLICY_VIOLATION,
            ReasonCode.INVALID_REQUEST,
        )

    def test_missing_tool_is_not_reported_as_tool_not_allowed(self):
        """§4.1(a). The corpus asserts this code's *absence*, not just the other's presence.

        Reporting a client that forgot a field as a governance verdict about a tool is
        how 13 cases came to look like working code inspection when none of them reached
        a detection clause.
        """
        outcome = evaluate_tools_section(_execute(), {"search": {"allowed": True}})

        assert ReasonCode.TOOL_NOT_ALLOWED not in outcome.reason_codes

    def test_a_non_tool_action_without_a_tool_is_unaffected(self):
        """The precondition is scoped to `tool.execute`, not to every request."""
        outcome = evaluate_tools_section(
            _execute(action="chat.create", content="hello"),
            {"file_delete": {"allowed": False}},
        )

        assert outcome.allowed is True
        assert outcome.triggering_clause == CLAUSE_NONE
        assert ReasonCode.TOOL_NOT_ALLOWED not in outcome.reason_codes


class TestTA2AndTA3TheEntryDecides:
    def test_entry_configured_false_denies(self):
        outcome = evaluate_tools_section(
            _execute("file_delete"),
            {"file_delete": {"allowed": False}, "search": {"allowed": True}},
        )

        assert outcome.allowed is False
        assert outcome.reason_codes == DENY_CODES
        assert outcome.triggering_clause == "tools.file_delete.allowed"

    def test_entry_configured_true_permits_and_attributes_nothing(self):
        outcome = evaluate_tools_section(
            _execute("search"),
            {"file_delete": {"allowed": False}, "search": {"allowed": True}},
        )

        assert outcome.allowed is True
        assert outcome.reason_codes == (ReasonCode.POLICY_COMPLIANT,)
        assert outcome.triggering_clause == CLAUSE_NONE


class TestTA4DefaultDeny:
    def test_a_tool_absent_from_the_map_is_denied(self):
        outcome = evaluate_tools_section(
            _execute("unregistered_tool"), {"search": {"allowed": True}}
        )

        assert outcome.allowed is False
        assert outcome.reason_codes == DENY_CODES
        assert outcome.triggering_clause == "tools.unregistered_tool.absent"


class TestTA5AbsentAndDeniedAreDistinguishable:
    """Same action, same reason codes, different clause. The clause is the only signal."""

    def test_absent_and_denied_differ_only_in_the_clause(self):
        tool = "audit_export"
        absent = evaluate_tools_section(
            _execute(tool), {"search": {"allowed": True}}
        )
        denied = evaluate_tools_section(
            _execute(tool), {tool: {"allowed": False}, "search": {"allowed": True}}
        )

        assert absent.allowed is denied.allowed is False
        assert absent.reason_codes == denied.reason_codes == DENY_CODES

        assert absent.triggering_clause == f"tools.{tool}.absent"
        assert denied.triggering_clause == f"tools.{tool}.allowed"
        assert absent.triggering_clause != denied.triggering_clause


class TestTA6ExactMatching:
    """Case-sensitive, no normalisation, no pattern matching."""

    @pytest.mark.parametrize(
        "requested,policy_key,expectation",
        [
            ("FILE_DELETE", "file_delete", "a differently-cased name is a different tool"),
            ("Search", "search", "a permitted tool is not widened by case folding"),
            ("search ", "search", "trailing whitespace is not trimmed"),
        ],
    )
    def test_near_misses_are_absent_not_matched(
        self, requested, policy_key, expectation
    ):
        outcome = evaluate_tools_section(
            _execute(requested), {policy_key: {"allowed": True}}
        )

        assert outcome.allowed is False, expectation
        assert outcome.triggering_clause == f"tools.{requested}.absent"

    def test_a_denied_entry_is_not_matched_by_a_differently_cased_request(self):
        """The failure mode runs both ways: a near miss must not inherit a deny either.

        It lands on TA-4 and is denied as absent, which is the same action for a
        different and correctly-reported reason.
        """
        outcome = evaluate_tools_section(
            _execute("FILE_DELETE"), {"file_delete": {"allowed": False}}
        )

        assert outcome.triggering_clause == "tools.FILE_DELETE.absent"


class TestTA7AbsentSectionVersusEmptyMap:
    """The distinction that decides whether a misconfiguration opens everything."""

    def test_an_empty_map_permits_nothing(self):
        outcome, _ = evaluate_policies(_execute("anything"), {"tools": {}})

        assert outcome.allowed is False
        assert outcome.reason_codes == DENY_CODES
        assert outcome.triggering_clause == "tools.anything.absent"

    def test_an_absent_section_is_inapplicable(self):
        outcome, _ = evaluate_policies(_execute("anything"), {})

        assert outcome.allowed is True
        assert outcome.triggering_clause == CLAUSE_NONE
        assert ReasonCode.TOOL_NOT_ALLOWED not in outcome.reason_codes

    def test_a_null_section_is_treated_as_absent(self):
        """Not in the specification. Pinned here so the choice is visible and stable."""
        outcome, _ = evaluate_policies(_execute("anything"), {"tools": None})

        assert outcome.allowed is True
        assert outcome.triggering_clause == CLAUSE_NONE

    def test_no_policy_at_all_allows(self):
        """§5.3: an empty or absent policy allows, with POLICY_COMPLIANT and `none`."""
        for policies in ({}, None):
            outcome, _ = evaluate_policies(_execute("anything"), policies)

            assert outcome.allowed is True
            assert outcome.reason_codes == (ReasonCode.POLICY_COMPLIANT,)
            assert outcome.triggering_clause == CLAUSE_NONE


class TestTA8TheWildcardFallbackEntry:
    """`*` is a declared fallback, not a pattern. Precedence and attribution."""

    def test_fallback_denies_a_tool_with_no_entry_of_its_own(self):
        outcome = evaluate_tools_section(
            _execute("novel_tool"), {"*": {"allowed": False}}
        )

        assert outcome.allowed is False
        assert outcome.reason_codes == DENY_CODES
        assert outcome.triggering_clause == "tools.*.allowed"

    def test_fallback_permits_a_tool_with_no_entry_of_its_own(self):
        outcome = evaluate_tools_section(
            _execute("novel_tool"), {"*": {"allowed": True}}
        )

        assert outcome.allowed is True
        assert outcome.triggering_clause == CLAUSE_NONE

    def test_a_specific_permit_beats_a_fallback_deny(self):
        outcome = evaluate_tools_section(
            _execute("search"), {"*": {"allowed": False}, "search": {"allowed": True}}
        )

        assert outcome.allowed is True
        assert outcome.triggering_clause == CLAUSE_NONE

    def test_a_specific_deny_beats_a_fallback_permit_and_is_attributed_specifically(self):
        outcome = evaluate_tools_section(
            _execute("file_delete"),
            {"*": {"allowed": True}, "file_delete": {"allowed": False}},
        )

        assert outcome.allowed is False
        assert outcome.triggering_clause == "tools.file_delete.allowed"

    def test_a_fallback_denial_is_never_attributed_to_the_specific_tool(self):
        """TA-8(b). Without this an operator cannot tell a blanket default from a rule.

        The clause must say `*`, because that is the entry somebody wrote. Reporting
        `tools.novel_tool.allowed` would describe a line of policy that does not exist.
        """
        outcome = evaluate_tools_section(
            _execute("novel_tool"), {"*": {"allowed": False}}
        )

        assert outcome.triggering_clause == "tools.*.allowed"
        assert "novel_tool" not in outcome.triggering_clause

    def test_an_empty_map_has_no_fallback_so_ta4_still_applies(self):
        """TA-8(d). `tools: {}` contains no `*`, so it is not an escape hatch."""
        outcome = evaluate_tools_section(_execute("anything"), {})

        assert outcome.allowed is False
        assert outcome.triggering_clause == "tools.anything.absent"

    def test_the_fallback_is_the_only_way_to_opt_out_of_default_deny(self):
        """TA-8(d), stated positively: a blanket permit is explicit and auditable."""
        outcome = evaluate_tools_section(
            _execute("anything_at_all"), {"*": {"allowed": True}}
        )

        assert outcome.allowed is True


class TestMalformedPolicyIsNotAVerdict:
    """§6.1 requires `allowed` to be a boolean and does not say what to do otherwise.

    Both silent readings are bad: denying turns a typo into an outage attributed to a
    clause the author believes says `true`, and allowing turns a typo into silent
    non-enforcement. So a policy that cannot be read is raised rather than decided.

    Recorded as a specification gap. These tests pin the choice so it cannot drift while
    the gap is open.
    """

    @pytest.mark.parametrize(
        "entry",
        [
            {},
            {"allow": True},
            {"allowed": "true"},
            {"allowed": 1},
            {"allowed": None},
            "allowed",
            None,
        ],
    )
    def test_an_unreadable_entry_raises(self, entry):
        with pytest.raises(ValueError) as excinfo:
            evaluate_tools_section(_execute("file_delete"), {"file_delete": entry})

        assert "tools.file_delete" in str(excinfo.value)

    def test_a_non_mapping_tools_section_raises(self):
        with pytest.raises(ValueError) as excinfo:
            evaluate_tools_section(_execute("x"), ["file_delete"])

        assert "'tools' must be a mapping" in str(excinfo.value)

    def test_an_unreadable_entry_for_an_unrequested_tool_is_not_read(self):
        """Only the entry that governs this request is read.

        A malformed entry elsewhere in the policy is a real problem, but failing the
        request it does not govern would make one bad line deny everything. Validating
        the whole document belongs at configuration time, not per request.
        """
        outcome = evaluate_tools_section(
            _execute("search"),
            {"search": {"allowed": True}, "broken": {"allowed": "yes"}},
        )

        assert outcome.allowed is True


class TestAggregationAcrossSections:
    def test_aggregation_is_and(self):
        """§5.3: allowed only if every applicable section allows."""
        allow = ClauseOutcome(
            allowed=True,
            reason_codes=(ReasonCode.POLICY_COMPLIANT,),
            triggering_clause=CLAUSE_NONE,
            reason="ok",
        )
        deny = ClauseOutcome(
            allowed=False,
            reason_codes=DENY_CODES,
            triggering_clause="tools.x.allowed",
            reason="no",
        )

        assert aggregate_outcomes([allow, allow]).allowed is True
        assert aggregate_outcomes([allow, deny]).allowed is False
        assert aggregate_outcomes([deny, allow]).allowed is False
        assert aggregate_outcomes([]).allowed is True

    def test_the_first_denial_supplies_the_attribution(self):
        """§5.2 permits short-circuiting, so the clause must be the one that decided."""
        first = ClauseOutcome(
            allowed=False,
            reason_codes=DENY_CODES,
            triggering_clause="tools.a.allowed",
            reason="first",
        )
        second = ClauseOutcome(
            allowed=False,
            reason_codes=DENY_CODES,
            triggering_clause="tools.b.allowed",
            reason="second",
        )

        assert aggregate_outcomes([first, second]).triggering_clause == "tools.a.allowed"


class TestUnevaluatedSectionsAreVisible:
    """An unimplemented section must never be folded silently into an allow."""

    def test_unsupported_sections_are_reported(self):
        outcome, unsupported = evaluate_policies(
            _execute("search"),
            {
                "tools": {"search": {"allowed": True}},
                "content": {"pii": {"action": "deny"}},
                "codeExecution": {"allowedLanguages": ["python"]},
            },
        )

        assert outcome.allowed is True
        assert set(unsupported) == {"content", "codeExecution"}

    def test_the_supported_set_is_exactly_tools(self):
        """If this changes, §9.1's published support claim must change with it."""
        assert SUPPORTED_RULE_TYPES == ("tools",)

    def test_a_null_section_is_not_reported_as_unevaluated(self):
        assert unsupported_sections({"content": None}) == ()

    def test_no_policy_has_nothing_unevaluated(self):
        assert unsupported_sections(None) == ()
        assert unsupported_sections({}) == ()


class TestDeterminism:
    """§3.6: identical inputs produce identical outputs, including code order."""

    def test_repeated_evaluation_is_identical(self):
        policy = {"*": {"allowed": True}, "file_delete": {"allowed": False}}
        context = _execute("file_delete")

        first = evaluate_tools_section(context, policy)
        rest = [evaluate_tools_section(context, policy) for _ in range(20)]

        assert all(outcome == first for outcome in rest)

    def test_reason_code_order_is_fixed(self):
        """POLICY_VIOLATION first, then the specific code. TA-2 spells the order out."""
        outcome = evaluate_tools_section(
            _execute("file_delete"), {"file_delete": {"allowed": False}}
        )

        assert outcome.reason_codes == (
            ReasonCode.POLICY_VIOLATION,
            ReasonCode.TOOL_NOT_ALLOWED,
        )

    def test_key_insertion_order_does_not_affect_the_outcome(self):
        """§3.6 forbids depending on map iteration order."""
        a = evaluate_tools_section(
            _execute("file_delete"),
            {"*": {"allowed": True}, "file_delete": {"allowed": False}},
        )
        b = evaluate_tools_section(
            _execute("file_delete"),
            {"file_delete": {"allowed": False}, "*": {"allowed": True}},
        )

        assert a == b


class TestOutcomeCannotBeVacuous:
    def test_a_denying_outcome_must_name_a_clause(self):
        with pytest.raises(ValueError):
            ClauseOutcome(
                allowed=False,
                reason_codes=DENY_CODES,
                triggering_clause=CLAUSE_NONE,
                reason="denied by nothing in particular",
            )

    def test_outcomes_are_immutable(self):
        """§3.6's determinism is easier to keep if the result cannot be edited later."""
        outcome = evaluate_tools_section(
            _execute("file_delete"), {"file_delete": {"allowed": False}}
        )

        with pytest.raises(FrozenInstanceError):
            outcome.allowed = True  # type: ignore[misc]
