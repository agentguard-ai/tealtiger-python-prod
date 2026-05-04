"""
TealTiger Governance Sidecar — Python HTTP Server

Exposes TealEngine as a language-agnostic HTTP API.
Any agent (Go, Rust, Java, TypeScript, etc.) can call this sidecar
over HTTP to get governance decisions without importing the SDK.

Endpoints:
  POST /evaluate   — Policy evaluation (returns Decision)
  POST /validate   — TEEC validation
  POST /scan       — Secret/PII detection
  GET  /health     — Health check
  GET  /ready      — Readiness probe
  GET  /modules    — List active governance modules

Environment variables:
  TEALTIGER_PORT          HTTP port (default: 8080)
  TEALTIGER_HOST          Bind address (default: 0.0.0.0)
  TEALTIGER_MODE          Policy mode: ENFORCE | MONITOR | REPORT_ONLY (default: ENFORCE)
  TEALTIGER_POLICY_DIR    Path to policy JSON files (default: /etc/tealtiger/policies)
  TEALTIGER_LOG_LEVEL     Log level: info | debug | warn | error (default: info)
  TEALTIGER_MAX_BODY_BYTES Max request body size in bytes (default: 1048576)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# ── Config from environment ──────────────────────────────────────

PORT = int(os.environ.get("TEALTIGER_PORT", "8080"))
HOST = os.environ.get("TEALTIGER_HOST", "0.0.0.0")
POLICY_DIR = os.environ.get("TEALTIGER_POLICY_DIR", "/etc/tealtiger/policies")
POLICY_MODE = os.environ.get("TEALTIGER_MODE", "ENFORCE").upper()
LOG_LEVEL = os.environ.get("TEALTIGER_LOG_LEVEL", "info").upper()
MAX_BODY_SIZE = int(os.environ.get("TEALTIGER_MAX_BODY_BYTES", str(1024 * 1024)))

# ── Logger ───────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='{"ts": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("tealtiger.sidecar")

# ── Policy loader ────────────────────────────────────────────────

def load_policies() -> dict[str, Any]:
    policy: dict[str, Any] = {}
    policy_path = Path(POLICY_DIR)

    if not policy_path.exists():
        logger.info(f"Policy directory not found, using empty policy: {POLICY_DIR}")
        return policy

    for file in policy_path.glob("*.json"):
        try:
            content = file.read_text(encoding="utf-8")
            parsed = json.loads(content)
            policy.update(parsed)
            logger.info(f"Loaded policy file: {file.name}")
        except Exception as e:
            logger.warning(f"Failed to load policy file {file.name}: {e}")

    return policy

# ── Engine initialization ────────────────────────────────────────

_start_time = time.time()
_policy = load_policies()

# Import TealEngine — graceful fallback if v1.2 not yet available
_engine = None
_engine_version = "standalone"

try:
    # Try importing just the engine without triggering the full package
    import importlib
    engine_mod = importlib.import_module("tealtiger.core.engine")
    TealEngine = getattr(engine_mod, "TealEngine", None)
    ModeConfig = getattr(engine_mod, "ModeConfig", None)
    PolicyModeEnum = getattr(engine_mod, "PolicyMode", None)

    if TealEngine and ModeConfig and PolicyModeEnum:
        # Resolve the policy mode from environment variable
        mode_value = getattr(PolicyModeEnum, POLICY_MODE, PolicyModeEnum.ENFORCE)
        mode_config = ModeConfig(default=mode_value)

        _engine = TealEngine(
            policies=_policy,
            mode=mode_config,
        )
        _engine_version = "1.2"
        logger.info(f"TealEngine v1.2 initialized, mode={POLICY_MODE}, policy_keys={list(_policy.keys())}")
    else:
        logger.info("TealEngine class not found — running in standalone mode")
except Exception as e:
    logger.info(f"TealEngine not available ({e}) — running in standalone mode (health/validate still work)")

# ── Request handler ──────────────────────────────────────────────

class GovernanceHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the TealTiger governance sidecar."""

    server_version = "TealTiger/1.2"
    sys_version = ""  # suppress Python version in Server header

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Override to use structured logging."""
        logger.debug(f"{self.address_string()} - {format % args}")

    # ── Helpers ──────────────────────────────────────────────────

    def _read_body(self) -> bytes | None:
        """Read request body with size limit."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_BODY_SIZE:
            self._send_error(413, "Request body too large")
            return None
        return self.rfile.read(content_length)

    def _send_json(self, status: int, body: Any) -> None:
        """Send a JSON response."""
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-TealTiger-Version", "1.2.0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, status: int, message: str, details: Any = None) -> None:
        body: dict[str, Any] = {"error": message}
        if details is not None:
            body["details"] = str(details)
        self._send_json(status, body)

    def _parse_json_body(self) -> dict[str, Any] | None:
        raw = self._read_body()
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._send_error(400, "Invalid JSON body", str(e))
            return None

    # ── Route handlers ────────────────────────────────────────────

    def _handle_evaluate(self) -> None:
        payload = self._parse_json_body()
        if payload is None:
            return

        if _engine is None:
            return self._send_error(503, "TealEngine not available")

        correlation_id = payload.get("correlation_id") or str(uuid.uuid4())
        request = payload.get("request", payload)

        try:
            # Build context for evaluation
            eval_context = {
                **request,
                "agent_id": payload.get("agent_id"),
                "user_id": payload.get("user_id"),
                "session_id": payload.get("session_id"),
                "tenant_id": payload.get("tenant_id"),
                "correlation_id": correlation_id,
            }

            # Use evaluate_with_mode which returns a Decision object
            from tealtiger.core.context import ContextManager
            exec_context = ContextManager.create_context()

            decision = _engine.evaluate_with_mode(eval_context, exec_context)

            logger.debug(
                f"Evaluation complete: correlation_id={correlation_id} "
                f"action={decision.action} risk_score={decision.risk_score}"
            )

            # Convert Decision to dict for JSON serialization
            decision_dict = decision.model_dump() if hasattr(decision, "model_dump") else decision.__dict__

            self._send_json(200, {
                "correlation_id": correlation_id,
                "decision": decision_dict,
            })
        except Exception as e:
            logger.error(f"Evaluation failed: correlation_id={correlation_id} error={e}")
            self._send_error(500, "Evaluation failed", e)

    def _handle_validate(self) -> None:
        payload = self._parse_json_body()
        if payload is None:
            return

        decision = payload.get("decision")
        if not decision:
            return self._send_error(400, 'Missing "decision" field in request body')

        # Basic TEEC validation — check required fields
        required_fields = ["action", "reason_codes", "correlation_id"]
        missing = [f for f in required_fields if f not in decision]
        valid = len(missing) == 0
        results = [
            {"field": f, "valid": False, "message": f"Missing required field: {f}"}
            for f in missing
        ]
        if valid:
            results = [{"valid": True, "message": "Decision is TEEC-compliant"}]

        self._send_json(200, {"valid": valid, "results": results})

    def _handle_scan(self) -> None:
        payload = self._parse_json_body()
        if payload is None:
            return

        content = payload.get("content")
        if not content:
            return self._send_error(400, 'Missing "content" field in request body')

        correlation_id = payload.get("correlation_id") or str(uuid.uuid4())

        if _engine is None:
            return self._send_error(503, "TealEngine not available")

        try:
            from tealtiger.core.context import ContextManager
            exec_context = ContextManager.create_context()

            decision = _engine.evaluate_with_mode(
                {"content": content, "scan_type": "secrets", "correlation_id": correlation_id},
                exec_context,
            )

            findings = getattr(decision, "findings", []) or []
            self._send_json(200, {
                "correlation_id": correlation_id,
                "findings": findings,
                "action": decision.action.value if hasattr(decision.action, "value") else str(decision.action),
                "risk_score": getattr(decision, "risk_score", 0),
            })
        except Exception as e:
            logger.error(f"Scan failed: correlation_id={correlation_id} error={e}")
            self._send_error(500, "Scan failed", e)

    def _handle_health(self) -> None:
        self._send_json(200, {
            "status": "ok",
            "version": "1.2.0",
            "engine_version": _engine_version,
            "mode": POLICY_MODE,
            "uptime_seconds": round(time.time() - _start_time),
        })

    def _handle_ready(self) -> None:
        ready = _engine is not None
        self._send_json(200 if ready else 503, {"ready": ready})

    def _handle_modules(self) -> None:
        if _engine is None:
            return self._send_json(200, {"modules": {}})
        try:
            status = _engine.get_module_status() if hasattr(_engine, "get_module_status") else {}
            self._send_json(200, {"modules": status})
        except Exception as e:
            self._send_error(500, "Failed to get module status", e)

    # ── Router ────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/evaluate":
            self._handle_evaluate()
        elif path == "/validate":
            self._handle_validate()
        elif path == "/scan":
            self._handle_scan()
        else:
            self._send_error(404, f"Route not found: POST {path}")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            self._handle_health()
        elif path == "/ready":
            self._handle_ready()
        elif path == "/modules":
            self._handle_modules()
        else:
            self._send_error(404, f"Route not found: GET {path}")


# ── Server startup ───────────────────────────────────────────────

def main() -> None:
    server = HTTPServer((HOST, PORT), GovernanceHandler)

    def shutdown(signum: int, _frame: Any) -> None:
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, shutting down gracefully")
        server.server_close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(
        f"TealTiger governance sidecar started: "
        f"host={HOST} port={PORT} mode={POLICY_MODE} policy_dir={POLICY_DIR}"
    )
    logger.info(
        "Endpoints: POST /evaluate, POST /validate, POST /scan, "
        "GET /health, GET /ready, GET /modules"
    )

    server.serve_forever()


if __name__ == "__main__":
    main()
