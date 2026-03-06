"""
Performance Benchmarks for TealTiger Enterprise Features

Benchmarks for:
- Mode resolution (target: < 1ms p99)
- Decision evaluation overhead (target: < 10ms p99)
- Context propagation (target: < 0.5ms p99)
- Content redaction (target: < 5ms for 10KB p99)
- Audit logging (target: < 2ms async p99)
- Policy test execution (target: < 100ms per test)
"""

import time
import statistics
from typing import List, Dict, Any
import asyncio

from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import PolicyMode, ModeConfig, RequestContext, TealPolicy
from tealtiger.core.context.context_manager import ContextManager
from tealtiger.core.context.execution_context import ExecutionContext
from tealtiger.core.audit.redaction import ContentRedactor
from tealtiger.core.audit.types import RedactionLevel
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.output import ConsoleOutput
from tealtiger.core.engine.testing.policy_tester import PolicyTester
from tealtiger.core.engine.testing.types import PolicyTestCase, DecisionAction, ReasonCode


def benchmark(func, iterations: int = 1000) -> Dict[str, float]:
    """
    Run benchmark and return statistics.
    
    Args:
        func: Function to benchmark
        iterations: Number of iterations
        
    Returns:
        Dictionary with min, max, mean, median, p95, p99 in milliseconds
    """
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms
    
    times.sort()
    return {
        'min': times[0],
        'max': times[-1],
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'p95': times[int(len(times) * 0.95)],
        'p99': times[int(len(times) * 0.99)],
        'iterations': iterations
    }


async def benchmark_async(func, iterations: int = 1000) -> Dict[str, float]:
    """
    Run async benchmark and return statistics.
    
    Args:
        func: Async function to benchmark
        iterations: Number of iterations
        
    Returns:
        Dictionary with min, max, mean, median, p95, p99 in milliseconds
    """
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        await func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms
    
    times.sort()
    return {
        'min': times[0],
        'max': times[-1],
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'p95': times[int(len(times) * 0.95)],
        'p99': times[int(len(times) * 0.99)],
        'iterations': iterations
    }


def benchmark_mode_resolution():
    """Benchmark mode resolution (target: < 1ms p99)."""
    print("\n=== Mode Resolution Benchmark ===")
    
    # Setup
    policy = TealPolicy(
        tools={'file_delete': {'allowed': False}},
        identity={'agent_id': 'test-agent'}
    )
    mode_config = ModeConfig(
        default_mode=PolicyMode.MONITOR,
        policy_modes={'tools.file_delete': PolicyMode.ENFORCE},
        environment_modes={'production': PolicyMode.ENFORCE}
    )
    engine = TealEngine(policy, mode=mode_config)
    
    # Benchmark
    def resolve_mode():
        engine._resolve_policy_mode('tools.file_delete', 'production')
    
    results = benchmark(resolve_mode, iterations=10000)
    
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 1ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 1.0:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 1ms)")
    
    return results


def benchmark_decision_evaluation():
    """Benchmark decision evaluation overhead (target: < 10ms p99)."""
    print("\n=== Decision Evaluation Benchmark ===")
    
    # Setup
    policy = TealPolicy(
        tools={'file_delete': {'allowed': False}},
        identity={'agent_id': 'test-agent'}
    )
    engine = TealEngine(policy)
    context = ContextManager.create_context()
    
    # Benchmark
    def evaluate():
        request_context = RequestContext(
            agent_id='test-agent',
            action='tool.execute',
            tool='file_delete',
            context=context
        )
        engine.evaluate(request_context)
    
    results = benchmark(evaluate, iterations=5000)
    
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 10ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 10.0:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 10ms)")
    
    return results


def benchmark_context_propagation():
    """Benchmark context propagation (target: < 0.5ms p99)."""
    print("\n=== Context Propagation Benchmark ===")
    
    # Benchmark
    def propagate():
        context = ContextManager.create_context(
            tenant_id='test-tenant',
            app='test-app',
            env='production'
        )
        # Simulate propagation
        enriched = ExecutionContext(
            correlation_id=context.correlation_id,
            trace_id=context.trace_id,
            tenant_id=context.tenant_id,
            app=context.app,
            env=context.env,
            span_id=ContextManager.generate_correlation_id()
        )
    
    results = benchmark(propagate, iterations=10000)
    
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 0.5ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 0.5:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 0.5ms)")
    
    return results


def benchmark_content_redaction():
    """Benchmark content redaction (target: < 5ms for 10KB p99)."""
    print("\n=== Content Redaction Benchmark ===")
    
    # Setup - 10KB content
    content = "This is sensitive data. " * 400  # ~10KB
    redactor = ContentRedactor()
    
    # Benchmark HASH redaction
    def redact():
        redactor.redact(content, RedactionLevel.HASH)
    
    results = benchmark(redact, iterations=5000)
    
    print(f"  Content size: {len(content)} bytes (~10KB)")
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 5ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 5.0:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 5ms)")
    
    return results


async def benchmark_audit_logging():
    """Benchmark audit logging (target: < 2ms async p99)."""
    print("\n=== Audit Logging Benchmark ===")
    
    # Setup
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH
        )
    )
    context = ContextManager.create_context()
    
    # Benchmark
    async def log_event():
        from tealtiger.core.audit.types import AuditEventType
        audit.log_event(
            event_type=AuditEventType.POLICY_EVALUATION,
            context=context,
            metadata={'test': 'data'}
        )
    
    results = await benchmark_async(log_event, iterations=5000)
    
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 2ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 2.0:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 2ms)")
    
    return results


def benchmark_policy_test_execution():
    """Benchmark policy test execution (target: < 100ms per test)."""
    print("\n=== Policy Test Execution Benchmark ===")
    
    # Setup
    policy = TealPolicy(
        tools={'file_delete': {'allowed': False}},
        identity={'agent_id': 'test-agent'}
    )
    engine = TealEngine(policy)
    tester = PolicyTester(engine)
    
    test_case = PolicyTestCase(
        name='Block file deletion',
        context=RequestContext(
            agent_id='test-agent',
            action='tool.execute',
            tool='file_delete',
            context=ContextManager.create_context()
        ),
        expected={
            'action': DecisionAction.DENY,
            'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED]
        }
    )
    
    # Benchmark
    def run_test():
        tester.run_test(test_case)
    
    results = benchmark(run_test, iterations=1000)
    
    print(f"  Min: {results['min']:.4f}ms")
    print(f"  Mean: {results['mean']:.4f}ms")
    print(f"  Median: {results['median']:.4f}ms")
    print(f"  P95: {results['p95']:.4f}ms")
    print(f"  P99: {results['p99']:.4f}ms (target: < 100ms)")
    print(f"  Max: {results['max']:.4f}ms")
    
    if results['p99'] < 100.0:
        print("  ✓ PASSED")
    else:
        print(f"  ✗ FAILED (p99: {results['p99']:.4f}ms > 100ms)")
    
    return results


async def main():
    """Run all benchmarks."""
    print("=" * 60)
    print("TealTiger Enterprise Features - Performance Benchmarks")
    print("=" * 60)
    
    results = {}
    
    # Run benchmarks
    results['mode_resolution'] = benchmark_mode_resolution()
    results['decision_evaluation'] = benchmark_decision_evaluation()
    results['context_propagation'] = benchmark_context_propagation()
    results['content_redaction'] = benchmark_content_redaction()
    results['audit_logging'] = await benchmark_audit_logging()
    results['policy_test_execution'] = benchmark_policy_test_execution()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    targets = {
        'mode_resolution': 1.0,
        'decision_evaluation': 10.0,
        'context_propagation': 0.5,
        'content_redaction': 5.0,
        'audit_logging': 2.0,
        'policy_test_execution': 100.0
    }
    
    for name, result in results.items():
        target = targets[name]
        passed = result['p99'] < target
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:30s}: {result['p99']:8.4f}ms (target: < {target}ms) {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("All benchmarks PASSED ✓")
    else:
        print("Some benchmarks FAILED ✗")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
