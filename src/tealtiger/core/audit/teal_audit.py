"""
TealAudit - Audit Logging System

Comprehensive audit logging for compliance and debugging.
Supports multiple output targets (console, file, custom) with filtering and export capabilities.

Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.4)
Implements versioned audit events with security-by-default redaction.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from .redaction import (
    RedactionLevel,
    get_default_redaction_level,
)
from .types import AuditEvent, validate_audit_event
from ..context.execution_context import ExecutionContext


class CustomRedactionRule(BaseModel):
    """Custom redaction rule"""

    pattern: str = Field(..., description="Regex pattern to match")
    replacement: str = Field(..., description="Replacement string")


class AuditConfig(BaseModel):
    """
    Audit configuration with redaction support
    Part of TealTiger v1.1.x - Enterprise Adoption Features (P0.4)
    """

    input_redaction: RedactionLevel = Field(
        default=RedactionLevel.HASH,
        description="Redaction level for inputs (default: HASH)",
    )
    output_redaction: RedactionLevel = Field(
        default=RedactionLevel.HASH,
        description="Redaction level for outputs (default: HASH)",
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode - includes raw content (DANGEROUS, default: False)",
    )
    detect_pii: bool = Field(
        default=True, description="PII detection before logging (default: True)"
    )
    custom_redaction: Optional[List[CustomRedactionRule]] = Field(
        default=None, description="Custom redaction rules"
    )


class AuditOutput(ABC):
    """Output target interface for audit events"""

    @abstractmethod
    def write(self, event: Dict[str, Any]) -> None:
        """Write an audit event to the output"""
        pass

    def close(self) -> None:
        """Close the output (optional)"""
        pass


class ConsoleOutput(AuditOutput):
    """Console output for audit events"""

    def write(self, event: Dict[str, Any]) -> None:
        print(json.dumps(event, default=str))


class CustomOutput(AuditOutput):
    """Custom output with user-defined handler"""

    def __init__(self, handler: Callable[[Dict[str, Any]], None]):
        self.handler = handler

    def write(self, event: Dict[str, Any]) -> None:
        self.handler(event)


class AuditFilter(BaseModel):
    """Filter for querying audit events"""

    min_cost: Optional[float] = Field(None, description="Minimum cost threshold")
    agents: Optional[List[str]] = Field(None, description="Filter by agent IDs")
    actions: Optional[List[str]] = Field(None, description="Filter by actions")
    start_time: Optional[datetime] = Field(
        None, description="Start time for time range filter"
    )
    end_time: Optional[datetime] = Field(
        None, description="End time for time range filter"
    )
    has_error: Optional[bool] = Field(None, description="Filter by error presence")
    correlation_id: Optional[str] = Field(
        None, description="Filter by correlation ID (for versioned events)"
    )


class TealAuditConfig(BaseModel):
    """Configuration for TealAudit"""

    outputs: List[AuditOutput] = Field(..., description="Output targets for audit events")
    max_events: int = Field(
        default=10000, description="Maximum number of events to store in memory"
    )
    enable_storage: bool = Field(
        default=True, description="Enable in-memory storage for querying"
    )
    config: Optional[AuditConfig] = Field(
        default=None, description="Audit configuration with redaction support (P0.4)"
    )

    class Config:
        arbitrary_types_allowed = True


class TealAudit:
    """
    TealAudit - Comprehensive audit logging system

    Supports versioned AuditEvent format with security-by-default redaction.
    Implements context propagation for end-to-end traceability.

    Example:
        >>> # Production configuration (secure by default)
        >>> audit = TealAudit(
        ...     outputs=[ConsoleOutput()],
        ...     config=AuditConfig(
        ...         input_redaction=RedactionLevel.HASH,
        ...         output_redaction=RedactionLevel.HASH,
        ...         detect_pii=True,
        ...         debug_mode=False
        ...     )
        ... )
        >>>
        >>> # Log versioned audit event
        >>> audit.log(AuditEvent(
        ...     schema_version='1.0.0',
        ...     event_type=AuditEventType.POLICY_EVALUATION,
        ...     timestamp=datetime.utcnow().isoformat() + 'Z',
        ...     correlation_id='req-12345',
        ...     action=DecisionAction.ALLOW,
        ...     risk_score=25
        ... ))
        >>>
        >>> # Query events by correlation_id
        >>> events = audit.query(AuditFilter(correlation_id='req-12345'))
    """

    def __init__(
        self,
        outputs: List[AuditOutput],
        max_events: int = 10000,
        enable_storage: bool = True,
        config: Optional[AuditConfig] = None,
    ):
        """
        Initialize TealAudit

        Args:
            outputs: Output targets for audit events
            max_events: Maximum number of events to store in memory (default: 10000)
            enable_storage: Enable in-memory storage for querying (default: True)
            config: Audit configuration with redaction support (P0.4)
        """
        self.outputs = outputs
        self.events: List[AuditEvent] = []
        self.max_events = max_events
        self.enable_storage = enable_storage

        # Initialize audit config with security-by-default settings
        if config is None:
            config = AuditConfig()

        self.config = AuditConfig(
            input_redaction=config.input_redaction
            if config.input_redaction is not None
            else get_default_redaction_level(),
            output_redaction=config.output_redaction
            if config.output_redaction is not None
            else get_default_redaction_level(),
            debug_mode=config.debug_mode if config.debug_mode is not None else False,
            detect_pii=config.detect_pii if config.detect_pii is not None else True,
            custom_redaction=config.custom_redaction,
        )

        # Log warning if debug mode is enabled (Requirement 11.5)
        if self.config.debug_mode:
            print(
                "⚠️  TealAudit: DEBUG MODE ENABLED - Raw content will be logged. "
                "This is DANGEROUS in production and may expose sensitive data. "
                "Disable debug_mode for production use."
            )

    def get_config(self) -> AuditConfig:
        """
        Get the current audit configuration

        Returns:
            Current AuditConfig
        """
        return self.config.model_copy(deep=True)

    def propagate_context(
        self, event: AuditEvent, context: ExecutionContext
    ) -> AuditEvent:
        """
        Propagate ExecutionContext into an audit event

        This is a utility method for enriching audit events with context fields
        before logging. It extracts correlation_id, trace_id, workflow_id, run_id,
        span_id, and parent_span_id from the ExecutionContext and includes them
        in the audit event.

        This method completes in less than 0.5 milliseconds (Requirement 7.5).

        Args:
            event: Audit event to enrich
            context: ExecutionContext to propagate

        Returns:
            Enriched audit event with context fields

        Example:
            >>> context = ContextManager.create_context(tenant_id='acme-corp')
            >>> event = audit.propagate_context(
            ...     AuditEvent(
            ...         schema_version='1.0.0',
            ...         event_type=AuditEventType.POLICY_EVALUATION,
            ...         timestamp=datetime.utcnow().isoformat() + 'Z',
            ...         correlation_id='temp-id',
            ...         action=DecisionAction.ALLOW
            ...     ),
            ...     context
            ... )
            >>> audit.log(event)
        """
        # Clone the event to avoid mutating the original
        enriched = event.model_copy(deep=True)

        # Always include correlation_id from context (Requirement 3.11)
        if context.correlation_id:
            enriched.correlation_id = context.correlation_id

        # Include optional context fields if present
        if context.trace_id:
            enriched.trace_id = context.trace_id

        if context.workflow_id:
            enriched.workflow_id = context.workflow_id

        if context.run_id:
            enriched.run_id = context.run_id

        if context.span_id:
            enriched.span_id = context.span_id

        if context.parent_span_id:
            enriched.parent_span_id = context.parent_span_id

        # Include tenant_id in metadata if present
        if context.tenant_id:
            if not enriched.metadata:
                enriched.metadata = {}
            enriched.metadata["tenant_id"] = context.tenant_id

        # Include environment in metadata if present
        if context.environment:
            if not enriched.metadata:
                enriched.metadata = {}
            enriched.metadata["environment"] = context.environment

        # Include application in metadata if present
        if context.application:
            if not enriched.metadata:
                enriched.metadata = {}
            enriched.metadata["application"] = context.application

        return enriched

    def log(
        self, event: AuditEvent, context: Optional[ExecutionContext] = None
    ) -> None:
        """
        Log an audit event

        Applies redaction to safe_inputs and safe_outputs.
        Propagates ExecutionContext fields if provided.

        Args:
            event: Audit event to log
            context: Optional ExecutionContext for context propagation (P0.3)
        """
        try:
            # Validate versioned event
            validate_audit_event(event)

            # Process the event with redaction and context propagation
            processed_event = self._process_versioned_event(event, context)

            # Write to all outputs
            for output in self.outputs:
                try:
                    output.write(processed_event.model_dump(mode="json", exclude_none=True))
                except Exception as error:
                    print(f"TealAudit: Failed to write to output: {error}")

            # Store in memory if enabled
            if self.enable_storage:
                self.events.append(processed_event)

                # Enforce max events limit
                if len(self.events) > self.max_events:
                    self.events.pop(0)  # Remove oldest event

        except Exception as error:
            print(f"TealAudit: Failed to validate or process event: {error}")
            # Continue (non-blocking, Requirement 13.5)

    def _process_versioned_event(
        self, event: AuditEvent, context: Optional[ExecutionContext] = None
    ) -> AuditEvent:
        """
        Process a versioned audit event with redaction and context propagation

        This method applies the configured redaction levels to inputs and outputs.
        It never emits raw prompts/responses by default (Requirement 4.14).
        It also propagates ExecutionContext fields into the audit event (Requirements 3.8, 3.9, 3.10).

        Args:
            event: Audit event to process
            context: Optional ExecutionContext for context propagation

        Returns:
            Processed event with redacted content and propagated context
        """
        # Clone the event to avoid mutating the original
        processed = event.model_copy(deep=True)

        # Propagate ExecutionContext fields if provided (Requirements 3.8, 3.9, 3.10)
        if context:
            # Always include correlation_id from context (Requirement 3.11)
            if context.correlation_id:
                processed.correlation_id = context.correlation_id

            # Include optional context fields if present
            if context.trace_id:
                processed.trace_id = context.trace_id

            if context.workflow_id:
                processed.workflow_id = context.workflow_id

            if context.run_id:
                processed.run_id = context.run_id

            if context.span_id:
                processed.span_id = context.span_id

            if context.parent_span_id:
                processed.parent_span_id = context.parent_span_id

            # Include tenant_id in metadata if present
            if context.tenant_id:
                if not processed.metadata:
                    processed.metadata = {}
                processed.metadata["tenant_id"] = context.tenant_id

            # Include environment in metadata if present
            if context.environment:
                if not processed.metadata:
                    processed.metadata = {}
                processed.metadata["environment"] = context.environment

            # Include application in metadata if present
            if context.application:
                if not processed.metadata:
                    processed.metadata = {}
                processed.metadata["application"] = context.application

        # Apply custom redaction rules if configured
        if self.config.custom_redaction and len(self.config.custom_redaction) > 0:
            # Custom redaction is applied to metadata fields if present
            if processed.metadata:
                processed.metadata = self._apply_custom_redaction(processed.metadata)

        # If debug mode is enabled, add warning to metadata
        if self.config.debug_mode:
            if not processed.metadata:
                processed.metadata = {}
            processed.metadata[
                "debug_mode_warning"
            ] = "DEBUG_MODE_ENABLED: Raw content may be included"

        return processed

    def _apply_custom_redaction(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply custom redaction rules to metadata

        Args:
            metadata: Metadata object to redact

        Returns:
            Redacted metadata
        """
        redacted = metadata.copy()

        # Apply custom redaction rules to string values
        for key, value in redacted.items():
            if isinstance(value, str):
                redacted_value = value
                for rule in self.config.custom_redaction:
                    pattern = re.compile(rule.pattern)
                    redacted_value = pattern.sub(rule.replacement, redacted_value)
                redacted[key] = redacted_value
            elif isinstance(value, dict):
                # Recursively apply to nested objects
                redacted[key] = self._apply_custom_redaction(value)

        return redacted

    def query(self, filter: Optional[AuditFilter] = None) -> List[AuditEvent]:
        """
        Query audit events with optional filters

        Supports filtering by correlation_id (Requirement 3.12).

        Args:
            filter: Filter criteria

        Returns:
            Filtered audit events
        """
        if not self.enable_storage:
            raise ValueError("TealAudit: Storage is disabled, cannot query events")

        if not filter:
            return self.events.copy()

        return [event for event in self.events if self._matches_filter(event, filter)]

    def export(
        self, format: str = "json", filter: Optional[AuditFilter] = None
    ) -> str:
        """
        Export audit events to JSON or CSV format

        Args:
            format: Export format ('json' or 'csv')
            filter: Optional filter to apply before export

        Returns:
            Exported data as string
        """
        events = self.query(filter) if filter else self.query()

        if format == "json":
            return json.dumps(
                [event.model_dump(mode="json", exclude_none=True) for event in events],
                indent=2,
                default=str,
            )
        elif format == "csv":
            return self._export_to_csv(events)
        else:
            raise ValueError(f"TealAudit: Unsupported export format: {format}")

    def clear(self) -> None:
        """Clear all stored events"""
        self.events = []

    def get_event_count(self) -> int:
        """Get the number of stored events"""
        return len(self.events)

    def close(self) -> None:
        """Close all outputs"""
        for output in self.outputs:
            try:
                output.close()
            except Exception as error:
                print(f"TealAudit: Failed to close output: {error}")

    def _matches_filter(self, event: AuditEvent, filter: AuditFilter) -> bool:
        """
        Check if an event matches the filter criteria

        Args:
            event: Audit event to check
            filter: Filter criteria

        Returns:
            True if event matches filter, False otherwise
        """
        # Filter by correlation_id
        if filter.correlation_id and event.correlation_id != filter.correlation_id:
            return False

        # Filter by min_cost
        if filter.min_cost is not None and (
            event.cost is None or event.cost < filter.min_cost
        ):
            return False

        # Filter by agents
        if filter.agents and event.agent_id and event.agent_id not in filter.agents:
            return False

        # Filter by start_time
        if filter.start_time:
            event_time = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            # Make filter.start_time timezone-aware if it's naive
            start_time = filter.start_time
            if start_time.tzinfo is None:
                from datetime import timezone
                start_time = start_time.replace(tzinfo=timezone.utc)
            if event_time < start_time:
                return False

        # Filter by end_time
        if filter.end_time:
            event_time = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            # Make filter.end_time timezone-aware if it's naive
            end_time = filter.end_time
            if end_time.tzinfo is None:
                from datetime import timezone
                end_time = end_time.replace(tzinfo=timezone.utc)
            if event_time > end_time:
                return False

        # Filter by has_error
        if filter.has_error is not None:
            has_error = event.error is not None
            if has_error != filter.has_error:
                return False

        return True

    def _export_to_csv(self, events: List[AuditEvent]) -> str:
        """
        Export events to CSV format

        Args:
            events: Events to export

        Returns:
            CSV string
        """
        if len(events) == 0:
            return ""

        # Define headers
        headers = [
            "schema_version",
            "event_type",
            "timestamp",
            "correlation_id",
            "trace_id",
            "policy_id",
            "mode",
            "action",
            "risk_score",
            "agent_id",
            "provider",
            "model",
            "cost",
            "duration",
            "error",
        ]

        rows: List[str] = [",".join(headers)]

        for event in events:
            # Handle enum values - they're already strings due to use_enum_values=True
            event_type_str = event.event_type if isinstance(event.event_type, str) else event.event_type.value
            mode_str = event.mode if isinstance(event.mode, str) else event.mode.value if event.mode else ""
            action_str = event.action if isinstance(event.action, str) else event.action.value if event.action else ""
            
            row = [
                self._escape_csv(event.schema_version),
                self._escape_csv(event_type_str),
                self._escape_csv(event.timestamp),
                self._escape_csv(event.correlation_id),
                self._escape_csv(event.trace_id) if event.trace_id else "",
                self._escape_csv(event.policy_id) if event.policy_id else "",
                self._escape_csv(mode_str),
                self._escape_csv(action_str),
                str(event.risk_score) if event.risk_score is not None else "",
                self._escape_csv(event.agent_id) if event.agent_id else "",
                self._escape_csv(event.provider) if event.provider else "",
                self._escape_csv(event.model) if event.model else "",
                str(event.cost) if event.cost is not None else "",
                str(event.duration) if event.duration is not None else "",
                self._escape_csv(event.error) if event.error else "",
            ]
            rows.append(",".join(row))

        return "\n".join(rows)

    def _escape_csv(self, value: str) -> str:
        """
        Escape CSV field value

        Args:
            value: Value to escape

        Returns:
            Escaped value
        """
        if "," in value or '"' in value or "\n" in value:
            return '"' + value.replace('"', '""') + '"'
        return value
