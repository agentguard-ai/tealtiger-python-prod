"""
Enterprise Integration Example

Complete end-to-end example demonstrating all P0 enterprise features:
- Policy Rollout Modes (ENFORCE, MONITOR, REPORT_ONLY)
- Deterministic Decision Contract
- Correlation IDs and Traceability
- Audit Schema with Redaction
- Policy Testing

This example shows how to set up TealTiger for enterprise production use.
"""

import asyncio
import os
from tealtiger import TealOpenAI, TealOpenAIConfig
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import TealPolicy, PolicyMode, ModeConfig
from tealtiger.core.guard.teal_guard import TealGuard
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel
from tealtiger.core.audit.output import ConsoleOutput, FileOutput
from tealtiger.core.context.context_manager import ContextManager
from tealtiger.core.engine.testing.policy_tester import PolicyTester
from tealtiger.core.engine.testing.types import PolicyTestCase, PolicyTestSuite, RequestContext, DecisionAction, ReasonCode


async def main():
    """Complete enterprise setup with all P0 features."""
    print("=" * 70)
    print("TealTiger Enterprise Integration Example")
    print("=" * 70)
    
    # ========================================================================
    # STEP 1: Define Enterprise Policy
    # ========================================================================
    print("\n[1/6] Defining Enterprise Policy...")
    
    policy = TealPolicy(
        tools={
            'file_delete': {'allowed': False},
            'database_write': {'allowed': False},
            'customer_data_read': {'allowed': True},
            'send_email': {'allowed': True}
        },
        identity={
            'agent_id': 'customer-support-agent',
            'role': 'customer-support',
            'permissions': ['read:customer_data', 'send:email']
        }
    )
    
    print("✓ Policy defined with tool restrictions and identity controls")
    
    # ========================================================================
    # STEP 2: Configure Policy Rollout Modes
    # ========================================================================
    print("\n[2/6] Configuring Policy Rollout Modes...")
    
    # Environment-specific mode configuration
    env = os.getenv('ENVIRONMENT', 'development')
    
    if env == 'production':
        # Production: Enforce all policies
        mode_config = ModeConfig(
            default_mode=PolicyMode.ENFORCE
        )
        print("✓ Production mode: ENFORCE (blocks violations)")
    elif env == 'staging':
        # Staging: Enforce critical, monitor others
        mode_config = ModeConfig(
            default_mode=PolicyMode.MONITOR,
            policy_modes={
                'tools.file_delete': PolicyMode.ENFORCE,
                'tools.database_write': PolicyMode.ENFORCE
            }
        )
        print("✓ Staging mode: MONITOR with critical policies ENFORCED")
    else:
        # Development: Monitor everything
        mode_config = ModeConfig(
            default_mode=PolicyMode.MONITOR
        )
        print("✓ Development mode: MONITOR (logs violations, allows requests)")
    
    # ========================================================================
    # STEP 3: Initialize TealTiger Components
    # ========================================================================
    print("\n[3/6] Initializing TealTiger Components...")
    
    # TealEngine - Policy evaluation
    engine = TealEngine(policy, mode=mode_config)
    print("✓ TealEngine initialized")
    
    # TealGuard - Content validation
    guard = TealGuard()
    print("✓ TealGuard initialized")
    
    # TealAudit - Audit logging with security-by-default redaction
    audit = TealAudit(
        outputs=[
            ConsoleOutput(),
            FileOutput('./logs/audit.log')
        ],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,  # SHA-256 hash (default)
            output_redaction=RedactionLevel.HASH,
            detect_pii=True,  # Enabled by default
            debug_mode=False  # Never enable in production
        )
    )
    print("✓ TealAudit initialized with HASH redaction and PII detection")
    
    # ========================================================================
    # STEP 4: Test Policies Before Deployment
    # ========================================================================
    print("\n[4/6] Testing Policies...")
    
    test_suite = PolicyTestSuite(
        name='Customer Support Agent Tests',
        description='Pre-deployment policy validation',
        policy=policy,
        mode=mode_config,
        tests=[
            PolicyTestCase(
                name='Block file deletion',
                context=RequestContext(
                    agent_id='customer-support-agent',
                    action='tool.execute',
                    tool='file_delete',
                    context=ContextManager.create_context()
                ),
                expected={
                    'action': DecisionAction.DENY,
                    'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED]
                }
            ),
            PolicyTestCase(
                name='Allow customer data read',
                context=RequestContext(
                    agent_id='customer-support-agent',
                    action='tool.execute',
                    tool='customer_data_read',
                    context=ContextManager.create_context()
                ),
                expected={
                    'action': DecisionAction.ALLOW
                }
            )
        ]
    )
    
    tester = PolicyTester(engine)
    report = tester.run_suite(test_suite)
    
    print(f"✓ Policy tests: {report.passed}/{report.total} passed ({report.success_rate * 100:.1f}%)")
    
    if report.failed > 0:
        print("✗ Some tests failed - fix policies before deployment!")
        return
    
    # ========================================================================
    # STEP 5: Create Guarded OpenAI Client
    # ========================================================================
    print("\n[5/6] Creating Guarded OpenAI Client...")
    
    client = TealOpenAI(TealOpenAIConfig(
        api_key=os.getenv('OPENAI_API_KEY', 'sk-test-key'),
        agent_id='customer-support-agent',
        engine=engine,
        guard=guard,
        audit=audit
    ))
    
    print("✓ TealOpenAI client created with all enterprise features")
    
    # ========================================================================
    # STEP 6: Make LLM Request with Full Traceability
    # ========================================================================
    print("\n[6/6] Making LLM Request with Traceability...")
    
    # Create execution context for traceability
    context = ContextManager.create_context(
        tenant_id='acme-corp',
        app='customer-support',
        env=env,
        agent_purpose='ticket_resolution'
    )
    
    print(f"✓ Execution context created")
    print(f"  Correlation ID: {context.correlation_id}")
    print(f"  Tenant: {context.tenant_id}")
    print(f"  Environment: {context.env}")
    
    try:
        # Make LLM request with context
        response = await client.chat.completions.create(
            model='gpt-4',
            messages=[
                {'role': 'user', 'content': 'How can I help customers today?'}
            ],
            context=context  # Context propagates through all components
        )
        
        print(f"\n✓ LLM request successful")
        print(f"  Response: {response.choices[0]['message']['content'][:100]}...")
        print(f"  Correlation ID: {context.correlation_id}")
        
        # All audit events include the same correlation_id
        print(f"\n✓ Audit trail created with correlation_id: {context.correlation_id}")
        print("  Query audit logs by correlation_id to see:")
        print("  - Policy evaluation decision")
        print("  - Content validation result")
        print("  - LLM request/response (redacted)")
        print("  - Cost tracking")
        
    except ValueError as e:
        print(f"\n✗ Request blocked by policy: {e}")
        print(f"  Correlation ID: {context.correlation_id}")
        print("  Check audit logs for details")
    
    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("Enterprise Integration Complete!")
    print("=" * 70)
    print("\nFeatures Enabled:")
    print("  ✓ Policy Rollout Modes (environment-specific)")
    print("  ✓ Deterministic Decision Contract")
    print("  ✓ Correlation IDs and Traceability")
    print("  ✓ Audit Schema with Redaction (HASH + PII detection)")
    print("  ✓ Policy Testing (pre-deployment validation)")
    print("\nSecurity Guarantees:")
    print("  ✓ No raw prompts/responses in audit logs (HASH redaction)")
    print("  ✓ PII detection enabled by default")
    print("  ✓ End-to-end request tracing with correlation IDs")
    print("  ✓ Policy behavior validated before deployment")
    print("\nProduction Readiness:")
    print("  ✓ Environment-specific mode configuration")
    print("  ✓ Comprehensive audit trails")
    print("  ✓ Compliance-ready (OWASP, NIST AI RMF, Google SAIF)")
    print("  ✓ Zero infrastructure required")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
