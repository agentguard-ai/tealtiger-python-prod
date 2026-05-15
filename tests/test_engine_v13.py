"""Tests for TealEngine v1.3 — Governance Bundle Engine (Python SDK).

Covers:
- FREEZE rule blocks matching actions
- PLAN_ONLY blocks side-effecting actions
- NHI revoked/suspended denial
- ZSP grant validation
- Backward compatibility (no v1.3 features = v1.2 behavior)
"""

import time
from typing import List, Literal, Optional

import pytest

from tealtiger.core.engine.v1_3 import (
    TealEngineV13,
    TealEngineV13Options,
    V13ReasonCode,
    GovernanceRequest,
    GovernanceContext,
    FreezeRule,
    PolicyMatcher,
    PlanOnlyConfig,
    NHIDescriptor,
    NHIInventory as NHIInventoryProtocol,
    ZSPConfig,
    JITGrant,
    AttestationConfig,
    AgentAttestation,
    DecisionV13,
)


# ── Helpers ──────────────────────────────────────────────────────


class SimpleNHIInventory:
    """Simple in-memory NHI inventory for testing."""

    def __init__(self, agents: Optional[List[NHIDescriptor]] = None) -> None:
        self._agents = {a.agent_id: a for a in (agents or [])}

    def lookup(self, agent_id: str) -> Optional[NHIDescriptor]:
        return self._agents.get(agent_id)

    def update_status(
        self, agent_id: str, status: Literal["active", "suspended", "revoked"]
    ) -> None:
        if agent_id in self._agents:
            old = self._agents[agent_id]
            self._agents[agent_id] = NHIDescriptor(
                agent_id=old.agent_id,
                owner=old.owner,
                created_at=old.created_at,
                capability_scope=old.capability_scope,
                environment_constraints=old.environment_constraints,
                status=status,
            )


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── FREEZE Rule Tests ────────────────────────────────────────────


class TestFreezeRules:
    """FREEZE rules block matching actions with absolute precedence."""

    async def test_freeze_rule_blocks_matching_action_class(self):
        """A FREEZE rule matching action_class should produce DENY with FREEZE_BLOCK."""
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-deploys",
                    match=PolicyMatcher(action_class="PRODUCTION_DEPLOY"),
                    reason="Deployment freeze during incident",
                    created_at=_now_ms(),
                    created_by="ops-team",
                ),
            ],
        ))

        request = GovernanceRequest(
            correlation_id="test-001",
            action_class="PRODUCTION_DEPLOY",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.FREEZE_BLOCK in decision.reason_codes
        assert decision.risk_score == 100
        assert "freeze-deploys" in decision.metadata.get("freeze_rule_id", "")

    async def test_freeze_rule_does_not_block_non_matching_action(self):
        """A FREEZE rule should not block actions that don't match."""
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-deploys",
                    match=PolicyMatcher(action_class="PRODUCTION_DEPLOY"),
                    reason="Deployment freeze",
                    created_at=_now_ms(),
                    created_by="ops-team",
                ),
            ],
        ))

        request = GovernanceRequest(
            correlation_id="test-002",
            action_class="READ",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"
        assert V13ReasonCode.FREEZE_BLOCK not in decision.reason_codes

    async def test_freeze_rule_with_tool_pattern(self):
        """A FREEZE rule matching a tool pattern should block that tool."""
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-db-writes",
                    match=PolicyMatcher(tool="database_*"),
                    reason="DB maintenance window",
                    created_at=_now_ms(),
                    created_by="dba-team",
                ),
            ],
        ))

        request = GovernanceRequest(
            correlation_id="test-003",
            tool="database_write",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.FREEZE_BLOCK in decision.reason_codes

    def test_freeze_rules_are_immutable(self):
        """Attempting to modify FREEZE rules emits a tamper event."""
        events = []
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-1",
                    match=PolicyMatcher(action_class="CODE_CHANGE"),
                    reason="Code freeze",
                    created_at=_now_ms(),
                    created_by="admin",
                ),
            ],
        ))
        engine.on_event(lambda e: events.append(e))

        # Attempt to modify
        engine.modify_freeze_rules([])

        assert len(events) == 1
        assert events[0].type == V13ReasonCode.FREEZE_TAMPER_ATTEMPT

        # Rules should still be intact
        assert len(engine.freeze_rules) == 1
        assert engine.freeze_rules[0].id == "freeze-1"


# ── PLAN_ONLY Mode Tests ─────────────────────────────────────────


class TestPlanOnlyMode:
    """PLAN_ONLY mode blocks side-effecting actions."""

    async def test_plan_only_blocks_side_effecting_action(self):
        """Side-effecting actions should be denied in PLAN_ONLY mode."""
        engine = TealEngineV13(TealEngineV13Options(
            plan_only_mode=True,
        ))

        request = GovernanceRequest(
            correlation_id="test-010",
            action_class="DATABASE_WRITE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.PLAN_ONLY_BLOCK in decision.reason_codes

    async def test_plan_only_allows_read_actions(self):
        """Read-only actions should be allowed in PLAN_ONLY mode."""
        engine = TealEngineV13(TealEngineV13Options(
            plan_only_mode=True,
        ))

        request = GovernanceRequest(
            correlation_id="test-011",
            action_class="READ",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"
        assert V13ReasonCode.PLAN_ONLY_BLOCK not in decision.reason_codes

    async def test_plan_only_allows_reasoning_actions(self):
        """Reasoning actions should be allowed in PLAN_ONLY mode."""
        engine = TealEngineV13(TealEngineV13Options(
            plan_only_mode=True,
        ))

        request = GovernanceRequest(
            correlation_id="test-012",
            action_class="REASONING",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"

    async def test_plan_only_with_custom_config(self):
        """Custom PLAN_ONLY config should override defaults."""
        engine = TealEngineV13(TealEngineV13Options(
            plan_only_config=PlanOnlyConfig(
                enabled=True,
                side_effecting_actions=["CUSTOM_WRITE"],
                allowed_actions=["CUSTOM_READ"],
            ),
        ))

        # Custom side-effecting action should be blocked
        request = GovernanceRequest(
            correlation_id="test-013",
            action_class="CUSTOM_WRITE",
        )
        decision = await engine.evaluate(request)
        assert decision.action == "DENY"
        assert V13ReasonCode.PLAN_ONLY_BLOCK in decision.reason_codes

        # Custom allowed action should pass
        request2 = GovernanceRequest(
            correlation_id="test-014",
            action_class="CUSTOM_READ",
        )
        decision2 = await engine.evaluate(request2)
        assert decision2.action == "ALLOW"

    async def test_plan_only_disabled_allows_all(self):
        """When PLAN_ONLY is disabled, all actions proceed normally."""
        engine = TealEngineV13(TealEngineV13Options(
            plan_only_mode=False,
        ))

        request = GovernanceRequest(
            correlation_id="test-015",
            action_class="DATABASE_WRITE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"


# ── NHI Status Tests ─────────────────────────────────────────────


class TestNHIStatus:
    """NHI revoked/suspended identities are denied."""

    async def test_nhi_revoked_denied(self):
        """A revoked NHI should be denied with NHI_REVOKED."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-020",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-revoked",
                owner="team-a",
                created_at=_now_ms() - 86400000,
                status="revoked",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.NHI_REVOKED in decision.reason_codes

    async def test_nhi_suspended_denied(self):
        """A suspended NHI should be denied with NHI_SUSPENDED."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-021",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-suspended",
                owner="team-b",
                created_at=_now_ms() - 86400000,
                status="suspended",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.NHI_SUSPENDED in decision.reason_codes

    async def test_nhi_active_allowed(self):
        """An active NHI with proper scope should be allowed."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-022",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-active",
                owner="team-c",
                created_at=_now_ms() - 86400000,
                capability_scope=["read:*"],
                status="active",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"

    async def test_nhi_inventory_overrides_request_status(self):
        """The NHI inventory status should override the request descriptor status."""
        inventory = SimpleNHIInventory([
            NHIDescriptor(
                agent_id="agent-001",
                owner="team-a",
                created_at=_now_ms() - 86400000,
                status="revoked",  # Inventory says revoked
            ),
        ])

        engine = TealEngineV13(TealEngineV13Options(
            nhi_inventory=inventory,
        ))

        # Request says active, but inventory says revoked
        request = GovernanceRequest(
            correlation_id="test-023",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-001",
                owner="team-a",
                created_at=_now_ms() - 86400000,
                status="active",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.NHI_REVOKED in decision.reason_codes

    async def test_nhi_scope_violation(self):
        """An action outside NHI capability scope should be denied."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-024",
            action_class="DATABASE_WRITE",
            nhi_identity=NHIDescriptor(
                agent_id="agent-limited",
                owner="team-d",
                created_at=_now_ms() - 86400000,
                capability_scope=["read:memory"],
                status="active",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.NHI_SCOPE_VIOLATION in decision.reason_codes

    async def test_nhi_environment_violation(self):
        """Operating in a disallowed environment should be denied."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-025",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-staging-only",
                owner="team-e",
                created_at=_now_ms() - 86400000,
                capability_scope=["read:*"],
                environment_constraints=["staging"],
                status="active",
            ),
        )

        ctx = GovernanceContext(
            correlation_id="test-025",
            environment="production",
        )

        decision = await engine.evaluate(request, ctx)

        assert decision.action == "DENY"
        assert V13ReasonCode.NHI_ENVIRONMENT_VIOLATION in decision.reason_codes


# ── ZSP Grant Tests ──────────────────────────────────────────────


class TestZSPGrant:
    """Zero Standing Privilege grant validation."""

    async def test_zsp_no_grant_denied(self):
        """When ZSP is enabled and no grant is provided, access is denied."""
        engine = TealEngineV13(TealEngineV13Options(
            zsp_config=ZSPConfig(enabled=True, max_grant_ttl_ms=3600000),
        ))

        request = GovernanceRequest(
            correlation_id="test-030",
            action_class="TOOL_INVOKE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.ACCESS_STANDING_PRIVILEGE_DENIED in decision.reason_codes

    async def test_zsp_expired_grant_denied(self):
        """When ZSP is enabled and grant is expired, access is denied."""
        engine = TealEngineV13(TealEngineV13Options(
            zsp_config=ZSPConfig(enabled=True, max_grant_ttl_ms=3600000),
        ))

        request = GovernanceRequest(
            correlation_id="test-031",
            action_class="TOOL_INVOKE",
            jit_grant=JITGrant(
                grant_id="grant-001",
                agent_id="agent-001",
                scope=["tool:database"],
                issued_at=_now_ms() - 7200000,  # 2 hours ago
                expires_at=_now_ms() - 3600000,  # Expired 1 hour ago
                issued_by="admin",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.ACCESS_GRANT_EXPIRED in decision.reason_codes

    async def test_zsp_valid_grant_allowed(self):
        """When ZSP is enabled and grant is valid, access is allowed."""
        engine = TealEngineV13(TealEngineV13Options(
            zsp_config=ZSPConfig(enabled=True, max_grant_ttl_ms=3600000),
        ))

        request = GovernanceRequest(
            correlation_id="test-032",
            action_class="TOOL_INVOKE",
            jit_grant=JITGrant(
                grant_id="grant-002",
                agent_id="agent-001",
                scope=["tool:database"],
                issued_at=_now_ms(),
                expires_at=_now_ms() + 3600000,  # Expires in 1 hour
                issued_by="admin",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"

    async def test_zsp_disabled_no_grant_allowed(self):
        """When ZSP is disabled, no grant is needed."""
        engine = TealEngineV13(TealEngineV13Options(
            zsp_config=ZSPConfig(enabled=False),
        ))

        request = GovernanceRequest(
            correlation_id="test-033",
            action_class="TOOL_INVOKE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"


# ── Attestation Tests ────────────────────────────────────────────


class TestAttestation:
    """Agent attestation verification."""

    async def test_attestation_missing_when_required(self):
        """Missing attestation when required should be denied."""
        engine = TealEngineV13(TealEngineV13Options(
            attestation_config=AttestationConfig(
                required=True,
                trusted_signers=["signer-key-1"],
            ),
        ))

        request = GovernanceRequest(
            correlation_id="test-040",
            action_class="TOOL_INVOKE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.AGENT_ATTESTATION_MISSING in decision.reason_codes

    async def test_attestation_untrusted_signer(self):
        """Attestation from untrusted signer should fail integrity check."""
        engine = TealEngineV13(TealEngineV13Options(
            attestation_config=AttestationConfig(
                required=True,
                trusted_signers=["signer-key-1"],
            ),
        ))

        request = GovernanceRequest(
            correlation_id="test-041",
            action_class="TOOL_INVOKE",
            attestation=AgentAttestation(
                agent_id="agent-001",
                signature="valid-sig",
                signer="untrusted-signer",
                attested_at=_now_ms(),
                integrity_hash="abc123",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "DENY"
        assert V13ReasonCode.AGENT_INTEGRITY_FAILED in decision.reason_codes

    async def test_attestation_valid(self):
        """Valid attestation from trusted signer should pass."""
        engine = TealEngineV13(TealEngineV13Options(
            attestation_config=AttestationConfig(
                required=True,
                trusted_signers=["signer-key-1"],
            ),
        ))

        request = GovernanceRequest(
            correlation_id="test-042",
            action_class="TOOL_INVOKE",
            attestation=AgentAttestation(
                agent_id="agent-001",
                signature="valid-sig",
                signer="signer-key-1",
                attested_at=_now_ms(),
                integrity_hash="abc123",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"


# ── Backward Compatibility Tests ─────────────────────────────────


class TestBackwardCompatibility:
    """No v1.3 features configured = v1.2 behavior."""

    async def test_no_v13_features_produces_allow(self):
        """With no v1.3 features, engine should produce standard ALLOW."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-050",
            action_class="TOOL_INVOKE",
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"
        assert decision.policy_version == "1.3.0"
        assert decision.teec_version == "2.0.0"
        assert "POLICY_COMPLIANT" in decision.reason_codes

    async def test_no_v13_features_with_nhi_active(self):
        """Active NHI with broad scope should pass through to v1.2."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(
            correlation_id="test-051",
            action_class="READ",
            nhi_identity=NHIDescriptor(
                agent_id="agent-full-access",
                owner="platform-team",
                created_at=_now_ms() - 86400000,
                capability_scope=["*"],
                status="active",
            ),
        )

        decision = await engine.evaluate(request)

        assert decision.action == "ALLOW"
        assert decision.nhi_context is not None
        assert decision.nhi_context["agent_id"] == "agent-full-access"

    async def test_decision_v13_has_correct_structure(self):
        """DecisionV13 should have all expected fields."""
        engine = TealEngineV13(TealEngineV13Options())

        request = GovernanceRequest(correlation_id="test-052")

        decision = await engine.evaluate(request)

        assert isinstance(decision, DecisionV13)
        assert decision.correlation_id == "test-052"
        assert decision.module == "TealEngineV13"
        assert decision.component_versions == {"sdk": "1.3.0", "engine": "1.3.0"}
        assert decision.timestamp > 0


# ── Pre-evaluation Order Tests ───────────────────────────────────


class TestPreEvaluationOrder:
    """Pre-evaluation checks execute in correct order (FREEZE first)."""

    async def test_freeze_takes_precedence_over_plan_only(self):
        """FREEZE should block even when PLAN_ONLY would also block."""
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-all",
                    match=PolicyMatcher(action_class="CODE_CHANGE"),
                    reason="Total freeze",
                    created_at=_now_ms(),
                    created_by="admin",
                ),
            ],
            plan_only_mode=True,
        ))

        request = GovernanceRequest(
            correlation_id="test-060",
            action_class="CODE_CHANGE",
        )

        decision = await engine.evaluate(request)

        # FREEZE should win (it's checked first)
        assert decision.action == "DENY"
        assert V13ReasonCode.FREEZE_BLOCK in decision.reason_codes
        assert V13ReasonCode.PLAN_ONLY_BLOCK not in decision.reason_codes

    async def test_freeze_takes_precedence_over_nhi_revoked(self):
        """FREEZE should block before NHI status is even checked."""
        engine = TealEngineV13(TealEngineV13Options(
            freeze_rules=[
                FreezeRule(
                    id="freeze-tools",
                    match=PolicyMatcher(action_class="TOOL_INVOKE"),
                    reason="Tool freeze",
                    created_at=_now_ms(),
                    created_by="admin",
                ),
            ],
        ))

        request = GovernanceRequest(
            correlation_id="test-061",
            action_class="TOOL_INVOKE",
            nhi_identity=NHIDescriptor(
                agent_id="agent-revoked",
                owner="team-a",
                created_at=_now_ms() - 86400000,
                status="revoked",
            ),
        )

        decision = await engine.evaluate(request)

        # FREEZE should win
        assert V13ReasonCode.FREEZE_BLOCK in decision.reason_codes
        assert V13ReasonCode.NHI_REVOKED not in decision.reason_codes
