"""TealTiger Python SDK - Enterprise-grade security for AI agents."""

from tealtiger.client import TealTiger
from tealtiger.policy import PolicyBuilder, PolicyTester
from tealtiger.types import ExecutionResult, SecurityDecision
from tealtiger.guardrails import (
    Guardrail,
    GuardrailResult,
    GuardrailEngine,
    GuardrailEngineResult,
    PIIDetectionGuardrail,
    ContentModerationGuardrail,
    PromptInjectionGuardrail,
)

# Cost tracking and budget management
from tealtiger.cost import (
    # Types
    ModelProvider,
    BudgetPeriod,
    BudgetAction,
    AlertSeverity,
    ModelPricing,
    TokenUsage,
    CostBreakdown,
    CostEstimate,
    CostRecord,
    BudgetScope,
    BudgetConfig,
    BudgetStatus,
    CostAlert,
    CostSummary,
    # Pricing
    MODEL_PRICING,
    get_model_pricing,
    get_provider_models,
    is_model_supported,
    get_supported_models,
    get_supported_providers,
    # Tracker
    CostTracker,
    CostTrackerConfig,
)

# Storage and budget management
from tealtiger.cost.storage import CostStorage, InMemoryCostStorage
from tealtiger.cost.budget import BudgetManager

# Guarded AI clients
from tealtiger.clients import (
    TealOpenAI,
    TealOpenAIConfig,
    TealAnthropic,
    TealAnthropicConfig,
    TealAzureOpenAI,
    TealAzureOpenAIConfig,
)

# Enterprise features (v1.1.x)
from tealtiger.core.engine.types import (
    PolicyMode,
    DecisionAction,
    ReasonCode,
    ModeConfig,
    Decision,
)
from tealtiger.core.context import (
    ExecutionContext,
    ExecutionContextOptions,
    ContextManager,
)
from tealtiger.core.engine.testing import (
    PolicyTester as PolicyTestRunner,
    TestCorpora,
    PolicyTestCase,
    PolicyTestSuite,
    PolicyTestResult,
    PolicyTestReport,
)

__version__ = "1.0.0"
__all__ = [
    # Core client
    "TealTiger",
    "PolicyBuilder",
    "PolicyTester",
    "ExecutionResult",
    "SecurityDecision",
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
]

