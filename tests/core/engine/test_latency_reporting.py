"""The engine must report its own latency honestly.

`metadata.evaluation_time_ms` reaches callers on every decision, and until this change it
was computed with `time.time()` and truncated with `int()`. Measured over 2000 decisions
on Windows: 0 ms for 1962 of them, 1 ms for 38, against an actual mean of 0.054 ms. Two
separate faults producing the same answer — a clock that ticks every ~15.6ms cannot see a
sub-millisecond operation, and `int(0.054)` is 0 regardless of the clock.

Conformance specification §3.6 states it directly: implementations MUST NOT measure
elapsed time with a wall-clock source. The same defect was fixed in `PolicyTester`
(`b8a3ca7`), where it was writing `0.000` into JUnit XML.

These tests are deliberately about the *shape* of the measurement rather than its value.
Asserting a specific duration would make them a speed benchmark, which belongs in a
benchmark and fails on a loaded CI runner for reasons that say nothing about correctness.
"""

import time

import pytest

from tealtiger.core.circuit import TealCircuit
from tealtiger.core.context import ContextManager
from tealtiger.core.engine import ModeConfig, PolicyMode, TealEngine

POLICY = {"tools": {"search": {"allowed": True}, "file_delete": {"allowed": False}}}
REQUEST = {"agentId": "a", "action": "tool.execute", "tool": "file_delete"}


def _engine(mode=PolicyMode.ENFORCE):
    return TealEngine(policies=POLICY, mode=ModeConfig(default=mode))


class TestReportedLatencyIsNotAlwaysZero:
    """The regression that matters: a field that only ever says 0 is not a measurement."""

    def test_a_sub_millisecond_evaluation_is_not_reported_as_zero(self):
        decisions = [
            _engine().evaluate_with_mode(REQUEST).metadata["evaluation_time_ms"]
            for _ in range(200)
        ]

        assert all(d >= 0 for d in decisions)
        assert any(d > 0 for d in decisions), (
            "Every one of 200 evaluations reported 0 ms. Tool-allowlist evaluation takes "
            "tens of microseconds, so this is a clock-resolution or truncation bug, not "
            "an impossibly fast engine."
        )

    def test_the_value_has_sub_millisecond_resolution(self):
        """An integer millisecond cannot express the duration being measured."""
        values = {
            _engine().evaluate_with_mode(REQUEST).metadata["evaluation_time_ms"]
            for _ in range(200)
        }

        assert any(
            isinstance(v, float) and v != int(v) for v in values
        ), f"No value carried a fractional millisecond: {sorted(values)[:10]}"

    @pytest.mark.parametrize(
        "mode", [PolicyMode.ENFORCE, PolicyMode.MONITOR, PolicyMode.REPORT_ONLY]
    )
    def test_every_mode_reports_a_duration(self, mode):
        """All three modes build their own metadata, so all three can regress."""
        values = [
            _engine(mode).evaluate_with_mode(REQUEST).metadata["evaluation_time_ms"]
            for _ in range(100)
        ]

        assert all(v >= 0 for v in values)
        assert any(v > 0 for v in values), f"{mode.value} always reported 0 ms"

    def test_the_circuit_breaker_reports_a_duration_too(self):
        values = [
            TealCircuit().evaluate(ContextManager.create_context()).metadata[
                "evaluation_time_ms"
            ]
            for _ in range(200)
        ]

        assert any(v > 0 for v in values)


class TestTheMeasurementIsMonotonic:
    def test_a_duration_is_never_negative(self):
        """Wall-clock time can run backwards; a monotonic clock cannot.

        NTP correction or a DST adjustment mid-evaluation could make a wall-clock
        duration negative, which is not a value any consumer is prepared for.
        """
        values = [
            _engine().evaluate_with_mode(REQUEST).metadata["evaluation_time_ms"]
            for _ in range(500)
        ]

        assert min(values) >= 0

    def test_reported_latency_is_bounded_by_wall_clock_elapsed(self):
        """A sanity check on the units, which is where this kind of fix goes wrong.

        Reporting seconds in a field named `_ms`, or microseconds, would pass every
        other test here. The reported figure must be no larger than the real elapsed
        time for the same work, measured independently.
        """
        engine = _engine()
        iterations = 200

        started = time.perf_counter()
        reported = [
            engine.evaluate_with_mode(REQUEST).metadata["evaluation_time_ms"]
            for _ in range(iterations)
        ]
        elapsed_ms = (time.perf_counter() - started) * 1000

        assert sum(reported) <= elapsed_ms + 1, (
            f"Reported {sum(reported):.3f} ms of evaluation inside {elapsed_ms:.3f} ms "
            "of wall-clock time. The field is probably in the wrong unit."
        )
