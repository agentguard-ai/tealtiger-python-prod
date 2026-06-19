"""Main CLI entry point for TealTiger SDK.

Provides a Click group with subcommands:
- test: Run policy tests
- validate: Validate policy files
"""

import click


@click.group()
@click.version_option(version="1.3.0", prog_name="tealtiger")
def cli() -> None:
    """TealTiger - AI agent security and governance CLI."""
    pass


# Import subcommands and register them
from .test import test  # noqa: E402
from .validate import validate  # noqa: E402

cli.add_command(test)
cli.add_command(validate)


if __name__ == '__main__':
    cli()
