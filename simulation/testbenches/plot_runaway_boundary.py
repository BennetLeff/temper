#!/usr/bin/env python3
"""plot_runaway_boundary.py

Reads runaway_boundary_map.csv, generates a scatter-plot SVG with
interlock trip lines overlaid. Annotates worst-3 corners.

Output: simulation/results/runaway_boundary_map.svg
"""

import csv
import os
import sys
from pathlib import Path


def plot_boundary_map(csv_path: str, svg_path: str) -> str:
    """Read CSV and write SVG scatter plot.

    Returns path to generated SVG.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("ERROR: matplotlib is required. Install with: pip install matplotlib")
        sys.exit(1)

    points: dict[str, list[tuple[float, float]]] = {
        "steady-state": [],
        "runaway": [],
        "destructive": [],
        "warm": [],
        "failed": [],
    }

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cls = row.get("classification", "failed")
            try:
                heatsink = float(row["ths_end_powered"])
                coil = float(row["tcoil_end_powered"])
            except (ValueError, KeyError, TypeError):
                heatsink = 0.0
                coil = 0.0
            if heatsink < 0 or coil < 0:
                continue
            points.setdefault(cls, []).append((heatsink, coil))

    fig, ax = plt.subplots(figsize=(10, 8))

    colors = {
        "steady-state": "#2ecc71",  # green
        "runaway": "#e74c3c",       # red
        "destructive": "#8e44ad",   # purple
        "warm": "#f39c12",          # orange
        "failed": "#95a5a6",        # grey
    }
    markers = {
        "steady-state": "o",
        "runaway": "s",
        "destructive": "X",
        "warm": "d",
        "failed": ".",
    }

    for cls, pts in points.items():
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.scatter(xs, ys, c=colors.get(cls, "#000000"),
                   marker=markers.get(cls, "o"),
                   label=cls, alpha=0.7, edgecolors="black", linewidth=0.3)

    # Interlock trip lines
    # Heatsink NTC trip at 85 C (hardware latch)
    ax.axvline(x=85, color="#3498db", linestyle="--", linewidth=1.5,
               label="Heatsink trip (85 C)")
    # Coil NTC trip at 120 C
    ax.axhline(y=120, color="#e67e22", linestyle="--", linewidth=1.5,
               label="Coil trip (120 C)")

    # Annotate worst-3 corners (highest heatsink or coil temp among non-runaway,
    # closest to the interlock trip lines)
    worst_candidates = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                hs = float(row["ths_end_powered"])
                co = float(row["tcoil_end_powered"])
                tj = float(row["tj_max"]) if row.get("tj_max") else 0.0
                cls = row.get("classification", "failed")
                vbus = row["vbus"]
                k = row["k"]
                ctol = row["ctol"]
                tamb = row["tamb"]
                fan = row["fan"]
            except (ValueError, KeyError, TypeError):
                continue
            worst_candidates.append((hs, co, tj, cls, vbus, k, ctol, tamb, fan))

    # Sort by proximity to intersection of trip lines (85, 120)
    # closer = smaller margin; prefer non-failed, non-destructive
    worst_candidates.sort(
        key=lambda x: (x[3] == "failed", x[3] == "destructive",
                       abs(float(x[0]) - 85) + abs(float(x[1]) - 120) * 0.1
                       - 100 * (x[3] in ("warm", "steady-state")))
    )

    for i, (hs, co, tj, cls, vbus, k, ctol, tamb, fan) in enumerate(
            worst_candidates[:3]):
        ax.annotate(
            f"#{i+1}: V={vbus} k={k} C={ctol} T={tamb} F={fan}\n"
            f"Hs={hs:.0f}C Coil={co:.0f}C Tj={tj:.0f}C [{cls}]",
            xy=(hs, co),
            xytext=(20, -20 if i == 0 else 20),
            textcoords="offset points",
            fontsize=7,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="gray", alpha=0.9),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.2",
                            color="gray")
        )

    ax.set_xlabel("Heatsink Temperature (C)")
    ax.set_ylabel("Coil Temperature (C)")
    ax.set_title("Runaway Boundary Map\n"
                 "Half-Bridge IKW40N120H3 IGBTs (432-point sweep)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)

    # Axis limits with margin
    all_hs = [p[0] for pts in points.values() for p in pts]
    all_co = [p[1] for pts in points.values() for p in pts]
    if all_hs:
        hs_min, hs_max = min(all_hs), max(all_hs)
        ax.set_xlim(max(0, hs_min - 10), hs_max + 20)
    if all_co:
        co_min, co_max = min(all_co), max(all_co)
        ax.set_ylim(max(0, co_min - 10), co_max + 20)

    fig.tight_layout()
    fig.savefig(svg_path, format="svg", dpi=150)
    plt.close(fig)

    return svg_path


def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    results_dir = project_root / "simulation" / "results"
    csv_path = results_dir / "runaway_boundary_map.csv"
    svg_path = results_dir / "runaway_boundary_map.svg"

    if not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}")
        print("Run sweep_runaway_boundary.sh first.")
        sys.exit(1)

    output = plot_boundary_map(str(csv_path), str(svg_path))
    print(f"Boundary map SVG written to: {output}")


if __name__ == "__main__":
    main()
