#!/usr/bin/env python3
"""
Measurement system for GPBM workflow.

Runs measurements defined in bd issue descriptions and logs results
to metrics/measurements.jsonl.

Usage:
    # As library
    from gpbm.measure import MeasurementRunner
    runner = MeasurementRunner()
    results = runner.run_for_task("temper-xxx")

    # As CLI
    python measure.py --task temper-xxx
    python measure.py --task temper-xxx --json
    python measure.py --metric fw_test_coverage
"""

import json
import os
import re

import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

try:
    from ..utils import CommandRunner, BDCommand
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "packages" / "temper-workflow" / "src"))
    from temper_workflow.utils import CommandRunner, BDCommand



@dataclass
class MeasurementTarget:
    """A measurement target from an issue description."""

    metric: str
    target: str  # e.g., ">=80", "==0", "<1.0"

    def evaluate(self, value: float) -> bool:
        """Evaluate if value meets target."""
        # Parse target expression
        match = re.match(r"([<>=!]+)\s*(\d+\.?\d*)", self.target)
        if not match:
            return False

        op, threshold = match.groups()
        threshold = float(threshold)

        ops = {
            ">=": lambda v, t: v >= t,
            "<=": lambda v, t: v <= t,
            ">": lambda v, t: v > t,
            "<": lambda v, t: v < t,
            "==": lambda v, t: abs(v - t) < 0.001,
            "!=": lambda v, t: abs(v - t) >= 0.001,
        }

        return ops.get(op, lambda v, t: False)(value, threshold)


@dataclass
class MeasurementResult:
    """Result of a single measurement."""

    metric: str
    value: float
    target: str
    passed: bool
    timestamp: str
    task: str
    commit: str = ""
    details: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON."""
        return {
            "timestamp": self.timestamp,
            "metric": self.metric,
            "value": self.value,
            "target": self.target,
            "pass": self.passed,
            "task": self.task,
            "commit": self.commit,
            "details": self.details,
            "error": self.error,
        }

    def to_jsonl(self) -> str:
        """Convert to JSONL line."""
        d = self.to_dict()
        # Remove empty fields
        d = {k: v for k, v in d.items() if v}
        return json.dumps(d)


@dataclass
class MetricDefinition:
    """Definition of a metric from METRICS.md."""

    id: str
    description: str
    target: str
    source: str
    command: str


class MetricsRegistry:
    """Registry of metric definitions from METRICS.md."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or CommandRunner._find_project_root()
        self.metrics: dict[str, MetricDefinition] = {}
        self._load_metrics()


    def _load_metrics(self):
        """Load metrics from METRICS.md."""
        metrics_file = self.project_root / "metrics" / "METRICS.md"
        if not metrics_file.exists():
            return

        content = metrics_file.read_text()

        # Parse table rows: | `metric_id` | description | target | source | command |
        # We need to handle commands that contain shell pipes (|)
        # Strategy: Parse line by line, split on | but respect backtick-wrapped content

        for line in content.split("\n"):
            line = line.strip()

            # Skip non-table lines and header separators
            if not line.startswith("|") or "---" in line:
                continue

            # Check if this line has a metric ID (backtick-wrapped identifier)
            if not re.search(r"\|\s*`[\w_]+`\s*\|", line):
                continue

            # Parse the line respecting backtick-wrapped content
            metric = self._parse_metric_line(line)
            if metric:
                self.metrics[metric.id] = metric

    def _parse_metric_line(self, line: str) -> Optional["MetricDefinition"]:
        """Parse a single metric table line, handling backtick-wrapped commands with pipes.

        Format: | `metric_id` | description | target | source | `command with | pipes` |
        """
        # Remove leading/trailing pipes and split carefully
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]

        # Split on | but not inside backticks
        # Use a state machine approach
        parts = []
        current = []
        in_backticks = False

        for char in line:
            if char == "`":
                in_backticks = not in_backticks
                current.append(char)
            elif char == "|" and not in_backticks:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)

        # Don't forget the last part
        if current:
            parts.append("".join(current).strip())

        # We expect 5 parts: metric_id, description, target, source, command
        if len(parts) < 5:
            return None

        metric_id = parts[0].strip("` ")
        desc = parts[1].strip()
        target = parts[2].strip()
        source = parts[3].strip()
        command = parts[4].strip("` ")  # Remove backticks from command

        # Validate metric_id is a valid identifier
        if not re.match(r"^[\w_]+$", metric_id):
            return None

        return MetricDefinition(
            id=metric_id,
            description=desc,
            target=target,
            source=source,
            # Unescape pipe characters that were escaped for markdown tables
            command=command.replace("\\|", "|"),
        )

    def get(self, metric_id: str) -> MetricDefinition | None:
        """Get metric definition by ID."""
        return self.metrics.get(metric_id)

    def list_all(self) -> list[str]:
        """List all metric IDs."""
        return list(self.metrics.keys())


class MeasurementRunner:
    """Run measurements for tasks."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or CommandRunner._find_project_root()
        self.registry = MetricsRegistry(self.project_root)
        self.cmd_runner = CommandRunner(cwd=self.project_root)
        self.results: list[MeasurementResult] = []


    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        result = self.cmd_runner.run(["git", "rev-parse", "--short", "HEAD"], timeout=5)
        return result.stdout if result.success else ""

    def _get_task_description(self, task_id: str) -> str:
        """Get task description from bd."""
        result = BDCommand.show(task_id, cwd=self.project_root, timeout=10)
        if result.success:
            try:
                data = json.loads(result.stdout)
                if isinstance(data, list) and data:
                    return data[0].get("description", "")
            except Exception:
                pass
        return ""

    def _parse_measurement_targets(self, description: str) -> list[MeasurementTarget]:
        """Parse measurement_targets from task description."""
        targets = []

        # Look for YAML-like measurement_targets block
        # measurement_targets:
        #   - metric: fw_test_coverage
        #     target: ">=80"
        pattern = re.compile(
            r"measurement_targets:\s*\n((?:\s*-\s*metric:\s*\w+\s*\n\s*target:\s*[^\n]+\s*\n?)+)",
            re.MULTILINE,
        )

        match = pattern.search(description)
        if match:
            block = match.group(1)
            # Parse individual targets
            target_pattern = re.compile(
                r'-\s*metric:\s*(\w+)\s*\n\s*target:\s*["\']?([^"\'\n]+)["\']?',
                re.MULTILINE,
            )
            for m in target_pattern.finditer(block):
                targets.append(
                    MeasurementTarget(metric=m.group(1).strip(), target=m.group(2).strip())
                )

        return targets

    def _run_command(self, command: str, timeout: int = 60) -> tuple[bool, str, str]:
        """Run a shell command and return (success, stdout, stderr)."""
        result = self.cmd_runner.run(command, shell=True, timeout=timeout)
        return (result.success, result.stdout, result.stderr)

    def _extract_numeric_value(self, output: str, metric_id: str) -> float | None:
        """Extract numeric value from command output."""
        # Try to find a number in the output
        # Different metrics may need different extraction logic

        # For test counts, look for patterns like "37 tests" or "Tests: 37"
        if "test" in metric_id.lower():
            match = re.search(r"(\d+)\s*(?:tests?|passed)", output, re.IGNORECASE)
            if match:
                return float(match.group(1))
            # Also try just counting test lines
            match = re.search(r"Test #(\d+)", output)
            if match:
                # Count all Test # occurrences
                return float(len(re.findall(r"Test #\d+", output)))

        # For coverage, look for percentage
        if "coverage" in metric_id.lower() or "pct" in metric_id.lower():
            match = re.search(r"(\d+\.?\d*)%", output)
            if match:
                return float(match.group(1))

        # For counts (violations, errors), look for 0 or numbers
        if "violation" in metric_id.lower() or "error" in metric_id.lower():
            match = re.search(r"(\d+)\s*(?:violation|error|warning)", output, re.IGNORECASE)
            if match:
                return float(match.group(1))
            # If output is empty or says "0", return 0
            if not output.strip() or output.strip() == "0":
                return 0.0

        # For loss values
        if "loss" in metric_id.lower():
            match = re.search(r"(?:loss|value)[:\s]*(\d+\.?\d*)", output, re.IGNORECASE)
            if match:
                return float(match.group(1))

        # Generic: try to find any float
        match = re.search(r"(\d+\.?\d*)", output)
        if match:
            return float(match.group(1))

        return None

    def run_metric(
        self, metric_id: str, task_id: str, target: str | None = None
    ) -> MeasurementResult:
        """Run a single metric measurement."""
        timestamp = datetime.now(UTC).isoformat()
        commit = self._get_git_commit()

        # Get metric definition
        metric_def = self.registry.get(metric_id)
        if not metric_def:
            return MeasurementResult(
                metric=metric_id,
                value=0,
                target=target or "unknown",
                passed=False,
                timestamp=timestamp,
                task=task_id,
                commit=commit,
                error=f"Unknown metric: {metric_id}",
            )

        target = target or metric_def.target
        command = metric_def.command

        # Run the command
        success, stdout, stderr = self._run_command(command)

        # Some commands return non-zero but still have valid output
        # (e.g., linters return 1 when they find issues)
        # Only treat as hard failure if there's no stdout and there's stderr
        if not success and not stdout and stderr:
            return MeasurementResult(
                metric=metric_id,
                value=0,
                target=target,
                passed=False,
                timestamp=timestamp,
                task=task_id,
                commit=commit,
                error=stderr or "Command failed",
                details=stdout,
            )

        # Try to extract value from output (even if command returned non-zero)
        output = stdout or stderr  # Some tools output to stderr
        value = self._extract_numeric_value(output, metric_id)
        if value is None:
            return MeasurementResult(
                metric=metric_id,
                value=0,
                target=target,
                passed=False,
                timestamp=timestamp,
                task=task_id,
                commit=commit,
                error="Could not extract numeric value from output",
                details=stdout[:200],
            )

        # Evaluate against target
        mt = MeasurementTarget(metric=metric_id, target=target)
        passed = mt.evaluate(value)

        return MeasurementResult(
            metric=metric_id,
            value=value,
            target=target,
            passed=passed,
            timestamp=timestamp,
            task=task_id,
            commit=commit,
            details=stdout[:200] if not passed else "",
        )

    def run_metric_with_retry(
        self,
        metric_id: str,
        task_id: str,
        target: Optional[str] = None,
        max_retries: Optional[int] = None,
    ) -> MeasurementResult:
        """Run a metric measurement with retry on transient failures.

        Args:
            metric_id: Metric ID from registry
            task_id: Task ID for context
            target: Target expression (e.g., ">=80")
            max_retries: Max retry attempts (defaults to GPBM_MAX_RETRIES env var or 2)

        Returns:
            MeasurementResult with success/failure details
        """
        if max_retries is None:
            max_retries = int(os.environ.get("GPBM_MAX_RETRIES", "2"))

        # List of error patterns that indicate transient failures worth retrying
        transient_patterns = [
            "timeout",
            "timed out",
            "connection",
            "temporarily unavailable",
            "locked",
            "busy",
            "resource unavailable",
            "try again",
        ]

        result: MeasurementResult | None = None
        for attempt in range(max_retries + 1):
            result = self.run_metric(metric_id, task_id, target)

            # Success or result without error - return immediately
            if result.passed or not result.error:
                if attempt > 0:
                    print(
                        f"  ✓ {metric_id} succeeded on attempt {attempt + 1}",
                        file=sys.stderr,
                    )
                return result

            # Check if error is transient
            error_lower = result.error.lower()
            is_transient = any(pattern in error_lower for pattern in transient_patterns)

            # Don't retry if this is the last attempt or error is permanent
            if not is_transient or attempt >= max_retries:
                if not is_transient and attempt == 0:
                    print(
                        f"  ⊗ {metric_id} failed with permanent error (no retry)",
                        file=sys.stderr,
                    )
                return result

            # Exponential backoff: 1s, 2s, 4s
            wait = 2**attempt
            print(
                f"  ⟳ Retrying {metric_id} in {wait}s (attempt {attempt + 2}/{max_retries + 1})",
                file=sys.stderr,
            )
            time.sleep(wait)

        # Should never reach here, but satisfy type checker
        assert result is not None
        return result

    def run_for_task(self, task_id: str) -> list[MeasurementResult]:
        """Run all measurements defined in a task's description (with retry)."""
        description = self._get_task_description(task_id)
        targets = self._parse_measurement_targets(description)

        if not targets:
            return []

        results = []
        for target in targets:
            result = self.run_metric_with_retry(target.metric, task_id, target.target)
            results.append(result)

        self.results = results
        return results

    def log_results(self, results: list[MeasurementResult] | None = None):
        """Append results to measurements.jsonl."""
        results = results or self.results
        if not results:
            return

        log_file = self.project_root / "metrics" / "measurements.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(log_file, "a") as f:
            for result in results:
                f.write(result.to_jsonl() + "\n")

    def format_results(self, results: list[MeasurementResult] | None = None) -> str:
        """Format results for display."""
        results = results or self.results
        if not results:
            return "No measurements to report."

        lines = ["", "=" * 50, "MEASUREMENT RESULTS", "=" * 50, ""]

        all_passed = True
        for r in results:
            icon = "✓" if r.passed else "✗"
            if not r.passed:
                all_passed = False

            lines.append(f"{icon} {r.metric}")
            lines.append(f"  Value:  {r.value}")
            lines.append(f"  Target: {r.target}")
            if r.error:
                lines.append(f"  Error:  {r.error}")
            lines.append("")

        lines.append("=" * 50)
        summary = "ALL PASSED" if all_passed else "SOME FAILED"
        lines.append(f"Summary: {summary}")
        lines.append("=" * 50)

        return "\n".join(lines)


def main():
    """CLI interface for measurement runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run measurements for GPBM workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run measurements for a task
  python measure.py --task temper-xxx

  # Run a specific metric
  python measure.py --metric fw_test_coverage --task temper-xxx

  # Output as JSON
  python measure.py --task temper-xxx --json

  # List available metrics
  python measure.py --list-metrics
""",
    )

    parser.add_argument("--task", type=str, help="bd task ID to run measurements for")
    parser.add_argument("--metric", type=str, help="Specific metric to run")
    parser.add_argument("--target", type=str, help="Target value (e.g., '>=80')")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--no-log", action="store_true", help="Don't log results to measurements.jsonl"
    )
    parser.add_argument("--list-metrics", action="store_true", help="List available metrics")
    parser.add_argument("--root", type=str, help="Project root directory")

    args = parser.parse_args()

    root = Path(args.root) if args.root else None
    runner = MeasurementRunner(project_root=root)

    if args.list_metrics:
        print("Available metrics:\n")
        for metric_id in sorted(runner.registry.list_all()):
            metric = runner.registry.get(metric_id)
            if metric:
                print(f"  {metric_id}")
                print(f"    {metric.description}")
                print(f"    Target: {metric.target}")
                print()
        return

    if not args.task:
        parser.error("--task is required (or use --list-metrics)")

    if args.metric:
        # Run single metric
        result = runner.run_metric(args.metric, args.task, args.target)
        results = [result]
    else:
        # Run all measurements for task
        results = runner.run_for_task(args.task)

    if not results:
        print(f"No measurement targets found for task {args.task}")
        print("Add measurement_targets to the task description:")
        print("""
measurement_targets:
  - metric: fw_test_coverage
    target: ">=80"
""")
        sys.exit(0)

    # Log results
    if not args.no_log:
        runner.log_results(results)

    # Output
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(runner.format_results(results))

    # Exit code based on pass/fail
    all_passed = all(r.passed for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
