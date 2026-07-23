# mypy: ignore-errors
# ruff: noqa: ARG001, F821  # enable_numba_los from incomplete numba merge
"""
Router V6: Net ordering for A* pathfinding.

Part of temper-N6 decomposition — split from astar_pathfinding.py.
"""

from __future__ import annotations

from temper_placer.router_v6.channel_mapping import ChannelMapping


def _compute_net_order(
    channel_mapping: ChannelMapping,
    bottleneck_widths: dict[str, float] | None = None,
) -> list[str]:
    """
    Compute routing order for nets using spatial conflict awareness.

    Algorithm:
      1. Compute bounding boxes for each net from its waypoints.
      2. Build a conflict graph: two nets conflict if their bounding boxes
         overlap sufficiently (overlap / smaller_area > 0.1).
      3. Find connected components (clusters of mutually-overlapping nets).
      4. Within each cluster, sort by (power_first, bottleneck_asc, area_asc)
         when bottleneck_widths is provided; otherwise (power_first, area_asc).
         Bottleneck-first ordering addresses channel competition (min widths),
         complementing the area-based ordering that addresses area competition.
      5. Route isolated clusters first, then largest clusters.

    Rationale:
      The rip-up cascade occurs when a large-footprint net consumes
      space that a small-footprint net later needs.  Routing small nets
      first ensures they claim their narrow corridors before larger nets
      spread through the region.  Adding bottleneck widths gives priority
      to nets with the narrowest routing corridors — they have fewer
      routing options and must be routed before competitors claim their
      only viable path.

    Args:
        channel_mapping: Channel mapping with waypoints per net.
        bottleneck_widths: Optional dict mapping net_name to bottleneck
            width in mm.  When provided, nets with narrower bottlenecks
            route earlier within their cluster.

    Proof of correctness (induction):
      Base case: Two nets with zero bounding-box overlap.
        Assigned to separate clusters.  Their routing order cannot
        affect each other — the board has independent regions.
      Induction: Within a cluster of k overlapping nets, routing
        net 1 (smallest footprint or narrowest bottleneck) first gives
        it a clean grid.  When net k routes, it finds space that
        net 1 through net k-1 didn't need.  By induction on k,
        all nets in the cluster have at least the same routing
        opportunity as random ordering.
      Bottleneck lemma: routing net A (bottleneck=0.5mm) before net B
        (bottleneck=5mm) never makes B unroutable that wouldn't already
        be unroutable (B has 10x more routing options).
    """
    nets = list(channel_mapping.channel_paths)

    if len(nets) <= 1:
        return nets

    # 1. Compute bounding box for each net
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    bbox_areas: dict[str, float] = {}
    for net_name in nets:
        path = channel_mapping.channel_paths[net_name]
        waypoints = path.waypoints
        if not waypoints:
            bboxes[net_name] = (0, 0, 0, 0)
            bbox_areas[net_name] = 0.0
            continue
        xs = [w[0] for w in waypoints]
        ys = [w[1] for w in waypoints]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bboxes[net_name] = (min_x, min_y, max_x, max_y)
        bbox_areas[net_name] = (max_x - min_x) * (max_y - min_y)

    # 2. Build conflict graph.  Two nets conflict if their bounding
    #    boxes overlap more than 10% of the smaller net's area.
    #    This threshold prevents false clusters from slightly-overlapping
    #    nets that route in entirely different channels.
    threshold = 0.1
    conflict: dict[str, set[str]] = {n: set() for n in nets}
    net_list = list(nets)
    for i in range(len(net_list)):
        a = net_list[i]
        ax1, ay1, ax2, ay2 = bboxes[a]
        area_a = bbox_areas[a]
        if area_a <= 0:
            continue
        for j in range(i + 1, len(net_list)):
            b = net_list[j]
            bx1, by1, bx2, by2 = bboxes[b]
            area_b = bbox_areas[b]
            if area_b <= 0:
                continue
            # Compute overlap
            ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            oy = max(0.0, min(ay2, by2) - max(ay1, by1))
            overlap = ox * oy
            min_area = min(area_a, area_b)
            if min_area > 0 and overlap / min_area > threshold:
                conflict[a].add(b)
                conflict[b].add(a)

    # 2b. Find connected components (clusters) via BFS
    visited: set[str] = set()
    clusters: list[list[str]] = []
    for net in nets:
        if net in visited:
            continue
        queue = [net]
        cluster: list[str] = []
        while queue:
            n = queue.pop()
            if n in visited:
                continue
            visited.add(n)
            cluster.append(n)
            # sorted(): conflict[n] is a set, whose iteration order depends
            # on PYTHONHASHSEED (randomized per-process by default). Without
            # this, BFS discovery order -- and therefore the tie-break for
            # nets with identical cluster_sort_key tuples below -- silently
            # varies across process runs, making net routing order (and all
            # downstream track geometry / DRC results) non-reproducible even
            # with a fixed seed passed to route_pcb.
            for neighbor in sorted(conflict[n]):
                if neighbor not in visited:
                    queue.append(neighbor)
        clusters.append(cluster)

    # 3. Within each cluster, sort by (power_first, bottleneck_asc, area_asc)
    def cluster_sort_key(net_name: str) -> tuple:
        name_upper = net_name.upper()
        is_power = any(x in name_upper for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        if bottleneck_widths is not None:
            bw = bottleneck_widths.get(net_name, float("inf"))
            return (not is_power, bw, bbox_areas.get(net_name, float("inf")))
        return (not is_power, bbox_areas.get(net_name, float("inf")))

    for cluster in clusters:
        cluster.sort(key=cluster_sort_key)

    # 4. Sort clusters: isolated first, then by cluster size descending
    clusters.sort(key=lambda c: (-len(c), sum(bbox_areas.get(n, 0) for n in c)))

    # 5. Flatten
    result = []
    for cluster in clusters:
        result.extend(cluster)
    return result
