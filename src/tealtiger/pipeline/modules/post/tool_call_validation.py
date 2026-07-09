"""Multi-Stage Defense Pipeline — Tool Call Validation Module (Python SDK).

Verifies tool calls in the LLM response conform to expected schemas and
parameter constraints. Returns DENY with ``remediation: 'resample'`` metadata
and reason code TOOL_CALL_INVALID when a tool call is malformed or violates
configured constraints.

Module: pipeline/modules/post/tool_call_validation
Requirements: 7.4, 7.6, 7.7
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ToolCallSchema:
    """Schema definition for a single tool's expected parameters."""

    required_params: Optional[List[str]] = None
    """Required parameter names that must be present in the tool call arguments."""

    param_types: Optional[Dict[str, str]] = None
    """Parameter name → expected type name (e.g., {'query': 'str', 'limit': 'int'})."""

    allowed_params: Optional[List[str]] = None
    """Allowed parameter names. Extra params are rejected when set."""


@dataclass
class ToolConstraint:
    """Additional constraint applied across all tool calls."""

    max_argument_length: Optional[int] = None
    """Maximum length (chars) for any single argument value (stringified)."""

    max_tool_calls: Optional[int] = None
    """Maximum total number of tool calls in a single response."""

    disallowed_tools: Optional[List[str]] = None
    """Disallowed function names."""


@dataclass
class ToolCallValidationConfig:
    """Configuration object for ToolCallValidationModule."""

    schemas: Optional[Dict[str, ToolCallSchema]] = None
    """Tool name → expected parameter schema mapping."""

    constraints: List[ToolConstraint] = field(default_factory=list)
    """Additional constraints applied to all tool calls."""

    require_schema: bool = False
    """If True, tool calls without a matching schema are rejected."""


# ---------------------------------------------------------------------------
# Internal Types
# ---------------------------------------------------------------------------


@dataclass
class ParsedToolCall:
    """A normalized tool call extracted from the response."""

    id: Optional[str]
    name: str
    arguments: Dict[str, Any]


@dataclass
class ValidationFailure:
    """A single validation failure for a tool call."""

    tool_name: str
    tool_call_id: Optional[str]
    reason: str


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class ToolCallValidationModule:
    """Verifies tool calls in the LLM response conform to expected schemas
    and parameter constraints.

    Returns DENY with ``remediation: 'resample'`` when a tool call is
    malformed or violates configured constraints.

    When no tool calls are present in the response, the module returns ALLOW.
    """

    name: str = "ToolCallValidationModule"
    version: str = "1.0.0"

    def __init__(self, config: Optional[ToolCallValidationConfig] = None) -> None:
        cfg = config or ToolCallValidationConfig()
        self._schemas = cfg.schemas or {}
        self._constraints = cfg.constraints
        self._require_schema = cfg.require_schema

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate tool calls in the response for validation.

        Args:
            request: The module evaluation request (dict-like, includes _response).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        tool_calls = self._extract_tool_calls(request)

        # No tool calls present — allow
        if not tool_calls:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.tool_call_validation",
                "metadata": {
                    "module": self.name,
                },
            }

        failures: List[ValidationFailure] = []

        # Check global constraints: max tool calls
        for constraint in self._constraints:
            if (
                constraint.max_tool_calls is not None
                and len(tool_calls) > constraint.max_tool_calls
            ):
                failures.append(
                    ValidationFailure(
                        tool_name="*",
                        tool_call_id=None,
                        reason=f"Too many tool calls: {len(tool_calls)} > max {constraint.max_tool_calls}",
                    )
                )

        # Validate each tool call
        for tool_call in tool_calls:
            # Check disallowed tools
            for constraint in self._constraints:
                if (
                    constraint.disallowed_tools
                    and tool_call.name in constraint.disallowed_tools
                ):
                    failures.append(
                        ValidationFailure(
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            reason=f"Tool '{tool_call.name}' is disallowed",
                        )
                    )

            # Check schema requirement
            schema = self._schemas.get(tool_call.name)
            if not schema and self._require_schema:
                failures.append(
                    ValidationFailure(
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        reason=f"No schema defined for tool '{tool_call.name}'",
                    )
                )
                continue

            # Validate against schema if one exists
            if schema:
                self._validate_against_schema(tool_call, schema, failures)

            # Check argument length constraints
            self._validate_constraints(tool_call, failures)

        if failures:
            return {
                "action": "DENY",
                "reason_codes": ["TOOL_CALL_INVALID"],
                "event_type": "pipeline.tool_call_validation",
                "metadata": {
                    "module": self.name,
                    "remediation": "resample",
                    "failures": [self._failure_to_dict(f) for f in failures],
                    "failure_count": len(failures),
                    "tool_call_count": len(tool_calls),
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.tool_call_validation",
            "metadata": {
                "module": self.name,
                "tool_call_count": len(tool_calls),
                "validated_tools": [tc.name for tc in tool_calls],
            },
        }

    def _extract_tool_calls(self, request: Any) -> List[ParsedToolCall]:
        """Extract tool calls from the response, checking multiple formats.

        Supported locations:
        1. ``request["_response"]["tool_calls"]`` — direct array
        2. ``request["_response"]["choices"][].message.tool_calls`` — OpenAI format
        """
        if not isinstance(request, dict):
            return []

        response = request.get("_response")
        if not isinstance(response, dict):
            return []

        tool_calls: List[ParsedToolCall] = []

        # Check direct tool_calls array
        direct_tool_calls = response.get("tool_calls")
        if isinstance(direct_tool_calls, list):
            for tc in direct_tool_calls:
                parsed = self._parse_tool_call(tc)
                if parsed:
                    tool_calls.append(parsed)
            return tool_calls

        # Check OpenAI-style choices[].message.tool_calls
        choices = response.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if isinstance(choice, dict):
                    message = choice.get("message")
                    if isinstance(message, dict):
                        msg_tool_calls = message.get("tool_calls")
                        if isinstance(msg_tool_calls, list):
                            for tc in msg_tool_calls:
                                parsed = self._parse_tool_call(tc)
                                if parsed:
                                    tool_calls.append(parsed)

        return tool_calls

    def _parse_tool_call(self, tc: Any) -> Optional[ParsedToolCall]:
        """Parse a single tool call object into a normalized format."""
        if not isinstance(tc, dict):
            return None

        tc_id = tc.get("id") if isinstance(tc.get("id"), str) else None

        # OpenAI-style: { id, type, function: { name, arguments } }
        fn = tc.get("function")
        if isinstance(fn, dict):
            name = fn.get("name")
            if not isinstance(name, str) or not name:
                return None
            args = self._parse_arguments(fn.get("arguments"))
            return ParsedToolCall(id=tc_id, name=name, arguments=args)

        # Flat format: { name, arguments }
        name = tc.get("name")
        if not isinstance(name, str) or not name:
            return None
        args = self._parse_arguments(tc.get("arguments"))
        return ParsedToolCall(id=tc_id, name=name, arguments=args)

    @staticmethod
    def _parse_arguments(args: Any) -> Dict[str, Any]:
        """Parse arguments from a tool call."""
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                return {}

        if isinstance(args, dict):
            return args

        return {}

    def _validate_against_schema(
        self,
        tool_call: ParsedToolCall,
        schema: ToolCallSchema,
        failures: List[ValidationFailure],
    ) -> None:
        """Validate a tool call against its schema."""
        args = tool_call.arguments

        # Check required parameters
        if schema.required_params:
            for param in schema.required_params:
                if args.get(param) is None:
                    failures.append(
                        ValidationFailure(
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            reason=f"Missing required parameter '{param}' for tool '{tool_call.name}'",
                        )
                    )

        # Check parameter types
        if schema.param_types:
            type_map = {
                "str": str, "string": str,
                "int": int, "number": (int, float),
                "float": float,
                "bool": bool, "boolean": bool,
                "list": list, "array": list,
                "dict": dict, "object": dict,
            }
            for param, expected_type_name in schema.param_types.items():
                value = args.get(param)
                if value is not None:
                    expected_type = type_map.get(expected_type_name.lower())
                    if expected_type and not isinstance(value, expected_type):
                        actual_type = type(value).__name__
                        failures.append(
                            ValidationFailure(
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                                reason=(
                                    f"Type mismatch for parameter '{param}' of tool "
                                    f"'{tool_call.name}': expected {expected_type_name}, got {actual_type}"
                                ),
                            )
                        )

        # Check allowed parameters (reject extra params)
        if schema.allowed_params:
            allowed_set: Set[str] = set(schema.allowed_params)
            for param in args:
                if param not in allowed_set:
                    failures.append(
                        ValidationFailure(
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            reason=f"Unexpected parameter '{param}' for tool '{tool_call.name}'",
                        )
                    )

    def _validate_constraints(
        self,
        tool_call: ParsedToolCall,
        failures: List[ValidationFailure],
    ) -> None:
        """Validate a tool call against global constraints."""
        for constraint in self._constraints:
            # Check max argument length
            if constraint.max_argument_length is not None:
                for param, value in tool_call.arguments.items():
                    stringified = value if isinstance(value, str) else json.dumps(value)
                    if len(stringified) > constraint.max_argument_length:
                        failures.append(
                            ValidationFailure(
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                                reason=(
                                    f"Argument '{param}' of tool '{tool_call.name}' exceeds "
                                    f"max length: {len(stringified)} > {constraint.max_argument_length}"
                                ),
                            )
                        )

    @staticmethod
    def _failure_to_dict(failure: ValidationFailure) -> Dict[str, Any]:
        """Convert a ValidationFailure to a dictionary."""
        result: Dict[str, Any] = {
            "tool_name": failure.tool_name,
            "reason": failure.reason,
        }
        if failure.tool_call_id is not None:
            result["tool_call_id"] = failure.tool_call_id
        return result
