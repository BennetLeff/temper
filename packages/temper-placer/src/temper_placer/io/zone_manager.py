"""
Zone manager for KiCad copper pour generation.

kiutils-free (Wave 4 Phase 3, formats/IO): board I/O goes through the
Rust parse engine's text path — ``extract_board_outline_py`` /
``extract_net_map_from_text_py`` / ``extract_copper_layer_names_py``
read board data, ``power_plane_zone_sexpr_py`` constructs each zone's
s-expression (mirroring the pre-migration kiutils ``Zone``
construction field-for-field, including thermal reliefs), and
``append_items_to_board_py`` inserts zones into the KiNode tree and
serializes back to text. No kiutils ``Board`` / ``Zone`` /
``ZonePolygon`` / ``FillSettings`` objects are created.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
from temper_io_types import kicad_write_geometry as _GEOM


@dataclass
class PlaneConfig:
    """Configuration for a power plane zone."""

    layer: str
    net_name: str
    priority: int = 0
    min_thickness: float = 0.25
    clearance: float = 0.3
    thermal_gap: float = 0.5
    thermal_bridge_width: float = 0.5


@dataclass
class ZoneResult:
    """Result of zone generation."""

    zones_added: int
    nets_covered: list[str]
    layers_used: list[str]
    warnings: list[str] = field(default_factory=list)


def get_board_outline_from_text(content: str) -> list[tuple[float, float]]:
    """Extract board outline as polygon coordinates from raw board text.

    Returns Edge.Cuts line-segment endpoints, deduplicated and sorted
    by angle from centroid for proper polygon ordering.
    """
    lines = _tdb.parse_engine.extract_board_outline_py(content)

    outline_points: list[tuple[float, float]] = []
    for sx, sy, ex, ey in lines:
        outline_points.append((sx, sy))
        outline_points.append((ex, ey))

    if not outline_points:
        return [(0.0, 0.0), (100.0, 0.0), (100.0, 130.0), (0.0, 130.0)]

    seen: set[tuple[float, float]] = set()
    unique_points: list[tuple[float, float]] = []
    for point in outline_points:
        if point not in seen:
            seen.add(point)
            unique_points.append(point)
    if len(unique_points) < 3:
        return [(0.0, 0.0), (100.0, 0.0), (100.0, 130.0), (0.0, 130.0)]

    cx = sum(p[0] for p in unique_points) / len(unique_points)
    cy = sum(p[1] for p in unique_points) / len(unique_points)
    sorted_points = sorted(unique_points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))

    return sorted_points


def get_net_code_from_map(net_map: dict[str, int], net_name: str) -> int:
    """Get net code for a net name from a net name→index map."""
    return net_map.get(net_name, 0)


def create_zone_sexpr(
    net_index: int,
    config: PlaneConfig,
    outline: list[tuple[float, float]],
) -> list:
    """Create a copper pour zone s-expression for a power plane.

    Delegates to the Rust kernel ``power_plane_zone_sexpr_py``, which
    mirrors the pre-migration kiutils Zone construction field-for-field:
    thermal reliefs (connect_pads thermal_reliefs), config clearance,
    min_thickness, fill settings with thermal_gap/thermal_bridge_width,
    priority, and the ``<net>_plane`` name.
    """
    return _GEOM.power_plane_zone_sexpr_py(
        config.net_name,
        net_index,
        config.layer,
        config.priority,
        config.clearance,
        config.min_thickness,
        config.thermal_gap,
        config.thermal_bridge_width,
        outline,
    )


def _validate_4_layer_output_text(content: str) -> None:
    """Text-path port of ``kicad_exporter._validate_4_layer_output``.

    Warns instead of raising for boards with differing layer counts — the
    canonical 4-layer stackup is the production target, but non-production
    boards (test fixtures, 2-layer prototypes) are valid output.
    """
    import logging

    from temper_placer.core.board import CANONICAL_4LAYER_LAYER_NAMES

    logger = logging.getLogger(__name__)

    copper_names = _tdb.parse_engine.extract_copper_layer_names_py(content)
    if len(copper_names) != 4:
        logger.warning(
            "Board has %d copper layers (canonical 4-layer stackup: %s). "
            "Proceeding — non-4-layer boards are valid for test fixtures and prototypes.",
            len(copper_names),
            sorted(CANONICAL_4LAYER_LAYER_NAMES),
        )
        return
    name_set = set(copper_names)
    if name_set != set(CANONICAL_4LAYER_LAYER_NAMES):
        raise RuntimeError(
            f"Copper layer names must match canonical set {sorted(CANONICAL_4LAYER_LAYER_NAMES)}, "
            f"got {sorted(name_set)}"
        )


def add_power_planes_to_text(
    content: str,
    gnd_nets: Sequence[str] = ("GND",),
    vcc_nets: Sequence[str] = ("+15V", "+5V", "+3V3", "VCC"),
    gnd_layer: str = "In1.Cu",
    vcc_layer: str = "In2.Cu",
) -> tuple[str, ZoneResult]:
    """Add power plane zones to raw board text.

    Creates copper pour zones on inner layers for power distribution.
    Returns (new_text, ZoneResult).
    """
    outline = get_board_outline_from_text(content)
    net_map = _tdb.parse_engine.extract_net_map_from_text_py(content)
    warnings: list[str] = []
    zones_added = 0
    nets_covered: list[str] = []
    layers_used: list[str] = []
    item_sexprs: list = []

    primary_gnd = None
    for net_name in gnd_nets:
        if get_net_code_from_map(net_map, net_name) != 0:
            primary_gnd = net_name
            break

    if primary_gnd:
        config = PlaneConfig(
            layer=gnd_layer,
            net_name=primary_gnd,
            priority=0,
            clearance=0.3,
            thermal_gap=0.5,
            thermal_bridge_width=0.5,
        )
        item_sexprs.append(
            create_zone_sexpr(
                get_net_code_from_map(net_map, config.net_name),
                config,
                outline,
            )
        )
        zones_added += 1
        nets_covered.append(primary_gnd)
        if gnd_layer not in layers_used:
            layers_used.append(gnd_layer)
    else:
        warnings.append("No GND nets found, skipping GND plane")

    primary_vcc = None
    for net_name in vcc_nets:
        if get_net_code_from_map(net_map, net_name) != 0:
            primary_vcc = net_name
            break

    if primary_vcc:
        config = PlaneConfig(
            layer=vcc_layer,
            net_name=primary_vcc,
            priority=0,
            clearance=0.3,
            thermal_gap=0.5,
            thermal_bridge_width=0.5,
        )
        item_sexprs.append(
            create_zone_sexpr(
                get_net_code_from_map(net_map, config.net_name),
                config,
                outline,
            )
        )
        zones_added += 1
        nets_covered.append(primary_vcc)
        if vcc_layer not in layers_used:
            layers_used.append(vcc_layer)
    else:
        warnings.append("No VCC nets found, skipping VCC plane")

    new_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)

    return new_text, ZoneResult(
        zones_added=zones_added,
        nets_covered=nets_covered,
        layers_used=layers_used,
        warnings=warnings,
    )


def add_zones_to_pcb(
    input_pcb: Path,
    output_pcb: Path,
    gnd_nets: Sequence[str] = ("GND",),
    vcc_nets: Sequence[str] = ("+15V", "+5V", "+3V3", "VCC"),
) -> ZoneResult:
    """Add power plane zones to a PCB file."""
    content = Path(input_pcb).read_text(encoding="utf-8")
    new_text, result = add_power_planes_to_text(content, gnd_nets, vcc_nets)
    _validate_4_layer_output_text(new_text)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(new_text, encoding="utf-8")
    return result


def add_zones_from_classification(
    input_pcb: Path,
    output_pcb: Path,
    net_classification: "NetClassification",
) -> ZoneResult:
    """Add copper zones based on NetClassification type system."""
    from temper_placer.core.net_types import ConnectivityStrategy

    content = Path(input_pcb).read_text(encoding="utf-8")
    outline = get_board_outline_from_text(content)
    net_map = _tdb.parse_engine.extract_net_map_from_text_py(content)

    warnings: list[str] = []
    zones_added = 0
    nets_covered: list[str] = []
    layers_used: list[str] = []
    item_sexprs: list = []

    layer_to_nets: dict[str, list[tuple[str, NetTypeSpec]]] = {}

    for net_name, spec in net_classification.specs.items():
        if spec.connectivity == ConnectivityStrategy.PLANE:
            layer = spec.target_layer
            if layer not in layer_to_nets:
                layer_to_nets[layer] = []
            layer_to_nets[layer].append((net_name, spec))

    for pattern in net_classification.ground_patterns:
        if pattern not in net_classification.specs:
            spec = net_classification.classify_net(pattern)
            if spec.connectivity == ConnectivityStrategy.PLANE:
                layer = spec.target_layer
                if layer not in layer_to_nets:
                    layer_to_nets[layer] = []
                if get_net_code_from_map(net_map, pattern) != 0:
                    layer_to_nets[layer].append((pattern, spec))

    priority_map = {"In1.Cu": 0, "In2.Cu": 1, "F.Cu": 2, "B.Cu": 2}

    for layer, net_specs in layer_to_nets.items():
        for net_name, spec in net_specs:
            if get_net_code_from_map(net_map, net_name) != 0:
                config = PlaneConfig(
                    layer=layer,
                    net_name=net_name,
                    priority=priority_map.get(layer, 1),
                    clearance=spec.clearance_mm,
                    min_thickness=0.25,
                )
                item_sexprs.append(
                    create_zone_sexpr(
                        get_net_code_from_map(net_map, net_name),
                        config,
                        outline,
                    )
                )
                zones_added += 1
                nets_covered.append(net_name)
                if layer not in layers_used:
                    layers_used.append(layer)
                break
        else:
            warnings.append(f"No valid nets found for layer {layer}")

    new_text = _tdb.parse_engine.append_items_to_board_py(content, item_sexprs)
    _validate_4_layer_output_text(new_text)
    output_pcb.parent.mkdir(parents=True, exist_ok=True)
    output_pcb.write_text(new_text, encoding="utf-8")

    return ZoneResult(
        zones_added=zones_added,
        nets_covered=nets_covered,
        layers_used=layers_used,
        warnings=warnings,
    )


if TYPE_CHECKING:
    from temper_placer.core.net_types import NetClassification, NetTypeSpec
