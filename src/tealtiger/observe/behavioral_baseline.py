"""
BehavioralBaseline — computes statistical summary of request patterns
from the first N requests through an observe() proxy.

Once complete (N samples collected), the baseline is frozen and
subsequent add_sample() calls are no-ops (immutable after completion).

Requirements: 8.6, 4.1–4.8
"""

from __future__ import annotations

import math
from typing import List, Optional

from .types import BaselineSample, BaselineResult, BaselineStats, PercentileStats


def _compute_percentiles(sorted_values: List[float]) -> PercentileStats:
    """Compute P50, P95, P99 percentiles for a sorted list of numbers."""
    n = len(sorted_values)
    return PercentileStats(
        p50=sorted_values[math.floor(n * 0.5)],
        p95=sorted_values[math.floor(n * 0.95)],
        p99=sorted_values[math.floor(n * 0.99)],
    )


class BehavioralBaseline:
    """
    Computes a behavioral baseline from the first N requests through a proxy.

    Collects samples until the configured window size is reached, then
    computes P50/P95/P99 percentile statistics for each tracked metric.
    After completion, add_sample() is a no-op — the baseline is immutable.

    Args:
        window_size: Number of requests to collect before computing stats. Default: 100.
    """

    def __init__(self, window_size: int = 100) -> None:
        self._window_size: int = window_size
        self._samples: List[BaselineSample] = []
        self._completed: bool = False
        self._computed_stats: Optional[BaselineStats] = None

    def add_sample(self, sample: BaselineSample) -> None:
        """
        Add a sample to the baseline.

        No-op if baseline is already complete (immutability guarantee).
        """
        if self._completed:
            return

        self._samples.append(sample)

        if len(self._samples) >= self._window_size:
            self._completed = True
            self._computed_stats = self._compute_stats()

    def get_baseline(self) -> BaselineResult:
        """Get current baseline status and stats."""
        return BaselineResult(
            is_complete=self._completed,
            sample_count=len(self._samples),
            window_size=self._window_size,
            stats=self._computed_stats,
        )

    def is_complete(self) -> bool:
        """Check if baseline computation is complete."""
        return self._completed

    def _compute_stats(self) -> BaselineStats:
        """Compute percentile statistics from collected samples."""
        latencies = sorted(s.latency_ms for s in self._samples)
        input_tokens = sorted(float(s.input_tokens) for s in self._samples)
        output_tokens = sorted(float(s.output_tokens) for s in self._samples)
        costs = sorted(s.cost_usd for s in self._samples)
        tool_calls = sorted(float(s.tool_call_count) for s in self._samples)

        return BaselineStats(
            latency_ms=_compute_percentiles(latencies),
            input_tokens=_compute_percentiles(input_tokens),
            output_tokens=_compute_percentiles(output_tokens),
            cost_usd=_compute_percentiles(costs),
            tool_call_count=_compute_percentiles(tool_calls),
        )
