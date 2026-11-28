"""Validate a policy document before the engine has to evaluate it.

**Which policy.** This validates the policy :class:`~tealtiger.core.engine.TealEngine`
evaluates — the sectioned document whose ``tools`` entries the conformance specification
defines in §6.1, and the shape the shared conformance corpus uses. It is deliberately
**not** about :class:`tealtiger.policy.PolicyBuilder`'s ``Policy``, a separate
rules-and-conditions model that the engine cannot evaluate at all. Two policy models
exist in this package; only one is enforced, and conflating them is how a user ends up
validating a document nothing will ever read.

**Why it reuses the evaluator rather than re-deriving the rules.** Every structural check
here asks the evaluator's own reader whether an entry is legible, so there is exactly one
implementation of "what makes a tool entry valid". A validator with its own copy of those
rules is a second opinion waiting to drift from the first, which is the defect this
module's own design notes exist to avoid. The consequence worth stating: **this validator
cannot pass a policy the engine would reject**, because it is asking the engine.

**Two questions, not one.** A policy can be perfectly well formed and still beyond what
this build enforces — §7 leaves most rule types UNSPECIFIED, and a document written for a
more capable implementation is not malformed. So the result answers both separately:
``well_formed`` and ``enforceable_here``. Collapsing them into a single ``valid`` would
force one of two wrong answers.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from .policy_evaluator import (
    SUPPORTED_RULE_TYPES,
    WILDCARD_TOOL,
    _tool_entry_permits,
    unsupported_sections,
)

ERROR = "error"
"""Severity: the engine cannot evaluate this document."""

WARNING = "warning"
"""Severity: legal, enforced as written, and probably not what was meant."""


@dataclass(frozen=True)
class ValidationFinding:
    """One problem with a policy document.

    ``code`` is the stable, machine-readable part. The ``message`` may be reworded; the
    code is what a caller should branch on, for the same reason decisions carry reason
    codes rather than only prose.
    """

    severity: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class PolicyValidationResult:
    """The outcome of validating a policy document."""

    well_formed: bool
    """No structural errors: every section and entry the engine would read is legible."""

    enforceable_here: bool
    """This build can enforce everything the document configures.

    False does not imply malformed. A policy configuring content governance is a
    legitimate document that this SDK declines to evaluate (§9.2), and
    :meth:`TealEngine.evaluate_with_mode` will refuse it rather than partly honour it.
    """

    findings: Tuple[ValidationFinding, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> Tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity == ERROR)

    @property
    def warnings(self) -> Tuple[ValidationFinding, ...]:
        return tuple(f for f in self.findings if f.severity == WARNING)

    def __bool__(self) -> bool:
        """True when the document is both well formed and enforceable here.

        Defined explicitly because the alternative — a caller writing
        ``if result:`` against a dataclass that is always truthy — would silently
        treat every policy as acceptable.
        """
        return self.well_formed and self.enforceable_here


def validate_policy(policies: Optional[Mapping[str, Any]]) -> PolicyValidationResult:
    """Check a policy document for problems the engine would hit, or silently accept.

    Returns findings rather than raising, so a caller can report every problem at once.
    The engine raises on the first unreadable entry it reaches, which is right for a
    request path and wrong for a configuration check.
    """
    findings: list[ValidationFinding] = []

    if policies is None:
        return PolicyValidationResult(
            well_formed=True,
            enforceable_here=True,
            findings=(
                ValidationFinding(
                    WARNING,
                    "NO_POLICY",
                    "",
                    "No policy document. Nothing will be enforced; every request is "
                    "allowed with POLICY_COMPLIANT (§5.3).",
                ),
            ),
        )

    if not isinstance(policies, Mapping):
        return PolicyValidationResult(
            well_formed=False,
            enforceable_here=False,
            findings=(
                ValidationFinding(
                    ERROR,
                    "POLICY_NOT_A_MAPPING",
                    "",
                    f"A policy document must be a mapping of rule type to configuration, "
                    f"got {type(policies).__name__}.",
                ),
            ),
        )

    structurally_broken = False

    # Sections this build cannot enforce. Asked of the evaluator so the validator and
    # the engine cannot disagree about what is supported.
    unenforceable = unsupported_sections(policies)
    for section in unenforceable:
        findings.append(
            ValidationFinding(
                ERROR,
                "SECTION_NOT_ENFORCEABLE",
                section,
                f"Rule type '{section}' is configured but UNSPECIFIED in conformance "
                f"specification v0.1 §7, so this SDK does not implement it. "
                f"evaluate_with_mode() will refuse this policy rather than enforce the "
                f"rest of it. Enforced here: {', '.join(SUPPORTED_RULE_TYPES)}.",
            )
        )

    tools = policies.get("tools")

    if tools is None and "tools" in policies:
        findings.append(
            ValidationFinding(
                WARNING,
                "SECTION_NULL",
                "tools",
                "The 'tools' section is present but null, which is treated as absent: "
                "no tool policy is configured and no tool is checked. Use '{}' to "
                "permit nothing, or remove the key.",
            )
        )
    elif tools is not None:
        if not isinstance(tools, Mapping):
            structurally_broken = True
            findings.append(
                ValidationFinding(
                    ERROR,
                    "SECTION_NOT_A_MAPPING",
                    "tools",
                    f"The 'tools' section must be a mapping of tool name to "
                    f"configuration, got {type(tools).__name__}.",
                )
            )
        else:
            findings.extend(_validate_tools(tools))
            structurally_broken = structurally_broken or any(
                f.severity == ERROR and f.code.startswith("TOOL_")
                for f in findings
            )

    if not any(policies.get(name) is not None for name in SUPPORTED_RULE_TYPES):
        if not unenforceable:
            findings.append(
                ValidationFinding(
                    WARNING,
                    "NOTHING_ENFORCED",
                    "",
                    "The document configures no rule type this SDK enforces, so every "
                    f"request will be allowed. Enforced here: "
                    f"{', '.join(SUPPORTED_RULE_TYPES)}.",
                )
            )

    return PolicyValidationResult(
        well_formed=not structurally_broken,
        enforceable_here=not unenforceable and not structurally_broken,
        findings=tuple(findings),
    )


def _validate_tools(tools: Mapping[str, Any]) -> list[ValidationFinding]:
    """Check every entry in the ``tools`` section. TA-2, TA-6, TA-7, TA-8."""
    findings: list[ValidationFinding] = []

    # TA-7: an empty map is an allowlist that permits nothing. Legal, fail-closed, and
    # more often a misconfiguration than an intent — so it is surfaced rather than
    # accepted in silence.
    if not tools:
        findings.append(
            ValidationFinding(
                WARNING,
                "TOOL_MAP_EMPTY",
                "tools",
                "An empty 'tools' map is an allowlist that permits nothing: every tool "
                "is denied as absent. If that is intended, it is correct; if the map "
                "was meant to be populated, nothing will work.",
            )
        )

    for name in tools:
        if not isinstance(name, str):
            findings.append(
                ValidationFinding(
                    ERROR,
                    "TOOL_NAME_NOT_A_STRING",
                    f"tools.{name}",
                    f"Tool names must be strings, got {type(name).__name__}.",
                )
            )
            continue

        # Ask the evaluator's own reader. One implementation of the rule, so a policy
        # this validator accepts is one the engine can read.
        try:
            permits = _tool_entry_permits(tools, name)
        except ValueError as exc:
            findings.append(
                ValidationFinding(
                    ERROR, "TOOL_ENTRY_UNREADABLE", f"tools.{name}", str(exc)
                )
            )
            continue

        # TA-6: names match exactly. Whitespace in a key is legal and almost certainly
        # a typo, because no request will ever carry it.
        if name != name.strip():
            findings.append(
                ValidationFinding(
                    WARNING,
                    "TOOL_NAME_HAS_WHITESPACE",
                    f"tools.{name}",
                    f"Tool name {name!r} has leading or trailing whitespace. Names are "
                    "matched exactly with no normalisation (TA-6), so this entry only "
                    "matches a request carrying the same whitespace.",
                )
            )

        # TA-8(d): the fallback entry is the only way to disable default-deny, so a
        # permissive one is worth naming out loud.
        if name == WILDCARD_TOOL and permits:
            findings.append(
                ValidationFinding(
                    WARNING,
                    "WILDCARD_PERMITS_EVERYTHING",
                    "tools.*.allowed",
                    "The '*' fallback is configured 'allowed: true', which permits every "
                    "tool without an entry of its own and disables default-deny. "
                    "Decisions it produces are attributed to 'tools.*.allowed', so this "
                    "is visible in the audit trail — but it is a blanket permit.",
                )
            )

    return findings
