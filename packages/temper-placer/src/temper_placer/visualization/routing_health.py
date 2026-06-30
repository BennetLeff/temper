"""Routing health dashboard: EDT widths, capacity-demand, conflict clusters.

Overlays mathematical pipeline data onto the PCB board view to surface
hidden failure modes before routing begins.

Layout (3×3 grid, aligned to board coordinates):
  Row 1: [EDT Width Map (span 2)] [Bottleneck Widths]
  Row 2: [Routability Map] [Capacity-Demand] [Summary]
  Row 3: [Conflict Clusters (span 2)] [empty]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

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


def _board_aspect(bounds):
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    return w / max(h, 1.0)


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
    _check_plotly()
    min_x, min_y, max_x, max_y = board_bounds
    board_w = max_x - min_x
    board_h = max_y - min_y
    aspect = _board_aspect(board_bounds)

    # All board-coordinate panels share the same range with 2% padding
    pad_x = board_w * 0.02
    pad_y = board_h * 0.02
    x_range = [min_x - pad_x, max_x + pad_x]
    y_range = [min_y - pad_y, max_y + pad_y]

    # EDT heatmap row gets proportional height based on board aspect ratio.
    # For a 150×100mm board (aspect 1.5), EDT row = 500px to keep cells square-ish.
    edt_row_h = max(350, int(450 / max(aspect, 0.5)))

    fig = make_subplots(
        rows=3, cols=3,
        column_widths=[0.38, 0.32, 0.30],
        row_heights=[edt_row_h, 320, 280],
        subplot_titles=[
            "EDT Width Map",
            "Bottleneck Width per Net",
            None,
            "Routability Check",
            "Capacity-Demand Ratios",
            "Summary",
            "Spatial Conflict Clusters",
            None,
            None,
        ],
        specs=[
            [{"type": "heatmap", "colspan": 2}, None, {"type": "bar"}],
            [{"type": "xy"}, {"type": "scatter"}, {"type": "xy"}],
            [{"type": "scatter", "colspan": 2}, None, None],
        ],
        horizontal_spacing=0.05,
        vertical_spacing=0.06,
    )

    # ── Row 1, Col 1-2: EDT Width Heatmap ──
    if edt_grid is not None and edt_mask is not None:
        h_cells, w_cells = edt_grid.shape
        dx = board_w / w_cells
        dy = board_h / h_cells
        display = np.where(edt_mask, edt_grid * edt_cell_size * 2, np.nan)
        fig.add_trace(
            go.Heatmap(
                z=display,
                x0=min_x, dx=dx,
                y0=min_y, dy=dy,
                colorscale="RdYlGn_r",
                colorbar=dict(
                    title="Width mm",
                    orientation="h",
                    x=0.5, y=-0.18,
                    xanchor="center", yanchor="top",
                    len=0.6, thickness=12,
                    tickfont=dict(size=10),
                ),
                zmin=0,
                zmax=max(10.0, float(np.nanmax(display))),
                hoverongaps=False,
                name="EDT Width",
            ),
            row=1, col=1,
        )
        fig.update_xaxes(title_text="X (mm)", title_font=dict(size=11),
                         row=1, col=1, range=x_range, constrain="domain")
        fig.update_yaxes(title_text="Y (mm)", title_font=dict(size=11),
                         row=1, col=1, range=y_range,
                         scaleanchor="x", scaleratio=1.0, constrain="domain")

    # ── Row 1, Col 3: Bottleneck Widths ──
    if bottleneck_widths:
        items = sorted(bottleneck_widths.items(), key=lambda x: x[1])
        names = [n for n, _ in items]
        widths = [w for _, w in items]
        colors = [
            "#F44336" if w < 0.5 else "#FF9800" if w < 2.0 else "#4CAF50"
            for w in widths
        ]
        fig.add_trace(
            go.Bar(x=names, y=widths, marker_color=colors, name="Bottleneck",
                   hovertemplate="%{x}: %{y:.2f}mm<extra></extra>"),
            row=1, col=3,
        )
        fig.add_hline(y=0.5, line_dash="dash", line_color="red", row=1, col=3,
                       annotation_text="critical")
        fig.update_xaxes(title_text="", tickangle=90, tickfont=dict(size=8),
                         row=1, col=3)
        fig.update_yaxes(title_text="Min Width (mm)", title_font=dict(size=10),
                         row=1, col=3)

    # ── Row 2, Col 1: Routability Map ──
    if routability and net_bboxes:
        xs, ys, cs, ts = [], [], [], []
        for net_name, ok in routability.items():
            bbox = net_bboxes.get(net_name)
            if bbox:
                xs.append((bbox[0] + bbox[2]) / 2)
                ys.append((bbox[1] + bbox[3]) / 2)
                cs.append("#4CAF50" if ok else "#F44336")
                ts.append(net_name)
        if xs:
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys, mode="markers+text",
                    text=ts, textposition="top center", textfont=dict(size=8, color="#333"),
                    marker=dict(size=10, color=cs, symbol="square",
                                line=dict(width=1, color="white")),
                    name="Routability",
                ),
                row=2, col=1,
            )
            fig.add_shape(type="rect", x0=min_x, y0=min_y, x1=max_x, y1=max_y,
                          line=dict(color="gray", dash="dot"), row=2, col=1)
        fig.update_xaxes(title_text="X (mm)", title_font=dict(size=11),
                         row=2, col=1, range=x_range)
        fig.update_yaxes(title_text="Y (mm)", title_font=dict(size=11),
                         row=2, col=1, range=y_range)

    # ── Row 2, Col 2: Capacity-Demand Scatter ──
    if capacity_ratios and net_bboxes:
        names = list(capacity_ratios.keys())
        ratios = [capacity_ratios[n] for n in names]
        cs = ["#4CAF50" if r >= 1.0 else "#F44336" for r in ratios]
        if bottleneck_widths:
            x_vals = [bottleneck_widths.get(n, 0) for n in names]
            x_label = "Bottleneck Width (mm)"
        else:
            x_vals = [(net_bboxes[n][2]-net_bboxes[n][0])*(net_bboxes[n][3]-net_bboxes[n][1])
                      if n in net_bboxes else 0 for n in names]
            x_label = "Net Area (mm²)"
        fig.add_trace(
            go.Scatter(
                x=x_vals, y=ratios, mode="markers",
                text=names,
                marker=dict(size=7, color=cs),
                hovertemplate="%{text}: %{y:.1f}x (%{x:.2f}mm)<extra></extra>",
            ),
            row=2, col=2,
        )
        fig.add_hline(y=1.0, line_dash="dash", line_color="red", row=2, col=2)
        fig.update_xaxes(title_text=x_label, title_font=dict(size=10), row=2, col=2)
        fig.update_yaxes(title_text="C/D Ratio", title_font=dict(size=10), row=2, col=2)

    # ── Row 2, Col 3: Summary ──
    lines = []
    if routability:
        lines.append(f"Routable: {sum(1 for v in routability.values() if v)}/{len(routability)}")
    if capacity_ratios:
        lines.append(f"At-risk: {sum(1 for v in capacity_ratios.values() if v < 1.0)}")
    if bottleneck_widths:
        lines.append(f"Critical: {sum(1 for v in bottleneck_widths.values() if v < 0.5)}")
    if conflict_clusters:
        lines.append(f"Clusters: {len(conflict_clusters)}")
    if edt_grid is not None and edt_mask is not None:
        lines.append(f"Area: {100*np.sum(edt_mask)/edt_mask.size:.1f}%")
    text = "<br>".join(lines) if lines else "No data"
    fig.add_annotation(
        text=f"<b>Summary</b><br><br>{text}",
        xref="x6 domain", yref="y6 domain",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=12, color="#333"),
        row=2, col=3,
    )
    fig.update_xaxes(visible=False, row=2, col=3)
    fig.update_yaxes(visible=False, row=2, col=3)

    # ── Row 3, Col 1-2: Conflict Clusters ──
    if conflict_clusters and net_bboxes:
        n_clusters = len(conflict_clusters)
        for ci, cluster in enumerate(conflict_clusters):
            cxs, cys, cts = [], [], []
            for net_name in cluster:
                bbox = net_bboxes.get(net_name)
                if bbox:
                    cxs.append((bbox[0] + bbox[2]) / 2)
                    cys.append((bbox[1] + bbox[3]) / 2)
                    cts.append(net_name)
            if cxs:
                hue = ci * 360 // max(1, n_clusters)
                fig.add_trace(
                    go.Scatter(
                        x=cxs, y=cys, mode="markers+text",
                        text=cts, textposition="top center", textfont=dict(size=7, color="#555"),
                        marker=dict(size=8, color=f"hsl({hue},70%,50%)"),
                        name=f"C{ci+1} ({len(cluster)})",
                    ),
                    row=3, col=1,
                )
        fig.add_shape(type="rect", x0=min_x, y0=min_y, x1=max_x, y1=max_y,
                      line=dict(color="gray", dash="dot"), row=3, col=1)
        fig.update_xaxes(title_text="X (mm)", title_font=dict(size=11),
                         row=3, col=1, range=x_range, constrain="domain")
        fig.update_yaxes(title_text="Y (mm)", title_font=dict(size=11),
                         row=3, col=1, range=y_range, constrain="domain")

    # ── Global layout ──
    fig.update_layout(
        title=dict(text=title, font=dict(size=16), x=0.5),
        height=edt_row_h + 320 + 280 + 100,
        width=1400,
        showlegend=False,
        margin=dict(t=50, b=30, l=30, r=30),
        plot_bgcolor="rgba(245,245,245,1)",
        paper_bgcolor="white",
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
    """Build a full routing health dashboard from pipeline state."""
    from temper_placer.router_v6.capacity_check import compute_capacity_demand_ratios
    from temper_placer.router_v6.channel_widths import _build_edt

    edt = mask = None
    board_bounds = (0, 0, 1, 1)
    if stage2_output.routing_spaces:
        rs = next(iter(stage2_output.routing_spaces.values()))
        board_bounds = rs.available_area.bounds
        try:
            edt, mask, _ = _build_edt(rs, 0.1, use_cache=True)
        except Exception:
            pass

    capacities = None
    try:
        capacities = compute_capacity_demand_ratios(stage2_output, parsed_pcb)
    except Exception:
        pass

    net_bboxes = {}
    comp_by_ref = {c.ref: c for c in parsed_pcb.components}
    for net in parsed_pcb.nets:
        positions = [
            comp_by_ref[r].initial_position
            for r, _ in net.pins
            if r in comp_by_ref and comp_by_ref[r].initial_position
        ]
        if len(positions) >= 2:
            xs = [p[0] for p in positions]; ys = [p[1] for p in positions]
            net_bboxes[net.name] = (min(xs), min(ys), max(xs), max(ys))

    bottleneck_widths = None
    if edt is not None and mask is not None and net_bboxes and channel_mapping:
        from temper_placer.router_v6.astar_pathfinding import _compute_bottleneck_widths
        try:
            bottleneck_widths = _compute_bottleneck_widths(
                edt, mask, board_bounds, channel_mapping, 0.1,
            )
        except Exception:
            pass

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

    conflict_clusters = None
    if channel_mapping and net_bboxes:
        from temper_placer.router_v6.astar_pathfinding import _compute_net_order
        ordered = _compute_net_order(channel_mapping)
        if len(ordered) > 1:
            threshold = 0.1
            graph = {n: set() for n in ordered}
            nlist = list(ordered)
            for i in range(len(nlist)):
                a = nlist[i]
                if a not in net_bboxes: continue
                ax1, ay1, ax2, ay2 = net_bboxes[a]
                area_a = (ax2-ax1)*(ay2-ay1)
                if area_a <= 0: continue
                for j in range(i+1, len(nlist)):
                    b = nlist[j]
                    if b not in net_bboxes: continue
                    bx1, by1, bx2, by2 = net_bboxes[b]
                    area_b = (bx2-bx1)*(by2-by1)
                    if area_b <= 0: continue
                    ox = max(0.0, min(ax2,bx2)-max(ax1,bx1))
                    oy = max(0.0, min(ay2,by2)-max(ay1,by1))
                    if ox*oy / min(area_a,area_b) > threshold:
                        graph[a].add(b); graph[b].add(a)
            visited = set()
            conflict_clusters = []
            for net in ordered:
                if net in visited: continue
                queue = [net]; cluster = []
                while queue:
                    n = queue.pop()
                    if n in visited: continue
                    visited.add(n); cluster.append(n)
                    for nb in graph.get(n, set()):
                        if nb not in visited: queue.append(nb)
                conflict_clusters.append(cluster)

    return routing_health_dashboard(
        board_bounds=board_bounds,
        edt_grid=edt, edt_mask=mask, edt_cell_size=0.1,
        capacity_ratios=capacities,
        net_bboxes=net_bboxes,
        bottleneck_widths=bottleneck_widths,
        routability=routability,
        conflict_clusters=conflict_clusters,
        output_path=output_path,
    )
