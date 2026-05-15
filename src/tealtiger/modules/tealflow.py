"""TealFlow — Declarative Governance Workflows (Python SDK).

Implements YAML-based workflow parsing, validation, and execution for
governance automation. Port of the TypeScript TealFlow module with
identical parsing logic, validation rules, and execution semantics.

Components:
- TealFlowParser: YAML parser and schema validator
- TealFlowEngine: Async workflow execution engine
- evaluate_expression: CEL-like conditional expression evaluator

Module: modules/tealflow
Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.1, 12.4, 12.5
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ── Data Classes ─────────────────────────────────────────────────


@dataclass
class TriggerConfig:
    """Trigger configuration for a TealFlow workflow."""

    agent_action: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    workflow_dispatch: Optional[Dict[str, Any]] = None
    policy_violation: Optional[Dict[str, Any]] = None


@dataclass
class Step:
    """A single step within a TealFlow job."""

    name: str = ""
    uses: Optional[str] = None
    with_params: Optional[Dict[str, Any]] = None
    if_condition: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    run: Optional[str] = None


@dataclass
class Job:
    """A job within a TealFlow workflow, containing ordered steps."""

    steps: List[Step] = field(default_factory=list)
    needs: Optional[List[str]] = None
    if_condition: Optional[str] = None
    env: Optional[Dict[str, str]] = None


@dataclass
class TealFlowWorkflow:
    """A complete TealFlow workflow definition."""

    name: str = ""
    on: TriggerConfig = field(default_factory=TriggerConfig)
    env: Optional[Dict[str, str]] = None
    jobs: Dict[str, Job] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of workflow validation."""

    valid: bool = True
    errors: List[str] = field(default_factory=list)


@dataclass
class FlowContext:
    """Context available during TealFlow workflow execution."""

    event: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)


@dataclass
class FlowResult:
    """Result of a TealFlow workflow execution."""

    success: bool = True
    jobs_completed: List[str] = field(default_factory=list)
    jobs_failed: List[str] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)


# ── Expression Evaluator ─────────────────────────────────────────


def evaluate_expression(expr: str, context: FlowContext) -> bool:
    """Simple expression evaluator for `if` conditionals.

    Supports:
    - Property access: event.risk_score, env.ENVIRONMENT, etc.
    - Comparisons: ==, !=, >, <, >=, <=
    - Boolean literals: true, false
    - String literals: 'value' or "value"
    - Numeric literals: 42, 3.14
    - Logical operators: &&, ||, !
    """
    trimmed = expr.strip()

    # Boolean literals
    if trimmed == "true":
        return True
    if trimmed == "false":
        return False

    # Negation
    if trimmed.startswith("!"):
        return not evaluate_expression(trimmed[1:], context)

    # Logical OR (lowest precedence)
    or_parts = _split_logical(trimmed, "||")
    if len(or_parts) > 1:
        return any(evaluate_expression(part, context) for part in or_parts)

    # Logical AND
    and_parts = _split_logical(trimmed, "&&")
    if len(and_parts) > 1:
        return all(evaluate_expression(part, context) for part in and_parts)

    # Parenthesized expression
    if trimmed.startswith("(") and trimmed.endswith(")"):
        return evaluate_expression(trimmed[1:-1], context)

    # Comparison operators (check in order to handle >= before >)
    comparison_ops = ["==", "!=", ">=", "<=", ">", "<"]
    for op in comparison_ops:
        idx = trimmed.find(op)
        if idx != -1:
            left = _resolve_value(trimmed[:idx].strip(), context)
            right = _resolve_value(trimmed[idx + len(op) :].strip(), context)
            return _compare_values(left, right, op)

    # Truthy check on a single value
    val = _resolve_value(trimmed, context)
    return bool(val)


def _split_logical(expr: str, operator: str) -> List[str]:
    """Split an expression by a logical operator, respecting parentheses."""
    parts: List[str] = []
    depth = 0
    current = ""
    i = 0

    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1

        if depth == 0 and expr[i : i + len(operator)] == operator:
            parts.append(current)
            current = ""
            i += len(operator)
        else:
            current += ch
            i += 1

    parts.append(current)
    return parts if len(parts) > 1 else [expr]


def _resolve_value(token: str, context: FlowContext) -> Any:
    """Resolve a value reference from the context.

    Supports: event.X, env.X, secrets.X, string literals, numeric literals.
    """
    trimmed = token.strip()

    # String literal
    if (trimmed.startswith("'") and trimmed.endswith("'")) or (
        trimmed.startswith('"') and trimmed.endswith('"')
    ):
        return trimmed[1:-1]

    # Numeric literal
    if trimmed and trimmed not in ("true", "false"):
        try:
            return float(trimmed) if "." in trimmed else int(trimmed)
        except ValueError:
            pass

    # Boolean literals
    if trimmed == "true":
        return True
    if trimmed == "false":
        return False

    # Context path resolution
    parts = trimmed.split(".")
    root = parts[0]
    path = parts[1:]

    if root == "event":
        obj: Any = context.event
    elif root == "env":
        obj = context.env
    elif root == "secrets":
        obj = context.secrets
    else:
        # Try resolving from event as default namespace
        obj = context.event
        return _resolve_path(obj, parts)

    return _resolve_path(obj, path)


def _resolve_path(obj: Any, path: List[str]) -> Any:
    """Resolve a dotted path on an object."""
    current = obj
    for key in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _compare_values(left: Any, right: Any, op: str) -> bool:
    """Compare two values with the given operator."""
    if op == "==":
        return left == right
    elif op == "!=":
        return left != right
    elif op == ">":
        return _to_number(left) > _to_number(right)
    elif op == "<":
        return _to_number(left) < _to_number(right)
    elif op == ">=":
        return _to_number(left) >= _to_number(right)
    elif op == "<=":
        return _to_number(left) <= _to_number(right)
    return False


def _to_number(val: Any) -> float:
    """Convert a value to a number for comparison."""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ── TealFlowParser ───────────────────────────────────────────────

# Pattern for secret references
SECRET_REF_PATTERN = re.compile(r"\$\{\{\s*secrets\.\w+\s*\}\}")


class TealFlowParser:
    """TealFlow YAML Parser and Validator.

    Parses TealFlow workflow YAML documents into typed TealFlowWorkflow objects
    and validates them against the TealFlow schema.
    """

    def parse(self, yaml_content: str) -> TealFlowWorkflow:
        """Parse a YAML string into a TealFlowWorkflow object.

        Args:
            yaml_content: Raw YAML string representing a TealFlow workflow.

        Returns:
            Parsed TealFlowWorkflow object.

        Raises:
            ValueError: If YAML is malformed or cannot be parsed.
        """
        raw = yaml.safe_load(yaml_content)

        if not raw or not isinstance(raw, dict):
            raise ValueError("TealFlow: Invalid YAML — document must be an object")

        # YAML parses `on:` as boolean True, so check both "on" and True keys
        on_value = raw.get("on") if "on" in raw else raw.get(True)

        workflow = TealFlowWorkflow(
            name=raw.get("name", ""),
            on=self._parse_triggers(on_value),
            jobs=self._parse_jobs(raw.get("jobs")),
        )

        if raw.get("env") and isinstance(raw["env"], dict):
            workflow.env = raw["env"]

        return workflow

    def validate(self, workflow: TealFlowWorkflow) -> ValidationResult:
        """Validate a TealFlowWorkflow object against the schema.

        Args:
            workflow: The workflow object to validate.

        Returns:
            ValidationResult with valid flag and any errors.
        """
        errors: List[str] = []

        # Required: name
        if not workflow.name or not isinstance(workflow.name, str):
            errors.append('Workflow must have a "name" field of type string')

        # Required: on (triggers)
        if not self._has_trigger(workflow.on):
            errors.append('Workflow must have an "on" field defining at least one trigger')
        else:
            self._validate_triggers(workflow.on, errors)

        # Required: jobs
        if not workflow.jobs:
            errors.append('Workflow must have a "jobs" field with at least one job')
        else:
            job_ids = list(workflow.jobs.keys())
            if len(job_ids) == 0:
                errors.append("Workflow must have at least one job defined")

            for job_id in job_ids:
                self._validate_job(job_id, workflow.jobs[job_id], job_ids, errors)

        # Validate env if present
        if workflow.env is not None and not isinstance(workflow.env, dict):
            errors.append('Workflow "env" must be an object if provided')

        # Validate secrets references are not exposing values
        self._validate_secrets_not_exposed(workflow, errors)

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    # ── Private Helpers ──────────────────────────────────────────

    def _has_trigger(self, triggers: TriggerConfig) -> bool:
        return (
            triggers.agent_action is not None
            or triggers.schedule is not None
            or triggers.workflow_dispatch is not None
            or triggers.policy_violation is not None
        )

    def _parse_triggers(self, raw: Any) -> TriggerConfig:
        if not raw or not isinstance(raw, dict):
            return TriggerConfig()

        config = TriggerConfig()

        if "agent_action" in raw:
            aa = raw["agent_action"] if isinstance(raw["agent_action"], dict) else {}
            config.agent_action = {"types": aa.get("types", [])}
            if "risk_score_above" in aa:
                config.agent_action["risk_score_above"] = aa["risk_score_above"]

        if "schedule" in raw:
            sched = raw["schedule"] if isinstance(raw["schedule"], dict) else {}
            config.schedule = {"cron": sched.get("cron", "")}

        if "workflow_dispatch" in raw:
            config.workflow_dispatch = {}

        if "policy_violation" in raw:
            pv = raw["policy_violation"] if isinstance(raw["policy_violation"], dict) else {}
            config.policy_violation = {}
            if "reason_codes" in pv:
                config.policy_violation["reason_codes"] = pv["reason_codes"]
            if "severity" in pv:
                config.policy_violation["severity"] = pv["severity"]

        return config

    def _parse_jobs(self, raw: Any) -> Dict[str, Job]:
        if not raw or not isinstance(raw, dict):
            return {}

        jobs: Dict[str, Job] = {}

        for job_id, job_raw in raw.items():
            if not isinstance(job_raw, dict):
                continue

            job = Job(steps=self._parse_steps(job_raw.get("steps")))

            if "needs" in job_raw:
                needs = job_raw["needs"]
                job.needs = needs if isinstance(needs, list) else [needs]

            if "if" in job_raw:
                job.if_condition = job_raw["if"]

            if "env" in job_raw and isinstance(job_raw["env"], dict):
                job.env = job_raw["env"]

            jobs[job_id] = job

        return jobs

    def _parse_steps(self, raw: Any) -> List[Step]:
        if not isinstance(raw, list):
            return []

        steps: List[Step] = []
        for step_raw in raw:
            if not isinstance(step_raw, dict):
                continue

            step = Step(name=step_raw.get("name", ""))

            if "uses" in step_raw:
                step.uses = step_raw["uses"]

            if "with" in step_raw and isinstance(step_raw["with"], dict):
                step.with_params = step_raw["with"]

            if "if" in step_raw:
                step.if_condition = step_raw["if"]

            if "env" in step_raw and isinstance(step_raw["env"], dict):
                step.env = step_raw["env"]

            if "run" in step_raw:
                step.run = step_raw["run"]

            steps.append(step)

        return steps

    def _validate_triggers(self, triggers: TriggerConfig, errors: List[str]) -> None:
        if not self._has_trigger(triggers):
            errors.append('Workflow must define at least one trigger in "on" field')

        if triggers.agent_action is not None:
            if not isinstance(triggers.agent_action.get("types"), list):
                errors.append('Trigger "agent_action" must have a "types" array')

        if triggers.schedule is not None:
            cron = triggers.schedule.get("cron")
            if not cron or not isinstance(cron, str):
                errors.append('Trigger "schedule" must have a "cron" string')

        if triggers.policy_violation is not None:
            reason_codes = triggers.policy_violation.get("reason_codes")
            if reason_codes is not None and not isinstance(reason_codes, list):
                errors.append('Trigger "policy_violation.reason_codes" must be an array')
            severity = triggers.policy_violation.get("severity")
            if severity is not None and not isinstance(severity, list):
                errors.append('Trigger "policy_violation.severity" must be an array')

    def _validate_job(
        self, job_id: str, job: Job, all_job_ids: List[str], errors: List[str]
    ) -> None:
        # Steps required
        if not job.steps or len(job.steps) == 0:
            errors.append(f'Job "{job_id}" must have at least one step')
        else:
            for i, step in enumerate(job.steps):
                self._validate_step(job_id, i, step, errors)

        # Validate needs references
        if job.needs:
            for dep in job.needs:
                if dep not in all_job_ids:
                    errors.append(f'Job "{job_id}" depends on unknown job "{dep}"')
                if dep == job_id:
                    errors.append(f'Job "{job_id}" cannot depend on itself')

    def _validate_step(self, job_id: str, step_index: int, step: Step, errors: List[str]) -> None:
        if not step.name or not isinstance(step.name, str):
            errors.append(f'Job "{job_id}", step {step_index}: must have a "name" field')

        # A step must have either `uses` or `run`
        if not step.uses and not step.run:
            errors.append(
                f'Job "{job_id}", step "{step.name}": must have either "uses" or "run"'
            )

    def _validate_secrets_not_exposed(
        self, workflow: TealFlowWorkflow, errors: List[str]
    ) -> None:
        """Check that secret references use the ${{ secrets.NAME }} pattern."""

        def check_env(env: Optional[Dict[str, str]], ctx: str) -> None:
            if not env:
                return
            for key, value in env.items():
                if any(
                    kw in key.lower() for kw in ("secret", "token", "password")
                ):
                    if isinstance(value, str) and not SECRET_REF_PATTERN.search(value):
                        errors.append(
                            f'{ctx}: env var "{key}" appears to contain a hardcoded secret. '
                            "Use ${{ secrets.NAME }} syntax instead"
                        )

        check_env(workflow.env, "Workflow")

        for job_id, job in workflow.jobs.items():
            check_env(job.env, f'Job "{job_id}"')
            for step in job.steps:
                check_env(step.env, f'Job "{job_id}", step "{step.name}"')


# ── TealFlowEngine ──────────────────────────────────────────────


@dataclass
class _JobResult:
    """Internal result of a single job execution."""

    success: bool = True
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class TealFlowEngine:
    """TealFlow Execution Engine.

    Executes TealFlow workflows by:
    - Running steps sequentially within a job
    - Running independent jobs in parallel (asyncio.gather for jobs without `needs`)
    - Implementing `needs` dependency resolution
    - Evaluating `if` conditional expressions against context
    - Handling job failures (dependent jobs are skipped)
    """

    async def execute(self, workflow: TealFlowWorkflow, context: FlowContext) -> FlowResult:
        """Execute a TealFlow workflow with the given context.

        Args:
            workflow: The parsed TealFlowWorkflow to execute.
            context: The execution context (event, env, secrets).

        Returns:
            FlowResult with success status, completed/failed jobs, and outputs.
        """
        job_results: Dict[str, _JobResult] = {}
        job_ids = list(workflow.jobs.keys())
        completed: List[str] = []
        failed: List[str] = []
        outputs: Dict[str, Any] = {}

        # Merge workflow-level env into context
        merged_env = dict(context.env)
        if workflow.env:
            merged_env.update(workflow.env)
        merged_context = FlowContext(
            event=context.event,
            env=merged_env,
            secrets=context.secrets,
        )

        # Build dependency graph
        dependency_graph = self._build_dependency_graph(workflow.jobs)

        # Execute jobs in topological order
        await self._execute_jobs_in_order(
            job_ids,
            workflow.jobs,
            dependency_graph,
            merged_context,
            job_results,
            completed,
            failed,
            outputs,
        )

        return FlowResult(
            success=len(failed) == 0,
            jobs_completed=completed,
            jobs_failed=failed,
            outputs=outputs,
        )

    # ── Private Helpers ──────────────────────────────────────────

    def _build_dependency_graph(self, jobs: Dict[str, Job]) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {}
        for job_id, job in jobs.items():
            graph[job_id] = job.needs if job.needs else []
        return graph

    async def _execute_jobs_in_order(
        self,
        job_ids: List[str],
        jobs: Dict[str, Job],
        dependency_graph: Dict[str, List[str]],
        context: FlowContext,
        job_results: Dict[str, _JobResult],
        completed: List[str],
        failed: List[str],
        outputs: Dict[str, Any],
    ) -> None:
        remaining = set(job_ids)
        executing: set = set()

        while remaining:
            # Find jobs whose dependencies are all satisfied
            ready: List[str] = []
            for job_id in remaining:
                if job_id in executing:
                    continue
                deps = dependency_graph.get(job_id, [])
                all_deps_resolved = all(dep in job_results for dep in deps)
                if all_deps_resolved:
                    ready.append(job_id)

            if not ready and not executing:
                # Circular dependency or unresolvable — mark remaining as failed
                for job_id in remaining:
                    failed.append(job_id)
                    job_results[job_id] = _JobResult(
                        success=False, outputs={}, error="Unresolvable dependencies"
                    )
                break

            if not ready:
                break

            # Execute all ready jobs in parallel
            async def _run_job(jid: str) -> None:
                executing.add(jid)

                # Check if any dependency failed → skip this job
                deps = dependency_graph.get(jid, [])
                dep_failed = any(
                    jid_dep in job_results and not job_results[jid_dep].success
                    for jid_dep in deps
                )

                if dep_failed:
                    job_results[jid] = _JobResult(
                        success=False, outputs={}, error="Skipped: dependency failed"
                    )
                    failed.append(jid)
                    remaining.discard(jid)
                    executing.discard(jid)
                    return

                # Evaluate job-level `if` condition
                job = jobs[jid]
                if job.if_condition is not None:
                    condition_met = evaluate_expression(job.if_condition, context)
                    if not condition_met:
                        # Job skipped due to condition — counts as completed (not failed)
                        job_results[jid] = _JobResult(success=True, outputs={})
                        completed.append(jid)
                        remaining.discard(jid)
                        executing.discard(jid)
                        return

                # Execute the job
                result = await self._execute_job(jid, job, context)
                job_results[jid] = result

                if result.success:
                    completed.append(jid)
                    if result.outputs:
                        outputs[jid] = result.outputs
                else:
                    failed.append(jid)

                remaining.discard(jid)
                executing.discard(jid)

            await asyncio.gather(*[_run_job(jid) for jid in ready])

    async def _execute_job(
        self, _job_id: str, job: Job, context: FlowContext
    ) -> _JobResult:
        job_outputs: Dict[str, Any] = {}

        # Merge job-level env into context
        job_env = dict(context.env)
        if job.env:
            job_env.update(job.env)
        job_context = FlowContext(event=context.event, env=job_env, secrets=context.secrets)

        # Execute steps sequentially
        for step in job.steps:
            try:
                step_result = await self._execute_step(step, job_context)
                if step_result is not None:
                    job_outputs[step.name] = step_result
            except Exception as e:
                return _JobResult(success=False, outputs=job_outputs, error=str(e))

        return _JobResult(success=True, outputs=job_outputs)

    async def _execute_step(self, step: Step, context: FlowContext) -> Any:
        # Evaluate step-level `if` condition
        if step.if_condition is not None:
            condition_met = evaluate_expression(step.if_condition, context)
            if not condition_met:
                return None

        # Execute the step action
        if step.uses:
            return await self._execute_action(step.uses, step.with_params or {}, context)

        if step.run:
            # Inline command — in governance context, this is a no-op placeholder
            return {"ran": step.run}

        return None

    async def _execute_action(
        self, uses: str, params: Dict[str, Any], _context: FlowContext
    ) -> Any:
        """Execute a reusable action reference.

        Placeholder: returns action metadata. In production, this would
        resolve the action from a local/remote registry.
        """
        return {"action": uses, "params": params, "executed": True}
