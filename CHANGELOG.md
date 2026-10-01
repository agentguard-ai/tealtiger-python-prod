# Changelog

All notable changes to the TealTiger Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.5.0] - unreleased

### Added
- **`PolicyHotSwapManager`** (`tealtiger.core.engine.v1_3`) — runtime validation and
  hot-swapping of governance policy bundles, ported from the TypeScript core's
  `src/core/engine/v1.3/policy-hotswap.ts`. Provides `validate_bundle()` (schema,
  integrity hash, capability negotiation, signature), `load_policy()`
  (validate-then-swap, retaining the previous bundle on failure),
  `compute_bundle_hash()`, and event emission with listener isolation.
- **FREEZE rule accumulation** — rules persist across hot-swaps and are never removed
  by a bundle that omits them.
- Bundle hashes are **byte-compatible with the TypeScript core**. Verified by computing
  the digest for an identical bundle in both languages; the digest is pinned in
  `test_bundle_hash_matches_typescript_core` so interop cannot regress silently.

### Changed (behaviour change — read before upgrading)
- **`PolicyTester.test_policy()` now raises `NotImplementedError`.** It previously
  returned `decision="allow"` for every input, including policies whose rules denied
  the request — a published governance API handing out unconditional passes. It never
  evaluated the policy it was given.

  Technically this is a breaking change, but no caller could have been relying on a
  correct result. **Migration:** use `PolicyTestRunner`
  (`tealtiger.core.engine.testing.PolicyTester`, re-exported under a clearer name),
  which was already exported and evaluates test cases against a real engine:

  ```python
  from tealtiger import PolicyTestRunner
  runner = PolicyTestRunner(engine)
  report = runner.run_suite(suite)
  ```

### Fixed
- Cleared ~1,000 accumulated `ruff` findings across 76 files; `ruff check src tests`
  now passes. Three were fixed by hand so those rules stay active repo-wide rather than
  being globally disabled for one instance each.
- **Pinned `ruff` to `>=0.15,<0.16`.** The previous open-ended `>=0.0.285` floor meant
  CI silently adopted every new ruff release and its new default rules, so the lint gate
  drifted stricter over time without anyone changing it — which is how those findings
  accumulated while the job was nominally green.
- `C901` complexity is now ratcheted at `max-complexity = 34` (the current worst
  function) rather than disabled, so nothing can get worse. `B904` and `F841` are
  deferred with counts recorded in `pyproject.toml`.

### Repository metadata
- Corrected the CI badge and issue links, which pointed at
  `agentguard-ai/tealtiger-python` and `agentguard-ai/tealtiger` — neither of which
  exists. The source repository is `agentguard-ai/tealtiger-python-prod`.
- Replaced a relative link to the OWASP mapping that resolved to nothing when rendered
  on PyPI.

## [1.4.1] - 2026-09-12

> **Reconstructed after the fact.** This release was published to PyPI on 2026-09-12
> but left no record in this repository: no git tag, no GitHub Release, no version bump
> on `main` (which still read `1.4.0` until 1.5.0), and no changelog entry. The content
> below is inferred from the commits immediately preceding the upload and should be
> treated as the best available account rather than an authoritative one.
>
> See "Release process" in the 1.5.0 notes above for why this could happen.

### Fixed
- Exported `TealEngine`, `TealGuard`, `TealAudit` and `TealCircuit` at the package top
  level (PR #29, merged 2026-09-10) — previously these required importing from their
  submodules.

## [1.3.0] - 2026-05-18

> **Undocumented.** Published to PyPI on 2026-05-18 with no changelog entry and no git
> tag. Contents were not reconstructed; the commit range between `v1.2.0` and the 1.4.0
> release commit (`107fb3e`) is the only available record.

## [1.4.0] - 2026-06-15

### Added — observe() Zero-Config Instrumentation
- **`observe()`** — Single-function wrapper that instruments any supported LLM client with cost tracking, audit logging, behavioral baselines, and PII detection. Zero configuration required.
- **12-provider support** — Auto-detects OpenAI, Anthropic, Gemini, Bedrock, Azure OpenAI, Cohere, Mistral, DeepSeek, Groq, xAI, Together, and HF-TGI via duck-typing.
- **`freeze()` / `unfreeze()`** — Instant kill switch that blocks all requests to a specific agent (or all agents with `'*'`).
- **Behavioral baseline** — Computes P50/P95/P99 percentiles for latency, token counts, cost, and tool call frequency from the first N requests.
- **PII detection (REPORT_ONLY)** — Scans request/response payloads for email, phone, SSN, and credit card patterns without blocking.
- **Structured audit logging** — Every request/response/error/tool-call produces a typed event with correlation IDs and HASH redaction.
- **Sync + async support** — Automatically detects and wraps both sync and async provider methods.

## [1.2.0] - 2026-05-04

### Added — Governance Bundle
- **Governance Sidecar** — HTTP server for language-agnostic governance (`POST /evaluate`, `/validate`, `/scan`, `GET /health`, `/ready`)
- **Lazy imports** — Faster cold starts with deferred provider client loading in `clients/__init__.py`
- **Enhanced TealBedrock** — Updated Bedrock client with v1.2 governance integration
- **Dockerfile.sidecar** — Docker image for Python governance sidecar

### Fixed
- Cost types alignment with TypeScript SDK

### Changed
- Version bumped to 1.2.0
- README updated with v1.2.0 governance bundle features

## [1.1.1] - 2026-04-03

### Fixed
- README rewritten to accurately reflect all features included in v1.1.0
- Removed misleading "Enterprise Feature Comparison" table that incorrectly suggested v1.1.0 had fewer features than a non-existent "v1.1.x Enterprise"
- Removed "What's New in v0.2.0" section
- Removed merge conflict markers
- Removed old URLs (tealtiger.co.in)

### Changed
- License updated from MIT to Apache 2.0 across all files (LICENSE, pyproject.toml classifier, README badges)
- All enterprise features (TealEngine, TealGuard, TealCircuit, TealAudit, correlation IDs, policy testing) now correctly presented as included v1.1.0 features

### Notes
- **No code changes** — documentation and metadata only
- Fully backward compatible with v1.1.0

## [1.1.0] - 2026-03-15

### Added
- **TealEngine** — Deterministic policy evaluation with multi-mode enforcement (ENFORCE, MONITOR, REPORT_ONLY)
- **TealGuard** — Client-side security guardrails (PII detection, prompt injection, content moderation)
- **TealCircuit** — Circuit breaker for cascading failure prevention
- **TealAudit** — Versioned audit logging with security-by-default PII redaction
- **Correlation IDs** — Auto-generated UUID v4 with OpenTelemetry-compatible trace IDs
- **Decision Contract** — Deterministic typed Decision object with risk scores and reason codes
- **Policy Test Harness** — CLI/library test runner with JUnit XML export for CI/CD
- **Multi-Provider Support** — 7 providers (OpenAI, Anthropic, Gemini, Bedrock, Azure OpenAI, Cohere, Mistral)
- **OWASP Coverage** — 7/10 ASIs covered with SDK-only architecture

## [0.2.2] - 2026-01-31

### Added
- **Cost Tracking & Budget Management** - Complete feature parity with TypeScript SDK v0.2.2
  - `CostTracker` - Track AI model costs across OpenAI, Anthropic, and Azure OpenAI
  - `BudgetManager` - Create and enforce budgets with alerts and blocking
  - `InMemoryCostStorage` - Store and query cost records
  - Support for 20+ AI models with accurate pricing
  - Custom pricing support for proprietary models
  - Budget periods: hourly, daily, weekly, monthly, total
  - Alert thresholds with severity levels (info, warning, critical)
  - Agent-scoped budgets for multi-agent systems
  
- **Guarded AI Clients** - Drop-in replacements with integrated security
  - `GuardedOpenAI` - Secure OpenAI client with guardrails and cost tracking
  - `GuardedAnthropic` - Secure Anthropic client with guardrails and cost tracking
  - `GuardedAzureOpenAI` - Secure Azure OpenAI client with deployment mapping
  - Automatic input/output guardrail execution
  - Pre-request budget checking and enforcement
  - Automatic cost calculation and recording
  - Security metadata in all responses
  
- **Example Scripts** - Comprehensive demos for all new features
  - `cost_tracking_demo.py` - Cost estimation and tracking examples
  - `budget_management_demo.py` - Budget creation and enforcement examples
  - `guarded_openai_demo.py` - GuardedOpenAI usage examples
  - `guarded_anthropic_demo.py` - GuardedAnthropic usage examples
  - `guarded_azure_openai_demo.py` - GuardedAzureOpenAI usage examples

### Features
- **Multi-Provider Support**: OpenAI, Anthropic, Azure OpenAI
- **Accurate Pricing**: Real-time cost calculation for 20+ models
- **Budget Enforcement**: Block requests that exceed budgets
- **Alert System**: Configurable thresholds with severity levels
- **Agent Isolation**: Separate budgets per agent
- **Cost Queries**: Query costs by agent, date range, request ID
- **Custom Pricing**: Override pricing for custom models
- **Deployment Mapping**: Azure deployment names to model names
- **Security Integration**: Guardrails + cost tracking in one client

### Performance
- Async-first design for all operations
- Efficient in-memory storage with O(1) lookups
- Parallel guardrail execution
- < 10ms cost calculation overhead

### Documentation
- Updated README with cost tracking and guarded clients sections
- Added 5 comprehensive example scripts
- Full API documentation for all new classes
- Migration guide from v0.2.0

### Dependencies
- Added `openai>=1.0.0` for GuardedOpenAI and GuardedAzureOpenAI
- Added `anthropic>=0.18.0` for GuardedAnthropic
- Added `hypothesis>=6.0.0` for property-based testing (dev)

### Testing
- 71+ new tests for cost tracking and guarded clients
- Property-based tests for correctness validation
- Integration tests for end-to-end workflows
- 61% overall test coverage (focused on new features)

### Notes
- **Feature Parity**: Python SDK now matches TypeScript SDK v0.2.2
- **Breaking Changes**: None - fully backward compatible
- **Migration**: Existing code continues to work without changes

## [0.2.0] - 2026-01-30

### Added
- **Client-Side Guardrails** - Offline security protection without server dependency
  - `GuardrailEngine` for parallel/sequential guardrail execution
  - `PIIDetectionGuardrail` - Detect and redact PII (emails, phones, SSNs, credit cards)
  - `ContentModerationGuardrail` - Detect harmful content (hate, violence, harassment)
  - `PromptInjectionGuardrail` - Detect jailbreak and injection attempts
  - Configurable actions: block, allow, redact, mask, transform
  - Timeout protection and error handling with asyncio
  - Pydantic models for type safety
- Comprehensive test suite for guardrails (50 tests passing)
- Guardrails demo example with real-world scenarios
- Full async/await support for all guardrail operations

### Features
- **Offline Capability**: Run guardrails without network calls
- **Parallel Execution**: Execute multiple guardrails simultaneously with asyncio
- **Flexible Actions**: Block, redact, mask, or transform risky content
- **Risk Scoring**: Quantify security risks (0-100 scale)
- **Pattern Detection**: Regex-based detection with high accuracy
- **OpenAI Integration**: Optional OpenAI Moderation API support
- **Type Safety**: Full Pydantic models for all guardrail results

### Performance
- < 50ms guardrail execution (parallel mode)
- Configurable timeouts per guardrail
- Efficient pattern matching with compiled regex
- Async-first design for high concurrency

### Documentation
- Added guardrails usage examples
- Updated README with guardrails showcase
- Added inline documentation for all guardrail classes

## [0.1.1] - 2026-01-29

### Fixed
- Package name changed to `agentguard-sdk` (from `agentguard`) due to PyPI name conflict
- Updated all imports and documentation

### Added
- Published to PyPI as `agentguard-sdk`
- GitHub repository: https://github.com/agentguard-ai/agentguard-python

## [0.1.0] - 2026-01-28

### Added
- Initial release of AgentGuard Python SDK
- Core security evaluation functionality
- Tool execution with security decisions (allow/deny/transform)
- Security Sidecar Agent (SSA) HTTP client
- Configuration management with validation
- Comprehensive error handling with custom exceptions
- Audit trail functionality
- Policy validation and management
- Full async/await support
- Type hints throughout the codebase
- Comprehensive test suite with pytest
- Examples for basic and advanced usage
- Complete API documentation

### Features
- **Security Evaluation**: Evaluate tool calls before execution
- **Policy Enforcement**: Automatic policy-based decision making
- **Request Transformation**: Safe transformation of risky operations
- **Audit Trail**: Complete audit logging for compliance
- **Performance**: < 100ms security evaluation overhead
- **Type Safety**: Full type hints with Pydantic models
- **Async Support**: Built-in async/await for modern Python

### Security
- API key authentication with SSA
- Input validation and sanitization
- Secure HTTP communication with httpx
- Error handling that doesn't leak sensitive information

### Developer Experience
- Comprehensive documentation with examples
- Type hints for better IDE support
- Pytest test suite with 100% core functionality coverage
- Examples for common integration patterns
- Poetry and pip support

[Unreleased]: https://github.com/agentguard-ai/tealtiger-python-prod/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.2.0
[1.1.1]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.1.1
[1.1.0]: https://github.com/agentguard-ai/tealtiger-python-staging/releases/tag/v1.1.0
[0.2.2]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.2
[0.2.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.0
[0.1.1]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.1
[0.1.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.0
