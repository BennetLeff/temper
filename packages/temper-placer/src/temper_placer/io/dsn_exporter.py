from __future__ import annotations

import re

import jax.numpy as jnp
from typing import TYPE_CHECKING, Sequence, Union

from temper_placer.io.dsn import dsn_list
from temper_placer.core.pin_geometry import pin_world_position

if TYPE_CHECKING:
    from jax import Array
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.dsn import DSNExpression
    from temper_placer.io.kicad_parser import TraceData


def _natural_sort_key(s: str) -> list:
    """Sort key that ensures natural numeric ordering (e.g., 'pin10' > 'pin2')."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", s)]


class DSNExporter:
    """Exporter for KiCad PCB to SPECCTRA DSN format."""

    def __init__(
        self,
        board: Board,
        netlist: Netlist,
        positions: Array | None = None,
        rotations: Array | None = None,
        deterministic: bool = True,
    ):
        self.board = board
        self.netlist = netlist
        self.positions = positions
        self.deterministic = deterministic

        # Convert rotations to indices (0-3) if provided as logits/one-hot
        if rotations is not None:
            if rotations.ndim == 2:
                self.rotation_indices = jnp.argmax(rotations, axis=1)
            else:
                self.rotation_indices = rotations
        else:
            self.rotation_indices = None

        # Precompute bounding box center offsets for each component
        # This accounts for asymmetric pin layouts (e.g., connectors)
        self._center_offsets = self._compute_center_offsets()

    def _compute_center_offsets(self) -> list[tuple[float, float]]:
        """Compute the offset from footprint origin to bounding box center for each component.

        For components with asymmetric pin layouts (like connectors with pins at 0,10,20mm),
        the bounding box center differs from the footprint origin. This offset is used to:
        1. Center pins in the DSN image around (0,0)
        2. Adjust placement positions to be bounding box centers
        """
        offsets = []
        for comp in self.netlist.components:
            if not comp.pins:
                offsets.append((0.0, 0.0))
                continue

            # Find bounding box of all pins (including pad sizes)
            min_x = float('inf')
            max_x = float('-inf')
            min_y = float('inf')
            max_y = float('-inf')

            for pin in comp.pins:
                px, py = pin.position
                half_w, half_h = pin.width / 2, pin.height / 2
                min_x = min(min_x, px - half_w)
                max_x = max(max_x, px + half_w)
                min_y = min(min_y, py - half_h)
                max_y = max(max_y, py + half_h)

            # Center offset = center of bounding box relative to footprint origin
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            offsets.append((center_x, center_y))

        return offsets

    def export_structure(self, all_layers_signal: bool = True) -> DSNExpression:
        """Export the structure section (layers, boundaries, keepouts).

        Args:
            all_layers_signal: If True, all layers are marked as 'signal' type to allow
                autorouting on all layers. If False, uses original layer types (which may
                restrict routing on power/plane layers).
        """
        layer_exprs = []
        layer_names = []
        if self.board.layer_stackup:
            for i, layer in enumerate(self.board.layer_stackup.layers):
                # For autorouting, we want all layers to be 'signal' type
                # so the router can use them for signal traces
                if all_layers_signal:
                    ltype = "signal"
                else:
                    ltype = "signal" if layer.layer_type == "signal" else "power"
                layer_names.append(layer.name)
                layer_exprs.append(
                    dsn_list(
                        "layer",
                        layer.name,
                        dsn_list("type", ltype),
                        dsn_list("property", dsn_list("index", i)),
                    )
                )
        else:
            layer_names = ["F.Cu", "B.Cu"]
            layer_exprs.append(
                dsn_list("layer", "F.Cu", dsn_list("type", "signal"), dsn_list("property", dsn_list("index", 0)))
            )
            layer_exprs.append(
                dsn_list("layer", "B.Cu", dsn_list("type", "signal"), dsn_list("property", dsn_list("index", 1)))
            )

        # Scale factor for 'um 10' resolution (1 unit = 10um)
        # 1mm = 100 units
        S = 100.0

        # Boundary as a rect is preferred for the 'pcb' layer
        boundary = dsn_list(
            "boundary",
            dsn_list("rect", "pcb", 0, 0, round(self.board.width * S), round(self.board.height * S))
        )

        # Keepouts
        keepout_layer = layer_names[0] if layer_names else "F.Cu"
        keepout_exprs = []
        for i, ko in enumerate(self.board.keepouts):
            keepout_exprs.append(
                dsn_list("keepout", f"KO_{i}", dsn_list("rect", keepout_layer, round(ko[0] * S), round(ko[1] * S), round(ko[2] * S), round(ko[3] * S)))
            )
        if self.deterministic:
            keepout_exprs.sort(key=lambda k: str(k.args[0]) if k.args else "")
        
        # Vias
        via_exprs = [dsn_list("via", "VIA")]

        # Rules: slightly smaller width (0.13mm) to clear dense QFN fanouts
        rules = dsn_list(
            "rule",
            dsn_list("width", 13),
            dsn_list("clearance", 12)
        )

        return dsn_list("structure", *layer_exprs, boundary, *keepout_exprs, *via_exprs, rules)

    def _natural_sort_key(self, s: str) -> tuple:
        """Natural sort key: splits into text and number parts for sorting."""
        import re
        parts = re.split(r"(\d+)", s)
        result = []
        for p in parts:
            result.append(int(p) if p.isdigit() else p.lower())
        return tuple(result)

    def export_library(self) -> DSNExpression:
        """Export the library section (footprints and padstacks)."""
        images = []
        padstacks = {}
        S = 100.0  # Scale factor

        # Determine layers for padstacks
        layer_names = ["F.Cu", "B.Cu"]
        if self.board.layer_stackup:
            layer_names = [l.name for l in self.board.layer_stackup.layers]

        # Add VIA padstack (0.6mm diameter) on all layers
        via_shapes = [dsn_list("shape", dsn_list("circle", ln, 0.6 * S)) for ln in layer_names]
        padstacks["VIA"] = dsn_list("padstack", "VIA", *via_shapes)

        for i, comp in enumerate(self.netlist.components):
            # Get the center offset for this component (to center pins around origin)
            center_offset_x, center_offset_y = self._center_offsets[i]

            # 1. Create padstacks for unique pad shapes/sizes
            for pin in comp.pins:
                # Use actual pad size from Pin object
                pad_width, pad_height = pin.width, pin.height
                # Normalize shape name
                shape_name = pin.shape if pin.shape else "rect"
                if shape_name == "thru_hole":
                    shape_name = "circle"  # TODO: Handle drill sizes

                # Sanitize name: remove dots and add layer context
                layer_suffix = f"_{pin.layer.replace('.', '_')}" if pin.layer != "all" else "_ALL"
                dims_str = f"{pad_width:.3f}x{pad_height:.3f}".replace(".", "_")
                ps_name = f"PS_{shape_name.upper()}_{dims_str}{layer_suffix}"

                if ps_name not in padstacks:
                    x1, y1 = -pad_width / 2 * S, -pad_height / 2 * S
                    x2, y2 = pad_width / 2 * S, pad_height / 2 * S

                    shapes = []
                    layers_to_add = layer_names if pin.layer == "all" else [pin.layer]
                    for layer in layers_to_add:
                        if shape_name == "circle":
                            shapes.append(dsn_list("shape", dsn_list("circle", layer, pad_width * S)))
                        else:
                            shapes.append(dsn_list("shape", dsn_list("rect", layer, x1, y1, x2, y2)))

                    padstacks[ps_name] = dsn_list("padstack", ps_name, *shapes)

            # 2. Create image (footprint) - unique per component instance for proper centering
            # Use component ref to make image ID unique (allows per-instance pin centering)
            fp_id = f"{comp.footprint.replace(':', '_').replace('/', '_')}_{comp.ref}"

            pins = []
            for pin in comp.pins:
                # Reconstruct Sanitized PS name
                p_shape = pin.shape if pin.shape else "rect"
                if p_shape == "thru_hole":
                    p_shape = "circle"
                layer_suffix = f"_{pin.layer.replace('.', '_')}" if pin.layer != "all" else "_ALL"
                dims_str = f"{pin.width:.3f}x{pin.height:.3f}".replace(".", "_")
                ps_name = f"PS_{p_shape.upper()}_{dims_str}{layer_suffix}"

                # Center pins around (0,0) by subtracting the bounding box center offset
                # This ensures placement position represents the actual center of the component
                centered_x = pin.position[0] - center_offset_x
                centered_y = pin.position[1] - center_offset_y

                # pin format in image: (pin <padstack_id> <pin_id> <x> <y>)
                pins.append(
                    dsn_list(
                        "pin",
                        ps_name,
                        pin.number,
                        round(centered_x * S),
                        round(centered_y * S),
                    )
                )

            # Sort pins by pin number for deterministic output
            if self.deterministic:
                pins.sort(key=lambda p: self._natural_sort_key(str(p.args[2])))

            # For footprints without pins (like mounting holes), add a small keepout
            # to ensure the router doesn't treat them as empty space.
            if not pins:
                # Add a 1mm x 1mm keepout at origin as an 'outline'
                pins.append(dsn_list("outline", dsn_list("rect", layer_names[0], -0.5 * S, -0.5 * S, 0.5 * S, 0.5 * S)))

            # Sort pins by pin number for deterministic output
            if self.deterministic:
                pins.sort(key=lambda p: _natural_sort_key(str(p.args[1])) if len(p.args) > 1 else "0")
            images.append(dsn_list("image", fp_id, *pins))

        # Sort images by fp_id for deterministic output
        if self.deterministic:
            images.sort(key=lambda img: str(img.args[0]).lower())

        # Sort padstack values by padstack name for deterministic output
        ps_values = list(padstacks.values())
        if self.deterministic:
            ps_values.sort(key=lambda ps: str(ps.args[0]).lower())

        return dsn_list("library", *images, *ps_values)

    def export_placement(self) -> DSNExpression:
        """Export the placement section (component instances)."""
        components_by_fp = {}
        S = 100.0  # Scale factor

        for i, comp in enumerate(self.netlist.components):
            # Use component ref to match unique image ID from export_library()
            fp_id = f"{comp.footprint.replace(':', '_').replace('/', '_')}_{comp.ref}"
            if fp_id not in components_by_fp:
                components_by_fp[fp_id] = []

            # Get position and rotation
            if self.positions is not None:
                x, y = float(self.positions[i, 0]), float(self.positions[i, 1])
            else:
                x, y = comp.initial_position or (0.0, 0.0)

            # Add center offset to convert from footprint origin to bounding box center
            # This compensates for the centered pins in the image definition
            center_offset_x, center_offset_y = self._center_offsets[i]
            x += center_offset_x
            y += center_offset_y

            if self.rotation_indices is not None:
                rot = int(self.rotation_indices[i]) * 90
            else:
                rot = (comp.initial_rotation or 0) * 90
            
            # Determine side from first pin
            side = "front"
            if comp.pins and comp.pins[0].layer == "B.Cu":
                side = "back"

            # (place <ref> x y [front | back] <rotation>)
            components_by_fp[fp_id].append(
                dsn_list("place", comp.ref, x * S, y * S, side, float(rot))
            )

        comp_exprs = []
        if self.deterministic:
            sorted_fp_ids = sorted(components_by_fp.keys(), key=lambda k: k.lower())
            for fp_id in sorted_fp_ids:
                instances = components_by_fp[fp_id]
                instances.sort(key=lambda inst: str(inst.args[0]).lower())
                comp_exprs.append(dsn_list("component", fp_id, *instances))
            comp_exprs.sort(key=lambda c: str(c.args[0]).lower())
        else:
            for fp_id, instances in components_by_fp.items():
                comp_exprs.append(dsn_list("component", fp_id, *instances))

        return dsn_list("placement", *comp_exprs)

    def _compute_net_span(self, net) -> float:
        """Compute HPWL span of a net based on pin positions.

        Used for net ordering - shorter nets are easier to route first.
        """
        if len(net.pins) < 2:
            return 0.0

        xs, ys = [], []
        for comp_ref, pin_num in net.pins:
            try:
                comp_idx = self.netlist.get_component_index(comp_ref)
                comp = self.netlist.components[comp_idx]
                # Find pin position
                for pin in comp.pins:
                    if pin.number == pin_num:
                        # Use initial position + pin offset
                        if self.positions is not None:
                            base_x = float(self.positions[comp_idx, 0])
                            base_y = float(self.positions[comp_idx, 1])
                        else:
                            pos = comp.initial_position or (0.0, 0.0)
                            base_x, base_y = pos
                        wx, wy = pin_world_position(pin, comp)
                        xs.append(wx)
                        ys.append(wy)
                        break
            except (KeyError, IndexError):
                continue

        if len(xs) < 2:
            return 0.0
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    def export_network(
        self,
        use_net_classes: bool = True,
        exclude_nets: set[str] | None = None,
    ) -> DSNExpression:
        """Export the network section (nets, pins, and net classes).

        Args:
            use_net_classes: Whether to add net class definitions for power/signal routing.
            exclude_nets: Set of net names to exclude from routing (e.g., plane-connected nets).
        """
        net_exprs = []
        power_nets = []
        signal_nets = []
        excluded_count = 0

        # Known power/ground net patterns - use start/end anchors to avoid false matches
        # These are common power rail naming conventions
        power_prefixes = ["GND", "PGND", "CGND", "VCC", "VDD", "DC_BUS", "_PLUS"]
        # Voltage rail suffixes (3V3, 5V, etc.) - must be preceded by a voltage indicator
        import re
        voltage_pattern = re.compile(r"(_PLUS|VCC|VDD)\d+V?\d*$", re.IGNORECASE)

        # Sort nets: deterministic mode sorts alphabetically by sanitized name;
        # non-deterministic sorts by fanout (low first) then span (short first)
        # for better FreeRouter routing quality.
        if self.deterministic:
            sorted_nets = sorted(
                self.netlist.nets,
                key=lambda n: n.name.replace("+", "_PLUS").replace("-", "_MINUS").lower()
            )
        else:
            sorted_nets = sorted(
                self.netlist.nets,
                key=lambda n: (len(n.pins), self._compute_net_span(n))
            )

        for net in sorted_nets:
            # Sanitize net names for SPECCTRA compatibility
            clean_name = net.name.replace("+", "_PLUS").replace("-", "_MINUS")
            
            # Skip nets that are connected via power planes
            # Check both original name and sanitized name for exclusion
            if exclude_nets and (net.name in exclude_nets or clean_name in exclude_nets):
                excluded_count += 1
                continue
            pin_refs = []
            for comp_ref, pin_num in net.pins:
                pin_refs.append(f"{comp_ref}-{pin_num}")


            if pin_refs:
                net_exprs.append(dsn_list("net", clean_name, dsn_list("pins", *pin_refs)))

                # Classify net as power or signal using more precise matching
                upper_name = clean_name.upper()
                is_power = (
                    any(upper_name.startswith(prefix) for prefix in power_prefixes) or
                    bool(voltage_pattern.search(clean_name))
                )
                if is_power:
                    power_nets.append(clean_name)
                else:
                    signal_nets.append(clean_name)

        # Add net classes for better routing
        if use_net_classes and (power_nets or signal_nets):
            class_exprs = []

            # Determine layer names for routing preferences
            # layer_type is "signal", "plane", or "mixed" in the board model
            layer_names = ["F.Cu", "B.Cu"]
            inner_layers = []  # power/plane layers
            outer_layers = []  # signal layers
            if self.board.layer_stackup:
                layer_names = [l.name for l in self.board.layer_stackup.layers]
                for l in self.board.layer_stackup.layers:
                    if l.layer_type in ("plane", "mixed"):
                        inner_layers.append(l.name)
                    else:
                        outer_layers.append(l.name)
            else:
                outer_layers = ["F.Cu", "B.Cu"]

            # Power net class - prefer inner layers, wider traces
            if power_nets:
                power_class_items = [
                    "class",
                    "power",
                    *power_nets,
                    dsn_list("circuit", dsn_list("use_via", "VIA")),
                    dsn_list("rule", dsn_list("width", 25), dsn_list("clearance", 20)),
                ]
                # Allow power nets on all layers. Restricting to inner layers causes failures
                # when planes are split or components are isolated (e.g. J_AC_IN in HV zone).
                # We include all layers to ensure routability.
                all_layers = outer_layers + inner_layers
                if all_layers:
                    power_class_items.append(dsn_list("use_layer", *all_layers))
                class_exprs.append(dsn_list(*power_class_items))

            # Signal net class - prefer outer layers, standard traces
            if signal_nets:
                signal_class_items = [
                    "class",
                    "signal",
                    *signal_nets,
                    dsn_list("circuit", dsn_list("use_via", "VIA")),
                    dsn_list("rule", dsn_list("width", 13), dsn_list("clearance", 12)),
                ]
                # Add layer preference for outer (signal) layers if available
                if outer_layers:
                    signal_class_items.append(dsn_list("use_layer", *outer_layers))
                class_exprs.append(dsn_list(*signal_class_items))

            return dsn_list("network", *net_exprs, *class_exprs)

        return dsn_list("network", *net_exprs)

    def export_wiring(self, traces: list[TraceData]) -> DSNExpression:
        """Export the wiring section (existing traces)."""
        wire_exprs = []
        for trace in traces:
            # (wire (path <layer> <width> <x1> <y1> <x2> <y2>))
            wire_exprs.append(
                dsn_list(
                    "wire",
                    dsn_list("path", trace.layer, trace.width, trace.start[0], trace.start[1], trace.end[0], trace.end[1])
                )
            )
        return dsn_list("wiring", *wire_exprs)

    def export_pcb(
        self,
        pcb_name: str = "temper",
        traces: list[TraceData] | None = None,
        exclude_nets: set[str] | None = None,
    ) -> DSNExpression:
        """Export the full PCB design.

        Args:
            pcb_name: Name for the PCB in the DSN file.
            traces: Existing traces to include in the wiring section.
            exclude_nets: Set of net names to exclude from routing (plane-connected nets).
        """
        sections = [
            dsn_list("parser", dsn_list("string_quote", '"'), dsn_list("space_in_quoted_tokens", "on")),
            dsn_list("resolution", "um", 10),
            dsn_list("unit", "mm"),
            self.export_structure(),
            self.export_library(),
            self.export_placement(),
            self.export_network(exclude_nets=exclude_nets),
        ]

        if traces:
            sections.append(self.export_wiring(traces))

        pcb_expr = dsn_list("pcb", pcb_name, *sections)

        if self.deterministic:
            from temper_placer.io.dsn_schema import DSNSchemaHasher
            schema_hash = DSNSchemaHasher.compute_schema_hash(self.board, self.netlist)
            pcb_expr = pcb_expr.with_comment(f"schema-version: sha256:{schema_hash}")

        return pcb_expr
