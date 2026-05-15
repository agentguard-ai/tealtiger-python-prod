"""TealClassifier — Lightweight ML Detection Module (Python SDK).

Provides optional ONNX-based ML classification for prompt injection detection.
Uses a pluggable InferenceEngine protocol so the actual ONNX Runtime dependency
lives in a separate package.

Features:
- Load ONNX model via pluggable InferenceEngine (dependency injection)
- Local inference with no external API calls
- Confidence score always clamped to [0.0, 1.0]
- Deterministic: same input → same output (no sampling/temperature)
- Fallback: if model fails to load or inference fails → emit CLASSIFIER_FALLBACK event
- Hot-swap model without SDK restart via update_model()

Ensemble Modes:
- regex_only: v1.2 backward-compatible behavior, ML not loaded
- ml_only: only classifier output used
- ensemble_union: block if regex OR ml detects (higher recall)
- ensemble_intersection: block only if BOTH detect (higher precision)

Module: modules/tealclassifier
Requirements: 12.1, 12.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Protocol, runtime_checkable


# ── Types ────────────────────────────────────────────────────────

EnsembleMode = Literal["regex_only", "ml_only", "ensemble_union", "ensemble_intersection"]


@dataclass
class ClassifierConfig:
    """Configuration for the TealClassifier module."""

    model_path: str = ""
    ensemble_mode: EnsembleMode = "regex_only"
    confidence_threshold: float = 0.5
    max_tokens: int = 512


@dataclass
class ClassifierResult:
    """Result from ML classification."""

    detected: bool
    confidence: float
    source: Literal["regex", "ml", "ensemble"]


@dataclass
class ClassifierEvent:
    """Events emitted by the TealClassifier module."""

    type: Literal["CLASSIFIER_FALLBACK", "CLASSIFIER_LOADED", "CLASSIFIER_MODEL_UPDATED"]
    message: str
    timestamp: float
    model_path: Optional[str] = None
    error: Optional[Exception] = None


# ── InferenceEngine Protocol ─────────────────────────────────────


@runtime_checkable
class InferenceEngine(Protocol):
    """Pluggable inference engine interface.

    Implemented by a package wrapping ONNX Runtime.
    Allows the core SDK to remain free of heavy ONNX dependencies.
    """

    def predict(self, input: str) -> Dict[str, float]:
        """Run inference on the given input string.

        Must return a dict with at least {"confidence": float} where
        confidence is in [0.0, 1.0]. Must be deterministic.
        """
        ...


# ── TealClassifierModule ─────────────────────────────────────────


class TealClassifierModule:
    """Lightweight ML detection module.

    Provides optional ONNX-based ML classification for prompt injection detection.
    Uses a pluggable InferenceEngine protocol for dependency injection.
    """

    def __init__(
        self,
        config: Optional[ClassifierConfig] = None,
        engine: Optional[InferenceEngine] = None,
    ) -> None:
        self._config = config or ClassifierConfig()
        self._engine = engine
        self._model_loaded = False
        self._model_version = "unknown"
        self._listeners: List[Callable[[ClassifierEvent], None]] = []

    # ── Lifecycle ────────────────────────────────────────────────

    async def load(self, config: Optional[ClassifierConfig] = None) -> None:
        """Load the ONNX model via the inference engine.

        On failure, emits CLASSIFIER_FALLBACK and reverts to unloaded state.

        Args:
            config: Optional new configuration to apply before loading.
        """
        if config is not None:
            self._config = config

        if self._engine is None:
            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_FALLBACK",
                message="No inference engine provided; falling back to regex_only",
                timestamp=0.0,
                model_path=self._config.model_path,
            ))
            self._model_loaded = False
            return

        try:
            # If the engine has a load_model method, call it
            if hasattr(self._engine, "load_model"):
                self._engine.load_model(self._config.model_path)  # type: ignore[attr-defined]
            self._model_loaded = True
            self._model_version = self._extract_model_version(self._config.model_path)
            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_LOADED",
                message=f"Model loaded from {self._config.model_path}",
                timestamp=0.0,
                model_path=self._config.model_path,
            ))
        except Exception as e:
            self._model_loaded = False
            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_FALLBACK",
                message=f"Failed to load model: {e}",
                timestamp=0.0,
                model_path=self._config.model_path,
                error=e,
            ))

    async def classify(self, input: str) -> Optional[Dict[str, Any]]:
        """Run classification on the input string.

        Returns a dict with {"detected": bool, "confidence": float, "source": "ml"}
        or None if ML is unavailable (model not loaded or inference fails).

        Confidence is always clamped to [0.0, 1.0].

        Args:
            input: The text to classify.

        Returns:
            Classification result dict or None if ML unavailable.
        """
        if self._engine is None or not self._model_loaded:
            return None

        try:
            result = self._engine.predict(input)

            # Clamp confidence to [0.0, 1.0]
            confidence = max(0.0, min(1.0, result["confidence"]))

            detected = confidence >= self._config.confidence_threshold

            return {
                "detected": detected,
                "confidence": confidence,
                "source": "ml",
            }
        except Exception as e:
            # Inference failed — emit fallback event and return None
            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_FALLBACK",
                message=f"Inference failed: {e}",
                timestamp=0.0,
                error=e,
            ))
            return None

    def get_model_version(self) -> str:
        """Get the current model version string."""
        return self._model_version

    async def update_model(self, new_model_path: str) -> None:
        """Hot-swap the model without restarting the SDK.

        Loads a new model from the given path. If loading fails,
        the previous model state is preserved and a fallback event is emitted.

        Args:
            new_model_path: Path to the new model file.
        """
        previous_loaded = self._model_loaded
        previous_version = self._model_version

        try:
            if self._engine is None:
                raise RuntimeError("No inference engine available for model update")

            if hasattr(self._engine, "load_model"):
                self._engine.load_model(new_model_path)  # type: ignore[attr-defined]

            self._config.model_path = new_model_path
            self._model_loaded = True
            self._model_version = self._extract_model_version(new_model_path)

            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_MODEL_UPDATED",
                message=f"Model updated to {new_model_path}",
                timestamp=0.0,
                model_path=new_model_path,
            ))
        except Exception as e:
            # Restore previous state
            self._model_loaded = previous_loaded
            self._model_version = previous_version

            self._emit_event(ClassifierEvent(
                type="CLASSIFIER_FALLBACK",
                message=f"Model update failed: {e}",
                timestamp=0.0,
                model_path=new_model_path,
                error=e,
            ))

    # ── Event system ─────────────────────────────────────────────

    def on(self, listener: Callable[[ClassifierEvent], None]) -> None:
        """Register an event listener for classifier events."""
        self._listeners.append(listener)

    def off(self, listener: Callable[[ClassifierEvent], None]) -> None:
        """Remove an event listener."""
        self._listeners = [l for l in self._listeners if l is not listener]

    # ── Private helpers ──────────────────────────────────────────

    def _emit_event(self, event: ClassifierEvent) -> None:
        """Emit an event to all registered listeners."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                # Swallow listener errors to prevent cascading failures
                pass

    @staticmethod
    def _extract_model_version(model_path: str) -> str:
        """Extract version from path like 'models/classifier-v1.2.3.onnx'."""
        match = re.search(r"v?(\d+\.\d+\.\d+)", model_path)
        return match.group(1) if match else "unknown"


# ── EnsembleEvaluator ─────────────────────────────────────────────


class EnsembleEvaluator:
    """Combines regex detection results and ML classifier results.

    Handles ML unavailability gracefully by falling back to regex_only
    regardless of configured mode.

    Ensemble Modes:
    - regex_only: use only regex result, ignore ML (v1.2 backward compat)
    - ml_only: use only ML classifier output
    - ensemble_union: block if EITHER regex OR ml detects (higher recall)
    - ensemble_intersection: block only if BOTH detect (higher precision)
    """

    def evaluate(
        self,
        regex_result: bool,
        ml_result: Optional[Dict[str, Any]],
        mode: EnsembleMode,
    ) -> Dict[str, Any]:
        """Evaluate the combined detection result from regex and ML signals.

        Args:
            regex_result: Whether the regex layer detected a threat (True = detected).
            ml_result: The ML classifier result dict (with "detected" and "confidence"
                keys), or None if ML is unavailable.
            mode: The configured ensemble mode.

        Returns:
            Combined detection result dict with keys:
            - "detected" (bool): Whether content was detected as a threat.
            - "source" (str): Which signal source determined the outcome.
            - "confidence" (float): Confidence score in [0.0, 1.0].
        """
        # When ML is unavailable (None result), fall back to regex_only
        # regardless of configured mode
        if ml_result is None and mode != "regex_only":
            return {
                "detected": regex_result,
                "source": "regex",
                "confidence": 1.0 if regex_result else 0.0,
            }

        if mode == "regex_only":
            return self._evaluate_regex_only(regex_result)
        elif mode == "ml_only":
            return self._evaluate_ml_only(ml_result)  # type: ignore[arg-type]
        elif mode == "ensemble_union":
            return self._evaluate_union(regex_result, ml_result)  # type: ignore[arg-type]
        elif mode == "ensemble_intersection":
            return self._evaluate_intersection(regex_result, ml_result)  # type: ignore[arg-type]
        else:
            # Unknown mode — default to regex_only for safety
            return self._evaluate_regex_only(regex_result)

    # ── Private mode evaluators ──────────────────────────────────

    def _evaluate_regex_only(self, regex_result: bool) -> Dict[str, Any]:
        """regex_only: v1.2 backward-compatible behavior."""
        return {
            "detected": regex_result,
            "source": "regex",
            "confidence": 1.0 if regex_result else 0.0,
        }

    def _evaluate_ml_only(self, ml_result: Dict[str, Any]) -> Dict[str, Any]:
        """ml_only: uses only the ML classifier output."""
        return {
            "detected": ml_result["detected"],
            "source": "ml",
            "confidence": ml_result["confidence"],
        }

    def _evaluate_union(
        self, regex_result: bool, ml_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ensemble_union: block if EITHER regex OR ml detects (higher recall)."""
        detected = regex_result or ml_result["detected"]

        # Confidence: take the maximum confidence from whichever signal fired
        if regex_result and ml_result["detected"]:
            confidence = max(1.0, ml_result["confidence"])
            source = "ensemble"
        elif regex_result:
            confidence = 1.0
            source = "regex"
        elif ml_result["detected"]:
            confidence = ml_result["confidence"]
            source = "ml"
        else:
            confidence = ml_result["confidence"]
            source = "ensemble"

        return {"detected": detected, "source": source, "confidence": confidence}

    def _evaluate_intersection(
        self, regex_result: bool, ml_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """ensemble_intersection: block only if BOTH detect (higher precision)."""
        detected = regex_result and ml_result["detected"]

        # Confidence: when both detect, use ML confidence (more granular)
        if detected:
            confidence = ml_result["confidence"]
            source = "ensemble"
        elif regex_result and not ml_result["detected"]:
            confidence = ml_result["confidence"]
            source = "regex"
        elif not regex_result and ml_result["detected"]:
            confidence = ml_result["confidence"]
            source = "ml"
        else:
            confidence = ml_result["confidence"]
            source = "ensemble"

        return {"detected": detected, "source": source, "confidence": confidence}
