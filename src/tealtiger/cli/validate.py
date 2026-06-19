"""CLI subcommand for validating policy files.

Validates TealTiger policy files (JSON/YAML) against the expected schema:
- Required top-level fields: id, name, description, rules
- Each rule must have: condition, action, reason
- Valid actions: allow, deny, transform, redact, require_approval, degrade

Usage:
    tealtiger validate policy.json
    tealtiger validate policy.yaml
    tealtiger validate my-policy.json --format json
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import click
import yaml


# Valid actions as defined in core/engine/types.py DecisionAction enum
VALID_ACTIONS: Set[str] = {
    "allow",
    "deny",
    "transform",
    "redact",
    "require_approval",
    "degrade",
}


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, line: int, message: str) -> None:
        self.line = line
        self.message = message

    def __str__(self) -> str:
        return f"Line {self.line}: {self.message}"


class PolicyValidator:
    """Validates TealTiger policy files against the schema."""

    def __init__(self) -> None:
        self.errors: List[ValidationError] = []

    def validate(self, data: Dict[str, Any], path: str) -> bool:
        """Validate a parsed policy document.

        Returns True if valid, False otherwise (errors populated in self.errors).
        """
        if not isinstance(data, dict):
            self.errors.append(ValidationError(0, f"Policy file must be a JSON/YAML object, got {type(data).__name__}"))
            return False

        # Check required top-level fields
        for field in ("id", "name", "description", "rules"):
            if field not in data:
                self.errors.append(ValidationError(0, f"Missing required field: '{field}'"))

        # Validate id is a non-empty string
        if "id" in data and not isinstance(data["id"], str):
            self.errors.append(ValidationError(0, f"Field 'id' must be a string, got {type(data['id']).__name__}"))
        elif "id" in data and not data["id"].strip():
            self.errors.append(ValidationError(0, "Field 'id' must not be empty"))

        # Validate name is a non-empty string
        if "name" in data and not isinstance(data["name"], str):
            self.errors.append(ValidationError(0, f"Field 'name' must be a string, got {type(data['name']).__name__}"))
        elif "name" in data and not data["name"].strip():
            self.errors.append(ValidationError(0, "Field 'name' must not be empty"))

        # Validate description is a non-empty string
        if "description" in data and not isinstance(data["description"], str):
            self.errors.append(ValidationError(0, f"Field 'description' must be a string, got {type(data['description']).__name__}"))

        # Validate rules is a non-empty list
        if "rules" in data:
            if not isinstance(data["rules"], list):
                self.errors.append(ValidationError(0, f"Field 'rules' must be a list, got {type(data['rules']).__name__}"))
            elif len(data["rules"]) == 0:
                self.errors.append(ValidationError(0, "Field 'rules' must not be empty"))
            else:
                self._validate_rules(data["rules"])

        # Warn about optional 'enabled' field if present
        if "enabled" in data:
            if not isinstance(data["enabled"], bool):
                self.errors.append(ValidationError(0, f"Field 'enabled' must be a boolean, got {type(data['enabled']).__name__}"))

        return len(self.errors) == 0

    def _validate_rules(self, rules: List[Any]) -> None:
        """Validate each rule in the rules list."""
        for i, rule in enumerate(rules):
            rule_start = i + 1  # 1-indexed for readability
            if not isinstance(rule, dict):
                self.errors.append(ValidationError(rule_start, f"Rule {i + 1} must be an object, got {type(rule).__name__}"))
                continue

            # Check required rule fields
            for field in ("condition", "action", "reason"):
                if field not in rule:
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1} missing required field: '{field}'"))

            # Validate action
            if "action" in rule:
                action = rule["action"]
                if not isinstance(action, str):
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1}: 'action' must be a string, got {type(action).__name__}"))
                elif action.lower() not in VALID_ACTIONS:
                    self.errors.append(
                        ValidationError(
                            rule_start,
                            f"Rule {i + 1}: unknown action '{action}' (did you mean one of: {', '.join(sorted(VALID_ACTIONS))}?)",
                        )
                    )

            # Validate condition is a non-empty object
            if "condition" in rule:
                cond = rule["condition"]
                if not isinstance(cond, dict):
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1}: 'condition' must be an object"))
                elif len(cond) == 0:
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1}: 'condition' must not be empty"))

            # Validate reason is a non-empty string
            if "reason" in rule:
                reason = rule["reason"]
                if not isinstance(reason, str):
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1}: 'reason' must be a string, got {type(reason).__name__}"))
                elif not reason.strip():
                    self.errors.append(ValidationError(rule_start, f"Rule {i + 1}: 'reason' must not be empty"))


def _load_policy(path: str) -> Dict[str, Any]:
    """Load and parse a policy file (JSON or YAML)."""
    file_path = Path(path)

    if not file_path.exists():
        click.echo(f"Error: File not found: {path}", err=True)
        sys.exit(1)

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        click.echo(f"Error: Cannot read file: {e}", err=True)
        sys.exit(1)

    ext = file_path.suffix.lower()

    try:
        if ext in (".json",):
            data = json.loads(content)
        elif ext in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        else:
            # Try JSON first, then YAML
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        click.echo(f"Error: Invalid {ext or 'file'} format: {e}", err=True)
        sys.exit(1)

    return data


@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (text or json)",
)
def validate(path: str, output_format: str) -> None:
    """Validate a TealTiger policy file.

    Checks that the policy file has the correct schema:
    - Required fields: id, name, description, rules
    - Each rule must have: condition, action, reason
    - Valid actions: allow, deny, transform, redact, require_approval, degrade

    Examples:

        # Validate a JSON policy
        tealtiger validate my-policy.json

        # Validate a YAML policy
        tealtiger validate policies/production.yaml

        # Get JSON output for CI/CD pipelines
        tealtiger validate policy.json --format json
    """
    data = _load_policy(path)

    validator = PolicyValidator()
    is_valid = validator.validate(data, path)

    if output_format == "json":
        result = {
            "file": path,
            "valid": is_valid,
            "errors": [str(e) for e in validator.errors],
            "error_count": len(validator.errors),
        }
        click.echo(json.dumps(result, indent=2))
        sys.exit(1 if not is_valid else 0)
    else:
        if is_valid:
            rule_count = len(data.get("rules", [])) if isinstance(data, dict) else 0
            click.echo(f"\u2713 Policy '{data.get('name', path)}' is valid ({rule_count} rules)")
            sys.exit(0)
        else:
            click.echo(f"\u2717 Policy '{path}' has {len(validator.errors)} error(s):", err=True)
            for error in validator.errors:
                click.echo(f"  {error}", err=True)
            sys.exit(1)
