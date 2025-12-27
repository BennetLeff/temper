from __future__ import annotations

import jax.numpy as jnp
from typing import TYPE_CHECKING, Sequence, Union

from temper_placer.io.dsn import dsn_list

if TYPE_CHECKING:
    from jax import Array
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.dsn import DSNExpression
    from temper_placer.io.kicad_parser import TraceData


class DSNExporter:
    """Exporter for KiCad PCB to SPECCTRA DSN format."""

    def __init__(
        self,
        board: Board,
        netlist: Netlist,
        positions: Array | None = None,
        rotations: Array | None = None,
    ):
        self.board = board
        self.netlist = netlist
        self.positions = positions
        
        # Convert rotations to indices (0-3) if provided as logits/one-hot
        if rotations is not None:
            if rotations.ndim == 2:
                self.rotation_indices = jnp.argmax(rotations, axis=1)
            else:
                self.rotation_indices = rotations
        else:
            self.rotation_indices = None

    def export_structure(self) -> DSNExpression:
        """Export the structure section (layers, boundaries, keepouts)."""
        layer_exprs = []
        layer_names = []
        if self.board.layer_stackup:
            for i, layer in enumerate(self.board.layer_stackup.layers):
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
        
        # Vias
        via_exprs = [dsn_list("via", "VIA")]

        # Rules: slightly smaller width (0.13mm) to clear dense QFN fanouts
        rules = dsn_list(
            "rule",
            dsn_list("width", 13),
            dsn_list("clearance", 12)
        )

        return dsn_list("structure", *layer_exprs, boundary, *keepout_exprs, *via_exprs, rules)

    def export_library(self) -> DSNExpression:
        """Export the library section (footprints and padstacks)."""
        images = []
        padstacks = {}
        S = 100.0 # Scale factor
        
        # Determine layers for padstacks
        layer_names = ["F.Cu", "B.Cu"]
        if self.board.layer_stackup:
            layer_names = [l.name for l in self.board.layer_stackup.layers]

        # Add VIA padstack (0.6mm diameter) on all layers
        via_shapes = [dsn_list("shape", dsn_list("circle", ln, 0.6 * S)) for ln in layer_names]
        padstacks["VIA"] = dsn_list("padstack", "VIA", *via_shapes)

        for comp in self.netlist.components:
            # 1. Create padstacks for unique pad shapes/sizes
            for pin in comp.pins:
                # Use actual pad size from Pin object
                pad_width, pad_height = pin.width, pin.height
                # Normalize shape name
                shape_name = pin.shape if pin.shape else "rect"
                if shape_name == "thru_hole":
                    shape_name = "circle" # TODO: Handle drill sizes
                
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

            # 2. Create image (footprint)
            fp_id = comp.footprint.replace(":", "_").replace("/", "_")
            
            pins = []
            for pin in comp.pins:
                # Reconstruct Sanitized PS name
                p_shape = pin.shape if pin.shape else "rect"
                if p_shape == "thru_hole": p_shape = "circle"
                layer_suffix = f"_{pin.layer.replace('.', '_')}" if pin.layer != "all" else "_ALL"
                dims_str = f"{pin.width:.3f}x{pin.height:.3f}".replace(".", "_")
                ps_name = f"PS_{p_shape.upper()}_{dims_str}{layer_suffix}"
                
                # pin format in image: (pin <padstack_id> <pin_id> <x> <y>)
                pins.append(
                    dsn_list(
                        "pin",
                        ps_name,
                        pin.number,
                        round(pin.position[0] * S), 
                        round(pin.position[1] * S)
                    )
                )
            
            # For footprints without pins (like mounting holes), add a small keepout
            # to ensure the router doesn't treat them as empty space.
            if not pins:
                # Add a 1mm x 1mm keepout at origin as an 'outline'
                pins.append(dsn_list("outline", dsn_list("rect", layer_names[0], -0.5*S, -0.5*S, 0.5*S, 0.5*S)))

            images.append(dsn_list("image", fp_id, *pins))

        return dsn_list("library", *images, *padstacks.values())

    def export_placement(self) -> DSNExpression:
        """Export the placement section (component instances)."""
        components_by_fp = {}
        S = 100.0 # Scale factor
        
        for i, comp in enumerate(self.netlist.components):
            fp_id = comp.footprint.replace(":", "_").replace("/", "_")
            if fp_id not in components_by_fp:
                components_by_fp[fp_id] = []
            
            # Get position and rotation
            if self.positions is not None:
                x, y = float(self.positions[i, 0]), float(self.positions[i, 1])
            else:
                x, y = comp.initial_position or (0.0, 0.0)
                
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
        for fp_id, instances in components_by_fp.items():
            comp_exprs.append(dsn_list("component", fp_id, *instances))

        return dsn_list("placement", *comp_exprs)

    def export_network(self) -> DSNExpression:
        """Export the network section (nets and pins)."""
        net_exprs = []
        for net in self.netlist.nets:
            pin_refs = []
            for comp_ref, pin_num in net.pins:
                pin_refs.append(f"{comp_ref}-{pin_num}")
            
            # Sanitize net names for SPECCTRA compatibility
            clean_name = net.name.replace("+", "_PLUS").replace("-", "_MINUS")
            
            if pin_refs:
                net_exprs.append(dsn_list("net", clean_name, dsn_list("pins", *pin_refs)))

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

    def export_pcb(self, pcb_name: str = "temper", traces: list[TraceData] | None = None) -> DSNExpression:
        """Export the full PCB design."""
        sections = [
            dsn_list("parser", dsn_list("string_quote", '"'), dsn_list("space_in_quoted_tokens", "on")),
            dsn_list("resolution", "um", 10),
            dsn_list("unit", "mm"),
            self.export_structure(),
            self.export_library(),
            self.export_placement(),
            self.export_network(),
        ]
        
        if traces:
            sections.append(self.export_wiring(traces))
            
        return dsn_list("pcb", pcb_name, *sections)
