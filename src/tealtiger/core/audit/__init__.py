"""
TealAudit - Audit Logging System

Comprehensive audit logging for compliance and debugging with security-by-default redaction.
Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.4)
"""

from .types import (
    AUDIT_SCHEMA_VERSION,
    AuditEventType,
    SafeContent,
    AuditComponentVersions,
    CostMetadata,
    AuditEvent,
    is_valid_audit_event_type,
    validate_audit_event,
    create_audit_event,
)
from .redaction import (
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
from .teal_audit import (
    AuditConfig,
    CustomRedactionRule,
    AuditOutput,
    ConsoleOutput,
    CustomOutput,
    TealAuditConfig,
    TealAudit,
)

__all__ = [
    # Types
    "AUDIT_SCHEMA_VERSION",
    "AuditEventType",
    "SafeContent",
    "AuditComponentVersions",
    "CostMetadata",
    "AuditEvent",
    "is_valid_audit_event_type",
    "validate_audit_event",
    "create_audit_event",
    # Redaction
    "RedactionLevel",
    "ContentCategory",
    "SafeContentWithRaw",
    "PIIDetection",
    "redact_content",
    "compute_sha256_hash",
    "categorize_content",
    "is_valid_redaction_level",
    "get_default_redaction_level",
    "detect_pii_patterns",
    "redact_pii_from_content",
    "redact_content_with_pii",
    # TealAudit
    "AuditConfig",
    "CustomRedactionRule",
    "AuditOutput",
    "ConsoleOutput",
    "CustomOutput",
    "TealAuditConfig",
    "TealAudit",
]
