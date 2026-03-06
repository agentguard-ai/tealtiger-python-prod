"""CLI interface for TealTiger SDK.

Provides command-line tools for:
- Policy testing
- Configuration validation
- Report generation
"""

from .test import test

__all__ = ['test']
