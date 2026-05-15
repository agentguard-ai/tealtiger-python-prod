"""TealGuard v2 — Detection Modules (Python SDK).

Ports the TypeScript TealGuard v2 detection modules to Python with identical behavior:
- Encoded output detection (base64, hex, ROT13)
- Control character sanitization (ANSI, OSC52, BEL, non-printable)
- Markdown exfiltration detection (images, iframes, data-bearing URLs)

Module: guardrails/detectors_v13
Requirements: 12.1, 12.2
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TypedDict


__all__ = [
    "detect_encoded_output",
    "sanitize_control_chars",
    "detect_markdown_exfiltration",
]


# ── Encoded Output Detection ─────────────────────────────────────


class EncodedOutputResult(TypedDict):
    """Result of encoded output detection."""

    detected: bool
    encoding_type: str
    reason_code: str


def _build_base64_regex(threshold: int) -> re.Pattern[str]:
    """Build regex matching base64-encoded content of at least `threshold` chars."""
    return re.compile(rf"[A-Za-z0-9+/]{{{threshold},}}={{0,2}}")


def _build_hex_regex(threshold: int) -> re.Pattern[str]:
    """Build regex matching hex-encoded content of at least `threshold` chars."""
    return re.compile(rf"(?:0x)?[0-9a-fA-F]{{{threshold},}}")


def _rot13(input_str: str) -> str:
    """Apply ROT13 transformation to a string."""
    result = []
    for char in input_str:
        if "a" <= char <= "z":
            result.append(chr(((ord(char) - 97 + 13) % 26) + 97))
        elif "A" <= char <= "Z":
            result.append(chr(((ord(char) - 65 + 13) % 26) + 65))
        else:
            result.append(char)
    return "".join(result)


def _looks_like_readable_text(text: str) -> bool:
    """Check if a string looks like readable English text.

    Uses heuristics based on common English letter frequency and word patterns.
    """
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count < len(text) * 0.7:
        return False

    # Check for common English words (case-insensitive)
    common_words = re.compile(
        r"\b(the|and|for|are|but|not|you|all|can|had|her|was|one|our|out|has|his|how|its|may|new|now|old|see|way|who|did|get|let|say|she|too|use)\b",
        re.IGNORECASE,
    )
    if common_words.search(text):
        return True

    # Check for vowel/consonant ratio typical of English
    vowels = sum(1 for c in text if c in "aeiouAEIOU")
    if alpha_count == 0:
        return False
    ratio = vowels / alpha_count
    # English typically has 25-55% vowels
    return 0.25 <= ratio <= 0.55


def _detect_rot13(content: str, threshold: int) -> bool:
    """Detect ROT13-encoded content in the input string.

    Extracts alphabetic sequences of at least `threshold` length and checks
    if applying ROT13 produces readable text.
    """
    alpha_sequence_regex = re.compile(rf"[a-zA-Z][a-zA-Z ]{{{threshold - 1},}}")
    matches = alpha_sequence_regex.findall(content)

    if not matches:
        return False

    for match in matches:
        decoded = _rot13(match)
        # If the decoded version looks like readable text but the original doesn't,
        # it's likely ROT13-encoded
        if _looks_like_readable_text(decoded) and not _looks_like_readable_text(match):
            return True

    return False


def detect_encoded_output(
    content: str, threshold: int = 50
) -> EncodedOutputResult:
    """Detect encoded content (base64, hex, ROT13) in model output.

    Detection strategies:
    - Base64: Matches continuous base64 character sequences with optional padding
    - Hex: Matches long hexadecimal strings (with optional 0x prefix)
    - ROT13: Heuristic — text that becomes readable English after ROT13 decoding

    Args:
        content: The model output to analyze.
        threshold: Minimum length of encoded content to trigger detection (default: 50).

    Returns:
        EncodedOutputResult indicating detection status and encoding type.
    """
    if not content or len(content) < threshold:
        return {"detected": False, "encoding_type": "none", "reason_code": ""}

    # Check for base64-encoded content
    base64_regex = _build_base64_regex(threshold)
    base64_matches = base64_regex.findall(content)
    if base64_matches:
        # Verify it's likely base64 (not just a long word) by checking for mixed case + digits
        for match in base64_matches:
            has_upper = bool(re.search(r"[A-Z]", match))
            has_lower = bool(re.search(r"[a-z]", match))
            has_digit_or_special = bool(re.search(r"[0-9+/]", match))
            if (has_upper and has_lower and has_digit_or_special) or match.endswith("="):
                return {
                    "detected": True,
                    "encoding_type": "base64",
                    "reason_code": "ENCODED_OUTPUT_DETECTED",
                }

    # Check for hex-encoded content
    hex_regex = _build_hex_regex(threshold)
    hex_matches = hex_regex.findall(content)
    if hex_matches:
        # Verify it's likely hex (has mix of digits and a-f characters)
        for match in hex_matches:
            clean_match = match[2:] if match.startswith("0x") else match
            has_digits = bool(re.search(r"[0-9]", clean_match))
            has_hex_letters = bool(re.search(r"[a-fA-F]", clean_match))
            if has_digits and has_hex_letters:
                return {
                    "detected": True,
                    "encoding_type": "hex",
                    "reason_code": "ENCODED_OUTPUT_DETECTED",
                }

    # Check for ROT13-encoded content
    if _detect_rot13(content, threshold):
        return {
            "detected": True,
            "encoding_type": "rot13",
            "reason_code": "ENCODED_OUTPUT_DETECTED",
        }

    return {"detected": False, "encoding_type": "none", "reason_code": ""}


# ── Control Character Sanitization ───────────────────────────────


class ControlCharSanitizeResult(TypedDict):
    """Result of control character sanitization."""

    sanitized: str
    stripped: bool
    reason_code: str


# Regex matching ANSI escape sequences: ESC [ <params> <command>
_ANSI_ESCAPE_REGEX = re.compile(r"\x1B\[[0-9;]*[A-Za-z]")

# Regex matching OSC sequences: ESC ] <number> ; <data> (ST | BEL)
_OSC_SEQUENCE_REGEX = re.compile(r"\x1B\][0-9]*;[^\x07\x1B]*(?:\x07|\x1B\\|\x9C)")

# Regex matching BEL characters (U+0007)
_BEL_REGEX = re.compile(r"\x07")

# Regex matching non-printable control characters (U+0000–U+001F)
# EXCEPT for allowed whitespace: \n (U+000A), \r (U+000D), \t (U+0009)
_NON_PRINTABLE_REGEX = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# Regex matching C1 control characters (U+0080–U+009F)
_C1_CONTROL_REGEX = re.compile(r"[\x80-\x9F]")


def sanitize_control_chars(content: str) -> ControlCharSanitizeResult:
    """Strip dangerous control characters from model output.

    Removes:
    - ANSI escape sequences (e.g., color codes, cursor movement)
    - OSC 52 sequences (clipboard manipulation)
    - BEL characters (\\x07)
    - Non-printable control characters (U+0000–U+001F except \\n, \\r, \\t)
    - C1 control characters (U+0080–U+009F)

    Args:
        content: The model output to sanitize.

    Returns:
        ControlCharSanitizeResult with sanitized string and metadata.
    """
    if not content:
        return {"sanitized": content, "stripped": False, "reason_code": ""}

    sanitized = content

    # Strip OSC sequences first (they may contain BEL as terminator)
    sanitized = _OSC_SEQUENCE_REGEX.sub("", sanitized)

    # Strip ANSI escape sequences
    sanitized = _ANSI_ESCAPE_REGEX.sub("", sanitized)

    # Strip BEL characters
    sanitized = _BEL_REGEX.sub("", sanitized)

    # Strip non-printable control characters (except \n, \r, \t)
    sanitized = _NON_PRINTABLE_REGEX.sub("", sanitized)

    # Strip C1 control characters
    sanitized = _C1_CONTROL_REGEX.sub("", sanitized)

    stripped = sanitized != content

    return {
        "sanitized": sanitized,
        "stripped": stripped,
        "reason_code": "CONTROL_CHARS_STRIPPED" if stripped else "",
    }


# ── Markdown Exfiltration Detection ──────────────────────────────


class MarkdownExfilResult(TypedDict):
    """Result of markdown exfiltration detection."""

    detected: bool
    urls: List[str]
    reason_code: str


# Regex matching markdown image syntax: ![alt text](url)
_MARKDOWN_IMAGE_REGEX = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

# Regex matching markdown links: [text](url)
_MARKDOWN_LINK_REGEX = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Regex matching iframe HTML tags
_IFRAME_REGEX = re.compile(r'<iframe[^>]*src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)

# Regex matching HTML img tags (link-preview triggers)
_HTML_IMG_REGEX = re.compile(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)


def _extract_domain(url: str) -> Optional[str]:
    """Extract the domain from a URL string."""
    match = re.match(r"^(?:https?://)?([^/:?#]+)", url)
    return match.group(1).lower() if match else None


def _is_domain_allowed(domain: str, allowlist: List[str]) -> bool:
    """Check if a domain is in the allowlist.

    Supports exact match and subdomain matching (e.g., 'example.com' allows 'sub.example.com').
    """
    normalized_domain = domain.lower()
    for allowed in allowlist:
        normalized_allowed = allowed.lower()
        if normalized_domain == normalized_allowed:
            return True
        if normalized_domain.endswith("." + normalized_allowed):
            return True
    return False


def _has_data_bearing_params(url: str) -> bool:
    """Check if a URL has data-bearing query parameters.

    Looks for:
    - Base64-looking values (long alphanumeric + /+ with optional padding)
    - Long URL-encoded content
    - Hex-encoded values in parameters
    - Suspiciously long parameter values
    """
    # Try to parse the URL
    query_start = url.find("?")
    if query_start == -1:
        return False

    query_string = url[query_start + 1:]
    # Remove fragment
    fragment_start = query_string.find("#")
    if fragment_start != -1:
        query_string = query_string[:fragment_start]

    params = query_string.split("&")

    for param in params:
        eq_index = param.find("=")
        if eq_index == -1:
            continue
        value = param[eq_index + 1:]
        if not value:
            continue

        # Check for base64-looking values (long alphanumeric with +/= chars)
        if re.match(r"^[A-Za-z0-9+/]{20,}={0,2}$", value):
            return True

        # Check for long URL-encoded content
        if len(value) > 30 and re.search(r"%[0-9A-Fa-f]{2}", value):
            return True

        # Check for hex-encoded values
        if re.match(r"^[0-9a-fA-F]{20,}$", value):
            return True

        # Check for suspiciously long parameter values
        if len(value) > 50:
            return True

    return False


def detect_markdown_exfiltration(
    content: str, domain_allowlist: Optional[List[str]] = None
) -> MarkdownExfilResult:
    """Detect markdown-based data exfiltration attempts in model output.

    Checks for:
    1. Markdown image URLs (![...](url)) pointing to non-allowlisted domains
    2. Iframe references (<iframe src="...">)
    3. HTML img tags (link-preview triggers)
    4. URLs with data-bearing query parameters

    Args:
        content: The model output to analyze.
        domain_allowlist: List of allowed domains that are not flagged.

    Returns:
        MarkdownExfilResult indicating detection status and flagged URLs.
    """
    if not content:
        return {"detected": False, "urls": [], "reason_code": ""}

    if domain_allowlist is None:
        domain_allowlist = []

    flagged_urls: set[str] = set()

    # 1. Check markdown images
    for match in _MARKDOWN_IMAGE_REGEX.finditer(content):
        url = match.group(1).strip()
        domain = _extract_domain(url)

        if domain and not _is_domain_allowed(domain, domain_allowlist):
            flagged_urls.add(url)

        # Check for data-bearing params regardless of domain
        if _has_data_bearing_params(url):
            flagged_urls.add(url)

    # 2. Check iframes
    for match in _IFRAME_REGEX.finditer(content):
        url = match.group(1).strip()
        domain = _extract_domain(url)

        if domain and not _is_domain_allowed(domain, domain_allowlist):
            flagged_urls.add(url)

        if _has_data_bearing_params(url):
            flagged_urls.add(url)

    # 3. Check HTML img tags (link-preview triggers)
    for match in _HTML_IMG_REGEX.finditer(content):
        url = match.group(1).strip()
        domain = _extract_domain(url)

        if domain and not _is_domain_allowed(domain, domain_allowlist):
            flagged_urls.add(url)

        if _has_data_bearing_params(url):
            flagged_urls.add(url)

    # 4. Check markdown links for data-bearing params
    for match in _MARKDOWN_LINK_REGEX.finditer(content):
        url = match.group(1).strip()
        # Only flag links with data-bearing params (not all external links)
        if _has_data_bearing_params(url):
            flagged_urls.add(url)

    urls = list(flagged_urls)
    detected = len(urls) > 0

    return {
        "detected": detected,
        "urls": urls,
        "reason_code": "MARKDOWN_EXFILTRATION_DETECTED" if detected else "",
    }
