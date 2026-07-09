"""
ObservePIIScanner — REPORT_ONLY mode PII detection for observe().

Scans request/response payloads for PII patterns (email, phone, SSN,
credit card). Reports findings but NEVER blocks, delays, or modifies
traffic.

On any internal error: fails silently, returns None. The scan is
best-effort and must never interfere with the request lifecycle.

Requirements: 8.6, 5.1–5.8
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from tealtiger.observe.types import PIIDetectionSummary

# Pre-compiled regex patterns for each PII type (Req 5.1)
_PII_PATTERNS: Dict[str, re.Pattern[str]] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),
    "phone": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
}


def _extract_text(payload: Any) -> Optional[str]:
    """
    Extract text content from a payload for scanning.

    Handles:
    - str: used directly
    - dict with 'messages' key: extracts message contents
    - other: json.dumps fallback

    Returns None if no meaningful text can be extracted.
    """
    try:
        if isinstance(payload, str):
            return payload if payload else None

        if payload is None:
            return None

        # Handle dict with 'messages' key (common LLM request format)
        if isinstance(payload, dict) and "messages" in payload:
            messages = payload["messages"]
            if isinstance(messages, list):
                parts: List[str] = []
                for msg in messages:
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str):
                            parts.append(content)
                return " ".join(parts) if parts else None

        # Fallback: serialize to JSON
        return json.dumps(payload)
    except Exception:
        return None


class ObservePIIScanner:
    """
    Synchronous PII scanner operating in REPORT_ONLY mode.

    Scans payloads for PII patterns (email, phone, SSN, credit card) and
    returns a summary of detections. Never blocks, never raises exceptions,
    and never exposes detected PII values in output.

    Requirements:
        5.1 — Detects email, phone, SSN, credit card
        5.2 — Scans both request and response payloads
        5.3 — Output contains only types and counts, never PII values
        5.4 — Never blocks or delays requests/responses
        5.6 — Always REPORT_ONLY mode, no blocking or redaction
        5.7 — Never raises exceptions; returns None on any internal error
        5.8 — Uses pre-compiled regex patterns (no external guardrail dependency)
    """

    def scan(
        self, payload: Any, phase: str
    ) -> Optional[PIIDetectionSummary]:
        """
        Scan a payload for PII patterns.

        Args:
            payload: The request or response payload to scan.
            phase: Either 'request' or 'response'.

        Returns:
            PIIDetectionSummary with count and types if PII found,
            None if no PII detected or on any internal error.

        Note:
            This method NEVER raises an exception. All errors are
            swallowed silently per Req 5.7.
        """
        try:
            text = _extract_text(payload)
            if not text:
                return None

            detected_types: List[str] = []
            total_count = 0

            for pii_type, pattern in _PII_PATTERNS.items():
                matches = pattern.findall(text)
                if matches:
                    detected_types.append(pii_type)
                    total_count += len(matches)

            if total_count == 0:
                return None

            # Output never contains detected PII values — only types and counts (Req 5.3)
            return PIIDetectionSummary(
                count=total_count,
                types=detected_types,
                phase=phase,
            )
        except Exception:
            # Fail silently — PII detection is best-effort (Req 5.7)
            return None
