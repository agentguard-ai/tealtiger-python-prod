"""
TealTiger Guarded Clients

Drop-in replacements for AI provider clients with integrated security and cost tracking.

All provider clients are lazily imported. Only the provider SDK you actually use
needs to be installed via extras (e.g., pip install tealtiger[openai]).
"""


def __getattr__(name: str):
    """Lazy import for all provider clients."""
    if name in ("TealOpenAI", "TealOpenAIConfig", "ChatCompletionMessage", "ChatCompletionRequest", "SecurityMetadata", "ChatCompletionResponse"):
        from .teal_openai import TealOpenAI, TealOpenAIConfig, ChatCompletionMessage, ChatCompletionRequest, SecurityMetadata, ChatCompletionResponse
        _map = {
            "TealOpenAI": TealOpenAI,
            "TealOpenAIConfig": TealOpenAIConfig,
            "ChatCompletionMessage": ChatCompletionMessage,
            "ChatCompletionRequest": ChatCompletionRequest,
            "SecurityMetadata": SecurityMetadata,
            "ChatCompletionResponse": ChatCompletionResponse,
        }
        return _map[name]

    if name in ("TealAnthropic", "TealAnthropicConfig", "MessageCreateRequest", "MessageCreateResponse"):
        from .teal_anthropic import TealAnthropic, TealAnthropicConfig, MessageCreateRequest, MessageCreateResponse
        _map = {
            "TealAnthropic": TealAnthropic,
            "TealAnthropicConfig": TealAnthropicConfig,
            "MessageCreateRequest": MessageCreateRequest,
            "MessageCreateResponse": MessageCreateResponse,
        }
        return _map[name]

    if name in ("TealAzureOpenAI", "TealAzureOpenAIConfig", "AzureChatCompletionMessage", "AzureChatCompletionRequest", "AzureChatCompletionResponse"):
        from .teal_azure_openai import TealAzureOpenAI, TealAzureOpenAIConfig, AzureChatCompletionMessage, AzureChatCompletionRequest, AzureChatCompletionResponse
        _map = {
            "TealAzureOpenAI": TealAzureOpenAI,
            "TealAzureOpenAIConfig": TealAzureOpenAIConfig,
            "AzureChatCompletionMessage": AzureChatCompletionMessage,
            "AzureChatCompletionRequest": AzureChatCompletionRequest,
            "AzureChatCompletionResponse": AzureChatCompletionResponse,
        }
        return _map[name]

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
