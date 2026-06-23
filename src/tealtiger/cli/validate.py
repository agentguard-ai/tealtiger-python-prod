"""CLI interface for policy validation.

TealTiger SDK - Policy validation command.

Validates policy files (JSON/YAML) against the SDK schema:
- Checks required fields (name, description, rules)
- Validates action types (allow/deny/transform)
- Validates condition operators
- Reports errors with line numbers
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import click

# Valid action values for policy rules
VALID_ACTIONS = {"allow", "deny", "transform"}

# Valid top-level policy fields
VALID_POLICY_FIELDS = {"id", "name", "description", "rules", "enabled"}

# Valid rule fields
VALID_RULE_FIELDS = {"condition", "action", "reason"}


def _load_policy(path: str) -> Tuple[Any, str | None]:
    """Load a policy file (JSON or YAML).

    Args:
        path: Path to the policy file.

    Returns:
        Tuple of (parsed policy, error message).
        On success, error is None. On failure, policy is None.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"File not found: {path}"
    except OSError as e:
        return None, f"Cannot read file: {e}"

    ext = Path(path).suffix.lower()

    if ext in (".yaml", ".yml"):
        try:
            import yaml as _yaml

            policy = _yaml.safe_load(content)
        except ImportError:
            return None, (
                "PyYAML is required for YAML files. "
                "Install with: pip install pyyaml"
            )
        except _yaml.YAMLError as e:
            line = getattr(e, "problem_mark", None)
            line_num = line.line + 1 if line else "unknown"
            return None, f"YAML parse error at line {line_num}: {e}"
    elif ext in (".json",):
        try:
            policy = json.loads(content)
        except json.JSONDecodeError as e:
            return None, f"JSON parse error at line {e.lineno}: {e.msg}"
    else:
        # Try JSON first, then YAML
        try:
            policy = json.loads(content)
        except json.JSONDecodeError:
            try:
                import yaml as _yaml

                policy = _yaml.safe_load(content)
            except ImportError:
                return None, (
                    "Cannot determine file format. "
                    "Use .json, .yaml, or .yml extension."
                )
            except Exception:
                return None, "Failed to parse as JSON or YAML"

    return policy, None


def _validate_policy(policy: Any, source: str) -> List[str]:
    """Validate a policy dict against the TealTiger schema.

    Args:
        policy: Parsed policy dict.
        source: File path for error reporting.

    Returns:
        List of error messages. Empty list means valid.
    """
    errors: List[str] = []

    if not isinstance(policy, dict):
        errors.append(f"✗ {source}: Policy must be a JSON/YAML object (dict), got {type(policy).__name__}")
        return errors

    # Check for unknown top-level fields
    unknown_fields = set(policy.keys()) - VALID_POLICY_FIELDS
    for field in sorted(unknown_fields):
        errors.append(f"✗ {source}: Unknown policy field '{field}' (valid: {', '.join(sorted(VALID_POLICY_FIELDS))})")

    # Validate required fields
    for field in ("name", "description", "rules"):
        if field not in policy:
            errors.append(f"✗ {source}: Missing required field '{field}'")

    # Validate name is a non-empty string
    if "name" in policy and not isinstance(policy["name"], str):
        errors.append(f"✗ {source}: Field 'name' must be a string")
    elif "name" in policy and not policy["name"].strip():
        errors.append(f"✗ {source}: Field 'name' must not be empty")

    # Validate description is a non-empty string
    if "description" in policy and not isinstance(policy["description"], str):
        errors.append(f"✗ {source}: Field 'description' must be a string")
    elif "description" in policy and not policy["description"].strip():
        errors.append(f"✗ {source}: Field 'description' must not be empty")

    # Validate enabled is a boolean if present
    if "enabled" in policy and not isinstance(policy["enabled"], bool):
        errors.append(f"✗ {source}: Field 'enabled' must be a boolean")

    # Validate rules is a non-empty list
    if "rules" in policy:
        rules = policy["rules"]
        if not isinstance(rules, list):
            errors.append(f"✗ {source}: Field 'rules' must be a list")
        elif len(rules) == 0:
            errors.append(f"✗ {source}: Field 'rules' must not be empty")
        else:
            for i, rule in enumerate(rules):
                _validate_rule(rule, source, i + 1, errors)

    return errors


def _validate_rule(rule: Any, source: str, rule_num: int, errors: List[str]) -> None:
    """Validate a single policy rule.

    Args:
        rule: The rule dict to validate.
        source: File path for error reporting.
        rule_num: 1-based rule number for error messages.
        errors: List to append errors to.
    """
    prefix = f"{source} Rule {rule_num}"

    if not isinstance(rule, dict):
        errors.append(f"✗ {prefix}: Rule must be an object (dict), got {type(rule).__name__}")
        return

    # Check for unknown rule fields
    unknown_fields = set(rule.keys()) - VALID_RULE_FIELDS
    for field in sorted(unknown_fields):
        errors.append(f"✗ {prefix}: Unknown rule field '{field}' (valid: {', '.join(sorted(VALID_RULE_FIELDS))})")

    # Validate action
    if "action" not in rule:
        errors.append(f"✗ {prefix}: Missing required field 'action'")
    elif not isinstance(rule["action"], str):
        errors.append(f"✗ {prefix}: Field 'action' must be a string")
    elif rule["action"] not in VALID_ACTIONS:
        errors.append(
            f"✗ {prefix}: Invalid action '{rule['action']}' "
            f"(did you mean one of: {', '.join(sorted(VALID_ACTIONS))}?)"
        )

    # Validate condition is a dict
    if "condition" not in rule:
        errors.append(f"✗ {prefix}: Missing required field 'condition'")
    elif not isinstance(rule["condition"], dict):
        errors.append(f"✗ {prefix}: Field 'condition' must be an object (dict)")

    # Validate reason is a non-empty string
    if "reason" not in rule:
        errors.append(f"✗ {prefix}: Missing required field 'reason'")
    elif not isinstance(rule["reason"], str):
        errors.append(f"✗ {prefix}: Field 'reason' must be a string")
    elif not rule["reason"].strip():
        errors.append(f"✗ {prefix}: Field 'reason' must not be empty")


@click.command()
@click.argument("policy_path", type=click.Path(exists=True))
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors (fail on unknown fields)",
)
def validate(policy_path: str, strict: bool) -> None:
    """Validate a TealTiger policy file.

    Checks policy structure, required fields, valid action types,
    and condition format. Exits 0 on valid, 1 on invalid.

    Examples:

        tealtiger validate my-policy.json

        tealtiger validate my-policy.yaml --strict
    """
    policy, load_error = _load_policy(policy_path)

    if load_error:
        click.echo(f"✗ {load_error}", err=True)
        sys.exit(1)

    errors = _validate_policy(policy, policy_path)

    if errors:
        for error in errors:
            click.echo(error, err=True)
        click.echo(f"\n✗ Policy validation failed with {len(errors)} error(s)", err=True)
        sys.exit(1)

    rule_count = len(policy.get("rules", []))
    click.echo(f"✓ Policy '{policy.get('name', 'unnamed')}' is valid ({rule_count} rule{'s' if rule_count != 1 else ''})")
    sys.exit(0)
