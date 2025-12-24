"""Tests for command execution utilities."""

import pytest
from pathlib import Path
from temper_workflow.utils import CommandRunner, CommandResult, BDCommand


class TestCommandResult:
    """Test CommandResult dataclass."""

    def test_success_output(self):
        """Test success property returns stdout when success=True."""
        result = CommandResult(
            success=True, stdout="success output", stderr="", exit_code=0, duration=0.1
        )
        assert result.output == "success output"

    def test_failure_output(self):
        """Test success property returns stderr first when success=False."""
        result = CommandResult(
            success=False, stdout="output", stderr="error message", exit_code=1, duration=0.1
        )
        assert result.output == "error message\noutput"


class TestCommandRunner:
    """Test CommandRunner class."""

    def test_find_project_root(self):
        """Test _find_project_root finds .git directory."""
        root = CommandRunner._find_project_root()
        assert isinstance(root, Path)
        assert (root / ".git").exists()

    def test_run_simple_command(self):
        """Test running a simple command."""
        runner = CommandRunner(timeout=5)
        result = runner.run(["echo", "hello"])
        assert result.success
        assert result.stdout == "hello"
        assert result.exit_code == 0
        assert result.duration > 0

    def test_run_failed_command(self):
        """Test running a command that fails."""
        runner = CommandRunner(timeout=5)
        result = runner.run(["ls", "/nonexistent"])
        assert not result.success
        assert result.exit_code != 0
        assert len(result.stderr) > 0

    def test_run_with_string_command(self):
        """Test running a string command."""
        runner = CommandRunner(timeout=5)
        result = runner.run("echo 'test'")
        assert result.success
        assert result.stdout == "test"

    def test_run_with_shell_true(self):
        """Test running shell command with shell=True."""
        runner = CommandRunner(timeout=5)
        result = runner.run("echo shell-test", shell=True)
        assert result.success
        assert result.stdout == "shell-test"

    def test_timeout_handling(self):
        """Test command timeout."""
        runner = CommandRunner(timeout=1)
        result = runner.run(["sleep", "5"])
        assert not result.success
        assert "timed out" in result.stderr.lower()
        assert result.exit_code == -1

    def test_custom_cwd(self, tmp_path: Path):
        """Test running command with custom working directory."""
        runner = CommandRunner(timeout=5)
        result = runner.run(["pwd"], cwd=tmp_path)
        assert result.success
        assert str(tmp_path) in result.stdout


class TestBDCommand:
    """Test BDCommand convenience methods."""

    def test_list_issues(self):
        """Test listing bd issues."""
        result = BDCommand.list_issues()
        assert result.success
        assert result.exit_code == 0

    def test_list_issues_with_status(self):
        """Test listing bd issues with status filter."""
        result = BDCommand.list_issues(status="open")
        assert result.success

    def test_run_with_args(self):
        """Test running bd command with custom args."""
        result = BDCommand.run(["info", "--json"], timeout=10)
        assert result.success or "command not found" in result.stderr
