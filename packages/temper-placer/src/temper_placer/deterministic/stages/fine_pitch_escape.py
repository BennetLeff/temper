"""Fine-pitch IC escape routing stage.

This stage automatically detects fine-pitch components (components with pins
closer than a threshold) and places escape vias at their pins to enable
inner-layer routing. This solves the problem of overlapping clearance zones
on the surface layer that block routing.

Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001): the
**run orchestration** (the fine-pitch detection passes, the escape-via
placement loop, the debug prints and the Phase-5 escape validation) is
implemented in Rust (``temper-orchestration``'s ``FinePitchEscapeStage`` /
``run_fine_pitch_escape``), crossing the FFI once per stage call. This module
keeps the public API: the ``FinePitchEscapeStage`` dataclass (constructor
surface, the ``name`` property and the two leaf methods
``_calculate_min_pin_pitch`` / ``_get_escape_layer_for_net`` -- pinned by
``test_fine_pitch_escape_rust_differential.py``) stays as the pre-D7 bodies.
The two pure kernels stay single-source in ``temper_design_bundle_python``
(``min_pin_pitch_py`` / ``escape_layer_for_net_py``); ``pin_world_position_at``
and the ``Via`` pyclass stay Python and are driven through FFI by the port.
The pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_fine_pitch_escape_run_py_oracle.py``.
"""

from dataclasses import dataclass, field

import temper_design_bundle_python as _tdb
import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


@dataclass
class FinePitchEscapeStage(Stage):
    """Place escape vias for fine-pitch IC pins to enable inner-layer routing.

    This stage:
    1. Auto-detects fine-pitch components by calculating minimum pin-to-pin distance
    2. Places via-under-pad at each netted pin on fine-pitch components
    3. Vias connect from surface layer (F.Cu/Layer 0) to escape layer (In1.Cu or In2.Cu)
    4. Main router can then start routing from escape layer where clearances don't conflict

    EXP-6b: Distributes escape vias across multiple inner layers to reduce congestion.

    Args:
        pin_pitch_threshold_mm: Minimum pin spacing to qualify as fine-pitch (default: 0.65mm)
        escape_layer: Primary target inner layer for escape routing (default: 1 = In1.Cu)
        secondary_escape_layer: Secondary layer for load balancing (default: 2 = In2.Cu)
        via_drill_mm: Via drill diameter (default: 0.3mm)
        via_diameter_mm: Via copper diameter (default: 0.6mm)
        escape_layer: Primary target inner layer for escape routing (default: 1 = In1.Cu)
        secondary_escape_layer: Secondary layer for load balancing (default: 2 = In2.Cu)
        via_drill_mm: Via drill diameter (default: 0.3mm)
        via_diameter_mm: Via copper diameter (default: 0.6mm)
        layer2_nets: Set of net names that should escape to Layer 2 instead of Layer 1
        layer3_nets: Set of net names that should escape to Layer 3 (B.Cu) for outer-layer routing
    """

    pin_pitch_threshold_mm: float = 0.65  # Pins closer than this = fine-pitch
    escape_layer: int = 1  # In1.Cu (primary)
    secondary_escape_layer: int = 2  # In2.Cu (secondary, for load balancing)
    via_drill_mm: float = 0.3
    via_diameter_mm: float = 0.6
    # EXP-6b/EXP-10: Nets to route on Layer 2 (reduces Layer 1 congestion)
    # EXP-10: Added SPI_CLK, SPI_CS_TEMP to balance In1.Cu congestion
    layer2_nets: set = field(
        default_factory=lambda: {
            "PWM_H",
            "PWM_L",
            "GATE_H",
            "GATE_L",
            "SPI_CLK",
            "SPI_CS_TEMP",  # EXP-10: Move to In2.Cu
        }
    )
    # EXP-9: Analog/sensing nets escape to B.Cu (layer 3) to match routing restrictions [0, 3]
    layer3_nets: set = field(default_factory=lambda: {"I_SENSE", "TEMP_SENSE"})

    @property
    def name(self) -> str:
        return "fine_pitch_escape"

    def _get_escape_layer_for_net(self, net_name: str) -> tuple[int, str]:
        """Determine which layer a net should escape to.

        EXP-6b: Distribute nets across layers to reduce congestion.
        EXP-9: Analog/sensing nets escape to B.Cu to match their routing restrictions.

        Returns:
            Tuple of (layer_number, layer_name)
        """
        return _tdb.deterministic_leaves.escape_layer_for_net_py(
            net_name,
            self.layer2_nets,
            self.layer3_nets,
            self.escape_layer,
            self.secondary_escape_layer,
        )

    def run(self, state: BoardState) -> BoardState:
        """Run the fine-pitch escape orchestration in Rust (Phase D D7);
        crosses the FFI once per stage call."""
        return _to.run_fine_pitch_escape(state, self)

    def _calculate_min_pin_pitch(self, component):
        """Calculate minimum pin-to-pin distance for a component.

        Args:
            component: Component to analyze

        Returns:
            Minimum distance between any two pins in mm, or None if < 2 pins
        """
        return _tdb.deterministic_leaves.min_pin_pitch_py(component.pins)
