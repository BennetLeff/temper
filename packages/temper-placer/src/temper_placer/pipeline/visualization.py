from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

if TYPE_CHECKING:
    from temper_placer.pipeline.orchestrator import PipelineState, PipelinePhase

@dataclass
class TerminalProgress:
    """ASCII progress display for terminal."""
    total_phases: int = 8
    current_phase: int = 0
    current_iteration: int = 0
        
    def on_phase_start(self, phase: Any, state: PipelineState) -> None:
        self.current_phase += 1
        bar = self._make_bar(self.current_phase, self.total_phases)
        phase_name = phase.value if hasattr(phase, 'value') else str(phase)
        print(f"\r{bar} Phase {self.current_phase}/{self.total_phases}: {phase_name}", end="", flush=True)
        
    def on_phase_complete(self, phase: Any, state: PipelineState) -> None:
        print(" [DONE]")
        
    def on_iteration(self, iteration: int, state: PipelineState) -> None:
        self.current_iteration = iteration
        feasible = getattr(state.routing_report, 'feasible', 'Unknown') if state.routing_report else 'N/A'
        print(f"  Iteration {iteration}: routing_feasible={feasible}")
        
    def on_epoch(self, metrics: Any) -> None:
        # metrics is likely TrainingMetrics from optimizer
        epoch = getattr(metrics, 'epoch', 0)
        loss = getattr(metrics, 'loss', 0.0)
        if epoch % 100 == 0:
            print(f"    Epoch {epoch:5d}: loss={loss:.4f}")
    
    def _make_bar(self, current: int, total: int, width: int = 20) -> str:
        filled = int(width * current / total)
        return f"[{'#' * filled}{'.' * (width - filled)}]"

class RichDashboard:
    """Interactive terminal dashboard with Rich."""
    
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.losses = []
        self.current_phase = "Starting..."
        self.iteration = 0
        self.metrics = {}
        
    def create_layout(self) -> Layout:
        """Create dashboard layout."""
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        
        self.layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2),
        )
        
        self.layout["footer"].update(Panel("Press Ctrl+C to abort pipeline", style="dim"))
        
        return self.layout
    
    def update_header(self, phase: str, iteration: int) -> Panel:
        return Panel(
            Text.from_markup(f"Phase: [bold blue]{phase}[/] | Iteration: [bold green]{iteration}[/]"),
            title="[bold]Temper Placer Pipeline[/]",
            border_style="blue"
        )
    
    def update_metrics(self) -> Table:
        table = Table(title="Metrics", expand=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        for key, value in self.metrics.items():
            val_str = f"{value:.4f}" if isinstance(value, float) else str(value)
            table.add_row(key, val_str)
        
        return table
    
    def update_loss_chart(self) -> str:
        """ASCII sparkline for loss history."""
        if not self.losses:
            return "No loss data yet..."
        
        # Use a subset for the sparkline
        data = self.losses[-100:]
        min_l = min(data)
        max_l = max(data)
        range_l = max_l - min_l if max_l > min_l else 1.0
        
        blocks = " ▂▃▄▅▆▇█"
        sparkline = ""
        for val in data:
            idx = int((val - min_l) / range_l * (len(blocks) - 1))
            sparkline += blocks[idx]
            
        return f"Loss Trend (Last 100 epochs):\n{sparkline}\nCurrent Loss: {self.losses[-1]:.4f}"
    
    def update(self):
        """Refresh layout content."""
        phase_name = self.current_phase.value if hasattr(self.current_phase, 'value') else str(self.current_phase)
        self.layout["header"].update(self.update_header(phase_name, self.iteration))
        self.layout["body"]["left"].update(self.update_metrics())
        self.layout["body"]["right"].update(Panel(self.update_loss_chart(), title="Optimization Progress"))

    def on_epoch(self, metrics: Any) -> None:
        loss = getattr(metrics, 'loss', 0.0)
        self.losses.append(loss)
        self.metrics["epoch"] = getattr(metrics, 'epoch', 0)
        self.metrics["loss"] = loss
        if hasattr(metrics, 'temperature'):
            self.metrics["temp"] = metrics.temperature
        if hasattr(metrics, 'learning_rate'):
            self.metrics["lr"] = metrics.learning_rate

    def on_phase_start(self, phase: Any, state: Any) -> None:
        self.current_phase = phase
        
    def on_iteration(self, iteration: int, state: Any) -> None:
        self.iteration = iteration
        if state.routing_report:
            self.metrics["routing"] = "Feasible" if state.routing_report.feasible else "Infeasible"
            if hasattr(state.routing_report, 'total_congestion'):
                self.metrics["congestion"] = state.routing_report.total_congestion
