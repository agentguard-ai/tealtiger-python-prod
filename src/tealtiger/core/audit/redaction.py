"""
TealAudit - Content Redaction

Implements security-by-default content redaction for audit logging.
Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.4)
"""

import hashlib
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from .types import SafeContent


class RedactionLevel(str, Enum):
    """
    Redaction level enumeration
    Defines strategies for removing sensitive content from audit logs
    """

    NONE = "NONE"  # No redaction - includes raw content (DANGEROUS: debug mode only)
    HASH = "HASH"  # Hash content using SHA-256 (default, secure)
    SIZE_ONLY = "SIZE_ONLY"  # Show size/length only
    CATEGORY_ONLY = "CATEGORY_ONLY"  # Show category/type only
    FULL = "FULL"  # Complete redaction - no metadata


ContentCategory = Literal[
    "prompt", "response", "tool_params", "tool_result", "code", "data", "unknown"
]


class SafeContentWithRaw(BaseModel):
    """
    Safe content with raw data (debug mode only)
    """

    hash: Optional[str] = Field(None, description="SHA-256 hash of the content")
    size: Optional[int] = Field(None, description="Size of the content in bytes")
    category: Optional[str] = Field(None, description="Content category")
    raw: Optional[str] = Field(
        None, description="Raw content (only present when RedactionLevel.NONE)"
    )
    warning: Optional[str] = Field(
        None, description="Warning message (present when raw content is included)"
    )
    redacted: Optional[bool] = Field(
        None, description="Redacted flag (present when RedactionLevel.FULL)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (PII detection, errors, etc.)"
    )


class PIIDetection(BaseModel):
    """PII detection result"""

    type: str = Field(..., description="Type of PII detected")
    value: str = Field(..., description="Detected value")
    position: int = Field(..., description="Position in text")
    length: int = Field(..., description="Length of detected value")


# PII pattern definitions
# Pre-compiled regex patterns for detecting common PII types
PII_PATTERNS = {
    # Email addresses
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # Phone numbers (US and international formats)
    "phone": re.compile(
        r"(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    # Social Security Numbers (SSN)
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Credit card numbers (with spaces or dashes)
    "creditCard": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    # IP addresses (IPv4)
    "ipAddress": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # API keys and tokens (common patterns)
    "apiKey": re.compile(r"\b[A-Za-z0-9_-]{32,}\b"),
}


def compute_sha256_hash(content: str) -> str:
    """
    Computes SHA-256 hash of content

    Uses Python hashlib for secure, collision-resistant hashing.
    Hash is prefixed with 'sha256:' for clarity.

    Args:
        content: Content to hash

    Returns:
        SHA-256 hash with 'sha256:' prefix

    Example:
        >>> hash_val = compute_sha256_hash('hello world')
        >>> # 'sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(content.encode("utf-8"))
    return f"sha256:{hash_obj.hexdigest()}"


def categorize_content(content: str) -> ContentCategory:
    """
    Categorizes content based on heuristics

    Attempts to determine content type for CATEGORY_ONLY redaction level.
    Uses simple pattern matching - not intended for security decisions.

    Args:
        content: Content to categorize

    Returns:
        Content category

    Example:
        >>> categorize_content('SELECT * FROM users')
        'code'
        >>> categorize_content('{"key": "value"}')
        'data'
        >>> categorize_content('Hello, how are you?')
        'prompt'
    """
    if not content or len(content) == 0:
        return "unknown"

    # Trim for analysis
    trimmed = content.strip()

    # Check for empty after trim
    if len(trimmed) == 0:
        return "unknown"

    # Check for tool-related content (before JSON check)
    if "tool:" in trimmed or "function_call" in trimmed:
        return "tool_params"

    # Check for code patterns
    code_patterns = [
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "function ",
        "const ",
        "let ",
        "var ",
        "def ",
        "class ",
    ]
    if any(trimmed.startswith(pattern) or pattern in trimmed for pattern in code_patterns):
        return "code"

    # Check for structured data (JSON, XML)
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (
        trimmed.startswith("[") and trimmed.endswith("]")
    ) or (trimmed.startswith("<") and trimmed.endswith(">")):
        return "data"

    # Default to prompt for natural language
    return "prompt"


def redact_content(
    content: str,
    redaction_level: RedactionLevel,
    category: Optional[ContentCategory] = None,
) -> SafeContentWithRaw:
    """
    Redacts content according to the specified redaction level

    This function implements the core redaction algorithm with security-by-default.
    Raw content is NEVER included unless RedactionLevel.NONE is explicitly used.

    Performance target: < 5ms for 10KB content (Requirement 10.4)

    Args:
        content: Content to redact
        redaction_level: Redaction strategy to apply
        category: Optional content category for CATEGORY_ONLY level

    Returns:
        SafeContentWithRaw object with redacted metadata

    Example:
        >>> # Hash redaction (default, secure)
        >>> safe = redact_content('sensitive data', RedactionLevel.HASH)
        >>> # { hash: 'sha256:abc123...', size: 14 }

        >>> # Size only
        >>> safe = redact_content('sensitive data', RedactionLevel.SIZE_ONLY)
        >>> # { size: 14 }

        >>> # Category only
        >>> safe = redact_content('SELECT * FROM users', RedactionLevel.CATEGORY_ONLY, 'code')
        >>> # { category: 'code' }

        >>> # Full redaction
        >>> safe = redact_content('sensitive data', RedactionLevel.FULL)
        >>> # { redacted: True }

        >>> # Debug mode (DANGEROUS)
        >>> safe = redact_content('sensitive data', RedactionLevel.NONE)
        >>> # { raw: 'sensitive data', warning: 'DEBUG_MODE_ENABLED' }
    """
    # Handle null/undefined content
    if content is None:
        content = ""

    # Apply redaction based on level
    if redaction_level == RedactionLevel.NONE:
        # DANGEROUS: Only for debug mode
        # Raw content is included with explicit warning
        result = SafeContentWithRaw(
            raw=content,
            warning="DEBUG_MODE_ENABLED",
            size=len(content),
        )
        if category:
            result.category = category
        return result

    elif redaction_level == RedactionLevel.HASH:
        # Default secure mode: SHA-256 hash + size
        # Provides content verification without exposing raw data
        result = SafeContentWithRaw(
            hash=compute_sha256_hash(content),
            size=len(content),
        )
        if category:
            result.category = category
        return result

    elif redaction_level == RedactionLevel.SIZE_ONLY:
        # Minimal metadata: size only
        return SafeContentWithRaw(size=len(content))

    elif redaction_level == RedactionLevel.CATEGORY_ONLY:
        # Minimal metadata: category only
        return SafeContentWithRaw(
            category=category if category else categorize_content(content)
        )

    elif redaction_level == RedactionLevel.FULL:
        # Complete redaction: no metadata
        return SafeContentWithRaw(redacted=True)

    else:
        # Fallback to FULL redaction for unknown levels (safe default)
        return SafeContentWithRaw(redacted=True)


def is_valid_redaction_level(level: Any) -> bool:
    """
    Validates that a RedactionLevel value is valid

    Args:
        level: The redaction level to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        RedactionLevel(level)
        return True
    except (ValueError, TypeError):
        return False


def get_default_redaction_level() -> RedactionLevel:
    """
    Gets the default redaction level (HASH)

    This is the security-by-default redaction level used in production.

    Returns:
        Default RedactionLevel (HASH)
    """
    return RedactionLevel.HASH


def detect_pii_patterns(content: str) -> List[PIIDetection]:
    """
    Detects PII patterns in content

    This function scans content for common PII patterns including:
    - Email addresses
    - Phone numbers
    - Social Security Numbers (SSN)
    - Credit card numbers
    - IP addresses
    - API keys and tokens

    Performance: Optimized with pre-compiled regex patterns

    Args:
        content: Content to scan for PII

    Returns:
        List of detected PII instances

    Example:
        >>> detections = detect_pii_patterns('Email: test@example.com, SSN: 123-45-6789')
        >>> # [
        >>> #   { type: 'email', value: 'test@example.com', position: 7, length: 16 },
        >>> #   { type: 'ssn', value: '123-45-6789', position: 30, length: 11 }
        >>> # ]
    """
    # Handle null/undefined/empty content
    if not content or not isinstance(content, str) or len(content) == 0:
        return []

    detections: List[PIIDetection] = []

    # Scan for each PII pattern type
    for pii_type, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(content):
            detections.append(
                PIIDetection(
                    type=pii_type,
                    value=match.group(0),
                    position=match.start(),
                    length=len(match.group(0)),
                )
            )

    return detections


def redact_pii_from_content(content: str, detections: List[PIIDetection]) -> str:
    """
    Redacts PII patterns from content

    Replaces detected PII with redaction markers (e.g., [REDACTED_EMAIL]).
    Processes detections in reverse order to maintain string indices.

    Args:
        content: Content to redact
        detections: PII detections to redact

    Returns:
        Content with PII redacted

    Example:
        >>> content = 'Email: test@example.com, SSN: 123-45-6789'
        >>> detections = detect_pii_patterns(content)
        >>> redacted = redact_pii_from_content(content, detections)
        >>> # 'Email: [REDACTED_EMAIL], SSN: [REDACTED_SSN]'
    """
    # Handle null/undefined/empty content
    if not content or not isinstance(content, str):
        return ""

    # No detections, return original content
    if not detections or len(detections) == 0:
        return content

    redacted = content

    # Sort detections by position in reverse order to maintain indices
    sorted_detections = sorted(detections, key=lambda d: d.position, reverse=True)

    # Replace each detection with redaction marker
    for detection in sorted_detections:
        before = redacted[: detection.position]
        after = redacted[detection.position + detection.length :]
        marker = f"[REDACTED_{detection.type.upper()}]"
        redacted = before + marker + after

    return redacted


def redact_content_with_pii(
    content: str,
    redaction_level: RedactionLevel,
    category: Optional[ContentCategory] = None,
    detect_pii: bool = True,
) -> SafeContentWithRaw:
    """
    Redacts content with PII detection enabled

    This is the main entry point for PII-aware redaction.
    It combines PII detection with the standard redaction logic.

    Process:
    1. Detect PII patterns in content
    2. If PII detected, redact PII first
    3. Apply standard redaction level to the redacted content
    4. If PII detection fails, fall back to FULL redaction (Requirement 13.3)

    Security guarantee: Never logs raw PII in audit events (Requirement 11.2)

    Args:
        content: Content to redact
        redaction_level: Redaction strategy to apply
        category: Optional content category
        detect_pii: Enable PII detection (default: True)

    Returns:
        SafeContentWithRaw object with PII-aware redaction

    Example:
        >>> # With PII detection (default)
        >>> safe = redact_content_with_pii('Email: test@example.com', RedactionLevel.HASH)
        >>> # Content is first PII-redacted, then hashed

        >>> # Without PII detection
        >>> safe = redact_content_with_pii('Hello world', RedactionLevel.HASH, detect_pii=False)
        >>> # Standard redaction without PII detection
    """
    # Handle null/undefined content
    if content is None:
        content = ""

    # If PII detection is disabled, use standard redaction
    if not detect_pii:
        return redact_content(content, redaction_level, category)

    try:
        # Detect PII patterns
        detections = detect_pii_patterns(content)

        # If PII detected, redact it first
        processed_content = content
        if len(detections) > 0:
            processed_content = redact_pii_from_content(content, detections)

        # Apply standard redaction to the PII-redacted content
        result = redact_content(processed_content, redaction_level, category)

        # Add PII detection metadata
        if len(detections) > 0:
            if not result.metadata:
                result.metadata = {}
            result.metadata["pii_detected"] = True
            result.metadata["pii_count"] = len(detections)
            result.metadata["pii_types"] = list(set(d.type for d in detections))

        return result

    except Exception as error:
        # Requirement 13.3: Fall back to FULL redaction if PII detection fails
        print(f"PII detection failed, falling back to FULL redaction: {error}")
        return SafeContentWithRaw(
            redacted=True,
            metadata={
                "pii_detection_failed": True,
                "error": str(error),
            },
        )
