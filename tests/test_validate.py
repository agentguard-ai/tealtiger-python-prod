"""Tests for the policy validation CLI subcommand."""

import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from tealtiger.cli.__main__ import cli
from tealtiger.cli.validate import PolicyValidator


class TestPolicyValidator:
    """Tests for the PolicyValidator class."""

    def test_valid_policy(self):
        """Test validation of a complete valid policy."""
        policy = {
            "id": "test-policy",
            "name": "Test Policy",
            "description": "A test policy",
            "rules": [
                {"condition": {"tool_name": "file-write"}, "action": "deny", "reason": "No file writes"},
                {"condition": {"model": "gpt-4"}, "action": "allow", "reason": "GPT-4 approved"},
            ],
        }
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is True
        assert len(validator.errors) == 0

    def test_missing_required_fields(self):
        """Test that missing required fields are caught."""
        policy = {"id": "test"}
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        field_errors = [e for e in validator.errors if "Missing required field" in e.message]
        assert len(field_errors) == 3  # name, description, rules

    def test_invalid_action(self):
        """Test that invalid actions are detected."""
        policy = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "rules": [{"condition": {"x": 1}, "action": "alllow", "reason": "typo"}],
        }
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        action_errors = [e for e in validator.errors if "unknown action" in e.message]
        assert len(action_errors) == 1

    def test_empty_reason(self):
        """Test that empty reason strings are caught."""
        policy = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "rules": [{"condition": {"x": 1}, "action": "allow", "reason": ""}],
        }
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        reason_errors = [e for e in validator.errors if "reason" in e.message.lower() and "empty" in e.message.lower()]
        assert len(reason_errors) == 1

    def test_valid_actions(self):
        """Test all valid actions are accepted."""
        for action in ("allow", "deny", "transform", "redact", "require_approval", "degrade"):
            policy = {
                "id": "test",
                "name": "Test",
                "description": "Test",
                "rules": [{"condition": {"x": 1}, "action": action, "reason": "ok"}],
            }
            validator = PolicyValidator()
            assert validator.validate(policy, "test.json") is True, f"Action '{action}' should be valid"

    def test_missing_rule_fields(self):
        """Test missing fields within a rule."""
        policy = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "rules": [{"condition": {"x": 1}}],  # missing action and reason
        }
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        missing = [e for e in validator.errors if "missing required field" in e.message.lower()]
        assert len(missing) == 2  # action and reason

    def test_enabled_field_validation(self):
        """Test that enabled field must be boolean."""
        policy = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "rules": [],
            "enabled": "yes",
        }
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        bool_errors = [e for e in validator.errors if "enabled" in e.message and "boolean" in e.message.lower()]
        assert len(bool_errors) == 1

    def test_empty_rules_list(self):
        """Test that empty rules list is rejected."""
        policy = {"id": "test", "name": "Test", "description": "Test", "rules": []}
        validator = PolicyValidator()
        assert validator.validate(policy, "test.json") is False
        empty_errors = [e for e in validator.errors if "rules" in e.message.lower() and "empty" in e.message.lower()]
        assert len(empty_errors) == 1

    def test_non_dict_policy(self):
        """Test that non-dict policy data is rejected."""
        validator = PolicyValidator()
        assert validator.validate(["not", "a", "dict"], "test.json") is False
        assert len(validator.errors) == 1


class TestValidateCLI:
    """Tests for the CLI validate command."""

    def setup_method(self):
        self.runner = CliRunner()

    def _write_policy(self, data: dict, suffix: str = ".json") -> Path:
        """Write a policy file and return its path."""
        fd, path = tempfile.mkstemp(suffix=suffix)
        with open(path, "w") as f:
            if suffix == ".json":
                json.dump(data, f)
            else:
                import yaml
                yaml.dump(data, f)
        return Path(path)

    def test_valid_policy_cli(self):
        """Test CLI with a valid policy file."""
        policy = {
            "id": "test",
            "name": "Test Policy",
            "description": "A test",
            "rules": [{"condition": {"x": 1}, "action": "allow", "reason": "ok"}],
        }
        path = self._write_policy(policy)
        try:
            result = self.runner.invoke(cli, ["validate", str(path)])
            assert result.exit_code == 0
            assert "valid" in result.output.lower()
        finally:
            path.unlink()

    def test_invalid_policy_cli(self):
        """Test CLI with an invalid policy file."""
        policy = {"id": "test", "name": "Test", "rules": []}
        path = self._write_policy(policy)
        try:
            result = self.runner.invoke(cli, ["validate", str(path)])
            assert result.exit_code == 1
            assert "error" in result.output.lower()
        finally:
            path.unlink()

    def test_json_output_format(self):
        """Test JSON output format."""
        policy = {"id": "test", "name": "Test", "rules": []}
        path = self._write_policy(policy)
        try:
            result = self.runner.invoke(cli, ["validate", str(path), "--format", "json"])
            assert result.exit_code == 1
            output = json.loads(result.output)
            assert output["valid"] is False
            assert output["error_count"] > 0
        finally:
            path.unlink()

    def test_yaml_policy(self):
        """Test validation of a YAML policy file."""
        import yaml
        policy = {
            "id": "yaml-test",
            "name": "YAML Test",
            "description": "A YAML policy",
            "rules": [
                {"condition": {"model": "gpt-4"}, "action": "allow", "reason": "Approved"}
            ],
        }
        path = self._write_policy(policy, suffix=".yaml")
        try:
            result = self.runner.invoke(cli, ["validate", str(path)])
            assert result.exit_code == 0
            assert "valid" in result.output.lower()
        finally:
            path.unlink()

    def test_nonexistent_file(self):
        """Test that nonexistent files produce an error."""
        result = self.runner.invoke(cli, ["validate", "/tmp/nonexistent-policy-xyz.json"])
        # Click's click.Path(exists=True) returns exit code 2 for missing files
        assert result.exit_code in (1, 2)
        assert "not found" in result.output.lower() or "does not exist" in result.output.lower()

    def test_invalid_json_format(self):
        """Test that malformed JSON is caught."""
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with open(path, "w") as f:
                f.write("{invalid json content!!!}")
            result = self.runner.invoke(cli, ["validate", path])
            assert result.exit_code == 1
            assert "invalid" in result.output.lower() or "error" in result.output.lower()
        finally:
            Path(path).unlink()
