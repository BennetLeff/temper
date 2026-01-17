"""
LiveVisualizer integration for training loop.

This module provides the main integration class for real-time visualization
of placement optimization. It ties together the server, model, and renderers.

Usage:
    from temper_placer.visualization import LiveVisualizer

    # Create visualizer
    viz = LiveVisualizer(port=8765, open_browser=True)

    # Start server
    viz.start()

    # In training loop:
    viz.update(
        positions=positions,
        rotations=rotations,
        widths=widths,
        heights=heights,
        refs=refs,
        board_width=100.0,
        board_height=80.0,
        losses={'overlap': 0.5, 'boundary': 0.3},
        epoch=100,
    )

    # At end:
    viz.stop()
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from .model import (
    BoardView,
    ComponentView,
    ConstraintStatus,
    LossDataPoint,
    LossHistory,
    Point,
    Violation,
    ViolationType,
    VisualizationState,
    ZoneView,
)
from .server import (
    WEBSOCKETS_AVAILABLE,
    LiveServer,
    MockLiveServer,
)

logger = logging.getLogger(__name__)


@dataclass
class LiveVisualizerConfig:
    """Configuration for LiveVisualizer."""

    # Server settings
    host: str = "localhost"
    port: int = 8765
    open_browser: bool = True

    # Update settings
    update_interval_ms: int = 100  # Minimum time between updates
    log_interval: int = 100  # Epochs between log messages

    # Mode settings
    headless: bool = False  # If True, no server started, just logging
    verbose: bool = True  # Log progress messages

    # Constraint thresholds for violation detection
    overlap_threshold: float = 0.001
    boundary_threshold: float = 0.001
    clearance_threshold: float = 0.001


class LiveVisualizer:
    """
    Real-time visualization for placement optimization.

    This class integrates with the training loop to provide live updates
    to a browser-based visualization dashboard.

    Attributes:
        config: Configuration settings.
        server: The WebSocket server (or mock server if headless).
        loss_history: Accumulated loss history.

    Example:
        >>> viz = LiveVisualizer(port=8765)
        >>> viz.start()
        >>> for epoch in range(1000):
        ...     # ... training step ...
        ...     viz.update(
        ...         positions=positions,
        ...         rotations=rotations,
        ...         widths=widths,
        ...         heights=heights,
        ...         refs=refs,
        ...         board_width=100.0,
        ...         board_height=80.0,
        ...         losses={'total': loss},
        ...         epoch=epoch,
        ...     )
        >>> viz.stop()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        open_browser: bool = True,
        update_interval_ms: int = 100,
        log_interval: int = 100,
        headless: bool = False,
        verbose: bool = True,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
        on_step: Callable[[int], None] | None = None,
    ):
        """
        Initialize the LiveVisualizer.

        Args:
            host: Host to bind server to.
            port: Port for WebSocket server.
            open_browser: Whether to open browser on start.
            update_interval_ms: Minimum time between updates.
            log_interval: Epochs between log messages.
            headless: If True, no server is started (just logging).
            verbose: Whether to log progress messages.
            on_pause: Callback when user requests pause.
            on_resume: Callback when user requests resume.
            on_step: Callback when user requests N steps.
        """
        self.config = LiveVisualizerConfig(
            host=host,
            port=port,
            open_browser=open_browser,
            update_interval_ms=update_interval_ms,
            log_interval=log_interval,
            headless=headless,
            verbose=verbose,
        )

        # Callbacks
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_step = on_step

        # Server (created on start)
        self._server: LiveServer | MockLiveServer | None = None

        # State
        self._loss_history = LossHistory()
        self._start_time: float | None = None
        self._is_running = False
        self._last_log_epoch = -1

        # Thread safety
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Check if the visualizer is running."""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """Check if training is paused (by user request)."""
        if self._server:
            return self._server.is_paused
        return False

    @property
    def url(self) -> str:
        """Get the visualization URL."""
        if self._server:
            return self._server.url
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def client_count(self) -> int:
        """Get number of connected browser clients."""
        if self._server:
            return self._server.client_count
        return 0

    def start(self) -> None:
        """
        Start the visualization server.

        This spawns a background thread with the WebSocket server
        and optionally opens a browser window.
        """
        if self._is_running:
            logger.warning("LiveVisualizer already running")
            return

        self._start_time = time.time()

        if self.config.headless:
            # Headless mode - no server, just logging
            if self.config.verbose:
                logger.info("LiveVisualizer started in headless mode")
            self._server = MockLiveServer(
                host=self.config.host,
                port=self.config.port,
            )
        else:
            # Create real server
            if not WEBSOCKETS_AVAILABLE:
                logger.warning(
                    "websockets not installed, falling back to headless mode. "
                    "Install with: pip install websockets"
                )
                self._server = MockLiveServer(
                    host=self.config.host,
                    port=self.config.port,
                )
            else:
                self._server = LiveServer(
                    host=self.config.host,
                    port=self.config.port,
                    update_interval_ms=self.config.update_interval_ms,
                    open_browser=self.config.open_browser,
                    on_pause=self._on_pause,
                    on_resume=self._on_resume,
                    on_step=self._on_step,
                )
                self._server.start()

                if self.config.verbose:
                    logger.info(f"LiveVisualizer started at {self.url}")

        self._is_running = True

        # Notify clients that training has started
        if self._server:
            self._server.send_training_started()

    def stop(self) -> None:
        """
        Stop the visualization server.

        This shuts down the WebSocket server and cleans up resources.
        """
        if not self._is_running:
            return

        if self._server:
            # Send completion message with final state
            final_state = self._create_state(
                board=BoardView(width=0, height=0),
                epoch=len(self._loss_history.epochs),
                is_training=False,
            )
            self._server.send_training_complete(final_state)
            self._server.stop()

        self._is_running = False

        if self.config.verbose:
            logger.info("LiveVisualizer stopped")

    def update(
        self,
        positions: np.ndarray,
        rotations: np.ndarray,
        widths: np.ndarray,
        heights: np.ndarray,
        refs: list[str],
        board_width: float,
        board_height: float,
        losses: dict[str, float],
        epoch: int,
        zones: list[dict[str, Any]] | None = None,
        component_types: list[str] | None = None,
        component_groups: list[str] | None = None,
    ) -> None:
        """
        Send an update to the visualization.

        This method is thread-safe and can be called from the training loop.

        Args:
            positions: Component positions, shape (N, 2) or (N,) for x, (N,) for y.
            rotations: Component rotations in degrees, shape (N,).
            widths: Component widths, shape (N,).
            heights: Component heights, shape (N,).
            refs: Component reference designators.
            board_width: Board width in mm.
            board_height: Board height in mm.
            losses: Dictionary of loss names to values.
            epoch: Current epoch number.
            zones: Optional list of zone definitions.
            component_types: Optional list of component types.
            component_groups: Optional list of component groups.
        """
        if not self._is_running:
            return

        with self._lock:
            # Build board view
            board = self._build_board_view(
                positions=positions,
                rotations=rotations,
                widths=widths,
                heights=heights,
                refs=refs,
                board_width=board_width,
                board_height=board_height,
                zones=zones,
                component_types=component_types,
                component_groups=component_groups,
            )

            # Add to loss history
            total_loss = losses.get("total", sum(losses.values()))
            self._loss_history.add_point(
                LossDataPoint(
                    epoch=epoch,
                    total_loss=float(total_loss),
                    breakdown=losses,
                )
            )

            # Detect constraint violations
            constraints = self._detect_violations(
                positions=positions,
                widths=widths,
                heights=heights,
                board_width=board_width,
                board_height=board_height,
                losses=losses,
            )

            # Create visualization state
            state = self._create_state(
                board=board,
                epoch=epoch,
                is_training=True,
                constraints=constraints,
            )

            # Send to server
            if self._server:
                self._server.send_update(state)

            # Log progress
            if self.config.verbose and epoch - self._last_log_epoch >= self.config.log_interval:
                self._log_progress(epoch, total_loss, constraints)
                self._last_log_epoch = epoch

    def update_from_state(
        self,
        positions: np.ndarray,
        rotations: np.ndarray,
        component_info: dict[str, Any],
        board_info: dict[str, float],
        loss_info: dict[str, float],
        epoch: int,
    ) -> None:
        """
        Update from training state dictionaries.

        This is a convenience method for integration with the optimizer.

        Args:
            positions: Positions array, shape (N, 2).
            rotations: Rotations array, shape (N,).
            component_info: Dict with 'widths', 'heights', 'refs', optionally
                           'types', 'groups'.
            board_info: Dict with 'width', 'height'.
            loss_info: Dict of loss name -> value.
            epoch: Current epoch.
        """
        self.update(
            positions=positions,
            rotations=rotations,
            widths=np.array(component_info["widths"]),
            heights=np.array(component_info["heights"]),
            refs=component_info["refs"],
            board_width=board_info["width"],
            board_height=board_info["height"],
            losses=loss_info,
            epoch=epoch,
            component_types=component_info.get("types"),
            component_groups=component_info.get("groups"),
        )

    def _build_board_view(
        self,
        positions: np.ndarray,
        rotations: np.ndarray,
        widths: np.ndarray,
        heights: np.ndarray,
        refs: list[str],
        board_width: float,
        board_height: float,
        zones: list[dict[str, Any]] | None = None,
        component_types: list[str] | None = None,
        component_groups: list[str] | None = None,
    ) -> BoardView:
        """Build a BoardView from raw arrays."""
        # Handle different position formats
        if len(positions.shape) == 1:
            # Assume it's flattened [x0, y0, x1, y1, ...]
            n = positions.shape[0] // 2
            x_pos = positions[:n]
            y_pos = positions[n : 2 * n]
        elif positions.shape[1] == 2:
            x_pos = positions[:, 0]
            y_pos = positions[:, 1]
        else:
            raise ValueError(f"Invalid positions shape: {positions.shape}")

        # Build component views
        # Note: component_types and component_groups are accepted but not stored
        # in ComponentView (which only has: ref, position, rotation, width, height,
        # status, zone, footprint, violations). Future enhancement could add these.
        components = []
        for i, ref in enumerate(refs):
            comp = ComponentView(
                ref=ref,
                position=Point(float(x_pos[i]), float(y_pos[i])),
                rotation=float(rotations[i]) if i < rotations.shape[0] else 0.0,
                width=float(widths[i]),
                height=float(heights[i]),
            )
            components.append(comp)

        # Build zone views
        # ZoneView expects polygon: Tuple[Point, ...], we convert from rect bounds
        zone_views: list[ZoneView] = []
        if zones:
            for zone in zones:
                # Convert rectangular bounds to polygon points
                x = zone.get("x", 0)
                y = zone.get("y", 0)
                w = zone.get("width", 0)
                h = zone.get("height", 0)
                polygon = (
                    Point(x, y),
                    Point(x + w, y),
                    Point(x + w, y + h),
                    Point(x, y + h),
                )
                zone_view = ZoneView(
                    name=zone.get("name", ""),
                    zone_type=zone.get("type", "default"),
                    polygon=polygon,
                )
                zone_views.append(zone_view)

        return BoardView(
            width=board_width,
            height=board_height,
            components=tuple(components),
            zones=tuple(zone_views),
        )

    def _detect_violations(
        self,
        positions: np.ndarray,
        widths: np.ndarray,
        heights: np.ndarray,
        board_width: float,
        board_height: float,
        losses: dict[str, float],
    ) -> ConstraintStatus:
        """Detect constraint violations from loss values."""
        violations: list[Violation] = []

        # Count violations based on loss thresholds
        overlap_count = 0
        boundary_violations = 0
        clearance_violations = 0

        if losses.get("overlap", 0) > self.config.overlap_threshold:
            overlap_count = 1  # Simplified - actual count would need geometry
            violations.append(
                Violation(
                    violation_type=ViolationType.OVERLAP,
                    severity=float(losses.get("overlap", 0)),
                )
            )

        if losses.get("boundary", 0) > self.config.boundary_threshold:
            boundary_violations = 1
            violations.append(
                Violation(
                    violation_type=ViolationType.BOUNDARY,
                    severity=float(losses.get("boundary", 0)),
                )
            )

        if losses.get("clearance", 0) > self.config.clearance_threshold:
            clearance_violations = 1
            violations.append(
                Violation(
                    violation_type=ViolationType.CLEARANCE,
                    severity=float(losses.get("clearance", 0)),
                )
            )

        if losses.get("zone", 0) > 0:
            # Zone violations don't have a dedicated counter in ConstraintStatus
            violations.append(
                Violation(
                    violation_type=ViolationType.ZONE,
                    severity=float(losses.get("zone", 0)),
                )
            )

        return ConstraintStatus(
            violations=tuple(violations),
            overlap_count=overlap_count,
            boundary_violations=boundary_violations,
            clearance_violations=clearance_violations,
        )

    def _create_state(
        self,
        board: BoardView,
        epoch: int,
        is_training: bool,
        constraints: ConstraintStatus | None = None,
    ) -> VisualizationState:
        """Create a visualization state object."""
        elapsed = time.time() - self._start_time if self._start_time else 0.0

        return VisualizationState(
            board=board,
            loss_history=self._loss_history,
            constraints=constraints or ConstraintStatus(),
            epoch=epoch,
            elapsed_seconds=elapsed,
            is_training=is_training,
        )

    def _log_progress(
        self,
        epoch: int,
        total_loss: float,
        constraints: ConstraintStatus,
    ) -> None:
        """Log training progress."""
        elapsed = time.time() - self._start_time if self._start_time else 0.0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        violation_str = ""
        if constraints.overlap_count > 0:
            violation_str += f" overlaps={constraints.overlap_count}"
        if constraints.boundary_violations > 0:
            violation_str += f" boundary={constraints.boundary_violations}"

        logger.info(
            f"Epoch {epoch:5d} | Loss: {total_loss:.6f} | "
            f"Time: {minutes}:{seconds:02d}{violation_str}"
        )

    def get_loss_history(self) -> LossHistory:
        """Get the accumulated loss history."""
        return self._loss_history

    def clear_history(self) -> None:
        """Clear the loss history."""
        with self._lock:
            self._loss_history = LossHistory()


# Convenience function for quick setup
def create_visualizer(
    port: int = 8765,
    headless: bool = False,
    **kwargs: Any,
) -> LiveVisualizer:
    """
    Create a LiveVisualizer with sensible defaults.

    Args:
        port: Port for WebSocket server.
        headless: If True, no server is started.
        **kwargs: Additional arguments passed to LiveVisualizer.

    Returns:
        Configured LiveVisualizer instance.
    """
    return LiveVisualizer(port=port, headless=headless, **kwargs)
