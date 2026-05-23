from pathlib import Path

import pytest

from tealtiger import TealOpenAI, TealOpenAIConfig, TealTiger
from tealtiger.clients import TealOpenAI as ClientsTealOpenAI


@pytest.mark.asyncio
async def test_root_exports_canonical_provider_client() -> None:
    assert TealOpenAI is ClientsTealOpenAI

    client = TealOpenAI(
        TealOpenAIConfig(
            api_key="test-key",
            enable_guardrails=False,
            enable_cost_tracking=False,
        )
    )

    try:
        assert callable(client.chat.create)
        assert not hasattr(client.chat, "completions")
    finally:
        await client.close()


def test_sidecar_client_is_distinct_from_provider_api() -> None:
    assert TealTiger is not TealOpenAI
    assert hasattr(TealTiger, "execute_tool")


def test_readme_uses_canonical_openai_method() -> None:
    readme = Path(__file__).parents[2].joinpath("README.md").read_text()
    quick_start = readme.split("## 🌐", maxsplit=1)[0]

    assert "TealOpenAIConfig(" in quick_start
    assert "client.chat.create(" in quick_start
    assert "client.chat.completions.create(" not in quick_start
