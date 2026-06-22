"""
KiCad PCB parasitic extraction pipeline.

Extracts per-net trace lengths from a KiCad .kicad_pcb S-expression file
and computes hand-calculated parasitics (R_series, L_series, C_shunt)
using conservative derated formulas per the G3 fallback path.

Usage:
    python -m tools.spice.extract pcb/temper_spice_validated.kicad_pcb
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Physical constants
RHO_COPPER = 1.72e-8  # ohm·m at 20°C
COPPER_THICKNESS_1OZ = 0.035e-3  # m (35µm = 1oz)
EPSILON_R_FR4 = 4.5
PCB_THICKNESS_M = 1.6e-3  # m

# Derating multipliers (G3 conservative)
DERATE_L_GATE_DRIVE = 2.0
DERATE_L_BUS = 1.5
DERATE_L_TANK = 1.5
DERATE_R_TEMP = 1.3

# Loop group derating lookup
LOOP_DERATE_L: dict[str, float] = {
    "gate_drive_hs": DERATE_L_GATE_DRIVE,
    "gate_drive_ls": DERATE_L_GATE_DRIVE,
    "dc_bus": DERATE_L_BUS,
    "resonant_tank": DERATE_L_TANK,
    "aux_supply": 1.0,
}


@dataclass
class TraceSegment:
    """A single straight trace segment from a KiCad PCB."""

    start: tuple[float, float]
    end: tuple[float, float]
    width: float  # mm
    layer: str
    net_name: str


@dataclass
class ViaInfo:
    """A via in the PCB."""

    position: tuple[float, float]
    net_name: str


@dataclass
class NetGeometry:
    """Aggregated geometry for one net."""

    name: str
    total_length_mm: float = 0.0
    trace_widths_mm: list[float] = field(default_factory=list)
    segment_count: int = 0
    via_count: int = 0
    layers: set[str] = field(default_factory=set)


@dataclass
class ParasiticValues:
    """Per-net parasitic extraction result."""

    net_name: str
    R_mOhm: float
    L_nH: float
    C_pF: float
    loop_group: str | None = None


@dataclass
class ExtractionResult:
    """Result of parasitic extraction from a KiCad PCB."""

    pcb_file: str
    nets: dict[str, ParasiticValues]
    loop_groups: dict[str, list[str]]
    warnings: list[str] = field(default_factory=list)


def _distance_mm(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two 2D points in mm."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.sqrt(dx * dx + dy * dy)


def _parse_net_map(content: str) -> dict[str, str]:
    """Parse KiCad PCB net declarations into number->name mapping.

    Net declarations look like:
      (net 0 "")
      (net 1 "GND")
      (net 2 "GATE_H")
    """
    net_map: dict[str, str] = {}
    lines = content.split("\n")
    for line in lines:
        m = re.match(r'\(net\s+(\d+)\s+"([^"]*)"\)', line.strip())
        if m:
            net_map[m.group(1)] = m.group(2)
    return net_map


def _resolve_net_name(
    net_num: str, net_map: dict[str, str]
) -> str:
    """Resolve net number to name, falling back to number if unnamed."""
    return net_map.get(net_num, net_num)


def _parse_kicad_sexpr(content: str) -> list[TraceSegment]:
    """Parse KiCad PCB S-expression to extract trace segments.

    KiCad PCB format uses S-expressions.
    Trace segments look like:
      (segment (start x y) (end x y) (width w) (layer "F.Cu") (net N))

    Segments reference nets by number; net names are resolved from the
    net declarations block.
    """
    net_map = _parse_net_map(content)
    segments: list[TraceSegment] = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("(segment "):
            segment_lines = [line]
            depth = line.count("(") - line.count(")")
            while depth > 0 and i + 1 < len(lines):
                i += 1
                segment_lines.append(lines[i].strip())
                depth += lines[i].count("(") - lines[i].count(")")
            i += 1

            seg = _parse_segment_lines(segment_lines, net_map)
            if seg is not None:
                segments.append(seg)
            continue
        i += 1

    return segments


def _parse_segment_lines(
    lines: list[str], net_map: dict[str, str]
) -> TraceSegment | None:
    """Parse a single KiCad segment block from accumulated lines."""
    combined = " ".join(lines)

    def _extract_float(key: str) -> float | None:
        idx = combined.find(key)
        if idx == -1:
            return None
        rest = combined[idx + len(key) :].strip()
        end = rest.find(")")
        if end == -1:
            return None
        return float(rest[:end].strip().split()[-1])

    def _extract_from_pair(key: str) -> float | None:
        """Extract floats from (key x y) pattern."""
        idx = combined.find(f"({key} ")
        if idx == -1:
            return None
        rest = combined[idx + len(key) + 2 :].strip()
        end = rest.find(")")
        if end == -1:
            return None
        parts = rest[:end].strip().split()
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
        return None

    def _extract_net_num() -> str | None:
        """Extract net number from (net N) expression."""
        idx_net = combined.find("(net ")
        if idx_net == -1:
            return None
        rest = combined[idx_net + 5 :].strip()
        end = rest.find(")")
        if end == -1:
            return None
        return rest[:end].strip().split()[0]

    def _extract_layer() -> str | None:
        idx = combined.find("(layer ")
        if idx == -1:
            return None
        rest = combined[idx + 7 :].strip()
        end = rest.find(")")
        if end == -1:
            return None
        layer = rest[:end].strip().strip('"')
        return layer

    start = _extract_from_pair("start")
    end = _extract_from_pair("end")
    width_str = _extract_float("width")
    net_num = _extract_net_num()
    layer = _extract_layer()

    if start is None or end is None or net_num is None:
        return None

    width_mm = float(width_str) if width_str is not None else 0.25
    net_name = _resolve_net_name(net_num, net_map)

    return TraceSegment(
        start=start,
        end=end,
        width=width_mm,
        layer=layer or "unknown",
        net_name=net_name,
    )


def _parse_vias(content: str) -> list[ViaInfo]:
    """Parse vias from KiCad PCB S-expression."""
    net_map = _parse_net_map(content)
    vias: list[ViaInfo] = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("(via "):
            via_lines = [line]
            depth = line.count("(") - line.count(")")
            while depth > 0 and i + 1 < len(lines):
                i += 1
                via_lines.append(lines[i].strip())
                depth += lines[i].count("(") - lines[i].count(")")
            i += 1

            combined = " ".join(via_lines)

            combined_text = combined

            def _extract_at(
                _combined: str = combined_text,
            ) -> tuple[float, float] | None:
                idx = _combined.find("(at ")
                if idx == -1:
                    return None
                rest = _combined[idx + 4 :].strip()
                end = rest.find(")")
                if end == -1:
                    return None
                parts = rest[:end].strip().split()
                if len(parts) >= 2:
                    return float(parts[0]), float(parts[1])
                return None

            def _extract_net_num(
                _combined: str = combined_text,
            ) -> str | None:
                idx = _combined.find("(net ")
                if idx == -1:
                    return None
                rest = _combined[idx + 5 :].strip()
                end = rest.find(")")
                if end == -1:
                    return None
                return rest[:end].strip().split()[0]

            at_pos = _extract_at()
            net_num = _extract_net_num()
            if at_pos is not None and net_num is not None:
                net_name = _resolve_net_name(net_num, net_map)
                vias.append(ViaInfo(position=at_pos, net_name=net_name))
            continue
        i += 1

    return vias


def _build_net_geometry(
    segments: list[TraceSegment], vias: list[ViaInfo]
) -> dict[str, NetGeometry]:
    """Aggregate segments and vias into per-net geometry."""
    nets: dict[str, NetGeometry] = {}

    for seg in segments:
        if seg.net_name not in nets:
            nets[seg.net_name] = NetGeometry(name=seg.net_name)
        geo = nets[seg.net_name]
        geo.total_length_mm += _distance_mm(seg.start, seg.end)
        geo.trace_widths_mm.append(seg.width)
        geo.segment_count += 1
        geo.layers.add(seg.layer)

    for via in vias:
        if via.net_name not in nets:
            nets[via.net_name] = NetGeometry(name=via.net_name)
        nets[via.net_name].via_count += 1

    return nets


def _compute_parasitics(
    net_geo: NetGeometry, loop_group: str | None
) -> ParasiticValues:
    """Compute hand-calculated parasitics for a net."""
    length_mm = net_geo.total_length_mm
    avg_width_mm = (
        sum(net_geo.trace_widths_mm) / len(net_geo.trace_widths_mm)
        if net_geo.trace_widths_mm
        else 0.5
    )

    L_nH_per_mm = 0.8
    L_nH_trace = length_mm * L_nH_per_mm

    if net_geo.via_count > 0:
        L_nH_trace += net_geo.via_count * 1.0

    if loop_group and loop_group in LOOP_DERATE_L:
        L_nH_trace *= LOOP_DERATE_L[loop_group]

    width_m = avg_width_mm * 1e-3
    if width_m > 0:
        R_mOhm_trace = (
            length_mm * 1e-3 * (RHO_COPPER / (width_m * COPPER_THICKNESS_1OZ)) * 1000
        )
    else:
        R_mOhm_trace = 0.0
    R_mOhm_trace *= DERATE_R_TEMP

    C_pF_per_mm = avg_width_mm * 0.04
    C_pF_trace = length_mm * C_pF_per_mm

    return ParasiticValues(
        net_name=net_geo.name,
        R_mOhm=round(R_mOhm_trace, 2),
        L_nH=round(L_nH_trace, 2),
        C_pF=round(C_pF_trace, 2),
        loop_group=loop_group,
    )


def _load_net_groups(groups_path: Path) -> dict[str, dict[str, object]]:
    """Load net group definitions from YAML."""
    with open(groups_path) as f:
        return yaml.safe_load(f)


def _build_loop_group_map(
    groups: dict[str, dict[str, object]],
) -> dict[str, str]:
    """Build net name -> loop group name mapping."""
    mapping: dict[str, str] = {}
    for group_name, group_def in groups.items():
        for net_name in group_def.get("nets", []):
            mapping[net_name] = group_name
    return mapping


def extract_parasitics(
    pcb_file: str | Path, net_groups_path: str | Path | None = None
) -> ExtractionResult:
    """Extract parasitic values from a KiCad PCB file.

    Args:
        pcb_file: Path to .kicad_pcb file.
        net_groups_path: Path to net_groups.yaml. Defaults to bundled config.

    Returns:
        ExtractionResult with per-net parasitics and loop group mappings.
    """
    pcb_path = Path(pcb_file)
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_file}")

    if net_groups_path is None:
        net_groups_path = Path(__file__).parent / "net_groups.yaml"

    groups = _load_net_groups(Path(net_groups_path))
    content = pcb_path.read_text()
    segments = _parse_kicad_sexpr(content)
    vias = _parse_vias(content)
    net_geos = _build_net_geometry(segments, vias)

    nets: dict[str, ParasiticValues] = {}
    warnings: list[str] = []

    group_covered: set[str] = set()
    for group_name in groups:
        group_nets = groups[group_name].get("nets", [])
        for net_name in group_nets:
            group_covered.add(net_name)
            if net_name in net_geos:
                geo = net_geos[net_name]
                nets[net_name] = _compute_parasitics(geo, group_name)
            else:
                warnings.append(
                    f"Net '{net_name}' (group '{group_name}') not found in PCB"
                )
                nets[net_name] = ParasiticValues(
                    net_name=net_name,
                    R_mOhm=0.0,
                    L_nH=0.0,
                    C_pF=0.0,
                    loop_group=group_name,
                )

    identified_count = len(group_covered)
    total_net_count = len(net_geos)
    warnings.append(
        f"Extracted parasitics for {identified_count}/{total_net_count} "
        f"nets in defined loop groups. {total_net_count - identified_count} "
        f"nets not in any loop group are omitted."
    )

    loop_groups: dict[str, list[str]] = {}
    for group_name in groups:
        loop_groups[group_name] = groups[group_name].get("nets", [])

    return ExtractionResult(
        pcb_file=str(pcb_path),
        nets=nets,
        loop_groups=loop_groups,
        warnings=warnings,
    )


def main() -> None:
    """CLI entry point for parasitic extraction."""
    if len(sys.argv) < 2:
        print("Usage: python -m tools.spice.extract <kicad_pcb_file>", file=sys.stderr)
        sys.exit(1)

    result = extract_parasitics(sys.argv[1])

    print("=== Parasitic Extraction Results ===")
    for net_name, p in result.nets.items():
        print(
            f"{net_name} [{p.loop_group or 'unassigned'}]: "
            f"R={p.R_mOhm:.1f}mOhm L={p.L_nH:.1f}nH C={p.C_pF:.1f}pF"
        )

    for w in result.warnings:
        print(f"WARNING: {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
