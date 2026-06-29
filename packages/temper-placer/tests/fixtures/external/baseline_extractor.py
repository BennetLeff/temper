"""
Baseline metrics extractor for external PCB test fixtures.

Extracts placement quality metrics from human-designed PCB layouts
to use as ground truth baselines for optimizer comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:

    pass


@dataclass
class BaselineMetrics:
    """Quality metrics extracted from a human-designed placement."""

    # Identification
    project: str
    extracted_at: str
    source_pcb: str

    # Board info
    board_width_mm: float
    board_height_mm: float
    kicad_version: int = 6
    board_origin_x: float = 0.0
    board_origin_y: float = 0.0
    component_count: int = 0
    net_count: int = 0

    # Human placement metrics (normalized 0-1 scores where 1.0 is ideal)
    # Includes original positions and DRC results
    human_placement: dict[str, Any] = field(default_factory=dict)

    # DRC metrics (redundant but useful at top level)
    drc_errors: int = 0
    drc_warnings: int = 0
    drc_available: bool = False

    # Optional detailed metrics
    net_wirelengths: dict[str, float] = field(default_factory=dict)
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


def _check_dependencies() -> bool:
    """Check if required dependencies are available."""
    try:
        import jax.numpy as jnp  # noqa: F401

        from temper_placer.core import PlacementState  # noqa: F401
        from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: F401
        from temper_placer.losses import BoundaryLoss, OverlapLoss  # noqa: F401
        from temper_placer.losses.base import LossContext  # noqa: F401
        from temper_placer.losses.wirelength import compute_total_hpwl  # noqa: F401
        from temper_placer.validation.drc import KiCadDRCValidator  # noqa: F401

        return True
    except ImportError:
        return False


def extract_baseline_metrics(
    pcb_path: Path,
    project_name: str,
    constraints_path: Path | None = None,
) -> BaselineMetrics:
    """
    Extract placement quality metrics from a human-designed PCB.

    This parses the PCB, builds a PlacementState from the original positions,
    and evaluates standard loss functions to get ground truth metrics.

    Args:
        pcb_path: Path to the .kicad_pcb file
        project_name: Name for identification in the output
        constraints_path: Optional path to the constraints YAML file

    Returns:
        BaselineMetrics containing all extracted quality metrics
    """
    # Import dependencies (checked at runtime)
    import jax.numpy as jnp

    from temper_placer.core import PlacementState
    from temper_placer.io.config_loader import load_constraints
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.losses.base import LossContext
    from temper_placer.metrics.quality import compute_quality_report
    from temper_placer.validation.drc import KiCadDRCValidator

    warnings: list[str] = []

    # Parse the PCB
    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist
    board = result.board

    if board is None:
        raise ValueError(f"No board geometry found in {pcb_path}")

    # Load constraints if available
    constraints = None
    if constraints_path and constraints_path.exists():
        try:
            constraints = load_constraints(constraints_path)
        except Exception as e:
            warnings.append(f"Failed to load constraints from {constraints_path}: {e}")

    # Get board origin for coordinate transformation
    # Parser stores positions as origin-relative, but loss functions expect absolute
    origin_x, origin_y = board.origin

    # Extract component positions from original placement
    component_positions: dict[str, list[float]] = {}
    positions_list: list[tuple[float, float]] = []
    rotations_list: list[int] = []

    for comp in netlist.components:
        pos = comp.initial_position
        rot = comp.initial_rotation

        # Handle components without initial position (should not happen for parsed PCBs)
        if pos is None:
            warnings.append(f"Component {comp.ref} has no initial position, using (0, 0)")
            pos = (0.0, 0.0)
        if rot is None:
            rot = 0

        # Store origin-relative coordinates in [x, y, rotation] format
        component_positions[comp.ref] = [
            round(float(pos[0]), 3),
            round(float(pos[1]), 3),
            float(rot * 90),  # Store as degrees
        ]

        # Convert to ABSOLUTE coordinates for loss computation
        abs_x = float(pos[0]) + origin_x
        abs_y = float(pos[1]) + origin_y
        positions_list.append((abs_x, abs_y))

        # Convert rotation to discrete index (0=0°, 1=90°, 2=180°, 3=270°)
        rot_idx = int(rot) % 4
        rotations_list.append(rot_idx)

    # Build PlacementState from original positions (in absolute coordinates)
    n_components = len(netlist.components)
    positions_array = jnp.array(positions_list, dtype=jnp.float32)

    # Create one-hot rotation encoding
    rotations_one_hot = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotations_one_hot = rotations_one_hot.at[i, rot_idx].set(1.0)

    # Create PlacementState with rotation logits that match original rotations
    rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotation_logits = rotation_logits.at[i, rot_idx].set(10.0)  # High logit for selected

    state = PlacementState(
        positions=positions_array,
        rotation_logits=rotation_logits,
    )

    # Create LossContext from netlist and board
    context = LossContext.from_netlist_and_board(netlist, board)

    # Run DRC validation if KiCad is available
    drc_errors = 0
    drc_warnings = 0
    drc_available = False

    validator = KiCadDRCValidator()
    if validator.is_available():
        drc_available = True
        try:
            drc_result = validator.run_drc(pcb_path)
            if drc_result.success:
                drc_errors = drc_result.error_count
                drc_warnings = drc_result.warning_count
            else:
                warnings.append(f"DRC failed: {drc_result.raw_output[:200]}")
        except Exception as e:
            warnings.append(f"DRC exception: {str(e)}")

    # Compute high-level quality metrics
    quality_config = {}
    if constraints:
        # Map constraints to quality_config
        quality_config = {
            "thermal_components": set(),
            "hv_components": set(),
            "lv_components": set(),
            "zone_assignments": constraints.zone_assignments,
            "loop_components": [list(loop.nets) for loop in constraints.critical_loops],
            "min_hv_lv_clearance": constraints.hv_clearance_mm,
        }

        # Populate component sets from netlist and constraints
        for comp in netlist.components:
            if comp.net_class == "HighVoltage":
                quality_config["hv_components"].add(comp.ref)
            elif comp.net_class == "Signal":
                quality_config["lv_components"].add(comp.ref)

        # Add thermal components from constraints
        for tc in constraints.thermal_constraints:
            for ref in tc.components:
                quality_config["thermal_components"].add(ref)

    quality_report = compute_quality_report(
        state, netlist, board, context, quality_config
    )

    # Format human_placement dict according to requested schema
    human_placement = {
        "drc_errors": drc_errors,
        "drc_warnings": drc_warnings,
        "metrics": {
            "total_wirelength_mm": round(float(quality_report["total_wirelength"]), 2),
            "thermal_score": round(float(quality_report["thermal_score"]), 3),
            "zone_compliance": round(float(quality_report["zone_compliance_score"]), 3),
            "hv_lv_clearance": round(float(quality_report["hv_lv_clearance_score"]), 3),
            "loop_area_score": round(float(quality_report["loop_area_score"]), 3),
            "congestion_score": round(float(quality_report["congestion_score"]), 3),
            "compactness_score": round(float(quality_report["compactness_score"]), 3),
        },
        "component_positions": component_positions,
    }

    return BaselineMetrics(
        project=project_name,
        extracted_at=datetime.now().isoformat(),
        source_pcb=str(pcb_path),
        kicad_version=6,
        board_width_mm=round(float(board.width), 2),
        board_height_mm=round(float(board.height), 2),
        board_origin_x=round(origin_x, 2),
        board_origin_y=round(origin_y, 2),
        component_count=n_components,
        net_count=len(netlist.nets),
        human_placement=human_placement,
        drc_errors=drc_errors,
        drc_warnings=drc_warnings,
        drc_available=drc_available,
        warnings=warnings,
    )


def extract_baseline_for_project(
    project_name: str,
    output_dir: Path | None = None,
) -> Path | None:
    """
    Extract and save baseline metrics for a downloaded external PCB project.

    Args:
        project_name: Name of the project (from manifest.yaml)
        output_dir: Directory to save metrics (default: same as PCB cache)

    Returns:
        Path to generated baseline file, or None if failed
    """
    from .download_pcbs import get_cached_pcb_path, get_project_config

    # Check project exists and is KiCad 6+
    config = get_project_config(project_name)
    if config is None:
        print(f"Unknown project: {project_name}")
        return None

    kicad_version = config.get("kicad_version", 6)
    if kicad_version == 5:
        print(f"Skipping {project_name}: KiCad 5 format not supported")
        return None

    # Get PCB path
    pcb_path = get_cached_pcb_path(project_name)
    if pcb_path is None or not pcb_path.exists():
        print(f"PCB not downloaded: {project_name}")
        return None

    # Get constraints path
    constraints_path = pcb_path.parent / f"{project_name}_constraints.yaml"
    if not constraints_path.exists():
        print(f"Constraints not found for {project_name}, some metrics will be zero.")

    # Extract baseline metrics
    try:
        metrics = extract_baseline_metrics(pcb_path, project_name, constraints_path)
    except Exception as e:
        print(f"Failed to extract baseline for {project_name}: {e}")
        import traceback

        traceback.print_exc()
        return None

    # Save to file
    if output_dir is None:
        output_dir = pcb_path.parent

    # Save as _benchmark.yaml as requested
    output_path = output_dir / f"{project_name}_benchmark.yaml"
    metrics.save(output_path)

    print(f"Extracted benchmark for {project_name}: {output_path}")
    print(f"  Board origin: ({metrics.board_origin_x}, {metrics.board_origin_y})")
    print(f"  Components: {metrics.component_count}, Nets: {metrics.net_count}")

    m = metrics.human_placement.get("metrics", {})
    print(f"  Wirelength: {m.get('total_wirelength_mm', 0.0):.2f} mm")
    print(f"  Thermal Score: {m.get('thermal_score', 0.0):.3f}")
    print(f"  Zone Compliance: {m.get('zone_compliance', 0.0):.3f}")

    if metrics.drc_available:
        print(f"  DRC: {metrics.drc_errors} errors, {metrics.drc_warnings} warnings")
    else:
        print("  DRC: not available")

    if metrics.warnings:
        for w in metrics.warnings:
            print(f"  WARNING: {w}")

    return output_path


def extract_all_baselines() -> dict[str, Path]:
    """
    Extract baselines for all downloaded KiCad 6 projects.

    Returns:
        Dictionary mapping project name to baseline file path
    """
    from .download_pcbs import load_manifest

    manifest = load_manifest()
    projects = manifest.get("projects", {})

    results: dict[str, Path] = {}

    for name, config in projects.items():
        if config.get("kicad_version", 6) == 5:
            print(f"[SKIP] {name}: KiCad 5 format")
            continue

        result = extract_baseline_for_project(name)
        if result:
            results[name] = result

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Extract specific project
        for project in sys.argv[1:]:
            extract_baseline_for_project(project)
    else:
        # Extract all
        results = extract_all_baselines()
        print(f"\nExtracted baselines: {len(results)}")
