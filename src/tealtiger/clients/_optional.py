"""Helpers for optional provider SDK dependencies."""

from typing import NoReturn


def missing_provider_dependency_error(provider: str, extra: str, package: str) -> ImportError:
    """Build a consistent install hint for provider-specific dependencies."""
    return ImportError(
        f"{provider} support requires the optional '{package}' package. "
        f"Install it with `pip install 'tealtiger[{extra}]'`."
    )


def raise_missing_provider_dependency(provider: str, extra: str, package: str) -> NoReturn:
    """Raise a consistent install hint for provider-specific dependencies."""
    raise missing_provider_dependency_error(provider, extra, package)
