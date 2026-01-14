#!/usr/bin/env python3
"""
Run Spectral Placement Experiment.

1. Load PCB.
2. Compute Spectral Layout.
3. Visualize Initial vs Spectral.
"""

import sys
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.placement.spectral import SpectralPlacer
from temper_placer.placement.analytical import AnalyticalLegalizer


def plot_placement(coords, title, filename):
    plt.figure(figsize=(10, 10))
    x_vals = [p[0] for p in coords.values()]
    y_vals = [p[1] for p in coords.values()]
    labels = list(coords.keys())

    plt.scatter(x_vals, y_vals, alpha=0.5)

    for i, label in enumerate(labels):
        plt.annotate(label, (x_vals[i], y_vals[i]), fontsize=8)

    plt.title(title)
    plt.grid(True)
    plt.savefig(filename)
    print(f"Saved plot to {filename}")
    plt.close()


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        print("PCB not found")
        sys.exit(1)

    print("Loading PCB...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    # 1. Initial
    initial_coords = {c.ref: c.initial_position for c in pcb.components if c.initial_position}

    # Calculate bounds from initial placement (heuristic)
    init_x = [p[0] for p in initial_coords.values()]
    init_y = [p[1] for p in initial_coords.values()]
    min_x, max_x = min(init_x), max(init_x)
    min_y, max_y = min(init_y), max(init_y)
    # Add margin
    bounds = (min_x - 10, min_y - 10, max_x + 10, max_y + 10)

    # 2. Spectral
    print("Running Spectral Placement...")
    placer = SpectralPlacer(pcb)
    spectral_coords = placer.compute_placement()

    # Scale spectral coords to match initial bounds approximately
    # for better visualization comparison AND for legalization input
    spec_x = [p[0] for p in spectral_coords.values()]
    spec_y = [p[1] for p in spectral_coords.values()]
    s_min_x, s_max_x = min(spec_x), max(spec_x)
    s_min_y, s_max_y = min(spec_y), max(spec_y)

    scale_x = (max_x - min_x) / (s_max_x - s_min_x) if s_max_x != s_min_x else 1
    scale_y = (max_y - min_y) / (s_max_y - s_min_y) if s_max_y != s_min_y else 1
    # Use uniform scaling to preserve aspect ratio of spectral embedding
    scale = min(scale_x, scale_y)

    # Center
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    scaled_spectral = {}
    for ref, (x, y) in spectral_coords.items():
        scaled_spectral[ref] = (x * scale + center_x, y * scale + center_y)

    # Output
    output_dir = Path("pcb/placement_experiments")
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_placement(initial_coords, "Initial Placement", output_dir / "initial.png")
    plot_placement(scaled_spectral, "Spectral Placement (Relative)", output_dir / "spectral.png")

    # 3. Analytical Legalization
    print("Running Analytical Legalization...")
    legalizer = AnalyticalLegalizer(pcb)

    # Run legalization (updates pcb.components in-place)
    # We pass the scaled spectral coordinates as targets
    success = legalizer.legalize(scaled_spectral, bounds)

    if success:
        print("Legalization Successful.")
    else:
        print("Legalization Failed (LP infeasible).")

    # Extract new coords
    legal_coords = {c.ref: c.initial_position for c in pcb.components}
    plot_placement(legal_coords, "Analytical Legalization", output_dir / "legalized.png")

    # Print some stats
    print("\nSample Legal Coordinates:")
    for ref in list(legal_coords.keys())[:5]:
        print(f"  {ref}: {legal_coords[ref]}")


if __name__ == "__main__":
    main()
