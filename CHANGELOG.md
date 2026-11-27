# Changelog

All notable changes to the TealTiger Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (behaviour change — read before upgrading)

- **`TealEngine` enforces the tool allowlist.** `evaluate_with_mode()` now returns a real
  decision under `ENFORCE` and `MONITOR` for policies whose rule types this SDK
  implements, where 1.6.0 raised `NotImplementedError` for every policy. A tool
  configured `{"allowed": False}` comes back `DENY` with
  `[POLICY_VIOLATION, TOOL_NOT_ALLOWED]` and `triggering_clause` of
  `tools.<tool>.allowed`; a tool absent from the map comes back `DENY` attributed to
  `tools.<tool>.absent`. **Verified 16/16 against the published conformance corpus
  through the public API**, not only through the evaluator.

  **A policy that configures a rule type this SDK does not implement is refused**, with
  the new `UnsupportedPolicySectionError`. It subclasses `NotImplementedError`, so
  callers that adapted to 1.6.0 keep working, and now see it only for the sections that
  genuinely are not implemented.

  Refusing the whole policy is deliberate. Evaluating the sections the engine understands
  while ignoring the rest would return an `ALLOW` the policy did not earn — the 1.6.0
  defect in a smaller box. §9.2 forbids presenting a rule type as enforced when its
  clause is a no-op, and with a partial implementation the only way to keep that promise
  is to decline. A caller who configured content governance and received `ALLOW` has been
  told their policy was applied.

  `TealEngine.rule_type_support()` publishes the claim per rule type (§9.1), and
  `unenforceable_sections()` answers it for a specific engine's policy **before any
  request**, so the discovery happens at startup rather than on the first denial that
  mattered.

  Mode behaviour now follows §5.4 exactly:

  | Mode | Behaviour |
  |---|---|
  | `ENFORCE` | returns the computed decision unmodified |
  | `MONITOR` | evaluates fully, then returns `ALLOW` **while preserving** the reason codes and `triggering_clause`, so the would-be denial is recorded rather than erased |
  | `REPORT_ONLY` | unchanged — skips evaluation, and therefore honours any policy honestly whatever it contains |

  A `MONITOR` decision is an `ALLOW` that carries a clause. That reads as a
  contradiction and is exactly right: nothing was blocked, and this is the clause that
  would have blocked it.

  **Migration:** an empty or absent policy now **allows** instead of raising, which is
  specified behaviour (§5.3) rather than a gap — a policy that configures nothing has
  nothing to enforce. If you were relying on the 1.6.0 raise as a guard, check
  `unenforceable_sections()` at startup instead.

### Removed

- **`determine_reason_codes`** (module-level in `teal_engine`). It inferred reason codes
  by substring-matching clause paths and human-readable reason text — `if "tools" in
  policy`, `if "blocked" in reason` — so any clause containing `codeExecution` produced
  `UNSAFE_CODE_DETECTED` whether or not any code had been inspected. That is the defect
  class the conformance specification exists to prevent, and §3.6 now makes reason-code
  order part of the contract. The evaluator returns the codes directly, from the branch
  that actually decided.

### Added

- **Tool-allowlist policy evaluation** (`tealtiger.core.engine.policy_evaluator`) —
  the first rule type this SDK actually decides. Implements TA-1 through TA-8 of the
  policy conformance specification §6.2, §5.3 AND aggregation, §4.1 precondition
  handling, and §3.6 determinism. **Passes 16/16 against the published conformance
  corpus**, the same byte-identical suite the TypeScript SDK is scored on.

  Not yet wired into `TealEngine`, which still raises. That is the next change, because
  an engine that decides one rule type must declare per rule type what it enforces
  (§9.1) rather than implying it enforces everything.

  What the requirements amount to:

  - A `tool.execute` request with no `tool` is **malformed input**, reported as
    `request.tool.missing` with `INVALID_REQUEST` — never as `TOOL_NOT_ALLOWED`. A
    client that forgot a field and a governance verdict about a real tool are different
    events (TA-1, §4.1a).
  - An entry configured `allowed: false` denies, attributed to
    `tools.<tool>.allowed` (TA-2).
  - A tool **absent** from the map denies, attributed to `tools.<tool>.absent`.
    Default-deny is normative (TA-4), and the two denials are distinguishable by clause
    alone because they are different policy facts (TA-5).
  - Tool names match **exactly**: `Search`, `FILE_DELETE` and `search ` are three
    different tools from `search`, and each is denied as absent rather than quietly
    matched (TA-6).
  - An **absent** `tools` section and a present but **empty** `tools: {}` are not the
    same thing. Absent means no tool policy is configured; `{}` is an allowlist that
    permits nothing. Collapsing them would mean a misconfiguration producing an empty
    map silently permits every tool (TA-7).
  - `*` is a **fallback entry**, not a pattern. A specific entry always wins, and a
    denial inherited from the fallback reports `tools.*.allowed` so an operator can tell
    a blanket default from a rule somebody wrote about that tool (TA-8).

  Sections the evaluator does not implement are **reported, not ignored**:
  `evaluate_policies` returns the unevaluated section names alongside the outcome. An
  evaluator that silently allowed what it had not implemented would be the 1.6.0 defect
  in a smaller box.

  A malformed `allowed` value — absent, or not a boolean — **raises** rather than
  deciding. §6.1 requires a boolean and does not say what to do otherwise, and both
  silent readings are bad: denying turns a typo into an outage attributed to a clause the
  author believes says `true`, and allowing turns a typo into silent non-enforcement.
  Recorded as a specification gap.

- **`Decision.triggering_clause`** — the dotted path of the clause that produced a
  decision, for example `tools.file_delete.allowed`. Required by the policy conformance
  specification §3.5, where it is the *anti-vacuity* requirement: a correct verdict is not
  evidence of correct governance. In the cross-run that produced that specification, all
  13 unsafe-code cases returned the expected `DENY` with the expected
  `UNSAFE_CODE_DETECTED`, and all 13 were produced by a language precondition rather than
  by inspecting any code. Without this field a test suite can be entirely vacuous and
  still report as healthy.

  Defaulted to `"none"` rather than required, so no existing caller breaks. `"none"` is
  also the specified value for an allow under an empty or absent policy (§5.3).

  **A decision whose action is not `ALLOW` may not report `"none"`.** This is enforced by
  a model validator rather than left to each call site, so no future code path can
  produce an unattributed denial: a `DENY` attributed to nothing asserts that something
  was refused while recording nothing about what refused it. The rule covers `REDACT`,
  `TRANSFORM`, `REQUIRE_APPROVAL` and `DEGRADE` as well — each changes what happens to the
  request, so each must say what decided that.

  Populated by the components that produce decisions today, following the namespacing
  their `policy_id` values already use:

  - `TealGuard` — `guardrail.<name>` of the guardrail that failed, or the policy's own
    clause when a policy decision supplied the action
  - `TealCircuit` — `circuit.open`
  - `TealEngine` under `REPORT_ONLY` — `"none"`, which is honest: that mode consults no
    clause

  `CLAUSE_NONE` and `CLAUSE_UNKNOWN` are exported from `tealtiger.core.engine` for callers
  that construct decisions.

  Groundwork for tool-allowlist enforcement in this SDK, which cannot pass a single
  conformance case without it: corpus validity rule CV-2 requires every case to assert
  that the decision's `triggering_clause` equals the clause the case targets.

### Fixed

- The `MockEngine` fixture in the policy-tester tests returned a `DENY` with no clause,
  which the new validator rejects. It now reports `tools.file_delete.allowed`, the clause
  TA-2 specifies for an entry configured `allowed: false`. `policy_id` was already
  `tools.file_delete`, which is a different fact: it says which policy decided, not which
  line of it.

## [1.6.1] - 2026-11-15

Documentation only. No code change; the package behaves exactly as 1.6.0.

### Fixed

- **The README shipped with 1.6.0 still said "What's New in v1.5.0"** and carried a
  hardcoded `v1.5.0` version badge. PyPI renders the README as the project description and
  **freezes it per release**, so the 1.6.0 project page advertises the previous release's
  highlights and omits the breaking change that release exists to deliver. A project
  description cannot be edited after upload, so correcting it requires a new version — this
  one.

  The rest of the 1.6.0 README was accurate: the `TealEngine` section and the OWASP ASI
  table were corrected in that release and are unchanged here. What was missed is the
  "What's New" section and the badge, neither of which `twine check --strict` inspects — it
  verifies that the description *renders*, not that it is *current*.

- **Removed the hardcoded version badge** rather than bumping it. It duplicated the
  dynamic PyPI version badge immediately above it, which reads the real version from the
  registry and cannot go stale. One source for the version, like `pyproject.toml` is for
  the package itself.

## [1.6.0] - 2026-11-15

### Changed (behaviour change — read before upgrading)

- **`TealEngine.evaluate_with_mode()` now raises `NotImplementedError` under
  `PolicyMode.ENFORCE` and `PolicyMode.MONITOR`.** `TealEngine._evaluate_policies()`
  returned `{"allowed": True}` unconditionally and never read `self.policies`, so every
  request was permitted: a tool configured `{"allowed": False}`, prompt injection, PII,
  `os.system('rm -rf /')`, and any cost above any limit. It produced no denials under any
  policy while reporting `POLICY_COMPLIANT` and a risk score of 0.

  This is the same defect `PolicyTester.test_policy()` had in 1.5.0, one layer down, and
  gets the same treatment: a governance API that silently permits is worse than one that
  is absent, because it manufactures the appearance of a control.

  `PolicyMode.REPORT_ONLY` is unaffected and still returns a `Decision`. That mode's
  contract is that evaluation is skipped, which this engine can honour honestly.

  **Migration:** use the guardrails (`PIIDetectionGuardrail`,
  `PromptInjectionGuardrail`, `ContentModerationGuardrail`) for content governance,
  `observe()` for provider instrumentation and cost tracking, `freeze()` as a kill
  switch, `TealCircuit` for failure isolation, and the TypeScript SDK for tool-allowlist
  enforcement, which is verified against the shared conformance corpus. Python policy
  evaluation is scheduled for implementation against the published conformance
  specification.

  No caller could have been relying on a correct result, so no correct behaviour breaks.

### Fixed

- **Two tests that could fail against correct code.**
  - `test_update_budget` asserted `updated_at != created_at` across two real
    `datetime.utcnow()` calls microseconds apart. The Windows system clock ticks roughly
    every 15.6ms, so both calls returned the same instant and the test failed on a correct
    implementation. The clock is now pinned to two known instants, which also makes the
    assertion exact: `update_budget` must write the second one and leave `created_at` alone.
  - `test_wildcard_freeze_unfreeze_round_trip` asserted that an individually frozen agent
    survives a `freeze("*")`/`unfreeze("*")` round trip, but its `st.text(min_size=1)`
    strategy eventually generates `"*"` itself. `freeze("*")` sets the wildcard flag and
    adds nothing to the frozen set, so for that input there is no individual freeze to
    preserve. The sentinel is now excluded from the property and its actual semantics are
    pinned in explicit cases instead.
- **Removed a hardcoded absolute path from the test suite.** `tests/test_observe_properties.py`
  began with a `sys.path.insert` pointing into a OneDrive folder belonging to a different
  checkout (`tealtiger-python`, not this repository). It was a no-op in CI, where the path
  does not exist, but locally it could shadow the package under test with a stale copy.
- **Corrected the README's OWASP ASI coverage claims.** The table claimed 7 of 10
  categories covered, with 🟢 Full coverage of ASI02 (tool misuse), ASI03 (identity and
  access control) and ASI05 (unsafe code execution) attributed to `TealEngine`, which
  governs nothing. Those three rows are now marked not implemented, `TealEngine` is
  removed from ASI01 and ASI06, and the headline reads 2 of 10 with full coverage. The
  `TealEngine` feature section no longer documents an `evaluate()` method that does not
  exist or a `mode` dict that raises `AttributeError` in the constructor.

## [1.5.0] - 2026-10-03

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

## [1.4.0] - 2026-06-15

### Added — observe() Zero-Config Instrumentation
- **`observe()`** — Single-function wrapper that instruments any supported LLM client with cost tracking, audit logging, behavioral baselines, and PII detection. Zero configuration required.
- **12-provider support** — Auto-detects OpenAI, Anthropic, Gemini, Bedrock, Azure OpenAI, Cohere, Mistral, DeepSeek, Groq, xAI, Together, and HF-TGI via duck-typing.
- **`freeze()` / `unfreeze()`** — Instant kill switch that blocks all requests to a specific agent (or all agents with `'*'`).
- **Behavioral baseline** — Computes P50/P95/P99 percentiles for latency, token counts, cost, and tool call frequency from the first N requests.
- **PII detection (REPORT_ONLY)** — Scans request/response payloads for email, phone, SSN, and credit card patterns without blocking.
- **Structured audit logging** — Every request/response/error/tool-call produces a typed event with correlation IDs and HASH redaction.
- **Sync + async support** — Automatically detects and wraps both sync and async provider methods.

## [1.3.0] - 2026-05-18

> **Undocumented.** Published to PyPI on 2026-05-18 with no changelog entry and no git
> tag. Contents were not reconstructed; the commit range between `v1.2.0` and the 1.4.0
> release commit (`107fb3e`) is the only available record.

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

[Unreleased]: https://github.com/agentguard-ai/tealtiger-python-prod/compare/v1.6.1...HEAD
[1.6.1]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.6.1
[1.6.0]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.6.0
[1.5.0]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.5.0
[1.2.0]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.2.0
[1.1.1]: https://github.com/agentguard-ai/tealtiger-python-prod/releases/tag/v1.1.1
[1.1.0]: https://github.com/agentguard-ai/tealtiger-python-staging/releases/tag/v1.1.0
[0.2.2]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.2
[0.2.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.2.0
[0.1.1]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.1
[0.1.0]: https://github.com/agentguard-ai/agentguard-python/releases/tag/v0.1.0
