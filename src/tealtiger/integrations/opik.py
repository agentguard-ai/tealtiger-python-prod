"""TealTiger governance evaluation metrics for Opik.

Evaluate governance policy correctness using Opik's evaluation framework.
Tests whether your policies make the right decisions: block PII, allow clean
inputs, enforce budgets, and catch unauthorized tool calls.

Usage:
    from opik.evaluation import evaluate
    from tealtiger.integrations.opik import (
        GovernanceAccuracyMetric,
        PIIDetectionMetric,
        FalsePositiveRateMetric,
    )

    evaluate(
        dataset=my_dataset,
        task=governance_task,
        scoring_metrics=[
            GovernanceAccuracyMetric(),
            PIIDetectionMetric(),
            FalsePositiveRateMetric(),
        ],
    )
"""

from __future__ import annotations

from typing import Any, List

try:
    from opik.evaluation.metrics import base_metric, score_result
except ImportError:
    raise ImportError(
        "opik is required for this integration. "
        "Install it with: pip install opik"
    )


class GovernanceAccuracyMetric(base_metric.BaseMetric):
    """Evaluate whether governance made the correct decision.

    Compares the actual governance action (ALLOW/DENY) against an expected
    action from the dataset. Returns 1.0 for correct, 0.0 for incorrect.

    Dataset format:
        {"input": "text to evaluate", "expected_output": "ALLOW" or "DENY"}

    Task output format:
        {"output": "ALLOW" or "DENY"}
    """

    def __init__(self, name: str = "governance_accuracy"):
        super().__init__(name)

    def score(
        self,
        output: str,
        expected_output: str = "",
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        """Score whether governance decision matches expected outcome."""
        actual = output.strip().upper() if output else ""
        expected = expected_output.strip().upper() if expected_output else ""

        is_correct = actual == expected

        reason = (
            f"Correct: governance returned {actual} as expected"
            if is_correct
            else f"Incorrect: expected {expected}, got {actual}"
        )

        return score_result.ScoreResult(
            value=1.0 if is_correct else 0.0,
            name=self.name,
            reason=reason,
        )


class PIIDetectionMetric(base_metric.BaseMetric):
    """Evaluate PII detection accuracy.

    Tests whether governance correctly identifies PII in inputs.
    Returns 1.0 if PII detection matches expectation, 0.0 otherwise.

    Dataset format:
        {"input": "text", "expected_output": "pii_found" or "no_pii"}

    Task output format:
        {"output": "pii_found" or "no_pii"}
    """

    def __init__(self, name: str = "pii_detection_accuracy"):
        super().__init__(name)

    def score(
        self,
        output: str,
        expected_output: str = "",
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        """Score PII detection accuracy."""
        actual = output.strip().lower() if output else ""
        expected = expected_output.strip().lower() if expected_output else ""

        is_correct = actual == expected

        if is_correct and expected == "pii_found":
            reason = "True positive: PII correctly detected"
        elif is_correct and expected == "no_pii":
            reason = "True negative: clean input correctly passed"
        elif not is_correct and expected == "pii_found":
            reason = "False negative: PII missed — governance failed to detect"
        else:
            reason = "False positive: clean input incorrectly flagged as PII"

        return score_result.ScoreResult(
            value=1.0 if is_correct else 0.0,
            name=self.name,
            reason=reason,
        )


class FalsePositiveRateMetric(base_metric.BaseMetric):
    """Measure false positive rate of governance policies.

    Specifically tests cases where the expected outcome is ALLOW —
    returns 0.0 if governance incorrectly denied (false positive),
    1.0 if governance correctly allowed.

    Dataset format:
        {"input": "clean text that should be allowed", "expected_output": "ALLOW"}

    Task output format:
        {"output": "ALLOW" or "DENY"}
    """

    def __init__(self, name: str = "false_positive_rate"):
        super().__init__(name)

    def score(
        self,
        output: str,
        expected_output: str = "",
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        """Score false positive rate (lower is better for the 0.0 case)."""
        actual = output.strip().upper() if output else ""
        expected = expected_output.strip().upper() if expected_output else ""

        # Only relevant for cases where expected is ALLOW
        if expected != "ALLOW":
            return score_result.ScoreResult(
                value=1.0,
                name=self.name,
                reason="N/A: expected action is not ALLOW (not a false positive test)",
            )

        is_false_positive = actual == "DENY"

        return score_result.ScoreResult(
            value=0.0 if is_false_positive else 1.0,
            name=self.name,
            reason=(
                "False positive: legitimate input was denied"
                if is_false_positive
                else "Correct: legitimate input was allowed"
            ),
        )


class GovernanceLatencyMetric(base_metric.BaseMetric):
    """Evaluate governance evaluation latency.

    Returns 1.0 if evaluation completed within the threshold (default 5ms),
    0.0 if it exceeded the threshold.

    Task output format:
        {"output": "2.3"} (evaluation time in ms as string)
    """

    def __init__(self, name: str = "governance_latency", threshold_ms: float = 5.0):
        super().__init__(name)
        self._threshold_ms = threshold_ms

    def score(
        self,
        output: str,
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        """Score whether governance evaluation met latency threshold."""
        try:
            latency_ms = float(output.strip()) if output else 0.0
        except (ValueError, TypeError):
            return score_result.ScoreResult(
                value=0.0,
                name=self.name,
                reason=f"Invalid latency value: {output}",
            )

        within_threshold = latency_ms <= self._threshold_ms

        return score_result.ScoreResult(
            value=1.0 if within_threshold else 0.0,
            name=self.name,
            reason=(
                f"Within threshold: {latency_ms:.2f}ms <= {self._threshold_ms}ms"
                if within_threshold
                else f"Exceeded threshold: {latency_ms:.2f}ms > {self._threshold_ms}ms"
            ),
        )


class GovernanceMultiMetric(base_metric.BaseMetric):
    """Combined governance evaluation returning multiple scores at once.

    Returns accuracy, false positive detection, and latency in one metric.

    Task output format:
        {"output": "ALLOW|no_pii|1.2"}  (action|pii_status|latency_ms pipe-separated)

    Dataset format:
        {"input": "text", "expected_output": "ALLOW|no_pii"}
    """

    def __init__(self, name: str = "governance_multi", latency_threshold_ms: float = 5.0):
        super().__init__(name)
        self._threshold_ms = latency_threshold_ms

    def score(
        self,
        output: str,
        expected_output: str = "",
        **ignored_kwargs: Any,
    ) -> List[score_result.ScoreResult]:
        """Score multiple governance dimensions."""
        results = []

        # Parse output: "ALLOW|no_pii|1.2"
        output_parts = (output or "").split("|")
        expected_parts = (expected_output or "").split("|")

        actual_action = output_parts[0].strip().upper() if len(output_parts) > 0 else ""
        expected_action = expected_parts[0].strip().upper() if len(expected_parts) > 0 else ""

        # Accuracy
        action_correct = actual_action == expected_action
        results.append(score_result.ScoreResult(
            value=1.0 if action_correct else 0.0,
            name=f"{self.name}_accuracy",
            reason=f"{'Correct' if action_correct else 'Incorrect'}: expected {expected_action}, got {actual_action}",
        ))

        # PII detection
        if len(output_parts) > 1 and len(expected_parts) > 1:
            actual_pii = output_parts[1].strip().lower()
            expected_pii = expected_parts[1].strip().lower()
            pii_correct = actual_pii == expected_pii
            results.append(score_result.ScoreResult(
                value=1.0 if pii_correct else 0.0,
                name=f"{self.name}_pii",
                reason=f"PII detection {'correct' if pii_correct else 'incorrect'}",
            ))

        # Latency
        if len(output_parts) > 2:
            try:
                latency_ms = float(output_parts[2].strip())
                within = latency_ms <= self._threshold_ms
                results.append(score_result.ScoreResult(
                    value=1.0 if within else 0.0,
                    name=f"{self.name}_latency",
                    reason=f"{latency_ms:.2f}ms {'<=' if within else '>'} {self._threshold_ms}ms",
                ))
            except (ValueError, TypeError):
                pass

        return results
