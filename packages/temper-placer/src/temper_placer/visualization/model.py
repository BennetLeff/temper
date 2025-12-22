"""
Visualization data models.

This module defines dataclasses for visualization state that can be
serialized to JSON for WebSocket transmission to the browser frontend.

The models are designed to be:
- Immutable (frozen dataclasses) for safe sharing between threads
- JSON-serializable via to_dict() methods
- Decoupled from JAX arrays (use plain Python types)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast


class ComponentStatus(Enum):
    """Status of a component for color-coding in visualization."""

    OK = "ok"  # No violations
    WARNING = "warning"  # Minor violations (e.g., thermal proximity)
    ERROR = "error"  # Major violations (e.g., overlap, boundary)
    FIXED = "fixed"  # Component is fixed/locked


class ViolationType(Enum):
    """Type of constraint violation."""

    OVERLAP = "overlap"
    BOUNDARY = "boundary"
    CLEARANCE = "clearance"
    THERMAL = "thermal"
    ZONE = "zone"
    DRC = "drc"


@dataclass(frozen=True)
class Point:
    """2D point."""

    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_tuple(cls, t: tuple[float, float]) -> Point:
        return cls(x=t[0], y=t[1])


@dataclass(frozen=True)
class Rectangle:
    """Axis-aligned rectangle defined by center, width, height, and rotation."""

    center: Point
    width: float
    height: float
    rotation: float = 0.0  # Degrees

    def to_dict(self) -> dict[str, Any]:
        return {
            "center": self.center.to_dict(),
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
        }

    @property
    def corners(self) -> list[Point]:
        """Get the four corners of the rectangle (for rendering)."""
        import math

        cx, cy = self.center.x, self.center.y
        w, h = self.width / 2, self.height / 2
        angle = math.radians(self.rotation)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        # Corners relative to center
        corners_rel = [(-w, -h), (w, -h), (w, h), (-w, h)]

        # Rotate and translate
        corners = []
        for dx, dy in corners_rel:
            rx = dx * cos_a - dy * sin_a + cx
            ry = dx * sin_a + dy * cos_a + cy
            corners.append(Point(rx, ry))

        return corners


@dataclass(frozen=True)
class ComponentView:
    """
    Visualization data for a single component.

    Attributes:
        ref: Component reference designator (e.g., "U1", "R5").
        position: Center position (x, y) in mm.
        rotation: Rotation angle in degrees (0, 90, 180, 270).
        width: Component width in mm.
        height: Component height in mm.
        status: Current status for color-coding.
        zone: Zone the component is in (if any).
        footprint: Footprint name for hover info.
        value: Component value (e.g., "100uF", "10k", "LED").
        violations: List of active violations.
    """

    ref: str
    position: Point
    rotation: float
    width: float
    height: float
    status: ComponentStatus = ComponentStatus.OK
    zone: str | None = None
    footprint: str | None = None
    value: str | None = None
    violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "position": self.position.to_dict(),
            "rotation": self.rotation,
            "width": self.width,
            "height": self.height,
            "status": self.status.value,
            "zone": self.zone,
            "footprint": self.footprint,
            "value": self.value,
            "violations": list(self.violations),
        }

    @property
    def bounds(self) -> Rectangle:
        """Get the component bounding rectangle."""
        return Rectangle(
            center=self.position,
            width=self.width,
            height=self.height,
            rotation=self.rotation,
        )


@dataclass(frozen=True)
class ZoneView:
    """
    Visualization data for a board zone.

    Attributes:
        name: Zone name/identifier.
        polygon: List of points defining the zone boundary.
        zone_type: Type of zone (keepout, copper, etc.).
        color: Suggested color for rendering.
    """

    name: str
    polygon: tuple[Point, ...]
    zone_type: str = "generic"
    color: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "polygon": [p.to_dict() for p in self.polygon],
            "zone_type": self.zone_type,
            "color": self.color,
        }


@dataclass(frozen=True)
class TraceView:
    """
    Visualization data for a PCB trace segment.

    Attributes:
        start: Start point (x, y) in mm.
        end: End point (x, y) in mm.
        width: Trace width in mm.
        layer: Layer name (e.g., 'F.Cu', 'B.Cu').
        net: Optional net name for hover info.
    """

    start: Point
    end: Point
    width: float = 0.25
    layer: str = "F.Cu"
    net: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "width": self.width,
            "layer": self.layer,
            "net": self.net,
        }


@dataclass(frozen=True)
class PadView:
    """
    Visualization data for a component pad.

    Attributes:
        position: Center position (x, y) in mm.
        size: (width, height) in mm.
        shape: Pad shape ('rect', 'circle', 'oval', 'roundrect').
        rotation: Rotation angle in degrees.
        layer: Layer name (e.g., 'F.Cu', 'B.Cu').
        number: Pad number/name.
        net: Optional net name for hover info.
        component_ref: Reference of parent component.
    """

    position: Point
    size: tuple[float, float]
    shape: str = "rect"
    rotation: float = 0.0
    layer: str = "F.Cu"
    number: str = ""
    net: str | None = None
    component_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "size": list(self.size),
            "shape": self.shape,
            "rotation": self.rotation,
            "layer": self.layer,
            "number": self.number,
            "net": self.net,
            "component_ref": self.component_ref,
        }


@dataclass(frozen=True)
class BoardView:
    """
    Visualization data for the entire board state.

    Attributes:
        width: Board width in mm.
        height: Board height in mm.
        components: List of component views.
        zones: List of zone views.
        traces: List of trace views.
        pads: List of pad views.
        origin: Board origin offset (for coordinate display).
        title: Optional title for the visualization.
    """

    width: float
    height: float
    components: tuple[ComponentView, ...] = ()
    zones: tuple[ZoneView, ...] = ()
    traces: tuple[TraceView, ...] = ()
    pads: tuple[PadView, ...] = ()
    origin: Point = field(default_factory=lambda: Point(0.0, 0.0))
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "components": [c.to_dict() for c in self.components],
            "zones": [z.to_dict() for z in self.zones],
            "traces": [t.to_dict() for t in self.traces],
            "pads": [p.to_dict() for p in self.pads],
            "origin": self.origin.to_dict(),
            "title": self.title,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass(frozen=True)
class LossDataPoint:
    """Single data point in loss history."""

    epoch: int
    total_loss: float
    breakdown: dict[str, float] = field(default_factory=dict)
    temperature: float | None = None
    learning_rate: float | None = None
    convergence_confidence: float | None = None
    improvement_ema: float | None = None
    positions: list[tuple[float, float]] | None = None
    rotations: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "total_loss": self.total_loss,
            "breakdown": self.breakdown,
            "temperature": self.temperature,
            "learning_rate": self.learning_rate,
            "convergence_confidence": self.convergence_confidence,
            "improvement_ema": self.improvement_ema,
            "positions": self.positions,
            "rotations": self.rotations,
        }


@dataclass
class LossHistory:
    """
    Loss history for plotting curves.

    This class is mutable to allow incremental updates during training.

    Attributes:
        data_points: List of loss data points.
        phase_boundaries: Epoch numbers where curriculum phases change.
        phase_names: Names of curriculum phases.
    """

    data_points: list[LossDataPoint] = field(default_factory=list)
    phase_boundaries: list[int] = field(default_factory=list)
    phase_names: list[str] = field(default_factory=list)

    def add_point(self, point: LossDataPoint):
        """Add a new data point."""
        self.data_points.append(point)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_points": [p.to_dict() for p in self.data_points],
            "phase_boundaries": self.phase_boundaries,
            "phase_names": self.phase_names,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def epochs(self) -> list[int]:
        """Get list of epoch numbers."""
        return [p.epoch for p in self.data_points]

    @property
    def losses(self) -> list[float]:
        """Get list of total losses."""
        return [p.total_loss for p in self.data_points]

    def get_term_history(self, term_name: str) -> list[float]:
        """Get history for a specific loss term."""
        return [p.breakdown.get(term_name, 0.0) for p in self.data_points]

    @property
    def loss_terms(self) -> list[str]:
        """Get names of all loss terms."""
        if not self.data_points:
            return []
        return list(self.data_points[0].breakdown.keys())


@dataclass(frozen=True)
class Violation:
    """
    A single constraint violation.

    Attributes:
        violation_type: Type of violation.
        severity: Severity level (0-1, higher is worse).
        component_refs: Components involved in the violation.
        message: Human-readable description.
        location: Optional location of the violation.
    """

    violation_type: ViolationType
    severity: float
    component_refs: tuple[str, ...] = ()
    message: str = ""
    location: Point | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.violation_type.value,
            "severity": self.severity,
            "components": list(self.component_refs),
            "message": self.message,
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass(frozen=True)
class ConstraintStatus:
    """
    Status of all constraints.

    Attributes:
        violations: List of active violations.
        overlap_count: Number of overlapping component pairs.
        boundary_violations: Number of components outside boundary.
        clearance_violations: Number of clearance violations.
        thermal_warnings: Number of thermal proximity warnings.
        drc_errors: Number of DRC errors (if DRC validation enabled).
    """

    violations: tuple[Violation, ...] = ()
    overlap_count: int = 0
    boundary_violations: int = 0
    clearance_violations: int = 0
    thermal_warnings: int = 0
    drc_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "summary": {
                "overlap": self.overlap_count,
                "boundary": self.boundary_violations,
                "clearance": self.clearance_violations,
                "thermal": self.thermal_warnings,
                "drc": self.drc_errors,
            },
            "total_violations": len(self.violations),
            "has_errors": self.overlap_count > 0 or self.boundary_violations > 0,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def is_valid(self) -> bool:
        """Check if placement has no critical violations."""
        return self.overlap_count == 0 and self.boundary_violations == 0


@dataclass(frozen=True)
class VisualizationState:
    """
    Complete visualization state for a single frame.

    This is the top-level object sent to the frontend via WebSocket.

    Attributes:
        board: Current board view with component positions.
        loss_history: Loss curve data.
        constraints: Current constraint status.
        epoch: Current training epoch.
        elapsed_seconds: Total training time.
        is_training: Whether training is currently active.
    """

    board: BoardView
    loss_history: LossHistory
    constraints: ConstraintStatus
    epoch: int = 0
    elapsed_seconds: float = 0.0
    is_training: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board.to_dict(),
            "loss_history": self.loss_history.to_dict(),
            "constraints": self.constraints.to_dict(),
            "epoch": self.epoch,
            "elapsed_seconds": self.elapsed_seconds,
            "is_training": self.is_training,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# Factory functions for creating views from internal data structures


def create_component_view(
    ref: str,
    position: tuple[float, float],
    rotation_degrees: float,
    bounds: tuple[float, float],
    footprint: str | None = None,
    status: ComponentStatus = ComponentStatus.OK,
    violations: list[str] | None = None,
) -> ComponentView:
    """
    Create a ComponentView from raw data.

    Args:
        ref: Component reference designator.
        position: (x, y) position in mm.
        rotation_degrees: Rotation in degrees.
        bounds: (width, height) in mm.
        footprint: Optional footprint name.
        status: Component status.
        violations: Optional list of violation messages.

    Returns:
        ComponentView instance.
    """
    return ComponentView(
        ref=ref,
        position=Point(position[0], position[1]),
        rotation=rotation_degrees,
        width=bounds[0],
        height=bounds[1],
        footprint=footprint,
        status=status,
        violations=tuple(violations) if violations else (),
    )


def create_board_view_from_state(
    board_width: float,
    board_height: float,
    component_refs: list[str],
    positions: list[tuple[float, float]],
    rotations: list[float],
    bounds: list[tuple[float, float]],
    footprints: list[str] | None = None,
    statuses: list[ComponentStatus] | None = None,
) -> BoardView:
    """
    Create a BoardView from placement state arrays.

    Args:
        board_width: Board width in mm.
        board_height: Board height in mm.
        component_refs: List of component reference designators.
        positions: List of (x, y) positions.
        rotations: List of rotation angles in degrees.
        bounds: List of (width, height) bounds.
        footprints: Optional list of footprint names.
        statuses: Optional list of component statuses.

    Returns:
        BoardView instance.
    """
    n = len(component_refs)
    # Use explicit typing to handle None list - cast to satisfy type checker
    fp_list: list[str | None] = cast(
        list[str | None], footprints if footprints else [None] * n
    )
    status_list = statuses if statuses else [ComponentStatus.OK] * n

    components = tuple(
        ComponentView(
            ref=component_refs[i],
            position=Point(positions[i][0], positions[i][1]),
            rotation=rotations[i],
            width=bounds[i][0],
            height=bounds[i][1],
            footprint=fp_list[i],
            status=status_list[i],
        )
        for i in range(n)
    )

    return BoardView(
        width=board_width,
        height=board_height,
        components=components,
    )


def create_loss_data_point_from_metrics(metrics: Any) -> LossDataPoint:
    """
    Create a LossDataPoint from TrainingMetrics.

    Args:
        metrics: TrainingMetrics from optimizer.

    Returns:
        LossDataPoint instance.
    """
    return LossDataPoint(
        epoch=metrics.epoch,
        total_loss=metrics.loss,
        breakdown=dict(metrics.loss_breakdown) if metrics.loss_breakdown else {},
        temperature=metrics.temperature,
        learning_rate=metrics.learning_rate,
        convergence_confidence=getattr(metrics, "convergence_confidence", None),
        improvement_ema=getattr(metrics, "loss_improvement_ema", None),
    )
