"""Multi-Stage Defense Pipeline — Error Hierarchy (Python SDK).

Pipeline-specific exception classes for construction-time validation,
runtime module failures, and remediation budget exhaustion.

Module: pipeline/errors
"""


class PipelineError(Exception):
    """Base class for all pipeline errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code for programmatic handling.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ModuleValidationError(PipelineError):
    """Thrown at construction when a module doesn't implement the TealModule interface.

    Attributes:
        module_name: Name of the non-conforming module.
        missing_fields: List of required TealModule fields that are missing.
    """

    def __init__(self, module_name: str, missing_fields: list[str]) -> None:
        self.module_name = module_name
        self.missing_fields = missing_fields
        super().__init__(
            f"Module '{module_name}' does not implement TealModule interface. "
            f"Missing: {', '.join(missing_fields)}",
            "MODULE_VALIDATION_FAILED",
        )


class PipelineConfigError(PipelineError):
    """Thrown when pipeline configuration is invalid.

    Examples: neither observeProxy nor providerClient provided,
    invalid resample_budget value, etc.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, "PIPELINE_CONFIG_INVALID")


class ModuleTimeoutError(PipelineError):
    """Thrown when a module exceeds its evaluation timeout.

    Attributes:
        module_name: Name of the module that timed out.
        timeout_ms: The configured timeout in milliseconds.
    """

    def __init__(self, module_name: str, timeout_ms: int) -> None:
        self.module_name = module_name
        self.timeout_ms = timeout_ms
        super().__init__(
            f"Module '{module_name}' exceeded evaluation timeout of {timeout_ms}ms",
            "MODULE_TIMEOUT",
        )


class ResampleBudgetExhaustedError(PipelineError):
    """Thrown internally when the resample budget is exhausted.

    This error is not exposed to callers — it is caught by the pipeline
    orchestrator and converted into a PipelineResult with
    ``remediation_exhausted=True``.

    Attributes:
        budget: The configured resample budget.
        attempts: The number of resample attempts made.
    """

    def __init__(self, budget: int, attempts: int) -> None:
        self.budget = budget
        self.attempts = attempts
        super().__init__(
            f"Resample budget exhausted: {attempts}/{budget} attempts used",
            "RESAMPLE_BUDGET_EXHAUSTED",
        )
