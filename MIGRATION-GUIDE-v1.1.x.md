# Migration Guide: TealTiger Python SDK v1.1.x

## Overview

TealTiger SDK v1.1.x introduces enterprise-grade features for organizational adoption while maintaining **100% backwards compatibility** with v1.0.x. All new features are **opt-in** and require no code changes for existing users.

## What's New in v1.1.x

### P0 Features (Release-Gating)

1. **Policy Rollout Modes** - ENFORCE, MONITOR, REPORT_ONLY modes for safe policy deployment
2. **Deterministic Decision Contract** - Stable typed Decision object for reliable flows
3. **Correlation IDs + Traceability** - ExecutionContext with auto-generated correlation_id
4. **Audit Schema + Redaction Guarantees** - Versioned audit events with security-by-default
5. **Policy Test Harness** - CLI/library test runner for CI/CD integration

## Backwards Compatibility Guarantee

✅ **No Breaking Changes** - All existing code continues to work without modification

- TealEngine accepts policy configurations without mode settings (uses safe defaults)
- TealEngine accepts requests without ExecutionContext (auto-generates correlation IDs)
- Decision object is a superset of the existing PolicyEvaluationResult interface
- TealAudit accepts configurations without redaction settings (uses secure defaults)
- All new features are opt-in

## Migration Paths

### Path 1: No Migration Required (Continue Using v1.0.x API)

If you're happy with your current setup, **no changes are needed**. Your existing code will continue to work:

```python
# v1.0.x code - still works in v1.1.x
from tealtiger import TealOpenAI, TealOpenAIConfig
from tealtiger.guardrails import GuardrailEngine

engine = GuardrailEngine()
client = TealOpenAI(TealOpenAIConfig(
    api_key="your-api-key",
    guardrail_engine=engine
))

# Works exactly as before
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Path 2: Gradual Adoption (Recommended)

Adopt new features incrementally as needed:

#### Step 1: Add Correlation IDs (5 minutes)

```python
from tealtiger.core.context.context_manager import ContextManager

# Create execution context
context = ContextManager.create_context(
    tenant_id='acme-corp',
    app='customer-support'
)

# Pass context to LLM requests
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    context=context  # NEW: Add context for traceability
)
```

**Benefits:**
- End-to-end request tracing
- Query audit logs by correlation_id
- Distributed tracing integration

#### Step 2: Enable Policy Rollout Modes (10 minutes)

```python
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import TealPolicy, PolicyMode, ModeConfig

# Define policy
policy = TealPolicy(
    tools={'file_delete': {'allowed': False}}
)

# Configure modes for safe rollout
mode_config = ModeConfig(
    default_mode=PolicyMode.MONITOR  # NEW: Start with MONITOR mode
)

engine = TealEngine(policy, mode=mode_config)
```

**Benefits:**
- Test policies without breaking production
- Gradual rollout (MONITOR → ENFORCE)
- Environment-specific modes

#### Step 3: Add Audit Redaction (5 minutes)

```python
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel
from tealtiger.core.audit.output import FileOutput

# Configure audit with redaction (secure by default)
audit = TealAudit(
    outputs=[FileOutput('./logs/audit.log')],
    config=AuditConfig(
        input_redaction=RedactionLevel.HASH,  # NEW: Default (secure)
        output_redaction=RedactionLevel.HASH,
        detect_pii=True  # NEW: Enabled by default
    )
)
```

**Benefits:**
- No raw prompts/responses in logs
- PII detection and redaction
- Compliance-ready audit trails

#### Step 4: Add Policy Testing (15 minutes)

```python
from tealtiger.core.engine.testing.policy_tester import PolicyTester
from tealtiger.core.engine.testing.types import PolicyTestCase, PolicyTestSuite

# Define test suite
test_suite = PolicyTestSuite(
    name='My Policy Tests',
    policy=policy,
    mode=mode_config,
    tests=[
        PolicyTestCase(
            name='Block file deletion',
            context=RequestContext(
                agent_id='test-agent',
                action='tool.execute',
                tool='file_delete',
                context=ContextManager.create_context()
            ),
            expected={'action': DecisionAction.DENY}
        )
    ]
)

# Run tests before deployment
tester = PolicyTester(engine)
report = tester.run_suite(test_suite)
```

**Benefits:**
- Validate policies before deployment
- Prevent regressions
- CI/CD integration

### Path 3: Full Enterprise Setup (30 minutes)

See `examples/enterprise_integration.py` for complete setup with all P0 features.

## API Changes

### New Interfaces

#### ExecutionContext

```python
from tealtiger.core.context.execution_context import ExecutionContext

context = ExecutionContext(
    correlation_id='req-12345',  # Auto-generated if not provided
    trace_id='4bf92f3577b34da6a3ce929d0e0e4736',  # Optional
    tenant_id='acme-corp',  # Optional
    app='customer-support',  # Optional
    env='production',  # Optional
    agent_purpose='ticket_resolution'  # Optional
)
```

#### Decision Object

```python
from tealtiger.core.engine.types import Decision, DecisionAction, ReasonCode

decision = Decision(
    action=DecisionAction.DENY,
    reason_codes=[ReasonCode.TOOL_NOT_ALLOWED],
    risk_score=95,
    mode=PolicyMode.ENFORCE,
    policy_id='tools.file_delete',
    policy_version='1.0.0',
    correlation_id='req-12345',
    component_versions={'engine': '1.1.0'}
)
```

#### PolicyMode Enum

```python
from tealtiger.core.engine.types import PolicyMode

# Three evaluation modes
PolicyMode.ENFORCE      # Block violations
PolicyMode.MONITOR      # Log violations, allow requests
PolicyMode.REPORT_ONLY  # Log decisions without evaluation
```

#### RedactionLevel Enum

```python
from tealtiger.core.audit.types import RedactionLevel

RedactionLevel.NONE          # Raw content (debug only)
RedactionLevel.HASH          # SHA-256 hash + size (default)
RedactionLevel.SIZE_ONLY     # Content size only
RedactionLevel.CATEGORY_ONLY # Content category only
RedactionLevel.FULL          # Fully redacted
```

### Updated Interfaces

#### TealOpenAI / TealAnthropic

```python
# NEW: Accept ExecutionContext in create() methods
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[...],
    context=context  # NEW: Optional ExecutionContext
)
```

#### TealEngine

```python
# NEW: Accept ModeConfig in constructor
engine = TealEngine(
    policy,
    mode=ModeConfig(default_mode=PolicyMode.MONITOR)  # NEW: Optional
)
```

#### TealAudit

```python
# NEW: Accept AuditConfig with redaction settings
audit = TealAudit(
    outputs=[...],
    config=AuditConfig(  # NEW: Optional
        input_redaction=RedactionLevel.HASH,
        output_redaction=RedactionLevel.HASH,
        detect_pii=True
    )
)
```

## Environment-Specific Configuration

### Development

```python
mode_config = ModeConfig(default_mode=PolicyMode.MONITOR)
audit_config = AuditConfig(
    input_redaction=RedactionLevel.SIZE_ONLY,
    debug_mode=True  # Explicit opt-in
)
```

### Staging

```python
mode_config = ModeConfig(
    default_mode=PolicyMode.MONITOR,
    policy_modes={
        'tools.file_delete': PolicyMode.ENFORCE,  # Critical policies
        'tools.database_write': PolicyMode.ENFORCE
    }
)
audit_config = AuditConfig(
    input_redaction=RedactionLevel.HASH,
    detect_pii=True
)
```

### Production

```python
mode_config = ModeConfig(default_mode=PolicyMode.ENFORCE)
audit_config = AuditConfig(
    input_redaction=RedactionLevel.HASH,
    output_redaction=RedactionLevel.HASH,
    detect_pii=True,
    debug_mode=False  # Never enable in production
)
```

## Testing Your Migration

### 1. Run Existing Tests

```bash
# Ensure existing tests still pass
pytest tests/
```

### 2. Add Policy Tests

```bash
# Run policy tests
python -m tealtiger.cli.test ./policies/*.json
```

### 3. Verify Audit Logs

```python
# Check that audit logs don't contain raw content
audit = TealAudit(outputs=[FileOutput('./logs/audit.log')])
# Verify logs contain hashes, not raw prompts
```

## Common Migration Scenarios

### Scenario 1: Adding Traceability to Existing Setup

**Before:**
```python
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

**After:**
```python
context = ContextManager.create_context(tenant_id='acme-corp')
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    context=context
)
```

### Scenario 2: Safe Policy Rollout

**Before:**
```python
engine = TealEngine(policy)  # Defaults to ENFORCE
```

**After:**
```python
# Start with MONITOR mode
engine = TealEngine(policy, mode=ModeConfig(default_mode=PolicyMode.MONITOR))

# After validation, switch to ENFORCE
engine = TealEngine(policy, mode=ModeConfig(default_mode=PolicyMode.ENFORCE))
```

### Scenario 3: Securing Audit Logs

**Before:**
```python
audit = TealAudit(outputs=[FileOutput('./audit.log')])
# May log raw content
```

**After:**
```python
audit = TealAudit(
    outputs=[FileOutput('./audit.log')],
    config=AuditConfig(
        input_redaction=RedactionLevel.HASH,
        output_redaction=RedactionLevel.HASH,
        detect_pii=True
    )
)
# Never logs raw content
```

## Troubleshooting

### Issue: "ExecutionContext not found"

**Solution:** Import from correct module:
```python
from tealtiger.core.context.execution_context import ExecutionContext
```

### Issue: "PolicyMode not recognized"

**Solution:** Import PolicyMode enum:
```python
from tealtiger.core.engine.types import PolicyMode
```

### Issue: "Audit logs still contain raw content"

**Solution:** Verify redaction configuration:
```python
config = AuditConfig(
    input_redaction=RedactionLevel.HASH,  # Not NONE
    debug_mode=False  # Must be False
)
```

### Issue: "Tests failing after upgrade"

**Solution:** Ensure backwards compatibility - existing tests should pass without changes. If tests fail, please report an issue.

## Getting Help

- **Documentation:** See `examples/` directory for complete examples
- **Issues:** Report bugs at https://github.com/tealtiger/tealtiger/issues
- **Discussions:** Ask questions at https://github.com/tealtiger/tealtiger/discussions

## Summary

✅ **100% Backwards Compatible** - No breaking changes
✅ **Opt-In Features** - Adopt at your own pace
✅ **Gradual Migration** - Start with correlation IDs, add features incrementally
✅ **Production Ready** - Security-by-default, compliance-ready
✅ **Zero Infrastructure** - Everything runs client-side in SDK

**Recommended Migration Timeline:**
- Week 1: Add correlation IDs
- Week 2: Enable policy rollout modes
- Week 3: Configure audit redaction
- Week 4: Add policy testing
- Week 5: Full enterprise setup

Happy migrating! 🎉
