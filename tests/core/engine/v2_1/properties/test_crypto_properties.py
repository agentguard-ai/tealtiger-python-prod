"""Property-based tests for TEEC v2.1 CryptoService.

Tests verify:
- Property 1: GovernanceSeal Determinism — hmac_sha256 and sha256 are pure functions
- Property 3: Normalization Equivalence — semantically equivalent payloads produce
  identical normalization_id, and intent_ref differs from normalization_id for
  non-canonical payloads

**Validates: Requirements 2.4, 2.7, 3.5, 3.6**

Uses Hypothesis library for property-based testing.
"""

import re

from hypothesis import given, settings
import hypothesis.strategies as st

from tealtiger.core.engine.v2_1.crypto_service import CryptoService


# Strategy: generate printable text (avoids surrogates that can cause UTF-8 issues)
text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=200,
)

# Strategy: generate non-empty text for keys (HMAC keys should be non-empty for realism,
# but the property still holds for empty keys)
key_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=100,
)

# Hex pattern for SHA-256 output: exactly 64 lowercase hex characters
HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Property 1: GovernanceSeal Determinism
# For any inputs, computing the cryptographic hash/HMAC twice with the same
# inputs SHALL produce identical results. The computation is a pure function.
# ---------------------------------------------------------------------------


class TestSealDeterminism:
    """Property 1: GovernanceSeal Determinism.

    Verifies that hmac_sha256 and sha256 are pure functions — same inputs always
    produce the same output, and outputs are always 64-char lowercase hex.

    **Validates: Requirements 2.4, 2.7**
    """

    @given(key=key_strategy, data=text_strategy)
    @settings(max_examples=200)
    def test_hmac_sha256_determinism(self, key: str, data: str) -> None:
        """hmac_sha256 called twice with identical inputs returns identical results."""
        result1 = CryptoService.hmac_sha256(key, data)
        result2 = CryptoService.hmac_sha256(key, data)
        assert result1 == result2

    @given(key=key_strategy, data=text_strategy)
    @settings(max_examples=200)
    def test_hmac_sha256_output_format(self, key: str, data: str) -> None:
        """hmac_sha256 always produces a 64-character lowercase hex string."""
        result = CryptoService.hmac_sha256(key, data)
        assert HEX_64_PATTERN.match(result), (
            f"Expected 64-char lowercase hex, got: {result!r}"
        )

    @given(data=text_strategy)
    @settings(max_examples=200)
    def test_sha256_determinism(self, data: str) -> None:
        """sha256 called twice with identical input returns identical results."""
        result1 = CryptoService.sha256(data)
        result2 = CryptoService.sha256(data)
        assert result1 == result2

    @given(data=text_strategy)
    @settings(max_examples=200)
    def test_sha256_output_format(self, data: str) -> None:
        """sha256 always produces a 64-character lowercase hex string."""
        result = CryptoService.sha256(data)
        assert HEX_64_PATTERN.match(result), (
            f"Expected 64-char lowercase hex, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Normalization Equivalence
# For any two request payloads that differ only in key ordering, string casing,
# or whitespace padding, the normalization_id SHALL be identical.
# Additionally, for non-canonical payloads, intent_ref and normalization_id
# SHALL be distinct values.
# ---------------------------------------------------------------------------


# Strategy: generate a base payload dict with string values
# Use ASCII letters + digits for values in casing tests to avoid Unicode
# case-folding edge cases (e.g., µ → Μ → μ round-trip mismatch).
payload_value_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=50,
)

# ASCII-only value strategy for casing invariance tests
ascii_value_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
)

payload_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), blacklist_categories=("Cs",)),
    min_size=1,
    max_size=20,
)

base_payload_strategy = st.dictionaries(
    keys=payload_key_strategy,
    values=payload_value_strategy,
    min_size=1,
    max_size=10,
)

# ASCII payload strategy for casing tests (avoids Unicode case-folding edge cases)
ascii_payload_strategy = st.dictionaries(
    keys=payload_key_strategy,
    values=ascii_value_strategy,
    min_size=1,
    max_size=10,
)


class TestNormalizationEquivalence:
    """Property 3: Normalization Equivalence.

    Verifies that semantically equivalent payloads (differing only in key order,
    whitespace, or casing) produce identical normalization_id. Also verifies that
    intent_ref and normalization_id are distinct for non-canonical payloads.

    **Validates: Requirements 3.5, 3.6**
    """

    @given(payload=base_payload_strategy)
    @settings(max_examples=200)
    def test_key_order_invariance(self, payload: dict) -> None:
        """Payloads with reversed key order produce identical normalization output."""
        if len(payload) < 2:
            # Need at least 2 keys to demonstrate key-order invariance
            return

        # Create variant with reversed key order
        variant = dict(reversed(list(payload.items())))

        normalized_original = CryptoService.normalize_payload(payload)
        normalized_variant = CryptoService.normalize_payload(variant)

        assert normalized_original == normalized_variant

    @given(payload=base_payload_strategy)
    @settings(max_examples=200)
    def test_whitespace_padding_invariance(self, payload: dict) -> None:
        """Payloads with whitespace-padded string values produce identical normalization output."""
        # Add whitespace padding to values
        variant = {k: f"  {v}  " for k, v in payload.items()}

        normalized_original = CryptoService.normalize_payload(payload)
        normalized_variant = CryptoService.normalize_payload(variant)

        assert normalized_original == normalized_variant

    @given(payload=ascii_payload_strategy)
    @settings(max_examples=200)
    def test_casing_invariance(self, payload: dict) -> None:
        """Payloads with uppercased string values produce identical normalization output.

        Uses ASCII-only values to avoid Unicode case-folding edge cases
        (e.g., µ → Μ → μ round-trip mismatch).
        """
        # Uppercase all values
        variant = {k: v.upper() for k, v in payload.items()}

        normalized_original = CryptoService.normalize_payload(payload)
        normalized_variant = CryptoService.normalize_payload(variant)

        assert normalized_original == normalized_variant

    @given(payload=ascii_payload_strategy)
    @settings(max_examples=200)
    def test_combined_key_order_whitespace_casing(self, payload: dict) -> None:
        """Payloads with shuffled keys, whitespace, AND casing changes produce same normalization.

        Uses ASCII-only values to avoid Unicode case-folding edge cases.
        """
        if len(payload) < 2:
            return

        # Apply all three transformations
        variant = dict(reversed(list(payload.items())))
        variant = {k: f"  {v.upper()}  " for k, v in variant.items()}

        normalized_original = CryptoService.normalize_payload(payload)
        normalized_variant = CryptoService.normalize_payload(variant)

        assert normalized_original == normalized_variant

    @given(payload=base_payload_strategy)
    @settings(max_examples=200)
    def test_intent_ref_differs_from_normalization_id_for_non_canonical(
        self, payload: dict
    ) -> None:
        """For non-canonical payloads, sha256(deterministic_serialize(payload)) differs from
        sha256(normalize_payload(payload)).

        intent_ref = sha256(deterministic_serialize(payload))
        normalization_id = sha256(normalize_payload(payload))

        These should differ when the payload is not already in canonical form
        (i.e., has uppercase letters or whitespace in values).
        """
        # Create a non-canonical payload: add whitespace and uppercase to values
        non_canonical = {k: f"  {v.upper()}  " for k, v in payload.items()}

        # Check if the payload is actually non-canonical (has values that differ
        # after normalization)
        has_non_canonical_value = any(
            v != v.strip().lower() for v in non_canonical.values()
        )
        if not has_non_canonical_value:
            return

        serialized = CryptoService.deterministic_serialize(non_canonical)
        normalized = CryptoService.normalize_payload(non_canonical)

        intent_ref = CryptoService.sha256(serialized)
        normalization_id = CryptoService.sha256(normalized)

        assert intent_ref != normalization_id, (
            "intent_ref and normalization_id should differ for non-canonical payloads"
        )
