"""PII Detection Guardrail for detecting personally identifiable information."""

import re
from typing import Any, Dict, List, Optional

from tealtiger.guardrails.base import Guardrail, GuardrailResult


class PIIDetectionGuardrail(Guardrail):
    """Detects PII in text: emails, phones, SSNs, credit cards.

    Valid ``detect_types`` values: ``email``, ``phone``, ``ssn``,
    ``credit_card``, ``name``. Default:
    ``['email', 'phone', 'ssn', 'credit_card']``. Unknown values raise
    ``ValueError`` on construction.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize PII detection guardrail.

        Args:
            config: Configuration with detect_types, action, risk_scores.
                Unknown ``detect_types`` values raise ValueError.
        """
        config = config or {}
        super().__init__({
            "name": "PIIDetection",
            "description": "Detects personally identifiable information in text",
            "version": "1.0.0",
            **config
        })

        # Patterns for PII detection
        self.patterns = {
            "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "phone": re.compile(r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
            "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
            "name": re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'),
        }

        # Configure which PII types to detect
        self.detect_types = config.get("detect_types", ["email", "phone", "ssn", "credit_card"])
        self._assert_known_detect_types(self.detect_types)

        # Configure action: block, redact, mask, allow
        self.action = config.get("action", "block")

        # Risk scores per PII type
        self.risk_scores = config.get("risk_scores", {
            "email": 30,
            "phone": 40,
            "ssn": 90,
            "credit_card": 95,
            "name": 20,
        })

    async def evaluate(
        self,
        input_data: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> GuardrailResult:
        """Evaluate input for PII.

        Args:
            input_data: Input to scan for PII
            context: Execution context

        Returns:
            GuardrailResult with detection results
        """
        text = self._extract_text(input_data)
        detections = self._detect_pii(text)

        if not detections:
            return GuardrailResult(
                passed=True,
                action="allow",
                reason="No PII detected",
                metadata={"detections": []},
                risk_score=0,
            )

        # Calculate maximum risk score
        max_risk_score = max(self.risk_scores.get(d["type"], 50) for d in detections)

        # Determine action
        action = self.action
        passed = action in ["allow", "redact", "mask"]

        metadata = {"detections": detections}
        if action == "redact":
            metadata["redacted_text"] = self._redact_pii(text, detections)
        elif action == "mask":
            metadata["masked_text"] = self._mask_pii(text, detections)

        return GuardrailResult(
            passed=passed,
            action=action,
            reason=f"Detected {len(detections)} PII instance(s): {', '.join(d['type'] for d in detections)}",
            metadata=metadata,
            risk_score=max_risk_score,
        )

    def _assert_known_detect_types(self, types: List[str]) -> None:
        """Reject unknown detect_types; patterns map is the source of truth."""
        allowed = list(self.patterns.keys())
        unknown = [t for t in types if t not in self.patterns]
        if not unknown:
            return
        listed = ", ".join(f"'{t}'" for t in unknown)
        plural = "detect_type" if len(unknown) == 1 else "detect_types"
        raise ValueError(
            f"Unknown PII {plural} {listed}. Valid: {', '.join(allowed)}."
        )

    def _extract_text(self, input_data: Any) -> str:
        """Extract text from various input formats."""
        if isinstance(input_data, str):
            return input_data

        if isinstance(input_data, dict):
            if "prompt" in input_data:
                return input_data["prompt"]
            if "messages" in input_data and isinstance(input_data["messages"], list):
                return " ".join(m.get("content", "") for m in input_data["messages"])
            if "text" in input_data:
                return input_data["text"]

        return str(input_data)

    def _detect_pii(self, text: str) -> List[Dict[str, Any]]:
        """Detect PII in text."""
        detections = []

        for pii_type in self.detect_types:
            pattern = self.patterns.get(pii_type)
            if not pattern:
                continue

            for match in pattern.finditer(text):
                detections.append({
                    "type": pii_type,
                    "value": match.group(0),
                    "position": match.start(),
                    "length": len(match.group(0)),
                })

        return detections

    def _redact_pii(self, text: str, detections: List[Dict[str, Any]]) -> str:
        """Redact PII from text."""
        # Sort by position in reverse to maintain indices
        sorted_detections = sorted(detections, key=lambda d: d["position"], reverse=True)

        redacted = text
        for detection in sorted_detections:
            start = detection["position"]
            end = start + detection["length"]
            redacted = redacted[:start] + f"[REDACTED_{detection['type'].upper()}]" + redacted[end:]

        return redacted

    def _mask_pii(self, text: str, detections: List[Dict[str, Any]]) -> str:
        """Mask PII from text."""
        # Sort by position in reverse to maintain indices
        sorted_detections = sorted(detections, key=lambda d: d["position"], reverse=True)

        masked = text
        for detection in sorted_detections:
            start = detection["position"]
            end = start + detection["length"]
            masked = masked[:start] + "*" * detection["length"] + masked[end:]

        return masked
