#!/usr/bin/env python3
"""
Experiment P1: Power Plane Synthesis.

Visualizes generated power planes for VCC/GND on the actual board.
"""

import matplotlib.pyplot as plt
from pathlib import Path
from shapely.geometry import Polygon
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v7.power_planes import PowerPlaneGenerator
from temper_placer.router_v6.obstacle_map import build_obstacle_map


def plot_poly(ax, poly, color, alpha=0.5):
    if poly.is_empty:
        return
    if isinstance(poly, Polygon):
        x, y = poly.exterior.xy
        ax.fill(x, y, color=color, alpha=alpha)
        for interior in poly.interiors:
            x, y = interior.xy
            ax.plot(x, y, color="white")
    else:
        for geom in poly.geoms:
            plot_poly(ax, geom, color, alpha)


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        print("PCB not found")
        return

    print("Loading PCB...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    # 2. Extract Seeds
    # Let's target "GND" (usually net name is specific, check pcb.nets)
    # Filter for nets containing "GND"
    gnd_nets = [n for n in pcb.nets if "GND" in n.name.upper()]
    if not gnd_nets:
        print("No GND nets found")
        return

    target_net = gnd_nets[0]
    print(f"Generating Plane for {target_net.name}...")

    # 1. Build Obstacle Map (Signal Keepouts)
    # We treat ALL components as obstacles EXCEPT the target net pads
    print("Building Obstacles...")
    obstacles = build_obstacle_map(pcb, [], exclude_net_name=target_net.name)
    fcu_obs = obstacles.get("F.Cu")

    seeds = []
    # Find pins for this net
    # We need Component positions
    from temper_placer.router_v6.astar_pathfinding import _extract_pad_centers_per_net

    pad_info = _extract_pad_centers_per_net(pcb)

    if target_net.name in pad_info:
        for x, y, r, l in pad_info[target_net.name]:
            if l == "F.Cu" or l == "All" or "*.Cu" in l:
                seeds.append((x, y))

    print(f"Found {len(seeds)} seeds.")

    # 3. Generate
    # Determine bounds
    # Use bounds from pipeline logic or just hardcode for visualization
    # 0,0 to 100,100 is safe guess, or compute
    all_x = [c.initial_position[0] for c in pcb.components if c.initial_position]
    all_y = [c.initial_position[1] for c in pcb.components if c.initial_position]
    bounds = (min(all_x) - 5, min(all_y) - 5, max(all_x) + 5, max(all_y) + 5)

    gen = PowerPlaneGenerator(bounds)
    if fcu_obs:
        gen.add_obstacle(fcu_obs)

    planes = gen.generate_plane(seeds, clearance=0.25)
    print(f"Generated {len(planes)} plane regions.")

    # 4. Plot
    fig, ax = plt.subplots(figsize=(12, 12))

    # Plot obstacles
    if fcu_obs:
        plot_poly(ax, fcu_obs, "red", 0.3)

    # Plot Plane
    for p in planes:
        plot_poly(ax, p, "green", 0.5)

    # Plot Seeds
    sx = [s[0] for s in seeds]
    sy = [s[1] for s in seeds]
    ax.scatter(sx, sy, color="blue", marker="x", label="Seeds")

    ax.set_aspect("equal")
    ax.legend()
    plt.title(f"Power Plane: {target_net.name}")

    output_file = Path("pcb/plane_experiment.png")
    plt.savefig(output_file)
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
