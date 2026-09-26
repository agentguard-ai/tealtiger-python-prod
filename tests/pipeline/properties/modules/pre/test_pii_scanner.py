"""Unit tests for PIIScannerModule — pre-execution PII scanning."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src"))

import pytest

from tealtiger.pipeline.modules.pre.pii_scanner import (
    PIIScannerConfig,
    PIIScannerModule,
)


@pytest.mark.asyncio
class TestPIIScannerModuleIBAN:
    async def test_deny_on_iban_above_threshold(self):
        module = PIIScannerModule()
        request = {"content": "My IBAN is GB29 NWBK 6016 1331 9268 19"}
        result = await module.evaluate(request, ctx={}, policy={})
        assert result["action"] == "DENY"
        assert "PII_DETECTED" in result["reason_codes"]
        patterns = [f["pattern"] for f in result["metadata"]["findings"]]
        assert "iban" in patterns

    async def test_allow_on_clean_content(self):
        module = PIIScannerModule()
        request = {"content": "Just a normal sentence with no PII."}
        result = await module.evaluate(request, ctx={}, policy={})
        assert result["action"] == "ALLOW"


@pytest.mark.asyncio
class TestPIIScannerModulePassport:
    async def test_deny_on_us_passport_above_threshold(self):
        module = PIIScannerModule()
        request = {"content": "Passport: A12345678"}
        result = await module.evaluate(request, ctx={}, policy={})
        assert result["action"] == "DENY"
        patterns = [f["pattern"] for f in result["metadata"]["findings"]]
        assert "passport" in patterns

    async def test_deny_on_india_passport_above_threshold(self):
        module = PIIScannerModule()
        request = {"content": "Passport: 123456789"}
        result = await module.evaluate(request, ctx={}, policy={})
        assert result["action"] == "DENY"
        patterns = [f["pattern"] for f in result["metadata"]["findings"]]
        assert "passport" in patterns

    async def test_passport_below_custom_high_threshold_allows(self):
            # US passport format (letter + 8 digits) does not collide with the
            # ssn pattern (9 contiguous digits), so this isolates passport's own
            # confidence (0.7) against a threshold that should not trigger DENY.
            config = PIIScannerConfig(threshold=0.75)
            module = PIIScannerModule(config=config)
            request = {"content": "Passport: A12345678"}
            result = await module.evaluate(request, ctx={}, policy={})
            assert result["action"] == "ALLOW"
