"""TealGuard - Enhanced Guardrails with Decision Contract.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

This module implements TealGuard that returns Decision objects for consistency
with TealEngine and TealCircuit.
"""

import time
from typing import Any, Dict, List, Optional

from ..context.context_manager import ContextManager
from ..context.execution_context import ExecutionContext
from ..engine.types import Decision, DecisionAction, PolicyMode, ReasonCode
from .types import GuardrailResult


def get_component_versions_with_guard() -> Dict[str, str]:
    """Get component versions including guard.
    
    Returns:
        Dict with component versions
    """
    import importlib.metadata
    
    try:
        version = importlib.metadata.version("tealtiger")
    except importlib.metadata.PackageNotFoundError:
        version = "1.1.0"
    
    return {
        "sdk": version,
        "guard": version,
    }


def determine_reason_codes_from_guardrails(
    guardrail_results: List[GuardrailResult],
    policy_decision: Optional[Decision] = None,
) -> List[ReasonCode]:
    """Determine reason codes from guardrail results.
    
    Args:
        guardrail_results: List of guardrail execution results
        policy_decision: Optional policy decision
        
    Returns:
        List of ReasonCode values
    """
    codes: List[ReasonCode] = []
    
    # If policy decision exists, include its reason codes
    if policy_decision:
        codes.extend(policy_decision.reason_codes)
    
    # Add guardrail-specific reason codes
    for result in guardrail_results:
        if not result.passed:
            name = result.name.lower()
            # Map guardrail names to reason codes
            if "pii" in name:
                codes.append(ReasonCode.PII_DETECTED)
            elif "injection" in name:
                codes.append(ReasonCode.PROMPT_INJECTION_DETECTED)
            elif "harmful" in name or "content" in name:
                codes.append(ReasonCode.HARMFUL_CONTENT_DETECTED)
            elif "code" in name:
                codes.append(ReasonCode.UNSAFE_CODE_DETECTED)
            else:
                # Generic policy violation
                if ReasonCode.POLICY_VIOLATION not in codes:
                    codes.append(ReasonCode.POLICY_VIOLATION)
    
    # If all passed and no codes yet, mark as compliant
    if not codes:
        codes.append(ReasonCode.POLICY_COMPLIANT)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_codes = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)
    
    return unique_codes


def calculate_risk_score_from_guardrails(
    guardrail_results: List[GuardrailResult],
    policy_decision: Optional[Decision] = None,
) -> int:
    """Calculate risk score from guardrail results.
    
    Args:
        guardrail_results: List of guardrail execution results
        policy_decision: Optional policy decision
        
    Returns:
        Risk score (0-100)
    """
    # If policy decision exists and has higher risk, use it
    if policy_decision and policy_decision.risk_score > 0:
        return policy_decision.risk_score
    
    # If all guardrails passed, no risk
    all_passed = all(result.passed for result in guardrail_results)
    if all_passed:
        return 0
    
    # Base risk score for violations
    risk_score = 50
    
    # Increase risk based on number of failed guardrails
    failed_count = sum(1 for result in guardrail_results if not result.passed)
    risk_score += min(failed_count * 15, 40)
    
    # Check for high-risk guardrail failures
    high_risk_guardrails = ["pii", "injection", "harmful", "unsafe"]
    for result in guardrail_results:
        if not result.passed:
            is_high_risk = any(
                pattern in result.name.lower() for pattern in high_risk_guardrails
            )
            if is_high_risk:
                risk_score = min(risk_score + 10, 100)
    
    return min(max(risk_score, 0), 100)


def build_reason_from_guardrails(
    passed: bool,
    guardrail_results: List[GuardrailResult],
    policy_decision: Optional[Decision] = None,
) -> str:
    """Build human-readable reason from guardrail results.
    
    Args:
        passed: Whether all checks passed
        guardrail_results: List of guardrail execution results
        policy_decision: Optional policy decision
        
    Returns:
        Human-readable reason string
    """
    if passed:
        return "All guardrail checks passed"
    
    failed_guardrails = [result.name for result in guardrail_results if not result.passed]
    
    reason = f"Guardrail check failed: {', '.join(failed_guardrails)}"
    
    if policy_decision and policy_decision.action != DecisionAction.ALLOW:
        reason += f" | Policy: {policy_decision.reason}"
    
    return reason


class TealGuard:
    """TealGuard - Enhanced guardrails system with Decision contract.
    
    Integrates guardrail execution with policy evaluation and returns Decision objects
    for consistency with TealEngine and TealCircuit.
    
    Example:
        >>> from tealtiger.core.guard import TealGuard
        >>> from tealtiger.core.context import ContextManager
        >>> 
        >>> guard = TealGuard()
        >>> context = ContextManager.create_context()
        >>> 
        >>> decision = await guard.check("Hello world", context)
        >>> print(f"Action: {decision.action}")
        >>> print(f"Risk Score: {decision.risk_score}")
    """
    
    def __init__(
        self,
        engine: Optional[Any] = None,
        policy: Optional[Dict[str, Any]] = None,
        policy_driven: bool = False,
        enable_cache: bool = False,
        cache_ttl: int = 60000,
        cache_max_size: int = 1000,
    ):
        """Initialize TealGuard.
        
        Args:
            engine: Optional TealEngine instance for policy evaluation
            policy: Optional policy configuration (if engine not provided)
            policy_driven: Whether to enable policy-driven mode
            enable_cache: Whether to enable result caching
            cache_ttl: Cache TTL in milliseconds
            cache_max_size: Maximum cache size
        """
        self.engine = engine
        self.policy = policy
        self.policy_driven = policy_driven
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.cache_max_size = cache_max_size
        self.component_versions = get_component_versions_with_guard()
        
        # Cache storage (simple dict for now)
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    async def check(
        self,
        input_data: Any,
        context: Optional[ExecutionContext] = None,
    ) -> Decision:
        """Check input against all guardrails and policies.
        
        Returns a Decision object with the same structure as TealEngine for consistency.
        
        Args:
            input_data: Input to check
            context: Optional ExecutionContext with correlation_id
            
        Returns:
            Decision object with action, reason_codes, risk_score, and metadata
        """
        start_time = time.time()
        
        # Ensure we have a valid ExecutionContext
        execution_context = context or ContextManager.create_context()
        
        # Execute guardrails (simplified - in real implementation, use GuardrailEngine)
        guardrail_results = await self._execute_guardrails(input_data, execution_context)
        
        # Evaluate policy if policy-driven mode is enabled
        policy_decision: Optional[Decision] = None
        if self.policy_driven and self.engine:
            request_context = {
                "agentId": execution_context.tenant_id or "default",
                "action": "guardrail.check",
                "content": str(input_data) if not isinstance(input_data, str) else input_data,
                "metadata": {
                    "correlation_id": execution_context.correlation_id,
                    "trace_id": execution_context.trace_id,
                    "workflow_id": execution_context.workflow_id,
                    "run_id": execution_context.run_id,
                    "span_id": execution_context.span_id,
                },
            }
            policy_decision = self.engine.evaluate_with_mode(request_context, execution_context)
        
        execution_time = int((time.time() - start_time) * 1000)
        
        # Determine overall action based on guardrail and policy results
        all_passed = all(result.passed for result in guardrail_results)
        passed = all_passed and (
            policy_decision.action == DecisionAction.ALLOW if policy_decision else True
        )
        
        # Build Decision object
        decision = self._build_decision(
            passed=passed,
            guardrail_results=guardrail_results,
            policy_decision=policy_decision,
            execution_context=execution_context,
            execution_time=execution_time,
        )
        
        return decision
    
    async def _execute_guardrails(
        self,
        input_data: Any,
        context: ExecutionContext,
    ) -> List[GuardrailResult]:
        """Execute guardrails (simplified implementation).
        
        Args:
            input_data: Input to check
            context: ExecutionContext
            
        Returns:
            List of GuardrailResult objects
        """
        # Simplified guardrail execution - in real implementation, use GuardrailEngine
        # For now, just return empty list (all passed)
        return []
    
    def _build_decision(
        self,
        passed: bool,
        guardrail_results: List[GuardrailResult],
        policy_decision: Optional[Decision],
        execution_context: ExecutionContext,
        execution_time: int,
    ) -> Decision:
        """Build Decision object from guardrail and policy results.
        
        Args:
            passed: Whether all checks passed
            guardrail_results: List of guardrail execution results
            policy_decision: Optional policy decision
            execution_context: ExecutionContext
            execution_time: Execution time in milliseconds
            
        Returns:
            Decision object
        """
        # Determine action
        if policy_decision and policy_decision.action != DecisionAction.ALLOW:
            action = policy_decision.action
        elif not passed:
            action = DecisionAction.DENY
        else:
            action = DecisionAction.ALLOW
        
        # Determine reason codes
        reason_codes = determine_reason_codes_from_guardrails(
            guardrail_results, policy_decision
        )
        
        # Calculate risk score
        risk_score = calculate_risk_score_from_guardrails(
            guardrail_results, policy_decision
        )
        
        # Build human-readable reason
        reason = build_reason_from_guardrails(passed, guardrail_results, policy_decision)
        
        # Determine mode (default to ENFORCE if not policy-driven)
        mode = policy_decision.mode if policy_decision else PolicyMode.ENFORCE
        
        # Build triggered policies list
        triggered_policies: List[str] = []
        for result in guardrail_results:
            if not result.passed:
                triggered_policies.append(f"guardrail.{result.name}")
        if policy_decision and policy_decision.metadata.get("triggered_policies"):
            triggered_policies.extend(policy_decision.metadata["triggered_policies"])
        
        # Build metadata
        metadata: Dict[str, Any] = {
            "evaluation_time_ms": execution_time,
            "cache_hit": False,
            "guardrail_results": {
                "passed": all(result.passed for result in guardrail_results),
                "total": len(guardrail_results),
                "failed": sum(1 for result in guardrail_results if not result.passed),
            },
        }
        
        if triggered_policies:
            metadata["triggered_policies"] = triggered_policies
        if execution_context.tenant_id:
            metadata["tenant_id"] = execution_context.tenant_id
        if execution_context.application:
            metadata["application"] = execution_context.application
        if execution_context.environment:
            metadata["environment"] = execution_context.environment
        if execution_context.agent_purpose:
            metadata["agent_purpose"] = execution_context.agent_purpose
        
        # Build Decision object
        decision = Decision(
            action=action,
            reason_codes=reason_codes,
            risk_score=risk_score,
            mode=mode,
            policy_id="guardrail.check",
            policy_version=self.component_versions.get("guard", "1.1.0"),
            component_versions=self.component_versions,
            correlation_id=execution_context.correlation_id,
            reason=reason,
            metadata=metadata,
        )
        
        # Add optional fields only if defined
        if execution_context.trace_id:
            decision.trace_id = execution_context.trace_id
        if execution_context.workflow_id:
            decision.workflow_id = execution_context.workflow_id
        if execution_context.run_id:
            decision.run_id = execution_context.run_id
        if execution_context.span_id:
            decision.span_id = execution_context.span_id
        if execution_context.parent_span_id:
            decision.parent_span_id = execution_context.parent_span_id
        
        return decision
