#!/usr/bin/env python
"""Run the shared conformance corpus against this build of the Python SDK.

Obligations from §8.3 of the policy conformance specification:

  H-1  report the identity of the build under test
  H-2  fail loudly if the loaded build is not the intended one
  H-3  score by the same rules as every other implementation
  H-4  report per-category outcomes, never a bare pass rate

Usage:
    CONFORMANCE_CORPUS=/path/to/suites/tool-allowlist.v0.1.json python conformance_harness.py

Exit codes:
    0  every case passed
    1  at least one case failed
    2  the harness could not establish what it was testing (H-2)

The corpus is deliberately **not** vendored into this repository. §8.1 requires it to be
shared across implementations, and a per-SDK copy is a copy that drifts — the drift
between privately held corpora is what left the two SDKs with 3 shared test inputs out of
69 and 25.
"""

import importlib.metadata
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Overridable because a fixed path in the repository root is only convenient for the one
# caller that runs this once per checkout. Anything else — two suites in a row, a local
# run you do not want to overwrite, a test of the harness itself — silently clobbers the
# previous result, and a results file that might belong to an earlier run is not evidence.
RESULTS_PATH = Path(
    os.environ.get("CONFORMANCE_RESULTS", REPO_ROOT / "conformance-results.json")
)

# ── H-2, part one: load the build under test from THIS repository ───────────────
#
# This is not boilerplate caution. During the measurement work that produced the
# specification, ambient Python silently imported `tealtiger` 1.0.0 from a user's AppData
# directory instead of the repository, and every number taken from that run would have
# been meaningless. An earlier false finding in a published release note came from
# exactly this cause.
#
# Putting src/ first is the fix; asserting where the module actually came from is the
# proof. The assertion is the part that matters, because the path insertion can be
# defeated by an editable install pointing somewhere else.
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import tealtiger
    from tealtiger.core.engine import ModeConfig, PolicyMode, TealEngine
    from tealtiger.core.engine.policy_evaluator import RULE_TYPE_SUPPORT
except Exception as exc:  # noqa: BLE001
    print(f"H-2 FAILED: cannot import the SDK under test: {exc}", file=sys.stderr)
    sys.exit(2)

module_path = Path(tealtiger.__file__).resolve()

try:
    package_version = importlib.metadata.version("tealtiger")
except importlib.metadata.PackageNotFoundError:
    package_version = "unknown (not installed as a distribution)"

# ── H-1: say what is being tested, before saying how it scored ──────────────────
print("build under test")
print(f"  package : tealtiger {package_version}")
print(f"  module  : {module_path}")
print(f"  runtime : Python {sys.version.split()[0]}")

# ── H-2, part two: refuse to score a build we cannot vouch for ──────────────────
if REPO_ROOT not in module_path.parents:
    print(
        f"\nH-2 FAILED: the SDK resolved outside the repository under test."
        f"\n  expected under : {REPO_ROOT}"
        f"\n  actually from  : {module_path}"
        "\n\nA conformance result measured against an unknown build is worse than no "
        "result, because it looks like evidence.",
        file=sys.stderr,
    )
    sys.exit(2)

corpus_env = os.environ.get("CONFORMANCE_CORPUS")
if not corpus_env:
    print(
        "\nH-2 FAILED: CONFORMANCE_CORPUS is not set, so there is no corpus to run."
        "\nPoint it at a suite file, e.g. suites/tool-allowlist.v0.1.json from"
        "\nagentguard-ai/tealtiger-conformance.",
        file=sys.stderr,
    )
    sys.exit(2)

corpus_path = Path(corpus_env).resolve()
if not corpus_path.is_file():
    print(f"\nH-2 FAILED: corpus not found at {corpus_path}", file=sys.stderr)
    sys.exit(2)

suite = json.loads(corpus_path.read_text(encoding="utf-8"))

print("\ncorpus under test")
print(f"  file    : {corpus_path}")
print(f"  suite   : {suite.get('suite_id', 'unstated')}")
print(f"  spec    : {suite.get('spec_version', 'unstated')}")
print(f"  registry: {suite.get('registry', 'unstated')}")

# §9.1: state the support claim alongside the score, so a reader can see which rule
# types the number covers. A pass rate without that is unreadable — an implementation
# enforcing one rule type perfectly and an implementation enforcing none can both
# report 100% of the cases they were given.
enforced = sorted(n for n, state in RULE_TYPE_SUPPORT.items() if state == "enforced")
print(f"\ndeclared support (spec 9.1)\n  enforced: {', '.join(enforced)}")

# ── H-3: judgement rules, applied identically to every case ────────────────────
#
# The same four checks the TypeScript harness applies, in the same order, producing the
# same categories. §8.3 H-3 requires it: a result that is not comparable across
# implementations cannot settle a disagreement between them, which is the entire purpose
# of having a shared corpus.
outcomes = []

for case in suite["tests"]:
    expected = case["expected"]
    failures = []
    actual = None
    category = "PASS"

    try:
        engine = TealEngine(
            policies=case.get("policy") or {},
            mode=ModeConfig(default=PolicyMode.ENFORCE),
        )
        decision = engine.evaluate_with_mode(dict(case["input"]["request"]))

        actual = {
            "action": decision.action.value,
            "reason_codes": [c.value for c in decision.reason_codes],
            "triggering_clause": decision.triggering_clause,
        }

        if actual["action"] != expected["decision_action"]:
            failures.append(
                f"action: expected {expected['decision_action']}, got {actual['action']}"
            )
            category = "WRONG_ACTION"

        missing = [
            c for c in expected.get("reason_codes", []) if c not in actual["reason_codes"]
        ]
        if missing:
            failures.append(f"missing reason codes: {', '.join(missing)}")
            if category == "PASS":
                category = "WRONG_CODES"

        forbidden = [
            c
            for c in expected.get("reason_codes_absent", [])
            if c in actual["reason_codes"]
        ]
        if forbidden:
            failures.append(f"forbidden reason codes present: {', '.join(forbidden)}")
            if category == "PASS":
                category = "WRONG_CODES"

        # CV-2: a correct verdict from the wrong clause is not a pass. This is the check
        # that distinguishes governing from coinciding, and the reason the field exists.
        if actual["triggering_clause"] != expected["triggering_clause"]:
            failures.append(
                f"triggering_clause: expected {expected['triggering_clause']}, "
                f"got {actual['triggering_clause']}"
            )
            if category == "PASS":
                category = "WRONG_MECHANISM"

    except Exception as exc:  # noqa: BLE001
        failures.append(f"exception: {type(exc).__name__}: {exc}")
        category = "ERROR"

    outcomes.append(
        {
            "test_id": case["test_id"],
            "passed": not failures,
            "category": "PASS" if not failures else category,
            "failures": failures,
            "actual": actual,
        }
    )

# ── H-4: per-category outcomes, never a bare pass rate ─────────────────────────
#
# A single percentage ranked a do-nothing engine above a partly-working one on the
# original corpus: Python scored 9/69 against TypeScript's 8/69 while denying nothing at
# all, because allowing everything satisfies every ALLOW-expecting case. The split below
# is what makes that visible.
by_category = {}
for outcome in outcomes:
    by_category[outcome["category"]] = by_category.get(outcome["category"], 0) + 1

total = len(outcomes)
passed = sum(1 for o in outcomes if o["passed"])

print("\noutcomes by category")
for category, count in sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0])):
    print(f"  {category:<16} {count}")

deny_expected = [
    i for i, c in enumerate(suite["tests"]) if c["expected"]["decision_action"] == "DENY"
]
deny_passed = sum(1 for i in deny_expected if outcomes[i]["passed"])
allow_total = total - len(deny_expected)
allow_passed = passed - deny_passed

print("\ngovernance signal")
print(f"  DENY-expecting cases passed : {deny_passed}/{len(deny_expected)}")
print(f"  ALLOW-expecting cases passed: {allow_passed}/{allow_total}")

if passed < total:
    print("\nfailures")
    for outcome in (o for o in outcomes if not o["passed"]):
        print(f"  {outcome['test_id']}  [{outcome['category']}]")
        for failure in outcome["failures"]:
            print(f"      {failure}")
        if outcome["actual"]:
            codes = ",".join(outcome["actual"]["reason_codes"])
            print(
                f"      actual: {outcome['actual']['action']} "
                f"clause={outcome['actual']['triggering_clause']} codes=[{codes}]"
            )

RESULTS_PATH.write_text(
    json.dumps(
        {
            "build": {
                "package": f"tealtiger@{package_version}",
                "module": str(module_path),
                "runtime": f"Python {sys.version.split()[0]}",
            },
            "declared_support": RULE_TYPE_SUPPORT,
            "suite": suite.get("suite_id"),
            "spec_version": suite.get("spec_version"),
            "total": total,
            "passed": passed,
            "by_category": by_category,
            "governance_signal": {
                "deny_expecting_passed": deny_passed,
                "deny_expecting_total": len(deny_expected),
                "allow_expecting_passed": allow_passed,
                "allow_expecting_total": allow_total,
            },
            "outcomes": outcomes,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

print(f"\n{passed}/{total} pass")
print(f"results written to {RESULTS_PATH}")

sys.exit(0 if passed == total else 1)
