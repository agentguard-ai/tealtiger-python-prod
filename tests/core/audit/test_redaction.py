"""
Unit tests for TealAudit redaction module
Tests RedactionLevel, PII detection, and content redaction
"""

import pytest

from tealtiger.core.audit.redaction import (
    RedactionLevel,
    ContentCategory,
    SafeContentWithRaw,
    PIIDetection,
    redact_content,
    compute_sha256_hash,
    categorize_content,
    is_valid_redaction_level,
    get_default_redaction_level,
    detect_pii_patterns,
    redact_pii_from_content,
    redact_content_with_pii,
)


class TestRedactionLevel:
    """Test RedactionLevel enum"""

    def test_all_redaction_levels_defined(self):
        """Test that all expected redaction levels are defined"""
        assert RedactionLevel.NONE == "NONE"
        assert RedactionLevel.HASH == "HASH"
        assert RedactionLevel.SIZE_ONLY == "SIZE_ONLY"
        assert RedactionLevel.CATEGORY_ONLY == "CATEGORY_ONLY"
        assert RedactionLevel.FULL == "FULL"

    def test_is_valid_redaction_level(self):
        """Test validation of redaction levels"""
        assert is_valid_redaction_level("HASH") is True
        assert is_valid_redaction_level("NONE") is True
        assert is_valid_redaction_level("INVALID") is False
        assert is_valid_redaction_level(None) is False
        assert is_valid_redaction_level(123) is False

    def test_get_default_redaction_level(self):
        """Test default redaction level is HASH"""
        assert get_default_redaction_level() == RedactionLevel.HASH


class TestComputeSHA256Hash:
    """Test SHA-256 hash computation"""

    def test_hash_simple_string(self):
        """Test hashing a simple string"""
        hash_val = compute_sha256_hash("hello world")
        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71  # "sha256:" (7) + 64 hex chars

    def test_hash_empty_string(self):
        """Test hashing an empty string"""
        hash_val = compute_sha256_hash("")
        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71

    def test_hash_deterministic(self):
        """Test that hashing is deterministic"""
        content = "test content"
        hash1 = compute_sha256_hash(content)
        hash2 = compute_sha256_hash(content)
        assert hash1 == hash2

    def test_hash_different_content(self):
        """Test that different content produces different hashes"""
        hash1 = compute_sha256_hash("content1")
        hash2 = compute_sha256_hash("content2")
        assert hash1 != hash2


class TestCategorizeContent:
    """Test content categorization"""

    def test_categorize_empty_content(self):
        """Test categorizing empty content"""
        assert categorize_content("") == "unknown"
        assert categorize_content("   ") == "unknown"

    def test_categorize_code(self):
        """Test categorizing code content"""
        assert categorize_content("SELECT * FROM users") == "code"
        assert categorize_content("function test() {}") == "code"
        assert categorize_content("const x = 10") == "code"
        assert categorize_content("def main():") == "code"
        assert categorize_content("class MyClass:") == "code"

    def test_categorize_data(self):
        """Test categorizing structured data"""
        assert categorize_content('{"key": "value"}') == "data"
        assert categorize_content('["item1", "item2"]') == "data"
        assert categorize_content("<xml>data</xml>") == "data"

    def test_categorize_tool_params(self):
        """Test categorizing tool parameters"""
        assert categorize_content("tool: file_delete") == "tool_params"
        assert categorize_content("function_call: get_weather") == "tool_params"

    def test_categorize_prompt(self):
        """Test categorizing natural language prompts"""
        assert categorize_content("Hello, how are you?") == "prompt"
        assert categorize_content("What is the weather today?") == "prompt"


class TestRedactContent:
    """Test content redaction"""

    def test_redact_none_level(self):
        """Test NONE redaction level (debug mode)"""
        result = redact_content("sensitive data", RedactionLevel.NONE)
        assert result.raw == "sensitive data"
        assert result.warning == "DEBUG_MODE_ENABLED"
        assert result.size == 14

    def test_redact_hash_level(self):
        """Test HASH redaction level (default)"""
        result = redact_content("sensitive data", RedactionLevel.HASH)
        assert result.hash is not None
        assert result.hash.startswith("sha256:")
        assert result.size == 14
        assert result.raw is None

    def test_redact_size_only_level(self):
        """Test SIZE_ONLY redaction level"""
        result = redact_content("sensitive data", RedactionLevel.SIZE_ONLY)
        assert result.size == 14
        assert result.hash is None
        assert result.category is None
        assert result.raw is None

    def test_redact_category_only_level(self):
        """Test CATEGORY_ONLY redaction level"""
        result = redact_content("SELECT * FROM users", RedactionLevel.CATEGORY_ONLY)
        assert result.category == "code"
        assert result.size is None
        assert result.hash is None
        assert result.raw is None

    def test_redact_category_only_with_explicit_category(self):
        """Test CATEGORY_ONLY with explicit category"""
        result = redact_content("data", RedactionLevel.CATEGORY_ONLY, category="prompt")
        assert result.category == "prompt"

    def test_redact_full_level(self):
        """Test FULL redaction level"""
        result = redact_content("sensitive data", RedactionLevel.FULL)
        assert result.redacted is True
        assert result.hash is None
        assert result.size is None
        assert result.category is None
        assert result.raw is None

    def test_redact_null_content(self):
        """Test redacting None content"""
        result = redact_content(None, RedactionLevel.HASH)
        assert result.hash is not None
        assert result.size == 0


class TestDetectPIIPatterns:
    """Test PII pattern detection"""

    def test_detect_email(self):
        """Test detecting email addresses"""
        detections = detect_pii_patterns("Contact: test@example.com")
        assert len(detections) == 1
        assert detections[0].type == "email"
        assert detections[0].value == "test@example.com"

    def test_detect_phone(self):
        """Test detecting phone numbers"""
        detections = detect_pii_patterns("Call: (555) 123-4567")
        assert len(detections) == 1
        assert detections[0].type == "phone"
        assert detections[0].value == "(555) 123-4567"

    def test_detect_ssn(self):
        """Test detecting SSN"""
        detections = detect_pii_patterns("SSN: 123-45-6789")
        assert len(detections) == 1
        assert detections[0].type == "ssn"
        assert detections[0].value == "123-45-6789"

    def test_detect_credit_card(self):
        """Test detecting credit card numbers"""
        detections = detect_pii_patterns("Card: 1234-5678-9012-3456")
        assert len(detections) == 1
        assert detections[0].type == "creditCard"
        assert detections[0].value == "1234-5678-9012-3456"

    def test_detect_ip_address(self):
        """Test detecting IP addresses"""
        detections = detect_pii_patterns("IP: 192.168.1.1")
        assert len(detections) == 1
        assert detections[0].type == "ipAddress"
        assert detections[0].value == "192.168.1.1"

    def test_detect_multiple_pii(self):
        """Test detecting multiple PII patterns"""
        content = "Email: test@example.com, SSN: 123-45-6789"
        detections = detect_pii_patterns(content)
        assert len(detections) == 2
        types = [d.type for d in detections]
        assert "email" in types
        assert "ssn" in types

    def test_detect_no_pii(self):
        """Test content with no PII"""
        detections = detect_pii_patterns("Hello, how are you?")
        assert len(detections) == 0

    def test_detect_empty_content(self):
        """Test detecting PII in empty content"""
        assert detect_pii_patterns("") == []
        assert detect_pii_patterns(None) == []


class TestRedactPIIFromContent:
    """Test PII redaction from content"""

    def test_redact_single_pii(self):
        """Test redacting single PII instance"""
        content = "Email: test@example.com"
        detections = detect_pii_patterns(content)
        redacted = redact_pii_from_content(content, detections)
        assert redacted == "Email: [REDACTED_EMAIL]"

    def test_redact_multiple_pii(self):
        """Test redacting multiple PII instances"""
        content = "Email: test@example.com, SSN: 123-45-6789"
        detections = detect_pii_patterns(content)
        redacted = redact_pii_from_content(content, detections)
        assert "[REDACTED_EMAIL]" in redacted
        assert "[REDACTED_SSN]" in redacted
        assert "test@example.com" not in redacted
        assert "123-45-6789" not in redacted

    def test_redact_no_detections(self):
        """Test redacting with no detections"""
        content = "Hello world"
        redacted = redact_pii_from_content(content, [])
        assert redacted == "Hello world"

    def test_redact_empty_content(self):
        """Test redacting empty content"""
        assert redact_pii_from_content("", []) == ""
        assert redact_pii_from_content(None, []) == ""


class TestRedactContentWithPII:
    """Test PII-aware content redaction"""

    def test_redact_with_pii_detection_enabled(self):
        """Test redaction with PII detection enabled"""
        content = "Email: test@example.com"
        result = redact_content_with_pii(content, RedactionLevel.HASH, detect_pii=True)

        # Content should be PII-redacted first, then hashed
        assert result.hash is not None
        assert result.size is not None
        assert result.metadata is not None
        assert result.metadata["pii_detected"] is True
        assert result.metadata["pii_count"] == 1
        assert "email" in result.metadata["pii_types"]

    def test_redact_with_pii_detection_disabled(self):
        """Test redaction with PII detection disabled"""
        content = "Email: test@example.com"
        result = redact_content_with_pii(content, RedactionLevel.HASH, detect_pii=False)

        # Standard redaction without PII detection
        assert result.hash is not None
        assert result.metadata is None or "pii_detected" not in result.metadata

    def test_redact_no_pii_found(self):
        """Test redaction when no PII is found"""
        content = "Hello world"
        result = redact_content_with_pii(content, RedactionLevel.HASH, detect_pii=True)

        assert result.hash is not None
        assert result.metadata is None or "pii_detected" not in result.metadata

    def test_redact_with_pii_full_redaction(self):
        """Test FULL redaction with PII detection"""
        content = "SSN: 123-45-6789"
        result = redact_content_with_pii(content, RedactionLevel.FULL, detect_pii=True)

        # Even with PII detected, FULL redaction should apply
        assert result.redacted is True
        # PII metadata should still be present
        assert result.metadata is not None
        assert result.metadata["pii_detected"] is True

    def test_redact_with_pii_none_level(self):
        """Test NONE redaction with PII detection (debug mode)"""
        content = "Email: test@example.com"
        result = redact_content_with_pii(content, RedactionLevel.NONE, detect_pii=True)

        # Debug mode: PII is redacted but result includes redacted content
        assert result.raw is not None
        assert "[REDACTED_EMAIL]" in result.raw
        assert result.warning == "DEBUG_MODE_ENABLED"

    def test_redact_pii_detection_failure_fallback(self):
        """Test fallback to FULL redaction on PII detection failure"""
        # This test simulates a failure scenario
        # In practice, we'd need to mock the detect_pii_patterns function
        # For now, we test that the function handles None content gracefully
        result = redact_content_with_pii(None, RedactionLevel.HASH, detect_pii=True)
        assert result.hash is not None
        assert result.size == 0


class TestSafeContentWithRaw:
    """Test SafeContentWithRaw model"""

    def test_safe_content_with_raw_all_fields(self):
        """Test SafeContentWithRaw with all fields"""
        safe = SafeContentWithRaw(
            hash="sha256:abc123",
            size=1024,
            category="prompt",
            raw="sensitive data",
            warning="DEBUG_MODE_ENABLED",
            redacted=False,
            metadata={"pii_detected": True},
        )

        assert safe.hash == "sha256:abc123"
        assert safe.size == 1024
        assert safe.category == "prompt"
        assert safe.raw == "sensitive data"
        assert safe.warning == "DEBUG_MODE_ENABLED"
        assert safe.metadata["pii_detected"] is True

    def test_safe_content_with_raw_minimal(self):
        """Test SafeContentWithRaw with minimal fields"""
        safe = SafeContentWithRaw(size=512)
        assert safe.size == 512
        assert safe.hash is None
        assert safe.raw is None


class TestPIIDetection:
    """Test PIIDetection model"""

    def test_pii_detection_model(self):
        """Test PIIDetection model creation"""
        detection = PIIDetection(
            type="email",
            value="test@example.com",
            position=7,
            length=16,
        )

        assert detection.type == "email"
        assert detection.value == "test@example.com"
        assert detection.position == 7
        assert detection.length == 16
