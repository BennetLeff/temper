from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from temper_workflow.utils.command import CommandResult, CommandRunner


class BasePhase(ABC):
    """Base class for GPBM phases with shared functionality."""

    def __init__(self, project_root: Path | None = None):
        """Initialize the phase.
        
        Args:
            project_root: Root directory of the project. If None, detected automatically.
        """
        self.cmd_runner = CommandRunner(cwd=project_root)
        self.project_root = self.cmd_runner.cwd

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute the phase. Must be implemented by subclasses."""
        pass

    def _run_bd(self, args: list[str]) -> CommandResult:
        """Convenience method for running bd commands.
        
        Args:
            args: List of arguments for the bd command.
            
        Returns:
            CommandResult containing success status and output.
        """
        return self.cmd_runner.run(["bd", "--sandbox"] + args)
