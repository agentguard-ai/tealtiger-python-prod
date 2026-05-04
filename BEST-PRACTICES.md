# TealTiger Python SDK - Best Practices

## Overview

This guide provides best practices for using TealTiger SDK v1.1.x enterprise features in production environments.

## Policy Rollout Modes

### Best Practice 1: Start with MONITOR Mode

Always start with MONITOR mode when deploying new policies to production:

```python
from tealtiger.core.engine.teal_engine import TealEngine
from tealtiger.core.engine.types import PolicyMode, ModeConfig

# Start with MONITOR mode
mode_config = ModeConfig(default_mode=PolicyMode.MONITOR)
engine = TealEngine(policy, mode=mode_config)
```

**Why?** MONITOR mode allows you to observe policy behavior without breaking production.

### Best Practice 2: Graduate to ENFORCE Mode

After validating policy behavior in MONITOR mode, graduate to ENFORCE:

```python
# After 1-2 weeks of monitoring
mode_config = ModeConfig(default_mode=PolicyMode.ENFORCE)
engine = TealEngine(policy, mode=mode_config)
```

### Best Practice 3: Use Environment-Specific Modes

Configure different modes for different environments:

```python
import os

env = os.getenv('ENVIRONMENT', 'development')

if env == 'production':
    mode_config = ModeConfig(default_mode=PolicyMode.ENFORCE)
elif env == 'staging':
    mode_config = ModeConfig(
        default_mode=PolicyMode.MONITOR,
        policy_modes={
            'tools.file_delete': PolicyMode.ENFORCE,
            'tools.database_write': PolicyMode.ENFORCE
        }
    )
else:
    mode_config = ModeConfig(default_mode=PolicyMode.MONITOR)
```

## Correlation IDs and Traceability

### Best Practice 4: Always Use Correlation IDs

Create ExecutionContext for every request:

```python
from tealtiger.core.context.context_manager import ContextManager

context = ContextManager.create_context(
    tenant_id='acme-corp',
    app='customer-support',
    env='production'
)

response = await client.chat.completions.create(
    model='gpt-4',
    messages=[...],
    context=context
)
```

### Best Practice 5: Propagate Context Through Operations

Pass the same context to all operations:

```python
# Create once
context = ContextManager.create_context(tenant_id='acme-corp')

# Use everywhere
decision = engine.evaluate(request_context)
guard_result = guard.check(content, context)
audit.log_event(event_type, context, metadata)
```

### Best Practice 6: Use HTTP Headers for Distributed Tracing

Convert context to/from HTTP headers:

```python
# Outgoing request
headers = ContextManager.to_headers(context)
response = requests.post(url, headers=headers)

# Incoming request
context = ContextManager.from_headers(request.headers)
```

## Audit Redaction

### Best Practice 7: Use HASH Redaction in Production

Always use HASH redaction for production audit logs:

```python
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel

audit = TealAudit(
    outputs=[FileOutput('./logs/audit.log')],
    config=AuditConfig(
        input_redaction=RedactionLevel.HASH,
        output_redaction=RedactionLevel.HASH,
        detect_pii=True
    )
)
```

### Best Practice 8: Never Enable Debug Mode in Production

Debug mode disables redaction - only use in development:

```python
# Development only
if os.getenv('ENVIRONMENT') == 'development':
    config = AuditConfig(
        input_redaction=RedactionLevel.NONE,
        debug_mode=True
    )
else:
    # Production - secure by default
    config = AuditConfig(
        input_redaction=RedactionLevel.HASH,
        output_redaction=RedactionLevel.HASH
    )
```

## Policy Testing

### Best Practice 9: Test Policies Before Deployment

Run policy tests in CI/CD before deploying:

```python
from tealtiger.core.engine.testing.policy_tester import PolicyTester

tester = PolicyTester(engine)
report = tester.run_suite(test_suite)

if report.failed > 0:
    raise Exception(f"Policy tests failed: {report.failed}/{report.total}")
```

### Best Practice 10: Use Starter Test Corpora

Leverage pre-built test suites for comprehensive coverage:

```python
from tealtiger.core.engine.testing.test_corpora import TestCorpora

# Get all starter tests
all_tests = TestCorpora.all()

# Or specific categories
injection_tests = TestCorpora.prompt_injection()
pii_tests = TestCorpora.pii_detection()
```

### Best Practice 11: Integrate with CI/CD

Add policy testing to your CI/CD pipeline:

```yaml
# .github/workflows/policy-tests.yml
name: Policy Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install tealtiger
      - run: python -m tealtiger.cli.test ./policies/*.json
```

## Performance Optimization

### Best Practice 12: Reuse Engine Instances

Create TealEngine once and reuse:

```python
# Good - create once
engine = TealEngine(policy, mode=mode_config)

# Reuse for all requests
for request in requests:
    decision = engine.evaluate(request)
```

### Best Practice 13: Use Async Operations

Use async/await for better performance:

```python
async def process_requests(requests):
    tasks = [
        client.chat.completions.create(
            model='gpt-4',
            messages=req.messages,
            context=req.context
        )
        for req in requests
    ]
    return await asyncio.gather(*tasks)
```

## Security

### Best Practice 14: Validate All Inputs

Always validate user inputs before processing:

```python
from tealtiger.core.guard.teal_guard import TealGuard

guard = TealGuard()
decision = guard.check(user_input, context)

if decision.action != 'ALLOW':
    raise ValueError(f"Input validation failed: {decision.reason}")
```

### Best Practice 15: Use PII Detection

Enable PII detection by default:

```python
config = AuditConfig(
    input_redaction=RedactionLevel.HASH,
    output_redaction=RedactionLevel.HASH,
    detect_pii=True  # Always enabled
)
```

## Monitoring and Observability

### Best Practice 16: Query Audit Logs by Correlation ID

Use correlation IDs to trace requests:

```python
# Query all events for a request
events = audit.query(correlation_id='req-12345')

for event in events:
    print(f"{event.event_type}: {event.timestamp}")
```

### Best Practice 17: Track Coverage

Monitor policy test coverage:

```python
report = tester.run_suite(test_suite)

if report.coverage.coverage_percentage < 80:
    print(f"Warning: Low coverage ({report.coverage.coverage_percentage}%)")
    print(f"Untested policies: {report.coverage.untested_policies}")
```

## Error Handling

### Best Practice 18: Handle Policy Violations Gracefully

Catch and handle policy violations:

```python
try:
    response = await client.chat.completions.create(
        model='gpt-4',
        messages=[...],
        context=context
    )
except ValueError as e:
    if 'Policy evaluation failed' in str(e):
        # Handle policy violation
        logger.error(f"Policy violation: {e}")
        return error_response("Request blocked by policy")
    raise
```

## Configuration Management

### Best Practice 19: Use Environment Variables

Store configuration in environment variables:

```python
import os

config = TealOpenAIConfig(
    api_key=os.getenv('OPENAI_API_KEY'),
    agent_id=os.getenv('AGENT_ID', 'default-agent')
)
```

### Best Practice 20: Separate Policies by Environment

Use different policy files for different environments:

```python
env = os.getenv('ENVIRONMENT', 'development')
policy_file = f'./policies/{env}.json'

with open(policy_file) as f:
    policy = json.load(f)
```

## Summary

✅ Start with MONITOR mode, graduate to ENFORCE
✅ Always use correlation IDs for traceability
✅ Use HASH redaction in production
✅ Test policies in CI/CD before deployment
✅ Use starter test corpora for comprehensive coverage
✅ Configure environment-specific modes
✅ Enable PII detection by default
✅ Reuse engine instances for performance
✅ Handle policy violations gracefully
✅ Monitor coverage and audit logs
