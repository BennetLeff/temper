#!/usr/bin/env python3
"""Check candidate orthogonal grid links against exact native copper.

This is a feasibility audit, not a FastHenry deck or proof of all-path
connectivity. A failed link may be replaceable by a different native-contained
path; it must never be silently emitted or dropped from a claimed mesh.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict

import numpy as np
import shapely
from characterize_geometry import HERE, LAYERS, RAW, bore, sha, shape
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leg", choices=("A", "B"), required=True)
    parser.add_argument("--pitch", type=float, choices=(1.0, 0.5, 0.25, 0.125), required=True)
    parser.add_argument("--margin", type=float, choices=(5., 10., 20., 40.), required=True)
    args = parser.parse_args()
    raw = json.load(gzip.open(RAW, "rt"))
    port_path = HERE / "port-map.json"
    ports = json.loads(port_path.read_text())
    if raw["board_sha256"] != ports["board_sha256"] or sha(RAW) != ports["copper_export_sha256"]:
        raise ValueError("native data identity mismatch")
    rows = ports["legs"][args.leg]
    xy = [row[key] for row in rows for key in ("from_xy_mm", "to_xy_mm")]
    x0 = min(p[0] for p in xy) - args.margin
    y0 = min(p[1] for p in xy) - args.margin
    x1 = max(p[0] for p in xy) + args.margin
    y1 = max(p[1] for p in xy) + args.margin
    pitch = args.pitch
    xs = x0 + np.arange(int((x1 - x0) // pitch) + 1) * pitch
    ys = y0 + np.arange(int((y1 - y0) // pitch) + 1) * pitch
    xx, yy = np.meshgrid(xs, ys)
    roi = box(x0, y0, x1, y1)
    nets = {row["net"] for row in rows}
    by_nl = defaultdict(list)
    for item in raw["primitives"]:
        if item["net"] in nets and item["layer"] in LAYERS:
            candidate = shape(item)
            if candidate.intersects(roi):
                by_nl[item["net"], item["layer"]].append(candidate)
    bores = defaultdict(list)
    for item in raw["barrels"]:
        hole = bore(item)
        if hole is None or not hole.intersects(roi):
            continue
        a, b = (LAYERS.index(layer) for layer in item["physical_span_layers"])
        for layer in LAYERS[min(a, b):max(a, b) + 1]:
            bores[layer].append(hole)
    bore_geom = {layer: unary_union(items) for layer, items in bores.items()}
    report = {"board_sha256": raw["board_sha256"], "export_sha256": sha(RAW),
              "port_map_sha256": sha(port_path), "leg": args.leg,
              "pitch_mm": pitch, "margin_mm": args.margin,
              "roi_xy_mm": [x0, y0, x1, y1], "min_practical_width_mm": 0.020,
              "qualification": "CANDIDATE_GRID_LINK_AUDIT_ONLY", "net_layers": []}
    for (net, layer), items in sorted(by_nl.items()):
        geom = unary_union(items).difference(bore_geom.get(layer, Polygon()))
        native_roi = geom.intersection(roi)
        native_polys = [native_roi] if native_roi.geom_type == "Polygon" else (
            list(native_roi.geoms) if native_roi.geom_type == "MultiPolygon" else
            [g for g in getattr(native_roi, "geoms", ()) if g.geom_type == "Polygon"])
        mask = shapely.intersects_xy(geom, xx, yy)
        count = {"net": net, "layer": layer, "grid_nodes": int(mask.sum()),
                 "native_roi_polygon_components": len(native_polys),
                 "candidate_links": 0, "centerline_outside": 0,
                 "min_20um_rectangle_outside": 0, "nominal_rectangle_outside": 0,
                 "examples_20um_outside": []}
        center_pairs = []
        narrow_pairs = []
        for direction in ("horizontal", "vertical"):
            if direction == "horizontal":
                both = mask[:, :-1] & mask[:, 1:]
                jj, ii = np.nonzero(both)
                start = np.column_stack((xs[ii], ys[jj]))
                end = np.column_stack((xs[ii + 1], ys[jj]))
            else:
                both = mask[:-1, :] & mask[1:, :]
                jj, ii = np.nonzero(both)
                start = np.column_stack((xs[ii], ys[jj]))
                end = np.column_stack((xs[ii], ys[jj + 1]))
            count["candidate_links"] += len(start)
            node_a = jj * len(xs) + ii
            node_b = (jj * len(xs) + ii + 1) if direction == "horizontal" else ((jj + 1) * len(xs) + ii)
            for offset in range(0, len(start), 4096):
                first = start[offset:offset + 4096]
                last = end[offset:offset + 4096]
                lines = shapely.linestrings(np.stack((first, last), axis=1))
                inside = shapely.covers(geom, lines)
                count["centerline_outside"] += int((~inside).sum())
                if not inside.any():
                    continue
                local_a = node_a[offset:offset + 4096][inside]
                local_b = node_b[offset:offset + 4096][inside]
                center_pairs.extend(zip(local_a.tolist(), local_b.tolist(), strict=True))
                accepted_lines = lines[inside]
                narrow = shapely.buffer(accepted_lines, 0.010, cap_style="flat", quad_segs=1)
                narrow_ok = shapely.covers(geom, narrow)
                narrow_pairs.extend(zip(local_a[narrow_ok].tolist(), local_b[narrow_ok].tolist(), strict=True))
                count["min_20um_rectangle_outside"] += int((~narrow_ok).sum())
                full = shapely.buffer(accepted_lines, pitch / 2, cap_style="flat", quad_segs=1)
                count["nominal_rectangle_outside"] += int((~shapely.covers(geom, full)).sum())
                for point in first[inside][~narrow_ok][:max(0, 5 - len(count["examples_20um_outside"]))]:
                    count["examples_20um_outside"].append([float(point[0]), float(point[1]), direction])
        active = np.flatnonzero(mask.ravel())
        renumber = np.full(mask.size, -1, dtype=np.int32)
        renumber[active] = np.arange(len(active), dtype=np.int32)
        for label, pairs in (("centerline", center_pairs), ("min_20um", narrow_pairs)):
            if pairs:
                edges = np.asarray(pairs, dtype=np.int32)
                a = renumber[edges[:, 0]]
                b = renumber[edges[:, 1]]
                graph = coo_matrix((np.ones(len(a) * 2, dtype=np.int8),
                                    (np.r_[a, b], np.r_[b, a])), shape=(len(active), len(active))).tocsr()
                component_count, labels = connected_components(graph, directed=False)
            else:
                component_count = len(active)
                labels = np.arange(len(active), dtype=np.int32)
            count[f"{label}_components"] = int(component_count)
            sizes = np.bincount(labels, minlength=component_count)
            count[f"{label}_largest_component_nodes"] = int(sizes.max(initial=0))
            count[f"{label}_nonlargest_nodes"] = int(len(active) - sizes.max(initial=0))
            count[f"{label}_components_over_10_nodes"] = int((sizes > 10).sum())
        largest_label = int(np.argmax(sizes)) if len(sizes) else -1
        count["port_pad_coverage"] = []
        pad_refs = {ref for port in rows if port["net"] == net
                    for ref in (port["from_ref"], port["to_ref"])}
        for ref in sorted(pad_refs):
            pad_shapes = [shape(item) for item in raw["primitives"]
                          if item["kind"] == "pad" and item.get("ref") == ref
                          and item["net"] == net and item["layer"] == layer]
            if not pad_shapes:
                continue
            pad_geom = unary_union(pad_shapes)
            on_pad = shapely.intersects_xy(pad_geom, xx.ravel()[active], yy.ravel()[active])
            count["port_pad_coverage"].append({"ref": ref, "grid_nodes": int(on_pad.sum()),
                                               "nodes_in_largest_20um_component": int((labels[on_pad] == largest_label).sum()),
                                               "component_ids_20um": sorted(int(v) for v in np.unique(labels[on_pad]))})
        report["net_layers"].append(count)
        print(net, layer, count["candidate_links"], "links,", count["min_20um_rectangle_outside"],
              "centerline-contained links fail 20um width; components",
              count["centerline_components"], "->", count["min_20um_components"], flush=True)
    report["totals"] = {key: sum(row[key] for row in report["net_layers"])
                        for key in ("grid_nodes", "candidate_links", "centerline_outside",
                                    "min_20um_rectangle_outside", "nominal_rectangle_outside")}
    out = HERE / f"link-audit-{args.leg.lower()}-m{int(args.margin)}-p{str(pitch).replace('.', 'p')}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["totals"], indent=2))


if __name__ == "__main__":
    main()
