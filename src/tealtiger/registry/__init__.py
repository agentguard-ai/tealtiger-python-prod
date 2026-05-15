"""TealTiger v1.3 — TealRegistry v2 (Python SDK).

This package contains the Python implementation of TealRegistry v2 detectors:
- Tool description injection scanner
- Adapter composition allowlist
"""

from .detectors import (
    CompositionAllowlist,
    check_composition,
    scan_tool_description,
)

__all__ = [
    "scan_tool_description",
    "CompositionAllowlist",
    "check_composition",
]
