"""CLI interface for TealTiger SDK."""

import click

from .check import check
from .test import test


@click.group()
def cli() -> None:
    """TealTiger command-line interface."""
    pass


cli.add_command(test)
cli.add_command(check)

__all__ = ["cli", "test", "check"]
