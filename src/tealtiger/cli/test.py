"""CLI interface for policy testing.

TealTiger SDK v1.1.x - Enterprise Adoption Features
P0.5: Policy Test Harness

Command-line interface for running policy tests:
- Run tests from files
- Filter by tags
- Watch mode for continuous testing
- Export reports (JSON, JUnit XML)
- Coverage reporting
"""

import sys
import time
from pathlib import Path
from typing import List, Optional

import click

from ..core.engine.testing import PolicyTester, PolicyTestSuite
from ..core.engine.teal_engine import TealEngine


@click.command()
@click.argument('test_files', nargs=-1, type=click.Path(exists=True))
@click.option(
    '--tags',
    '-t',
    help='Filter tests by tags (comma-separated)',
    type=str,
)
@click.option(
    '--watch',
    '-w',
    is_flag=True,
    help='Watch mode for continuous testing',
)
@click.option(
    '--coverage',
    '-c',
    is_flag=True,
    help='Show coverage report',
)
@click.option(
    '--format',
    '-f',
    type=click.Choice(['json', 'junit'], case_sensitive=False),
    default='json',
    help='Output format (json or junit)',
)
@click.option(
    '--output',
    '-o',
    type=click.Path(),
    help='Output file path (default: stdout)',
)
@click.option(
    '--verbose',
    '-v',
    is_flag=True,
    help='Verbose output',
)
def test(
    test_files: tuple,
    tags: Optional[str],
    watch: bool,
    coverage: bool,
    format: str,
    output: Optional[str],
    verbose: bool,
) -> None:
    """Run TealTiger policy tests.
    
    Examples:
    
        # Run tests from a file
        tealtiger test ./policies/customer-support.test.json
        
        # Run tests with tag filtering
        tealtiger test ./policies/*.test.json --tags=pii,injection
        
        # Generate coverage report
        tealtiger test ./policies/*.test.json --coverage
        
        # Export to JUnit XML
        tealtiger test ./policies/*.test.json --format=junit --output=results.xml
        
        # Watch mode for development
        tealtiger test ./policies/*.test.json --watch
    """
    if not test_files:
        click.echo("Error: No test files specified", err=True)
        click.echo("Usage: tealtiger test <test_files>", err=True)
        sys.exit(1)

    # Parse tags
    tag_filter = None
    if tags:
        tag_filter = [t.strip() for t in tags.split(',')]

    # Run tests
    if watch:
        _run_watch_mode(test_files, tag_filter, coverage, verbose)
    else:
        exit_code = _run_tests(test_files, tag_filter, coverage, format, output, verbose)
        sys.exit(exit_code)


def _run_tests(
    test_files: tuple,
    tag_filter: Optional[List[str]],
    show_coverage: bool,
    output_format: str,
    output_file: Optional[str],
    verbose: bool,
) -> int:
    """Run tests once and return exit code."""
    total_passed = 0
    total_failed = 0
    all_reports = []

    for test_file in test_files:
        try:
            # Load test suite
            import json
            with open(test_file, 'r', encoding='utf-8') as f:
                suite_data = json.load(f)

            suite = PolicyTestSuite(**suite_data)

            # Filter tests by tags
            if tag_filter:
                filtered_tests = [
                    test for test in suite.tests
                    if any(tag in test.tags for tag in tag_filter)
                ]
                suite.tests = filtered_tests

            if not suite.tests:
                if verbose:
                    click.echo(f"No tests to run in {test_file}")
                continue

            # Create engine and tester
            engine = TealEngine(policies=suite.policy, mode=suite.mode)
            tester = PolicyTester(engine)

            # Run tests
            if verbose:
                click.echo(f"\nRunning tests from {test_file}...")

            report = tester.run_suite(suite)
            all_reports.append(report)

            total_passed += report.passed
            total_failed += report.failed

            # Display results
            _display_results(report, verbose)

        except Exception as e:
            click.echo(f"Error running tests from {test_file}: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            return 1

    # Display summary
    click.echo("\n" + "=" * 60)
    click.echo(f"Total: {total_passed + total_failed} tests")
    click.echo(f"Passed: {total_passed} ({_percentage(total_passed, total_passed + total_failed)})")
    click.echo(f"Failed: {total_failed} ({_percentage(total_failed, total_passed + total_failed)})")

    # Display coverage
    if show_coverage and all_reports:
        _display_coverage(all_reports[-1])

    # Export report
    if output_file and all_reports:
        _export_report(all_reports[-1], output_format, output_file)

    # Return exit code
    return 0 if total_failed == 0 else 1


def _run_watch_mode(
    test_files: tuple,
    tag_filter: Optional[List[str]],
    show_coverage: bool,
    verbose: bool,
) -> None:
    """Run tests in watch mode."""
    click.echo("Watch mode enabled. Press Ctrl+C to exit.")
    click.echo("Watching for changes...\n")

    last_modified = {}
    for test_file in test_files:
        last_modified[test_file] = Path(test_file).stat().st_mtime

    try:
        while True:
            # Check for file changes
            changed = False
            for test_file in test_files:
                current_mtime = Path(test_file).stat().st_mtime
                if current_mtime > last_modified[test_file]:
                    changed = True
                    last_modified[test_file] = current_mtime

            if changed:
                click.clear()
                click.echo(f"[{time.strftime('%H:%M:%S')}] Running tests...\n")
                _run_tests(test_files, tag_filter, show_coverage, 'json', None, verbose)
                click.echo("\nWatching for changes...")

            time.sleep(1)

    except KeyboardInterrupt:
        click.echo("\nWatch mode stopped.")


def _display_results(report, verbose: bool) -> None:
    """Display test results."""
    if verbose:
        click.echo(f"\nTest Suite: {report.suite_name}")
        click.echo(f"Timestamp: {report.timestamp}")
        click.echo(f"Duration: {report.total_time:.2f}ms\n")

        for result in report.results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            color = 'green' if result.passed else 'red'
            click.echo(
                click.style(f"{status}", fg=color) +
                f" {result.name} ({result.execution_time:.2f}ms)"
            )

            if not result.passed and result.failure_reason:
                click.echo(f"  Reason: {result.failure_reason}")

        click.echo()

    # Summary
    success_rate = report.success_rate * 100
    color = 'green' if report.failed == 0 else 'red'

    click.echo(
        f"Tests: {report.passed}/{report.total} passed " +
        click.style(f"({success_rate:.1f}%)", fg=color)
    )


def _display_coverage(report) -> None:
    """Display coverage information."""
    if not report.coverage:
        return

    coverage = report.coverage
    click.echo("\n" + "=" * 60)
    click.echo("Coverage Report")
    click.echo("=" * 60)
    click.echo(f"Total Policies: {coverage.total_policies}")
    click.echo(f"Tested Policies: {coverage.tested_policies}")
    click.echo(f"Coverage: {coverage.coverage_percentage:.1f}%")

    if coverage.untested_policies:
        click.echo("\nUntested Policies:")
        for policy in coverage.untested_policies:
            click.echo(f"  - {policy}")


def _export_report(report, format: str, output_file: str) -> None:
    """Export report to file."""
    from ..core.engine.testing import PolicyTester

    # Create a temporary tester to use export functionality
    # (we don't need the engine for export)
    class DummyEngine:
        def get_policies(self):
            return {}

    tester = PolicyTester(DummyEngine())
    content = tester.export_report(report, format)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

    click.echo(f"\nReport exported to {output_file}")


def _percentage(value: int, total: int) -> str:
    """Calculate percentage string."""
    if total == 0:
        return "0.0%"
    return f"{(value / total * 100):.1f}%"


if __name__ == '__main__':
    test()
