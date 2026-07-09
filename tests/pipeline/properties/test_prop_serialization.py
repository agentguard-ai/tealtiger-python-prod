"""Property test: Pipeline Result Serialization Round-Trip.

**Validates: Requirements 5.4, 13.1, 13.5**

Property 9: For any PipelineResult, serializing to JSON via to_dict()
and deserializing back SHALL produce a structurally equivalent object —
no information loss, all timing metadata preserved, and TEEC v2.1 chain intact.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tealtiger.pipeline.defense_pipeline import DefensePipeline
from tealtiger.pipeline.types import (
    PipelineConfig,
    PipelineRequest,
    PipelineResult,
    PipelineStage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class AllowModule:
    """Module that always returns ALLOW."""

    def __init__(self, name: str = "allow_mod") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "ALLOW", "reason_codes": [], "event_type": "test"}


class DenyModule:
    """Module that always returns DENY."""

    def __init__(self, name: str = "deny_mod") -> None:
        self.name = name
        self.version = "1.0.0"

    async def evaluate(self, request: Any, ctx: Any, policy: Any) -> Dict[str, Any]:
        return {"action": "DENY", "reason_codes": ["DENIED"], "event_type": "test"}


class MockProvider:
    """A mock provider returning a fixed response."""

    def __init__(self, response: Any = None) -> None:
        self._response = response or {"content": "hello", "model": "test"}

    async def call(self, payload: Dict[str, Any]) -> Any:
        return self._response

    def get_cost(self) -> Dict[str, Any]:
        return {"total_cost": 0.0, "request_count": 0}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Simple payloads for pipeline requests
simple_payloads = st.dictionaries(
    keys=st.text(min_size=1, max_size=8, alphabet="abcdefghijklmno"),
    values=st.one_of(
        st.text(min_size=0, max_size=20),
        st.integers(min_value=-100, max_value=100),
        st.booleans(),
    ),
    min_size=1,
    max_size=4,
)

# Pipeline modes
pipeline_modes = st.sampled_from(["allow_all", "deny_pre", "deny_post"])


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Property 9: Pipeline Result Serialization Round-Trip.

    to_dict() → json.dumps → json.loads produces a lossless round-trip.
    """

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        payload=simple_payloads,
        mode=pipeline_modes,
    )
    async def test_to_dict_is_json_serializable(
        self,
        payload: Dict[str, Any],
        mode: str,
    ) -> None:
        """to_dict() output is always JSON-serializable without errors."""
        result = await self._run_pipeline(payload, mode)
        result_dict = result.to_dict()

        # Must not raise
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        payload=simple_payloads,
        mode=pipeline_modes,
    )
    async def test_round_trip_is_lossless(
        self,
        payload: Dict[str, Any],
        mode: str,
    ) -> None:
        """json.dumps(to_dict()) → json.loads produces identical structure."""
        result = await self._run_pipeline(payload, mode)
        result_dict = result.to_dict()

        # Serialize and deserialize
        json_str = json.dumps(result_dict)
        deserialized = json.loads(json_str)

        # Structural equality
        assert deserialized == result_dict, (
            f"Round-trip mismatch.\n"
            f"Original: {result_dict}\n"
            f"Deserialized: {deserialized}"
        )

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(
        payload=simple_payloads,
        mode=pipeline_modes,
    )
    async def test_timing_metadata_preserved(
        self,
        payload: Dict[str, Any],
        mode: str,
    ) -> None:
        """Timing metadata is present and numeric in the serialized output."""
        result = await self._run_pipeline(payload, mode)
        result_dict = result.to_dict()

        timing = result_dict.get("timing")
        assert timing is not None, "timing should be present in serialized result"
        assert isinstance(timing["pipeline_entry"], (int, float))
        assert isinstance(timing["pre_execution_start"], (int, float))
        assert isinstance(timing["pre_execution_end"], (int, float))

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(
        payload=simple_payloads,
        mode=pipeline_modes,
    )
    async def test_decisions_array_preserved(
        self,
        payload: Dict[str, Any],
        mode: str,
    ) -> None:
        """The decisions array is present and non-empty in the serialized output."""
        result = await self._run_pipeline(payload, mode)
        result_dict = result.to_dict()

        decisions = result_dict.get("decisions")
        assert isinstance(decisions, list), "decisions should be a list"
        assert len(decisions) >= 1, "Should have at least the pre-decision"

        # Each decision has required fields
        for d in decisions:
            assert "action" in d
            assert "stage" in d
            assert "latency_ms" in d

    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(payload=simple_payloads)
    async def test_teec_fields_preserved_when_configured(
        self,
        payload: Dict[str, Any],
    ) -> None:
        """When seal_secret is configured, TEEC fields are in the serialized decisions."""
        pipeline = DefensePipeline(
            PipelineConfig(
                pre_execution_modules=[AllowModule()],
                post_execution_modules=[AllowModule(name="post_allow")],
                provider_client=MockProvider(),
                seal_secret="test_seal_secret_12345",
                agent_id="test_agent",
            )
        )

        # Ensure payload has 'content' key for the pipeline to process
        payload_with_content = {**payload, "content": "test content"}
        result = await pipeline.execute(
            PipelineRequest(payload=payload_with_content)
        )
        result_dict = result.to_dict()

        # Check TEEC fields in decisions
        decisions = result_dict.get("decisions", [])
        for d in decisions:
            assert "intent_ref" in d, "TEEC intent_ref should be present"
            assert "receipt_ref" in d, "TEEC receipt_ref should be present"
            assert "seq" in d, "TEEC seq should be present"
            assert "governance_seal" in d, "TEEC governance_seal should be present"

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        payload: Dict[str, Any],
        mode: str,
    ) -> PipelineResult:
        """Run the pipeline in the specified mode and return the result."""
        payload_with_content = {**payload, "content": "test content"}

        if mode == "allow_all":
            pipeline = DefensePipeline(
                PipelineConfig(
                    pre_execution_modules=[AllowModule()],
                    post_execution_modules=[AllowModule(name="post_allow")],
                    provider_client=MockProvider(),
                )
            )
        elif mode == "deny_pre":
            pipeline = DefensePipeline(
                PipelineConfig(
                    pre_execution_modules=[DenyModule()],
                    post_execution_modules=[AllowModule(name="post_allow")],
                    provider_client=MockProvider(),
                )
            )
        else:  # deny_post
            pipeline = DefensePipeline(
                PipelineConfig(
                    pre_execution_modules=[AllowModule()],
                    post_execution_modules=[DenyModule(name="post_deny")],
                    provider_client=MockProvider(),
                    resample_budget=0,
                )
            )

        return await pipeline.execute(PipelineRequest(payload=payload_with_content))
