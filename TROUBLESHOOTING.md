# TealTiger Python SDK - Troubleshooting Guide

## Common Issues and Solutions

### 1. Invalid Mode Configuration Errors

#### Issue: "Invalid policy mode: INVALID_MODE"

**Cause:** Using an invalid PolicyMode value.

**Solution:** Use one of the three valid modes:

```python
from tealtiger.core.engine.types import PolicyMode

# Valid modes
PolicyMode.ENFORCE
PolicyMode.MONITOR
PolicyMode.REPORT_ONLY
```

#### Issue: "ModeConfig is required"

**Cause:** Passing `None` as mode configuration.

**Solution:** Provide a valid ModeConfig or omit the parameter:

```python
# Option 1: Provide ModeConfig
mode_config = ModeConfig(default_mode=PolicyMode.ENFORCE)
engine = TealEngine(policy, mode=mode_config)

# Option 2: Omit (uses default ENFORCE)
engine = TealEngine(policy)
```

### 2. Missing Correlation IDs

#### Issue: "ExecutionContext must have a non-empty correlation_id"

**Cause:** Creating ExecutionContext with empty correlation_id.

**Solution:** Let ContextManager auto-generate the ID:

```python
# Good - auto-generates correlation_id
context = ContextManager.create_context()

# Bad - empty correlation_id
context = ExecutionContext(correlation_id='')  # Error!
```

#### Issue: Correlation IDs not propagating

**Cause:** Creating new context instead of reusing existing one.

**Solution:** Pass the same context to all operations:

```python
# Create once
context = ContextManager.create_context()

# Reuse everywhere
decision = engine.evaluate(request_context)
guard_result = guard.check(content, context)  # Same context
audit.log_event(event_type, context, metadata)  # Same context
```

### 3. Audit Redaction Failures

#### Issue: Raw content appearing in audit logs

**Cause:** Debug mode enabled or redaction level set to NONE.

**Solution:** Use HASH redaction and disable debug mode:

```python
config = AuditConfig(
    input_redaction=RedactionLevel.HASH,  # Not NONE
    output_redaction=RedactionLevel.HASH,
    debug_mode=False  # Must be False
)
```

#### Issue: "PII detection failed"

**Cause:** PII detection error during redaction.

**Solution:** System automatically falls back to FULL redaction. Check logs for details:

```python
# PII detection is enabled by default
config = AuditConfig(
    input_redaction=RedactionLevel.HASH,
    detect_pii=True  # Enabled by default
)

# If PII detection fails, content is fully redacted (safe fallback)
```

### 4. Policy Test Assertion Failures

#### Issue: "Expected action=DENY, got action=ALLOW"

**Cause:** Policy not blocking as expected.

**Solution:** Check policy configuration and mode:

```python
# Verify policy
policy = TealPolicy(
    tools={'file_delete': {'allowed': False}}  # Should be False
)

# Verify mode
mode_config = ModeConfig(default_mode=PolicyMode.ENFORCE)  # Not MONITOR
```

#### Issue: "Missing expected reason codes"

**Cause:** Decision doesn't include all expected reason codes.

**Solution:** Update test expectations to match actual behavior:

```python
# Check what reason codes are actually returned
decision = engine.evaluate(request_context)
print(f"Actual reason codes: {decision.reason_codes}")

# Update test
expected = {
    'action': DecisionAction.DENY,
    'reason_codes': [ReasonCode.TOOL_NOT_ALLOWED]  # Match actual
}
```

#### Issue: "Risk score not in expected range"

**Cause:** Risk score outside expected range.

**Solution:** Adjust risk score range or check calculation:

```python
# Check actual risk score
decision = engine.evaluate(request_context)
print(f"Actual risk score: {decision.risk_score}")

# Update test
expected = {
    'action': DecisionAction.DENY,
    'risk_score_range': {'min': 90, 'max': 100}  # Adjust range
}
```

### 5. Mode Override Conflicts

#### Issue: Policy mode not being applied

**Cause:** Mode override priority not understood.

**Solution:** Remember the priority order (policy > environment > global):

```python
mode_config = ModeConfig(
    default_mode=PolicyMode.MONITOR,  # Lowest priority
    environment_modes={
        'production': PolicyMode.ENFORCE  # Medium priority
    },
    policy_modes={
        'tools.file_delete': PolicyMode.ENFORCE  # Highest priority
    }
)

# tools.file_delete will use ENFORCE (policy override)
# Other policies in production will use ENFORCE (environment override)
# Other policies in other environments will use MONITOR (global default)
```

#### Issue: Environment mode not working

**Cause:** Environment name mismatch.

**Solution:** Ensure environment name matches exactly:

```python
import os

env = os.getenv('ENVIRONMENT', 'development')

mode_config = ModeConfig(
    default_mode=PolicyMode.MONITOR,
    environment_modes={
        env: PolicyMode.ENFORCE  # Use actual environment name
    }
)
```

### 6. Performance Issues

#### Issue: Slow policy evaluation

**Cause:** Creating new engine instance for each request.

**Solution:** Reuse engine instance:

```python
# Good - create once
engine = TealEngine(policy, mode=mode_config)

# Reuse for all requests
for request in requests:
    decision = engine.evaluate(request)  # Fast
```

#### Issue: Slow audit logging

**Cause:** Synchronous file I/O.

**Solution:** Use async operations:

```python
# Use async audit logging
await audit.log_event_async(event_type, context, metadata)
```

#### Issue: High memory usage

**Cause:** Storing too many audit events in memory.

**Solution:** Use file-based storage:

```python
from tealtiger.core.audit.output import FileOutput

audit = TealAudit(
    outputs=[FileOutput('./logs/audit.log')],  # Write to file
    config=config
)
```

## Debugging Tips

### Enable Verbose Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('tealtiger')
logger.setLevel(logging.DEBUG)
```

### Check Component Versions

```python
decision = engine.evaluate(request_context)
print(f"Component versions: {decision.component_versions}")
```

### Validate Decision Objects

```python
from tealtiger.core.engine.types import validate_decision

try:
    validate_decision(decision)
    print("Decision is valid")
except ValueError as e:
    print(f"Invalid decision: {e}")
```

### Query Audit Logs

```python
# Query by correlation ID
events = audit.query(correlation_id='req-12345')

for event in events:
    print(f"{event.event_type}: {event.timestamp}")
    print(f"  Metadata: {event.metadata}")
```

## Getting Help

If you're still experiencing issues:

1. Check the [Migration Guide](MIGRATION-GUIDE-v1.1.x.md) for upgrade instructions
2. Review [Best Practices](BEST-PRACTICES.md) for recommended patterns
3. Check [Examples](examples/) for working code samples
4. Open an issue at https://github.com/tealtiger/tealtiger/issues
5. Ask questions at https://github.com/tealtiger/tealtiger/discussions

## Common Error Messages

| Error Message | Cause | Solution |
|--------------|-------|----------|
| "Invalid policy mode" | Invalid PolicyMode value | Use ENFORCE, MONITOR, or REPORT_ONLY |
| "ExecutionContext is required" | Missing context | Create context with ContextManager |
| "Decision must have correlation_id" | Empty correlation_id | Let ContextManager auto-generate |
| "Policy evaluation failed" | Policy violation | Check policy configuration and mode |
| "Guardrail check failed" | Content validation failed | Review guardrail configuration |
| "Budget exceeded" | Cost limit reached | Check budget configuration |
| "PII detected" | PII in content | Enable PII redaction |
| "Test failed" | Test assertion mismatch | Update test expectations |

## Performance Benchmarks

Expected performance targets:

- Mode resolution: < 1ms p99
- Decision evaluation: < 10ms p99
- Context propagation: < 0.5ms p99
- Content redaction: < 5ms for 10KB p99
- Audit logging: < 2ms async p99
- Policy test execution: < 100ms per test

If you're not meeting these targets, check for:
- Creating new engine instances per request
- Synchronous I/O operations
- Large content sizes without streaming
- Excessive logging
