"""
Performance validation: observe() overhead benchmark.

Property 9: With a mock zero-latency provider, P99 overhead < 5ms
across 100+ iterations.

Run:
    python -m pytest benchmarks/test_observe_overhead.py -v

Requirements: 7.4
"""
import sys
import os
import time
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from tealtiger.observe import observe
from tealtiger.observe.freeze_registry import FreezeRegistry


# Reset singleton
@pytest.fixture(autouse=True)
def reset():
    FreezeRegistry.get_instance()._reset()
    yield
    FreezeRegistry.get_instance()._reset()


# Mock zero-latency provider
class ZeroLatencyCompletions:
    """Completes instantly with minimal response object."""
    def create(self, **kwargs):
        # Inline response object — zero network latency
        class Response:
            class Usage:
                prompt_tokens = 10
                completion_tokens = 20
                total_tokens = 30
            usage = Usage()
            model = "gpt-4o"
            choices = []
        return Response()


class ZeroLatencyChat:
    completions = ZeroLatencyCompletions()


class ZeroLatencyClient:
    chat = ZeroLatencyChat()
    base_url = "https://api.openai.com/v1"


def test_observe_p99_overhead_under_5ms():
    """P99 overhead of observe() proxy is under 5ms with zero-latency provider."""
    client = observe(ZeroLatencyClient(), agent_id="bench-agent")

    # Warmup (JIT, import caches, etc.)
    for _ in range(10):
        client.chat.completions.create(model="gpt-4o", messages=[])

    # Benchmark
    latencies_ms = []
    for _ in range(200):
        start = time.perf_counter_ns()
        client.chat.completions.create(model="gpt-4o", messages=[])
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        latencies_ms.append(elapsed_ms)

    # Compute P99
    latencies_sorted = sorted(latencies_ms)
    p50 = latencies_sorted[len(latencies_sorted) * 50 // 100]
    p95 = latencies_sorted[len(latencies_sorted) * 95 // 100]
    p99 = latencies_sorted[len(latencies_sorted) * 99 // 100]

    print(f"\n  Observe overhead (200 iterations):")
    print(f"    P50: {p50:.3f} ms")
    print(f"    P95: {p95:.3f} ms")
    print(f"    P99: {p99:.3f} ms")
    print(f"    Max: {max(latencies_ms):.3f} ms")
    print(f"    Mean: {statistics.mean(latencies_ms):.3f} ms")

    # Assert P99 < 5ms
    assert p99 < 5.0, (
        f"P99 overhead ({p99:.3f} ms) exceeds 5ms threshold. "
        f"Investigate observe() pipeline for bottlenecks."
    )


def test_observe_mean_overhead_under_2ms():
    """Mean overhead of observe() proxy is under 2ms with zero-latency provider."""
    client = observe(ZeroLatencyClient(), agent_id="bench-mean-agent")

    # Warmup
    for _ in range(10):
        client.chat.completions.create(model="gpt-4o", messages=[])

    # Benchmark
    latencies_ms = []
    for _ in range(200):
        start = time.perf_counter_ns()
        client.chat.completions.create(model="gpt-4o", messages=[])
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        latencies_ms.append(elapsed_ms)

    mean_ms = statistics.mean(latencies_ms)

    print(f"\n  Mean overhead: {mean_ms:.3f} ms")

    assert mean_ms < 2.0, (
        f"Mean overhead ({mean_ms:.3f} ms) exceeds 2ms threshold."
    )
