"""Multi-Stage Defense Pipeline — Hallucination Marker Module (Python SDK).

Flags response content containing hallucination indicators such as fabricated
URLs, unsupported citations, low-confidence markers, and made-up statistics.
Returns MONITOR (never DENY) with flagged segments in metadata.

Module: pipeline/modules/post/hallucination_marker
Requirements: 7.3, 7.6, 7.7
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class HallucinationIndicator:
    """A single hallucination detection indicator with an associated regex pattern."""

    name: str
    """Human-readable name for this indicator."""

    regex: str
    """Regular expression string to detect the indicator."""

    confidence: float
    """Confidence weight (0–1) — how likely this match indicates hallucination."""

    description: Optional[str] = None
    """Description of what this indicator detects."""


@dataclass
class HallucinationSegment:
    """A flagged segment in the response that may indicate hallucination."""

    indicator: str
    """Indicator name that matched."""

    text: str
    """The matched text."""

    confidence: float
    """Confidence score for this finding."""

    offset: int
    """Character offset where the match was found."""

    length: int
    """Length of the matched text."""


@dataclass
class HallucinationMarkerConfig:
    """Configuration object for HallucinationMarkerModule."""

    indicators: Optional[List[HallucinationIndicator]] = None
    """Custom indicators to scan for. If omitted, uses default indicators."""

    confidence_threshold: float = 0.3
    """Confidence threshold (0–1) above which the module flags for MONITOR."""


# ---------------------------------------------------------------------------
# Default Indicators
# ---------------------------------------------------------------------------

DEFAULT_INDICATORS: List[HallucinationIndicator] = [
    HallucinationIndicator(
        name="fabricated_url",
        description="URLs with non-existent TLDs or suspicious patterns",
        regex=r"https?://(?:www\.)?[a-zA-Z0-9-]+\.(?:xyz123|fakeTLD|example\.fake|notreal|zzz|qqqq|internal-only)\b[^\s]*",
        confidence=0.85,
    ),
    HallucinationIndicator(
        name="suspicious_url_pattern",
        description="URLs with overly deep paths suggesting fabrication",
        regex=r"https?://(?:www\.)?[a-zA-Z0-9-]+\.[a-z]{2,6}/(?:[a-z0-9-]+/){4,}[a-z0-9-]+",
        confidence=0.4,
    ),
    HallucinationIndicator(
        name="unsupported_citation",
        description="Academic citations in [Author, Year] format without supporting data",
        regex=r"\[(?:[A-Z][a-z]+(?:\s(?:et\s+al\.?|&\s+[A-Z][a-z]+))?),?\s+\d{4}\]",
        confidence=0.7,
    ),
    HallucinationIndicator(
        name="confidence_hedging",
        description="Phrases indicating low confidence or uncertainty",
        regex=r"\b(?:I(?:'m| am)\s+not\s+(?:sure|certain)\s+but|I\s+believe|I\s+think\s+(?:that|it)|if\s+I\s+recall\s+correctly|as\s+far\s+as\s+I\s+know|to\s+the\s+best\s+of\s+my\s+knowledge)\b",
        confidence=0.35,
    ),
    HallucinationIndicator(
        name="fabricated_statistic",
        description="Made-up statistics with high specificity",
        regex=r"\b\d{1,3}\.\d{3,}%|\bexactly\s+\d+\.\d{2,}\s*(?:%|percent|million|billion|thousand)\b",
        confidence=0.6,
    ),
]


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class HallucinationMarkerModule:
    """Flags response content containing hallucination indicators and returns
    MONITOR with flagged segments in metadata.

    This module NEVER returns DENY — it only flags content for observation
    and audit.

    Default indicators detect:
    - Fabricated URLs with non-existent TLDs (confidence: 0.85)
    - Suspicious URL patterns with overly deep paths (confidence: 0.4)
    - Academic citations in [Author, Year] format (confidence: 0.7)
    - Confidence hedging phrases (confidence: 0.35)
    - Fabricated statistics with high decimal specificity (confidence: 0.6)
    """

    name: str = "HallucinationMarkerModule"
    version: str = "1.0.0"

    def __init__(self, config: Optional[HallucinationMarkerConfig] = None) -> None:
        cfg = config or HallucinationMarkerConfig()
        self._confidence_threshold = cfg.confidence_threshold
        self._indicators = cfg.indicators or DEFAULT_INDICATORS

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the response for hallucination indicators.

        Args:
            request: The module evaluation request (dict-like).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        content = request.get("content", "") if isinstance(request, dict) else ""

        if not content:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.hallucination_scan",
                "metadata": {
                    "module": self.name,
                    "flagged_segments": [],
                },
            }

        segments = self._scan_content(content)

        # Determine max confidence across all flagged segments
        max_confidence = max((s.confidence for s in segments), default=0.0)

        # Build indicator counts for observability
        indicator_counts: Dict[str, int] = {}
        for segment in segments:
            indicator_counts[segment.indicator] = (
                indicator_counts.get(segment.indicator, 0) + 1
            )

        if max_confidence >= self._confidence_threshold and segments:
            return {
                "action": "MONITOR",
                "reason_codes": ["HALLUCINATION_DETECTED"],
                "event_type": "pipeline.hallucination_scan",
                "metadata": {
                    "module": self.name,
                    "flagged_segments": [self._segment_to_dict(s) for s in segments],
                    "max_confidence": max_confidence,
                    "confidence_threshold": self._confidence_threshold,
                    "indicator_counts": indicator_counts,
                    "total_flags": len(segments),
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.hallucination_scan",
            "metadata": {
                "module": self.name,
                "flagged_segments": [],
                "max_confidence": max_confidence,
                "confidence_threshold": self._confidence_threshold,
            },
        }

    def _scan_content(self, content: str) -> List[HallucinationSegment]:
        """Scan content against all configured hallucination indicators."""
        segments: List[HallucinationSegment] = []

        for indicator in self._indicators:
            flags = re.IGNORECASE if "(?i)" not in indicator.regex else 0
            for match in re.finditer(indicator.regex, content, flags):
                segments.append(
                    HallucinationSegment(
                        indicator=indicator.name,
                        text=match.group(),
                        confidence=indicator.confidence,
                        offset=match.start(),
                        length=len(match.group()),
                    )
                )

        return segments

    @staticmethod
    def _segment_to_dict(segment: HallucinationSegment) -> Dict[str, Any]:
        """Convert a HallucinationSegment to a dictionary."""
        return {
            "indicator": segment.indicator,
            "text": segment.text,
            "confidence": segment.confidence,
            "offset": segment.offset,
            "length": segment.length,
        }
