"""Cross-SDK consistency tests for TEEC v2.1 CryptoService (Python SDK).

**Property 10: Cross-SDK HMAC Consistency** — verify Python outputs match
same precomputed vectors used by the TypeScript SDK.

Tests all CryptoService functions (deterministic_serialize, sha256,
normalize_payload, hmac_sha256) against shared test vectors to ensure
byte-identical outputs across both SDKs.

**Validates: Requirements 7.5, 7.6, 7.7**
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tealtiger.core.engine.v2_1.crypto_service import CryptoService

# ── Load shared test vectors ───────────────────────────────────────

_VECTORS_PATH = Path(__file__).parent / "cross-sdk-vectors.json"

with open(_VECTORS_PATH, encoding="utf-8") as _f:
    _VECTORS_DATA = json.load(_f)

_VECTORS = _VECTORS_DATA["vectors"]


def _vector_ids() -> list[str]:
    return [v["id"] for v in _VECTORS]


# ── Parametrized cross-SDK consistency tests ───────────────────────


@pytest.mark.parametrize("vector", _VECTORS, ids=_vector_ids())
class TestCrossSDKVectors:
    """Verify Python CryptoService outputs match precomputed cross-SDK vectors.

    **Validates: Requirements 7.5, 7.6, 7.7**
    """

    def test_deterministic_serialize(self, vector: dict) -> None:
        """deterministic_serialize produces expected output for vector."""
        inputs = vector["inputs"]
        expected = vector["expected"]["deterministic_serialize"]

        result = CryptoService.deterministic_serialize(inputs["request_payload"])

        assert result == expected, (
            f"Vector '{vector['id']}': deterministic_serialize mismatch.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )

    def test_intent_ref(self, vector: dict) -> None:
        """SHA-256 of serialized payload matches expected intent_ref."""
        inputs = vector["inputs"]
        expected_serialized = vector["expected"]["deterministic_serialize"]
        expected_intent_ref = vector["expected"]["intent_ref"]

        serialized = CryptoService.deterministic_serialize(inputs["request_payload"])
        assert serialized == expected_serialized

        intent_ref = CryptoService.sha256(serialized)

        assert intent_ref == expected_intent_ref, (
            f"Vector '{vector['id']}': intent_ref mismatch.\n"
            f"  Expected: {expected_intent_ref}\n"
            f"  Got:      {intent_ref}"
        )

    def test_normalize_payload(self, vector: dict) -> None:
        """normalize_payload produces expected output for vector."""
        inputs = vector["inputs"]
        expected = vector["expected"]["normalize_payload"]

        result = CryptoService.normalize_payload(inputs["request_payload"])

        assert result == expected, (
            f"Vector '{vector['id']}': normalize_payload mismatch.\n"
            f"  Expected: {expected}\n"
            f"  Got:      {result}"
        )

    def test_normalization_id(self, vector: dict) -> None:
        """SHA-256 of normalized payload matches expected normalization_id."""
        inputs = vector["inputs"]
        expected_normalized = vector["expected"]["normalize_payload"]
        expected_normalization_id = vector["expected"]["normalization_id"]

        normalized = CryptoService.normalize_payload(inputs["request_payload"])
        assert normalized == expected_normalized

        normalization_id = CryptoService.sha256(normalized)

        assert normalization_id == expected_normalization_id, (
            f"Vector '{vector['id']}': normalization_id mismatch.\n"
            f"  Expected: {expected_normalization_id}\n"
            f"  Got:      {normalization_id}"
        )

    def test_hmac_input(self, vector: dict) -> None:
        """HMAC input string (serialized + timestamp + agent_id) matches expected."""
        inputs = vector["inputs"]
        expected_serialized = vector["expected"]["deterministic_serialize"]
        expected_hmac_input = vector["expected"]["hmac_input"]

        serialized = CryptoService.deterministic_serialize(inputs["request_payload"])
        assert serialized == expected_serialized

        hmac_input = serialized + str(inputs["timestamp"]) + inputs["agent_id"]

        assert hmac_input == expected_hmac_input, (
            f"Vector '{vector['id']}': hmac_input mismatch.\n"
            f"  Expected: {expected_hmac_input}\n"
            f"  Got:      {hmac_input}"
        )

    def test_hmac(self, vector: dict) -> None:
        """HMAC-SHA256 output matches expected for vector."""
        inputs = vector["inputs"]
        expected_hmac_input = vector["expected"]["hmac_input"]
        expected_hmac = vector["expected"]["hmac"]

        # Reconstruct hmac_input
        serialized = CryptoService.deterministic_serialize(inputs["request_payload"])
        hmac_input = serialized + str(inputs["timestamp"]) + inputs["agent_id"]
        assert hmac_input == expected_hmac_input

        hmac_result = CryptoService.hmac_sha256(inputs["seal_secret"], hmac_input)

        assert hmac_result == expected_hmac, (
            f"Vector '{vector['id']}': hmac mismatch.\n"
            f"  Expected: {expected_hmac}\n"
            f"  Got:      {hmac_result}"
        )
