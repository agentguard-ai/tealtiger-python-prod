"""TEEC v2.1 Governance Contract — Error Types (Python SDK).

Module: core/engine/v2_1/errors
"""


class SealConfigurationError(Exception):
    """Raised when seal_secret is required but not configured.

    TEEC v2.1 governance requires a seal_secret to compute the
    GovernanceSeal HMAC. This error is raised at initialization
    time when governance mode is enabled but no secret is provided.
    """

    def __init__(self, context: str = "") -> None:
        msg = (
            "seal_secret is required for TEEC v2.1 governance. "
            f"{context or 'Provide seal_secret in engine options or ObserveConfig.governance_seal_secret.'}"
        )
        super().__init__(msg)
        self.code = "SEAL_SECRET_MISSING"
