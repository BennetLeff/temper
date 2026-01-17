"""Subprocess command execution utilities.

Provides consistent error handling, timeout configuration, and result parsing
for subprocess execution across GPBM workflow.
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CommandResult:
    """Result of a command execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration: float

    @property
    def output(self) -> str:
        """Combined stdout and stderr (stderr first if success=False)."""
        if self.success:
            return self.stdout
        return f"{self.stderr}\n{self.stdout}"


class CommandRunner:
    """Execute commands with consistent error handling."""

    def __init__(self, cwd: Path | None = None, timeout: int = 30):
        """Initialize command runner.

        Args:
            cwd: Working directory for commands (defaults to project root)
            timeout: Default timeout in seconds
        """
        self.cwd = cwd or self._find_project_root()
        self.timeout = timeout

    @staticmethod
    def _find_project_root() -> Path:
        """Find project root by looking for .git directory."""
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                return parent
        return cwd

    def run(
        self,
        cmd: str | list[str],
        timeout: int | None = None,
        cwd: Path | None = None,
        shell: bool = False,
        **kwargs: Any,
    ) -> CommandResult:
        """Execute command with consistent error handling.

        Args:
            cmd: Command to execute (string or list)
            timeout: Timeout in seconds (uses default if None)
            cwd: Working directory (uses instance default if None)
            shell: Use shell=True for string commands
            **kwargs: Additional arguments passed to subprocess.run

        Returns:
            CommandResult with success status and output
        """
        start = time.time()

        if isinstance(cmd, str) and not shell:
            cmd = ["sh", "-c", cmd]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd or self.cwd,
                timeout=timeout if timeout is not None else self.timeout,
                shell=shell,
                **kwargs,
            )
            return CommandResult(
                success=result.returncode == 0,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
                duration=time.time() - start,
            )
        except subprocess.TimeoutExpired as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout or self.timeout}s",
                exit_code=-1,
                duration=time.time() - start,
            )
        except Exception as e:
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration=time.time() - start,
            )


class BDCommand:
    """Convenience methods for running bd commands."""

    @staticmethod
    def run(
        args: list[str],
        cwd: Path | None = None,
        timeout: int = 30,
        sandbox: bool = True,
    ) -> CommandResult:
        """Run a bd command.

        Args:
            args: Arguments to pass to bd (e.g., ["list", "--status", "open"])
            cwd: Working directory
            timeout: Timeout in seconds
            sandbox: Use --sandbox flag

        Returns:
            CommandResult with success status and output
        """
        runner = CommandRunner(cwd=cwd, timeout=timeout)
        cmd = ["bd"]
        if sandbox:
            cmd.append("--sandbox")
        cmd.extend(args)
        return runner.run(cmd)

    @staticmethod
    def list_issues(
        status: str | None = None,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """List bd issues.

        Args:
            status: Filter by status (e.g., "open", "closed", "in_progress")
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with JSON output
        """
        args = ["list", "--json"]
        if status:
            args.extend(["--status", status])
        return BDCommand.run(args, cwd=cwd, timeout=timeout)

    @staticmethod
    def show(
        issue_id: str,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """Show bd issue details.

        Args:
            issue_id: Issue ID to show
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with JSON output
        """
        return BDCommand.run(["show", issue_id, "--json"], cwd=cwd, timeout=timeout)

    @staticmethod
    def create(
        title: str,
        description: str = "",
        issue_type: str = "task",
        priority: int = 2,
        labels: list[str] | None = None,
        parent: str | None = None,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """Create a bd issue.

        Args:
            title: Issue title
            description: Issue description
            issue_type: Type of issue (task, bug, feature, epic)
            priority: Priority (0-4)
            labels: Labels to add
            parent: Parent issue ID (for subtasks)
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with created issue ID
        """
        args = [
            "create",
            title,
            "--description",
            description,
            "-t",
            issue_type,
            "-p",
            str(priority),
            "--json",
        ]
        if labels:
            for label in labels:
                args.extend(["--label", label])
        if parent:
            args.extend(["--parent", parent])
        return BDCommand.run(args, cwd=cwd, timeout=timeout)

    @staticmethod
    def update(
        issue_id: str,
        status: str | None = None,
        priority: int | None = None,
        labels: list[str] | None = None,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """Update a bd issue.

        Args:
            issue_id: Issue ID to update
            status: New status
            priority: New priority
            labels: Labels to add/remove
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with updated issue details
        """
        args = ["update", issue_id]
        if status:
            args.extend(["--status", status])
        if priority is not None:
            args.extend(["--priority", str(priority)])
        if labels:
            for label in labels:
                args.extend(["--add-label", label])
        args.append("--json")
        return BDCommand.run(args, cwd=cwd, timeout=timeout)

    @staticmethod
    def close(
        issue_id: str,
        reason: str = "",
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """Close a bd issue.

        Args:
            issue_id: Issue ID to close
            reason: Reason for closing
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with confirmation
        """
        args = ["close", issue_id]
        if reason:
            args.extend(["--reason", reason])
        args.append("--json")
        return BDCommand.run(args, cwd=cwd, timeout=timeout)

    @staticmethod
    def dep(
        from_id: str,
        to_id: str,
        dep_type: str = "blocks",
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> CommandResult:
        """Add dependency between bd issues.

        Args:
            from_id: Source issue ID
            to_id: Target issue ID
            dep_type: Dependency type (blocks, related, parent-child, discovered-from)
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            CommandResult with confirmation
        """
        args = ["dep", "add", from_id, to_id, "--type", dep_type]
        return BDCommand.run(args, cwd=cwd, timeout=timeout)
