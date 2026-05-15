"""Tests for TealProof and TealFlow Python modules.

Covers:
- Merkle tree: append, root changes, proof verification
- TealProof: receipt generation, chain formation, tampering detection
- TealFlow: parse YAML, validate, execute with dependencies, conditional skipping

Requirements: 12.1, 12.4, 12.5
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import List

import pytest

from tealtiger.modules.tealproof import (
    SHA256MerkleTree,
    GovernanceReceipt,
    TealProofModule,
    INITIAL_PREVIOUS_HASH,
    _sha256,
)
from tealtiger.modules.tealflow import (
    FlowContext,
    FlowResult,
    TealFlowEngine,
    TealFlowParser,
    TealFlowWorkflow,
    ValidationResult,
    evaluate_expression,
)


# ══════════════════════════════════════════════════════════════════
# SHA256MerkleTree Tests
# ══════════════════════════════════════════════════════════════════


class TestSHA256MerkleTree:
    """Tests for the SHA-256 Merkle tree implementation."""

    def test_empty_tree_root(self) -> None:
        """Empty tree root is SHA-256 of empty string."""
        tree = SHA256MerkleTree()
        expected = hashlib.sha256(b"").hexdigest()
        assert tree.root() == expected

    def test_single_leaf_root(self) -> None:
        """Single leaf tree root is the leaf itself."""
        tree = SHA256MerkleTree()
        leaf = _sha256("hello")
        tree.append(leaf)
        assert tree.root() == leaf

    def test_append_returns_index(self) -> None:
        """Append returns sequential indices starting from 0."""
        tree = SHA256MerkleTree()
        assert tree.append("a") == 0
        assert tree.append("b") == 1
        assert tree.append("c") == 2

    def test_root_changes_on_append(self) -> None:
        """Root changes each time a new leaf is appended."""
        tree = SHA256MerkleTree()
        tree.append(_sha256("leaf1"))
        root1 = tree.root()

        tree.append(_sha256("leaf2"))
        root2 = tree.root()

        tree.append(_sha256("leaf3"))
        root3 = tree.root()

        assert root1 != root2
        assert root2 != root3
        assert root1 != root3

    def test_proof_verification_two_leaves(self) -> None:
        """Proof verification works for a two-leaf tree."""
        tree = SHA256MerkleTree()
        leaf0 = _sha256("leaf0")
        leaf1 = _sha256("leaf1")
        tree.append(leaf0)
        tree.append(leaf1)

        root = tree.root()
        proof0 = tree.get_proof(0)
        proof1 = tree.get_proof(1)

        assert tree.verify(leaf0, proof0, root) is True
        assert tree.verify(leaf1, proof1, root) is True

    def test_proof_verification_multiple_leaves(self) -> None:
        """Proof verification works for trees with 3+ leaves."""
        tree = SHA256MerkleTree()
        leaves: List[str] = []
        for i in range(5):
            leaf = _sha256(f"leaf{i}")
            leaves.append(leaf)
            tree.append(leaf)

        root = tree.root()
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert tree.verify(leaf, proof, root) is True

    def test_proof_fails_for_wrong_leaf(self) -> None:
        """Verification fails when the leaf doesn't match."""
        tree = SHA256MerkleTree()
        tree.append(_sha256("leaf0"))
        tree.append(_sha256("leaf1"))

        root = tree.root()
        proof = tree.get_proof(0)

        # Wrong leaf should fail verification
        wrong_leaf = _sha256("wrong")
        assert tree.verify(wrong_leaf, proof, root) is False

    def test_proof_fails_for_wrong_root(self) -> None:
        """Verification fails when the root doesn't match."""
        tree = SHA256MerkleTree()
        leaf = _sha256("leaf0")
        tree.append(leaf)
        tree.append(_sha256("leaf1"))

        proof = tree.get_proof(0)
        wrong_root = _sha256("wrong_root")
        assert tree.verify(leaf, proof, wrong_root) is False

    def test_get_proof_empty_tree_raises(self) -> None:
        """Getting proof from empty tree raises ValueError."""
        tree = SHA256MerkleTree()
        with pytest.raises(ValueError, match="empty tree"):
            tree.get_proof(0)

    def test_get_proof_out_of_bounds_raises(self) -> None:
        """Getting proof with invalid index raises ValueError."""
        tree = SHA256MerkleTree()
        tree.append(_sha256("leaf"))
        with pytest.raises(ValueError, match="out of bounds"):
            tree.get_proof(5)

    def test_single_leaf_proof_is_empty(self) -> None:
        """Single leaf tree has empty proof."""
        tree = SHA256MerkleTree()
        tree.append(_sha256("only"))
        proof = tree.get_proof(0)
        assert proof == []

    def test_size_property(self) -> None:
        """Size property tracks number of leaves."""
        tree = SHA256MerkleTree()
        assert tree.size == 0
        tree.append("a")
        assert tree.size == 1
        tree.append("b")
        assert tree.size == 2


# ══════════════════════════════════════════════════════════════════
# TealProofModule Tests
# ══════════════════════════════════════════════════════════════════


class TestTealProofModule:
    """Tests for the TealProof governance receipt module."""

    def test_append_decision_returns_receipt(self) -> None:
        """append_decision returns a valid GovernanceReceipt."""
        proof = TealProofModule()
        receipt = proof.append_decision(
            decision_action="ALLOW",
            context="test-context",
            timestamp=1000,
            policy_version="1.0.0",
            correlation_id="corr-001",
        )

        assert isinstance(receipt, GovernanceReceipt)
        assert receipt.leaf_index == 0
        assert receipt.decision_hash != ""
        assert receipt.previous_hash == INITIAL_PREVIOUS_HASH
        assert receipt.timestamp == 1000
        assert receipt.policy_version == "1.0.0"
        assert receipt.correlation_id == "corr-001"

    def test_chain_formation(self) -> None:
        """Each receipt's previous_hash links to the prior decision_hash."""
        proof = TealProofModule()

        r1 = proof.append_decision("ALLOW", "ctx1", 1000, "1.0.0", "c1")
        r2 = proof.append_decision("DENY", "ctx2", 2000, "1.0.0", "c2")
        r3 = proof.append_decision("MODIFY", "ctx3", 3000, "1.0.0", "c3")

        # First receipt links to genesis
        assert r1.previous_hash == INITIAL_PREVIOUS_HASH
        # Second receipt links to first
        assert r2.previous_hash == r1.decision_hash
        # Third receipt links to second
        assert r3.previous_hash == r2.decision_hash

    def test_decision_hash_computation(self) -> None:
        """Decision hash is SHA-256(action + context + timestamp + policy_version + prev_hash)."""
        proof = TealProofModule()
        receipt = proof.append_decision("ALLOW", "ctx", 1000, "1.0.0", "c1")

        expected_input = "ALLOW" + "ctx" + "1000" + "1.0.0" + INITIAL_PREVIOUS_HASH
        expected_hash = hashlib.sha256(expected_input.encode("utf-8")).hexdigest()
        assert receipt.decision_hash == expected_hash

    def test_get_root_changes(self) -> None:
        """Root changes after each decision is appended."""
        proof = TealProofModule()
        root0 = proof.get_root()

        proof.append_decision("ALLOW", "ctx", 1000, "1.0.0", "c1")
        root1 = proof.get_root()

        proof.append_decision("DENY", "ctx", 2000, "1.0.0", "c2")
        root2 = proof.get_root()

        assert root0 != root1
        assert root1 != root2

    def test_verify_receipt_valid(self) -> None:
        """verify_receipt returns True for a valid receipt."""
        proof = TealProofModule()
        proof.append_decision("ALLOW", "ctx1", 1000, "1.0.0", "c1")
        r2 = proof.append_decision("DENY", "ctx2", 2000, "1.0.0", "c2")

        assert proof.verify_receipt(r2) is True

    def test_detect_tampering_no_tamper(self) -> None:
        """detect_tampering returns False when chain is intact."""
        proof = TealProofModule()
        r1 = proof.append_decision("ALLOW", "ctx1", 1000, "1.0.0", "c1")
        r2 = proof.append_decision("DENY", "ctx2", 2000, "1.0.0", "c2")

        # r2's previous_hash should match r1's decision_hash
        assert proof.detect_tampering(r2, r1.decision_hash) is False
        assert len(proof.get_events()) == 0

    def test_detect_tampering_detected(self) -> None:
        """detect_tampering returns True and emits event when chain is broken."""
        proof = TealProofModule()
        proof.append_decision("ALLOW", "ctx1", 1000, "1.0.0", "c1")
        r2 = proof.append_decision("DENY", "ctx2", 2000, "1.0.0", "c2")

        # Provide wrong expected hash
        tampered = proof.detect_tampering(r2, "wrong_hash_value")
        assert tampered is True

        events = proof.get_events()
        assert len(events) == 1
        assert events[0].event_type == "PROOF_CHAIN_INTEGRITY_VIOLATION"
        assert events[0].details["expected_previous_hash"] == "wrong_hash_value"

    def test_get_previous_hash(self) -> None:
        """get_previous_hash returns the last decision hash."""
        proof = TealProofModule()
        assert proof.get_previous_hash() == INITIAL_PREVIOUS_HASH

        r1 = proof.append_decision("ALLOW", "ctx", 1000, "1.0.0", "c1")
        assert proof.get_previous_hash() == r1.decision_hash


# ══════════════════════════════════════════════════════════════════
# TealFlowParser Tests
# ══════════════════════════════════════════════════════════════════


SAMPLE_WORKFLOW_YAML = """
name: security-scan
on:
  agent_action:
    types: [CODE_CHANGE, TOOL_INVOKE]
  workflow_dispatch: {}
jobs:
  scan:
    steps:
      - name: run-guard
        uses: tealtiger/guard@v1
        with:
          mode: strict
  notify:
    needs: [scan]
    steps:
      - name: send-alert
        uses: tealtiger/notify@v1
        with:
          channel: security
"""

CONDITIONAL_WORKFLOW_YAML = """
name: conditional-flow
on:
  agent_action:
    types: [CODE_CHANGE]
jobs:
  check:
    steps:
      - name: basic-check
        uses: tealtiger/check@v1
  deploy:
    needs: [check]
    if: "event.risk_score < 50"
    steps:
      - name: deploy-step
        uses: tealtiger/deploy@v1
"""


class TestTealFlowParser:
    """Tests for the TealFlow YAML parser."""

    def test_parse_basic_workflow(self) -> None:
        """Parses a basic workflow YAML into TealFlowWorkflow."""
        parser = TealFlowParser()
        workflow = parser.parse(SAMPLE_WORKFLOW_YAML)

        assert workflow.name == "security-scan"
        assert workflow.on.agent_action is not None
        assert workflow.on.agent_action["types"] == ["CODE_CHANGE", "TOOL_INVOKE"]
        assert workflow.on.workflow_dispatch is not None
        assert "scan" in workflow.jobs
        assert "notify" in workflow.jobs
        assert workflow.jobs["notify"].needs == ["scan"]

    def test_parse_steps(self) -> None:
        """Parses steps with uses and with parameters."""
        parser = TealFlowParser()
        workflow = parser.parse(SAMPLE_WORKFLOW_YAML)

        scan_steps = workflow.jobs["scan"].steps
        assert len(scan_steps) == 1
        assert scan_steps[0].name == "run-guard"
        assert scan_steps[0].uses == "tealtiger/guard@v1"
        assert scan_steps[0].with_params == {"mode": "strict"}

    def test_parse_invalid_yaml_raises(self) -> None:
        """Raises ValueError for invalid YAML."""
        parser = TealFlowParser()
        with pytest.raises(ValueError, match="Invalid YAML"):
            parser.parse("null")

    def test_validate_valid_workflow(self) -> None:
        """Validates a correct workflow without errors."""
        parser = TealFlowParser()
        workflow = parser.parse(SAMPLE_WORKFLOW_YAML)
        result = parser.validate(workflow)

        assert result.valid is True
        assert result.errors == []

    def test_validate_missing_name(self) -> None:
        """Validation fails when name is missing."""
        parser = TealFlowParser()
        workflow = TealFlowWorkflow(name="")
        workflow.on.workflow_dispatch = {}
        from tealtiger.modules.tealflow import Job, Step

        workflow.jobs = {"j": Job(steps=[Step(name="s", uses="x")])}
        result = parser.validate(workflow)

        assert result.valid is False
        assert any("name" in e for e in result.errors)

    def test_validate_missing_trigger(self) -> None:
        """Validation fails when no trigger is defined."""
        parser = TealFlowParser()
        from tealtiger.modules.tealflow import Job, Step, TriggerConfig

        workflow = TealFlowWorkflow(
            name="test",
            on=TriggerConfig(),
            jobs={"j": Job(steps=[Step(name="s", uses="x")])},
        )
        result = parser.validate(workflow)

        assert result.valid is False
        assert any("trigger" in e.lower() for e in result.errors)

    def test_validate_unknown_dependency(self) -> None:
        """Validation fails when a job depends on an unknown job."""
        parser = TealFlowParser()
        yaml_content = """
name: test
on:
  workflow_dispatch: {}
jobs:
  build:
    needs: [nonexistent]
    steps:
      - name: step1
        uses: action@v1
"""
        workflow = parser.parse(yaml_content)
        result = parser.validate(workflow)

        assert result.valid is False
        assert any("unknown job" in e for e in result.errors)

    def test_validate_self_dependency(self) -> None:
        """Validation fails when a job depends on itself."""
        parser = TealFlowParser()
        yaml_content = """
name: test
on:
  workflow_dispatch: {}
jobs:
  build:
    needs: [build]
    steps:
      - name: step1
        uses: action@v1
"""
        workflow = parser.parse(yaml_content)
        result = parser.validate(workflow)

        assert result.valid is False
        assert any("cannot depend on itself" in e for e in result.errors)


# ══════════════════════════════════════════════════════════════════
# TealFlowEngine Tests
# ══════════════════════════════════════════════════════════════════


class TestTealFlowEngine:
    """Tests for the TealFlow execution engine."""

    @pytest.fixture
    def parser(self) -> TealFlowParser:
        return TealFlowParser()

    @pytest.fixture
    def engine(self) -> TealFlowEngine:
        return TealFlowEngine()

    @pytest.fixture
    def context(self) -> FlowContext:
        return FlowContext(
            event={"risk_score": 30, "action": "CODE_CHANGE"},
            env={"ENVIRONMENT": "staging"},
            secrets={"API_KEY": "secret-value"},
        )

    @pytest.mark.asyncio
    async def test_execute_basic_workflow(
        self, parser: TealFlowParser, engine: TealFlowEngine, context: FlowContext
    ) -> None:
        """Executes a basic workflow with dependencies."""
        workflow = parser.parse(SAMPLE_WORKFLOW_YAML)
        result = await engine.execute(workflow, context)

        assert result.success is True
        assert "scan" in result.jobs_completed
        assert "notify" in result.jobs_completed
        assert result.jobs_failed == []

    @pytest.mark.asyncio
    async def test_execute_with_conditional_true(
        self, parser: TealFlowParser, engine: TealFlowEngine
    ) -> None:
        """Job executes when if condition is true."""
        workflow = parser.parse(CONDITIONAL_WORKFLOW_YAML)
        context = FlowContext(
            event={"risk_score": 30},  # < 50, condition is true
            env={},
            secrets={},
        )
        result = await engine.execute(workflow, context)

        assert result.success is True
        assert "deploy" in result.jobs_completed

    @pytest.mark.asyncio
    async def test_execute_with_conditional_false(
        self, parser: TealFlowParser, engine: TealFlowEngine
    ) -> None:
        """Job is skipped (counted as completed) when if condition is false."""
        workflow = parser.parse(CONDITIONAL_WORKFLOW_YAML)
        context = FlowContext(
            event={"risk_score": 80},  # >= 50, condition is false
            env={},
            secrets={},
        )
        result = await engine.execute(workflow, context)

        assert result.success is True
        # deploy is skipped but counts as completed (not failed)
        assert "deploy" in result.jobs_completed
        assert "deploy" not in result.jobs_failed

    @pytest.mark.asyncio
    async def test_execute_dependency_order(
        self, engine: TealFlowEngine, context: FlowContext
    ) -> None:
        """Jobs with needs wait for dependencies to complete."""
        parser = TealFlowParser()
        yaml_content = """
name: ordered
on:
  workflow_dispatch: {}
jobs:
  first:
    steps:
      - name: step-a
        uses: action@v1
  second:
    needs: [first]
    steps:
      - name: step-b
        uses: action@v1
  third:
    needs: [second]
    steps:
      - name: step-c
        uses: action@v1
"""
        workflow = parser.parse(yaml_content)
        result = await engine.execute(workflow, context)

        assert result.success is True
        assert set(result.jobs_completed) == {"first", "second", "third"}

    @pytest.mark.asyncio
    async def test_execute_parallel_independent_jobs(
        self, engine: TealFlowEngine, context: FlowContext
    ) -> None:
        """Independent jobs (no needs) can execute in parallel."""
        parser = TealFlowParser()
        yaml_content = """
name: parallel
on:
  workflow_dispatch: {}
jobs:
  job_a:
    steps:
      - name: step-a
        uses: action@v1
  job_b:
    steps:
      - name: step-b
        uses: action@v1
  job_c:
    steps:
      - name: step-c
        uses: action@v1
"""
        workflow = parser.parse(yaml_content)
        result = await engine.execute(workflow, context)

        assert result.success is True
        assert set(result.jobs_completed) == {"job_a", "job_b", "job_c"}


# ══════════════════════════════════════════════════════════════════
# Expression Evaluator Tests
# ══════════════════════════════════════════════════════════════════


class TestEvaluateExpression:
    """Tests for the expression evaluator."""

    @pytest.fixture
    def context(self) -> FlowContext:
        return FlowContext(
            event={"risk_score": 75, "action": "CODE_CHANGE", "approved": True},
            env={"ENVIRONMENT": "production"},
            secrets={},
        )

    def test_boolean_literal_true(self, context: FlowContext) -> None:
        assert evaluate_expression("true", context) is True

    def test_boolean_literal_false(self, context: FlowContext) -> None:
        assert evaluate_expression("false", context) is False

    def test_comparison_greater_than(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score > 50", context) is True
        assert evaluate_expression("event.risk_score > 80", context) is False

    def test_comparison_less_than(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score < 80", context) is True
        assert evaluate_expression("event.risk_score < 50", context) is False

    def test_comparison_equals(self, context: FlowContext) -> None:
        assert evaluate_expression("event.action == 'CODE_CHANGE'", context) is True
        assert evaluate_expression("event.action == 'OTHER'", context) is False

    def test_comparison_not_equals(self, context: FlowContext) -> None:
        assert evaluate_expression("event.action != 'OTHER'", context) is True

    def test_logical_and(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score > 50 && event.approved == true", context) is True
        assert evaluate_expression("event.risk_score > 80 && event.approved == true", context) is False

    def test_logical_or(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score > 80 || event.approved == true", context) is True

    def test_negation(self, context: FlowContext) -> None:
        assert evaluate_expression("!false", context) is True
        assert evaluate_expression("!true", context) is False

    def test_env_access(self, context: FlowContext) -> None:
        assert evaluate_expression("env.ENVIRONMENT == 'production'", context) is True

    def test_numeric_comparison_gte(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score >= 75", context) is True
        assert evaluate_expression("event.risk_score >= 76", context) is False

    def test_numeric_comparison_lte(self, context: FlowContext) -> None:
        assert evaluate_expression("event.risk_score <= 75", context) is True
        assert evaluate_expression("event.risk_score <= 74", context) is False
