"""Multi-Stage Defense Pipeline — Content Moderation Module (Python SDK).

Evaluates LLM response content against configurable content policies
(toxicity, bias, harmful content, violence, sexual) using keyword-based
detection. Returns DENY with ``remediation: 'resample'`` metadata when a
policy violation is detected.

Module: pipeline/modules/post/content_moderation
Requirements: 7.1, 7.6, 7.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ContentModerationConfig:
    """Configuration object for ContentModerationModule."""

    categories: Optional[List[str]] = None
    """Content categories to check (e.g., 'toxicity', 'bias', 'harmful', 'violence', 'sexual')."""

    thresholds: Optional[Dict[str, float]] = None
    """Per-category threshold (0–1). Default: 0.5 for all categories."""

    keywords: Optional[Dict[str, List[str]]] = None
    """Category → keyword list for simple keyword-based detection."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ContentModerationFinding:
    """A single content moderation finding detected in response content."""

    category: str
    """Category that was violated."""

    keyword: str
    """The keyword that triggered the finding."""

    score: float
    """Confidence/severity score for this finding (0–1)."""

    offset: int
    """Character offset where the keyword was found."""


# ---------------------------------------------------------------------------
# Default Keywords
# ---------------------------------------------------------------------------

DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "toxicity": [
        "kill yourself", "kys", "die in a fire", "go die", "i hate you",
        "worthless", "piece of shit", "scum", "subhuman", "trash person",
    ],
    "bias": [
        "all women are", "all men are", "those people always",
        "typical of their kind", "they are inferior", "naturally stupid",
        "genetically predisposed to crime",
    ],
    "harmful": [
        "how to make a bomb", "how to synthesize", "instructions for poison",
        "hack into", "steal identity", "bypass security",
        "exploit vulnerability", "social engineer",
    ],
    "violence": [
        "murder them", "stab", "shoot them", "blow them up",
        "beat them", "torture", "dismember", "behead",
    ],
    "sexual": [
        "explicit sexual", "pornographic", "sexual acts with minors",
        "non-consensual", "revenge porn",
    ],
}

DEFAULT_THRESHOLD: float = 0.5
DEFAULT_CATEGORIES: List[str] = ["toxicity", "bias", "harmful", "violence", "sexual"]


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class ContentModerationModule:
    """Evaluates response content against configurable content policies using
    keyword-based detection.

    When a policy violation is found, returns DENY with
    ``remediation: 'resample'`` metadata.

    Detection approach:
    - For each configured category, scans response content for keyword matches
    - A match score is calculated based on keyword length
    - When any category's max score exceeds its threshold, the module returns DENY
    """

    name: str = "ContentModerationModule"
    version: str = "1.0.0"

    def __init__(self, config: Optional[ContentModerationConfig] = None) -> None:
        cfg = config or ContentModerationConfig()
        self._categories = cfg.categories or DEFAULT_CATEGORIES
        self._thresholds = cfg.thresholds or {}
        self._keywords = cfg.keywords or DEFAULT_KEYWORDS

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the response content for content policy violations.

        Args:
            request: The module evaluation request (dict-like, includes _response).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        content = self._extract_content(request)

        if not content:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.content_moderation",
                "metadata": {
                    "module": self.name,
                    "findings": [],
                },
            }

        findings = self._scan_content(content)
        categories_violated = self._get_categories_violated(findings)

        if categories_violated:
            reason_codes = [
                f"CONTENT_MODERATION_{cat.upper()}" for cat in categories_violated
            ]
            return {
                "action": "DENY",
                "reason_codes": reason_codes,
                "event_type": "pipeline.content_moderation",
                "metadata": {
                    "remediation": "resample",
                    "findings": [self._finding_to_dict(f) for f in findings],
                    "categories_violated": categories_violated,
                    "module": self.name,
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.content_moderation",
            "metadata": {
                "module": self.name,
                "findings": [self._finding_to_dict(f) for f in findings],
                "categories_violated": [],
            },
        }

    def _extract_content(self, request: Any) -> str:
        """Extract response content from the evaluation request.

        Checks ``_response`` (pipeline convention) and falls back to ``content``.
        """
        if not isinstance(request, dict):
            return ""

        response = request.get("_response")
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            content = response.get("content")
            if isinstance(content, str):
                return content

        return request.get("content") or ""

    def _scan_content(self, content: str) -> List[ContentModerationFinding]:
        """Scan content against keyword lists for all configured categories."""
        findings: List[ContentModerationFinding] = []
        normalized_content = content.lower()

        for category in self._categories:
            category_keywords = self._keywords.get(category)
            if not category_keywords:
                continue

            for keyword in category_keywords:
                normalized_keyword = keyword.lower()
                search_start = 0

                while True:
                    index = normalized_content.find(normalized_keyword, search_start)
                    if index == -1:
                        break

                    # Score based on keyword length
                    score = min(1.0, 0.6 + (len(normalized_keyword) / 50))

                    findings.append(
                        ContentModerationFinding(
                            category=category,
                            keyword=keyword,
                            score=score,
                            offset=index,
                        )
                    )

                    search_start = index + len(normalized_keyword)

        return findings

    def _get_categories_violated(
        self, findings: List[ContentModerationFinding]
    ) -> List[str]:
        """Determine which categories have violations above their threshold."""
        violated: List[str] = []

        for category in self._categories:
            category_findings = [f for f in findings if f.category == category]
            if not category_findings:
                continue

            max_score = max(f.score for f in category_findings)
            threshold = self._thresholds.get(category, DEFAULT_THRESHOLD)

            if max_score > threshold:
                violated.append(category)

        return violated

    @staticmethod
    def _finding_to_dict(finding: ContentModerationFinding) -> Dict[str, Any]:
        """Convert a finding to a dictionary."""
        return {
            "category": finding.category,
            "keyword": finding.keyword,
            "score": finding.score,
            "offset": finding.offset,
        }
