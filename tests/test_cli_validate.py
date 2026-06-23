"""Tests for the policy validation CLI command."""

import json
import tempfile
from pathlib import Path

from tealtiger.cli.validate import (
    VALID_ACTIONS,
    _load_policy,
    _validate_policy,
)


class TestLoadPolicy:
    """Tests for policy file loading."""

    def test_load_valid_json(self):
        """Test loading a valid JSON policy file."""
        policy = {"name": "test", "description": "desc", "rules": []}
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            json.dump(policy, f)
            f.flush()
            path = f.name

        try:
            result, error = _load_policy(path)
            assert error is None
            assert result == policy
        finally:
            Path(path).unlink()

    def test_load_invalid_json(self):
        """Test loading an invalid JSON file returns an error."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w", delete=False
        ) as f:
            f.write("{invalid json}")
            f.flush()
            path = f.name

        try:
            result, error = _load_policy(path)
            assert result is None
            assert error is not None
            assert "parse error" in (error or "").lower()
        finally:
            Path(path).unlink()

    def test_load_missing_file(self):
        """Test loading a non-existent file returns an error."""
        result, error = _load_policy("/nonexistent/path/policy.json")
        assert result is None
        assert "not found" in error.lower()

    def test_load_yaml_file(self):
        """Test loading a YAML policy file."""
        try:
            import yaml  # noqa: F811
        except ImportError:
            return  # Skip if PyYAML not installed

        policy = {"name": "test", "description": "desc", "rules": []}
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False
        ) as f:
            yaml.dump(policy, f)
            f.flush()
            path = f.name

        try:
            result, error = _load_policy(path)
            assert error is None
            assert result["name"] == "test"
        finally:
            Path(path).unlink()


class TestValidatePolicy:
    """Tests for policy validation logic."""

    def test_valid_policy(self):
        """Test a fully valid policy passes validation."""
        policy = {
            "name": "production-allowlist",
            "description": "Allow all tools in production",
            "rules": [
                {
                    "condition": {"tool_name": "file-read"},
                    "action": "allow",
                    "reason": "Reads are allowed",
                }
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert errors == []

    def test_valid_policy_multiple_rules(self):
        """Test a policy with multiple rules passes validation."""
        policy = {
            "name": "multi-rule",
            "description": "Multiple rules",
            "rules": [
                {
                    "condition": {"tool_name": "file-read"},
                    "action": "allow",
                    "reason": "Reads allowed",
                },
                {
                    "condition": {"tool_name": "file-write"},
                    "action": "deny",
                    "reason": "Writes denied",
                },
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert errors == []

    def test_missing_name(self):
        """Test missing required 'name' field."""
        policy = {"description": "no name", "rules": []}
        errors = _validate_policy(policy, "policy.json")
        assert any("name" in e for e in errors)

    def test_missing_description(self):
        """Test missing required 'description' field."""
        policy = {"name": "test", "rules": []}
        errors = _validate_policy(policy, "policy.json")
        assert any("description" in e for e in errors)

    def test_missing_rules(self):
        """Test missing required 'rules' field."""
        policy = {"name": "test", "description": "desc"}
        errors = _validate_policy(policy, "policy.json")
        assert any("rules" in e for e in errors)

    def test_unknown_action(self):
        """Test invalid action type in rule."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {
                    "condition": {"tool_name": "test"},
                    "action": "alllow",
                    "reason": "typo in action",
                }
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("alllow" in e for e in errors)
        assert any("allow" in e for e in errors)  # suggestion

    def test_missing_required_field_in_rule(self):
        """Test rule missing required 'condition' field."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {"action": "allow", "reason": "no condition"}
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("condition" in e for e in errors)

    def test_unknown_rule_field(self):
        """Test rule with unknown field."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {
                    "condition": {"tool_name": "test"},
                    "action": "allow",
                    "reason": "test",
                    "priority": 1,
                }
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("priority" in e for e in errors)

    def test_empty_rules_list(self):
        """Test empty rules list."""
        policy = {"name": "test", "description": "desc", "rules": []}
        errors = _validate_policy(policy, "policy.json")
        assert any("empty" in e.lower() for e in errors)

    def test_rules_not_a_list(self):
        """Test rules field is not a list."""
        policy = {"name": "test", "description": "desc", "rules": "not a list"}
        errors = _validate_policy(policy, "policy.json")
        assert any("list" in e.lower() for e in errors)

    def test_policy_not_a_dict(self):
        """Test policy that is not a dict."""
        errors = _validate_policy("just a string", "policy.json")
        assert any("must be" in e for e in errors)

    def test_rule_not_a_dict(self):
        """Test a rule that is not a dict."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": ["not a dict"],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("Rule 1" in e for e in errors)

    def test_valid_actions_set(self):
        """Test that VALID_ACTIONS contains expected values."""
        assert VALID_ACTIONS == {"allow", "deny", "transform"}

    def test_missing_action_in_rule(self):
        """Test rule missing 'action' field."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {"condition": {"tool_name": "test"}, "reason": "no action"}
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("action" in e for e in errors)

    def test_missing_reason_in_rule(self):
        """Test rule missing 'reason' field."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {"condition": {"tool_name": "test"}, "action": "allow"}
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("reason" in e for e in errors)

    def test_condition_not_dict(self):
        """Test rule with condition that is not a dict."""
        policy = {
            "name": "test",
            "description": "desc",
            "rules": [
                {"condition": "not a dict", "action": "allow", "reason": "test"}
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert any("condition" in e for e in errors)

    def test_multiple_errors(self):
        """Test that multiple errors are reported."""
        policy = {
            "name": "",
            "rules": [
                {"action": "invalid", "reason": ""},
            ],
        }
        errors = _validate_policy(policy, "policy.json")
        assert len(errors) >= 3  # missing description, empty name, invalid action, missing condition, missing reason
