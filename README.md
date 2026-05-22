<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/logo/tealtiger-logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset=".github/logo/tealtiger-logo-light.png">
    <img alt="TealTiger Logo" src=".github/logo/tealtiger-logo-light.png" width="200">
  </picture>
  
  # TealTiger Python SDK

  > The first open-source AI agent security SDK with **client-side guardrails** 🛡️

  [![PyPI version](https://badge.fury.io/py/tealtiger.svg)](https://pypi.org/project/tealtiger/)
  [![Python versions](https://img.shields.io/pypi/pyversions/tealtiger.svg)](https://pypi.org/project/tealtiger/)
  [![Tests](https://github.com/agentguard-ai/tealtiger-python/actions/workflows/test.yml/badge.svg)](https://github.com/agentguard-ai/tealtiger-python/actions/workflows/test.yml)
  [![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
  [![Documentation](https://img.shields.io/badge/docs-docs.tealtiger.ai-teal)](https://docs.tealtiger.ai)
  [![v1.3.0](https://img.shields.io/badge/version-v1.3.0-teal.svg)](https://pypi.org/project/tealtiger/)
  [![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da?logo=discord&logoColor=white)](https://discord.gg/X2ePf8QAj)
</div>

> 📖 **[Read the introduction blog post](https://dev.to/nagasatish_chilakamarti_2/introducing-tealtiger-ai-security-cost-control-made-simple-4lma)** | 📚 **[Documentation](https://docs.tealtiger.ai)**

## What's New in v1.3.0 — Autonomous Agent Governance

TealTiger v1.3 introduces **cryptographically verifiable governance** for autonomous AI agents with 7 new modules:

- **TealEngineV13** — Pre/post evaluation pipeline with FREEZE rules, automation levels, NHI verification
- **TealProof** — Cryptographic governance receipts (Merkle trees + RFC 3161 timestamping)
- **TealFlow** — Declarative YAML governance workflows with org-level inheritance
- **TealClassifier** — Local ONNX-based ML inference for content classification (≤20ms)
- **TealDrift** — Behavioral drift detection with statistical baselines
- **TealState** — Context size governance with provenance metadata
- **TealTemporal** — Session TTL, cooldown periods, time-of-day restrictions
- **TealMonitor v2** — Governance-owned cost ceilings, anomaly detection, reasoning-token budgets
- **OWASP Agentic Top 10 Policy Pack** — Zero-config governance for all 10 ASI risks
- **Platform Adapters** — AWS Bedrock Agents, AWS AgentCore, Azure AI Agent Service
- **12 LLM Providers** — Added DeepSeek, Groq, Together AI, HuggingFace TGI, xAI

```bash
pip install tealtiger==1.3.0
```
- **GovernanceDashboard** — Governance visibility UI
- **BundleExporter** — Evidence export in SARIF v2.1.0, JUnit XML, and JSON
- **Docker Sidecar** — Language-agnostic governance via `POST /evaluate` over HTTP

```bash
# Three ways to use TealTiger v1.2
npm install tealtiger                                              # TypeScript
pip install tealtiger                                              # Python
docker run -p 8080:8080 tealtigeradmin/tealtiger-typescript:1.2    # Any language
```

## 🚀 Quick Start

```bash
pip install tealtiger
```

```python
import asyncio
from tealtiger import (
    TealOpenAI,
    TealOpenAIConfig,
    GuardrailEngine,
    PIIDetectionGuardrail,
    PromptInjectionGuardrail,
)

async def main():
    # Set up guardrails
    engine = GuardrailEngine()
    engine.register_guardrail(PIIDetectionGuardrail())
    engine.register_guardrail(PromptInjectionGuardrail())

    # Create a guarded provider client using the canonical Python client API.
    config = TealOpenAIConfig(
        api_key="your-openai-key",
        agent_id="my-agent",
        guardrail_engine=engine,
        enable_cost_tracking=False,
    )
    client = TealOpenAI(config)

    response = await client.chat.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}]
    )

    print(response.choices[0]["message"]["content"])
    print(f"Guardrails passed: {response.security.guardrail_result.passed}")

asyncio.run(main())
```

Provider clients from `tealtiger.clients` are the canonical public API for LLM calls and are also re-exported from `tealtiger`. The `TealTiger` class remains the sidecar/tool-execution client for policy evaluation workflows, not the provider-call API.

## Async/Await Usage

The Python SDK exposes async methods for provider calls and guardrail execution. Initialize clients inside your async application, then `await` each API call.

```python
import asyncio
from tealtiger.clients import TealOpenAI, TealOpenAIConfig


async def main():
    config = TealOpenAIConfig(
        api_key="your-openai-key",
        enable_guardrails=True,
        enable_cost_tracking=False,
    )
    client = TealOpenAI(config)

    response = await client.chat.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}],
    )

    print(response.choices[0]["message"]["content"])


asyncio.run(main())
```

Use an async context manager when you want the SDK to close the underlying async HTTP client automatically.

```python
import asyncio
from tealtiger.clients import TealOpenAI, TealOpenAIConfig


async def main():
    config = TealOpenAIConfig(
        api_key="your-openai-key",
        enable_guardrails=True,
    )

    async with TealOpenAI(config) as client:
        response = await client.chat.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0]["message"]["content"])


asyncio.run(main())
```

## 🌐 Supported Providers

95%+ market coverage with 7 LLM providers:

| Provider | Client | Primary method | Models | Features |
|----------|--------|----------------|--------|----------|
| **OpenAI** | `TealOpenAI` | `client.chat.create()` | GPT-4, GPT-3.5 Turbo | Chat, Completions, Embeddings |
| **Anthropic** | `TealAnthropic` | `client.messages.create()` | Claude 3, Claude 2 | Chat, Streaming |
| **Google** | `TealGemini` | `client.generate_content()` | Gemini Pro, Ultra | Multimodal, Safety Settings |
| **AWS** | `TealBedrock` | `client.invoke_model()` | Claude, Titan, Jurassic, Command, Llama | Multi-model, Regional |
| **Azure** | `TealAzureOpenAI` | `client.chat.completions.create()` | GPT-4, GPT-3.5 | Deployment-based, Azure AD |
| **Mistral** | `TealMistral` | `client.chat()` | Large, Medium, Small, Mixtral | EU Data Residency, GDPR |
| **Cohere** | `TealCohere` | `client.chat()` / `client.embed()` | Command, Embed | RAG, Citations, Connectors |

## 🛡️ Key Features

### TealEngine — Policy Evaluation

Deterministic policy evaluation with multi-mode enforcement:

```python
from tealtiger import TealEngine, PolicyMode, DecisionAction, ReasonCode

engine = TealEngine(
    policies=my_policies,
    mode={
        "default_mode": PolicyMode.ENFORCE,       # or MONITOR, REPORT_ONLY
        "policy_modes": {
            "tools.file_delete": PolicyMode.ENFORCE,
            "identity.admin_access": PolicyMode.ENFORCE
        }
    }
)

decision = engine.evaluate({
    "agent_id": "agent-001",
    "action": "tool.execute",
    "tool": "file_delete",
    "correlation_id": "req-12345"
})

if decision.action == DecisionAction.ALLOW:
    await execute_tool()
elif decision.action == DecisionAction.DENY:
    if ReasonCode.TOOL_NOT_ALLOWED in decision.reason_codes:
        raise ToolNotAllowedError(decision.reason)
elif decision.action == DecisionAction.REQUIRE_APPROVAL:
    await request_approval(decision)

# Risk-based routing
if decision.risk_score > 80:
    await escalate_to_human(decision)
```

**Decision fields:** `action` (ALLOW, DENY, REDACT, TRANSFORM, REQUIRE_APPROVAL, DEGRADE), `reason_codes` (standardized enums), `risk_score` (0-100), `correlation_id`, `metadata`

### TealGuard — Security Guardrails

Client-side guardrails that run in milliseconds with no server dependency:

```python
from tealtiger import GuardrailEngine, PIIDetectionGuardrail, PromptInjectionGuardrail, ContentModerationGuardrail

engine = GuardrailEngine(mode="parallel", timeout=5000)

engine.register_guardrail(PIIDetectionGuardrail(action="redact"))
engine.register_guardrail(PromptInjectionGuardrail(sensitivity="high"))
engine.register_guardrail(ContentModerationGuardrail(threshold=0.7))

result = await engine.execute(user_input)
print(f"Passed: {result.passed}")
print(f"Risk Score: {result.risk_score}")
```

**Detects:** PII (emails, phones, SSNs, credit cards), prompt injection, jailbreaks, harmful content, custom patterns.

### TealCircuit — Circuit Breaker

Cascading failure prevention with automatic failover:

```python
from tealtiger import TealCircuit

circuit = TealCircuit(
    failure_threshold=5,
    reset_timeout=30000,
    monitor_interval=10000
)

# Wraps provider calls with circuit breaker protection
response = await circuit.execute(
    lambda: client.chat.create(model="gpt-4", messages=messages)
)
```

### TealAudit — Audit Logging & Redaction

Versioned audit events with security-by-default PII redaction:

```python
from tealtiger import TealAudit, RedactionLevel, FileOutput

audit = TealAudit(
    outputs=[FileOutput("./audit.log")],
    config={
        "input_redaction": RedactionLevel.HASH,    # SHA-256 hash + size (default)
        "output_redaction": RedactionLevel.HASH,
        "detect_pii": True,
        "debug_mode": False
    }
)
```

**Redaction levels:** HASH (default, production-safe), SIZE_ONLY, CATEGORY_ONLY, FULL, NONE (debug only).

### Correlation IDs & Traceability

End-to-end request tracking across all components:

```python
from tealtiger import ContextManager

context = ContextManager.create_context(
    tenant_id="acme-corp",
    app="customer-support",
    env="production"
)

# Context propagates through TealEngine, TealAudit, and all providers
response = await client.chat.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    context=context
)

# Query audit logs by correlation_id
events = await audit.query(correlation_id=context.correlation_id)
```

**Features:** Auto-generated UUID v4 correlation IDs, OpenTelemetry-compatible trace IDs, HTTP header propagation, multi-tenant support.

### Policy Test Harness

Validate policy behavior before production deployment:

```python
from tealtiger import PolicyTester, TestCorpora

tester = PolicyTester(engine)
report = tester.run_suite({
    "name": "Customer Support Policy Tests",
    "tests": [
        {
            "name": "Block file deletion",
            "context": {"agent_id": "support-001", "action": "tool.execute", "tool": "file_delete"},
            "expected": {"action": DecisionAction.DENY, "reason_codes": [ReasonCode.TOOL_NOT_ALLOWED]}
        },
        *TestCorpora.prompt_injection(),
        *TestCorpora.pii_detection()
    ]
})

print(f"Tests: {report.passed}/{report.total} passed")
```

```bash
# CLI usage
python -m tealtiger.cli.test ./policies/*.test.json --coverage --format=junit --output=./results.xml
```

### Cost Tracking & Budget Management

Track costs across 50+ models and enforce spending limits:

```python
from tealtiger import CostTracker, BudgetManager, InMemoryCostStorage

storage = InMemoryCostStorage()
tracker = CostTracker()
budget_manager = BudgetManager(storage)

budget_manager.create_budget({
    "name": "Daily GPT-4 Budget",
    "limit": 10.0,
    "period": "daily",
    "alert_thresholds": [50, 75, 90, 100],
    "action": "block",
    "enabled": True
})

# Estimate before request
estimate = tracker.estimate_cost("gpt-4", {"input_tokens": 1000, "output_tokens": 500}, "openai")

# Check budget
check = await budget_manager.check_budget("agent-123", estimate)
if not check.allowed:
    print(f"Blocked by: {check.blocked_by.name}")
```

## 🛡️ OWASP Top 10 for Agentic Applications Coverage

TealTiger v1.2.0 covers **7 out of 10** OWASP ASIs through its SDK-only architecture:

| ASI | Vulnerability | Coverage | Components |
|-----|--------------|----------|------------|
| ASI01 | Goal Hijacking & Prompt Injection | 🟡 Partial | TealGuard, TealEngine |
| ASI02 | Tool Misuse & Unauthorized Actions | 🟢 Full | TealEngine |
| ASI03 | Identity & Access Control Failures | 🟢 Full | TealEngine |
| ASI04 | Supply Chain Vulnerabilities | 🔧 Support | TealAudit |
| ASI05 | Unsafe Code Execution | 🟢 Full | TealEngine |
| ASI06 | Memory & Context Corruption | 🟢 Full | TealEngine, TealGuard |
| ASI07 | Inter-Agent Communication Security | ❌ Platform | N/A |
| ASI08 | Cascading Failures & Resource Exhaustion | 🟢 Full | TealCircuit |
| ASI09 | Harmful Content Generation | 🔧 Support | TealGuard |
| ASI10 | Rogue Agent Behavior | 🟢 Full | TealAudit |

📖 [Complete OWASP ASI Mapping](../../OWASP-AGENTIC-TOP10-TEALTIGER-MAPPING.md) | [OWASP Top 10 for Agentic Applications](https://owasp.org/www-project-top-10-for-agentic-applications/)

## 🎯 Use Cases

- **Customer Support Bots** — Protect customer PII
- **Healthcare AI** — HIPAA compliance
- **Financial Services** — Prevent data leakage
- **E-commerce** — Secure payment information
- **Enterprise AI** — Policy enforcement and audit trails
- **Education Platforms** — Content safety

## 📚 Documentation

- [Full Documentation](https://docs.tealtiger.ai)
- [API Reference](https://docs.tealtiger.ai/api)
- [Examples](https://github.com/agentguard-ai/tealtiger-python-prod/tree/main/examples)
- [Changelog](https://github.com/agentguard-ai/tealtiger-python-prod/blob/main/CHANGELOG.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](https://github.com/agentguard-ai/tealtiger-python-prod/blob/main/CONTRIBUTING.md).

## 📄 License

Apache 2.0 — see [LICENSE](https://github.com/agentguard-ai/tealtiger-python-prod/blob/main/LICENSE)

## 🔗 Links

- **PyPI**: https://pypi.org/project/tealtiger/
- **GitHub**: https://github.com/agentguard-ai/tealtiger
- **TypeScript SDK**: https://www.npmjs.com/package/tealtiger
- **Documentation**: https://docs.tealtiger.ai
- **Discord**: https://discord.gg/X2ePf8QAj
- **LinkedIn**: https://www.linkedin.com/company/tealtiger/
- **X (Twitter)**: https://x.com/TealtigerAI
- **Contact**: reachout@tealtiger.ai
- **Issues**: https://github.com/agentguard-ai/tealtiger/issues

---

**Made with ❤️ by the TealTiger team**
