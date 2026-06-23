"""CLI interface for TealTiger SDK.

Provides command-line tools for:
- Policy testing
- Policy validation
- Configuration validation
- Report generation
"""

import click

from .test import test as test_cmd
from .validate import validate


@click.group()
def cli():
    """TealTiger CLI - AI agent security platform."""
    pass


cli.add_command(test_cmd)
cli.add_command(validate)

if __name__ == "__main__":
    cli()
