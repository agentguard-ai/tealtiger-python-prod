"""TealTiger Python SDK - Enterprise-grade security for AI agents."""

# v1.4: observe() — Zero-Config Entry Point
from tealtiger.client import TealTiger

# Guarded AI clients
from tealtiger.clients import (
    TealAnthropic,
    TealAnthropicConfig,
    TealAzureOpenAI,
    TealAzureOpenAIConfig,
    TealOpenAI,
    TealOpenAIConfig,
)

# Core governance engine and components (re-exported at the top level so
# `from tealtiger import TealEngine` works, matching the docs and README).
from tealtiger.core import (
    CircuitOpenError,
    CircuitState,
    RedactionLevel,
    TealAudit,
    TealAuditConfig,
    TealCircuit,
    TealEngine,
    TealGuard,
)
from tealtiger.core.context import (
    ContextManager,
    ExecutionContext,
    ExecutionContextOptions,
)
from tealtiger.core.engine.testing import (
    PolicyTestCase,
    PolicyTestReport,
    PolicyTestResult,
    PolicyTestSuite,
    TestCorpora,
)
from tealtiger.core.engine.testing import (
    PolicyTester as PolicyTestRunner,
)

# Enterprise features (v1.1.x)
from tealtiger.core.engine.types import (
    Decision,
    DecisionAction,
    ModeConfig,
    PolicyMode,
    ReasonCode,
)

# Cost tracking and budget management
from tealtiger.cost import (
    # Pricing
    MODEL_PRICING,
    AlertSeverity,
    BudgetAction,
    BudgetConfig,
    BudgetPeriod,
    BudgetScope,
    BudgetStatus,
    CostAlert,
    CostBreakdown,
    CostEstimate,
    CostRecord,
    CostSummary,
    # Tracker
    CostTracker,
    CostTrackerConfig,
    ModelPricing,
    # Types
    ModelProvider,
    TokenUsage,
    get_model_pricing,
    get_provider_models,
    get_supported_models,
    get_supported_providers,
    is_model_supported,
)
from tealtiger.cost.budget import BudgetManager

# Storage and budget management
from tealtiger.cost.storage import CostStorage, InMemoryCostStorage
from tealtiger.guardrails import (
    ContentModerationGuardrail,
    Guardrail,
    GuardrailEngine,
    GuardrailEngineResult,
    GuardrailResult,
    PIIDetectionGuardrail,
    PromptInjectionGuardrail,
)
from tealtiger.observe import freeze, observe, unfreeze
from tealtiger.observe.errors import FrozenAgentError, UnsupportedProviderError
from tealtiger.policy import PolicyBuilder, PolicyTester
from tealtiger.types import ExecutionResult, SecurityDecision

__version__ = "1.4.0"
__all__ = [
    # Core client
    "TealTiger",
    "PolicyBuilder",
    "PolicyTester",
    "ExecutionResult",
    "SecurityDecision",
    # Core governance engine and components
    "TealEngine",
    "TealGuard",
    "TealAudit",
    "TealAuditConfig",
    "TealCircuit",
    "CircuitState",
    "CircuitOpenError",
    "RedactionLevel",
    # Guardrails
    "Guardrail",
    "GuardrailResult",
    "GuardrailEngine",
    "GuardrailEngineResult",
    "PIIDetectionGuardrail",
    "ContentModerationGuardrail",
    "PromptInjectionGuardrail",
    # Cost tracking types
    "ModelProvider",
    "BudgetPeriod",
    "BudgetAction",
    "AlertSeverity",
    "ModelPricing",
    "TokenUsage",
    "CostBreakdown",
    "CostEstimate",
    "CostRecord",
    "BudgetScope",
    "BudgetConfig",
    "BudgetStatus",
    "CostAlert",
    "CostSummary",
    # Pricing functions
    "MODEL_PRICING",
    "get_model_pricing",
    "get_provider_models",
    "is_model_supported",
    "get_supported_models",
    "get_supported_providers",
    # Cost tracking
    "CostTracker",
    "CostTrackerConfig",
    "CostStorage",
    "InMemoryCostStorage",
    # Budget management
    "BudgetManager",
    # Guarded clients
    "TealOpenAI",
    "TealOpenAIConfig",
    "TealAnthropic",
    "TealAnthropicConfig",
    "TealAzureOpenAI",
    "TealAzureOpenAIConfig",
    # Enterprise features (v1.1.x)
    "PolicyMode",
    "DecisionAction",
    "ReasonCode",
    "ModeConfig",
    "Decision",
    "ExecutionContext",
    "ExecutionContextOptions",
    "ContextManager",
    "PolicyTestRunner",
    "TestCorpora",
    "PolicyTestCase",
    "PolicyTestSuite",
    "PolicyTestResult",
    "PolicyTestReport",
    # v1.4: observe() zero-config entry point
    "observe",
    "freeze",
    "unfreeze",
    "FrozenAgentError",
    "UnsupportedProviderError",
]

