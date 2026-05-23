"""
TealTiger Guarded Clients

Drop-in replacements for AI provider clients with integrated security and cost tracking.

Provider SDKs are imported only when their guarded client is initialized.
Only the provider extra you actually use needs to be installed.
"""

# Core client wrappers are importable without provider SDKs installed.
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
