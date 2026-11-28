"""Guardrail execution engine."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tealtiger.guardrails.base import Guardrail, GuardrailResult

logger = logging.getLogger(__name__)


class GuardrailEngineResult(BaseModel):
    """Aggregated result from all guardrails."""

    passed: bool = Field(..., description="Whether all guardrails passed")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Individual guardrail results")
    execution_time: float = Field(..., description="Total execution time in milliseconds")
    guardrails_executed: int = Field(..., description="Number of guardrails executed")
    max_risk_score: int = Field(default=0, description="Maximum risk score across all guardrails")
    failed_guardrails: List[str] = Field(default_factory=list, description="Names of failed guardrails")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def all_passed(self) -> bool:
        """Check if all guardrails passed."""
        return self.passed

    def get_failed_guardrails(self) -> List[str]:
        """Get list of failed guardrail names."""
        return self.failed_guardrails

    def get_max_risk_score(self) -> int:
        """Get maximum risk score."""
        return self.max_risk_score

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return {
            "passed": self.passed,
            "guardrails_executed": self.guardrails_executed,
            "failed_count": len(self.failed_guardrails),
            "max_risk_score": self.max_risk_score,
            "execution_time": self.execution_time,
        }


class GuardrailEngine:
    """Engine for executing multiple guardrails."""

    def __init__(
        self,
        parallel_execution: bool = True,
        continue_on_error: bool = True,
        timeout: float = 5.0,
    ):
        """Initialize guardrail engine.

        Args:
            parallel_execution: Execute guardrails in parallel
            continue_on_error: Continue execution if a guardrail fails
            timeout: Timeout for individual guardrail execution in seconds
        """
        self.guardrails: List[Guardrail] = []
        self.parallel_execution = parallel_execution
        self.continue_on_error = continue_on_error
        self.timeout = timeout

    def register_guardrail(self, guardrail: Guardrail) -> None:
        """Register a guardrail for execution.

        Args:
            guardrail: Guardrail instance to register
        """
        if not hasattr(guardrail, "evaluate"):
            raise ValueError("Guardrail must implement evaluate() method")

        self.guardrails.append(guardrail)
        logger.info(f"[GuardrailEngine] Registered guardrail: {guardrail.name}")

    def unregister_guardrail(self, name: str) -> None:
        """Unregister a guardrail by name.

        Args:
            name: Name of guardrail to remove
        """
        self.guardrails = [g for g in self.guardrails if g.name != name]
        logger.info(f"[GuardrailEngine] Unregistered guardrail: {name}")

    async def execute(
        self,
        input_data: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailEngineResult:
        """Execute all registered guardrails.

        Args:
            input_data: Input to evaluate
            context: Execution context

        Returns:
            GuardrailEngineResult with aggregated results
        """
        start_time = time.perf_counter()
        enabled_guardrails = [g for g in self.guardrails if g.enabled]

        if not enabled_guardrails:
            return GuardrailEngineResult(
                passed=True,
                results=[],
                execution_time=0.0,
                guardrails_executed=0,
            )

        if self.parallel_execution:
            results = await self._execute_parallel(enabled_guardrails, input_data, context)
        else:
            results = await self._execute_sequential(enabled_guardrails, input_data, context)

        execution_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds

        # Aggregate results
        passed = all(r.get("result", {}).get("passed", False) for r in results)
        max_risk_score = max((r.get("result", {}).get("risk_score", 0) for r in results), default=0)
        failed_guardrails = [
            r["guardrail_name"] for r in results if not r.get("result", {}).get("passed", False)
        ]

        return GuardrailEngineResult(
            passed=passed,
            results=results,
            execution_time=execution_time,
            guardrails_executed=len(enabled_guardrails),
            max_risk_score=max_risk_score,
            failed_guardrails=failed_guardrails,
        )

    async def _execute_parallel(
        self,
        guardrails: List[Guardrail],
        input_data: Any,
        context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Execute guardrails in parallel."""
        tasks = [self._execute_with_timeout(g, input_data, context) for g in guardrails]
        return await asyncio.gather(*tasks)

    async def _execute_sequential(
        self,
        guardrails: List[Guardrail],
        input_data: Any,
        context: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Execute guardrails sequentially."""
        results = []

        for guardrail in guardrails:
            result = await self._execute_with_timeout(guardrail, input_data, context)
            results.append(result)

            # Stop on first failure if configured
            if not self.continue_on_error and result.get("error"):
                break

        return results

    async def _execute_with_timeout(
        self,
        guardrail: Guardrail,
        input_data: Any,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute a single guardrail with timeout and error handling."""
        guardrail_name = guardrail.name
        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                guardrail.evaluate(input_data, context),
                timeout=self.timeout,
            )

            return {
                "guardrail_name": guardrail_name,
                "result": result.dict(),
                "execution_time": (time.perf_counter() - start_time) * 1000,
                "error": None,
            }

        except asyncio.TimeoutError:
            logger.error(f"[GuardrailEngine] Timeout executing {guardrail_name}")

            if self.continue_on_error:
                return {
                    "guardrail_name": guardrail_name,
                    "result": GuardrailResult(
                        passed=False,
                        action="block",
                        reason="Guardrail execution timeout",
                        risk_score=100,
                    ).dict(),
                    "execution_time": (time.perf_counter() - start_time) * 1000,
                    "error": "Timeout",
                }
            raise

        except Exception as error:
            logger.error(f"[GuardrailEngine] Error executing {guardrail_name}: {error}")

            if self.continue_on_error:
                return {
                    "guardrail_name": guardrail_name,
                    "result": GuardrailResult(
                        passed=False,
                        action="block",
                        reason=f"Guardrail execution failed: {str(error)}",
                        risk_score=100,
                    ).dict(),
                    "execution_time": (time.perf_counter() - start_time) * 1000,
                    "error": str(error),
                }
            raise

    def get_registered_guardrails(self) -> List[Dict[str, Any]]:
        """Get list of registered guardrails.

        Returns:
            List of guardrail metadata
        """
        return [g.get_metadata() for g in self.guardrails]

    def clear_guardrails(self) -> None:
        """Clear all registered guardrails."""
        self.guardrails = []
        logger.info("[GuardrailEngine] Cleared all guardrails")
