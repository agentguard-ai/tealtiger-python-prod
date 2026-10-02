"""TealTiger integrations with external observability and monitoring platforms.

Each integration in this package depends on a third-party SDK that TealTiger
does not require: ``agentops``, ``langfuse``, ``opik``, and ``google-adk``. Those
modules raise ``ImportError`` at import time when their SDK is absent.

This module therefore resolves its exports lazily (PEP 562). Previously it
imported all four eagerly, which meant a single missing optional SDK made the
whole subpackage unimportable — ``from tealtiger.integrations.google_adk import
TealTigerCallback`` failed with "agentops is required for this integration"
even though the Google ADK callback has no third-party dependency at all,
because importing a submodule first executes its parent package.

With lazy resolution you pay only for what you import, and the ImportError you
get names the SDK you actually asked for. Install extras as needed::

    pip install tealtiger[agentops]
    pip install tealtiger[integrations]   # all of them
"""

from typing import Any

# Export name -> module that defines it. Kept in sync with __all__ below, which
# the test suite asserts against so the two cannot drift.
_EXPORTS = {
    "AgentOpsGovernanceReporter": "tealtiger.integrations.agentops",
    "TealTigerCallback": "tealtiger.integrations.google_adk",
    "LangfuseGovernanceExporter": "tealtiger.integrations.langfuse",
    "FalsePositiveRateMetric": "tealtiger.integrations.opik",
    "GovernanceAccuracyMetric": "tealtiger.integrations.opik",
    "GovernanceLatencyMetric": "tealtiger.integrations.opik",
    "GovernanceMultiMetric": "tealtiger.integrations.opik",
    "PIIDetectionMetric": "tealtiger.integrations.opik",
}

__all__ = [
    "AgentOpsGovernanceReporter",
    "FalsePositiveRateMetric",
    "GovernanceAccuracyMetric",
    "GovernanceLatencyMetric",
    "GovernanceMultiMetric",
    "LangfuseGovernanceExporter",
    "PIIDetectionMetric",
    "TealTigerCallback",
]


def __getattr__(name: str) -> Any:
    """Import an integration on first access.

    Raises AttributeError for unknown names (so ``hasattr`` and
    ``from ... import`` behave normally) and propagates the integration's own
    ImportError, which names the missing SDK, unchanged.
    """
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    value = getattr(import_module(module_name), name)
    # Cache on the module so subsequent lookups skip __getattr__ entirely.
    globals()[name] = value
    return value


def __dir__() -> list:
    return sorted(__all__)
