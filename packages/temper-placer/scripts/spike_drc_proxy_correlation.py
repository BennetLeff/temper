#!/usr/bin/env python3
"""
Spike: DRC Proxy vs KiCad DRC Correlation.

Computes Pearson correlation coefficient between:
- DRC proxy score (sum of width-inflated occupancy penalties)
- KiCad DRC track-to-track clearance violation count

across 6 populated golden boards from power_pcb_dataset/.

Gate: r >= 0.95 → proceed to full implementation.
      0.85 <= r < 0.94 → iterate once.
      r < 0.85 → fall back to DRC ratchet.

Usage:
    python scripts/spike_drc_proxy_correlation.py [--dataset power_pcb_dataset/] [--threshold 0.95]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

# Add temper-placer to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def parse_kicad_drc_json(drc_json_path: Path) -> int:
    """
    Count track-to-track clearance violations from KiCad DRC JSON.

    Args:
        drc_json_path: Path to KiCad DRC report JSON file.

    Returns:
        Number of clearance violations.
    """
    with open(drc_json_path) as f:
        data = json.load(f)

    clearance_count = 0
    for violation in data.get("violations", []):
        vtype = violation.get("type", "")
        if "clearance" in vtype.lower() or "shorting" in vtype.lower():
            clearance_count += 1

    return clearance_count


def run_kicad_drc(pcb_path: Path, output_dir: Path) -> Path:
    """
    Run KiCad DRC on a PCB file and return path to JSON report.

    Args:
        pcb_path: Path to .kicad_pcb file.
        output_dir: Directory to write DRC report.

    Returns:
        Path to DRC JSON report file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output = output_dir / f"{pcb_path.stem}_drc.json"

    cmd = [
        "kicad-cli", "drc",
        str(pcb_path),
        "--output-format", "json",
        "--output", str(json_output),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"  [WARN] kicad-cli failed for {pcb_path.name}: {result.stderr[:200]}")
    except FileNotFoundError:
        print("  [WARN] kicad-cli not found in PATH")
    except subprocess.TimeoutExpired:
        print(f"  [WARN] kicad-cli timeout for {pcb_path.name}")

    return json_output


def compute_proxy_score_placeholder(positions: np.ndarray, dims: np.ndarray) -> float:
    """
    Compute proxy score using the standalone function.

    This is a placeholder for the spike — uses precomputed inflated dims.
    In production, dims would come from geometry/drc_inflate.py.

    Args:
        positions: (N, 2) component positions.
        dims: (N, 2) inflated (width, height) per component.

    Returns:
        Scalar proxy score.
    """
    import jax.numpy as jnp

    from temper_placer.geometry.drc_inflate import compute_drc_proxy_score

    half_w = jnp.array(dims[:, 0] / 2.0, dtype=jnp.float32)
    half_h = jnp.array(dims[:, 1] / 2.0, dtype=jnp.float32)
    pos = jnp.array(positions, dtype=jnp.float32)

    return float(compute_drc_proxy_score(pos, half_w, half_h))


def load_board_data(board_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Load component positions and dimensions from board data.

    Tries multiple formats:
    1. placement JSON
    2. Netlist CSV
    3. Returns empty placeholder

    Args:
        board_dir: Path to board directory.

    Returns:
        Tuple of (positions, dims) as numpy arrays, or (empty, empty).
    """
    import json

    # Try placement JSON
    placement_path = board_dir / "placement.json"
    if placement_path.exists():
        with open(placement_path) as f:
            data = json.load(f)
        positions = []
        dims = []
        for comp in data.get("components", data if isinstance(data, list) else []):
            pos = comp.get("position", [0.0, 0.0])
            w = comp.get("width", 10.0)
            h = comp.get("height", 5.0)
            positions.append(pos[:2])
            dims.append([w, h])
        if positions:
            return np.array(positions, dtype=np.float32), np.array(dims, dtype=np.float32)

    # Placeholder: return synthetic data
    return np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32)


def compute_pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    """Compute Pearson correlation coefficient."""
    if len(x) < 2:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def main():
    parser = argparse.ArgumentParser(
        description="Spike: DRC Proxy vs KiCad DRC correlation"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / ".." / ".." / "power_pcb_dataset",
        help="Path to power_pcb_dataset directory",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Pearson r threshold for gate (default: 0.95)",
    )
    parser.add_argument(
        "--skip-kicad",
        action="store_true",
        help="Skip KiCad DRC (only run proxy)",
    )
    args = parser.parse_args()

    dataset_path = args.dataset
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        print("Skipping spike — dataset unavailable.")
        return 0

    # Find populated boards
    board_dirs = sorted(dataset_path.glob("board_*"))
    if not board_dirs:
        print(f"No board directories found in {dataset_path}")
        return 0

    # Limit to 6 golden boards
    board_dirs = [d for d in board_dirs if d.is_dir()][:6]
    print(f"Processing {len(board_dirs)} golden boards...")

    proxy_scores = []
    kicad_counts = []

    for board_dir in board_dirs:
        print(f"\n  Board: {board_dir.name}")

        # Load board data
        positions, dims = load_board_data(board_dir)
        if positions.shape[0] == 0:
            print("    [SKIP] No component data found")
            continue

        # Compute proxy score
        proxy = compute_proxy_score_placeholder(positions, dims)
        proxy_scores.append(proxy)
        print(f"    Proxy score: {proxy:.4f}")

        # Run KiCad DRC if available
        kicad_count = 0
        if not args.skip_kicad:
            pcb_path = board_dir / f"{board_dir.name}.kicad_pcb"
            if not pcb_path.exists():
                pcbs = list(board_dir.glob("*.kicad_pcb"))
                if pcbs:
                    pcb_path = pcbs[0]

            if pcb_path.exists():
                drc_json = run_kicad_drc(pcb_path, board_dir / "drc_output")
                if drc_json.exists():
                    kicad_count = parse_kicad_drc_json(drc_json)
            else:
                print("    [WARN] No .kicad_pcb found")

        kicad_counts.append(kicad_count)
        print(f"    KiCad DRC clearance violations: {kicad_count}")

    if len(proxy_scores) < 2:
        print("\nNot enough data for correlation (need >= 2 boards).")
        return 1

    # Compute Pearson correlation
    x = np.array(proxy_scores)
    y = np.array(kicad_counts)
    r = compute_pearson_r(x, y)

    print(f"\n{'='*60}")
    print(f"Pearson r: {r:.4f}")
    print(f"Threshold: {args.threshold:.4f}")

    if r >= args.threshold:
        print("✓ PASS — proceed to full implementation (Phase 2+)")
        result = 0
    elif r >= 0.85:
        print("⚠ MARGINAL — iterate on proxy once before proceeding")
        result = 1
    else:
        print("✗ FAIL — fall back to DRC ratchet")
        result = 2

    print(f"{'='*60}")
    return result


if __name__ == "__main__":
    sys.exit(main())
