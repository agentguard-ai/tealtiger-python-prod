"""Sidecar client for TealTiger policy evaluation and tool execution.

Use provider clients from :mod:`tealtiger.clients` for guarded LLM calls.
"""

import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union

import httpx

from tealtiger.types import ExecutionContext, ExecutionResult, SecurityDecision

logger = logging.getLogger(__name__)


class TealTigerError(Exception):
    """Base exception for TealTiger errors."""

    def __init__(self, message: str, code: str = "UNKNOWN_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class TealTiger:
    """Client for interacting with the TealTiger Security Sidecar Agent."""

    def __init__(
        self,
        api_key: str,
        ssa_url: str,
        agent_id: str = "default-agent",
        timeout: float = 5.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        debug: bool = False,
        headers: Optional[Dict[str, str]] = None,
        on_security_decision: Optional[Callable[[SecurityDecision], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Initialize the TealTiger client.

        Args:
            api_key: API key for authentication
            ssa_url: URL of the Security Sidecar Agent
            agent_id: Unique identifier for this agent
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            debug: Enable debug logging
            headers: Additional headers to include in requests
            on_security_decision: Callback for security decisions
            on_error: Callback for errors
        """
        self.api_key = api_key
        self.ssa_url = ssa_url.rstrip("/")
        self.agent_id = agent_id
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.debug = debug
        self.on_security_decision = on_security_decision
        self.on_error = on_error

        # Configure logging
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug(f"[TealTiger] Initialized with SSA URL: {self.ssa_url}")

        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(headers or {}),
        }

        # Statistics
        self._stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "denied_requests": 0,
            "transformed_requests": 0,
            "average_response_time": 0.0,
            "error_count": 0,
        }

        self._client = httpx.AsyncClient(
            base_url=self.ssa_url,
            headers=self._headers,
            timeout=self.timeout,
        )

        self._sync_client = httpx.Client(
            base_url=self.ssa_url,
            headers=self._headers,
            timeout=self.timeout,
        )

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Union[ExecutionContext, Dict[str, Any]],
        executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None,
    ) -> ExecutionResult:
        """Execute a tool with security evaluation (async).

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Execution context
            executor: Optional custom async executor function

        Returns:
            ExecutionResult with data and security decision
        """
        start_time = time.time()

        try:
            # Validate inputs
            self._validate_tool_name(tool_name)
            self._validate_parameters(parameters)

            # Convert context to dict if it's an ExecutionContext
            context_dict = context.dict() if isinstance(context, ExecutionContext) else context

            if self.debug:
                logger.debug(f"[TealTiger] Evaluating tool: {tool_name}")
                logger.debug(f"[TealTiger] Parameters: {self._sanitize_params(parameters)}")

            # Evaluate security
            decision = await self._evaluate_security_async(tool_name, parameters, context_dict)

            # Update statistics
            response_time = time.time() - start_time
            self._update_stats(decision, response_time)

            # Call callback if provided
            if self.on_security_decision:
                self.on_security_decision(decision)

            # Handle decision
            if decision.allowed:
                return await self._handle_allow_async(tool_name, parameters, decision, executor)
            elif decision.transformed:
                return await self._handle_transform_async(decision, executor)
            else:
                return self._handle_deny(decision)

        except Exception as error:
            self._stats["error_count"] += 1

            if self.on_error:
                self.on_error(error)

            if self.debug:
                logger.error(f"[TealTiger] Tool execution failed: {error}")

            return ExecutionResult(
                success=False,
                error=str(error),
                security_decision=SecurityDecision(
                    allowed=False,
                    reason=f"Tool execution failed: {str(error)}",
                    policy_id=None,
                    transformed=False,
                ),
            )

    def execute_tool_sync(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Union[ExecutionContext, Dict[str, Any]],
        executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> ExecutionResult:
        """Execute a tool with security evaluation (sync).

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Execution context
            executor: Optional custom sync executor function

        Returns:
            ExecutionResult with data and security decision
        """
        start_time = time.time()

        try:
            # Validate inputs
            self._validate_tool_name(tool_name)
            self._validate_parameters(parameters)

            # Convert context to dict if it's an ExecutionContext
            context_dict = context.dict() if isinstance(context, ExecutionContext) else context

            if self.debug:
                logger.debug(f"[TealTiger] Evaluating tool: {tool_name}")

            # Evaluate security
            decision = self._evaluate_security_sync(tool_name, parameters, context_dict)

            # Update statistics
            response_time = time.time() - start_time
            self._update_stats(decision, response_time)

            # Call callback if provided
            if self.on_security_decision:
                self.on_security_decision(decision)

            # Handle decision
            if decision.allowed:
                return self._handle_allow_sync(tool_name, parameters, decision, executor)
            elif decision.transformed:
                return self._handle_transform_sync(decision, executor)
            else:
                return self._handle_deny(decision)

        except Exception as error:
            self._stats["error_count"] += 1

            if self.on_error:
                self.on_error(error)

            if self.debug:
                logger.error(f"[TealTiger] Tool execution failed: {error}")

            return ExecutionResult(
                success=False,
                error=str(error),
                security_decision=SecurityDecision(
                    allowed=False,
                    reason=f"Tool execution failed: {str(error)}",
                    policy_id=None,
                    transformed=False,
                ),
            )

    async def health_check(self) -> Dict[str, Any]:
        """Check if the SSA is healthy (async).

        Returns:
            Health check response
        """
        response = await self._client.get("/health")
        response.raise_for_status()
        return response.json()

    def health_check_sync(self) -> Dict[str, Any]:
        """Check if the SSA is healthy (sync).

        Returns:
            Health check response
        """
        response = self._sync_client.get("/health")
        response.raise_for_status()
        return response.json()

    def get_statistics(self) -> Dict[str, Any]:
        """Get SDK usage statistics.

        Returns:
            Dictionary with statistics
        """
        return self._stats.copy()

    def reset_statistics(self) -> None:
        """Reset SDK statistics."""
        self._stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "denied_requests": 0,
            "transformed_requests": 0,
            "average_response_time": 0.0,
            "error_count": 0,
        }

    async def _evaluate_security_async(
        self, tool_name: str, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> SecurityDecision:
        """Evaluate security asynchronously."""
        payload = {
            "agentId": self.agent_id,
            "toolName": tool_name,
            "parameters": parameters,
            "context": context,
        }

        response = await self._client.post("/api/evaluate", json=payload)
        response.raise_for_status()
        data = response.json()

        return SecurityDecision(**data.get("decision", {}))

    def _evaluate_security_sync(
        self, tool_name: str, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> SecurityDecision:
        """Evaluate security synchronously."""
        payload = {
            "agentId": self.agent_id,
            "toolName": tool_name,
            "parameters": parameters,
            "context": context,
        }

        response = self._sync_client.post("/api/evaluate", json=payload)
        response.raise_for_status()
        data = response.json()

        return SecurityDecision(**data.get("decision", {}))

    async def _handle_allow_async(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        decision: SecurityDecision,
        executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]],
    ) -> ExecutionResult:
        """Handle allow decision asynchronously."""
        if self.debug:
            logger.debug(f"[TealTiger] Tool allowed: {decision.reason}")

        data = None
        if executor:
            try:
                data = await executor(tool_name, parameters)
            except Exception as error:
                return ExecutionResult(
                    success=False,
                    error=f"Tool execution failed: {str(error)}",
                    security_decision=decision,
                )

        return ExecutionResult(success=True, data=data, security_decision=decision)

    def _handle_allow_sync(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        decision: SecurityDecision,
        executor: Optional[Callable[[str, Dict[str, Any]], Any]],
    ) -> ExecutionResult:
        """Handle allow decision synchronously."""
        if self.debug:
            logger.debug(f"[TealTiger] Tool allowed: {decision.reason}")

        data = None
        if executor:
            try:
                data = executor(tool_name, parameters)
            except Exception as error:
                return ExecutionResult(
                    success=False,
                    error=f"Tool execution failed: {str(error)}",
                    security_decision=decision,
                )

        return ExecutionResult(success=True, data=data, security_decision=decision)

    async def _handle_transform_async(
        self,
        decision: SecurityDecision,
        executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]],
    ) -> ExecutionResult:
        """Handle transform decision asynchronously."""
        if self.debug:
            logger.debug(f"[TealTiger] Tool transformed: {decision.reason}")

        if not decision.original_request:
            return ExecutionResult(
                success=False,
                error="Transform decision but no transformed request available",
                security_decision=decision,
            )

        data = None
        if executor:
            try:
                transformed = decision.original_request
                data = await executor(transformed.get("toolName", ""), transformed.get("parameters", {}))
            except Exception as error:
                return ExecutionResult(
                    success=False,
                    error=f"Transformed tool execution failed: {str(error)}",
                    security_decision=decision,
                )

        return ExecutionResult(success=True, data=data, security_decision=decision)

    def _handle_transform_sync(
        self,
        decision: SecurityDecision,
        executor: Optional[Callable[[str, Dict[str, Any]], Any]],
    ) -> ExecutionResult:
        """Handle transform decision synchronously."""
        if self.debug:
            logger.debug(f"[TealTiger] Tool transformed: {decision.reason}")

        if not decision.original_request:
            return ExecutionResult(
                success=False,
                error="Transform decision but no transformed request available",
                security_decision=decision,
            )

        data = None
        if executor:
            try:
                transformed = decision.original_request
                data = executor(transformed.get("toolName", ""), transformed.get("parameters", {}))
            except Exception as error:
                return ExecutionResult(
                    success=False,
                    error=f"Transformed tool execution failed: {str(error)}",
                    security_decision=decision,
                )

        return ExecutionResult(success=True, data=data, security_decision=decision)

    def _handle_deny(self, decision: SecurityDecision) -> ExecutionResult:
        """Handle deny decision."""
        if self.debug:
            logger.debug(f"[TealTiger] Tool denied: {decision.reason}")

        return ExecutionResult(
            success=False,
            error=f"Tool execution denied: {decision.reason}",
            security_decision=decision,
        )

    def _update_stats(self, decision: SecurityDecision, response_time: float) -> None:
        """Update internal statistics."""
        self._stats["total_requests"] += 1

        if decision.allowed:
            self._stats["allowed_requests"] += 1
        elif decision.transformed:
            self._stats["transformed_requests"] += 1
        else:
            self._stats["denied_requests"] += 1

        # Update average response time
        total_time = self._stats["average_response_time"] * (self._stats["total_requests"] - 1) + response_time
        self._stats["average_response_time"] = total_time / self._stats["total_requests"]

    def _validate_tool_name(self, tool_name: str) -> None:
        """Validate tool name."""
        if not tool_name or not isinstance(tool_name, str):
            raise TealTigerError("Tool name must be a non-empty string", "VALIDATION_ERROR")

    def _validate_parameters(self, parameters: Dict[str, Any]) -> None:
        """Validate parameters."""
        if not isinstance(parameters, dict):
            raise TealTigerError("Parameters must be a dictionary", "VALIDATION_ERROR")

    def _sanitize_params(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize parameters for logging."""
        # Remove sensitive keys
        sensitive_keys = {"password", "token", "secret", "api_key", "apiKey"}
        return {k: "***" if k.lower() in sensitive_keys else v for k, v in parameters.items()}

    async def close(self) -> None:
        """Close the async HTTP client."""
        await self._client.aclose()

    def close_sync(self) -> None:
        """Close the sync HTTP client."""
        self._sync_client.close()

    async def __aenter__(self) -> "TealTiger":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def __enter__(self) -> "TealTiger":
        """Sync context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Sync context manager exit."""
        self.close_sync()
