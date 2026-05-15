"""TealMemory v2 — Detection Modules (Python SDK).

Ports the TypeScript TealMemory v2 detection modules to Python with identical behavior:
- Instruction injection scoring (imperative verbs, conditional triggers, role references, encoded payloads)
- Instruction injection detection (threshold-based)
- Memory exfiltration detection (data-bearing URLs, webhook URLs, markdown images)

Module: memory/detectors
Requirements: 12.1, 12.2
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict


__all__ = [
    "score_instruction_likeness",
    "detect_memory_instruction_injection",
    "detect_memory_exfiltration",
]


# ── Pattern Definitions ──────────────────────────────────────────

IMPERATIVE_VERB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?previous\b", re.IGNORECASE),
    re.compile(r"\byou\s+must\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\b", re.IGNORECASE),
    re.compile(r"\byou\s+will\b", re.IGNORECASE),
    re.compile(r"\bexecute\s+the\b", re.IGNORECASE),
    re.compile(r"\brun\s+the\b", re.IGNORECASE),
    re.compile(r"\bdelete\s+(all|the|this|every)\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(the|all|any)\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(the|all|any|previous)\b", re.IGNORECASE),
    re.compile(r"\bforget\s+(all|the|previous|everything)\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+(follow|obey|listen)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(reveal|disclose|share|mention)\b", re.IGNORECASE),
    re.compile(r"\balways\s+(respond|reply|answer|say)\b", re.IGNORECASE),
    re.compile(r"\brespond\s+(only\s+)?with\b", re.IGNORECASE),
    re.compile(r"\boutput\s+(only|the)\b", re.IGNORECASE),
    re.compile(r"\bprint\s+(the|this|out)\b", re.IGNORECASE),
    re.compile(r"\breturn\s+(the|only|this)\b", re.IGNORECASE),
    re.compile(r"\bsend\s+(the|this|all)\b", re.IGNORECASE),
    re.compile(r"\bwrite\s+(the|this|to)\b", re.IGNORECASE),
]

CONDITIONAL_TRIGGER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bif\s+(asked|prompted|queried)\s+(about|for|to)\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+you\s+(see|receive|encounter|get|are)\b", re.IGNORECASE),
    re.compile(r"\bupon\s+(receiving|seeing|encountering)\b", re.IGNORECASE),
    re.compile(r"\bwhenever\s+(a|the|someone|anyone)\b", re.IGNORECASE),
    re.compile(r"\bin\s+case\s+(of|someone|the|a)\b", re.IGNORECASE),
    re.compile(r"\bif\s+the\s+user\s+(asks|says|types|mentions)\b", re.IGNORECASE),
    re.compile(r"\bafter\s+(receiving|the|this|you)\b", re.IGNORECASE),
    re.compile(r"\bbefore\s+(responding|answering|replying)\b", re.IGNORECASE),
    re.compile(r"\bonce\s+you\s+(receive|see|get|have)\b", re.IGNORECASE),
    re.compile(r"\btrigger\s+(when|if|on)\b", re.IGNORECASE),
]

ROLE_TOOL_REFERENCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bas\s+an?\s+(assistant|ai|bot|agent|model|system)\b", re.IGNORECASE),
    re.compile(r"\byour\s+(role|purpose|function|job|task)\s+is\b", re.IGNORECASE),
    re.compile(r"\buse\s+the\s+(tool|function|api|endpoint)\b", re.IGNORECASE),
    re.compile(r"\bcall\s+the\s+(function|api|tool|method)\b", re.IGNORECASE),
    re.compile(r"\binvoke\s+(the|this)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+(a|an|now|the)\b", re.IGNORECASE),
    re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(a|an|if|though)\b", re.IGNORECASE),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.IGNORECASE),
    re.compile(r"\brole[-\s]?play\b", re.IGNORECASE),
    re.compile(r"\bnew\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\bupdated?\s+instructions?\b", re.IGNORECASE),
]

# Encoded payload detection patterns
_BASE64_PATTERN = re.compile(r"(?:[A-Za-z0-9+/]{4}){5,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
_HEX_PATTERN = re.compile(r"(?:0x)?[0-9a-fA-F]{16,}")

# ── Category Weights ─────────────────────────────────────────────

DEFAULT_WEIGHTS: Dict[str, float] = {
    "imperative_verbs": 0.35,
    "conditional_triggers": 0.25,
    "role_references": 0.25,
    "encoded_payloads": 0.15,
}


# ── Scoring Functions ────────────────────────────────────────────


def _score_category(content: str, patterns: list[re.Pattern[str]]) -> float:
    """Score a content string against a list of patterns.

    Returns:
        Score between 0 and 1 based on match count:
        - 0 matches = 0.0
        - 1 match = 0.5
        - 2 matches = 0.8
        - 3+ matches = 1.0
    """
    match_count = 0
    for pattern in patterns:
        if pattern.search(content):
            match_count += 1

    if match_count == 0:
        return 0.0
    if match_count == 1:
        return 0.5
    if match_count == 2:
        return 0.8
    return 1.0


def _score_encoded_payloads(content: str) -> float:
    """Score content for encoded payload presence.

    Returns:
        Score between 0 and 1 based on suspicious encoded content found.
    """
    base64_matches = _BASE64_PATTERN.findall(content)
    hex_matches = _HEX_PATTERN.findall(content)

    # Filter to suspicious matches
    suspicious_base64 = [m for m in base64_matches if len(m) >= 20]
    suspicious_hex = [m for m in hex_matches if len(m) >= 16]

    total_suspicious = len(suspicious_base64) + len(suspicious_hex)
    if total_suspicious == 0:
        return 0.0
    if total_suspicious == 1:
        return 0.5
    return 1.0


# ── Public API ───────────────────────────────────────────────────


class InstructionLikenessResult(TypedDict):
    """Result of instruction likeness scoring."""

    score: float
    categories: Dict[str, float]


class InstructionInjectionDetectionResult(TypedDict):
    """Result of instruction injection detection."""

    detected: bool
    score: float
    reason_code: str


class ExfiltrationDetectionResult(TypedDict):
    """Result of memory exfiltration detection."""

    detected: bool
    findings: List[str]
    reason_code: str


def score_instruction_likeness(content: str) -> InstructionLikenessResult:
    """Score a content string for instruction-likeness.

    Evaluates content against four categories:
    - Imperative verbs (e.g., "ignore previous", "you must", "execute")
    - Conditional triggers (e.g., "if asked about", "when you see")
    - Role/tool references (e.g., "as an assistant", "use the tool")
    - Encoded payloads (base64, hex within text)

    Returns a total score (0-1) and per-category breakdown.

    Args:
        content: The content string to score.

    Returns:
        InstructionLikenessResult with total score and category breakdown.
    """
    categories: Dict[str, float] = {
        "imperative_verbs": _score_category(content, IMPERATIVE_VERB_PATTERNS),
        "conditional_triggers": _score_category(content, CONDITIONAL_TRIGGER_PATTERNS),
        "role_references": _score_category(content, ROLE_TOOL_REFERENCE_PATTERNS),
        "encoded_payloads": _score_encoded_payloads(content),
    }

    # Weighted sum of category scores
    weighted_sum = 0.0
    for category, weight in DEFAULT_WEIGHTS.items():
        weighted_sum += categories.get(category, 0.0) * weight

    # Multi-category boost: when 3+ categories fire, apply a multiplier
    active_categories = sum(1 for v in categories.values() if v > 0)
    if active_categories >= 3:
        multi_category_boost = 1.4
    elif active_categories >= 2:
        multi_category_boost = 1.2
    else:
        multi_category_boost = 1.0

    score = min(1.0, weighted_sum * multi_category_boost)

    return {"score": score, "categories": categories}


def detect_memory_instruction_injection(
    content: str, threshold: float = 0.6
) -> InstructionInjectionDetectionResult:
    """Detect instruction injection in memory content.

    Scores the content for instruction-likeness and returns whether injection
    was detected based on the configured threshold.

    Args:
        content: The memory content to analyze.
        threshold: Score threshold above which injection is detected (default: 0.6).

    Returns:
        InstructionInjectionDetectionResult with detection status and score.
    """
    result = score_instruction_likeness(content)
    score = result["score"]
    detected = score >= threshold

    return {
        "detected": detected,
        "score": score,
        "reason_code": "MEMORY_INSTRUCTION_INJECTION" if detected else "",
    }


# ── Memory Exfiltration Detection ────────────────────────────────

# Matches URLs with query parameters that contain long base64-like or encoded values
_URL_WITH_DATA_PARAMS_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+\?[^\s\"'<>]*[=][A-Za-z0-9+/=%]{20,}", re.IGNORECASE
)

# Matches markdown image syntax: ![alt](url)
_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

# Matches webhook-formatted URLs (paths containing /webhook/, /hook/, /callback/)
_WEBHOOK_URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]*/(?:webhook|hook|callback)s?/[^\s\"'<>]*", re.IGNORECASE
)


def _extract_domain(url: str) -> Optional[str]:
    """Extract the domain from a URL string."""
    match = re.match(r"https?://([^/:?\s\"'<>]+)", url, re.IGNORECASE)
    return match.group(1).lower() if match else None


def _is_domain_allowlisted(domain: str, allowlist: List[str]) -> bool:
    """Check if a domain is in the allowlist.

    Supports exact match and wildcard subdomain matching (e.g., "*.example.com").
    """
    lower_domain = domain.lower()
    for allowed in allowlist:
        lower_allowed = allowed.lower()
        if lower_domain == lower_allowed:
            return True
        # Wildcard subdomain: *.example.com matches sub.example.com
        if lower_allowed.startswith("*."):
            base_domain = lower_allowed[2:]
            if lower_domain == base_domain or lower_domain.endswith("." + base_domain):
                return True
    return False


def _has_data_bearing_params(url: str) -> bool:
    """Check if a URL has data-bearing query parameters.

    A data-bearing param has a value that looks like base64 or encoded data (20+ chars).
    """
    query_start = url.find("?")
    if query_start == -1:
        return False

    query_string = url[query_start + 1:]
    params = query_string.split("&")

    for param in params:
        eq_index = param.find("=")
        if eq_index == -1:
            continue
        value = param[eq_index + 1:]
        # Check if value looks like encoded data (20+ chars of base64/hex-like content)
        if len(value) >= 20 and re.match(r"^[A-Za-z0-9+/=%_-]+$", value):
            return True

    return False


def detect_memory_exfiltration(
    content: str, domain_allowlist: Optional[List[str]] = None
) -> ExfiltrationDetectionResult:
    """Detect potential data exfiltration patterns in memory content.

    Checks for:
    1. URLs with data-bearing query parameters (long base64-looking values)
    2. Markdown image links pointing to non-allowlisted domains
    3. Webhook-formatted strings (URLs with /webhook/, /hook/, /callback/ paths)

    Args:
        content: The memory content to analyze.
        domain_allowlist: List of allowed domains (supports wildcards like "*.example.com").

    Returns:
        ExfiltrationDetectionResult with detection status and findings.
    """
    if domain_allowlist is None:
        domain_allowlist = []

    findings: List[str] = []

    # 1. Check for URLs with data-bearing query parameters
    data_param_urls = _URL_WITH_DATA_PARAMS_PATTERN.findall(content)
    for url in data_param_urls:
        domain = _extract_domain(url)
        if domain and not _is_domain_allowlisted(domain, domain_allowlist):
            if _has_data_bearing_params(url):
                findings.append(
                    f"URL with data-bearing params to non-allowlisted domain: {domain}"
                )

    # 2. Check for markdown image links to non-allowlisted domains
    for match in _MARKDOWN_IMAGE_PATTERN.finditer(content):
        image_url = match.group(1)
        domain = _extract_domain(image_url)
        if domain and not _is_domain_allowlisted(domain, domain_allowlist):
            findings.append(f"Markdown image to non-allowlisted domain: {domain}")

    # 3. Check for webhook-formatted URLs to non-allowlisted domains
    webhook_urls = _WEBHOOK_URL_PATTERN.findall(content)
    for url in webhook_urls:
        domain = _extract_domain(url)
        if domain and not _is_domain_allowlisted(domain, domain_allowlist):
            findings.append(f"Webhook URL to non-allowlisted domain: {domain}")

    detected = len(findings) > 0

    return {
        "detected": detected,
        "findings": findings,
        "reason_code": "MEMORY_EXFILTRATION_RISK" if detected else "",
    }
