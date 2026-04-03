# Changelog

All notable changes to the TealTiger Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/agentguard-ai/tealtiger-python-staging/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/agentguard-ai/tealtiger-python-staging/releases/tag/v1.1.1
[1.1.0]: https://github.com/agentguard-ai/tealtiger-python-staging/releases/tag/v1.1.0
[0.2.2]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.2
[0.2.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.0
[0.1.1]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.1
[0.1.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.0
