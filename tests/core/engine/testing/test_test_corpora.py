"""Unit tests for TestCorpora.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.5: Policy Test Harness

Tests for starter test corpora:
- Prompt injection test cases
- PII detection test cases
- Unsafe code test cases
- Tool misuse test cases
- Cost limit test cases
"""

import pytest

from tealtiger.core.engine.testing import TestCorpora
from tealtiger.core.engine.types import DecisionAction, ReasonCode


class TestTestCorpora:
    """Test suite for TestCorpora."""

    def test_prompt_injection_corpora(self):
        """Test prompt injection test cases."""
        tests = TestCorpora.prompt_injection()

        assert len(tests) > 0
        assert all(test.name for test in tests)
        assert all(test.context for test in tests)
        assert all(test.expected for test in tests)

        # All should expect DENY action
        for test in tests:
            assert test.expected.action == DecisionAction.DENY
            assert ReasonCode.PROMPT_INJECTION_DETECTED in test.expected.reason_codes

        # Check tags
        for test in tests:
            assert 'prompt-injection' in test.tags
            assert 'security' in test.tags

    def test_prompt_injection_coverage(self):
        """Test prompt injection corpora covers key scenarios."""
        tests = TestCorpora.prompt_injection()
        test_names = [test.name.lower() for test in tests]

        # Should cover key injection patterns
        assert any('ignore' in name for name in test_names)
        assert any('system' in name or 'prompt' in name for name in test_names)
        assert any('role' in name for name in test_names)

    def test_pii_detection_corpora(self):
        """Test PII detection test cases."""
        tests = TestCorpora.pii_detection()

        assert len(tests) > 0
        assert all(test.name for test in tests)
        assert all(test.context for test in tests)
        assert all(test.expected for test in tests)

        # All should expect DENY action
        for test in tests:
            assert test.expected.action == DecisionAction.DENY
            assert ReasonCode.PII_DETECTED in test.expected.reason_codes

        # Check tags
        for test in tests:
            assert 'pii' in test.tags
            assert 'security' in test.tags

    def test_pii_detection_coverage(self):
        """Test PII detection corpora covers key PII types."""
        tests = TestCorpora.pii_detection()
        test_names = [test.name.lower() for test in tests]

        # Should cover key PII types
        assert any('ssn' in name for name in test_names)
        assert any('credit' in name or 'card' in name for name in test_names)
        assert any('email' in name for name in test_names)
        assert any('phone' in name for name in test_names)

    def test_unsafe_code_corpora(self):
        """Test unsafe code detection test cases."""
        tests = TestCorpora.unsafe_code()

        assert len(tests) > 0
        assert all(test.name for test in tests)
        assert all(test.context for test in tests)
        assert all(test.expected for test in tests)

        # All should expect DENY action
        for test in tests:
            assert test.expected.action == DecisionAction.DENY
            assert ReasonCode.UNSAFE_CODE_DETECTED in test.expected.reason_codes

        # Check tags
        for test in tests:
            assert 'code-execution' in test.tags
            assert 'security' in test.tags

    def test_unsafe_code_coverage(self):
        """Test unsafe code corpora covers key dangerous patterns."""
        tests = TestCorpora.unsafe_code()
        test_names = [test.name.lower() for test in tests]

        # Should cover dangerous functions
        assert any('eval' in name for name in test_names)
        assert any('exec' in name for name in test_names)
        assert any('system' in name for name in test_names)

    def test_tool_misuse_corpora(self):
        """Test tool misuse detection test cases."""
        tests = TestCorpora.tool_misuse()

        assert len(tests) > 0
        assert all(test.name for test in tests)
        assert all(test.context for test in tests)
        assert all(test.expected for test in tests)

        # All should expect DENY action
        for test in tests:
            assert test.expected.action == DecisionAction.DENY

        # Check tags
        for test in tests:
            assert 'tool-misuse' in test.tags

    def test_tool_misuse_coverage(self):
        """Test tool misuse corpora covers key scenarios."""
        tests = TestCorpora.tool_misuse()
        test_names = [test.name.lower() for test in tests]

        # Should cover key misuse patterns
        assert any('disallowed' in name or 'not allowed' in name for name in test_names)
        assert any('rate limit' in name for name in test_names)
        assert any('size limit' in name for name in test_names)

    def test_cost_limits_corpora(self):
        """Test cost limit detection test cases."""
        tests = TestCorpora.cost_limits()

        assert len(tests) > 0
        assert all(test.name for test in tests)
        assert all(test.context for test in tests)
        assert all(test.expected for test in tests)

        # Check tags
        for test in tests:
            assert 'cost' in test.tags
            assert 'finops' in test.tags

    def test_cost_limits_coverage(self):
        """Test cost limits corpora covers key scenarios."""
        tests = TestCorpora.cost_limits()
        test_names = [test.name.lower() for test in tests]

        # Should cover key cost scenarios
        assert any('limit' in name for name in test_names)
        assert any('budget' in name for name in test_names)
        assert any('threshold' in name for name in test_names)

    def test_all_corpora(self):
        """Test getting all test cases."""
        all_tests = TestCorpora.all()

        # Should include tests from all categories
        prompt_injection = TestCorpora.prompt_injection()
        pii_detection = TestCorpora.pii_detection()
        unsafe_code = TestCorpora.unsafe_code()
        tool_misuse = TestCorpora.tool_misuse()
        cost_limits = TestCorpora.cost_limits()

        expected_total = (
            len(prompt_injection)
            + len(pii_detection)
            + len(unsafe_code)
            + len(tool_misuse)
            + len(cost_limits)
        )

        assert len(all_tests) == expected_total

    def test_test_case_structure(self):
        """Test that all test cases have proper structure."""
        all_tests = TestCorpora.all()

        for test in all_tests:
            # Required fields
            assert test.name
            assert test.context
            assert test.expected
            assert test.expected.action

            # Context should have agentId and action
            assert 'agentId' in test.context
            assert 'action' in test.context

            # Expected should have reason_codes
            assert test.expected.reason_codes
            assert len(test.expected.reason_codes) > 0

            # Tags should be present
            assert test.tags
            assert len(test.tags) > 0

    def test_test_case_uniqueness(self):
        """Test that test case names are unique."""
        all_tests = TestCorpora.all()
        names = [test.name for test in all_tests]

        # All names should be unique
        assert len(names) == len(set(names))

    def test_minimum_test_count(self):
        """Test that we have at least 20 test cases total (as per spec)."""
        all_tests = TestCorpora.all()

        # Spec requires at least 20 test cases
        assert len(all_tests) >= 20

    def test_prompt_injection_content_variety(self):
        """Test that prompt injection tests have varied content."""
        tests = TestCorpora.prompt_injection()
        contents = [test.context.get('content', '') for test in tests]

        # All should have content
        assert all(contents)

        # Content should be varied (no duplicates)
        assert len(contents) == len(set(contents))

    def test_pii_detection_content_variety(self):
        """Test that PII detection tests have varied content."""
        tests = TestCorpora.pii_detection()
        contents = [test.context.get('content', '') for test in tests]

        # All should have content
        assert all(contents)

        # Content should be varied (no duplicates)
        assert len(contents) == len(set(contents))

    def test_unsafe_code_variety(self):
        """Test that unsafe code tests have varied code samples."""
        tests = TestCorpora.unsafe_code()
        codes = [test.context.get('code', '') for test in tests]

        # All should have code
        assert all(codes)

        # Code should be varied (no duplicates)
        assert len(codes) == len(set(codes))

    def test_cost_limits_scenarios(self):
        """Test that cost limits cover different scenarios."""
        tests = TestCorpora.cost_limits()

        # Should have tests for different cost-related reason codes
        reason_codes = set()
        for test in tests:
            reason_codes.update(test.expected.reason_codes)

        # Should cover multiple cost-related codes
        cost_codes = [
            ReasonCode.COST_LIMIT_EXCEEDED,
            ReasonCode.COST_BUDGET_EXCEEDED,
            ReasonCode.COST_THRESHOLD_APPROACHING,
            ReasonCode.COST_ANOMALY_DETECTED,
            ReasonCode.MODEL_TIER_NOT_ALLOWED,
        ]

        # At least 3 different cost reason codes should be covered
        covered_codes = [code for code in cost_codes if code in reason_codes]
        assert len(covered_codes) >= 3
