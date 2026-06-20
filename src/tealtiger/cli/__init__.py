"""CLI interface for TealTiger SDK.

Provides command-line tools for:
- Policy testing
- Policy validation
- Configuration validation
- Report generation
"""

from .test import test
from .validate import validate

__all__ = ['test', 'validate']
