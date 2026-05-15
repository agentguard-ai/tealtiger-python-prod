"""TealRegistry v2 — Tool Description Injection Scanner & Composition Allowlist.

Scans tool description fields for injection patterns that could
manipulate agent behavior through MCP tool definitions.

Detects:
- Unicode manipulation (Tag-block U+E0000–U+E007F, variation selectors U+FE00–U+FE0F,
  zero-width chars U+200B, U+200C, U+200D, U+2060, U+FEFF)
- Imperative verbs ("ignore", "override", "execute", "you must")
- Conditional logic ("if the user", "when asked", "upon receiving")

Also provides adapter composition allowlist checking for approved adapter sets.

Module: registry/detectors
Requirements: 12.1, 12.3
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# ── Constants ────────────────────────────────────────────────────

REASON_CODE_INJECTION = "TOOL_DESCRIPTION_INJECTION"
REASON_CODE_COMPOSITION = "UNAPPROVED_ADAPTER_COMPOSITION"


# ── Unicode Manipulation Pattern ─────────────────────────────────
# Tag-block characters: U+E0000–U+E007F
# Variation selectors: U+FE00–U+FE0F
# Zero-width characters: U+200B, U+200C, U+200D, U+2060, U+FEFF

_UNICODE_MANIPULATION_REGEX = re.compile(
    r"[\U000E0000-\U000E007F\uFE00-\uFE0F\u200B\u200C\u200D\u2060\uFEFF]"
)


# ── Imperative Verb Patterns ─────────────────────────────────────
# Matches phrases like "ignore previous", "override the", "execute this",
# "you must", "you should", "always do", "never do", "disregard".

_IMPERATIVE_VERB_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b(ignore|disregard|forget|override|bypass|skip)\b", re.IGNORECASE),
    re.compile(
        r"\b(execute|run|perform|invoke)\s+(this|the|a|an|immediately)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byou\s+(must|should|shall|need\s+to|have\s+to|are\s+required\s+to)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(always|never)\s+(do|perform|execute|ignore|override|respond|output)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(do\s+not|don't)\s+(follow|obey|respect|enforce)\b",
        re.IGNORECASE,
    ),
]


# ── Conditional Logic Patterns ───────────────────────────────────
# Matches phrases like "if the user", "when asked", "upon receiving",
# "in case of", "whenever".

_CONDITIONAL_LOGIC_PATTERNS: List[re.Pattern[str]] = [
    re.compile(
        r"\b(if|when|whenever)\s+(the\s+)?(user|operator|admin|system|agent)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(when\s+asked|upon\s+receiving|after\s+receiving)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(in\s+case\s+of|in\s+the\s+event)\b", re.IGNORECASE),
    re.compile(
        r"\b(if\s+prompted|when\s+prompted|once\s+triggered)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(on\s+condition|provided\s+that|assuming\s+that)\b",
        re.IGNORECASE,
    ),
]


# ── Tool Description Scanner ─────────────────────────────────────


def scan_tool_description(description: str) -> Dict[str, object]:
    """Scan a tool description for injection patterns.

    Checks for:
    - Unicode manipulation (Tag-block, variation selectors, zero-width chars)
    - Imperative verbs ("ignore", "override", "execute", "you must")
    - Conditional logic ("if the user", "when asked", "upon receiving")

    Args:
        description: The tool description text to scan.

    Returns:
        A dict with keys:
        - "suspicious" (bool): Whether the description contains suspicious patterns.
        - "patterns" (list[str]): List of pattern categories detected.
        - "reason_code" (str): Always "TOOL_DESCRIPTION_INJECTION".
    """
    patterns: List[str] = []

    # Check for Unicode manipulation
    if _UNICODE_MANIPULATION_REGEX.search(description):
        patterns.append("unicode_manipulation")

    # Check for imperative verbs
    for pattern in _IMPERATIVE_VERB_PATTERNS:
        if pattern.search(description):
            patterns.append("imperative_verb")
            break

    # Check for conditional logic
    for pattern in _CONDITIONAL_LOGIC_PATTERNS:
        if pattern.search(description):
            patterns.append("conditional_logic")
            break

    return {
        "suspicious": len(patterns) > 0,
        "patterns": patterns,
        "reason_code": REASON_CODE_INJECTION,
    }


# ── Composition Allowlist ─────────────────────────────────────────


class CompositionAllowlist:
    """Manages an allowlist of approved adapter combinations.

    The allowlist is a list of approved adapter sets. Each set is a list
    of adapter names. A composition is allowed if it exactly matches one of
    the approved sets (order-independent comparison).

    Example:
        >>> allowlist = CompositionAllowlist([
        ...     ["adapter-bedrock", "adapter-agentcore"],
        ...     ["adapter-azure"],
        ... ])
        >>> allowlist.check(["adapter-bedrock", "adapter-agentcore"])
        {'allowed': True, 'reason_code': None}
        >>> allowlist.check(["adapter-bedrock", "adapter-azure"])
        {'allowed': False, 'reason_code': 'UNAPPROVED_ADAPTER_COMPOSITION'}
    """

    def __init__(self, approved_combinations: List[List[str]]) -> None:
        """Initialize with approved adapter combinations.

        Args:
            approved_combinations: List of approved adapter sets.
                Each set is a list of adapter names approved to be used together.
        """
        # Normalize: sort each set for order-independent comparison
        self._approved_sets: List[List[str]] = [
            sorted(combo) for combo in approved_combinations
        ]

    def check(self, adapters: List[str]) -> Dict[str, object]:
        """Check whether a given adapter composition is in the allowlist.

        Order-independent: ["a", "b"] matches ["b", "a"].

        Args:
            adapters: List of adapter names being composed.

        Returns:
            A dict with keys:
            - "allowed" (bool): Whether the composition is allowed.
            - "reason_code" (str | None): "UNAPPROVED_ADAPTER_COMPOSITION" if
              not allowed, None if allowed.
        """
        sorted_adapters = sorted(adapters)

        for approved in self._approved_sets:
            if approved == sorted_adapters:
                return {"allowed": True, "reason_code": None}

        return {"allowed": False, "reason_code": REASON_CODE_COMPOSITION}


def check_composition(
    adapters: List[str],
    approved_combinations: Optional[List[List[str]]] = None,
) -> Dict[str, object]:
    """Standalone function to check adapter composition against an allowlist.

    Args:
        adapters: List of adapter names being composed.
        approved_combinations: List of approved adapter sets.

    Returns:
        A dict with keys:
        - "allowed" (bool): Whether the composition is allowed.
        - "reason_code" (str | None): "UNAPPROVED_ADAPTER_COMPOSITION" if
          not allowed, None if allowed.
    """
    if approved_combinations is None:
        approved_combinations = []
    allowlist = CompositionAllowlist(approved_combinations)
    return allowlist.check(adapters)
