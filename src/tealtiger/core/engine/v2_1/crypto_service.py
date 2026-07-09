"""TEEC v2.1 Governance Contract — Cryptographic Service (Python SDK).

Provides all cryptographic primitives for the v2.1 governance pipeline:
- SHA-256 hashing
- HMAC-SHA256 signing
- Deterministic JSON serialization (lexicographic key ordering)
- Payload normalization (sort keys, trim whitespace, lowercase strings)

All functions are pure and stateless. Outputs are byte-identical to the
TypeScript SDK for the same inputs (cross-SDK consistency requirement).

Module: core/engine/v2_1/crypto_service
Requirements: 7.7, 2.7, 3.5
"""

from __future__ import annotations

import hashlib
import hmac as hmac_module
import json
from typing import Any


class CryptoService:
    """Stateless cryptographic service for TEEC v2.1 governance decisions.

    All methods are static and produce deterministic outputs. The same
    inputs will always produce byte-identical hex strings across both
    the Python and TypeScript SDKs.
    """

    @staticmethod
    def sha256(data: str) -> str:
        """Compute SHA-256 hash of a string, returned as lowercase hex.

        The input string is encoded as UTF-8 bytes before hashing,
        matching the TypeScript SDK's Buffer.from(data, 'utf-8') behavior.

        Args:
            data: The input string to hash.

        Returns:
            64-character lowercase hex-encoded SHA-256 digest.
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def hmac_sha256(key: str, data: str) -> str:
        """Compute HMAC-SHA256 of data using key, returned as lowercase hex.

        Both key and data are encoded as UTF-8 bytes before computation,
        matching the TypeScript SDK's crypto.createHmac behavior.

        Args:
            key: The HMAC secret key string.
            data: The message string to authenticate.

        Returns:
            64-character lowercase hex-encoded HMAC-SHA256 digest.
        """
        return hmac_module.new(
            key.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def deterministic_serialize(obj: Any) -> str:
        """Serialize an object to JSON with deterministic key ordering.

        Recursively sorts all dictionary keys lexicographically at every
        nesting level. Arrays preserve their original element order.
        Uses compact separators (',', ':') with no whitespace to match
        JavaScript's JSON.stringify default output.

        Args:
            obj: The object to serialize (typically a dict).

        Returns:
            Compact JSON string with lexicographically sorted keys.
        """

        def sort_keys(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: sort_keys(v) for k, v in sorted(value.items())}
            if isinstance(value, list):
                return [sort_keys(item) for item in value]
            return value

        return json.dumps(sort_keys(obj), separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def normalize_payload(payload: Any) -> str:
        """Normalize a payload for semantic deduplication.

        Applies the following transformations recursively:
        1. Sort all dictionary keys lexicographically at all nesting levels
        2. Trim leading/trailing whitespace from all string values
        3. Lowercase all string values
        4. Preserve arrays in their original order (applying normalization
           to each element)

        Then serializes the normalized structure to compact JSON.
        This ensures that payloads differing only in key order, string
        casing, or whitespace padding produce identical output.

        Args:
            payload: The payload to normalize (typically a dict).

        Returns:
            Compact JSON string of the normalized payload.
        """

        def normalize(value: Any) -> Any:
            if isinstance(value, str):
                return value.strip().lower()
            if isinstance(value, dict):
                return {k: normalize(v) for k, v in sorted(value.items())}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            return value

        return json.dumps(normalize(payload), separators=(",", ":"), ensure_ascii=False)
