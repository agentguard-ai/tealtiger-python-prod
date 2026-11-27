"""Policy evaluation for the rule types this SDK implements.

Scope
-----
**Tool allowlist only.** That is the one rule type the TealTiger policy conformance
specification defines completely (§6), and the only one with a verified genuine denial
in any implementation. Every other rule type — content, PII, prompt injection, code
execution, cost, rate limiting, memory governance — is UNSPECIFIED in v0.1 (§7) and is
deliberately **not** evaluated here.

That boundary is the point. The defect this module exists to replace returned
``{"allowed": True}`` for every request without reading the policy at all, which made
a published governance API appear to enforce while enforcing nothing. An evaluator that
quietly allows the rule types it has not implemented would be the same defect in a
smaller box, so :func:`evaluate_policies` reports which sections it did not evaluate
rather than folding them into an allow.

Requirement IDs (TA-1 … TA-8) refer to §6.2 of the specification. Each is cited at the
branch that implements it, so a reader can check the code against the document without
holding both in their head.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from .types import CLAUSE_NONE, ReasonCode

WILDCARD_TOOL = "*"
"""The reserved fallback key in the ``tools`` map (TA-8).

A literal key, not a pattern. TA-6 forbids globbing and prefix matching; `*` is exempt
because it is matched as a key rather than applied as a pattern.
"""

SUPPORTED_RULE_TYPES: Tuple[str, ...] = ("tools",)
"""Policy sections this evaluator implements.

Everything else present in a policy document is reported by
:func:`unsupported_sections` rather than evaluated. §9.1 requires an implementation to
publish, per rule type, one of ``enforced``, ``declared-unsupported`` or ``unspecified``;
this tuple is the machine-readable half of that claim.
"""


@dataclass(frozen=True)
class ClauseOutcome:
    """What one policy section decided, and which clause decided it.

    Frozen because §3.6 requires determinism: the same policy, context and mode must
    produce the same action, the same reason codes *in the same order*, and the same
    clause. An outcome that callers can mutate is a way for that to stop being true.
    """

    allowed: bool
    reason_codes: Tuple[ReasonCode, ...]
    triggering_clause: str
    reason: str

    def __post_init__(self) -> None:
        if not self.allowed and self.triggering_clause == CLAUSE_NONE:
            raise ValueError(
                "A denying outcome must name the clause that produced it (§3.5); "
                f"got triggering_clause={CLAUSE_NONE!r}."
            )


def _allowed() -> ClauseOutcome:
    """The shape of 'this section does not object'.

    §5.3: an empty or absent policy allows, with ``POLICY_COMPLIANT`` and a
    ``triggering_clause`` of ``none``. The same shape serves a section that examined the
    request and permitted it, because in both cases no clause denied.
    """
    return ClauseOutcome(
        allowed=True,
        reason_codes=(ReasonCode.POLICY_COMPLIANT,),
        triggering_clause=CLAUSE_NONE,
        reason="Request allowed and compliant with policy",
    )


def _denied(clause: str, reason: str, *, code: ReasonCode) -> ClauseOutcome:
    """A denial, with its reason codes in the order TA-2 and TA-4 require.

    ``POLICY_VIOLATION`` first, then the specific code. §3.6 makes the order part of the
    contract rather than an incidental detail, so it is produced in one place.
    """
    return ClauseOutcome(
        allowed=False,
        reason_codes=(ReasonCode.POLICY_VIOLATION, code),
        triggering_clause=clause,
        reason=reason,
    )


def _tool_entry_permits(tools: Mapping[str, Any], key: str) -> bool:
    """Read ``tools[key].allowed``, rejecting anything that is not a boolean.

    §6.1 makes ``allowed`` required and boolean, and says nothing about what to do when
    it is absent or some other type. Both available readings are bad:

    - **Deny** turns a typo into a silent, total outage attributed to a clause the author
      believes says ``true``.
    - **Allow** turns a typo into silent non-enforcement, which is the defect this whole
      module exists to remove.

    So neither: a policy that cannot be read is a policy-authoring error, not a
    governance verdict about this request, and it is raised rather than decided. Loud and
    immediate beats either silent outcome.

    Recorded as a gap in the specification; see this module's tests for the pinned
    behaviour.
    """
    entry = tools[key]
    if not isinstance(entry, Mapping):
        raise ValueError(
            f"Malformed tool policy at tools.{key}: expected a mapping with an "
            f"'allowed' boolean, got {type(entry).__name__}."
        )
    if "allowed" not in entry:
        raise ValueError(
            f"Malformed tool policy at tools.{key}: 'allowed' is required (§6.1) and is "
            "absent. Refusing to guess whether this tool is permitted."
        )
    allowed = entry["allowed"]
    if not isinstance(allowed, bool):
        raise ValueError(
            f"Malformed tool policy at tools.{key}.allowed: expected a boolean, got "
            f"{type(allowed).__name__} ({allowed!r})."
        )
    return allowed


def evaluate_tools_section(
    context: Mapping[str, Any], tools: Mapping[str, Any]
) -> ClauseOutcome:
    """Evaluate the ``tools`` section against a request. TA-1 … TA-8.

    The caller is responsible for deciding that the section applies at all; see
    :func:`evaluate_policies` for TA-7's absent-versus-empty distinction.
    """
    if not isinstance(tools, Mapping):
        raise ValueError(
            f"Malformed tool policy: 'tools' must be a mapping, got {type(tools).__name__}."
        )

    tool = context.get("tool")

    # TA-1 — a `tool.execute` request must name a tool.
    #
    # §4.1(a): report the *precondition* that failed, with a malformed-input reason
    # code, and not TOOL_NOT_ALLOWED. The distinction is the whole requirement. A
    # governance denial about a real tool and a client that forgot a field are different
    # events, and reporting the second as the first is what let TypeScript substitute
    # `language='unknown'` and then deny on an allowlist, producing 13 cases that looked
    # like working code inspection.
    #
    # Only meaningful where a tool policy exists: with no tool policy there is no clause
    # the missing field could be required by.
    if context.get("action") == "tool.execute" and not tool:
        return _denied(
            "request.tool.missing",
            "Request action is 'tool.execute' but no tool was supplied",
            code=ReasonCode.INVALID_REQUEST,
        )

    # No tool named and not a tool.execute request: this section has nothing to say.
    # The corpus pins this as `non-tool-action-unaffected` — a chat request under a
    # policy that denies file_delete is allowed, and nothing is attributed.
    if not tool:
        return _allowed()

    # TA-6 — exact, case-sensitive, no normalisation. `in` on a mapping is precisely
    # that: 'Search', 'FILE_DELETE' and 'search ' are three different keys from
    # 'search', and each lands on TA-4 rather than quietly matching.
    has_exact = tool in tools
    has_wildcard = WILDCARD_TOOL in tools

    # TA-4 — absent from the map, with no fallback, is denied. Default-deny is
    # normative: an unknown tool is not an allowed tool.
    #
    # TA-5 — the clause is `tools.<tool>.absent`, deliberately distinct from the
    # `tools.<tool>.allowed` used when an entry exists and denies. Both carry
    # TOOL_NOT_ALLOWED; they are different policy facts and an operator needs to tell
    # "nobody configured this tool" from "somebody configured this tool as forbidden".
    if not has_exact and not has_wildcard:
        return _denied(
            f"tools.{tool}.absent",
            f"Tool '{tool}' is not defined in policy",
            code=ReasonCode.TOOL_NOT_ALLOWED,
        )

    # TA-8(a) — a specific entry takes precedence over the `*` fallback, whether it
    # allows or denies.
    #
    # TA-8(b) — attribute the decision to whichever entry actually governed it, so a
    # denial inherited from `*` reports `tools.*.allowed` rather than naming a specific
    # entry that does not exist. Without this an operator cannot distinguish a blanket
    # default from a rule somebody wrote about this tool.
    clause_owner = tool if has_exact else WILDCARD_TOOL

    # TA-2 — an entry configured `allowed: false` denies.
    # TA-3 — `allowed: true` means this section permits; other sections still apply,
    #        which aggregation enforces.
    if not _tool_entry_permits(tools, clause_owner):
        return _denied(
            f"tools.{clause_owner}.allowed",
            f"Tool '{tool}' is blocked by policy",
            code=ReasonCode.TOOL_NOT_ALLOWED,
        )

    return _allowed()


def unsupported_sections(policies: Optional[Mapping[str, Any]]) -> Tuple[str, ...]:
    """Sections present in the policy that this evaluator does not implement.

    The caller decides what to do about them. This function exists so that the answer
    cannot be "nothing, silently": a policy section that is configured but unevaluated is
    the exact shape of the defect that made a published governance API meaningless, and
    the only defence is for it to be visible at the boundary.
    """
    if not policies:
        return ()
    return tuple(
        name
        for name in policies
        if name not in SUPPORTED_RULE_TYPES and policies[name] is not None
    )


def aggregate_outcomes(outcomes: Sequence[ClauseOutcome]) -> ClauseOutcome:
    """Combine section outcomes. §5.3: aggregation is AND.

    The request is allowed only if every applicable section allows it. §5.2 permits
    short-circuiting on the first denial, so the first denying outcome supplies the
    attribution — which keeps the reported clause the one that actually decided, rather
    than the last one to be consulted.
    """
    for outcome in outcomes:
        if not outcome.allowed:
            return outcome
    return _allowed()


def evaluate_policies(
    context: Mapping[str, Any], policies: Optional[Mapping[str, Any]]
) -> Tuple[ClauseOutcome, Tuple[str, ...]]:
    """Evaluate every supported section of ``policies`` against ``context``.

    Returns the aggregated outcome **and** the sections that were not evaluated. Both
    halves matter: a caller that ignores the second is reporting an allow it has not
    earned, and this signature is deliberately awkward to ignore.

    TA-7 governs the ``tools`` section's applicability, and the distinction is
    load-bearing:

    - ``tools`` **absent** (or ``None``) — no tool policy is configured, the section is
      inapplicable, and §5.3 governs.
    - ``tools: {}`` **present** — an allowlist that permits nothing. It contains no
      entries and no ``*``, so TA-4 applies and every tool is denied as absent.

    Collapsing the two would mean a misconfiguration producing an empty map silently
    permits every tool. Fail-closed is the correct reading for a governance product.
    """
    outcomes = []

    tools = policies.get("tools") if policies else None
    if tools is not None:
        outcomes.append(evaluate_tools_section(context, tools))

    return aggregate_outcomes(outcomes), unsupported_sections(policies)
