"""Multi-Stage Defense Pipeline — Tool Allowlist Module (Python SDK).

Inspects tool call requests and returns DENY with reason code TOOL_NOT_ALLOWED
when any requested tool is not on the configured allowlist.

Supports multiple tool field formats:
- ``request["tool"]`` — single tool name (string)
- ``request["tool_name"]`` — single tool name (string)
- ``request["tools"]`` — array of tool names or tool objects with a ``name`` field

Module: pipeline/modules/pre/tool_allowlist
Requirements: 6.5, 6.6, 6.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ToolAllowlistConfig:
    """Configuration object for ToolAllowlistModule."""

    allowlist: List[str] = field(default_factory=list)
    """List of permitted tool names. Matched case-sensitively."""


# ---------------------------------------------------------------------------
# Module Implementation
# ---------------------------------------------------------------------------


class ToolAllowlistModule:
    """Inspects tool call requests and denies those containing tools not on
    the configured allowlist.

    Returns ALLOW when no tool calls are found or all requested tools
    are permitted.

    Tool detection checks (in order):
    1. ``request["tool"]`` — single tool name string
    2. ``request["tool_name"]`` — single tool name string
    3. ``request["tools"]`` — array of tool names (strings) or tool objects
       with a ``name`` field
    """

    name: str = "ToolAllowlistModule"
    version: str = "1.0.0"

    def __init__(self, config: ToolAllowlistConfig) -> None:
        self._allowlist: Set[str] = set(config.allowlist)

    async def evaluate(
        self, request: Any, ctx: Any, policy: Any
    ) -> Dict[str, Any]:
        """Evaluate the request for tool calls against the allowlist.

        Args:
            request: The module evaluation request (dict-like).
            ctx: The module context.
            policy: The policy configuration (unused).

        Returns:
            A ModuleResult dict with action, reason_codes, event_type, metadata.
        """
        requested_tools = self._extract_tools(request)

        # If no tool calls found, allow the request
        if not requested_tools:
            return {
                "action": "ALLOW",
                "reason_codes": [],
                "event_type": "pipeline.tool_allowlist",
                "metadata": {
                    "module": self.name,
                },
            }

        # Check each tool against the allowlist
        blocked_tools = [t for t in requested_tools if t not in self._allowlist]

        if blocked_tools:
            return {
                "action": "DENY",
                "reason_codes": ["TOOL_NOT_ALLOWED"],
                "event_type": "pipeline.tool_allowlist",
                "metadata": {
                    "module": self.name,
                    "blocked_tools": blocked_tools,
                    "requested_tools": requested_tools,
                    "allowlist": sorted(self._allowlist),
                },
            }

        return {
            "action": "ALLOW",
            "reason_codes": [],
            "event_type": "pipeline.tool_allowlist",
            "metadata": {
                "module": self.name,
                "requested_tools": requested_tools,
            },
        }

    def _extract_tools(self, request: Any) -> List[str]:
        """Extract tool names from the request, checking multiple possible field formats."""
        if not isinstance(request, dict):
            return []

        tools: List[str] = []

        # Check `request["tool"]` (single tool name)
        tool = request.get("tool")
        if isinstance(tool, str) and tool:
            tools.append(tool)

        # Check `request["tool_name"]` (single tool name, alternative field)
        tool_name = request.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            tools.append(tool_name)

        # Check `request["tools"]` (array of tool names or tool objects)
        tools_field = request.get("tools")
        if isinstance(tools_field, list):
            for entry in tools_field:
                if isinstance(entry, str) and entry:
                    tools.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("name")
                    if isinstance(name, str) and name:
                        tools.append(name)

        return tools
