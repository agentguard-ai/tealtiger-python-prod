"""Multi-Stage Defense Pipeline — Cost Reconciliation Module (Python SDK).

Compares actual response token usage against pre-execution cost estimates.
Returns MONITOR when the actual cost exceeds the estimate by more than
a configurable tolerance (default 20%).

This module never returns DENY — it only flags cost overruns for
observability. The pipeline continues regardless of the finding.

Module: pipeline/modules/post/cost_reconciliation
Requirements: 7.5, 7.6, 7.7
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CostReconciliationConfig:
    """Configuration object for CostReconciliationModule."""

    tolerance_pct: float = 0.2
    """Tolerance percentage (0–1 scale). Default: 0.2 (20%)."""


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class CostReconciliationModule:
    """Compares actual token usage against pre-execution cost estimates and
    returns MONITOR when the actual cost exceeds the estimate by more than
    the configured tolerance.

    The module reads cost data from the evaluation request:
    - ``_execution_metadata.usage.total_tokens`` — actual token usage from provider
    - ``_estimated_tokens`` — pre-execution token estimate

    When a cost overrun is detected:
    - action: MONITOR
    - reason_codes: ['COST_OVERRUN']
    - metadata: { actual_tokens, estimated_tokens, overrun_pct, tolerance_pct }

    When within tolerance or when estimates are unavailable:
    - action: ALLOW
    - reason_codes: []
    """

    name: str = "CostReconciliationModule"
    version: str = "1.0.0"

    def __init__(self, config: Optional[CostReconciliationConfig] = None) -> None:
        cfg = config or CostReconciliationConfig()
        self._tolerance_pct = cfg.tolerance_pct

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate cost reconciliation between estimates and actuals.

        Args:
            request: The module evaluation request (dict-like, includes metadata).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        actual_tokens = self._extract_actual_tokens(request)
        estimated_tokens = self._extract_estimated_tokens(request)

        # If either value is missing or invalid, cannot reconcile — ALLOW
        if actual_tokens is None or estimated_tokens is None or estimated_tokens <= 0:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.cost_reconciliation",
                "metadata": {
                    "module": self.name,
                    "actual_tokens": actual_tokens,
                    "estimated_tokens": estimated_tokens,
                    "reconciliation_possible": False,
                },
            }

        # Calculate overrun percentage
        overrun_pct = (actual_tokens - estimated_tokens) / estimated_tokens

        if overrun_pct > self._tolerance_pct:
            return {
                "action": "MONITOR",
                "reason_codes": ["COST_OVERRUN"],
                "event_type": "pipeline.cost_reconciliation",
                "metadata": {
                    "module": self.name,
                    "actual_tokens": actual_tokens,
                    "estimated_tokens": estimated_tokens,
                    "overrun_pct": overrun_pct,
                    "tolerance_pct": self._tolerance_pct,
                    "reconciliation_possible": True,
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.cost_reconciliation",
            "metadata": {
                "module": self.name,
                "actual_tokens": actual_tokens,
                "estimated_tokens": estimated_tokens,
                "overrun_pct": overrun_pct,
                "tolerance_pct": self._tolerance_pct,
                "reconciliation_possible": True,
            },
        }

    def _extract_actual_tokens(self, request: Any) -> Optional[int]:
        """Extract actual token usage from execution metadata.

        Looks for ``_execution_metadata.usage.total_tokens`` in the request.
        Falls back to ``_response.usage.total_tokens``.
        """
        if not isinstance(request, dict):
            return None

        # Primary: _execution_metadata.usage.total_tokens
        exec_meta = request.get("_execution_metadata")
        if isinstance(exec_meta, dict):
            usage = exec_meta.get("usage")
            if isinstance(usage, dict):
                total = usage.get("total_tokens")
                if isinstance(total, (int, float)):
                    return int(total)

        # Fallback: _response.usage.total_tokens
        response = request.get("_response")
        if isinstance(response, dict):
            usage = response.get("usage")
            if isinstance(usage, dict):
                total = usage.get("total_tokens")
                if isinstance(total, (int, float)):
                    return int(total)

        return None

    def _extract_estimated_tokens(self, request: Any) -> Optional[int]:
        """Extract the pre-execution token estimate from the request.

        Looks for ``_estimated_tokens`` field.
        """
        if not isinstance(request, dict):
            return None

        estimated = request.get("_estimated_tokens")
        if isinstance(estimated, (int, float)) and estimated > 0:
            return int(estimated)

        return None
