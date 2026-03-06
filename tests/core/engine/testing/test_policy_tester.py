"""Unit tests for PolicyTester.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.5: Policy Test Harness

Tests for:
- PolicyTester.run_test()
- PolicyTester.run_suite()
- PolicyTester.run_from_file()
- PolicyTester.export_report()
- Coverage calculation
"""

import json
import tempfile
from pathlib import Path

import pytest

from tealtiger.core.engine.testing import (
    PolicyTestCase,
    PolicyTestReport,
    PolicyTestResult,
    PolicyTestSuite,
    PolicyTester,
)
from tealtiger.core.engine.types import DecisionAction, PolicyMode, ReasonCode


class MockEngine:
    """Mock TealEngine for testing."""

    def __init__(self, policies=None, mode=None):
        self.policies = policies or {}
        self.mode = mode or {}

    def get_policies(self):
        """Return policies."""
        return self.policies

    def evaluate(self, context):
        """Mock evaluate method."""
        from tealtiger.core.engine.types import Decision

        # Simple mock logic: deny if tool is 'file_delete'
        if context.get('tool') == 'file_delete':
            return Decision(
                action=DecisionAction.DENY,
                reason_codes=[ReasonCode.TOOL_NOT_ALLOWED],
                risk_score=95,
                mode=PolicyMode.ENFORCE,
                policy_id='tools.file_delete',
                policy_version='1.0.0',
                component_versions={'engine': '1.1.0'},
                correlation_id='test-correlation-id',
                reason='Tool file_delete is not allowed',
                metadata={},
            )
        else:
            return Decision(
                action=DecisionAction.ALLOW,
                reason_codes=[ReasonCode.POLICY_PASSED],
                risk_score=0,
                mode=PolicyMode.ENFORCE,
                policy_id='default',
                policy_version='1.0.0',
                component_versions={'engine': '1.1.0'},
                correlation_id='test-correlation-id',
                reason='Request complies with all policies',
                metadata={},
            )


class TestPolicyTester:
    """Test suite for PolicyTester."""

    def test_run_test_passing(self):
        """Test running a passing test case."""
        engine = MockEngine(
            policies={'tools': {'file_read': {'allowed': True}}}
        )
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Allow file read',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_read',
            },
            expected={
                'action': DecisionAction.ALLOW,
                'reason_codes': [ReasonCode.POLICY_PASSED],
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is True
        assert result.name == 'Allow file read'
        assert result.failure_reason is None
        assert result.execution_time > 0

    def test_run_test_failing(self):
        """Test running a failing test case."""
        engine = MockEngine(
            policies={'tools': {'file_delete': {'allowed': False}}}
        )
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Block file deletion',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_delete',
            },
            expected={
                'action': DecisionAction.DENY,
                'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED],
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is True
        assert result.name == 'Block file deletion'

    def test_run_test_action_mismatch(self):
        """Test test case with action mismatch."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Expected DENY but got ALLOW',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_read',
            },
            expected={
                'action': DecisionAction.DENY,
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is False
        assert 'Expected action=DENY, got action=ALLOW' in result.failure_reason

    def test_run_test_reason_code_mismatch(self):
        """Test test case with reason code mismatch."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Missing expected reason code',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_delete',
            },
            expected={
                'action': DecisionAction.DENY,
                'reason_codes': [
                    ReasonCode.TOOL_NOT_ALLOWED,
                    ReasonCode.PERMISSION_DENIED,
                ],
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is False
        assert 'Missing expected reason codes' in result.failure_reason

    def test_run_test_risk_score_range(self):
        """Test test case with risk score range validation."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Risk score in range',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_delete',
            },
            expected={
                'action': DecisionAction.DENY,
                'risk_score_range': {'min': 90, 'max': 100},
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is True

    def test_run_test_risk_score_out_of_range(self):
        """Test test case with risk score out of range."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Risk score out of range',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_delete',
            },
            expected={
                'action': DecisionAction.DENY,
                'risk_score_range': {'min': 0, 'max': 50},
            },
        )

        result = tester.run_test(test_case)

        assert result.passed is False
        assert 'Risk score' in result.failure_reason
        assert 'not in expected range' in result.failure_reason

    def test_run_suite(self):
        """Test running a test suite."""
        engine = MockEngine(
            policies={
                'tools': {
                    'file_read': {'allowed': True},
                    'file_delete': {'allowed': False},
                }
            }
        )
        tester = PolicyTester(engine)

        suite = PolicyTestSuite(
            name='File operations test suite',
            description='Test file operation policies',
            policy={
                'tools': {
                    'file_read': {'allowed': True},
                    'file_delete': {'allowed': False},
                }
            },
            tests=[
                PolicyTestCase(
                    name='Allow file read',
                    context={
                        'agentId': 'test-agent',
                        'action': 'tool.execute',
                        'tool': 'file_read',
                    },
                    expected={'action': DecisionAction.ALLOW},
                ),
                PolicyTestCase(
                    name='Block file delete',
                    context={
                        'agentId': 'test-agent',
                        'action': 'tool.execute',
                        'tool': 'file_delete',
                    },
                    expected={'action': DecisionAction.DENY},
                ),
            ],
        )

        report = tester.run_suite(suite)

        assert report.suite_name == 'File operations test suite'
        assert report.total == 2
        assert report.passed == 2
        assert report.failed == 0
        assert report.success_rate == 1.0
        assert report.total_time > 0
        assert len(report.results) == 2
        assert report.coverage is not None

    def test_run_from_file(self):
        """Test loading and running tests from a file."""
        engine = MockEngine(
            policies={'tools': {'file_delete': {'allowed': False}}}
        )
        tester = PolicyTester(engine)

        # Create temporary test file
        suite_data = {
            'name': 'Test Suite from File',
            'description': 'Test loading from file',
            'policy': {'tools': {'file_delete': {'allowed': False}}},
            'tests': [
                {
                    'name': 'Block file delete',
                    'context': {
                        'agentId': 'test-agent',
                        'action': 'tool.execute',
                        'tool': 'file_delete',
                    },
                    'expected': {'action': 'DENY'},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(suite_data, f)
            temp_file = f.name

        try:
            report = tester.run_from_file(temp_file)

            assert report.suite_name == 'Test Suite from File'
            assert report.total == 1
            assert len(report.results) == 1

        finally:
            Path(temp_file).unlink()

    def test_run_from_file_not_found(self):
        """Test loading from non-existent file."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        with pytest.raises(FileNotFoundError):
            tester.run_from_file('/nonexistent/file.json')

    def test_export_report_json(self):
        """Test exporting report as JSON."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        suite = PolicyTestSuite(
            name='Test Suite',
            policy={},
            tests=[
                PolicyTestCase(
                    name='Test 1',
                    context={'agentId': 'test'},
                    expected={'action': DecisionAction.ALLOW},
                )
            ],
        )

        report = tester.run_suite(suite)
        json_output = tester.export_report(report, format='json')

        # Verify it's valid JSON
        parsed = json.loads(json_output)
        assert parsed['suite_name'] == 'Test Suite'
        assert parsed['total'] == 1

    def test_export_report_junit(self):
        """Test exporting report as JUnit XML."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        suite = PolicyTestSuite(
            name='Test Suite',
            policy={},
            tests=[
                PolicyTestCase(
                    name='Test 1',
                    context={'agentId': 'test'},
                    expected={'action': DecisionAction.ALLOW},
                )
            ],
        )

        report = tester.run_suite(suite)
        xml_output = tester.export_report(report, format='junit')

        # Verify it's valid XML
        assert '<?xml version' in xml_output
        assert '<testsuite' in xml_output
        assert 'name="Test Suite"' in xml_output
        assert '<testcase' in xml_output

    def test_export_report_invalid_format(self):
        """Test exporting with invalid format."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        suite = PolicyTestSuite(
            name='Test Suite',
            policy={},
            tests=[
                PolicyTestCase(
                    name='Test 1',
                    context={'agentId': 'test'},
                    expected={'action': DecisionAction.ALLOW},
                )
            ],
        )

        report = tester.run_suite(suite)

        with pytest.raises(ValueError, match='Unsupported format'):
            tester.export_report(report, format='invalid')

    def test_coverage_calculation(self):
        """Test policy coverage calculation."""
        engine = MockEngine(
            policies={
                'tools': {
                    'file_read': {'allowed': True},
                    'file_delete': {'allowed': False},
                    'file_write': {'allowed': True},
                },
                'identity': {'agentId': 'test', 'role': 'user', 'permissions': []},
            }
        )
        tester = PolicyTester(engine)

        # Run tests that only cover some policies
        suite = PolicyTestSuite(
            name='Partial coverage',
            policy=engine.policies,
            tests=[
                PolicyTestCase(
                    name='Test file_delete',
                    context={
                        'agentId': 'test',
                        'action': 'tool.execute',
                        'tool': 'file_delete',
                    },
                    expected={'action': DecisionAction.DENY},
                )
            ],
        )

        report = tester.run_suite(suite)

        assert report.coverage is not None
        assert report.coverage.total_policies > 0
        assert report.coverage.tested_policies > 0
        assert report.coverage.coverage_percentage > 0
        assert len(report.coverage.untested_policies) > 0

    def test_test_reproducibility(self):
        """Test that tests produce consistent results."""
        engine = MockEngine(
            policies={'tools': {'file_delete': {'allowed': False}}}
        )
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Reproducibility test',
            context={
                'agentId': 'test-agent',
                'action': 'tool.execute',
                'tool': 'file_delete',
            },
            expected={'action': DecisionAction.DENY},
        )

        # Run the same test multiple times
        results = [tester.run_test(test_case) for _ in range(5)]

        # All results should be the same
        for result in results:
            assert result.passed is True
            assert result.name == 'Reproducibility test'
            assert result.actual['action'] == 'DENY'

    def test_execution_time_measurement(self):
        """Test that execution time is measured."""
        engine = MockEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Timing test',
            context={'agentId': 'test'},
            expected={'action': DecisionAction.ALLOW},
        )

        result = tester.run_test(test_case)

        # Execution time should be positive
        assert result.execution_time > 0
        # Should be reasonably fast (< 100ms as per spec)
        assert result.execution_time < 100

    def test_exception_handling(self):
        """Test handling of exceptions during test execution."""

        class FailingEngine:
            def get_policies(self):
                return {}

            def evaluate(self, context):
                raise RuntimeError('Simulated engine failure')

        engine = FailingEngine()
        tester = PolicyTester(engine)

        test_case = PolicyTestCase(
            name='Exception test',
            context={'agentId': 'test'},
            expected={'action': DecisionAction.ALLOW},
        )

        result = tester.run_test(test_case)

        assert result.passed is False
        assert 'Exception during test execution' in result.failure_reason
        assert 'Simulated engine failure' in result.failure_reason


class TestPolicyTestTypes:
    """Test suite for policy test types."""

    def test_policy_test_case_creation(self):
        """Test creating a PolicyTestCase."""
        test_case = PolicyTestCase(
            name='Test case',
            description='Test description',
            context={'agentId': 'test'},
            expected={'action': DecisionAction.ALLOW},
            tags=['test', 'security'],
        )

        assert test_case.name == 'Test case'
        assert test_case.description == 'Test description'
        assert test_case.context == {'agentId': 'test'}
        assert test_case.expected.action == DecisionAction.ALLOW
        assert test_case.tags == ['test', 'security']

    def test_policy_test_suite_creation(self):
        """Test creating a PolicyTestSuite."""
        suite = PolicyTestSuite(
            name='Test suite',
            description='Suite description',
            policy={'tools': {}},
            mode={'defaultMode': PolicyMode.ENFORCE},
            tests=[
                PolicyTestCase(
                    name='Test 1',
                    context={'agentId': 'test'},
                    expected={'action': DecisionAction.ALLOW},
                )
            ],
        )

        assert suite.name == 'Test suite'
        assert suite.description == 'Suite description'
        assert suite.policy == {'tools': {}}
        assert suite.mode == {'defaultMode': PolicyMode.ENFORCE}
        assert len(suite.tests) == 1

    def test_policy_test_result_creation(self):
        """Test creating a PolicyTestResult."""
        result = PolicyTestResult(
            name='Test result',
            passed=True,
            actual={'action': 'ALLOW'},
            expected={'action': DecisionAction.ALLOW},
            execution_time=5.5,
        )

        assert result.name == 'Test result'
        assert result.passed is True
        assert result.actual == {'action': 'ALLOW'}
        assert result.execution_time == 5.5
        assert result.failure_reason is None

    def test_policy_test_report_creation(self):
        """Test creating a PolicyTestReport."""
        report = PolicyTestReport(
            timestamp='2024-01-01T00:00:00Z',
            suite_name='Test report',
            total=10,
            passed=8,
            failed=2,
            skipped=0,
            success_rate=0.8,
            total_time=100.0,
            results=[],
        )

        assert report.suite_name == 'Test report'
        assert report.total == 10
        assert report.passed == 8
        assert report.failed == 2
        assert report.success_rate == 0.8
        assert report.total_time == 100.0
