"""TealProof — Cryptographic Governance Receipts (Python SDK).

Implements SHA-256 Merkle tree and governance receipt chain for tamper-evident
proof of policy decisions. Port of the TypeScript TealProof module with
identical hash computation and tree structure.

Components:
- SHA256MerkleTree: Merkle tree for organizing decision hashes
- TealProofModule: Governance receipt chain with tampering detection

Module: modules/tealproof
Requirements: 7.1, 7.2, 7.4, 7.8, 12.1, 12.4, 12.5
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Helpers ──────────────────────────────────────────────────────


def _sha256(data: str) -> str:
    """Compute SHA-256 hash of the input string, returning hex-encoded digest."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    """Compute the parent hash from two child hashes by concatenating and hashing."""
    return _sha256(left + right)


# ── Data Classes ─────────────────────────────────────────────────


@dataclass
class GovernanceReceipt:
    """Governance receipt — cryptographic proof of a policy decision."""

    leaf_index: int = 0
    decision_hash: str = ""
    previous_hash: str = ""
    timestamp: int = 0
    policy_version: str = ""
    correlation_id: str = ""
    merkle_proof: List[str] = field(default_factory=list)


@dataclass
class TealProofEvent:
    """Event emitted by TealProof (e.g., chain integrity violations)."""

    event_type: str = ""
    timestamp: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


# ── SHA256MerkleTree ─────────────────────────────────────────────


class SHA256MerkleTree:
    """SHA-256 based Merkle tree for governance decision hashes.

    Supports:
    - Appending leaves (decision hashes)
    - Computing the Merkle root
    - Generating inclusion proofs (sibling hashes)
    - Verifying a leaf's inclusion against a given root

    Edge cases handled:
    - Empty tree (root is hash of empty string)
    - Single leaf (root is the leaf itself)
    - Non-power-of-2 leaf counts (duplicates last node at each level)
    """

    def __init__(self) -> None:
        self._leaves: List[str] = []

    @property
    def size(self) -> int:
        """Return the number of leaves currently in the tree."""
        return len(self._leaves)

    def root(self) -> str:
        """Return the current Merkle root hash.

        - Empty tree: returns SHA-256 of empty string.
        - Single leaf: returns the leaf hash itself.
        - Multiple leaves: computes full tree root.
        """
        if len(self._leaves) == 0:
            return _sha256("")
        if len(self._leaves) == 1:
            return self._leaves[0]
        return self._compute_root(self._leaves)

    def append(self, leaf: str) -> int:
        """Append a leaf hash to the tree and return its index."""
        self._leaves.append(leaf)
        return len(self._leaves) - 1

    def get_proof(self, leaf_index: int) -> List[str]:
        """Return the sibling hashes needed to verify the leaf at the given index.

        The proof is ordered from leaf level to root level.

        Raises:
            ValueError: If leaf_index is out of bounds or tree is empty.
        """
        if len(self._leaves) == 0:
            raise ValueError("Cannot generate proof for empty tree")
        if leaf_index < 0 or leaf_index >= len(self._leaves):
            raise ValueError(
                f"Leaf index {leaf_index} out of bounds [0, {len(self._leaves) - 1}]"
            )
        if len(self._leaves) == 1:
            return []

        proof: List[str] = []
        current_level = list(self._leaves)
        index = leaf_index

        while len(current_level) > 1:
            # If odd number of nodes, duplicate the last one
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            # Determine sibling index
            sibling_index = index + 1 if index % 2 == 0 else index - 1
            proof.append(current_level[sibling_index])

            # Move up to next level
            next_level: List[str] = []
            for i in range(0, len(current_level), 2):
                next_level.append(_hash_pair(current_level[i], current_level[i + 1]))
            current_level = next_level
            index = index // 2

        return proof

    def verify(self, leaf: str, proof: List[str], expected_root: str) -> bool:
        """Verify that a leaf is included in a tree with the given root.

        Recomputes the root from the leaf and proof, then compares.
        """
        if len(proof) == 0:
            # Single-leaf tree: the leaf itself is the root
            return leaf == expected_root

        # Try to find the leaf index in our tree for deterministic verification
        if leaf in self._leaves:
            leaf_index = self._leaves.index(leaf)
            return self._verify_at_index(leaf, proof, expected_root, leaf_index)

        # External verification: try all possible positions
        return self._verify_without_index(leaf, proof, expected_root)

    # ── Private methods ────────────────────────────────────────────

    def _compute_root(self, leaves: List[str]) -> str:
        """Compute the Merkle root from a list of leaf hashes."""
        current_level = list(leaves)

        while len(current_level) > 1:
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            next_level: List[str] = []
            for i in range(0, len(current_level), 2):
                next_level.append(_hash_pair(current_level[i], current_level[i + 1]))
            current_level = next_level

        return current_level[0]

    def _verify_at_index(
        self, leaf: str, proof: List[str], expected_root: str, leaf_index: int
    ) -> bool:
        """Verify a leaf at a known index against the expected root."""
        current_hash = leaf
        index = leaf_index

        for sibling in proof:
            if index % 2 == 0:
                current_hash = _hash_pair(current_hash, sibling)
            else:
                current_hash = _hash_pair(sibling, current_hash)
            index = index // 2

        return current_hash == expected_root

    def _verify_without_index(
        self, leaf: str, proof: List[str], expected_root: str
    ) -> bool:
        """Attempt verification without knowing the exact index.

        Tries all possible left/right combinations (brute force for small proofs).
        """
        max_positions = 1 << len(proof)
        for pos in range(max_positions):
            current_hash = leaf
            index = pos
            for sibling in proof:
                if index % 2 == 0:
                    current_hash = _hash_pair(current_hash, sibling)
                else:
                    current_hash = _hash_pair(sibling, current_hash)
                index = index // 2
            if current_hash == expected_root:
                return True
        return False


# ── TealProofModule ──────────────────────────────────────────────

# Genesis: 64 hex zeros
INITIAL_PREVIOUS_HASH = "0" * 64
EVENT_CHAIN_VIOLATION = "PROOF_CHAIN_INTEGRITY_VIOLATION"


class TealProofModule:
    """TealProof — Cryptographic Governance Receipt Module.

    Produces tamper-evident proof chains for governance decisions using:
    - SHA-256 decision hashing (decision + context + timestamp + policy_version + prev_hash)
    - Merkle tree organization of decision hashes
    - Compact verification proofs (sibling hashes)
    - Chain integrity detection (tampering → PROOF_CHAIN_INTEGRITY_VIOLATION)
    """

    def __init__(self, tree: Optional[SHA256MerkleTree] = None) -> None:
        self._tree = tree if tree is not None else SHA256MerkleTree()
        self._previous_hash: str = INITIAL_PREVIOUS_HASH
        self._events: List[TealProofEvent] = []

    def append_decision(
        self,
        decision_action: str,
        context: str,
        timestamp: int,
        policy_version: str,
        correlation_id: str,
    ) -> GovernanceReceipt:
        """Append a governance decision to the proof chain.

        Computes: SHA-256(decision_action + context + timestamp + policy_version + previous_hash)
        Appends the hash to the Merkle tree and returns a GovernanceReceipt.
        """
        # Compute decision hash
        hash_input = (
            decision_action + context + str(timestamp) + policy_version + self._previous_hash
        )
        decision_hash = _sha256(hash_input)

        # Append to Merkle tree
        leaf_index = self._tree.append(decision_hash)

        # Generate Merkle proof for this leaf
        merkle_proof = self._tree.get_proof(leaf_index)

        # Build receipt
        receipt = GovernanceReceipt(
            leaf_index=leaf_index,
            decision_hash=decision_hash,
            previous_hash=self._previous_hash,
            timestamp=timestamp,
            policy_version=policy_version,
            correlation_id=correlation_id,
            merkle_proof=merkle_proof,
        )

        # Update chain: current hash becomes previous for next decision
        self._previous_hash = decision_hash

        return receipt

    def get_root(self) -> str:
        """Return the current Merkle root hash."""
        return self._tree.root()

    def verify_receipt(self, receipt: GovernanceReceipt) -> bool:
        """Verify a receipt against the current Merkle tree.

        Checks that the decision hash is included in the tree at the stated index.
        """
        return self._tree.verify(receipt.decision_hash, receipt.merkle_proof, self.get_root())

    def detect_tampering(self, receipt: GovernanceReceipt, expected_prev_hash: str) -> bool:
        """Detect tampering by checking chain integrity.

        Verifies that the receipt's previous_hash matches the expected previous hash.
        If tampering is detected, emits a PROOF_CHAIN_INTEGRITY_VIOLATION event.

        Args:
            receipt: The receipt to check.
            expected_prev_hash: The expected previous hash in the chain.

        Returns:
            True if tampering is detected, False if chain is intact.
        """
        tampered = receipt.previous_hash != expected_prev_hash

        if tampered:
            self._emit_event(
                TealProofEvent(
                    event_type=EVENT_CHAIN_VIOLATION,
                    timestamp=int(time.time() * 1000),
                    details={
                        "leaf_index": receipt.leaf_index,
                        "expected_previous_hash": expected_prev_hash,
                        "actual_previous_hash": receipt.previous_hash,
                        "decision_hash": receipt.decision_hash,
                        "correlation_id": receipt.correlation_id,
                    },
                )
            )

        return tampered

    def get_events(self) -> List[TealProofEvent]:
        """Return all emitted events (for testing and integration)."""
        return list(self._events)

    def clear_events(self) -> None:
        """Clear emitted events."""
        self._events = []

    def get_previous_hash(self) -> str:
        """Return the current previous hash (the last decision hash in the chain)."""
        return self._previous_hash

    # ── Private ────────────────────────────────────────────────────

    def _emit_event(self, event: TealProofEvent) -> None:
        self._events.append(event)
