"""Tests for the conformance harness's own obligations (spec §8.3).

The harness is the thing that says whether this SDK conforms, so a harness that reports
green when it could not establish what it was testing is worse than no harness. H-2
exists because that already happened: during the measurement work behind the
specification, ambient Python silently imported `tealtiger` 1.0.0 from a user's AppData
directory instead of the repository, and an earlier false finding in a published release
note came from exactly that cause.

These run it as a subprocess, because exit codes and refusal behaviour are the contract.
A harness that raised an exception instead of exiting 2 would still look like a failure
in CI but would not say *why*, and the distinction between "this build does not conform"
(exit 1) and "I cannot tell you anything about this build" (exit 2) is the whole point.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "conformance_harness.py"

MINIMAL_SUITE = {
    "suite_id": "harness-self-test",
    "spec_version": "policy-conformance-spec v0.1",
    "tests": [
        {
            "test_id": "deny-configured-tool",
            "targets": "tools.file_delete.allowed",
            "policy": {"tools": {"file_delete": {"allowed": False}}},
            "input": {
                "request": {
                    "agentId": "a",
                    "action": "tool.execute",
                    "tool": "file_delete",
                }
            },
            "expected": {
                "decision_action": "DENY",
                "reason_codes": ["POLICY_VIOLATION", "TOOL_NOT_ALLOWED"],
                "triggering_clause": "tools.file_delete.allowed",
            },
        }
    ],
}


def _run(corpus, suite=None, tmp_path=None, results_path=None):
    """Invoke the harness once.

    Each call costs a full SDK import, so runs are shared via module-scoped fixtures
    wherever the input is the same. Tests that need a different corpus get their own.
    """
    if suite is not None:
        corpus = tmp_path / "suite.json"
        corpus.write_text(json.dumps(suite), encoding="utf-8")

    env = dict(os.environ)
    if corpus is None:
        env.pop("CONFORMANCE_CORPUS", None)
    else:
        env["CONFORMANCE_CORPUS"] = str(corpus)

    # Keep each run's results out of the repository root and out of each other's way.
    if results_path is None and tmp_path is not None:
        results_path = tmp_path / "harness-results.json"
    if results_path is not None:
        env["CONFORMANCE_RESULTS"] = str(results_path)

    return subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _variant(**expected_overrides):
    """The minimal suite with its single case's expectations altered."""
    suite = json.loads(json.dumps(MINIMAL_SUITE))
    suite["tests"][0]["expected"].update(expected_overrides)
    return suite


@pytest.fixture(scope="module")
def passing_run(tmp_path_factory):
    """One successful run, shared by every test that only reads its output."""
    tmp_path = tmp_path_factory.mktemp("passing")
    return _run(None, suite=MINIMAL_SUITE, tmp_path=tmp_path)


@pytest.fixture(scope="module")
def no_corpus_run(tmp_path_factory):
    return _run(
        corpus=None,
        results_path=tmp_path_factory.mktemp("no-corpus") / "results.json",
    )


class TestH2RefusesToScoreWhatItCannotIdentify:
    """Exit 2 means "I cannot tell you anything", not "this build failed"."""

    def test_no_corpus_configured_exits_2(self, no_corpus_run):
        assert no_corpus_run.returncode == 2
        assert "H-2 FAILED" in no_corpus_run.stderr
        assert "CONFORMANCE_CORPUS" in no_corpus_run.stderr

    def test_a_missing_corpus_file_exits_2(self, tmp_path):
        result = _run(corpus=tmp_path / "does-not-exist.json")

        assert result.returncode == 2
        assert "H-2 FAILED" in result.stderr
        assert "corpus not found" in result.stderr

    def test_exit_2_is_distinct_from_a_conformance_failure(
        self, no_corpus_run, passing_run
    ):
        """The codes must not collide, or CI cannot tell the two apart."""
        assert no_corpus_run.returncode == 2
        assert passing_run.returncode == 0


class TestH1ReportsWhatItTested:
    def test_the_build_identity_comes_before_the_score(self, passing_run):
        assert passing_run.returncode == 0
        assert "build under test" in passing_run.stdout
        assert "package : tealtiger" in passing_run.stdout

        # Identity first, so a reader cannot absorb a number before knowing what
        # produced it.
        assert passing_run.stdout.index("build under test") < passing_run.stdout.index(
            "pass"
        )

    def test_the_module_path_under_test_is_reported(self, passing_run):
        assert "module  :" in passing_run.stdout
        assert str(REPO_ROOT) in passing_run.stdout

    def test_the_corpus_identity_is_reported(self, passing_run):
        assert "harness-self-test" in passing_run.stdout
        assert "policy-conformance-spec v0.1" in passing_run.stdout

    def test_the_declared_support_claim_is_reported(self, passing_run):
        """A pass rate is unreadable without knowing which rule types it covers."""
        assert "declared support" in passing_run.stdout
        assert "enforced: tools" in passing_run.stdout


class TestH4ReportsCategoriesNotJustARate:
    def test_outcomes_are_broken_down_by_category(self, passing_run):
        assert "outcomes by category" in passing_run.stdout
        assert "PASS" in passing_run.stdout

    def test_deny_and_allow_cases_are_counted_separately(self, passing_run):
        """The split that stops a do-nothing engine outranking a working one.

        On the original corpus Python scored 9/69 against TypeScript's 8/69 while
        denying nothing at all, because allowing everything satisfies every
        ALLOW-expecting case. A single rate hid that; this split cannot.
        """
        assert "governance signal" in passing_run.stdout
        assert "DENY-expecting cases passed : 1/1" in passing_run.stdout
        assert "ALLOW-expecting cases passed: 0/0" in passing_run.stdout


class TestFailureReporting:
    """Each needs its own corpus, so each pays for its own run."""

    def test_a_wrong_clause_fails_the_case_and_is_named_as_such(self, tmp_path):
        """CV-2: a correct verdict reached by the wrong clause is not a pass.

        The engine returns the right action and the right reason codes here. Only the
        clause differs, and that alone must fail the case — otherwise the corpus cannot
        tell governing from coinciding.
        """
        result = _run(
            None,
            suite=_variant(triggering_clause="tools.file_delete.absent"),
            tmp_path=tmp_path,
        )

        assert result.returncode == 1
        assert "WRONG_MECHANISM" in result.stdout
        assert "triggering_clause" in result.stdout

    def test_a_wrong_action_is_categorised_separately(self, tmp_path):
        result = _run(None, suite=_variant(decision_action="ALLOW"), tmp_path=tmp_path)

        assert result.returncode == 1
        assert "WRONG_ACTION" in result.stdout

    def test_an_unenforceable_policy_is_reported_as_an_error_not_a_pass(self, tmp_path):
        """A case whose policy this SDK refuses must not be scored as conforming."""
        suite = json.loads(json.dumps(MINIMAL_SUITE))
        suite["tests"][0]["policy"] = {"content": {"pii": {"action": "deny"}}}

        result = _run(None, suite=suite, tmp_path=tmp_path)

        assert result.returncode == 1
        assert "ERROR" in result.stdout
        assert "UnsupportedPolicySectionError" in result.stdout


class TestResultsArtifact:
    def test_results_are_written_for_ci_to_upload(self, tmp_path):
        """Written to its own path, so one run's result is never read as another's.

        This test needs its own run precisely because the output path is shared state;
        reusing `passing_run` would read whichever run happened to finish last.
        """
        results_path = tmp_path / "results.json"
        result = _run(
            None,
            suite=MINIMAL_SUITE,
            tmp_path=tmp_path,
            results_path=results_path,
        )

        assert result.returncode == 0
        assert results_path.is_file()

        data = json.loads(results_path.read_text(encoding="utf-8"))

        # The build identity travels with the number. A conformance result detached
        # from the build that produced it is not evidence of anything.
        assert data["build"]["package"].startswith("tealtiger@")
        assert str(REPO_ROOT) in data["build"]["module"]
        assert data["declared_support"]["tools"] == "enforced"
        assert data["passed"] == data["total"] == 1
        assert data["governance_signal"]["deny_expecting_passed"] == 1
