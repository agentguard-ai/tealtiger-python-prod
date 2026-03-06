"""PolicyTester - Policy testing framework for TealEngine.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.5: Policy Test Harness

This module provides the PolicyTester class for executing policy tests:
- Run individual test cases
- Run test suites
- Calculate coverage
- Export reports (JSON, JUnit XML)
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from xml.etree import ElementTree as ET

from ..types import Decision, DecisionAction, ReasonCode
from .types import (
    CoverageInfo,
    PolicyTestCase,
    PolicyTestReport,
    PolicyTestResult,
    PolicyTestSuite,
)


class PolicyTester:
    """Policy testing framework for TealEngine.
    
    Executes test cases against a TealEngine instance and generates reports.
    
    Example:
        ```python
        from tealtiger import TealEngine, PolicyTester, PolicyMode
        
        engine = TealEngine(
            policies=my_policies,
            mode={'defaultMode': PolicyMode.ENFORCE}
        )
        
        tester = PolicyTester(engine)
        
        test_case = PolicyTestCase(
            name='Block file deletion',
            context={
                'agentId': 'agent-001',
                'action': 'tool.execute',
                'tool': 'file_delete'
            },
            expected={
                'action': DecisionAction.DENY,
                'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED]
            }
        )
        
        result = tester.run_test(test_case)
        print(f"Test {'PASSED' if result.passed else 'FAILED'}")
        ```
    """

    def __init__(self, engine: Any) -> None:
        """Initialize PolicyTester with a TealEngine instance.
        
        Args:
            engine: TealEngine instance to test
        """
        self.engine = engine
        self.tracked_policies: Set[str] = set()
        self.tested_policies: Set[str] = set()
        self._initialize_tracking()

    def run_test(self, test_case: PolicyTestCase) -> PolicyTestResult:
        """Run a single test case.
        
        Args:
            test_case: Test case to execute
            
        Returns:
            Test result with pass/fail status and details
        """
        start_time = time.time()

        try:
            # Execute policy evaluation
            decision = self.engine.evaluate(test_case.context)

            # Track tested policies
            if hasattr(decision, 'policy_id') and decision.policy_id:
                self.tested_policies.add(decision.policy_id)

            # Convert Decision to dict for comparison
            actual_dict = self._decision_to_dict(decision)

            # Check if result matches expected
            passed, failure_reason = self._matches_expected(
                decision, test_case.expected
            )

            execution_time = (time.time() - start_time) * 1000  # Convert to ms

            return PolicyTestResult(
                name=test_case.name,
                passed=passed,
                actual=actual_dict,
                expected=test_case.expected,
                failure_reason=failure_reason if not passed else None,
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            return PolicyTestResult(
                name=test_case.name,
                passed=False,
                actual={
                    'action': 'ERROR',
                    'reason': str(e),
                    'error': True,
                },
                expected=test_case.expected,
                failure_reason=f"Exception during test execution: {str(e)}",
                execution_time=execution_time,
            )

    def run_suite(self, suite: PolicyTestSuite) -> PolicyTestReport:
        """Run a test suite.
        
        Args:
            suite: Test suite to execute
            
        Returns:
            Comprehensive test report with results and coverage
        """
        start_time = time.time()
        results: List[PolicyTestResult] = []

        # Reset coverage tracking for this suite
        self.tested_policies.clear()

        # Run each test case
        for test_case in suite.tests:
            result = self.run_test(test_case)
            results.append(result)

        # Calculate metrics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        success_rate = passed / total if total > 0 else 0.0
        total_time = (time.time() - start_time) * 1000

        # Calculate coverage
        coverage = self._calculate_coverage()

        return PolicyTestReport(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            suite_name=suite.name,
            total=total,
            passed=passed,
            failed=failed,
            skipped=0,
            success_rate=success_rate,
            total_time=total_time,
            results=results,
            coverage=coverage,
        )

    def run_from_file(self, file_path: str) -> PolicyTestReport:
        """Load and run tests from a JSON file.
        
        Args:
            file_path: Path to JSON file containing test suite
            
        Returns:
            Test report
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Test file not found: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Parse test suite
        suite = PolicyTestSuite(**data)

        return self.run_suite(suite)

    def export_report(
        self, report: PolicyTestReport, format: str = 'json'
    ) -> str:
        """Export test report to JSON or JUnit XML format.
        
        Args:
            report: Test report to export
            format: Output format ('json' or 'junit')
            
        Returns:
            Formatted report string
            
        Raises:
            ValueError: If format is not supported
        """
        if format == 'json':
            return self._export_json(report)
        elif format == 'junit':
            return self._export_junit(report)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'junit'")

    def _initialize_tracking(self) -> None:
        """Initialize policy tracking from engine configuration."""
        # Get policies from engine
        policies = self.engine.get_policies()

        # Track tool policies
        if 'tools' in policies and policies['tools']:
            for tool_name in policies['tools'].keys():
                self.tracked_policies.add(f"tools.{tool_name}")

        # Track identity policy
        if 'identity' in policies and policies['identity']:
            self.tracked_policies.add('identity')

        # Track code execution policy
        if 'codeExecution' in policies and policies['codeExecution']:
            self.tracked_policies.add('codeExecution')

        # Track behavioral policy
        if 'behavioral' in policies and policies['behavioral']:
            self.tracked_policies.add('behavioral')

        # Track content policy
        if 'content' in policies and policies['content']:
            self.tracked_policies.add('content')
            if policies['content'].get('pii'):
                self.tracked_policies.add('content.pii')
            if policies['content'].get('moderation'):
                self.tracked_policies.add('content.moderation')

    def _calculate_coverage(self) -> CoverageInfo:
        """Calculate policy coverage."""
        total_policies = len(self.tracked_policies)
        tested_policies = len(self.tested_policies)
        coverage_percentage = (
            (tested_policies / total_policies * 100) if total_policies > 0 else 0.0
        )

        untested = sorted(
            list(self.tracked_policies - self.tested_policies)
        )

        return CoverageInfo(
            total_policies=total_policies,
            tested_policies=tested_policies,
            coverage_percentage=coverage_percentage,
            untested_policies=untested,
        )

    def _decision_to_dict(self, decision: Decision) -> Dict[str, Any]:
        """Convert Decision object to dictionary."""
        if isinstance(decision, dict):
            return decision

        return {
            'action': decision.action.value if hasattr(decision.action, 'value') else decision.action,
            'reason_codes': [
                rc.value if hasattr(rc, 'value') else rc
                for rc in decision.reason_codes
            ],
            'risk_score': decision.risk_score,
            'mode': decision.mode.value if hasattr(decision.mode, 'value') else decision.mode,
            'policy_id': decision.policy_id,
            'policy_version': decision.policy_version,
            'correlation_id': decision.correlation_id,
            'reason': decision.reason,
            'metadata': decision.metadata,
        }

    def _matches_expected(
        self, actual: Decision, expected: Any
    ) -> tuple[bool, Optional[str]]:
        """Check if actual decision matches expected outcome.
        
        Returns:
            Tuple of (passed, failure_reason)
        """
        errors: List[str] = []

        # Check action
        actual_action = actual.action.value if hasattr(actual.action, 'value') else actual.action
        expected_action = expected.action.value if hasattr(expected.action, 'value') else expected.action

        if actual_action != expected_action:
            errors.append(
                f"Expected action={expected_action}, got action={actual_action}"
            )

        # Check reason codes if specified
        if expected.reason_codes:
            actual_codes = [
                rc.value if hasattr(rc, 'value') else rc
                for rc in actual.reason_codes
            ]
            expected_codes = [
                rc.value if hasattr(rc, 'value') else rc
                for rc in expected.reason_codes
            ]

            missing_codes = [
                code for code in expected_codes if code not in actual_codes
            ]

            if missing_codes:
                errors.append(
                    f"Missing expected reason codes: {', '.join(missing_codes)}"
                )

        # Check risk score range if specified
        if expected.risk_score_range:
            min_score = expected.risk_score_range.get('min', 0)
            max_score = expected.risk_score_range.get('max', 100)

            if not (min_score <= actual.risk_score <= max_score):
                errors.append(
                    f"Risk score {actual.risk_score} not in expected range [{min_score}, {max_score}]"
                )

        # Check mode if specified
        if expected.mode:
            actual_mode = actual.mode.value if hasattr(actual.mode, 'value') else actual.mode
            expected_mode = expected.mode.value if hasattr(expected.mode, 'value') else expected.mode

            if actual_mode != expected_mode:
                errors.append(
                    f"Expected mode={expected_mode}, got mode={actual_mode}"
                )

        if errors:
            return False, '; '.join(errors)

        return True, None

    def _export_json(self, report: PolicyTestReport) -> str:
        """Export report as JSON."""
        return report.model_dump_json(indent=2)

    def _export_junit(self, report: PolicyTestReport) -> str:
        """Export report as JUnit XML."""
        # Create root testsuite element
        testsuite = ET.Element('testsuite')
        testsuite.set('name', report.suite_name)
        testsuite.set('tests', str(report.total))
        testsuite.set('failures', str(report.failed))
        testsuite.set('skipped', str(report.skipped))
        testsuite.set('time', f"{report.total_time / 1000:.3f}")
        testsuite.set('timestamp', report.timestamp)

        # Add test cases
        for result in report.results:
            testcase = ET.SubElement(testsuite, 'testcase')
            testcase.set('name', result.name)
            testcase.set('classname', report.suite_name)
            testcase.set('time', f"{result.execution_time / 1000:.3f}")

            if not result.passed:
                failure = ET.SubElement(testcase, 'failure')
                failure.set('message', result.failure_reason or 'Test failed')
                failure.text = result.failure_reason or 'Test failed'

        # Convert to string
        tree = ET.ElementTree(testsuite)
        ET.indent(tree, space='  ')

        import io
        output = io.BytesIO()
        tree.write(output, encoding='utf-8', xml_declaration=True)
        return output.getvalue().decode('utf-8')
