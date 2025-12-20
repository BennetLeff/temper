"""Pipeline visualization components.

This module provides visualization classes for pipeline progress:
- TerminalProgress: Simple ASCII progress display
- RichDashboard: Rich library terminal dashboard
- ProgressCallback: Base class for progress callbacks

Usage:
    from temper_placer.pipeline.visualization import TerminalProgress, RichDashboard

    # Simple terminal progress
    progress = TerminalProgress()
    orchestrator.on_phase_start = progress.on_phase_start
    orchestrator.on_phase_complete = progress.on_phase_complete

    # Rich dashboard
    dashboard = RichDashboard()
    dashboard.attach(orchestrator)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table


class ProgressCallback:
    """Base class for progress callbacks.

    Defines the interface for progress display implementations.
    Subclasses should override these methods to provide custom
    visualization behavior.
    """

    def on_phase_start(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase starts.

        Args:
            phase: Name of the phase starting
            state: Current pipeline state
        """
        pass

    def on_phase_complete(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase completes.

        Args:
            phase: Name of the phase completed
            state: Current pipeline state
        """
        pass

    def on_iteration(self, iteration: int, state: Any) -> None:
        """Called when a refinement iteration starts.

        Args:
            iteration: Current iteration number
            state: Current pipeline state
        """
        pass

    def on_epoch(self, epoch: int, loss: float) -> None:
        """Called during optimization epochs.

        Args:
            epoch: Current epoch number
            loss: Current loss value
        """
        pass


@dataclass
class TerminalProgress(ProgressCallback):
    """Simple ASCII progress display for terminal.

    Provides minimal progress output suitable for non-interactive
    terminals and log files.

    Attributes:
        total_phases: Total number of pipeline phases
        current_phase: Currently executing phase number
        current_iteration: Current refinement iteration
        epoch_interval: How often to print epoch updates (default: 100)

    Example:
        progress = TerminalProgress()
        orchestrator.on_phase_start = progress.on_phase_start
        orchestrator.on_phase_complete = progress.on_phase_complete
        orchestrator.on_iteration = progress.on_iteration
    """

    total_phases: int = 8
    current_phase: int = 0
    current_iteration: int = 0
    epoch_interval: int = 100

    def on_phase_start(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase starts."""
        self.current_phase += 1
        bar = self._make_bar(self.current_phase, self.total_phases)
        print(f"{bar} Phase {self.current_phase}/{self.total_phases}: {phase}", end="", flush=True)

    def on_phase_complete(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase completes."""
        print(" [DONE]", flush=True)

    def on_iteration(self, iteration: int, state: Any) -> None:
        """Called when a refinement iteration starts."""
        self.current_iteration = iteration
        print(f"  Iteration {iteration}", flush=True)

    def on_epoch(self, epoch: int, loss: float) -> None:
        """Called during optimization epochs."""
        if epoch % self.epoch_interval == 0:
            print(f"    Epoch {epoch}: loss={loss:.4f}", flush=True)

    def _make_bar(self, current: int, total: int, width: int = 20) -> str:
        """Create an ASCII progress bar.

        Args:
            current: Current progress value
            total: Total value for 100%
            width: Character width of the bar

        Returns:
            ASCII progress bar string like "[######..........]"
        """
        if total <= 0:
            return f"[{'.' * width}]"
        filled = int(width * current / total)
        empty = width - filled
        return f"[{'#' * filled}{'.' * empty}]"


@dataclass
class RichDashboard(ProgressCallback):
    """Interactive terminal dashboard using Rich library.

    Provides a rich, colorful dashboard with metrics table,
    loss sparkline, and phase indicators.

    Attributes:
        console: Rich console for output
        losses: History of loss values
        current_phase: Name of current phase
        iteration: Current iteration number
        metrics: Dictionary of metrics to display

    Example:
        dashboard = RichDashboard()
        orchestrator.on_phase_start = dashboard.on_phase_start
        orchestrator.on_epoch = dashboard.on_epoch
    """

    console: Console = field(default_factory=Console)
    losses: list[float] = field(default_factory=list)
    current_phase: str = "Starting..."
    iteration: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    _layout: Optional[Layout] = field(default=None, repr=False)

    def create_layout(self) -> Layout:
        """Create the dashboard layout.

        Returns:
            Rich Layout with header, body (left/right), and footer sections.
        """
        layout = Layout()

        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )

        self._layout = layout
        return layout

    def update_header(self, phase: str, iteration: int) -> Panel:
        """Create header panel with current status.

        Args:
            phase: Current phase name
            iteration: Current iteration number

        Returns:
            Rich Panel with status information
        """
        return Panel(
            f"Phase: {phase} | Iteration: {iteration}",
            title="Temper Placer Pipeline",
            border_style="blue",
        )

    def update_metrics(self) -> Table:
        """Create metrics table.

        Returns:
            Rich Table with current metrics
        """
        table = Table(title="Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in self.metrics.items():
            if isinstance(value, float):
                table.add_row(key, f"{value:.4f}")
            else:
                table.add_row(key, str(value))

        return table

    def update_loss_chart(self) -> str:
        """Create ASCII sparkline for loss history.

        Returns:
            String with current loss and sparkline visualization
        """
        if not self.losses:
            return "No data"

        # Normalize to 0-1 range
        min_loss = min(self.losses)
        max_loss = max(self.losses)
        range_loss = max_loss - min_loss if max_loss > min_loss else 1.0

        # Use Unicode blocks for sparkline
        blocks = " ▁▂▃▄▅▆▇█"

        # Take last 50 values for display
        recent = self.losses[-50:]
        line = ""
        for loss in recent:
            normalized = (loss - min_loss) / range_loss
            idx = int(normalized * (len(blocks) - 1))
            idx = max(0, min(idx, len(blocks) - 1))
            line += blocks[idx]

        return f"Loss: {self.losses[-1]:.4f}\n{line}"

    def on_phase_start(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase starts."""
        self.current_phase = phase
        self.console.print(f"[blue]→[/] Starting {phase}...")

    def on_phase_complete(self, phase: str, state: Any) -> None:
        """Called when a pipeline phase completes."""
        self.console.print(f"[green]✓[/] Completed {phase}")

    def on_iteration(self, iteration: int, state: Any) -> None:
        """Called when a refinement iteration starts."""
        self.iteration = iteration
        self.console.print(f"[yellow]⟳[/] Iteration {iteration}")

    def on_epoch(self, epoch: int, loss: float) -> None:
        """Called during optimization epochs."""
        self.losses.append(loss)
        self.metrics["epoch"] = epoch
        self.metrics["loss"] = loss

        # Keep only last 1000 values to avoid memory issues
        if len(self.losses) > 1000:
            self.losses = self.losses[-1000:]


def create_progress_display(display_type: str = "terminal") -> ProgressCallback:
    """Factory function to create progress displays.

    Args:
        display_type: Type of display ("terminal", "rich", or default)

    Returns:
        ProgressCallback instance of the requested type

    Example:
        progress = create_progress_display("terminal")
        orchestrator.on_phase_start = progress.on_phase_start
    """
    if display_type == "rich":
        return RichDashboard()
    else:
        return TerminalProgress()
