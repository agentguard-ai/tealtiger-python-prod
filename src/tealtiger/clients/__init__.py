"""
TealTiger Guarded Clients

Drop-in replacements for AI provider clients with integrated security and cost tracking.

These provider clients are the canonical public API for guarded LLM calls.
The top-level tealtiger package re-exports the primary provider clients for
convenience, while tealtiger.client.TealTiger remains the sidecar client for
tool-execution policy workflows.

Clients are lazily imported to avoid requiring all provider SDKs to be installed.
Only the provider SDK you actually use needs to be installed.
"""

from typing import TYPE_CHECKING

# Always available (OpenAI is a required dependency)
from .teal_openai import (
    TealOpenAI,
    TealOpenAIConfig,
    ChatCompletionMessage,
    ChatCompletionRequest,
    SecurityMetadata,
    ChatCompletionResponse,
)

from .teal_anthropic import (
    TealAnthropic,
    TealAnthropicConfig,
    MessageCreateRequest,
    MessageCreateResponse,
)

from .teal_azure_openai import (
    TealAzureOpenAI,
    TealAzureOpenAIConfig,
    AzureChatCompletionMessage,
    AzureChatCompletionRequest,
    AzureChatCompletionResponse,
)

# Lazy imports for optional providers
def __getattr__(name: str):
    """Lazy import for optional provider clients."""
    if name in ("TealGemini", "TealGeminiConfig", "GenerateContentRequest", "GenerateContentResponse"):
        from .teal_gemini import TealGemini, TealGeminiConfig, GenerateContentRequest, GenerateContentResponse
        _map = {
            "TealGemini": TealGemini,
            "TealGeminiConfig": TealGeminiConfig,
            "GenerateContentRequest": GenerateContentRequest,
            "GenerateContentResponse": GenerateContentResponse,
        }
        return _map[name]

    if name in ("TealBedrock", "TealBedrockConfig", "BedrockResponse"):
        from .teal_bedrock import TealBedrock, TealBedrockConfig, BedrockResponse
        _map = {
            "TealBedrock": TealBedrock,
            "TealBedrockConfig": TealBedrockConfig,
            "BedrockResponse": BedrockResponse,
        }
        return _map[name]

    if name in ("TealCohere", "TealCohereConfig", "ChatResponse", "EmbedResponse"):
        from .teal_cohere import TealCohere, TealCohereConfig, ChatResponse, EmbedResponse
        _map = {
            "TealCohere": TealCohere,
            "TealCohereConfig": TealCohereConfig,
            "ChatResponse": ChatResponse,
            "EmbedResponse": EmbedResponse,
        }
        return _map[name]

    if name in ("TealMistral", "TealMistralConfig"):
        from .teal_mistral import TealMistral, TealMistralConfig
        _map = {
            "TealMistral": TealMistral,
            "TealMistralConfig": TealMistralConfig,
        }
        return _map[name]

    raise AttributeError(f"module 'tealtiger.clients' has no attribute {name!r}")


__all__ = [
    # Always available
    'TealOpenAI',
    'TealOpenAIConfig',
    'ChatCompletionMessage',
    'ChatCompletionRequest',
    'SecurityMetadata',
    'ChatCompletionResponse',
    'TealAnthropic',
    'TealAnthropicConfig',
    'MessageCreateRequest',
    'MessageCreateResponse',
    'TealAzureOpenAI',
    'TealAzureOpenAIConfig',
    'AzureChatCompletionMessage',
    'AzureChatCompletionRequest',
    'AzureChatCompletionResponse',
    # Lazy-loaded
    'TealGemini',
    'TealGeminiConfig',
    'GenerateContentRequest',
    'GenerateContentResponse',
    'TealBedrock',
    'TealBedrockConfig',
    'BedrockResponse',
    'TealCohere',
    'TealCohereConfig',
    'ChatResponse',
    'EmbedResponse',
    'TealMistral',
    'TealMistralConfig',
]
