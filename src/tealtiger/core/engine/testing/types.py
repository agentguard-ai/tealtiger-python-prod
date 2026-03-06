"""Type definitions for policy testing framework.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.5: Policy Test Harness

This module defines types for policy testing:
- PolicyTestCase: Individual test case
- PolicyTestSuite: Collection of test cases
- PolicyTestResult: Result of a single test
- PolicyTestReport: Comprehensive test report with coverage
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..types import DecisionAction, PolicyMode, ReasonCode


class ExpectedDecision(BaseModel):
    """Expected decision outcome for a test case."""

    action: DecisionAction = Field(
        ...,
        description="Expected decision action (ALLOW, DENY, etc.)",
    )

    reason_codes: Optional[List[ReasonCode]] = Field(
        None,
        description="Expected reason codes (all must be present in actual decision)",
    )

    risk_score_range: Optional[Dict[str, int]] = Field(
        None,
        description="Expected risk score range (min/max)",
    )

    mode: Optional[PolicyMode] = Field(
        None,
        description="Expected policy mode",
    )


class PolicyTestCase(BaseModel):
    """Test case for policy testing.
    
    Defines input context and expected decision outcome.
    """

    name: str = Field(
        ...,
        description="Test case name",
    )

    description: Optional[str] = Field(
        None,
        description="Test case description",
    )

    context: Dict[str, Any] = Field(
        ...,
        description="Request context to test (agentId, action, tool, content, etc.)",
    )

    expected: ExpectedDecision = Field(
        ...,
        description="Expected decision outcome",
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Tags for filtering tests (e.g., ['pii', 'injection'])",
    )


class PolicyTestSuite(BaseModel):
    """Test suite containing multiple test cases.
    
    Includes policy configuration and mode settings.
    """

    name: str = Field(
        ...,
        description="Test suite name",
    )

    description: Optional[str] = Field(
        None,
        description="Test suite description",
    )

    policy: Dict[str, Any] = Field(
        ...,
        description="Policy configuration to test",
    )

    mode: Optional[Dict[str, Any]] = Field(
        None,
        description="Mode configuration (defaultMode, policyModes, environmentModes)",
    )

    tests: List[PolicyTestCase] = Field(
        ...,
        description="Test cases in this suite",
    )


class PolicyTestResult(BaseModel):
    """Result of running a single test case."""

    name: str = Field(
        ...,
        description="Test case name",
    )

    passed: bool = Field(
        ...,
        description="Whether the test passed",
    )

    actual: Dict[str, Any] = Field(
        ...,
        description="Actual decision returned by TealEngine",
    )

    expected: ExpectedDecision = Field(
        ...,
        description="Expected decision",
    )

    failure_reason: Optional[str] = Field(
        None,
        description="Detailed failure reason (if test failed)",
    )

    execution_time: float = Field(
        ...,
        description="Execution time in milliseconds",
    )


class CoverageInfo(BaseModel):
    """Policy coverage information."""

    total_policies: int = Field(
        ...,
        description="Total number of policies",
    )

    tested_policies: int = Field(
        ...,
        description="Number of tested policies",
    )

    coverage_percentage: float = Field(
        ...,
        description="Coverage percentage (0-100)",
    )

    untested_policies: List[str] = Field(
        ...,
        description="List of untested policy IDs",
    )


class PolicyTestReport(BaseModel):
    """Comprehensive test report with coverage information."""

    timestamp: str = Field(
        ...,
        description="Report timestamp (ISO 8601)",
    )

    suite_name: str = Field(
        ...,
        description="Test suite name",
    )

    total: int = Field(
        ...,
        description="Total number of tests",
    )

    passed: int = Field(
        ...,
        description="Number of passed tests",
    )

    failed: int = Field(
        ...,
        description="Number of failed tests",
    )

    skipped: int = Field(
        default=0,
        description="Number of skipped tests",
    )

    success_rate: float = Field(
        ...,
        description="Success rate (0-1)",
    )

    total_time: float = Field(
        ...,
        description="Total execution time in milliseconds",
    )

    results: List[PolicyTestResult] = Field(
        ...,
        description="Individual test results",
    )

    coverage: Optional[CoverageInfo] = Field(
        None,
        description="Coverage information",
    )
