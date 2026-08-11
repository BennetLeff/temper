"""
D7 run-orchestration oracle for `deterministic/stages/fine_pitch_escape.py`.

Verbatim pre-D7 snapshot of the module at the D7 dispatch base (origin/main
`3a7dd1d9`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module except for
the four relative imports (`from ...core.pin_geometry` / `from ..state` /
`from .base` at module scope and the `from ...core.board import Via` inside
`run`) rewritten to their absolute forms so the oracle imports from the test
tree; the D7 Rust port (`temper-orchestration::FinePitchEscapeStage`) is the
differential subject, pinned by `test_deterministic_d7_rust_differential.py`.
The two leaf kernels (`min_pin_pitch_py` / `escape_layer_for_net_py`) stay
single-source in `temper_design_bundle_python.deterministic_leaves` and are
driven through FFI by the port.
"""

from dataclasses import dataclass, field

import temper_design_bundle_python as _tdb

from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---


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
        """Detect fine-pitch components and place escape vias."""
        if not state.netlist:
            return state

        from dataclasses import replace

        from temper_placer.core.board import Via

        placements = dict(state.placements) if state.placements else {}
        vias = list(state.vias) if state.vias else []

        # Track fine-pitch components for debug output
        fine_pitch_components = []
        layer1_vias = 0
        layer2_vias = 0
        layer3_vias = 0  # EXP-9: Track B.Cu escape vias

        # First pass: identify fine-pitch components and collect their nets
        fine_pitch_refs = set()
        fine_pitch_nets = set()  # Nets that touch fine-pitch components

        for component in state.netlist.components:
            min_pitch = self._calculate_min_pin_pitch(component)
            if min_pitch is not None and min_pitch < self.pin_pitch_threshold_mm:
                fine_pitch_refs.add(component.ref)
                fine_pitch_components.append((component.ref, min_pitch, len(component.pins)))
                # Collect all nets that touch this fine-pitch component
                for pin in component.pins:
                    if pin.net:
                        fine_pitch_nets.add(pin.net)

        # Track positions where we've placed vias to avoid duplicates
        via_positions = set()

        # Second pass: place escape vias for ALL pins on nets that touch fine-pitch components
        # This ensures both endpoints of a net can route on inner layers
        for component in state.netlist.components:
            comp_pos = placements.get(component.ref, component.initial_position)
            if comp_pos is None:
                continue

            for pin in component.pins:
                if not pin.net:
                    continue  # Skip NC pins

                # Place escape via if:
                # 1. This component is fine-pitch, OR
                # 2. This pin's net touches a fine-pitch component
                if component.ref not in fine_pitch_refs and pin.net not in fine_pitch_nets:
                    continue

                # Calculate absolute pin position
                pin_x, pin_y = pin_world_position_at(pin, component, comp_pos)

                # Skip if we already have a via at this position
                pos_key = (round(pin_x, 3), round(pin_y, 3))
                if pos_key in via_positions:
                    continue
                via_positions.add(pos_key)

                # EXP-6b: Determine escape layer based on net
                escape_layer_num, escape_layer_name = self._get_escape_layer_for_net(pin.net)

                # Create escape via (F.Cu to selected escape layer)
                via = Via(
                    position=(pin_x, pin_y),
                    drill=self.via_drill_mm,
                    width=self.via_diameter_mm,
                    layers=("F.Cu", escape_layer_name),
                    net=pin.net,
                )
                vias.append(via)

                if escape_layer_num == 1:
                    layer1_vias += 1
                elif escape_layer_num == 2:
                    layer2_vias += 1
                else:  # layer 3 (B.Cu)
                    layer3_vias += 1

        # Debug output
        if fine_pitch_components:
            print(f"  Fine-pitch components detected: {len(fine_pitch_components)}")
            for ref, pitch, pin_count in fine_pitch_components:
                # Count netted pins correctly
                comp = next((c for c in state.netlist.components if c.ref == ref), None)
                if comp:
                    netted_pins = sum(1 for pin in comp.pins if pin.net)
                    print(
                        f"    {ref}: min_pitch={pitch:.2f}mm, {netted_pins}/{pin_count} pins with nets"
                    )
            print(f"  Nets touching fine-pitch components: {len(fine_pitch_nets)}")
            # EXP-6b/EXP-9: Show layer distribution
            print(
                f"  Escape vias: {layer1_vias} to In1.Cu, {layer2_vias} to In2.Cu, {layer3_vias} to B.Cu"
            )
            if self.layer2_nets:
                print(f"  Layer 2 nets: {sorted(self.layer2_nets)}")
            if self.layer3_nets:
                print(f"  Layer 3 (B.Cu) nets: {sorted(self.layer3_nets)}")
        else:
            print(
                f"  No fine-pitch components detected (threshold: {self.pin_pitch_threshold_mm}mm)"
            )

        # ========== PHASE 5: ESCAPE VALIDATION ==========
        # Validate that ALL fine-pitch component pins have escape vias.
        # Auto-generate any missing escapes.

        if fine_pitch_refs:
            missing_escapes = []
            current_via_positions = {
                (round(v.position[0], 3), round(v.position[1], 3)) for v in vias
            }

            for component in state.netlist.components:
                if component.ref not in fine_pitch_refs:
                    continue

                comp_pos = placements.get(component.ref, component.initial_position)
                if comp_pos is None:
                    continue

                for pin in component.pins:
                    if not pin.net:
                        continue  # Skip NC pins

                    # Calculate absolute pin position
                    pin_x, pin_y = pin_world_position_at(pin, component, comp_pos)

                    # Check if escape via exists within tolerance
                    pos_key = (round(pin_x, 3), round(pin_y, 3))
                    if pos_key not in current_via_positions:
                        missing_escapes.append(
                            {
                                "ref": component.ref,
                                "pin": pin.name,
                                "net": pin.net,
                                "pos": (pin_x, pin_y),
                            }
                        )

            if missing_escapes:
                print(
                    f"\n  [EscapeValidation] Found {len(missing_escapes)} fine-pitch pins missing escape vias"
                )

                # Group by net for clearer output
                by_net: dict[str, list[dict]] = {}
                for m in missing_escapes:
                    net = m["net"]
                    if net not in by_net:
                        by_net[net] = []  # type: ignore[index]
                    by_net[net].append(m)  # type: ignore[index]

                for net, pins_list in sorted(by_net.items(), key=lambda x: -len(x[1]))[:10]:
                    pin_list = ", ".join(f"{p['ref']}.{p['pin']}" for p in pins_list[:3])
                    if len(pins_list) > 3:
                        pin_list += f" (+{len(pins_list) - 3} more)"
                    print(f"    {net}: {pin_list}")

                # Auto-generate missing escapes
                print(
                    f"\n  [EscapeValidation] Auto-generating {len(missing_escapes)} missing escape vias..."
                )

                generated_count = 0
                for m in missing_escapes:
                    pin_pos = m["pos"]
                    net_name = m["net"]

                    # Skip if position already has a via (shouldn't happen but safety check)
                    pos_key = (round(pin_pos[0], 3), round(pin_pos[1], 3))  # type: ignore[call-overload]
                    if pos_key in current_via_positions:
                        continue

                    # Determine escape layer
                    escape_layer_num, escape_layer_name = self._get_escape_layer_for_net(net_name)  # type: ignore[arg-type]

                    via = Via(
                        position=pin_pos,  # type: ignore[arg-type]
                        drill=self.via_drill_mm,
                        width=self.via_diameter_mm,
                        layers=("F.Cu", escape_layer_name),
                        net=net_name,  # type: ignore[arg-type]
                    )
                    vias.append(via)
                    current_via_positions.add(pos_key)
                    generated_count += 1

                    if escape_layer_num == 1:
                        layer1_vias += 1
                    elif escape_layer_num == 2:
                        layer2_vias += 1
                    elif escape_layer_num == 3:
                        layer3_vias += 1

                print(f"    Added {generated_count} escape vias")
                print(
                    f"  Updated totals: {layer1_vias} to In1.Cu, {layer2_vias} to In2.Cu, {layer3_vias} to B.Cu"
                )

        # ========== END PHASE 5 ==========

        return replace(state, vias=frozenset(vias))

    def _calculate_min_pin_pitch(self, component):
        """Calculate minimum pin-to-pin distance for a component.

        Args:
            component: Component to analyze

        Returns:
            Minimum distance between any two pins in mm, or None if < 2 pins
        """
        return _tdb.deterministic_leaves.min_pin_pitch_py(component.pins)
