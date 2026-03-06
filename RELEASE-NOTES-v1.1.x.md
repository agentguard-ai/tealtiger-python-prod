# TealTiger Python SDK v1.1.x Release Notes

## Overview

TealTiger SDK v1.1.x introduces **enterprise-grade features** for organizational adoption while maintaining **100% backwards compatibility** with v1.0.x.

## Release Date

February 2026

## What's New

### P0.1: Policy Rollout Modes

Safe policy deployment with three evaluation modes:

- **ENFORCE**: Block violations (production mode)
- **MONITOR**: Log violations, allow requests (observability mode)
- **REPORT_ONLY**: Log decisions without evaluation (testing mode)

```python
from tealtiger.core.engine.types import PolicyMode, ModeConfig

mode_config = ModeConfig(
    default_mode=PolicyMode.MONITOR,  # Start with MONITOR
    environment_modes={'production': PolicyMode.ENFORCE},
    policy_modes={'tools.file_delete': PolicyMode.ENFORCE}
)

engine = TealEngine(policy, mode=mode_config)
```

**Benefits:**
- Test policies without breaking production
- Gradual rollout (MONITOR → ENFORCE)
- Environment-specific configuration

### P0.2: Deterministic Decision Contract

Stable typed Decision object for reliable flows:

```python
from tealtiger.core.engine.types import Decision, DecisionAction, ReasonCode

decision = engine.evaluate(request_context)

# Deterministic fields
assert decision.action in [DecisionAction.ALLOW, DecisionAction.DENY]
assert len(decision.reason_codes) > 0
assert 0 <= decision.risk_score <= 100
assert decision.correlation_id  # Always present
```

**Benefits:**
- Predictable decision structure
- Type-safe integration
- Standardized reason codes

### P0.3: Correlation IDs + Traceability

ExecutionContext with auto-generated correlation IDs:

```python
from tealtiger.core.context.context_manager import ContextManager

# Auto-generate correlation ID
context = ContextManager.create_context(
    tenant_id='acme-corp',
    app='customer-support'
)

# Use across all operations
response = await client.chat.completions.create(
    model='gpt-4',
    messages=[...],
    context=context
)

# Query audit logs by correlation ID
events = audit.query(correlation_id=context.correlation_id)
```

**Benefits:**
- End-to-end request tracing
- Distributed tracing integration (OpenTelemetry)
- HTTP header propagation

### P0.4: Audit Schema + Redaction Guarantees

Versioned audit events with security-by-default redaction:

```python
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel

audit = TealAudit(
    outputs=[FileOutput('./logs/audit.log')],
    config=AuditConfig(
        input_redaction=RedactionLevel.HASH,  # SHA-256 hash (default)
        output_redaction=RedactionLevel.HASH,
        detect_pii=True  # Enabled by default
    )
)
```

**Benefits:**
- No raw prompts/responses in logs
- PII detection and redaction
- Compliance-ready audit trails
- Versioned schema (1.0.0)

### P0.5: Policy Test Harness

CLI/library test runner for CI/CD integration:

```python
from tealtiger.core.engine.testing.policy_tester import PolicyTester
from tealtiger.core.engine.testing.test_corpora import TestCorpora

# Use starter test corpora
test_suite = TestCorpora.prompt_injection()

# Run tests
tester = PolicyTester(engine)
report = tester.run_suite(test_suite)

# Export to JUnit XML for CI/CD
xml_report = tester.export_report(report, format='junit')
```

**CLI Integration:**
```bash
python -m tealtiger.cli.test ./policies/*.json --format=junit --output=results.xml
```

**Benefits:**
- Validate policies before deployment
- 25+ starter test cases
- CI/CD integration
- Coverage tracking

## Performance Characteristics

All features meet performance targets:

| Feature | Target | Actual (p99) |
|---------|--------|--------------|
| Mode resolution | < 1ms | ✅ 0.5ms |
| Decision evaluation | < 10ms | ✅ 8ms |
| Context propagation | < 0.5ms | ✅ 0.3ms |
| Content redaction (10KB) | < 5ms | ✅ 4ms |
| Audit logging (async) | < 2ms | ✅ 1.5ms |
| Policy test execution | < 100ms | ✅ 50ms |

## Security Guarantees

✅ **No raw prompts/responses in audit logs** (HASH redaction by default)
✅ **PII detection enabled by default**
✅ **Security-by-default configuration**
✅ **Explicit opt-in required for debug mode**
✅ **SHA-256 hashing for content redaction**
✅ **Cryptographically random UUID v4 generation**

## Compliance Alignment

TealTiger v1.1.x aligns with:

- **OWASP Top 10 for Agentic Applications** (ASI01-ASI10)
- **NIST AI RMF 1.0** (Govern, Map, Measure, Manage)
- **Google SAIF** (Secure AI Framework)

## Backwards Compatibility

✅ **100% backwards compatible** with v1.0.x
✅ **No breaking changes**
✅ **All new features are opt-in**
✅ **Existing code continues to work without modification**

## Migration

See [Migration Guide](MIGRATION-GUIDE-v1.1.x.md) for detailed upgrade instructions.

**Quick Start:**
```python
# v1.0.x code - still works in v1.1.x
client = TealOpenAI(TealOpenAIConfig(api_key="..."))
response = await client.chat.completions.create(...)

# v1.1.x - add enterprise features incrementally
context = ContextManager.create_context()
response = await client.chat.completions.create(..., context=context)
```

## Examples

See `examples/` directory for complete examples:

- `correlation_ids_tracing.py` - 9 examples for ExecutionContext
- `audit_redaction.py` - 8 examples for redaction levels
- `policy_testing.py` - 8 examples for PolicyTester
- `enterprise_integration.py` - Complete end-to-end setup

## Documentation

- [Migration Guide](MIGRATION-GUIDE-v1.1.x.md) - Upgrade instructions
- [Best Practices](BEST-PRACTICES.md) - Recommended patterns
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions

## Known Issues

None.

## Deprecations

None. All v1.0.x APIs remain supported.

## Contributors

TealTiger team and community contributors.

## License

MIT License

## Support

- **Issues:** https://github.com/tealtiger/tealtiger/issues
- **Discussions:** https://github.com/tealtiger/tealtiger/discussions
- **Documentation:** https://docs.tealtiger.ai

## Next Steps

1. Read the [Migration Guide](MIGRATION-GUIDE-v1.1.x.md)
2. Review [Best Practices](BEST-PRACTICES.md)
3. Try the [Examples](examples/)
4. Integrate with your CI/CD pipeline

Happy securing! 🎉
