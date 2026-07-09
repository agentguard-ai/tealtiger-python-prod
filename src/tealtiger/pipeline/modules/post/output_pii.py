"""Multi-Stage Defense Pipeline — Output PII Module (Python SDK).

Scans LLM response content for PII patterns (email addresses, phone numbers,
SSN, credit card numbers) and returns DENY with reason code PII_IN_RESPONSE
and ``remediation: 'redact'`` metadata when PII confidence exceeds a
configurable threshold.

This is the post-execution counterpart to the pre-execution PIIScannerModule.

Module: pipeline/modules/post/output_pii
Requirements: 7.2, 7.6, 7.7
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class PIIPattern:
    """A single PII detection pattern with associated confidence score."""

    name: str
    """Human-readable name for this pattern."""

    regex: str
    """Regular expression string to match PII instances."""

    confidence: float
    """Confidence score (0–1) assigned to each match of this pattern."""


@dataclass
class PIIFinding:
    """A single PII finding detected in response content."""

    pattern: str
    """Pattern name that matched."""

    confidence: float
    """Confidence score of this finding."""

    offset: int
    """Character offset where the match was found."""

    length: int
    """Length of the matched text."""


@dataclass
class OutputPIIConfig:
    """Configuration object for OutputPIIModule."""

    threshold: float = 0.5
    """Confidence threshold (0–1) above which PII triggers DENY."""

    patterns: Optional[List[PIIPattern]] = None
    """Custom patterns to scan for. If omitted, uses default patterns."""


# ---------------------------------------------------------------------------
# Default Patterns
# ---------------------------------------------------------------------------

DEFAULT_PII_PATTERNS: List[PIIPattern] = [
    PIIPattern(
        name="email",
        regex=r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        confidence=0.9,
    ),
    PIIPattern(
        name="phone",
        regex=r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        confidence=0.8,
    ),
    PIIPattern(
        name="ssn",
        regex=r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
        confidence=0.95,
    ),
    PIIPattern(
        name="credit_card",
        regex=r"\b(?:\d{4}[-.\s]?){3}\d{4}\b",
        confidence=0.9,
    ),
]


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class OutputPIIModule:
    """Scans LLM response content for PII patterns.

    Returns DENY with reason code PII_IN_RESPONSE and ``remediation: 'redact'``
    metadata when the maximum confidence of detected PII exceeds the configured
    threshold.

    Default patterns detect:
    - Email addresses (confidence: 0.9)
    - Phone numbers (confidence: 0.8)
    - Social Security Numbers (confidence: 0.95)
    - Credit card numbers (confidence: 0.9)
    """

    name: str = "OutputPIIModule"
    version: str = "1.0.0"

    def __init__(self, config: Optional[OutputPIIConfig] = None) -> None:
        cfg = config or OutputPIIConfig()
        self._threshold = cfg.threshold
        self._patterns = cfg.patterns or DEFAULT_PII_PATTERNS

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the response for PII content.

        Args:
            request: The module evaluation request (dict-like, includes _response).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        content = self._extract_response_content(request)

        if not content:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.output_pii_scan",
                "metadata": {
                    "module": self.name,
                    "findings": [],
                },
            }

        findings = self._scan_content(content)

        # Determine max confidence across all findings
        max_confidence = max((f.confidence for f in findings), default=0.0)

        if max_confidence > self._threshold:
            return {
                "action": "DENY",
                "reason_codes": ["PII_IN_RESPONSE"],
                "event_type": "pipeline.output_pii_scan",
                "metadata": {
                    "remediation": "redact",
                    "findings": [self._finding_to_dict(f) for f in findings],
                    "max_confidence": max_confidence,
                    "threshold": self._threshold,
                    "module": self.name,
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.output_pii_scan",
            "metadata": {
                "module": self.name,
                "findings": [self._finding_to_dict(f) for f in findings],
                "max_confidence": max_confidence,
                "threshold": self._threshold,
            },
        }

    def _extract_response_content(self, request: Any) -> str:
        """Extract response content from the evaluation request.

        In post-execution context, the response may be provided via:
        - ``request["_response"]`` (pipeline passes response here)
        - ``request["content"]`` (fallback, standard field)
        """
        if not isinstance(request, dict):
            return ""

        response = request.get("_response")
        if isinstance(response, str):
            return response

        return request.get("content") or ""

    def _scan_content(self, content: str) -> List[PIIFinding]:
        """Scan content against all configured PII patterns."""
        findings: List[PIIFinding] = []

        for pattern in self._patterns:
            for match in re.finditer(pattern.regex, content):
                findings.append(
                    PIIFinding(
                        pattern=pattern.name,
                        confidence=pattern.confidence,
                        offset=match.start(),
                        length=len(match.group()),
                    )
                )

        return findings

    @staticmethod
    def _finding_to_dict(finding: PIIFinding) -> Dict[str, Any]:
        """Convert a PIIFinding to a dictionary."""
        return {
            "pattern": finding.pattern,
            "confidence": finding.confidence,
            "offset": finding.offset,
            "length": finding.length,
        }
