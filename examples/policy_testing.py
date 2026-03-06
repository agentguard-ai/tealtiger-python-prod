"""
Policy Testing Examples

Demonstrates the policy testing framework for validating policy behavior
before production deployment.

Examples:
1. Define test suite with test cases
2. Run tests with PolicyTester
3. Use starter test corpora
4. Export test reports (JSON, JUnit XML)
5. CLI usage for CI/CD integration
6. Test assertions (action, reason codes, risk score, mode)
7. Coverage calculation
8. Filtering tests by tags
"""

import asyncio
import json
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import TealPolicy, PolicyMode, ModeConfig, RequestContext, DecisionAction, ReasonCode
from tealtiger.core.engine.testing.policy_tester import PolicyTester
from tealtiger.core.engine.testing.types import PolicyTestCase, PolicyTestSuite
from tealtiger.core.engine.testing.test_corpora import TestCorpora
from tealtiger.core.context.context_manager import ContextManager


# Example 1: Define test suite with test cases
async def example_define_test_suite():
    """Define a test suite for customer support agent policies."""
    print("\n=== Example 1: Define Test Suite ===\n")
    
    # Define test suite
    test_suite = PolicyTestSuite(
        name='Customer Support Agent Policy Tests',
        description='Validates policies for customer support agents',
        policy=TealPolicy(
            tools={
                'file_delete': {'allowed': False},
                'database_write': {'allowed': False},
                'customer_data_read': {'allowed': True},
                'send_email': {'allowed': True}
            },
            identity={'agent_id': 'support-agent-001', 'role': 'customer-support'}
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            PolicyTestCase(
                name='Block file deletion',
                description='Should deny file_delete tool usage',
                context=RequestContext(
                    agent_id='support-agent-001',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={
                    'action': DecisionAction.DENY,
                    'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED]
                },
                tags=['security', 'tools', 'critical']
            ),
            PolicyTestCase(
                name='Allow customer data read',
                description='Should allow customer_data_read tool',
                context=RequestContext(
                    agent_id='support-agent-001',
                    action='tool.execute',
                    tool='customer_data_read',
                    context=ContextManager.create_context()
                ),
                expected={
                    'action': DecisionAction.ALLOW,
                    'reason_codes': [ReasonCode.POLICY_PASSED]
                },
                tags=['security', 'tools', 'allowed']
            )
        ]
    )
    
    print(f"Test Suite: {test_suite.name}")
    print(f"Description: {test_suite.description}")
    print(f"Total Tests: {len(test_suite.tests)}")
    print(f"Mode: {test_suite.mode.default_mode.value}\n")
    
    print("Test Cases:")
    for i, test in enumerate(test_suite.tests, 1):
        print(f"  {i}. {test.name}")
        print(f"     Expected: {test.expected['action'].value}")
        print(f"     Tags: {', '.join(test.tags)}")
    
    print("\n✓ Test suite defined with 2 test cases")
    return test_suite


# Example 2: Run tests with PolicyTester
async def example_run_tests():
    """Execute test suite using PolicyTester."""
    print("\n=== Example 2: Run Tests with PolicyTester ===\n")
    
    # Define simple test suite
    test_suite = PolicyTestSuite(
        name='Basic Policy Tests',
        description='Simple tests for demonstration',
        policy=TealPolicy(
            tools={
                'file_delete': {'allowed': False},
                'customer_data_read': {'allowed': True}
            },
            identity={'agent_id': 'test-agent'}
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            PolicyTestCase(
                name='Deny file deletion',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY}
            ),
            PolicyTestCase(
                name='Allow data read',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='customer_data_read',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.ALLOW}
            )
        ]
    )
    
    # Initialize PolicyTester
    engine = TealEngine(test_suite.policy, mode=test_suite.mode)
    tester = PolicyTester(engine)
    
    print("Running test suite...\n")
    
    # Run tests
    report = tester.run_suite(test_suite)
    
    print("Test Results:")
    print(f"  Total: {report.total}")
    print(f"  Passed: {report.passed} ✓")
    print(f"  Failed: {report.failed}")
    print(f"  Success Rate: {report.success_rate * 100:.1f}%")
    print(f"  Execution Time: {report.total_time:.2f}ms\n")
    
    print("Individual Results:")
    for i, result in enumerate(report.results, 1):
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"  {i}. {result.name}: {status}")
        print(f"     Actual: {result.actual.action.value}")
        print(f"     Expected: {result.expected['action'].value}")
        if not result.passed:
            print(f"     Failure: {result.failure_reason}")
    
    # Coverage
    if report.coverage:
        print(f"\nCoverage:")
        print(f"  Total Policies: {report.coverage.total_policies}")
        print(f"  Tested: {report.coverage.tested_policies}")
        print(f"  Coverage: {report.coverage.coverage_percentage:.1f}%")
    
    print("\n✓ PolicyTester execution complete")
    return report


# Example 3: Use starter test corpora
async def example_test_corpora():
    """Use pre-built test suites from TestCorpora."""
    print("\n=== Example 3: Starter Test Corpora ===\n")
    
    print("Available Test Corpora:")
    print("  1. Prompt Injection (20+ attack vectors)")
    print("  2. PII Detection (SSN, credit cards, emails)")
    print("  3. Unsafe Code (eval, exec, system commands)")
    print("  4. Tool Misuse (unauthorized access)")
    print("  5. Cost Limits (budget enforcement)\n")
    
    # Prompt Injection Tests
    print("━━━ Prompt Injection Tests ━━━\n")
    injection_suite = TestCorpora.prompt_injection()
    print(f"Suite: {injection_suite.name}")
    print(f"Tests: {len(injection_suite.tests)}\n")
    
    engine1 = TealEngine(injection_suite.policy, mode=injection_suite.mode)
    tester1 = PolicyTester(engine1)
    report1 = tester1.run_suite(injection_suite)
    print(f"Results: {report1.passed}/{report1.total} passed ({report1.success_rate * 100:.1f}%)")
    
    # PII Detection Tests
    print("\n━━━ PII Detection Tests ━━━\n")
    pii_suite = TestCorpora.pii_detection()
    print(f"Suite: {pii_suite.name}")
    print(f"Tests: {len(pii_suite.tests)}\n")
    
    engine2 = TealEngine(pii_suite.policy, mode=pii_suite.mode)
    tester2 = PolicyTester(engine2)
    report2 = tester2.run_suite(pii_suite)
    print(f"Results: {report2.passed}/{report2.total} passed ({report2.success_rate * 100:.1f}%)")
    
    # Unsafe Code Tests
    print("\n━━━ Unsafe Code Tests ━━━\n")
    code_suite = TestCorpora.unsafe_code()
    print(f"Suite: {code_suite.name}")
    print(f"Tests: {len(code_suite.tests)}\n")
    
    engine3 = TealEngine(code_suite.policy, mode=code_suite.mode)
    tester3 = PolicyTester(engine3)
    report3 = tester3.run_suite(code_suite)
    print(f"Results: {report3.passed}/{report3.total} passed ({report3.success_rate * 100:.1f}%)")
    
    # Summary
    total_tests = report1.total + report2.total + report3.total
    print(f"\n✓ Test Corpora Summary:")
    print(f"   - Prompt Injection: {report1.passed}/{report1.total}")
    print(f"   - PII Detection: {report2.passed}/{report2.total}")
    print(f"   - Unsafe Code: {report3.passed}/{report3.total}")
    print(f"   - Total: {total_tests} tests")


# Example 4: Export test reports
async def example_export_reports():
    """Export test reports in JSON and JUnit XML formats."""
    print("\n=== Example 4: Export Test Reports ===\n")
    
    # Run test suite
    test_suite = PolicyTestSuite(
        name='Export Demo Tests',
        policy=TealPolicy(
            tools={'file_delete': {'allowed': False}}
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            PolicyTestCase(
                name='Test 1',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY}
            )
        ]
    )
    
    engine = TealEngine(test_suite.policy, mode=test_suite.mode)
    tester = PolicyTester(engine)
    report = tester.run_suite(test_suite)
    
    print("Exporting reports...\n")
    
    # JSON Export
    print("━━━ JSON Format ━━━\n")
    json_report = tester.export_report(report, format='json')
    print("JSON Report Structure:")
    print("  {")
    print("    'timestamp': '2024-02-19T10:30:00',")
    print("    'suite_name': 'Export Demo Tests',")
    print("    'total': 1,")
    print("    'passed': 1,")
    print("    'results': [...]")
    print("  }")
    print("\n✓ JSON export ready for programmatic processing")
    
    # JUnit XML Export
    print("\n━━━ JUnit XML Format ━━━\n")
    junit_xml = tester.export_report(report, format='junit')
    print("JUnit XML Structure:")
    print("  <?xml version='1.0'?>")
    print("  <testsuites>")
    print("    <testsuite name='...' tests='1' failures='0'>")
    print("      <testcase name='Test 1' time='0.050'/>")
    print("    </testsuite>")
    print("  </testsuites>")
    print("\n✓ JUnit XML ready for CI/CD integration")


# Example 5: CLI usage for CI/CD
async def example_cli_usage():
    """Demonstrate CLI commands for CI/CD integration."""
    print("\n=== Example 5: CLI Usage for CI/CD ===\n")
    
    print("TealTiger CLI - Policy Testing Commands\n")
    
    print("━━━ Basic Usage ━━━\n")
    print("# Run tests from file")
    print("$ python -m tealtiger.cli.test ./policies/customer-support.test.json\n")
    
    print("# Run tests from directory")
    print("$ python -m tealtiger.cli.test ./policies/\n")
    
    print("━━━ Output Formats ━━━\n")
    print("# Export to JSON")
    print("$ python -m tealtiger.cli.test ./policies/*.json --format=json --output=results.json\n")
    
    print("# Export to JUnit XML")
    print("$ python -m tealtiger.cli.test ./policies/*.json --format=junit --output=results.xml\n")
    
    print("━━━ Filtering ━━━\n")
    print("# Run tests with specific tags")
    print("$ python -m tealtiger.cli.test ./policies/*.json --tags=security,critical\n")
    
    print("━━━ Coverage ━━━\n")
    print("# Generate coverage report")
    print("$ python -m tealtiger.cli.test ./policies/*.json --coverage\n")
    
    print("━━━ CI/CD Integration ━━━\n")
    
    print("GitHub Actions (.github/workflows/policy-tests.yml):")
    print("```yaml")
    print("name: Policy Tests")
    print("on: [push, pull_request]")
    print("jobs:")
    print("  test:")
    print("    runs-on: ubuntu-latest")
    print("    steps:")
    print("      - uses: actions/checkout@v3")
    print("      - uses: actions/setup-python@v4")
    print("        with:")
    print("          python-version: '3.11'")
    print("      - run: pip install tealtiger")
    print("      - run: python -m tealtiger.cli.test ./policies/*.json --format=junit --output=results.xml")
    print("```\n")
    
    print("✓ CLI enables zero-config policy testing in CI/CD")


# Example 6: Test assertions
async def example_test_assertions():
    """Demonstrate different types of test assertions."""
    print("\n=== Example 6: Test Assertions ===\n")
    
    test_suite = PolicyTestSuite(
        name='Assertion Examples',
        policy=TealPolicy(
            tools={'file_delete': {'allowed': False}}
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            # Action only
            PolicyTestCase(
                name='Assert action only',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY}
            ),
            # Action + reason codes
            PolicyTestCase(
                name='Assert action and reason codes',
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
            ),
            # Action + risk score range
            PolicyTestCase(
                name='Assert action and risk score',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={
                    'action': DecisionAction.DENY,
                    'risk_score_range': {'min': 70, 'max': 100}
                }
            )
        ]
    )
    
    engine = TealEngine(test_suite.policy, mode=test_suite.mode)
    tester = PolicyTester(engine)
    report = tester.run_suite(test_suite)
    
    print("Assertion Test Results:\n")
    for i, result in enumerate(report.results, 1):
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"{i}. {result.name}: {status}")
        print(f"   Expected: {result.expected['action'].value}")
        print(f"   Actual: {result.actual.action.value}")
        if 'reason_codes' in result.expected:
            print(f"   Reason Codes: {[rc.value for rc in result.expected['reason_codes']]}")
        if 'risk_score_range' in result.expected:
            rng = result.expected['risk_score_range']
            print(f"   Risk Score Range: {rng['min']}-{rng['max']}")
        print()
    
    print("✓ Assertion types demonstrated:")
    print("   - Action-only (simplest)")
    print("   - Action + reason codes")
    print("   - Action + risk score range")


# Example 7: Coverage calculation
async def example_coverage():
    """Demonstrate coverage calculation."""
    print("\n=== Example 7: Coverage Calculation ===\n")
    
    # Policy with multiple tools
    test_suite = PolicyTestSuite(
        name='Coverage Demo',
        policy=TealPolicy(
            tools={
                'file_delete': {'allowed': False},
                'file_read': {'allowed': True},
                'database_write': {'allowed': False},
                'customer_data_read': {'allowed': True}
            }
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            # Only test 2 out of 4 tools
            PolicyTestCase(
                name='Test file_delete',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY}
            ),
            PolicyTestCase(
                name='Test file_read',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_read',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.ALLOW}
            )
        ]
    )
    
    engine = TealEngine(test_suite.policy, mode=test_suite.mode)
    tester = PolicyTester(engine)
    report = tester.run_suite(test_suite)
    
    print("Coverage Report:")
    print(f"  Total Policies: {report.coverage.total_policies}")
    print(f"  Tested Policies: {report.coverage.tested_policies}")
    print(f"  Coverage: {report.coverage.coverage_percentage:.1f}%")
    print(f"  Untested: {', '.join(report.coverage.untested_policies)}\n")
    
    print("✓ Coverage helps identify untested policies")


# Example 8: Filter tests by tags
async def example_filter_by_tags():
    """Demonstrate filtering tests by tags."""
    print("\n=== Example 8: Filter Tests by Tags ===\n")
    
    test_suite = PolicyTestSuite(
        name='Tagged Tests',
        policy=TealPolicy(
            tools={'file_delete': {'allowed': False}}
        ),
        mode=ModeConfig(default_mode=PolicyMode.ENFORCE),
        tests=[
            PolicyTestCase(
                name='Critical security test',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY},
                tags=['security', 'critical']
            ),
            PolicyTestCase(
                name='Non-critical test',
                context=RequestContext(
                    agent_id='test-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={'action': DecisionAction.DENY},
                tags=['security']
            )
        ]
    )
    
    print("All tests:")
    for test in test_suite.tests:
        print(f"  - {test.name} (tags: {', '.join(test.tags)})")
    
    print("\nFiltered tests (tag='critical'):")
    critical_tests = [t for t in test_suite.tests if 'critical' in t.tags]
    for test in critical_tests:
        print(f"  - {test.name}")
    
    print("\n✓ Tags enable selective test execution")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("Policy Testing Examples")
    print("=" * 70)
    
    await example_define_test_suite()
    await example_run_tests()
    await example_test_corpora()
    await example_export_reports()
    await example_cli_usage()
    await example_test_assertions()
    await example_coverage()
    await example_filter_by_tags()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("- Define test suites with PolicyTestCase")
    print("- Run tests with PolicyTester")
    print("- Use TestCorpora for common scenarios")
    print("- Export to JSON/JUnit XML for CI/CD")
    print("- Track coverage to identify gaps")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
