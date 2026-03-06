"""ContextManager utility for creating and managing ExecutionContext.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.3: Correlation IDs and Traceability

This module provides ContextManager utility class for context creation, propagation,
and HTTP header conversion.
"""

import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union

from .execution_context import (
    CONTEXT_HEADERS,
    ExecutionContext,
    ExecutionContextOptions,
    is_valid_correlation_id,
    is_valid_uuid_v4,
    validate_execution_context,
)


def generate_uuid_v4() -> str:
    """Generates a cryptographically random UUID v4.
    
    Uses Python's uuid.uuid4() which uses os.urandom() for cryptographic randomness.
    
    Returns:
        UUID v4 string
    """
    return str(uuid.uuid4())


def generate_correlation_id() -> str:
    """Generates a new correlation ID (UUID v4).
    
    Returns:
        Correlation ID string (UUID v4)
    """
    return generate_uuid_v4()


def generate_span_id() -> str:
    """Generates a new span ID (8 bytes hex).
    
    Compatible with OpenTelemetry span ID format.
    
    Returns:
        Span ID string (16 hex characters)
    """
    # Generate 8 random bytes and convert to hex
    random_bytes = secrets.token_bytes(8)
    return random_bytes.hex()


def generate_trace_id() -> str:
    """Generates a W3C Trace Context compatible trace ID (32 hex characters).
    
    Returns:
        Trace ID string (32 hex characters)
    """
    # Generate 16 random bytes and convert to hex
    random_bytes = secrets.token_bytes(16)
    return random_bytes.hex()


class ContextManager:
    """ContextManager utility class for creating and managing ExecutionContext.
    
    Provides methods for context creation, propagation, and HTTP header conversion.
    """

    @staticmethod
    def create_context(options: Optional[ExecutionContextOptions] = None) -> ExecutionContext:
        """Creates a new ExecutionContext with auto-generated correlation ID.
        
        Args:
            options: Optional context options
            
        Returns:
            New ExecutionContext with generated correlation_id
        """
        if options is None:
            options = ExecutionContextOptions()

        # Build context dict
        context_dict: Dict[str, Any] = {
            "correlation_id": options.correlation_id or generate_correlation_id(),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        # Add optional fields if provided
        if options.trace_id:
            context_dict["trace_id"] = options.trace_id
        if options.workflow_id:
            context_dict["workflow_id"] = options.workflow_id
        if options.run_id:
            context_dict["run_id"] = options.run_id
        if options.span_id:
            context_dict["span_id"] = options.span_id
        if options.parent_span_id:
            context_dict["parent_span_id"] = options.parent_span_id
        if options.tenant_id:
            context_dict["tenant_id"] = options.tenant_id
        if options.application:
            context_dict["application"] = options.application
        if options.environment:
            context_dict["environment"] = options.environment
        if options.agent_purpose:
            context_dict["agent_purpose"] = options.agent_purpose
        if options.session_id:
            context_dict["session_id"] = options.session_id
        if options.user_id:
            context_dict["user_id"] = options.user_id
        if options.metadata:
            context_dict["metadata"] = dict(options.metadata)

        return ExecutionContext(**context_dict)

    @staticmethod
    def from_headers(headers: Dict[str, Union[str, list]]) -> ExecutionContext:
        """Creates a new ExecutionContext from HTTP headers.
        
        Extracts context information from standard headers.
        
        Args:
            headers: HTTP headers dict (key-value pairs)
            
        Returns:
            ExecutionContext extracted from headers
        """

        def get_header(key: str) -> Optional[str]:
            """Get header value with case-insensitive lookup."""
            # Try exact match first
            if key in headers:
                value = headers[key]
                return value[0] if isinstance(value, list) else value

            # Try case-insensitive match
            lower_key = key.lower()
            for header_key, header_value in headers.items():
                if header_key.lower() == lower_key:
                    return header_value[0] if isinstance(header_value, list) else header_value

            return None

        options_dict: Dict[str, Any] = {}

        correlation_id = get_header(CONTEXT_HEADERS["CORRELATION_ID"])
        if correlation_id:
            options_dict["correlation_id"] = correlation_id

        trace_id = get_header(CONTEXT_HEADERS["TRACE_ID"])
        if trace_id:
            options_dict["trace_id"] = trace_id

        workflow_id = get_header(CONTEXT_HEADERS["WORKFLOW_ID"])
        if workflow_id:
            options_dict["workflow_id"] = workflow_id

        run_id = get_header(CONTEXT_HEADERS["RUN_ID"])
        if run_id:
            options_dict["run_id"] = run_id

        span_id = get_header(CONTEXT_HEADERS["SPAN_ID"])
        if span_id:
            options_dict["span_id"] = span_id

        parent_span_id = get_header(CONTEXT_HEADERS["PARENT_SPAN_ID"])
        if parent_span_id:
            options_dict["parent_span_id"] = parent_span_id

        tenant_id = get_header(CONTEXT_HEADERS["TENANT_ID"])
        if tenant_id:
            options_dict["tenant_id"] = tenant_id

        application = get_header(CONTEXT_HEADERS["APPLICATION"])
        if application:
            options_dict["application"] = application

        environment = get_header(CONTEXT_HEADERS["ENVIRONMENT"])
        if environment:
            options_dict["environment"] = environment

        agent_purpose = get_header(CONTEXT_HEADERS["AGENT_PURPOSE"])
        if agent_purpose:
            options_dict["agent_purpose"] = agent_purpose

        session_id = get_header(CONTEXT_HEADERS["SESSION_ID"])
        if session_id:
            options_dict["session_id"] = session_id

        user_id = get_header(CONTEXT_HEADERS["USER_ID"])
        if user_id:
            options_dict["user_id"] = user_id

        options = ExecutionContextOptions(**options_dict)
        return ContextManager.create_context(options)

    @staticmethod
    def to_headers(context: ExecutionContext) -> Dict[str, str]:
        """Converts ExecutionContext to HTTP headers for propagation.
        
        Args:
            context: ExecutionContext to convert
            
        Returns:
            HTTP headers dict
        """
        headers: Dict[str, str] = {
            CONTEXT_HEADERS["CORRELATION_ID"]: context.correlation_id
        }

        if context.trace_id:
            headers[CONTEXT_HEADERS["TRACE_ID"]] = context.trace_id
        if context.workflow_id:
            headers[CONTEXT_HEADERS["WORKFLOW_ID"]] = context.workflow_id
        if context.run_id:
            headers[CONTEXT_HEADERS["RUN_ID"]] = context.run_id
        if context.span_id:
            headers[CONTEXT_HEADERS["SPAN_ID"]] = context.span_id
        if context.parent_span_id:
            headers[CONTEXT_HEADERS["PARENT_SPAN_ID"]] = context.parent_span_id
        if context.tenant_id:
            headers[CONTEXT_HEADERS["TENANT_ID"]] = context.tenant_id
        if context.application:
            headers[CONTEXT_HEADERS["APPLICATION"]] = context.application
        if context.environment:
            headers[CONTEXT_HEADERS["ENVIRONMENT"]] = context.environment
        if context.agent_purpose:
            headers[CONTEXT_HEADERS["AGENT_PURPOSE"]] = context.agent_purpose
        if context.session_id:
            headers[CONTEXT_HEADERS["SESSION_ID"]] = context.session_id
        if context.user_id:
            headers[CONTEXT_HEADERS["USER_ID"]] = context.user_id

        return headers

    @staticmethod
    def propagate(
        parent_context: ExecutionContext,
        options: Optional[ExecutionContextOptions] = None,
    ) -> ExecutionContext:
        """Propagates context by creating a new child context.
        
        Preserves correlation_id, workflow_id, run_id.
        Generates new span_id and sets parent_span_id.
        
        Args:
            parent_context: Parent ExecutionContext
            options: Optional overrides for child context
            
        Returns:
            New child ExecutionContext
        """
        validate_execution_context(parent_context)

        if options is None:
            options = ExecutionContextOptions()

        # Build child context dict
        child_dict: Dict[str, Any] = {
            # Required field
            "correlation_id": parent_context.correlation_id,
            # Generate new span
            "span_id": generate_span_id(),
            # Timestamp
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        # Set parent_span_id only if parent has span_id
        if parent_context.span_id:
            child_dict["parent_span_id"] = parent_context.span_id

        # Preserve optional fields from parent if they exist
        if parent_context.workflow_id:
            child_dict["workflow_id"] = parent_context.workflow_id
        if parent_context.run_id:
            child_dict["run_id"] = parent_context.run_id
        if parent_context.trace_id:
            child_dict["trace_id"] = parent_context.trace_id
        if parent_context.tenant_id:
            child_dict["tenant_id"] = parent_context.tenant_id
        if parent_context.application:
            child_dict["application"] = parent_context.application
        if parent_context.environment:
            child_dict["environment"] = parent_context.environment
        if parent_context.agent_purpose:
            child_dict["agent_purpose"] = parent_context.agent_purpose
        if parent_context.session_id:
            child_dict["session_id"] = parent_context.session_id
        if parent_context.user_id:
            child_dict["user_id"] = parent_context.user_id

        # Merge metadata
        if parent_context.metadata or options.metadata:
            child_dict["metadata"] = {
                **parent_context.metadata,
                **options.metadata,
            }

        # Apply overrides (only set if defined)
        if options.trace_id:
            child_dict["trace_id"] = options.trace_id
        if options.workflow_id:
            child_dict["workflow_id"] = options.workflow_id
        if options.run_id:
            child_dict["run_id"] = options.run_id
        if options.span_id:
            child_dict["span_id"] = options.span_id
        if options.tenant_id:
            child_dict["tenant_id"] = options.tenant_id
        if options.application:
            child_dict["application"] = options.application
        if options.environment:
            child_dict["environment"] = options.environment
        if options.agent_purpose:
            child_dict["agent_purpose"] = options.agent_purpose
        if options.session_id:
            child_dict["session_id"] = options.session_id
        if options.user_id:
            child_dict["user_id"] = options.user_id

        return ExecutionContext(**child_dict)

    @staticmethod
    def enrich(
        context: ExecutionContext,
        metadata: Dict[str, Any],
    ) -> ExecutionContext:
        """Enriches an existing context with additional metadata.
        
        Args:
            context: ExecutionContext to enrich
            metadata: Additional metadata to add
            
        Returns:
            New ExecutionContext with enriched metadata
        """
        context_dict = context.model_dump()
        context_dict["metadata"] = {
            **context.metadata,
            **metadata,
        }
        return ExecutionContext(**context_dict)

    @staticmethod
    def is_valid(context: ExecutionContext) -> bool:
        """Validates that a context is valid.
        
        Args:
            context: ExecutionContext to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            validate_execution_context(context)
            return True
        except Exception:
            return False

    @staticmethod
    def extract(
        source: Optional[Union[Dict[str, Union[str, list]], ExecutionContext]] = None
    ) -> ExecutionContext:
        """Extracts context from various sources (headers, existing context, or creates new).
        
        Args:
            source: Headers dict, ExecutionContext, or None
            
        Returns:
            ExecutionContext
        """
        if source is None:
            return ContextManager.create_context()

        # If already an ExecutionContext, validate and return
        if isinstance(source, ExecutionContext):
            validate_execution_context(source)
            return source

        # Otherwise treat as headers
        return ContextManager.from_headers(source)
