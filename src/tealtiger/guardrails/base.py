"""Base guardrail interface for TealTiger."""

from abc import ABC, abstractmethod
from datetime import datetime
import inspect
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    """Result from guardrail evaluation."""

    passed: bool = Field(..., description="Whether the guardrail passed")
    action: str = Field(..., description="Action to take: allow, block, redact, mask, transform")
    reason: str = Field(..., description="Reason for the decision")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    risk_score: int = Field(default=0, ge=0, le=100, description="Risk score 0-100")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def is_passed(self) -> bool:
        """Check if guardrail passed."""
        return self.passed

    def should_block(self) -> bool:
        """Check if action should be blocked."""
        return self.action == "block"

    def get_risk_score(self) -> int:
        """Get risk score."""
        return self.risk_score


class CustomGuardrailCheckResult(BaseModel):
    """Result returned by a function-based custom guardrail."""

    passed: bool = Field(..., description="Whether the custom guardrail passed")
    reason: Optional[str] = Field(default=None, description="Reason for the decision")
    action: Optional[str] = Field(default=None, description="Action to take")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    risk_score: Optional[int] = Field(default=None, ge=0, le=100, description="Risk score 0-100")


class Guardrail(ABC):
    """Base class for all guardrails."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize guardrail.

        Args:
            config: Configuration dictionary
        """
        config = config or {}
        self.name = config.get("name", self.__class__.__name__)
        self.enabled = config.get("enabled", True)
        self.config = config

    @abstractmethod
    async def evaluate(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> GuardrailResult:
        """Evaluate input against this guardrail.

        Args:
            input_data: Input to evaluate
            context: Execution context

        Returns:
            GuardrailResult with evaluation outcome
        """
        pass

    def configure(self, config: Dict[str, Any]) -> None:
        """Update guardrail configuration.

        Args:
            config: New configuration values
        """
        self.config.update(config)
        if "enabled" in config:
            self.enabled = config["enabled"]

    def get_metadata(self) -> Dict[str, Any]:
        """Get guardrail metadata.

        Returns:
            Dictionary with metadata
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "version": self.config.get("version", "1.0.0"),
            "description": self.config.get("description", "No description provided"),
        }


CustomGuardrailResponse = Union[
    CustomGuardrailCheckResult,
    GuardrailResult,
    Dict[str, Any],
]


class CustomGuardrail(Guardrail):
    """Function-based custom guardrail."""

    def __init__(
        self,
        name: str,
        check: Callable[..., Union[CustomGuardrailResponse, Awaitable[CustomGuardrailResponse]]],
        description: Optional[str] = None,
        enabled: bool = True,
    ):
        """Initialize a custom guardrail.

        Args:
            name: Guardrail name
            check: Function that receives input data and optionally context
            description: Optional description
            enabled: Whether the guardrail is enabled
        """
        super().__init__({
            "name": name,
            "description": description or "Custom guardrail",
            "enabled": enabled,
        })
        self.check = check

    async def evaluate(
        self,
        input_data: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailResult:
        """Evaluate input with the custom check function."""
        parameters = inspect.signature(self.check).parameters
        if len(parameters) >= 2:
            result = self.check(input_data, context)
        else:
            result = self.check(input_data)

        if inspect.isawaitable(result):
            result = await result

        if isinstance(result, GuardrailResult):
            return result

        if isinstance(result, CustomGuardrailCheckResult):
            data = result.model_dump()
        elif isinstance(result, dict):
            data = result
        else:
            raise ValueError("Custom guardrail must return a dict, CustomGuardrailCheckResult, or GuardrailResult")

        passed = bool(data["passed"])
        return GuardrailResult(
            passed=passed,
            action=data.get("action") or ("allow" if passed else "block"),
            reason=data.get("reason") or (
                "Custom guardrail passed" if passed else f"Custom guardrail failed: {self.name}"
            ),
            metadata=data.get("metadata") or {},
            risk_score=data.get("risk_score") if data.get("risk_score") is not None else (0 if passed else 50),
        )
