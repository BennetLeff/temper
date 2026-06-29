"""
Baseline metrics extractor for human-designed PCB layouts.

Extracts placement quality metrics from human-designed PCB layouts
to use as ground truth baselines for optimizer comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BaselineMetrics:
    """Quality metrics extracted from a human-designed placement."""

    project: str
    extracted_at: str
    source_pcb: str

    board_width_mm: float
    board_height_mm: float
    kicad_version: int = 6
    board_origin_x: float = 0.0
    board_origin_y: float = 0.0
    component_count: int = 0
    net_count: int = 0

    overlap_count: int = 0
    boundary_violations: int = 0
    hv_lv_clearance_violations: int = 0
    zone_violations: int = 0

    total_wirelength_mm: float = 0.0
    gate_loop_area_mm2: float = 0.0
    bootstrap_loop_area_mm2: float = 0.0
    commutation_loop_area_mm2: float = 0.0

    drc_errors: int = 0
    drc_warnings: int = 0
    drc_available: bool = False

    component_positions: dict[str, list[float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return asdict(self)

    def save(self, output_path: Path) -> None:
        """Save metrics to YAML file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            yaml.dump(
                self.to_dict(),
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    @classmethod
    def load(cls, input_path: Path) -> BaselineMetrics:
        """Load metrics from YAML file."""
        with open(input_path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


def extract_baseline_metrics(
    pcb_path: Path,
    project_name: str,
) -> BaselineMetrics:
    """
    Extract placement quality metrics from a human-designed PCB.

    This parses the PCB, builds a PlacementState from the original positions,
    and evaluates standard loss functions to get ground truth metrics.

    Args:
        pcb_path: Path to the .kicad_pcb file
        project_name: Name for identification in the output

    Returns:
        BaselineMetrics containing all extracted quality metrics
    """
    import jax.numpy as jnp

    from temper_placer.core import PlacementState
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.losses.base import LossContext
    from temper_placer.validation.drc import KiCadDRCValidator
    from temper_placer.validation.metrics import compute_metrics

    warnings: list[str] = []
    component_positions: dict[str, list[float]] = {}

    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    board = parse_result.board

    if board is None:
        raise ValueError(f"No board geometry found in {pcb_path}")

    origin_x, origin_y = board.origin

    positions_list: list[tuple[float, float]] = []
    rotations_list: list[int] = []

    for comp in netlist.components:
        pos = comp.initial_position
        rot = comp.initial_rotation

        if pos is None:
            warnings.append(f"Component {comp.ref} has no initial position, using (0, 0)")
            pos = (0.0, 0.0)
        if rot is None:
            rot = 0

        component_positions[comp.ref] = [
            round(float(pos[0]), 3),
            round(float(pos[1]), 3),
            float(rot * 90),
        ]

        abs_x = float(pos[0]) + origin_x
        abs_y = float(pos[1]) + origin_y
        positions_list.append((abs_x, abs_y))

        rot_idx = int(rot) % 4
        rotations_list.append(rot_idx)

    n_components = len(netlist.components)
    positions_array = jnp.array(positions_list, dtype=jnp.float32)

    rotations_one_hot = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotations_one_hot = rotations_one_hot.at[i, rot_idx].set(1.0)

    rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotation_logits = rotation_logits.at[i, rot_idx].set(10.0)

    state = PlacementState(
        positions=positions_array,
        rotation_logits=rotation_logits,
    )

    LossContext.from_netlist_and_board(netlist, board)

    validator = KiCadDRCValidator()
    drc_available = validator.is_available()
    drc_errors = 0
    drc_warnings = 0

    if drc_available:
        try:
            drc_result = validator.run_drc(pcb_path)
            if drc_result.success:
                drc_errors = drc_result.error_count
                drc_warnings = drc_result.warning_count
            else:
                warnings.append(f"DRC failed: {drc_result.raw_output[:200]}")
        except Exception as e:
            warnings.append(f"DRC exception: {str(e)}")
            drc_available = False

    metrics = compute_metrics(state, netlist, board, hv_lv_clearance=10.0)

    return BaselineMetrics(
        project=project_name,
        extracted_at=datetime.now().isoformat(),
        source_pcb=str(pcb_path),
        board_width_mm=round(float(board.width), 2),
        board_height_mm=round(float(board.height), 2),
        board_origin_x=round(origin_x, 2),
        board_origin_y=round(origin_y, 2),
        component_count=n_components,
        net_count=len(netlist.nets),
        overlap_count=metrics.overlap_count,
        boundary_violations=metrics.boundary_violations,
        hv_lv_clearance_violations=metrics.hv_lv_violations,
        zone_violations=metrics.zone_violations,
        total_wirelength_mm=round(float(metrics.total_wirelength), 2),
        component_positions=component_positions,
        drc_errors=drc_errors,
        drc_warnings=drc_warnings,
        drc_available=drc_available,
        warnings=warnings,
    )


def extract_baseline_for_pcb(
    pcb_path: Path,
    output_dir: Path | None = None,
) -> Path:
    """
    Extract and save baseline metrics for a PCB file.

    Args:
        pcb_path: Path to the .kicad_pcb file
        output_dir: Directory to save metrics (default: same dir as PCB)

    Returns:
        Path to generated baseline file
    """
    project_name = pcb_path.stem

    metrics = extract_baseline_metrics(pcb_path, project_name)

    if output_dir is None:
        output_dir = pcb_path.parent

    output_path = output_dir / f"{project_name}_baseline.yaml"
    metrics.save(output_path)

    print(f"Extracted baseline for {project_name}: {output_path}")
    print(f"  Components: {metrics.component_count}, Nets: {metrics.net_count}")
    print(f"  Wirelength: {metrics.total_wirelength_mm:.2f}mm")
    print(
        f"  Overlaps: {metrics.overlap_count}, Boundary violations: {metrics.boundary_violations}"
    )

    if metrics.drc_available:
        print(f"  DRC: {metrics.drc_errors} errors, {metrics.drc_warnings} warnings")
    else:
        print("  DRC: not available")

    if metrics.warnings:
        for w in metrics.warnings:
            print(f"  WARNING: {w}")

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        pcb_path = Path(sys.argv[1])
        extract_baseline_for_pcb(pcb_path)
    else:
        print("Usage: python -m temper_placer.validation.baseline_extractor <pcb_file>")
