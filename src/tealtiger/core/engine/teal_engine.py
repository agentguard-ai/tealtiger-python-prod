"""TealEngine - Core Policy Evaluation Engine for Python SDK.

TealTiger SDK v1.1.x - Enterprise Adoption Features
Phase 2: Decision Contract

This module implements the TealEngine with mode-specific behavior and Decision contract.
"""

import importlib.metadata
import time
from typing import Any, Dict, List, Optional

from ..context.context_manager import ContextManager
from ..context.execution_context import ExecutionContext
from .types import Decision, DecisionAction, ModeConfig, PolicyMode, ReasonCode


def get_package_version() -> str:
    """Get the TealTiger package version.
    
    Returns:
        Package version string
    """
    try:
        return importlib.metadata.version("tealtiger")
    except importlib.metadata.PackageNotFoundError:
        return "1.1.0"  # Fallback version


def get_component_versions() -> Dict[str, str]:
    """Get component versions for Decision objects.
    
    Returns:
        Dict with component versions
    """
    version = get_package_version()
    return {
        "sdk": version,
        "engine": version,
    }


def resolve_policy_mode(
    policy_id: str,
    mode_config: ModeConfig,
    environment: Optional[str] = None,
) -> PolicyMode:
    """Resolve the effective policy mode using hierarchical resolution.
    
    Priority: policy-specific > environment-specific > global default
    
    Args:
        policy_id: Policy identifier
        mode_config: Mode configuration
        environment: Optional environment name
        
    Returns:
        Resolved PolicyMode
    """
    # Check policy-specific override (highest priority)
    if policy_id in mode_config.policy:
        return mode_config.policy[policy_id]
    
    # Check environment-specific override
    if environment and environment in mode_config.environment:
        return mode_config.environment[environment]
    
    # Fall back to global default
    return mode_config.default


def calculate_risk_score(allowed: bool, triggered_policies: List[str]) -> int:
    """Calculate risk score based on policy evaluation result.
    
    Args:
        allowed: Whether the request was allowed
        triggered_policies: List of triggered policy IDs
        
    Returns:
        Risk score (0-100)
    """
    if allowed:
        return 0  # No risk if allowed
    
    # Base risk score for violations
    risk_score = 50
    
    # Increase risk based on number of triggered policies
    triggered_count = len(triggered_policies)
    risk_score += min(triggered_count * 10, 40)
    
    # Check for high-risk policy violations
    high_risk_patterns = [
        "tools.file_delete",
        "tools.database_delete",
        "identity.forbidden",
        "codeExecution.blockedFunctions",
        "codeExecution.blockedPatterns",
    ]
    
    for policy in triggered_policies:
        if any(pattern in policy for pattern in high_risk_patterns):
            risk_score = min(risk_score + 20, 100)
    
    return min(max(risk_score, 0), 100)


def determine_reason_codes(allowed: bool, triggered_policies: List[str], reason: Optional[str] = None) -> List[ReasonCode]:
    """Determine reason codes from policy evaluation result.
    
    Args:
        allowed: Whether the request was allowed
        triggered_policies: List of triggered policy IDs
        reason: Optional reason string
        
    Returns:
        List of ReasonCode values
    """
    if allowed:
        return [ReasonCode.POLICY_COMPLIANT]
    
    codes: List[ReasonCode] = [ReasonCode.POLICY_VIOLATION]
    
    # Map triggered policies to reason codes
    for policy in triggered_policies:
        if "tools" in policy:
            # Check if it's a tool not allowed violation
            if "allowed" in policy or (reason and ("blocked" in reason or "not defined" in reason)):
                codes.append(ReasonCode.TOOL_NOT_ALLOWED)
            elif "rateLimit" in policy:
                codes.append(ReasonCode.TOOL_RATE_LIMIT_EXCEEDED)
        elif "identity.forbidden" in policy:
            codes.append(ReasonCode.POLICY_VIOLATION)
        elif "codeExecution" in policy:
            codes.append(ReasonCode.UNSAFE_CODE_DETECTED)
        elif "behavioral.costLimit" in policy:
            codes.append(ReasonCode.COST_BUDGET_EXCEEDED)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_codes = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique_codes.append(code)
    
    return unique_codes


def get_policy_id_from_context(context: Dict[str, Any]) -> str:
    """Extract policy ID from request context.
    
    Args:
        context: Request context dict
        
    Returns:
        Policy ID string
    """
    # Generate policy ID based on context
    if "tool" in context:
        return f"tools.{context['tool']}"
    elif "code" in context:
        return "codeExecution"
    elif "action" in context:
        return f"action.{context['action']}"
    else:
        return "general"


class TealEngine:
    """TealEngine - Core policy evaluation engine.
    
    Provides policy evaluation with mode-specific behavior and Decision contract.
    
    Example:
        >>> from tealtiger.core.engine import TealEngine, ModeConfig, PolicyMode
        >>> from tealtiger.core.context import ContextManager
        >>> 
        >>> # Create engine with MONITOR mode
        >>> engine = TealEngine(
        ...     policies={},
        ...     mode=ModeConfig(default=PolicyMode.MONITOR)
        ... )
        >>> 
        >>> # Evaluate request
        >>> context = ContextManager.create_context()
        >>> decision = engine.evaluate_with_mode(
        ...     {"agentId": "agent-001", "action": "tool.execute", "tool": "file_delete"},
        ...     context
        ... )
        >>> 
        >>> print(f"Action: {decision.action}")
        >>> print(f"Risk Score: {decision.risk_score}")
    """
    
    def __init__(
        self,
        policies: Dict[str, Any],
        mode: Optional[ModeConfig] = None,
        cache_ttl: Optional[int] = None,
        cache_enabled: bool = True,
        cache_max_size: int = 1000,
    ):
        """Initialize TealEngine.
        
        Args:
            policies: Policy configuration dict
            mode: Optional mode configuration (defaults to ENFORCE)
            cache_ttl: Optional cache TTL in milliseconds
            cache_enabled: Whether to enable caching
            cache_max_size: Maximum cache size
        """
        self.policies = policies
        self.mode_config = mode or ModeConfig(default=PolicyMode.ENFORCE)
        self.cache_ttl = cache_ttl
        self.cache_enabled = cache_enabled
        self.cache_max_size = cache_max_size
        self.component_versions = get_component_versions()
        
        # Validate mode configuration
        self._validate_mode_config()
    
    def _validate_mode_config(self) -> None:
        """Validate mode configuration.
        
        Raises:
            ValueError: If mode configuration is invalid
        """
        # Validate default mode
        if not isinstance(self.mode_config.default, PolicyMode):
            raise ValueError(f"Invalid default mode: {self.mode_config.default}")
        
        # Validate environment modes
        for env, mode in self.mode_config.environment.items():
            if not isinstance(mode, PolicyMode):
                raise ValueError(f"Invalid mode for environment '{env}': {mode}")
        
        # Validate policy modes
        for policy_id, mode in self.mode_config.policy.items():
            if not isinstance(mode, PolicyMode):
                raise ValueError(f"Invalid mode for policy '{policy_id}': {mode}")
    
    def evaluate_with_mode(
        self,
        context: Dict[str, Any],
        execution_context: Optional[ExecutionContext] = None,
    ) -> Decision:
        """Evaluate a request with mode-specific behavior and return a Decision object.
        
        Args:
            context: Request context dict with keys like agentId, action, tool, etc.
            execution_context: Optional ExecutionContext for tracing
            
        Returns:
            Decision object with action, reason_codes, risk_score, and metadata
        """
        start_time = time.time()
        
        # Ensure we have an execution context with correlation_id
        exec_context = execution_context or ContextManager.create_context()
        
        # Resolve the effective mode for this policy
        policy_id = get_policy_id_from_context(context)
        environment = exec_context.environment if exec_context else None
        
        effective_mode = resolve_policy_mode(
            policy_id=policy_id,
            mode_config=self.mode_config,
            environment=environment,
        )
        
        # REPORT_ONLY mode: Always allow without evaluating policies
        if effective_mode == PolicyMode.REPORT_ONLY:
            metadata: Dict[str, Any] = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": [],
                "evaluation_performed": False,
            }
            
            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose
            
            decision = Decision(
                action=DecisionAction.ALLOW,
                reason_codes=[ReasonCode.REPORT_ONLY_MODE],
                risk_score=0,
                mode=PolicyMode.REPORT_ONLY,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason="Request allowed in REPORT_ONLY mode (policy evaluation skipped)",
                metadata=metadata,
            )
            
            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]
            
            return decision
        
        # Evaluate policies (simplified - in real implementation, use PolicyEvaluator)
        eval_result = self._evaluate_policies(context)
        
        # Calculate risk score
        risk_score = calculate_risk_score(
            eval_result["allowed"],
            eval_result["triggered_policies"],
        )
        
        # Determine reason codes
        reason_codes = determine_reason_codes(
            eval_result["allowed"],
            eval_result["triggered_policies"],
            eval_result.get("reason"),
        )
        
        # MONITOR mode: Always allow but log violations
        if effective_mode == PolicyMode.MONITOR:
            metadata = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": eval_result["triggered_policies"],
                "evaluation_performed": True,
            }
            
            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose
            
            decision = Decision(
                action=DecisionAction.ALLOW,
                reason_codes=(
                    [ReasonCode.POLICY_COMPLIANT]
                    if eval_result["allowed"]
                    else [ReasonCode.MONITOR_MODE_VIOLATION] + reason_codes
                ),
                risk_score=risk_score,
                mode=PolicyMode.MONITOR,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason=(
                    "Request allowed and compliant with policy"
                    if eval_result["allowed"]
                    else f"Request allowed in MONITOR mode but would violate policy: {eval_result.get('reason', 'Policy violation')}"
                ),
                metadata=metadata,
            )
            
            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]
            
            return decision
        
        # ENFORCE mode: Block violations, allow compliant requests
        if effective_mode == PolicyMode.ENFORCE:
            metadata = {
                "evaluation_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "triggered_policies": eval_result["triggered_policies"],
                "evaluation_performed": True,
            }
            
            # Add optional context fields
            if exec_context.tenant_id:
                metadata["tenant_id"] = exec_context.tenant_id
            if exec_context.application:
                metadata["application"] = exec_context.application
            if exec_context.environment:
                metadata["environment"] = exec_context.environment
            if exec_context.agent_purpose:
                metadata["agent_purpose"] = exec_context.agent_purpose
            
            decision = Decision(
                action=DecisionAction.ALLOW if eval_result["allowed"] else DecisionAction.DENY,
                reason_codes=(
                    [ReasonCode.POLICY_COMPLIANT]
                    if eval_result["allowed"]
                    else reason_codes
                ),
                risk_score=risk_score,
                mode=PolicyMode.ENFORCE,
                policy_id=policy_id,
                policy_version=self.component_versions["engine"],
                component_versions=self.component_versions,
                correlation_id=exec_context.correlation_id,
                reason=(
                    "Request allowed and compliant with policy"
                    if eval_result["allowed"]
                    else eval_result.get("reason", "Request denied by policy")
                ),
                metadata=metadata,
            )
            
            # Add optional fields
            if exec_context.trace_id:
                decision.trace_id = exec_context.trace_id
            if exec_context.workflow_id:
                decision.workflow_id = exec_context.workflow_id
            if exec_context.run_id:
                decision.run_id = exec_context.run_id
            if exec_context.span_id:
                decision.span_id = exec_context.span_id
            if exec_context.parent_span_id:
                decision.parent_span_id = exec_context.parent_span_id
            if context.get("metadata", {}).get("provider"):
                decision.provider = context["metadata"]["provider"]
            
            return decision
        
        # Fallback (should never reach here due to mode validation)
        raise ValueError(f"Invalid policy mode: {effective_mode}")
    
    def _evaluate_policies(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate policies against request context (simplified implementation).
        
        Args:
            context: Request context dict
            
        Returns:
            Dict with keys: allowed (bool), reason (str), triggered_policies (list)
        """
        # Simplified policy evaluation - in real implementation, use PolicyEvaluator
        # For now, just return a basic result
        return {
            "allowed": True,
            "reason": None,
            "triggered_policies": [],
        }
    
    def get_mode_config(self) -> ModeConfig:
        """Get the current mode configuration.
        
        Returns:
            Current ModeConfig
        """
        return self.mode_config
