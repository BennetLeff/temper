

import matplotlib.pyplot as plt
import numpy as np

from temper_placer.router_v6.astar_pathfinding import _extract_pad_centers_per_net
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.router_v6.test_boards import get_available_boards


def plot_debug():
    boards = get_available_boards()
    piantor = boards[0]
    print(f'Board: {piantor.name}')

    print('Running Router V6...')
    pipeline = RouterV6Pipeline(verbose=False)
    result = pipeline.run(piantor.path)
    routes = result.stage4.pathfinding_result.routed_paths

    # Extract Pads (Absolute)
    pad_info = _extract_pad_centers_per_net(result.pcb)

    # Get Origin
    origin = (0.0, 0.0)
    if hasattr(result.pcb.board, 'origin'):
        origin = result.pcb.board.origin
    print(f'Origin: {origin}')

    plt.figure(figsize=(12, 12))

    # Plot Pads
    sides = []
    for comp in result.pcb.components:
        sides.append(getattr(comp, 'initial_side', 0))

    from collections import Counter
    side_counts = Counter(sides)
    print(f"Component Sides: {side_counts}")

    for net, pads in pad_info.items():
        if not pads:
            continue
        px = [p[0] for p in pads]
        py = [p[1] for p in pads]
        plt.scatter(px, py, c='blue', s=20, alpha=0.5, label='Pads' if net==list(pad_info.keys())[0] else "")

    # Plot Routes (With Origin Fix)
    for net, path in routes.items():
        if not path.coordinates:
            continue

        # Apply Origin Fix
        rx = [p[0] + origin[0] for p in path.coordinates]
        ry = [p[1] + origin[1] for p in path.coordinates]

        plt.plot(rx, ry, 'r-', linewidth=1, alpha=0.7, label='Routes' if net==list(routes.keys())[0] else "")

        # Plot raw routes (without origin) for comparison
        # rx_raw = [p[0] for p in path.coordinates]
        # ry_raw = [p[1] for p in path.coordinates]
        # plt.plot(rx_raw, ry_raw, 'g--', linewidth=0.5, alpha=0.3)

    plt.title(f"Route vs Pad Alignment (Origin={origin})")
    plt.grid(True)
    plt.legend()
    plt.axis('equal')

    # Calculate Centroids
    all_px = []
    all_py = []
    for pads_list in pad_info.values():
        for p in pads_list:
            all_px.append(p[0])
            all_py.append(p[1])

    # Calculate Gaps
    gaps = []
    found_nets = 0
    for net, path in routes.items():
        if not path.coordinates or net not in pad_info:
            continue

        found_nets += 1
        p_start = path.coordinates[0]
        p_end = path.coordinates[-1]

        # Find closest pad for start and end
        pads = pad_info[net]

        def min_dist(p, pads):
            return min(np.sqrt((p[0]-pad[0])**2 + (p[1]-pad[1])**2) for pad in pads)

        d_start = min_dist(p_start, pads)
        d_end = min_dist(p_end, pads)
        gaps.extend([d_start, d_end])

    if gaps:
        print(f"Gap Analysis ({found_nets} nets):")
        print(f"  Mean Gap:   {np.mean(gaps):.4f} mm")
        print(f"  Max Gap:    {np.max(gaps):.4f} mm")
        print(f"  Min Gap:    {np.min(gaps):.4f} mm")
        print(f"  Median Gap: {np.median(gaps):.4f} mm")

    output_png = '/tmp/debug_alignment_option_h.png'
    plt.savefig(output_png)
    print(f'Saved debug plot to {output_png}')

if __name__ == "__main__":
    plot_debug()
