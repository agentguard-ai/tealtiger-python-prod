"""
Provider detector — identifies which of the 12 supported providers
a client instance belongs to using duck-typing (no isinstance checks).

This is the Python port of the TypeScript provider-detector.ts.
Detection order matters: URL-based variants (Azure, DeepSeek, Groq, xAI, Together)
must be checked before the generic OpenAI fallback.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .errors import UnsupportedProviderError
from .types import ProviderSignature, SupportedProvider, ToolCallInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_nested_attr(obj: object, path: str) -> bool:
    """Check whether *obj* has a dot-separated attribute path.

    Each segment is resolved via ``getattr``. The final segment may be a
    callable, a property, or any non-None value.

    Args:
        obj: The object to inspect.
        path: Dot-separated attribute path (e.g. ``"chat.completions"``).

    Returns:
        True if the entire path resolves to a non-None value.
    """
    current: Any = obj
    for part in path.split("."):
        if current is None:
            return False
        current = getattr(current, part, None)
    return current is not None


def _get_base_url(client: Any) -> str:
    """Extract a base URL string from various client patterns.

    Tries several known attribute locations used by popular Python SDK clients
    (openai, anthropic, httpx-based, etc.).

    Args:
        client: The provider client instance.

    Returns:
        Lowercased base URL string, or empty string if not found.
    """
    url: Optional[str] = (
        getattr(client, "base_url", None)
        or getattr(client, "baseURL", None)
        or getattr(client, "_base_url", None)
    )

    # Some clients store it nested (e.g. client._client.base_url for httpx)
    if url is None:
        inner = getattr(client, "_client", None)
        if inner is not None:
            url = getattr(inner, "base_url", None)

    # openai-python stores it as an httpx.URL object — coerce to str
    if url is not None:
        url = str(url)
    else:
        url = ""

    return url.lower()


def _hash_args(args: Any) -> str:
    """Compute a truncated SHA-256 hash of serialized arguments.

    Args:
        args: The tool call arguments (dict, str, or None).

    Returns:
        String in the format ``"sha256:<first 32 hex chars>"``.
    """
    if isinstance(args, str):
        raw = args
    else:
        raw = json.dumps(args if args is not None else {}, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"sha256:{digest}"


# ---------------------------------------------------------------------------
# Usage Extractors
# ---------------------------------------------------------------------------


def _openai_usage_extractor(response: Any) -> Optional[Dict[str, int]]:
    """Extract token usage from an OpenAI-style response.

    Works for OpenAI, Azure OpenAI, DeepSeek, Groq, xAI, and Together
    since they all follow the same ``response.usage`` schema.

    Args:
        response: The provider API response object.

    Returns:
        Dict with inputTokens, outputTokens, totalTokens or None.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    input_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", None) or (input_tokens + output_tokens)

    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
    }


def _anthropic_usage_extractor(response: Any) -> Optional[Dict[str, int]]:
    """Extract token usage from an Anthropic response.

    Anthropic uses ``input_tokens`` and ``output_tokens`` on the usage object.

    Args:
        response: The Anthropic API response object.

    Returns:
        Dict with inputTokens, outputTokens, totalTokens or None.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0

    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _gemini_usage_extractor(response: Any) -> Optional[Dict[str, int]]:
    """Extract token usage from a Google Gemini response.

    Gemini uses ``usage_metadata`` with ``prompt_token_count`` and
    ``candidates_token_count``.

    Args:
        response: The Gemini API response object.

    Returns:
        Dict with inputTokens, outputTokens, totalTokens or None.
    """
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None

    input_tokens = getattr(meta, "prompt_token_count", 0) or 0
    output_tokens = getattr(meta, "candidates_token_count", 0) or 0
    total_tokens = getattr(meta, "total_token_count", None) or (input_tokens + output_tokens)

    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
    }


def _cohere_usage_extractor(response: Any) -> Optional[Dict[str, int]]:
    """Extract token usage from a Cohere response.

    Cohere nests usage under ``response.meta.tokens``.

    Args:
        response: The Cohere API response object.

    Returns:
        Dict with inputTokens, outputTokens, totalTokens or None.
    """
    meta = getattr(response, "meta", None)
    if meta is None:
        return None
    tokens = getattr(meta, "tokens", None)
    if tokens is None:
        return None

    input_tokens = getattr(tokens, "input_tokens", 0) or 0
    output_tokens = getattr(tokens, "output_tokens", 0) or 0

    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _null_usage_extractor(response: Any) -> Optional[Dict[str, int]]:
    """Return None — used for providers without standard usage metadata.

    Args:
        response: The provider API response (unused).

    Returns:
        None always.
    """
    return None


# ---------------------------------------------------------------------------
# Model Extractors
# ---------------------------------------------------------------------------


def _openai_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from an OpenAI-style request/response.

    Prefers the response model (which may reflect aliasing) over the request.

    Args:
        request: The original request parameters.
        response: The provider API response.

    Returns:
        Model name string or 'unknown'.
    """
    resp_model = getattr(response, "model", None)
    if resp_model:
        return str(resp_model)
    if isinstance(request, dict):
        return request.get("model", "unknown")
    return getattr(request, "model", "unknown") or "unknown"


def _anthropic_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from an Anthropic request/response.

    Args:
        request: The original request parameters.
        response: The provider API response.

    Returns:
        Model name string or 'unknown'.
    """
    resp_model = getattr(response, "model", None)
    if resp_model:
        return str(resp_model)
    if isinstance(request, dict):
        return request.get("model", "unknown")
    return getattr(request, "model", "unknown") or "unknown"


def _gemini_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from a Gemini request.

    Gemini typically carries model in the request, not the response.

    Args:
        request: The original request parameters.
        response: The Gemini API response (unused).

    Returns:
        Model name string or 'gemini-unknown'.
    """
    if isinstance(request, dict):
        return request.get("model", "gemini-unknown")
    return getattr(request, "model", "gemini-unknown") or "gemini-unknown"


def _bedrock_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from a Bedrock request/response.

    Args:
        request: The original request parameters.
        response: The Bedrock API response.

    Returns:
        Model name string or 'bedrock-model'.
    """
    if isinstance(request, dict):
        return request.get("modelId", "bedrock-model")
    return getattr(request, "model_id", None) or "bedrock-model"


def _cohere_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from a Cohere request/response.

    Args:
        request: The original request parameters.
        response: The Cohere API response.

    Returns:
        Model name string or 'command-r'.
    """
    resp_model = getattr(response, "model", None)
    if resp_model:
        return str(resp_model)
    if isinstance(request, dict):
        return request.get("model", "command-r")
    return getattr(request, "model", "command-r") or "command-r"


def _hf_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from a Hugging Face TGI request/response.

    Args:
        request: The original request parameters.
        response: The HF-TGI API response.

    Returns:
        Model name string or 'hf-model'.
    """
    if isinstance(request, dict):
        return request.get("model", "hf-model")
    return getattr(request, "model", "hf-model") or "hf-model"


def _mistral_model_extractor(request: Any, response: Any) -> str:
    """Extract model name from a Mistral request/response.

    Args:
        request: The original request parameters.
        response: The Mistral API response.

    Returns:
        Model name string or 'unknown'.
    """
    resp_model = getattr(response, "model", None)
    if resp_model:
        return str(resp_model)
    if isinstance(request, dict):
        return request.get("model", "unknown")
    return getattr(request, "model", "unknown") or "unknown"


# ---------------------------------------------------------------------------
# Tool Call Extractors
# ---------------------------------------------------------------------------


def _openai_tool_call_extractor(response: Any) -> List[ToolCallInfo]:
    """Extract tool calls from an OpenAI-style response.

    Looks at ``response.choices[0].message.tool_calls``.

    Args:
        response: The OpenAI-style API response.

    Returns:
        List of ToolCallInfo dataclasses.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        return []

    first_choice = choices[0] if len(choices) > 0 else None
    if first_choice is None:
        return []

    message = getattr(first_choice, "message", None)
    if message is None:
        return []

    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return []

    results: List[ToolCallInfo] = []
    for tc in tool_calls:
        func = getattr(tc, "function", None)
        if func is None:
            continue

        name = getattr(func, "name", "unknown") or "unknown"
        raw_args = getattr(func, "arguments", "{}")

        # arguments may be a JSON string or already parsed dict
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                parsed = {}
        else:
            parsed = raw_args if isinstance(raw_args, dict) else {}

        results.append(
            ToolCallInfo(
                tool_name=name,
                argument_count=len(parsed),
                arguments_hash=_hash_args(raw_args),
            )
        )

    return results


def _anthropic_tool_call_extractor(response: Any) -> List[ToolCallInfo]:
    """Extract tool calls from an Anthropic response.

    Anthropic returns content blocks; those with ``type == 'tool_use'``
    represent tool invocations.

    Args:
        response: The Anthropic API response.

    Returns:
        List of ToolCallInfo dataclasses.
    """
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        return []

    results: List[ToolCallInfo] = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type != "tool_use":
            continue

        name = getattr(block, "name", "unknown") or "unknown"
        input_data = getattr(block, "input", {}) or {}

        if not isinstance(input_data, dict):
            input_data = {}

        results.append(
            ToolCallInfo(
                tool_name=name,
                argument_count=len(input_data),
                arguments_hash=_hash_args(input_data),
            )
        )

    return results


def _default_tool_call_extractor(response: Any) -> List[ToolCallInfo]:
    """Return an empty list — used for providers without tool call support.

    Args:
        response: The provider API response (unused).

    Returns:
        Empty list.
    """
    return []


# ---------------------------------------------------------------------------
# Main Detection Function
# ---------------------------------------------------------------------------


def detect_provider(client: object) -> ProviderSignature:
    """Detect the provider type from a client instance using duck-typing.

    Detection order is significant — URL-based variants (Azure OpenAI,
    DeepSeek, Groq, xAI, Together) are checked before the generic OpenAI
    fallback since they share the same ``chat.completions`` interface.

    Args:
        client: An instantiated provider client (e.g. ``openai.OpenAI()``,
            ``anthropic.Anthropic()``, ``google.generativeai.GenerativeModel``).

    Returns:
        A ProviderSignature dataclass containing the provider name and
        associated extractor functions.

    Raises:
        UnsupportedProviderError: If the client does not match any of the
            12 supported providers.
    """
    base_url = _get_base_url(client)

    # --- Azure OpenAI (must check before generic OpenAI) ---
    if _has_nested_attr(client, "chat.completions"):
        azure_endpoint = getattr(client, "_azure_deployment", None) or getattr(
            client, "azure_endpoint", None
        )
        if azure_endpoint or "azure" in base_url:
            return ProviderSignature(
                provider="azure-openai",
                intercept_methods=["chat.completions.create", "completions.create"],
                usage_extractor=_openai_usage_extractor,
                model_extractor=_openai_model_extractor,
                tool_call_extractor=_openai_tool_call_extractor,
            )

    # --- DeepSeek (OpenAI-compatible, baseURL contains 'deepseek') ---
    if _has_nested_attr(client, "chat.completions") and "deepseek" in base_url:
        return ProviderSignature(
            provider="deepseek",
            intercept_methods=["chat.completions.create"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_openai_model_extractor,
            tool_call_extractor=_openai_tool_call_extractor,
        )

    # --- Groq (OpenAI-compatible, baseURL contains 'groq') ---
    if _has_nested_attr(client, "chat.completions") and "groq" in base_url:
        return ProviderSignature(
            provider="groq",
            intercept_methods=["chat.completions.create"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_openai_model_extractor,
            tool_call_extractor=_openai_tool_call_extractor,
        )

    # --- xAI (OpenAI-compatible, baseURL contains 'x.ai') ---
    if _has_nested_attr(client, "chat.completions") and "x.ai" in base_url:
        return ProviderSignature(
            provider="xai",
            intercept_methods=["chat.completions.create"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_openai_model_extractor,
            tool_call_extractor=_openai_tool_call_extractor,
        )

    # --- Together (OpenAI-compatible, baseURL contains 'together') ---
    if _has_nested_attr(client, "chat.completions") and "together" in base_url:
        return ProviderSignature(
            provider="together",
            intercept_methods=["chat.completions.create"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_openai_model_extractor,
            tool_call_extractor=_openai_tool_call_extractor,
        )

    # --- OpenAI (generic — checked after URL-specific variants) ---
    if _has_nested_attr(client, "chat.completions"):
        return ProviderSignature(
            provider="openai",
            intercept_methods=["chat.completions.create", "completions.create"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_openai_model_extractor,
            tool_call_extractor=_openai_tool_call_extractor,
        )

    # --- Anthropic (has 'messages' attribute) ---
    if _has_nested_attr(client, "messages"):
        return ProviderSignature(
            provider="anthropic",
            intercept_methods=["messages.create"],
            usage_extractor=_anthropic_usage_extractor,
            model_extractor=_anthropic_model_extractor,
            tool_call_extractor=_anthropic_tool_call_extractor,
        )

    # --- Gemini (has generate_content method or models.generate_content) ---
    if callable(getattr(client, "generate_content", None)) or _has_nested_attr(
        client, "models.generate_content"
    ):
        return ProviderSignature(
            provider="gemini",
            intercept_methods=["generate_content", "models.generate_content"],
            usage_extractor=_gemini_usage_extractor,
            model_extractor=_gemini_model_extractor,
            tool_call_extractor=_default_tool_call_extractor,
        )

    # --- Bedrock (has invoke_model or meta.region_name from boto3) ---
    if callable(getattr(client, "invoke_model", None)) or _has_nested_attr(
        client, "meta.region_name"
    ):
        return ProviderSignature(
            provider="bedrock",
            intercept_methods=["invoke_model", "invoke_model_with_response_stream"],
            usage_extractor=_openai_usage_extractor,
            model_extractor=_bedrock_model_extractor,
            tool_call_extractor=_default_tool_call_extractor,
        )

    # --- Cohere (has both 'chat' and 'generate' methods) ---
    if callable(getattr(client, "chat", None)) and callable(
        getattr(client, "generate", None)
    ):
        return ProviderSignature(
            provider="cohere",
            intercept_methods=["chat", "generate"],
            usage_extractor=_cohere_usage_extractor,
            model_extractor=_cohere_model_extractor,
            tool_call_extractor=_default_tool_call_extractor,
        )

    # --- Mistral (has 'chat' method and class name contains 'mistral') ---
    if callable(getattr(client, "chat", None)):
        class_name = type(client).__name__.lower()
        if "mistral" in class_name:
            return ProviderSignature(
                provider="mistral",
                intercept_methods=["chat", "chat.complete"],
                usage_extractor=_openai_usage_extractor,
                model_extractor=_mistral_model_extractor,
                tool_call_extractor=_openai_tool_call_extractor,
            )

    # --- HF-TGI (has text_generation method or baseURL contains 'huggingface') ---
    if callable(getattr(client, "text_generation", None)) or "huggingface" in base_url:
        return ProviderSignature(
            provider="hf-tgi",
            intercept_methods=["text_generation", "chat_completion"],
            usage_extractor=_null_usage_extractor,
            model_extractor=_hf_model_extractor,
            tool_call_extractor=_default_tool_call_extractor,
        )

    # --- No match ---
    type_name = type(client).__name__
    raise UnsupportedProviderError(type_name)
