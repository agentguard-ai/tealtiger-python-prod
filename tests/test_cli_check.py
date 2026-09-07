"""Tests for the tealtiger check CLI command."""

import json

from click.testing import CliRunner

from tealtiger.cli import cli


def test_check_pii_deny() -> None:
    """PII input should be denied."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            "--text",
            "My SSN is 123-45-6789",
            "--policy",
            "pii_block",
        ],
    )

    assert result.exit_code == 0

    output = json.loads(result.output)

    assert output["action"] == "DENY"
    assert "PII_DETECTED:ssn" in output["reason_codes"]
    assert output["evaluation_time_ms"] >= 0


def test_check_pii_allow() -> None:
    """Text without PII should be allowed."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            "--text",
            "Hello from TealTiger",
            "--policy",
            "pii_block",
        ],
    )

    assert result.exit_code == 0

    output = json.loads(result.output)

    assert output["action"] == "ALLOW"
    assert output["reason_codes"] == []


def test_check_tool_allowlist_allow() -> None:
    """An allowlisted tool should be allowed."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            "--tool",
            "search",
            "--allowlist",
            "search,read_file",
        ],
    )

    assert result.exit_code == 0

    output = json.loads(result.output)

    assert output["action"] == "ALLOW"
    assert output["reason_codes"] == []


def test_check_tool_allowlist_deny() -> None:
    """A tool outside the allowlist should be denied."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            "--tool",
            "delete_database",
            "--allowlist",
            "search,read_file",
        ],
    )

    assert result.exit_code == 0

    output = json.loads(result.output)

    assert output["action"] == "DENY"
    assert output["reason_codes"] == ["TOOL_NOT_ALLOWED"]


def test_check_requires_complete_text_policy_pair() -> None:
    """Text evaluation requires both text and policy."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["check", "--text", "hello"],
    )

    assert result.exit_code != 0
    assert "--text and --policy must be provided together" in result.output


def test_check_help() -> None:
    """Check command should expose CLI help."""
    runner = CliRunner()

    result = runner.invoke(cli, ["check", "--help"])

    assert result.exit_code == 0
    assert "--text" in result.output
    assert "--policy" in result.output
    assert "--tool" in result.output
    assert "--allowlist" in result.output


def test_check_requires_complete_tool_allowlist_pair() -> None:
    """Tool evaluation requires both tool and allowlist."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["check", "--tool", "search"],
    )

    assert result.exit_code != 0
    assert "--tool and --allowlist must be provided together" in result.output


def test_check_rejects_unsupported_policy() -> None:
    """Unknown policy names should be rejected."""
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "check",
            "--text",
            "hello",
            "--policy",
            "unknown_policy",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported policy: unknown_policy" in result.output
