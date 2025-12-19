"""
Batch script to generate unrouted benchmark fixtures from manifest.yaml.

This script:
1. Loads manifest.yaml
2. Downloads any missing projects (using existing download utility)
3. For each project:
   - Strips all routing from original PCB
   - Computes human baseline metrics (HPWL, Area)
   - Saves stripped PCB and baseline YAML to cache
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import strip_routing
from temper_placer.io.reference_loader import compute_design_stats, netlist_to_placement_state
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import compute_total_hpwl

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Paths
SCRIPTS_DIR = Path(__file__).parent
EXTERNAL_DIR = SCRIPTS_DIR.parent / "tests" / "fixtures" / "external"
MANIFEST_PATH = EXTERNAL_DIR / "manifest.yaml"
CACHE_DIR = EXTERNAL_DIR / ".cache"


def load_manifest() -> dict[str, Any]:
    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)


def generate_unrouted_benchmarks():
    manifest = load_manifest()
    projects = manifest.get("projects", {})

    logger.info(f"Generating unrouted benchmarks for {len(projects)} projects...")

    for name, config in projects.items():
        if config.get("kicad_version") == 5:
            logger.info(f"Skipping {name} (KiCad 5 format not supported for stripping)")
            continue

        # 1. Get original PCB path
        # The download script saves to CACHE_DIR / project_name / filename
        project_cache = CACHE_DIR / name
        if not project_cache.exists():
            logger.warning(f"Project {name} not found in cache. Skipping.")
            continue

        pcb_files = config.get("pcb_files", [])
        if not pcb_files:
            continue

        original_filename = Path(pcb_files[0]).name
        original_pcb_path = project_cache / original_filename

        if not original_pcb_path.exists():
            logger.warning(f"PCB file {original_pcb_path} not found. Skipping.")
            continue

        unrouted_pcb_path = project_cache / f"{name}_unrouted.kicad_pcb"
        baseline_yaml_path = project_cache / f"{name}_baseline.yaml"

        logger.info(f"Processing {name}...")

        try:
            # 2. Extract Human Baseline Metrics
            parse_result = parse_kicad_pcb(original_pcb_path)
            stats = compute_design_stats(parse_result)

            # Compute HPWL
            state = netlist_to_placement_state(parse_result.netlist, parse_result.board)
            context = LossContext.from_netlist_and_board(parse_result.netlist, parse_result.board)

            # Using alpha=20 for sharp HPWL estimate matching human layout

            # We need a dummy rotation array (N, 4) - human rotations are fixed in state
            n = parse_result.netlist.n_components
            # netlist_to_placement_state already sets rotation_logits to high values for initial
            # We can sample them with low temperature to get hard one-hots
            from temper_placer.geometry.transform import sample_rotation_batch

            rotations = sample_rotation_batch(
                state.rotation_logits, jax.random.PRNGKey(0), temperature=0.01
            )

            hpwl = float(compute_total_hpwl(state.positions, rotations, context, alpha=20.0))

            baseline_data = {
                "project": name,
                "components": stats["n_components"],
                "nets": stats["n_nets"],
                "board_area_mm2": stats["board_area_mm2"],
                "human_metrics": {
                    "total_hpwl_mm": round(hpwl, 2),
                    "density": stats["density"],
                    "drc_errors": 0,  # Assume human layout is DRC clean
                },
            }

            with open(baseline_yaml_path, "w") as f:
                yaml.dump(baseline_data, f, default_flow_style=False)

            logger.info(f"  ✓ Saved baseline: {baseline_yaml_path}")

            # 3. Strip Routing
            strip_result = strip_routing(original_pcb_path, unrouted_pcb_path)
            logger.info(f"  ✓ Saved unrouted: {unrouted_pcb_path}")
            logger.info(
                f"    (Removed {strip_result.traces_removed} traces, {strip_result.vias_removed} vias)"
            )

        except Exception as e:
            logger.error(f"  ✗ Failed to process {name}: {e}")
            import traceback

            logger.debug(traceback.format_exc())

    logger.info("Done!")


if __name__ == "__main__":
    import jax

    generate_unrouted_benchmarks()
