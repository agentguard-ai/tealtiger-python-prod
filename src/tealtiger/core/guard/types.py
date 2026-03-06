"""Type definitions for TealGuard.

TealTiger SDK v1.1.x - Enterprise Adoption Features
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    """Result from a single guardrail execution.
    
    Attributes:
        name: Guardrail name
        passed: Whether the guardrail check passed
        message: Optional message explaining the result
        metadata: Additional metadata
    """
    
    name: str = Field(
        ...,
        description="Guardrail name",
    )
    
    passed: bool = Field(
        ...,
        description="Whether the guardrail check passed",
    )
    
    message: Optional[str] = Field(
        None,
        description="Optional message explaining the result",
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
