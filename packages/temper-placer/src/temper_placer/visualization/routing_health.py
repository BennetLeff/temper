"""Routing health dashboard: EDT widths, capacity-demand, conflict clusters.

Overlays mathematical pipeline data onto the PCB board view to surface
hidden failure modes before routing begins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# Plotly is optional for headless environments
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None
    make_subplots = None


def _check_plotly():
    if not PLOTLY_AVAILABLE:
        raise ImportError("plotly is required for routing health dashboard")


def routing_health_dashboard(
    board_bounds: tuple[float, float, float, float],
    edt_grid: np.ndarray | None = None,
    edt_mask: np.ndarray | None = None,
    edt_cell_size: float = 0.1,
    capacity_ratios: dict[str, float] | None = None,
    net_bboxes: dict[str, tuple[float, float, float, float]] | None = None,
    bottleneck_widths: dict[str, float] | None = None,
    routability: dict[str, bool] | None = None,
    conflict_clusters: list[list[str]] | None = None,
    title: str = "Routing Health Dashboard",
    output_path: str | Path | None = None,
) -> go.Figure:
    """Render a multi-panel dashboard for routing health assessment.

    Panel layout (3×2):
      [EDT Width Map]    [Capacity-Demand Ratios]
      [Bottleneck Widths] [Routability Results]
      [Conflict Graph]   [Summary Stats]

    Args:
        board_bounds: (min_x, min_y, max_x, max_y) in mm.
        edt_grid: Euclidean Distance Transform grid (cells).
        edt_mask: Boolean mask where True = interior.
        edt_cell_size: Cell size in mm for the EDT grid.
        capacity_ratios: {net_name: capacity/demand ratio}.
        net_bboxes: {net_name: (min_x, min_y, max_x, max_y)}.
        bottleneck_widths: {net_name: min_edt_width_mm}.
        routability: {net_name: is_routable}.
        conflict_clusters: List of clusters, each a list of net names.
        title: Dashboard title.
        output_path: If provided, save HTML to this path.
    """
    _check_plotly()
    min_x, min_y, max_x, max_y = board_bounds
    w, h = max_x - min_x, max_y - min_y

    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=[
            "EDT Width Map (narrow → wide)",
            "Capacity-Demand Ratios",
            "Bottleneck Width per Net",
            "Routability Check",
            "Conflict Clusters",
            "Summary",
        ],
        specs=[
            [{"type": "heatmap"}, {"type": "xy"}, {"type": "bar"}],
            [{"type": "xy"}, {"type": "xy"}, {"type": "xy"}],
        ],
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    # --- Panel 1: EDT Width Heatmap ---
    if edt_grid is not None and edt_mask is not None:
        w_cells = edt_grid.shape[1]
        h_cells = edt_grid.shape[0]
        # Show interior cells only, colored by width
        display = np.where(edt_mask, edt_grid * edt_cell_size * 2, np.nan)
        fig.add_trace(
            go.Heatmap(
                z=display,
                x0=min_x, dx=(max_x - min_x) / w_cells,
                y0=min_y, dy=(max_y - min_y) / h_cells,
                colorscale="RdYlGn_r",
                colorbar=dict(title="Width mm", x=0.32),
                zmin=0,
                zmax=max(10.0, float(np.nanmax(display))),
                hoverongaps=False,
                name="EDT Width",
            ),
            row=1, col=1,
        )
        fig.update_xaxes(title_text="X (mm)", row=1, col=1, range=[min_x, max_x])
        fig.update_yaxes(title_text="Y (mm)", row=1, col=1, range=[min_y, max_y])

    # --- Panel 2: Capacity-Demand Scatter ---
    if capacity_ratios and net_bboxes:
        net_names = list(capacity_ratios.keys())
        ratios = [capacity_ratios[n] for n in net_names]
        colors = ["#4CAF50" if r >= 1.0 else "#F44336" for r in ratios]
        areas = [
            (net_bboxes[n][2] - net_bboxes[n][0]) * (net_bboxes[n][3] - net_bboxes[n][1])
            if n in net_bboxes else 0
            for n in net_names
        ]
        fig.add_trace(
            go.Scatter(
                x=areas,
                y=ratios,
                mode="markers+text",
                text=net_names,
                textposition="top center",
                marker=dict(size=8, color=colors),
                name="Capacity/Demand",
                hovertemplate="%{text}: %{y:.1f}x<br>area=%{x:.0f}mm²<extra></extra>",
            ),
            row=1, col=2,
        )
        fig.add_hline(y=1.0, line_dash="dash", line_color="red", row=1, col=2)
        fig.update_xaxes(title_text="Net Area (mm²)", row=1, col=2)
        fig.update_yaxes(title_text="Capacity/Demand Ratio", row=1, col=2)

    # --- Panel 3: Bottleneck Widths ---
    if bottleneck_widths:
        sorted_nets = sorted(bottleneck_widths.items(), key=lambda x: x[1])
        names = [n for n, _ in sorted_nets]
        widths = [w for _, w in sorted_nets]
        colors = ["#F44336" if w < 0.5 else "#FF9800" if w < 2.0 else "#4CAF50" for w in widths]
        fig.add_trace(
            go.Bar(
                x=names,
                y=widths,
                marker_color=colors,
                name="Bottleneck",
                hovertemplate="%{x}: %{y:.2f}mm<extra></extra>",
            ),
            row=1, col=3,
        )
        fig.add_hline(y=0.5, line_dash="dash", line_color="red", row=1, col=3,
                       annotation_text="critical")
        fig.update_xaxes(title_text="Net", tickangle=45, row=1, col=3)
        fig.update_yaxes(title_text="Min Channel Width (mm)", row=1, col=3)

    # --- Panel 4: Routability Pass/Fail ---
    if routability and net_bboxes:
        xs, ys, colors_r, texts = [], [], [], []
        for net_name, ok in routability.items():
            if net_name in net_bboxes:
                bbox = net_bboxes[net_name]
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                xs.append(cx)
                ys.append(cy)
                colors_r.append("#4CAF50" if ok else "#F44336")
                texts.append(f"{net_name}: {'✓' if ok else '✗'}")

        if xs:
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="markers+text",
                    text=texts, textposition="top center",
                    marker=dict(size=14, color=colors_r, symbol="square"),
                    name="Routability",
                    hovertemplate="%{text}<extra></extra>",
                ),
                row=2, col=1,
            )
            # Add board outline
            fig.add_shape(type="rect", x0=min_x, y0=min_y, x1=max_x, y1=max_y,
                          line=dict(color="gray", dash="dot"),
                          row=2, col=1)
        fig.update_xaxes(title_text="X (mm)", row=2, col=1, range=[min_x, max_x])
        fig.update_yaxes(title_text="Y (mm)", row=2, col=1, range=[min_y, max_y])

    # --- Panel 5: Conflict Clusters ---
    if conflict_clusters and net_bboxes:
        cluster_colors = [
            f"hsl({i * 360 // max(1, len(conflict_clusters))}, 70%, 50%)"
            for i in range(len(conflict_clusters))
        ]
        for ci, cluster in enumerate(conflict_clusters):
            cxs, cys = [], []
            for net_name in cluster:
                if net_name in net_bboxes:
                    bbox = net_bboxes[net_name]
                    cxs.append((bbox[0] + bbox[2]) / 2)
                    cys.append((bbox[1] + bbox[3]) / 2)
            if cxs:
                fig.add_trace(
                    go.Scatter(
                        x=cxs, y=cys, mode="markers",
                        marker=dict(size=10, color=cluster_colors[ci % len(cluster_colors)]),
                        name=f"Cluster {ci + 1} ({len(cluster)} nets)",
                        hovertemplate="Cluster %{text}<extra></extra>",
                        text=cluster * len(cxs),
                    ),
                    row=2, col=2,
                )
        fig.add_shape(type="rect", x0=min_x, y0=min_y, x1=max_x, y1=max_y,
                      line=dict(color="gray", dash="dot"), row=2, col=2)
        fig.update_xaxes(title_text="X (mm)", row=2, col=2, range=[min_x, max_x])
        fig.update_yaxes(title_text="Y (mm)", row=2, col=2, range=[min_y, max_y])

    # --- Panel 6: Summary Stats ---
    summary_lines = []
    if routability:
        routable = sum(1 for v in routability.values() if v)
        summary_lines.append(f"Routable: {routable}/{len(routability)}")
    if capacity_ratios:
        at_risk = sum(1 for v in capacity_ratios.values() if v < 1.0)
        summary_lines.append(f"At-risk nets: {at_risk}/{len(capacity_ratios)}")
    if bottleneck_widths:
        critical = sum(1 for v in bottleneck_widths.values() if v < 0.5)
        summary_lines.append(f"Critical bottlenecks: {critical}")
    if conflict_clusters:
        summary_lines.append(f"Conflict clusters: {len(conflict_clusters)}")
        max_cluster = max(len(c) for c in conflict_clusters) if conflict_clusters else 0
        summary_lines.append(f"Largest cluster: {max_cluster} nets")
    if edt_grid is not None and edt_mask is not None:
        total = np.sum(edt_mask)
        interior = np.sum(edt_mask)
        summary_lines.append(f"Routing cells: {interior:,} / {edt_mask.size:,}")

    summary_text = "<br>".join(summary_lines) if summary_lines else "No data"
    fig.add_annotation(
        text=summary_text,
        xref="x6 domain", yref="y6 domain",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14),
        row=2, col=3,
    )
    fig.update_xaxes(visible=False, row=2, col=3)
    fig.update_yaxes(visible=False, row=2, col=3)

    # --- Layout ---
    fig.update_layout(
        title=dict(text=title, font=dict(size=18)),
        height=900,
        width=1400,
        showlegend=False,
        margin=dict(t=60, b=40, l=40, r=40),
    )

    if output_path:
        fig.write_html(str(output_path))

    return fig


def build_dashboard_from_pipeline(
    parsed_pcb: Any,
    stage2_output: Any,
    channel_mapping: Any | None = None,
    output_path: str | Path | None = None,
) -> go.Figure:
    """Build a full routing health dashboard from pipeline state.

    This is the main entry point for generating a dashboard from a running
    pipeline.  It orchestrates all the mathematical modules we've built.

    Args:
        parsed_pcb: ParsedPCB from Stage 0.
        stage2_output: Stage2Output from _run_stage2().
        channel_mapping: Optional ChannelMapping for net ordering context.
        output_path: Optional path to save HTML.
    """
    from temper_placer.router_v6.capacity_check import compute_capacity_demand_ratios
    from temper_placer.router_v6.channel_widths import _build_edt

    # EDT from Stage 2
    edt, mask, bounds = None, None, None
    min_x = min_y = max_x = max_y = 0.0
    if stage2_output.routing_spaces:
        rs = next(iter(stage2_output.routing_spaces.values()))
        board_bounds = rs.available_area.bounds
        try:
            edt, mask, bounds = _build_edt(rs, 0.1, use_cache=True)
        except Exception:
            pass
    else:
        board_bounds = (0, 0, 1, 1)

    # Capacity-demand ratios
    capacities = None
    try:
        capacities = compute_capacity_demand_ratios(stage2_output, parsed_pcb)
    except Exception:
        pass

    # Net bounding boxes from components
    net_bboxes = {}
    comp_by_ref = {c.ref: c for c in parsed_pcb.components}
    for net in parsed_pcb.nets:
        positions = [
            comp_by_ref[r].initial_position
            for r, _ in net.pins if r in comp_by_ref and comp_by_ref[r].initial_position
        ]
        if len(positions) >= 2:
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            net_bboxes[net.name] = (min(xs), min(ys), max(xs), max(ys))

    # Bottleneck widths (computed from EDT)
    bottleneck_widths = None
    if edt is not None and mask is not None and net_bboxes:
        from temper_placer.router_v6.astar_pathfinding import (
            _compute_bottleneck_widths,
        )
        try:
            bottleneck_widths = _compute_bottleneck_widths(
                edt, mask, bounds, channel_mapping, 0.1
            )
        except Exception:
            pass

    # Routability checks
    routability = None
    if edt is not None and mask is not None and net_bboxes:
        from temper_placer.router_v6.routability_check import check_routability_direct
        routability = {}
        for net_name, bbox in net_bboxes.items():
            try:
                ok = check_routability_direct(
                    (bbox[0], bbox[1]), (bbox[2], bbox[3]),
                    edt, mask, 0.1, trace_width=0.2,
                )
                routability[net_name] = ok
            except Exception:
                routability[net_name] = False

    # Conflict clusters (from net ordering)
    conflict_clusters = None
    if channel_mapping:
        from temper_placer.router_v6.astar_pathfinding import _compute_net_order
        # Re-run ordering to get clusters (side effect: _compute_net_order
        # computes clusters internally; we need to extract them)
        # For now, just get the ordered list and reconstruct simple clusters
        ordered = _compute_net_order(channel_mapping)
        # Simple: if we have net_bboxes, group by spatial overlap threshold
        if net_bboxes and len(ordered) > 1:
            threshold = 0.1
            conflict_graph = {n: set() for n in ordered}
            net_list = list(ordered)
            for i in range(len(net_list)):
                a = net_list[i]
                if a not in net_bboxes:
                    continue
                ax1, ay1, ax2, ay2 = net_bboxes[a]
                area_a = (ax2 - ax1) * (ay2 - ay1)
                if area_a <= 0:
                    continue
                for j in range(i + 1, len(net_list)):
                    b = net_list[j]
                    if b not in net_bboxes:
                        continue
                    bx1, by1, bx2, by2 = net_bboxes[b]
                    area_b = (bx2 - bx1) * (by2 - by1)
                    if area_b <= 0:
                        continue
                    ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
                    oy = max(0.0, min(ay2, by2) - max(ay1, by1))
                    overlap = ox * oy
                    if overlap / min(area_a, area_b) > threshold:
                        conflict_graph[a].add(b)
                        conflict_graph[b].add(a)
            visited = set()
            conflict_clusters = []
            for net in ordered:
                if net in visited:
                    continue
                queue = [net]
                cluster = []
                while queue:
                    n = queue.pop()
                    if n in visited:
                        continue
                    visited.add(n)
                    cluster.append(n)
                    for neighbor in conflict_graph.get(n, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                conflict_clusters.append(cluster)

    return routing_health_dashboard(
        board_bounds=board_bounds,
        edt_grid=edt,
        edt_mask=mask,
        edt_cell_size=0.1,
        capacity_ratios=capacities,
        net_bboxes=net_bboxes,
        bottleneck_widths=bottleneck_widths,
        routability=routability,
        conflict_clusters=conflict_clusters,
        output_path=output_path,
    )
