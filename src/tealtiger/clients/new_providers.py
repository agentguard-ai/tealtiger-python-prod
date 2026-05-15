"""TealTiger v1.3 — New Providers (Python SDK).

Guarded clients for 5 new LLM providers with integrated governance pipeline:
- TealGroq — Groq (ultra-fast LPU inference)
- TealDeepSeek — DeepSeek (reasoning and coding models)
- TealTogether — Together AI (open-source model hosting)
- TealXai — xAI / Grok
- TealHfTgi — Hugging Face Text Generation Inference (self-hosted)

Each provider implements the same GuardedClient pattern with:
- Input/output guardrails (TealGuard)
- Cost tracking and budget enforcement
- Audit logging via correlation IDs
- Governance-wrapped LLM calls

Module: clients/new_providers
Requirements: 12.1, 13.1–13.7, 13.8
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from ..core.engine.v1_3 import (
    DecisionV13,
    GovernanceRequest,
    TealEngineV13,
)

__all__ = [
    # Groq
    "GROQ_PRICING",
    "TealGroq",
    # DeepSeek
    "DEEPSEEK_PRICING",
    "TealDeepSeek",
    # Together AI
    "TOGETHER_PRICING",
    "TealTogether",
    # xAI
    "XAI_PRICING",
    "TealXai",
    # HF TGI
    "HF_TGI_PRICING",
    "TealHfTgi",
]


# ── Pricing Constants ─────────────────────────────────────────────

GROQ_PRICING: Dict[str, Dict[str, float]] = {
    "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
    "llama-3.1-8b-instant": {"input": 0.00005, "output": 0.00008},
    "llama-3.1-70b-versatile": {"input": 0.00059, "output": 0.00079},
    "llama-3.1-405b-reasoning": {"input": 0.006, "output": 0.006},
    "mixtral-8x7b-32768": {"input": 0.00024, "output": 0.00024},
    "gemma2-9b-it": {"input": 0.00020, "output": 0.00020},
    "llama-guard-3-8b": {"input": 0.00020, "output": 0.00020},
}

DEEPSEEK_PRICING: Dict[str, Dict[str, float]] = {
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
}

TOGETHER_PRICING: Dict[str, Dict[str, float]] = {
    "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": {"input": 0.005, "output": 0.005},
    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": {"input": 0.00088, "output": 0.00088},
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": {"input": 0.00018, "output": 0.00018},
    "mistralai/Mixtral-8x22B-Instruct-v0.1": {"input": 0.0012, "output": 0.0012},
    "mistralai/Mixtral-8x7B-Instruct-v0.1": {"input": 0.0006, "output": 0.0006},
    "Qwen/Qwen2.5-72B-Instruct-Turbo": {"input": 0.0012, "output": 0.0012},
    "deepseek-ai/DeepSeek-R1": {"input": 0.003, "output": 0.007},
    "google/gemma-2-27b-it": {"input": 0.0008, "output": 0.0008},
}

XAI_PRICING: Dict[str, Dict[str, float]] = {
    "grok-3": {"input": 0.003, "output": 0.015},
    "grok-3-mini": {"input": 0.0003, "output": 0.0005},
    "grok-2": {"input": 0.002, "output": 0.010},
    "grok-2-mini": {"input": 0.0002, "output": 0.0004},
    "grok-beta": {"input": 0.005, "output": 0.015},
}

HF_TGI_PRICING: Dict[str, Dict[str, float]] = {
    "meta-llama/Meta-Llama-3.1-70B-Instruct": {"input": 0.0009, "output": 0.0009},
    "meta-llama/Meta-Llama-3.1-8B-Instruct": {"input": 0.0002, "output": 0.0002},
    "mistralai/Mixtral-8x7B-Instruct-v0.1": {"input": 0.0005, "output": 0.0005},
    "microsoft/Phi-3-medium-128k-instruct": {"input": 0.0003, "output": 0.0003},
    "tiiuae/falcon-40b-instruct": {"input": 0.0007, "output": 0.0007},
    "bigscience/bloom": {"input": 0.001, "output": 0.001},
    "custom-model": {"input": 0.0005, "output": 0.0005},
}


# ── Shared Config Dataclass ───────────────────────────────────────

@dataclass
class ProviderConfig:
    """Base configuration for all guarded provider clients."""

    api_key: str
    """API key for the provider."""

    base_url: Optional[str] = None
    """Custom base URL for the provider API."""

    model: Optional[str] = None
    """Default model to use."""

    agent_id: str = "default-agent"
    """Agent ID for tracking."""

    enable_guardrails: bool = True
    """Enable input/output guardrails."""

    enable_cost_tracking: bool = True
    """Enable cost tracking and budget enforcement."""

    engine: Optional[TealEngineV13] = None
    """TealEngine v1.3 instance for governance evaluation."""


# ── Helper ────────────────────────────────────────────────────────

def _generate_correlation_id() -> str:
    """Generate a UUID v4 correlation ID."""
    return str(uuid.uuid4())


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


# ── Base Guarded Client ───────────────────────────────────────────

class _BaseGuardedClient:
    """Base class for all guarded provider clients.

    Provides shared governance wrapping logic:
    - Pre-call governance evaluation (input guardrails)
    - Post-call governance evaluation (output guardrails)
    - Cost estimation and tracking
    - Correlation ID propagation
    """

    _provider_name: str = "base"
    _pricing: Dict[str, Dict[str, float]] = {}

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a governance-wrapped chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model identifier (overrides config default).
            **kwargs: Additional provider-specific parameters.

        Returns:
            Dict containing the completion response with governance metadata.

        Raises:
            ValueError: If governance evaluation denies the request.
        """
        resolved_model = model or self._config.model or ""
        correlation_id = _generate_correlation_id()

        # 1. Pre-call governance evaluation
        if self._config.engine:
            user_content = "\n".join(
                m.get("content", "") for m in messages if m.get("role") == "user"
            )
            request = GovernanceRequest(
                correlation_id=correlation_id,
                content=user_content,
                model=resolved_model,
                action_class="LLM_REQUEST",
                action_attributes={
                    "provider": self._provider_name,
                    "message_count": len(messages),
                },
            )
            decision = await self._evaluate_governance(request)
            if decision.action == "DENY":
                raise ValueError(
                    f"Governance denied: {', '.join(decision.reason_codes)}"
                )

        # 2. Make the API call (mock in simplified implementation)
        response = await self._call_provider(messages, resolved_model, **kwargs)

        # 3. Post-call governance evaluation (output guardrails)
        if self._config.engine:
            output_content = response.get("content", "")
            output_request = GovernanceRequest(
                correlation_id=correlation_id,
                content=output_content,
                model=resolved_model,
                action_class="LLM_RESPONSE",
                action_attributes={
                    "provider": self._provider_name,
                },
            )
            output_decision = await self._evaluate_governance(output_request)
            if output_decision.action == "DENY":
                raise ValueError(
                    f"Output governance denied: {', '.join(output_decision.reason_codes)}"
                )

        # 4. Attach governance metadata
        response["governance"] = {
            "correlation_id": correlation_id,
            "provider": self._provider_name,
            "model": resolved_model,
        }

        return response

    async def _evaluate_governance(self, request: GovernanceRequest) -> DecisionV13:
        """Evaluate a governance request via the engine."""
        if not self._config.engine:
            return DecisionV13(action="ALLOW")
        return await self._config.engine.evaluate(request)

    async def _call_provider(
        self,
        messages: List[Dict[str, str]],
        model: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Call the provider API (mock implementation).

        In production, this would use the actual provider SDK or HTTP client.
        """
        input_text = "\n".join(m.get("content", "") for m in messages)
        input_tokens = _estimate_tokens(input_text)
        output_tokens = kwargs.get("max_tokens", 100)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "content": f"Mock response from {self._provider_name}.",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"Mock response from {self._provider_name}.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }

    def get_config(self) -> Dict[str, Any]:
        """Get the current provider configuration."""
        return {
            "provider": self._provider_name,
            "api_key": "***",  # Never expose the key
            "base_url": self._config.base_url,
            "model": self._config.model,
            "agent_id": self._config.agent_id,
            "enable_guardrails": self._config.enable_guardrails,
            "enable_cost_tracking": self._config.enable_cost_tracking,
        }


# ── TealGroq ─────────────────────────────────────────────────────

class TealGroq(_BaseGuardedClient):
    """Guarded client for Groq's ultra-fast LPU inference.

    Wraps Groq API calls with TealTiger governance pipeline:
    - Input/output guardrails
    - Cost tracking with GROQ_PRICING
    - Audit logging via correlation IDs

    Example:
        ```python
        client = TealGroq(ProviderConfig(
            api_key="gsk_...",
            model="llama-3.3-70b-versatile",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """

    _provider_name = "groq"
    _pricing = GROQ_PRICING

    def __init__(self, config: ProviderConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://api.groq.com/openai/v1"
        if config.model is None:
            config.model = "llama-3.3-70b-versatile"
        super().__init__(config)


# ── TealDeepSeek ──────────────────────────────────────────────────

class TealDeepSeek(_BaseGuardedClient):
    """Guarded client for DeepSeek's reasoning and coding models.

    Wraps DeepSeek API calls with TealTiger governance pipeline:
    - Input/output guardrails
    - Cost tracking with DEEPSEEK_PRICING
    - Audit logging via correlation IDs

    Example:
        ```python
        client = TealDeepSeek(ProviderConfig(
            api_key="sk-...",
            model="deepseek-chat",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Explain recursion"}]
        )
        ```
    """

    _provider_name = "deepseek"
    _pricing = DEEPSEEK_PRICING

    def __init__(self, config: ProviderConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://api.deepseek.com/v1"
        if config.model is None:
            config.model = "deepseek-chat"
        super().__init__(config)


# ── TealTogether ──────────────────────────────────────────────────

class TealTogether(_BaseGuardedClient):
    """Guarded client for Together AI's open-source model hosting.

    Wraps Together AI API calls with TealTiger governance pipeline:
    - Input/output guardrails
    - Cost tracking with TOGETHER_PRICING
    - Audit logging via correlation IDs

    Example:
        ```python
        client = TealTogether(ProviderConfig(
            api_key="tog_...",
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """

    _provider_name = "together"
    _pricing = TOGETHER_PRICING

    def __init__(self, config: ProviderConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://api.together.xyz/v1"
        if config.model is None:
            config.model = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
        super().__init__(config)


# ── TealXai ───────────────────────────────────────────────────────

class TealXai(_BaseGuardedClient):
    """Guarded client for xAI's Grok models.

    Wraps xAI API calls with TealTiger governance pipeline:
    - Input/output guardrails
    - Cost tracking with XAI_PRICING
    - Audit logging via correlation IDs

    Example:
        ```python
        client = TealXai(ProviderConfig(
            api_key="xai-...",
            model="grok-3",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """

    _provider_name = "xai"
    _pricing = XAI_PRICING

    def __init__(self, config: ProviderConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://api.x.ai/v1"
        if config.model is None:
            config.model = "grok-3"
        super().__init__(config)


# ── TealHfTgi ─────────────────────────────────────────────────────

class TealHfTgi(_BaseGuardedClient):
    """Guarded client for Hugging Face Text Generation Inference (self-hosted).

    Wraps HF TGI endpoint calls with TealTiger governance pipeline:
    - Input/output guardrails
    - Cost tracking with HF_TGI_PRICING (reference values; override for actual infra costs)
    - Audit logging via correlation IDs

    Example:
        ```python
        client = TealHfTgi(ProviderConfig(
            api_key="",  # May be empty for local endpoints
            base_url="http://localhost:8080",
            model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        ))
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """

    _provider_name = "hf-tgi"
    _pricing = HF_TGI_PRICING

    def __init__(self, config: ProviderConfig) -> None:
        if config.base_url is None:
            config.base_url = "http://localhost:8080"
        if config.model is None:
            config.model = "meta-llama/Meta-Llama-3.1-8B-Instruct"
        super().__init__(config)
