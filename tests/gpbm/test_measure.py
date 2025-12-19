#!/usr/bin/env python3
"""
Unit tests for GPBM measurement system.

Tests the MetricsRegistry parser to ensure:
1. Commands with shell pipes (|) are correctly parsed
2. Escaped pipes (\\|) in markdown tables are unescaped
3. Backtick-wrapped commands have backticks removed
4. Edge cases are handled correctly
"""

import sys
from pathlib import Path
import tempfile
import pytest

# Add tools/gpbm to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools" / "gpbm"))

from measure import MetricsRegistry, MetricDefinition


class TestMetricsParsing:
    """Test cases for METRICS.md parsing."""

    def test_simple_command_without_pipes(self, tmp_path):
        """Test parsing of simple commands without pipes."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `test_count` | Number of tests | >=10 | pytest | `pytest --collect-only` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("test_count")

        assert metric is not None
        assert metric.id == "test_count"
        assert metric.command == "pytest --collect-only"
        assert metric.description == "Number of tests"
        assert metric.target == ">=10"

    def test_command_with_single_pipe(self, tmp_path):
        """Test parsing of commands with a single shell pipe."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `test_count` | Number of tests | >=10 | pytest | `pytest --collect-only \\| wc -l` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("test_count")

        assert metric is not None
        assert metric.command == "pytest --collect-only | wc -l"
        # Verify the pipe was unescaped
        assert "\\|" not in metric.command
        assert "|" in metric.command

    def test_command_with_multiple_pipes(self, tmp_path):
        """Test parsing of commands with multiple shell pipes."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `fw_test_count` | Test count | >=37 | ctest | `ctest -N \| grep test \| wc -l` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("fw_test_count")

        assert metric is not None
        assert metric.command == "ctest -N | grep test | wc -l"
        assert metric.command.count("|") == 2

    def test_command_with_pipes_and_quotes(self, tmp_path):
        """Test parsing of commands with pipes and quoted strings."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `grep_count` | Match count | >=5 | grep | `grep -c 'test_state' file.txt \| awk '{print $1}'` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("grep_count")

        assert metric is not None
        assert metric.command == "grep -c 'test_state' file.txt | awk '{print $1}'"
        assert "'" in metric.command  # Quotes preserved
        assert "|" in metric.command  # Pipe unescaped

    def test_command_with_complex_shell_syntax(self, tmp_path):
        """Test parsing of commands with complex shell syntax."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `token_count` | Token estimate | <=1500 | gather | `python3 tools/gpbm/gather.py --goal "$GOAL" \| wc -c \| awk '{print int($1/4)}'` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("token_count")

        assert metric is not None
        assert (
            metric.command
            == """python3 tools/gpbm/gather.py --goal "$GOAL" | wc -c | awk '{print int($1/4)}'"""
        )
        assert '"$GOAL"' in metric.command  # Variables preserved
        assert metric.command.count("|") == 2

    def test_backticks_removed_from_command(self, tmp_path):
        """Test that backticks are removed from commands."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `test_metric` | Test description | >=0 | source | `echo "hello" \| cat` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("test_metric")

        assert metric is not None
        # Backticks should be stripped
        assert not metric.command.startswith("`")
        assert not metric.command.endswith("`")
        # But pipe should be unescaped
        assert metric.command == 'echo "hello" | cat'

    def test_backticks_removed_from_metric_id(self, tmp_path):
        """Test that backticks are removed from metric IDs."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `test_metric` | Test description | >=0 | source | `echo hello` |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("test_metric")

        assert metric is not None
        assert metric.id == "test_metric"
        assert "`" not in metric.id

    def test_multiple_metrics_parsed(self, tmp_path):
        """Test that multiple metrics are all parsed correctly."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `metric1` | First metric | >=10 | source1 | `cmd1 \| grep foo` |
| `metric2` | Second metric | <=5 | source2 | `cmd2 arg` |
| `metric3` | Third metric | ==0 | source3 | `cmd3 \| awk '{print $1}' \| sort` |
""")

        registry = MetricsRegistry(tmp_path)

        assert len(registry.list_all()) == 3
        assert set(registry.list_all()) == {"metric1", "metric2", "metric3"}

        # Verify each metric
        m1 = registry.get("metric1")
        assert m1.command == "cmd1 | grep foo"

        m2 = registry.get("metric2")
        assert m2.command == "cmd2 arg"
        assert "|" not in m2.command

        m3 = registry.get("metric3")
        assert m3.command == "cmd3 | awk '{print $1}' | sort"
        assert m3.command.count("|") == 2

    def test_skip_non_metric_rows(self, tmp_path):
        """Test that non-metric rows are skipped."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
# Test Metrics

Some introductory text.

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `valid_metric` | Valid metric | >=0 | source | `echo test` |

Some more text in between.

| Random table | Without metric format |
|--------------|---------------------|
| Not a metric | Should be skipped |
""")

        registry = MetricsRegistry(tmp_path)

        assert len(registry.list_all()) == 1
        assert "valid_metric" in registry.list_all()

    def test_empty_or_missing_file(self, tmp_path):
        """Test graceful handling of missing METRICS.md."""
        registry = MetricsRegistry(tmp_path)

        assert len(registry.list_all()) == 0

    def test_real_firmware_metrics_format(self, tmp_path):
        """Test parsing of real firmware metrics from the project."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
## Firmware Metrics

| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `fw_state_machine_tests` | State machine test count | >=37 | Unity | `ctest -N \| grep -c 'test_state'` |
| `fw_integration_tests` | Integration test count | >=30 | Unity | `ctest -N \| grep -c 'test_integration'` |
| `fw_build_size_kb` | Firmware binary size | <=512 | ESP-IDF | `ls -la build/*.bin \| awk '{print $5/1024}'` |
""")

        registry = MetricsRegistry(tmp_path)

        # All three metrics should be parsed
        assert len(registry.list_all()) == 3

        # Check fw_state_machine_tests
        m1 = registry.get("fw_state_machine_tests")
        assert m1 is not None
        assert m1.command == "ctest -N | grep -c 'test_state'"
        assert m1.target == ">=37"

        # Check fw_integration_tests
        m2 = registry.get("fw_integration_tests")
        assert m2 is not None
        assert m2.command == "ctest -N | grep -c 'test_integration'"

        # Check fw_build_size_kb
        m3 = registry.get("fw_build_size_kb")
        assert m3 is not None
        assert m3.command == "ls -la build/*.bin | awk '{print $5/1024}'"
        assert "\\|" not in m3.command


class TestEdgeCases:
    """Test edge cases in metric parsing."""

    def test_metric_with_no_backticks(self, tmp_path):
        """Test metric row without backticks (should still parse if format is clear)."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        # Note: Current implementation REQUIRES backticks for metric_id
        # This test documents that behavior
        metrics_file.write_text("""
| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| test_metric | No backticks | >=0 | source | echo hello |
""")

        registry = MetricsRegistry(tmp_path)

        # Should NOT parse without backticks (by design)
        assert "test_metric" not in registry.list_all()

    def test_metric_with_extra_whitespace(self, tmp_path):
        """Test metric with extra whitespace."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
|   `test_metric`   |   Description   |   >=10   |   source   |   `echo test \| wc`   |
""")

        registry = MetricsRegistry(tmp_path)
        metric = registry.get("test_metric")

        assert metric is not None
        # Whitespace should be stripped
        assert metric.id == "test_metric"
        assert metric.description == "Description"
        assert metric.command == "echo test | wc"

    def test_metric_with_invalid_id(self, tmp_path):
        """Test that metrics with invalid IDs are skipped."""
        metrics_file = tmp_path / "metrics" / "METRICS.md"
        metrics_file.parent.mkdir(parents=True)
        metrics_file.write_text("""
| Metric ID | Description | Target | Source | Command |
|-----------|-------------|--------|--------|---------|
| `invalid-id` | Has dashes | >=0 | source | `echo test` |
| `valid_id` | Valid | >=0 | source | `echo test` |
""")

        registry = MetricsRegistry(tmp_path)

        # Only valid_id should be parsed (invalid-id has dashes)
        assert "valid_id" in registry.list_all()
        assert "invalid-id" not in registry.list_all()


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
