"""Terminal dashboard observer for live pipeline visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel


@dataclass
class TerminalDashboardObserver:
    """Live terminal dashboard driven by ProgressObserver lifecycle events."""

    stage_order: list[str]
    refresh_per_second: float = 4.0

    _console: Console = field(default_factory=Console)
    _live: Live | None = field(default=None, repr=False)
    _layout: Layout | None = field(default=None, repr=False)
    _stage_status: dict[str, str] = field(default_factory=dict)
    _stage_timers: dict[str, float] = field(default_factory=dict)
    _stage_durations: dict[str, float] = field(default_factory=dict)
    _stage_iterations: dict[str, int] = field(default_factory=dict)
    _losses: list[float] = field(default_factory=list)
    _loss_epochs: list[int] = field(default_factory=list)
    _current_stage: str = ""
    _pipeline_start: float = 0.0
    _total_duration: float = 0.0
    _pipeline_success: bool | None = None
    _feedback_count: int = 0
    _header_text: str = "Temper Pipeline"

    STATUS_IDLE = "idle"
    STATUS_ACTIVE = "active"
    STATUS_DONE = "done"
    STATUS_SKIP = "skip"
    STATUS_ERROR = "error"

    _STATUS_STYLES: ClassVar[dict[str, str]] = {
        "idle": "dim", "active": "bold cyan", "done": "bold green",
        "skip": "dim yellow", "error": "bold red",
    }
    _STATUS_ICONS: ClassVar[dict[str, str]] = {
        "idle": " ", "active": "\u25b8", "done": "\u2713",
        "skip": "\u2212", "error": "\u2717",
    }

    def on_stage_start(self, stage_name: str, iteration: int, context: dict[str, Any]) -> None:
        import time
        self._stage_status[stage_name] = self.STATUS_ACTIVE
        self._stage_timers[stage_name] = time.monotonic()
        self._stage_iterations[stage_name] = iteration
        self._current_stage = stage_name
        self._header_text = f"Temper Pipeline \u2014 {stage_name}"
        if self._pipeline_start == 0.0:
            self._pipeline_start = time.monotonic()

    def on_stage_complete(self, stage_name: str, duration_s: float, outputs: dict[str, Any]) -> None:
        self._stage_status[stage_name] = self.STATUS_DONE
        self._stage_durations[stage_name] = duration_s

    def on_stage_skip(self, stage_name: str, reason: str) -> None:
        self._stage_status[stage_name] = self.STATUS_SKIP
        self._stage_durations[stage_name] = 0.0

    def on_stage_error(self, stage_name: str, error: Exception) -> None:
        self._stage_status[stage_name] = self.STATUS_ERROR
        self._header_text = f"Temper Pipeline \u2014 {stage_name} FAILED"

    def on_feedback_triggered(self, contract_name: str, from_stage: str, to_stage: str,
                               attempt: int) -> None:
        self._feedback_count += 1

    def on_pipeline_complete(self, success: bool, total_duration_s: float,
                              stage_timings: dict[str, float]) -> None:
        self._pipeline_success = success
        self._total_duration = total_duration_s
        self._stage_durations.update(stage_timings)
        self._header_text = (
            f"Temper Pipeline \u2014 {'PASSED' if success else 'FAILED'} "
            f"({total_duration_s:.1f}s)"
        )

    def on_epoch(self, stage_name: str, epoch: int, loss: float) -> None:
        self._loss_epochs.append(epoch)
        self._losses.append(loss)
        if len(self._losses) > 200:
            self._losses = self._losses[-200:]
            self._loss_epochs = self._loss_epochs[-200:]

    def __enter__(self) -> TerminalDashboardObserver:
        self._init_layout()
        self._live = Live(self._layout, console=self._console,
                          refresh_per_second=self.refresh_per_second, screen=False)
        self._live.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._live is not None:
            self._live.__exit__(*args)
            self._live = None

    def _init_layout(self) -> None:
        layout = Layout()
        layout.split(Layout(name="header", size=3), Layout(name="stages"),
                      Layout(name="footer", size=3))
        self._layout = layout

    def _make_header(self) -> Panel:
        return Panel(self._header_text, title="temper watch", border_style="blue")

    def _make_stage_panels(self) -> list[RenderableType]:
        import time
        panels: list[RenderableType] = []
        now = time.monotonic()
        for name in self.stage_order:
            status = self._stage_status.get(name, self.STATUS_IDLE)
            style = self._STATUS_STYLES.get(status, "")
            icon = self._STATUS_ICONS.get(status, " ")
            lines: list[str] = [f"[{style}]{icon} {name}[/]"]
            if status == self.STATUS_ACTIVE and name in self._stage_timers:
                lines.append(f"  running: {now - self._stage_timers[name]:.1f}s")
            elif name in self._stage_durations:
                dur = self._stage_durations[name]
                if dur > 0:
                    lines.append(f"  duration: {dur:.1f}s")
                elif status == self.STATUS_SKIP:
                    lines.append("  skipped")
            if name == "geometric" and self._losses:
                lines.append(f"  loss: {self._losses[-1]:.4f}")
                spark = self._make_sparkline()
                if spark:
                    lines.append(f"  {spark}")
            panel_style = {"done": "green", "error": "red", "active": "cyan"}.get(status, "dim") if status != self.STATUS_IDLE else "dim"
            panels.append(Panel("\n".join(lines) if lines else " ", border_style=panel_style))
        return panels

    def _make_sparkline(self) -> str:
        if len(self._losses) < 2:
            return ""
        recent = self._losses[-50:]
        mn, mx = min(recent), max(recent)
        rng = mx - mn if mx > mn else 1.0
        blocks = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
        return "".join(blocks[max(0, min(int((v - mn) / rng * (len(blocks) - 1)), len(blocks) - 1))] for v in recent)

    def _make_footer(self) -> Panel:
        import time
        parts: list[str] = []
        if self._pipeline_start > 0 and self._pipeline_success is None:
            parts.append(f"Elapsed: {time.monotonic() - self._pipeline_start:.1f}s")
        if self._feedback_count > 0:
            parts.append(f"Feedback: {self._feedback_count}")
        if self._pipeline_success is not None:
            parts.append(f"Total: {self._total_duration:.1f}s")
        return Panel(" | ".join(parts) if parts else " ", border_style="dim")

    def update(self) -> None:
        if self._live is not None and self._layout is not None:
            self._layout["header"].update(self._make_header())
            panels = self._make_stage_panels()
            cols = Layout()
            half = len(panels) // 2 + len(panels) % 2
            left, right = Layout(name="left"), Layout(name="right")
            left.split_column(*[Layout(p) for p in panels[:half]])
            right.split_column(*[Layout(p) for p in panels[half:]])
            cols.split_row(left, right)
            self._layout["stages"].update(cols)
            self._layout["footer"].update(self._make_footer())
            self._live.update(self._layout)


def create_terminal_dashboard(stage_order: list[str], **kwargs: Any) -> TerminalDashboardObserver:
    return TerminalDashboardObserver(stage_order=stage_order, **kwargs)
