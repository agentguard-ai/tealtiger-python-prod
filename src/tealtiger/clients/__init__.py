"""
TealTiger Guarded Clients

Drop-in replacements for AI provider clients with integrated security and cost tracking.
"""

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

from .teal_gemini import (
    TealGemini,
    TealGeminiConfig,
    GenerateContentRequest,
    GenerateContentResponse,
)

from .teal_bedrock import (
    TealBedrock,
    TealBedrockConfig,
    BedrockResponse,
)

from .teal_cohere import (
    TealCohere,
    TealCohereConfig,
    ChatResponse,
    EmbedResponse,
)

from .teal_mistral import (
    TealMistral,
    TealMistralConfig,
)

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
