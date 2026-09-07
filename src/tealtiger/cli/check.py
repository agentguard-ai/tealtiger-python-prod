"""CLI command for offline policy evaluation."""

import asyncio
import json
import time
from typing import Optional

import click

from tealtiger.guardrails.pii_detection import PIIDetectionGuardrail
from tealtiger.pipeline.modules.pre.tool_allowlist import (
    ToolAllowlistConfig,
    ToolAllowlistModule,
)


@click.command()
@click.option("--text", type=str, help="Text to evaluate.")
@click.option("--policy", type=str, help="Policy to evaluate.")
@click.option("--tool", type=str, help="Tool name to evaluate.")
@click.option("--allowlist", type=str, help="Comma-separated allowed tool names.")
def check(
    text: Optional[str],
    policy: Optional[str],
    tool: Optional[str],
    allowlist: Optional[str],
) -> None:
    """Evaluate a TealTiger policy locally."""

    if text is not None or policy is not None:
        if not text or not policy:
            raise click.UsageError("--text and --policy must be provided together")

        if policy != "pii_block":
            raise click.UsageError(f"Unsupported policy: {policy}")

        guardrail = PIIDetectionGuardrail({"action": "block"})

        start_time = time.perf_counter()
        pii_result = asyncio.run(guardrail.evaluate(text))
        evaluation_time_ms = (time.perf_counter() - start_time) * 1000

        reason_codes = [
            f"PII_DETECTED:{detection['type']}"
            for detection in pii_result.metadata.get("detections", [])
        ]

        output = {
            "action": "ALLOW" if pii_result.passed else "DENY",
            "reason": pii_result.reason,
            "reason_codes": reason_codes,
            "evaluation_time_ms": evaluation_time_ms,
        }

        click.echo(json.dumps(output))
        return

    if tool is not None or allowlist is not None:
        if not tool or allowlist is None:
            raise click.UsageError("--tool and --allowlist must be provided together")

        allowed_tools = [item.strip() for item in allowlist.split(",") if item.strip()]

        module = ToolAllowlistModule(ToolAllowlistConfig(allowlist=allowed_tools))

        start_time = time.perf_counter()
        tool_result = asyncio.run(
            module.evaluate(
                {"tool": tool},
                None,
                None,
            )
        )
        evaluation_time_ms = (time.perf_counter() - start_time) * 1000

        allowed = tool_result["action"] == "ALLOW"

        output = {
            "action": tool_result["action"],
            "reason": "Tool allowed" if allowed else "Tool not allowed",
            "reason_codes": tool_result["reason_codes"],
            "evaluation_time_ms": evaluation_time_ms,
        }

        click.echo(json.dumps(output))
        return

    raise click.UsageError("Provide either --text/--policy or --tool/--allowlist")
