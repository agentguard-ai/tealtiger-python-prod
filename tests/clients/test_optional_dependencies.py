"""Tests for provider SDK optional dependencies."""

import builtins
import sys
from importlib.metadata import metadata
from typing import Iterable

import pytest

from tealtiger.clients import (
    TealAnthropic,
    TealAnthropicConfig,
    TealAzureOpenAI,
    TealAzureOpenAIConfig,
    TealBedrock,
    TealBedrockConfig,
    TealCohere,
    TealCohereConfig,
    TealGemini,
    TealGeminiConfig,
    TealMistral,
    TealMistralConfig,
    TealOpenAI,
    TealOpenAIConfig,
)


def test_provider_extras_are_advertised() -> None:
    package_extras = set(metadata("tealtiger").get_all("Provides-Extra") or [])

    assert {
        "all",
        "anthropic",
        "azure-openai",
        "bedrock",
        "cohere",
        "gemini",
        "mistral",
        "openai",
        "providers",
    }.issubset(package_extras)


def block_imports(monkeypatch: pytest.MonkeyPatch, blocked_roots: Iterable[str]) -> None:
    """Make selected top-level packages behave as if they are not installed."""
    roots = tuple(blocked_roots)

    for module_name in list(sys.modules):
        if any(module_name == root or module_name.startswith(f"{root}.") for root in roots):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if any(name == root or name.startswith(f"{root}.") for root in roots):
            raise ImportError(f"No module named {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.mark.parametrize(
    ("client_cls", "config", "blocked_roots", "extra"),
    [
        (
            TealOpenAI,
            TealOpenAIConfig(api_key="test-key", enable_cost_tracking=False),
            ("openai",),
            "tealtiger[openai]",
        ),
        (
            TealAzureOpenAI,
            TealAzureOpenAIConfig(
                api_key="test-key",
                endpoint="https://example.openai.azure.com",
                enable_cost_tracking=False,
            ),
            ("openai",),
            "tealtiger[azure-openai]",
        ),
        (
            TealAnthropic,
            TealAnthropicConfig(api_key="test-key", enable_cost_tracking=False),
            ("anthropic",),
            "tealtiger[anthropic]",
        ),
        (
            TealGemini,
            TealGeminiConfig(api_key="test-key", enable_cost_tracking=False),
            ("google",),
            "tealtiger[gemini]",
        ),
        (
            TealCohere,
            TealCohereConfig(api_key="test-key", enable_cost_tracking=False),
            ("cohere",),
            "tealtiger[cohere]",
        ),
        (
            TealMistral,
            TealMistralConfig(api_key="test-key", enable_cost_tracking=False),
            ("mistralai",),
            "tealtiger[mistral]",
        ),
    ],
)
def test_provider_clients_raise_clear_install_hint(
    monkeypatch: pytest.MonkeyPatch,
    client_cls,
    config,
    blocked_roots,
    extra: str,
) -> None:
    block_imports(monkeypatch, blocked_roots)

    with pytest.raises(ImportError) as exc_info:
        client_cls(config)

    message = str(exc_info.value)
    assert "requires the optional" in message
    assert f"pip install '{extra}'" in message


@pytest.mark.asyncio
async def test_bedrock_raises_clear_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    block_imports(monkeypatch, ("boto3",))

    client = TealBedrock(TealBedrockConfig(enable_cost_tracking=False))

    with pytest.raises(ImportError) as exc_info:
        await client.invoke_model("hello")

    message = str(exc_info.value)
    assert "requires the optional" in message
    assert "pip install 'tealtiger[bedrock]'" in message
