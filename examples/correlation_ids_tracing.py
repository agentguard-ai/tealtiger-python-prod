"""
Correlation IDs and Tracing Examples

Demonstrates ExecutionContext usage for end-to-end request tracking across
all TealTiger components and external systems.

Examples:
1. Auto-generate correlation ID
2. Provide custom correlation ID
3. Propagate context through multiple operations
4. Query audit logs by correlation ID
5. Distributed tracing integration (OpenTelemetry)
6. HTTP header propagation
7. Multi-component tracing
8. Workflow and run ID tracking
9. Span-based operation tracing
"""

import asyncio
from tealtiger import TealOpenAI, TealOpenAIConfig
from tealtiger.core.context.context_manager import ContextManager
from tealtiger.core.context.execution_context import ExecutionContext
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import TealPolicy, PolicyMode, ModeConfig
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel
from tealtiger.core.audit.output import ConsoleOutput


# Example 1: Auto-generate correlation ID
async def example_auto_generate_correlation_id():
    """Auto-generate correlation ID when not provided."""
    print("\n=== Example 1: Auto-generate Correlation ID ===\n")
    
    # Create context without correlation_id - it will be auto-generated
    context = ContextManager.create_context(
        tenant_id='acme-corp',
        app='customer-support',
        env='production'
    )
    
    print(f"Auto-generated correlation_id: {context.correlation_id}")
    print(f"Tenant: {context.tenant_id}")
    print(f"App: {context.app}")
    print(f"Environment: {context.env}")


# Example 2: Provide custom correlation ID
async def example_custom_correlation_id():
    """Provide custom correlation ID for external system integration."""
    print("\n=== Example 2: Custom Correlation ID ===\n")
    
    # Use existing correlation ID from external system
    external_request_id = "req-12345-from-api-gateway"
    
    context = ExecutionContext(
        correlation_id=external_request_id,
        tenant_id='acme-corp',
        app='customer-support',
        env='production'
    )
    
    print(f"Custom correlation_id: {context.correlation_id}")
    print(f"This ID can be used to correlate with external systems")


# Example 3: Propagate context through multiple operations
async def example_context_propagation():
    """Propagate context through multiple TealTiger operations."""
    print("\n=== Example 3: Context Propagation ===\n")
    
    # Setup
    policy = TealPolicy(
        tools={'file_delete': {'allowed': False}},
        identity={'agent_id': 'support-agent-001'}
    )
    engine = TealEngine(policy)
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH
        )
    )
    
    # Create context
    context = ContextManager.create_context(
        tenant_id='acme-corp',
        app='customer-support'
    )
    
    print(f"Created context with correlation_id: {context.correlation_id}")
    
    # Operation 1: Policy evaluation
    from tealtiger.core.engine.types import RequestContext
    request_context = RequestContext(
        agent_id='support-agent-001',
        action='tool.execute',
        tool='customer_data_read',
        context=context
    )
    decision = engine.evaluate(request_context)
    print(f"\nOperation 1 - Policy evaluation:")
    print(f"  Decision: {decision.action}")
    print(f"  Correlation ID: {decision.correlation_id}")
    
    # Operation 2: Audit logging
    from tealtiger.core.audit.types import AuditEventType
    audit.log_event(
        event_type=AuditEventType.POLICY_EVALUATION,
        context=context,
        metadata={'operation': 'customer_data_read'}
    )
    print(f"\nOperation 2 - Audit logging:")
    print(f"  Logged with correlation_id: {context.correlation_id}")
    
    print(f"\nAll operations share the same correlation_id: {context.correlation_id}")


# Example 4: Query audit logs by correlation ID
async def example_query_by_correlation_id():
    """Query audit logs by correlation ID."""
    print("\n=== Example 4: Query Audit Logs by Correlation ID ===\n")
    
    # Setup
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH
        )
    )
    
    # Create context
    context = ContextManager.create_context(
        tenant_id='acme-corp'
    )
    
    print(f"Correlation ID: {context.correlation_id}")
    
    # Log multiple events with same correlation ID
    from tealtiger.core.audit.types import AuditEventType
    
    audit.log_event(
        event_type=AuditEventType.POLICY_EVALUATION,
        context=context,
        metadata={'step': 1}
    )
    
    audit.log_event(
        event_type=AuditEventType.GUARDRAIL_CHECK,
        context=context,
        metadata={'step': 2}
    )
    
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={'step': 3}
    )
    
    print(f"\nLogged 3 events with correlation_id: {context.correlation_id}")
    print("Query audit logs with this correlation_id to see all related events")


# Example 5: Distributed tracing integration (OpenTelemetry)
async def example_distributed_tracing():
    """Integrate with OpenTelemetry for distributed tracing."""
    print("\n=== Example 5: Distributed Tracing (OpenTelemetry) ===\n")
    
    # Simulate OpenTelemetry trace context
    otel_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    otel_span_id = "00f067aa0ba902b7"
    
    # Create context with trace IDs
    context = ExecutionContext(
        correlation_id=ContextManager.generate_correlation_id(),
        trace_id=otel_trace_id,
        span_id=otel_span_id,
        tenant_id='acme-corp',
        app='customer-support'
    )
    
    print(f"Correlation ID: {context.correlation_id}")
    print(f"OpenTelemetry Trace ID: {context.trace_id}")
    print(f"OpenTelemetry Span ID: {context.span_id}")
    print("\nThese IDs can be used to correlate TealTiger events with APM tools")


# Example 6: HTTP header propagation
async def example_http_header_propagation():
    """Propagate context via HTTP headers."""
    print("\n=== Example 6: HTTP Header Propagation ===\n")
    
    # Create context
    context = ContextManager.create_context(
        tenant_id='acme-corp',
        app='customer-support',
        env='production'
    )
    
    # Convert to HTTP headers for outgoing request
    headers = ContextManager.to_headers(context)
    
    print("Outgoing HTTP headers:")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    
    # Simulate receiving headers from incoming request
    incoming_headers = {
        'x-correlation-id': 'req-external-12345',
        'x-trace-id': '4bf92f3577b34da6a3ce929d0e0e4736',
        'x-tenant-id': 'acme-corp',
        'x-app': 'customer-support',
        'x-env': 'production'
    }
    
    # Extract context from headers
    extracted_context = ContextManager.from_headers(incoming_headers)
    
    print("\nExtracted context from incoming headers:")
    print(f"  Correlation ID: {extracted_context.correlation_id}")
    print(f"  Trace ID: {extracted_context.trace_id}")
    print(f"  Tenant ID: {extracted_context.tenant_id}")


# Example 7: Multi-component tracing
async def example_multi_component_tracing():
    """Track requests across TealEngine, TealGuard, and TealAudit."""
    print("\n=== Example 7: Multi-Component Tracing ===\n")
    
    # Setup all components
    policy = TealPolicy(
        tools={'file_delete': {'allowed': False}},
        identity={'agent_id': 'support-agent-001'}
    )
    engine = TealEngine(policy)
    
    from tealtiger.core.guard.teal_guard import TealGuard
    guard = TealGuard()
    
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH
        )
    )
    
    # Create context
    context = ContextManager.create_context(
        tenant_id='acme-corp',
        app='customer-support'
    )
    
    print(f"Correlation ID: {context.correlation_id}\n")
    
    # Component 1: TealEngine
    from tealtiger.core.engine.types import RequestContext
    request_context = RequestContext(
        agent_id='support-agent-001',
        action='llm.request',
        content='Hello, how can I help?',
        context=context
    )
    decision1 = engine.evaluate(request_context)
    print(f"TealEngine decision: {decision1.action}")
    print(f"  Correlation ID: {decision1.correlation_id}")
    
    # Component 2: TealGuard
    decision2 = guard.check('Hello, how can I help?', context)
    print(f"\nTealGuard decision: {decision2.action}")
    print(f"  Correlation ID: {decision2.correlation_id}")
    
    # Component 3: TealAudit
    from tealtiger.core.audit.types import AuditEventType
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={'model': 'gpt-4'}
    )
    print(f"\nTealAudit logged event")
    print(f"  Correlation ID: {context.correlation_id}")
    
    print(f"\nAll components share correlation_id: {context.correlation_id}")


# Example 8: Workflow and run ID tracking
async def example_workflow_run_tracking():
    """Track workflow executions with workflow_id and run_id."""
    print("\n=== Example 8: Workflow and Run ID Tracking ===\n")
    
    # Create context for a workflow execution
    context = ExecutionContext(
        correlation_id=ContextManager.generate_correlation_id(),
        workflow_id='customer_support.ticket_resolution:v3',
        run_id=ContextManager.generate_correlation_id(),
        tenant_id='acme-corp',
        app='customer-support',
        env='production'
    )
    
    print(f"Workflow ID: {context.workflow_id}")
    print(f"Run ID: {context.run_id}")
    print(f"Correlation ID: {context.correlation_id}")
    print("\nUse workflow_id for governance reporting across multiple runs")
    print("Use run_id to group all events from a single workflow execution")


# Example 9: Span-based operation tracing
async def example_span_based_tracing():
    """Track individual operations with span IDs."""
    print("\n=== Example 9: Span-Based Operation Tracing ===\n")
    
    # Root operation
    root_context = ExecutionContext(
        correlation_id=ContextManager.generate_correlation_id(),
        span_id=ContextManager.generate_correlation_id(),
        tenant_id='acme-corp'
    )
    
    print(f"Root operation:")
    print(f"  Correlation ID: {root_context.correlation_id}")
    print(f"  Span ID: {root_context.span_id}")
    
    # Child operation 1
    child1_context = ExecutionContext(
        correlation_id=root_context.correlation_id,
        span_id=ContextManager.generate_correlation_id(),
        parent_span_id=root_context.span_id,
        tenant_id='acme-corp'
    )
    
    print(f"\nChild operation 1:")
    print(f"  Span ID: {child1_context.span_id}")
    print(f"  Parent Span ID: {child1_context.parent_span_id}")
    
    # Child operation 2
    child2_context = ExecutionContext(
        correlation_id=root_context.correlation_id,
        span_id=ContextManager.generate_correlation_id(),
        parent_span_id=root_context.span_id,
        tenant_id='acme-corp'
    )
    
    print(f"\nChild operation 2:")
    print(f"  Span ID: {child2_context.span_id}")
    print(f"  Parent Span ID: {child2_context.parent_span_id}")
    
    print(f"\nAll operations share correlation_id: {root_context.correlation_id}")
    print("Span IDs form a lineage chain for operation tracing")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("Correlation IDs and Tracing Examples")
    print("=" * 70)
    
    await example_auto_generate_correlation_id()
    await example_custom_correlation_id()
    await example_context_propagation()
    await example_query_by_correlation_id()
    await example_distributed_tracing()
    await example_http_header_propagation()
    await example_multi_component_tracing()
    await example_workflow_run_tracking()
    await example_span_based_tracing()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
