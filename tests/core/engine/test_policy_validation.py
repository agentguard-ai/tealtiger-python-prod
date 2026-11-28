"""Tests for policy validation and simulation.

Two properties matter more than the individual cases, and each has a test that states it
directly:

- **The validator cannot pass a policy the engine would reject** — it asks the evaluator's
  own entry reader rather than re-deriving the rules, so there is no second opinion to
  drift.
- **The simulator agrees with the engine exactly** — it *is* the engine. A dry run that
  predicts from a lookalike evaluator is the defect this module was written instead of
  porting.
"""

import pytest

from tealtiger.core.engine import ModeConfig, PolicyMode, ReasonCode, TealEngine
from tealtiger.core.engine.policy_simulation import simulate_policy
from tealtiger.core.engine.policy_validation import WARNING, validate_policy

GOOD = {"tools": {"search": {"allowed": True}, "file_delete": {"allowed": False}}}

REQUESTS = [
    {"agentId": "a", "action": "tool.execute", "tool": "search"},
    {"agentId": "a", "action": "tool.execute", "tool": "file_delete"},
    {"agentId": "a", "action": "tool.execute", "tool": "unregistered"},
    {"agentId": "a", "action": "chat.create"},
]


def _codes(result):
    return [f.code for f in result.findings]


class TestAWellFormedPolicyPasses:
    def test_a_tool_policy_is_accepted_without_findings(self):
        result = validate_policy(GOOD)

        assert result.well_formed is True
        assert result.enforceable_here is True
        assert result.findings == ()
        assert bool(result) is True

    def test_the_wildcard_fallback_is_valid(self):
        result = validate_policy({"tools": {"*": {"allowed": False}}})

        assert result.well_formed is True
        assert result.enforceable_here is True
        assert result.errors == ()


class TestStructuralErrors:
    def test_a_non_mapping_document_is_rejected(self):
        result = validate_policy(["tools"])

        assert result.well_formed is False
        assert _codes(result) == ["POLICY_NOT_A_MAPPING"]

    def test_a_non_mapping_tools_section_is_rejected(self):
        result = validate_policy({"tools": ["search"]})

        assert result.well_formed is False
        assert "SECTION_NOT_A_MAPPING" in _codes(result)

    @pytest.mark.parametrize(
        "entry",
        [{}, {"allow": True}, {"allowed": "true"}, {"allowed": 1}, {"allowed": None}, None],
    )
    def test_an_unreadable_entry_is_rejected(self, entry):
        result = validate_policy({"tools": {"file_delete": entry}})

        assert result.well_formed is False
        assert "TOOL_ENTRY_UNREADABLE" in _codes(result)
        assert any("tools.file_delete" in f.path for f in result.errors)

    def test_every_bad_entry_is_reported_not_just_the_first(self):
        """The engine raises on the first one it reaches; a config check should not.

        Reporting one problem per run turns fixing a policy into a guessing loop.
        """
        result = validate_policy(
            {
                "tools": {
                    "a": {"allowed": "yes"},
                    "b": {},
                    "c": {"allowed": True},
                    "d": {"allowed": 0},
                }
            }
        )

        bad_paths = {f.path for f in result.errors}
        assert bad_paths == {"tools.a", "tools.b", "tools.d"}


class TestWellFormedIsNotTheSameAsEnforceableHere:
    """The distinction that stops the validator lying in either direction."""

    def test_an_unenforceable_section_is_well_formed_but_not_enforceable(self):
        """A content policy is a legitimate document this SDK declines to evaluate.

        Calling it malformed would be wrong — it is valid, and a more capable
        implementation enforces it. Calling it enforceable would be worse.
        """
        result = validate_policy({"content": {"pii": {"action": "deny"}}})

        assert result.well_formed is True
        assert result.enforceable_here is False
        assert "SECTION_NOT_ENFORCEABLE" in _codes(result)
        assert bool(result) is False

    def test_a_mixed_policy_is_not_enforceable_here(self):
        result = validate_policy(
            {"tools": {"search": {"allowed": True}}, "content": {"pii": "deny"}}
        )

        assert result.well_formed is True
        assert result.enforceable_here is False

    def test_the_error_names_the_section_and_what_is_enforced(self):
        result = validate_policy({"codeExecution": {"allowedLanguages": ["python"]}})

        message = result.errors[0].message
        assert "codeExecution" in result.errors[0].path
        assert "tools" in message


class TestWarningsForThingsThatAreLegalAndProbablyWrong:
    def test_an_empty_tool_map_warns_that_it_permits_nothing(self):
        result = validate_policy({"tools": {}})

        assert result.well_formed is True
        assert result.enforceable_here is True
        assert "TOOL_MAP_EMPTY" in _codes(result)
        assert all(f.severity == WARNING for f in result.findings)

    def test_a_null_tools_section_warns_that_it_is_treated_as_absent(self):
        """TA-7's distinction is load-bearing, and `null` is the third case.

        Treated as absent, which means no tool is checked — the opposite of `{}`.
        """
        result = validate_policy({"tools": None})

        assert "SECTION_NULL" in _codes(result)
        assert result.well_formed is True

    def test_a_permissive_wildcard_warns_that_default_deny_is_off(self):
        result = validate_policy({"tools": {"*": {"allowed": True}}})

        assert result.enforceable_here is True
        assert "WILDCARD_PERMITS_EVERYTHING" in _codes(result)

    def test_a_restrictive_wildcard_does_not_warn(self):
        result = validate_policy({"tools": {"*": {"allowed": False}}})

        assert "WILDCARD_PERMITS_EVERYTHING" not in _codes(result)

    def test_whitespace_in_a_tool_name_warns(self):
        """TA-6: names match exactly, so ' search' matches nothing a client sends."""
        result = validate_policy({"tools": {"search ": {"allowed": True}}})

        assert "TOOL_NAME_HAS_WHITESPACE" in _codes(result)

    def test_no_policy_warns_that_nothing_is_enforced(self):
        result = validate_policy(None)

        assert result.well_formed is True
        assert "NO_POLICY" in _codes(result)

    def test_a_document_with_no_enforceable_section_warns(self):
        result = validate_policy({})

        assert "NOTHING_ENFORCED" in _codes(result)
        assert result.enforceable_here is True


class TestTheValidatorCannotDisagreeWithTheEngine:
    """The no-drift property, asserted rather than assumed.

    Both halves matter. If the validator passed something the engine rejects, a caller
    would deploy a policy that fails on the first request. If it rejected something the
    engine accepts, it would block working configurations.
    """

    MALFORMED = [
        {"tools": {"x": {"allowed": "yes"}}},
        {"tools": {"x": {}}},
        {"tools": {"x": None}},
        {"tools": ["x"]},
    ]

    ACCEPTED = [
        GOOD,
        {"tools": {}},
        {"tools": None},
        {},
        {"tools": {"*": {"allowed": True}}},
        {"tools": {"*": {"allowed": False}, "search": {"allowed": True}}},
    ]

    @pytest.mark.parametrize("policy", MALFORMED)
    def test_what_the_validator_rejects_the_engine_also_rejects(self, policy):
        assert validate_policy(policy).well_formed is False

        engine = TealEngine(policies=policy, mode=ModeConfig(default=PolicyMode.ENFORCE))
        with pytest.raises((ValueError, TypeError)):
            engine.evaluate_with_mode(
                {"agentId": "a", "action": "tool.execute", "tool": "x"}
            )

    @pytest.mark.parametrize("policy", ACCEPTED)
    def test_what_the_validator_accepts_the_engine_evaluates(self, policy):
        result = validate_policy(policy)
        assert result.well_formed is True
        assert result.enforceable_here is True

        engine = TealEngine(
            policies=dict(policy or {}), mode=ModeConfig(default=PolicyMode.ENFORCE)
        )
        decision = engine.evaluate_with_mode(
            {"agentId": "a", "action": "tool.execute", "tool": "search"}
        )
        assert decision.triggering_clause  # produced a decision, whatever it was

    def test_an_unenforceable_policy_is_flagged_and_the_engine_refuses_it(self):
        policy = {"content": {"pii": "deny"}}

        assert validate_policy(policy).enforceable_here is False

        engine = TealEngine(policies=policy)
        with pytest.raises(NotImplementedError):
            engine.evaluate_with_mode({"agentId": "a", "action": "chat.create"})


class TestSimulationUsesTheRealEngine:
    def test_the_report_names_the_evaluator(self):
        """So a reader can tell a preview from a guess."""
        report = simulate_policy(GOOD, REQUESTS)

        assert report.evaluated_by.startswith("TealEngine ")

    def test_decisions_match_the_engine_exactly(self):
        """The property the whole module exists for.

        If simulation and production can differ, the dry run is advice about a
        different system.
        """
        report = simulate_policy(GOOD, REQUESTS)
        engine = TealEngine(policies=GOOD, mode=ModeConfig(default=PolicyMode.ENFORCE))

        for simulated, request in zip(report.decisions, REQUESTS):
            live = engine.evaluate_with_mode(dict(request))

            assert simulated.action == live.action.value
            assert simulated.reason_codes == tuple(c.value for c in live.reason_codes)
            assert simulated.triggering_clause == live.triggering_clause

    def test_it_counts_allowed_and_denied(self):
        report = simulate_policy(GOOD, REQUESTS)

        assert report.allowed == 2  # search, chat.create
        assert report.denied == 2  # file_delete, unregistered
        assert len(report.decisions) == len(REQUESTS)

    def test_it_reports_which_clause_did_the_work(self):
        report = simulate_policy(GOOD, REQUESTS)

        assert report.by_clause == {
            "none": 2,
            "tools.file_delete.allowed": 1,
            "tools.unregistered.absent": 1,
        }

    def test_monitor_mode_shows_what_would_have_been_blocked(self):
        """The rollout question: allowed now, and here is what would have been denied."""
        report = simulate_policy(GOOD, REQUESTS, mode=PolicyMode.MONITOR)

        assert report.mode == "MONITOR"
        assert report.denied == 0
        assert report.allowed == len(REQUESTS)

        would_deny = [
            d for d in report.decisions if d.triggering_clause != "none"
        ]
        assert {d.triggering_clause for d in would_deny} == {
            "tools.file_delete.allowed",
            "tools.unregistered.absent",
        }
        assert all(
            ReasonCode.MONITOR_MODE_VIOLATION.value in d.reason_codes for d in would_deny
        )

    def test_warnings_survive_a_successful_simulation(self):
        """A simulation that ran is not the same as a policy with nothing to flag."""
        report = simulate_policy({"tools": {"*": {"allowed": True}}}, REQUESTS[:1])

        assert report.allowed == 1
        assert "WILDCARD_PERMITS_EVERYTHING" in [
            f.code for f in report.validation.warnings
        ]


class TestSimulationRefusesRatherThanReturningNothing:
    """Zero decisions must never be mistakable for zero denials."""

    def test_an_unenforceable_policy_raises(self):
        with pytest.raises(ValueError) as excinfo:
            simulate_policy({"content": {"pii": "deny"}}, REQUESTS)

        message = str(excinfo.value)
        assert "SECTION_NOT_ENFORCEABLE" in message
        assert "nothing would be denied" in message

    def test_a_malformed_policy_raises(self):
        with pytest.raises(ValueError) as excinfo:
            simulate_policy({"tools": {"x": {"allowed": "yes"}}}, REQUESTS)

        assert "TOOL_ENTRY_UNREADABLE" in str(excinfo.value)

    def test_the_error_lists_every_problem(self):
        with pytest.raises(ValueError) as excinfo:
            simulate_policy(
                {"tools": {"a": {"allowed": "yes"}, "b": {}}, "content": {"pii": "x"}},
                REQUESTS,
            )

        message = str(excinfo.value)
        assert "tools.a" in message
        assert "tools.b" in message
        assert "content" in message

    def test_an_empty_request_list_is_an_empty_report_not_an_error(self):
        """No requests is a legitimate thing to ask, unlike an unusable policy."""
        report = simulate_policy(GOOD, [])

        assert report.decisions == ()
        assert report.allowed == report.denied == 0
