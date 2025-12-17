"""
Baseline metrics extractor for external PCB test fixtures.

Extracts placement quality metrics from human-designed PCB layouts
to use as ground truth baselines for optimizer comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import yaml

if TYPE_CHECKING:
    from jax import Array

    from temper_placer.core import Board, Component, Netlist, PlacementState
    from temper_placer.io.kicad_parser import ParseResult


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
    board_origin_x: float = 0.0
    board_origin_y: float = 0.0
    component_count: int = 0
    net_count: int = 0

    # Placement quality metrics
    total_wirelength_mm: float = 0.0
    overlap_loss: float = 0.0
    boundary_loss: float = 0.0

    # DRC metrics
    drc_errors: int = 0
    drc_warnings: int = 0
    drc_available: bool = False

    # Per-component data
    component_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Optional detailed metrics
    net_wirelengths: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
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
    def load(cls, input_path: Path) -> "BaselineMetrics":
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
    # Import dependencies (checked at runtime)
    import jax.numpy as jnp

    from temper_placer.core import PlacementState
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.losses import BoundaryLoss, OverlapLoss
    from temper_placer.losses.base import LossContext
    from temper_placer.losses.wirelength import compute_total_hpwl
    from temper_placer.validation.drc import KiCadDRCValidator

    warnings: List[str] = []

    # Parse the PCB
    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist
    board = result.board

    if board is None:
        raise ValueError(f"No board geometry found in {pcb_path}")

    # Get board origin for coordinate transformation
    # Parser stores positions as origin-relative, but loss functions expect absolute
    origin_x, origin_y = board.origin

    # Extract component positions from original placement
    component_positions: Dict[str, Dict[str, float]] = {}
    positions_list: List[Tuple[float, float]] = []
    rotations_list: List[int] = []

    for comp in netlist.components:
        pos = comp.initial_position
        rot = comp.initial_rotation

        # Handle components without initial position (should not happen for parsed PCBs)
        if pos is None:
            warnings.append(f"Component {comp.ref} has no initial position, using (0, 0)")
            pos = (0.0, 0.0)
        if rot is None:
            rot = 0

        # Store origin-relative coordinates in component_positions for human readability
        component_positions[comp.ref] = {
            "x": round(float(pos[0]), 3),
            "y": round(float(pos[1]), 3),
            "rotation": float(rot),
            "width": round(float(comp.bounds[0]), 3),
            "height": round(float(comp.bounds[1]), 3),
        }

        # Convert to ABSOLUTE coordinates for loss computation
        # The parser normalizes to origin-relative, but get_bounds_array() returns absolute
        abs_x = float(pos[0]) + origin_x
        abs_y = float(pos[1]) + origin_y
        positions_list.append((abs_x, abs_y))

        # Convert rotation to discrete index (0=0°, 1=90°, 2=180°, 3=270°)
        rot_idx = int(rot / 90) % 4
        rotations_list.append(rot_idx)

    # Build PlacementState from original positions (in absolute coordinates)
    n_components = len(netlist.components)
    positions_array = jnp.array(positions_list, dtype=jnp.float32)

    # Create one-hot rotation encoding
    rotations_one_hot = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotations_one_hot = rotations_one_hot.at[i, rot_idx].set(1.0)

    # Create PlacementState with rotation logits that match original rotations
    # Use high logit for the original rotation to make it "selected"
    rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)
    for i, rot_idx in enumerate(rotations_list):
        rotation_logits = rotation_logits.at[i, rot_idx].set(10.0)  # High logit for selected

    state = PlacementState(
        positions=positions_array,
        rotation_logits=rotation_logits,
    )

    # Create LossContext from netlist and board
    context = LossContext.from_netlist_and_board(netlist, board)

    # Calculate wirelength using HPWL directly
    total_wirelength = float(
        compute_total_hpwl(
            positions_array,
            rotations_one_hot,
            context,
        )
    )

    # Calculate overlap loss
    overlap_loss_fn = OverlapLoss()
    overlap_result = overlap_loss_fn(positions_array, rotations_one_hot, context)
    overlap_loss = float(overlap_result.value)

    if overlap_loss > 0.01:  # Small threshold for floating point
        warnings.append(f"Original design has overlap loss: {overlap_loss:.4f}")

    # Calculate boundary loss
    boundary_loss_fn = BoundaryLoss()
    boundary_result = boundary_loss_fn(positions_array, rotations_one_hot, context)
    boundary_loss = float(boundary_result.value)

    if boundary_loss > 0.01:  # Small threshold for floating point
        warnings.append(f"Original design has boundary loss: {boundary_loss:.4f}")

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
                if drc_errors > 0:
                    warnings.append(f"DRC found {drc_errors} errors")
            else:
                warnings.append(f"DRC failed: {drc_result.raw_output[:200]}")
        except Exception as e:
            warnings.append(f"DRC exception: {str(e)}")
    else:
        warnings.append("KiCad CLI not available - DRC metrics not computed")

    # Compute per-net wirelengths
    net_wirelengths: Dict[str, float] = {}
    # TODO: Implement per-net HPWL computation if needed

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
        total_wirelength_mm=round(total_wirelength, 2),
        overlap_loss=round(overlap_loss, 6),
        boundary_loss=round(boundary_loss, 6),
        drc_errors=drc_errors,
        drc_warnings=drc_warnings,
        drc_available=drc_available,
        component_positions=component_positions,
        net_wirelengths=net_wirelengths,
        warnings=warnings,
    )


def extract_baseline_for_project(
    project_name: str,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
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

    # Extract baseline metrics
    try:
        metrics = extract_baseline_metrics(pcb_path, project_name)
    except Exception as e:
        print(f"Failed to extract baseline for {project_name}: {e}")
        import traceback

        traceback.print_exc()
        return None

    # Save to file
    if output_dir is None:
        output_dir = pcb_path.parent

    output_path = output_dir / f"{project_name}_baseline.yaml"
    metrics.save(output_path)

    print(f"Extracted baseline for {project_name}: {output_path}")
    print(f"  Board origin: ({metrics.board_origin_x}, {metrics.board_origin_y})")
    print(f"  Components: {metrics.component_count}, Nets: {metrics.net_count}")
    print(f"  Wirelength: {metrics.total_wirelength_mm:.2f} mm")
    print(f"  Overlap: {metrics.overlap_loss:.6f}, Boundary: {metrics.boundary_loss:.6f}")
    if metrics.drc_available:
        print(f"  DRC: {metrics.drc_errors} errors, {metrics.drc_warnings} warnings")
    else:
        print(f"  DRC: not available")
    if metrics.warnings:
        for w in metrics.warnings:
            print(f"  WARNING: {w}")

    return output_path


def extract_all_baselines() -> Dict[str, Path]:
    """
    Extract baselines for all downloaded KiCad 6 projects.

    Returns:
        Dictionary mapping project name to baseline file path
    """
    from .download_pcbs import load_manifest

    manifest = load_manifest()
    projects = manifest.get("projects", {})

    results: Dict[str, Path] = {}

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
