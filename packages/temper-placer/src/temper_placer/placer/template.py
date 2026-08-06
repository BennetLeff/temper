"""
Template-based component placement structures.

Defines templates for common PCB layout patterns (half-bridge, LDO cluster, etc.)
that can be instantiated and placed deterministically.

Wave 4, **Phase 4** (placer non-`cp_sat` slice): the geometry compute of
``ComponentTemplate.apply`` and ``ParametricTemplate.apply`` (anchor-offset
scaling, the KiCad R(-theta) rotation around the anchor, absolute placement,
floored-modulo composite rotation) is implemented in Rust in the
``temper-io-types/placer_core`` crate
(``temper_io_types.placer_apply_component_template`` /
``placer_apply_parametric_template``). The dataclasses and the ``create_*``
data constructors stay Python (they are data containers, not compute, per
the R1e scorecard in ``packages/temper-io-types/VERIFICATION.md``), and
``load_template_from_yaml`` stays Python (``yaml.safe_load`` is a Python
library seam). The ``apply`` methods delegate to the Rust kernels.

The rotation transcendental (``math.cos``/``math.sin``) is a Python seam:
the shim passes a ``(cos, sin)`` callable into the kernel, so the
oracle's libm bits are preserved by construction (Rust's ``f64::sin`` is
not bit-identical to CPython's ``math.sin`` on this platform).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import temper_io_types as _t
import yaml  # type: ignore[import-untyped]


def _cos_sin(theta: float) -> tuple[float, float]:
    """Python seam: ``math.cos``/``math.sin`` of the rotation angle."""
    return (math.cos(theta), math.sin(theta))


@dataclass
class ComponentPosition:
    """Relative position of a component within a template."""

    ref: str  # Component reference (e.g., "Q1", "C_BUS1")
    x: float  # X position relative to template anchor (mm)
    y: float  # Y position relative to template anchor (mm)
    rotation: int = 0  # Rotation in degrees (0, 90, 180, 270)


@dataclass
class ParametricComponentPosition:
    """Relative position of a component within a parametric template."""

    ref: str
    x_ratio: float  # X position ratio [0, 1] within template width
    y_ratio: float  # Y position ratio [0, 1] within template height
    rotation: int = 0


@dataclass
class ParametricTemplate:
    """
    A template that scales based on target dimensions.

    Attributes:
        name: Template identifier
        components: List of parametric component positions
        anchor_ref: Reference of anchor component
        description: Human-readable description
    """

    name: str
    components: list[ParametricComponentPosition]
    anchor_ref: str
    description: str = ""

    def apply(
        self,
        anchor_x: float,
        anchor_y: float,
        target_width: float,
        target_height: float,
        rotation: int = 0,
    ) -> dict[str, tuple[float, float, int]]:
        """
        Apply parametric template at absolute position with target scaling.
        """
        anchor = next((c for c in self.components if c.ref == self.anchor_ref), None)
        # Default to center when the anchor ref is absent (the kernel's None
        # fallback computes 0.5 * target dims).
        anchor_ratio = None if anchor is None else (anchor.x_ratio, anchor.y_ratio)

        out = _t.placer_apply_parametric_template(
            [c.ref for c in self.components],
            [c.x_ratio for c in self.components],
            [c.y_ratio for c in self.components],
            [c.rotation for c in self.components],
            anchor_ratio,
            anchor_x,
            anchor_y,
            target_width,
            target_height,
            rotation,
            _cos_sin,
        )
        # The kernel returns insertion-ordered (ref, x, y, rot) rows; the
        # oracle's dict maps ref -> (x, y, rot) in that same order.
        return {ref: (x, y, rot) for ref, x, y, rot in out}

    @classmethod
    def create_half_bridge(
        cls,
        q1_ref: str = "Q1",
        q2_ref: str = "Q2",
        d1_ref: str = "D1",
        d2_ref: str = "D2",
        c_bus1_ref: str = "C_BUS1",
        c_bus2_ref: str = "C_BUS2",
    ) -> ParametricTemplate:
        """
        Create a parametric half-bridge template.
        """
        components = [
            # Vertical stack: Q1 top, Q2 bottom
            ParametricComponentPosition(q1_ref, 0.2, 0.8),
            ParametricComponentPosition(q2_ref, 0.2, 0.2),
            # Diodes adjacent
            ParametricComponentPosition(d1_ref, 0.5, 0.8),
            ParametricComponentPosition(d2_ref, 0.5, 0.2),
            # Caps flanking
            ParametricComponentPosition(c_bus1_ref, 0.8, 0.5),
            ParametricComponentPosition(c_bus2_ref, 0.8, 0.1),
        ]
        return cls(
            name="half_bridge_parametric",
            components=components,
            anchor_ref=q1_ref,
            description="Parametric half-bridge layout",
        )


@dataclass
class ComponentTemplate:
    """
    A template defining relative positions of related components.

    Templates provide known-good layouts for common patterns that can be
    instantiated at different absolute positions on the board.

    Attributes:
        name: Template identifier
        components: List of component positions relative to anchor
        anchor_point: Which component serves as the anchor (default: first)
        width: Template bounding box width (mm)
        height: Template bounding box height (mm)
        description: Human-readable description
    """

    name: str
    components: list[ComponentPosition]
    anchor_point: str | None = None  # Reference of anchor component
    width: float = 0.0
    height: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        """Set anchor to first component if not specified."""
        if self.anchor_point is None and self.components:
            self.anchor_point = self.components[0].ref

    def get_anchor_position(self) -> ComponentPosition | None:
        """Get the anchor component position."""
        for comp in self.components:
            if comp.ref == self.anchor_point:
                return comp
        return None

    def apply(
        self,
        anchor_x: float,
        anchor_y: float,
        rotation: int = 0,
    ) -> dict[str, tuple[float, float, int]]:
        """
        Apply template at absolute position.

        Args:
            anchor_x: Absolute X coordinate for anchor point
            anchor_y: Absolute Y coordinate for anchor point
            rotation: Template rotation (0, 90, 180, 270)

        Returns:
            Dict mapping ref -> (x, y, rotation) in absolute coordinates
        """
        anchor = self.get_anchor_position()
        if anchor is None:
            raise ValueError(f"Anchor point {self.anchor_point} not found in template")

        # The kernel needs the anchor index; the oracle's `next(...)` lookup
        # (first match on the anchor ref) is reproduced here.
        anchor_idx = next(
            i for i, comp in enumerate(self.components) if comp.ref == self.anchor_point
        )

        out = _t.placer_apply_component_template(
            [c.ref for c in self.components],
            [c.x for c in self.components],
            [c.y for c in self.components],
            [c.rotation for c in self.components],
            anchor_idx,
            anchor_x,
            anchor_y,
            rotation,
            _cos_sin,
        )
        # The kernel returns insertion-ordered (ref, x, y, rot) rows; the
        # oracle's dict maps ref -> (x, y, rot) in that same order.
        return {ref: (x, y, rot) for ref, x, y, rot in out}


@dataclass
class HalfBridgeTemplate(ComponentTemplate):
    """
    Half-bridge power stage template.

    Standard vertical layout:
    - Q1 (high-side IGBT) at top
    - Q2 (low-side IGBT) below Q1
    - D1 (high-side diode) adjacent to Q1
    - D2 (low-side diode) adjacent to Q2
    - C_BUS1, C_BUS2 (DC bus caps) flanking switches

    Optimized for:
    - Low commutation loop inductance
    - Symmetric current paths
    - Thermal management (vertical heatsink)
    """

    @classmethod
    def create_vertical(
        cls,
        q1_ref: str = "Q1",
        q2_ref: str = "Q2",
        d1_ref: str = "D1",
        d2_ref: str = "D2",
        c_bus1_ref: str = "C_BUS1",
        c_bus2_ref: str = "C_BUS2",
        switch_spacing: float = 25.0,  # Q1 to Q2 spacing (TO-247 is ~21mm tall)
        diode_offset: float = 18.0,  # Horizontal offset for diodes (TO-247 is ~16mm wide)
        cap_offset: float = 28.0,  # Lateral offset for bus caps
    ) -> HalfBridgeTemplate:
        """
        Create a vertical half-bridge template.

        Layout (top view, Y increases upward):
        ```
                          C_BUS2
        Q1 ---- D1          |
        |       |           |
        Q2 ---- D2          |
                          C_BUS1
        ```

        Default spacing for TO-247 IGBTs:
        - TO-247 package: ~16mm x 21mm
        - switch_spacing: 25mm (center-to-center, allows 4mm clearance)
        - diode_offset: 18mm (side-by-side with 2mm gap)
        - cap_offset: 28mm (centered between Q1/Q2 with margin)

        Args:
            q1_ref: High-side switch reference
            q2_ref: Low-side switch reference
            d1_ref: High-side diode reference
            d2_ref: Low-side diode reference
            c_bus1_ref: First bus capacitor reference
            c_bus2_ref: Second bus capacitor reference
            switch_spacing: Vertical spacing between Q1 and Q2 (mm)
            diode_offset: Horizontal offset for diodes from switches (mm)
            cap_offset: Horizontal offset for bus caps from center (mm)

        Returns:
            Configured HalfBridgeTemplate
        """
        components = [
            # Q1 at origin (anchor) - high side switch
            ComponentPosition(q1_ref, x=0.0, y=0.0, rotation=0),
            # Q2 below Q1 - low side switch
            ComponentPosition(q2_ref, x=0.0, y=-switch_spacing, rotation=0),
            # D1 right of Q1 - high side diode
            ComponentPosition(d1_ref, x=diode_offset, y=0.0, rotation=0),
            # D2 right of Q2 - low side diode
            ComponentPosition(d2_ref, x=diode_offset, y=-switch_spacing, rotation=0),
            # C_BUS1 right of power stage, between Q1 and Q2
            ComponentPosition(c_bus1_ref, x=cap_offset, y=-switch_spacing * 0.25, rotation=0),
            # C_BUS2 right of power stage, between Q1 and Q2
            ComponentPosition(c_bus2_ref, x=cap_offset, y=-switch_spacing * 0.75, rotation=0),
        ]

        return cls(
            name="half_bridge_vertical",
            components=components,
            anchor_point=q1_ref,
            width=cap_offset + 15,  # Include capacitor width
            height=switch_spacing + 15,  # Include component heights
            description="Vertical half-bridge with TO-247 IGBTs and bus capacitors",
        )


def load_template_from_yaml(path: Path) -> ComponentTemplate:
    """
    Load a component template from YAML file.

    YAML format:
    ```yaml
    name: half_bridge_vertical
    anchor_point: Q1
    description: "Vertical half-bridge layout"
    components:
      - ref: Q1
        x: 0.0
        y: 0.0
        rotation: 0
      - ref: Q2
        x: 0.0
        y: -15.0
        rotation: 0
    ```

    Args:
        path: Path to YAML template file

    Returns:
        ComponentTemplate instance
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    components = [
        ComponentPosition(
            ref=c["ref"],
            x=float(c["x"]),
            y=float(c["y"]),
            rotation=int(c.get("rotation", 0)),
        )
        for c in data["components"]
    ]

    return ComponentTemplate(
        name=data["name"],
        components=components,
        anchor_point=data.get("anchor_point"),
        width=float(data.get("width", 0)),
        height=float(data.get("height", 0)),
        description=data.get("description", ""),
    )
