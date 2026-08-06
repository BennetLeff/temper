"""S5 Part 1 measurement: is `scipy.cluster.hierarchy` tie-breaking observable
in `router_v6/zone_emission.py`'s emitted zone geometry?

`_cluster_positions` runs `linkage(pdist(P), method="ward")` followed by
`fcluster(Z, t=threshold, criterion="distance")`.  Ward agglomeration is only
partially determined by the distances: when two candidate merges have equal
cost, scipy's nn-chain implementation breaks the tie by *point index order*.
PCB pads sit on regular pitches, so exact ties are expected to be common.

A Rust reimplementation would be free to break those ties differently.  The
question this script answers is not "do ties occur" but "does the tie-break
reach the output".  Permuting the input positions permutes exactly the index
order that scipy's tie-break consults, so the permutation sweep explores the
tie-break space directly.  Three levels are compared per trial:

  1. the label *partition* (which pads land together),
  2. the emitted hull *polygons*, canonicalised to a rotation-independent
     vertex multiset (does the zone cover different copper?),
  3. the emitted zone s-expressions as a *multiset* (exact bytes, ignoring
     which zone comes first),
  4. the emitted zone s-expressions as a *sequence* (byte order in the file).

Levels 3 and 4 are strictly stronger than level 2 and are reported separately
because `MultiPoint(...).convex_hull` starts its exterior ring at a vertex
chosen from input order: the same polygon can serialise to different bytes.
Attributing that to the clustering tie-break would be a false positive.

Inputs are the real per-net pad position sets of a `.kicad_pcb`, plus
synthetic regular grids constructed to maximise exact ties.

Usage:
    python tools/measurements/spike_zone_cluster_tie_invariance.py [BOARD]

Writes a JSON summary to stdout.  Read-only; touches no production code.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ZONE_EMISSION = REPO / "packages/temper-placer/src/temper_placer/router_v6/zone_emission.py"
DEFAULT_BOARD = REPO / "pcb/temper.kicad_pcb"
N_PERMUTATIONS = 64
SEED = 20260804


def _load_zone_emission() -> Any:
    """Import zone_emission.py by path (it has no temper_placer imports)."""
    spec = importlib.util.spec_from_file_location("_zone_emission", ZONE_EMISSION)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {ZONE_EMISSION}")
    mod = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves the defining module out of sys.modules, so the
    # module must be registered before exec_module runs.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def extract_pad_positions(board_path: Path) -> dict[str, list[tuple[float, float]]]:
    """Per-net pad world positions from a .kicad_pcb, via kiutils."""
    from kiutils.board import Board

    board = Board.from_file(str(board_path))
    out: dict[str, list[tuple[float, float]]] = {}
    for fp in board.footprints:
        if fp.position is None:
            continue
        fx, fy = float(fp.position.X), float(fp.position.Y)
        ang = math.radians(float(fp.position.angle or 0.0))
        ca, sa = math.cos(ang), math.sin(ang)
        for pad in fp.pads:
            if pad.net is None or not getattr(pad.net, "name", ""):
                continue
            px, py = float(pad.position.X), float(pad.position.Y)
            # KiCad footprint-child rotation (y-down frame).
            wx = fx + (px * ca + py * sa)
            wy = fy + (-px * sa + py * ca)
            out.setdefault(pad.net.name, []).append((wx, wy))
    return out


def synthetic_cases() -> dict[str, list[tuple[float, float]]]:
    """Position sets engineered to maximise exact Ward merge ties."""
    cases: dict[str, list[tuple[float, float]]] = {}
    pitch = 2.54
    cases["grid_6x6_pitch2.54"] = [(i * pitch, j * pitch) for i in range(6) for j in range(6)]
    cases["two_grids_4x4_sep80"] = [
        (i * pitch + off, j * pitch) for off in (0.0, 80.0) for i in range(4) for j in range(4)
    ]
    cases["line_16_pitch1.27"] = [(i * 1.27, 0.0) for i in range(16)]
    cases["three_clusters_2x3"] = [
        (i * pitch + off_x, j * pitch + off_y)
        for off_x, off_y in ((0.0, 0.0), (95.0, 0.0), (0.0, 95.0))
        for i in range(2)
        for j in range(3)
    ]
    return cases


def tie_stats(positions: list[tuple[float, float]]) -> dict[str, Any]:
    """Exact-tie census on the pairwise distances and on Ward merge heights."""
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    d = pdist(positions)
    dist_counts = Counter(float(v) for v in d)
    z = linkage(d, method="ward")
    heights = [float(v) for v in z[:, 2]]
    height_counts = Counter(heights)
    return {
        "n_points": len(positions),
        "n_pairs": int(d.size),
        "n_distinct_distances": len(dist_counts),
        "n_tied_distance_pairs": int(d.size) - len(dist_counts),
        "max_distance_multiplicity": max(dist_counts.values()),
        "n_merges": len(heights),
        "n_distinct_merge_heights": len(height_counts),
        "n_tied_merges": len(heights) - len(height_counts),
        "max_merge_multiplicity": max(height_counts.values()),
    }


def cut_margin(positions: list[tuple[float, float]], mod: Any) -> float | None:
    """Distance from the fcluster threshold to the nearest Ward merge height.

    A small margin means the cut sits *among* merges, where a differently
    tie-broken dendrogram is most likely to move a pad across the cut.
    """
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import pdist

    threshold = _threshold_for(positions, mod)
    if threshold is None:
        return None
    z = linkage(pdist(positions), method="ward")
    return min(abs(float(h) - threshold) for h in z[:, 2])


def _threshold_for(positions: list[tuple[float, float]], mod: Any) -> float | None:
    """Recompute `_cluster_positions`'s threshold (its pre-scipy prologue).

    Kept as an independent transcription so the script measures the threshold
    rather than assuming it; a mismatch would show up as a nonsense margin.
    """
    if len(positions) <= 2:
        return None
    nn: list[float] = []
    for i, (xi, yi) in enumerate(positions):
        best = float("inf")
        for j, (xj, yj) in enumerate(positions):
            if j == i:
                continue
            d2 = (xj - xi) ** 2 + (yj - yi) ** 2
            best = min(best, d2)
        nn.append(best**0.5 if best < float("inf") else 0.0)
    nn.sort()
    max_gap_ratio = 0.0
    threshold = nn[-1] if nn else 0.0
    for i in range(len(nn) - 1):
        if nn[i] > 0:
            ratio = (nn[i + 1] - nn[i]) / nn[i]
            if ratio > max_gap_ratio:
                max_gap_ratio = ratio
                threshold = (nn[i] + nn[i + 1]) / 2.0
    if max_gap_ratio < 1.0 or threshold < 0.5:
        idx = min(len(nn) - 1, int(len(nn) * 0.95))
        threshold = max(10.0, nn[idx]) if nn else 10.0
    return threshold


def _partition(
    positions: list[tuple[float, float]], mod: Any
) -> frozenset[frozenset[tuple[float, float]]]:
    return frozenset(frozenset(g) for g in mod._cluster_positions(positions))


def _canonical_polygons(zones: list[Any]) -> Counter[tuple[tuple[float, float], ...]]:
    """Zones as a rotation-independent multiset of rounded vertex tuples.

    The convex hull of a fixed point set is a fixed polygon; only the ring's
    starting vertex and winding follow input order.  Sorting the vertices
    quotients both out, so a difference here is a difference in *copper*.
    """
    out: Counter[tuple[tuple[float, float], ...]] = Counter()
    for z in zones:
        out[tuple(sorted((round(x, 6), round(y, 6)) for x, y in z.points))] += 1
    return out


def permutation_trial(name: str, positions: list[tuple[float, float]], mod: Any) -> dict[str, Any]:
    """Permute input order N times; report partition/geometry/order stability."""
    rng = random.Random(SEED)
    base_partition = _partition(positions, mod)
    base_zones = mod.compute_zones_for_net("NET", 1, list(positions), margin=1.0)
    base_exprs = [mod.emit_zone_s_expr(z) for z in base_zones]
    base_multiset = Counter(base_exprs)
    base_polys = _canonical_polygons(base_zones)

    partition_flips = 0
    polygon_flips = 0
    geometry_flips = 0
    order_flips = 0
    first_flip: dict[str, Any] | None = None

    for trial in range(N_PERMUTATIONS):
        perm = list(positions)
        rng.shuffle(perm)
        part = _partition(perm, mod)
        zones = mod.compute_zones_for_net("NET", 1, perm, margin=1.0)
        exprs = [mod.emit_zone_s_expr(z) for z in zones]

        p_flip = part != base_partition
        poly_flip = _canonical_polygons(zones) != base_polys
        g_flip = Counter(exprs) != base_multiset
        o_flip = exprs != base_exprs
        partition_flips += p_flip
        polygon_flips += poly_flip
        geometry_flips += g_flip
        order_flips += o_flip
        if (p_flip or poly_flip) and first_flip is None:
            first_flip = {
                "trial": trial,
                "base_n_clusters": len(base_partition),
                "perm_n_clusters": len(part),
                "base_cluster_sizes": sorted(len(c) for c in base_partition),
                "perm_cluster_sizes": sorted(len(c) for c in part),
                "permuted_positions": perm,
            }

    return {
        "case": name,
        "n_points": len(positions),
        "n_clusters": len(base_partition),
        "cut_margin": cut_margin(positions, mod),
        "ties": tie_stats(positions),
        "permutations": N_PERMUTATIONS,
        "partition_flips": partition_flips,
        "canonical_polygon_flips": polygon_flips,
        "sexpr_multiset_flips": geometry_flips,
        "zone_sequence_flips": order_flips,
        "first_flip": first_flip,
    }


def hull_ring_order_probe(mod: Any) -> dict[str, Any]:
    """Attribute the s-expression byte flips that are *not* clustering flips.

    `_convex_hull_from_positions` is called for every cluster, clustered or
    not.  For >=3 non-collinear points GEOS `convex_hull` is order-independent;
    for a degenerate 2-point cluster it returns a LineString whose `.buffer`
    ring *starts at a vertex chosen from input order*.  Same copper, different
    bytes.  This probe pins that attribution so the Part 1 verdict does not
    charge a GEOS artefact to scipy.
    """
    probes: dict[str, Any] = {}
    for label, pts in {
        "2pt_collinear": [(0.0, 0.0), (10.0, 0.0)],
        "3pt_triangle": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        "4pt_square": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
    }.items():
        fwd = mod._convex_hull_from_positions(list(pts), margin=1.0)
        rev = mod._convex_hull_from_positions(list(reversed(pts)), margin=1.0)
        probes[label] = {
            "n_vertices": len(fwd),
            "ring_sequence_equal": fwd == rev,
            "vertex_set_equal": sorted(fwd) == sorted(rev),
        }
    return probes


def main() -> int:
    board = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    mod = _load_zone_emission()

    cases: dict[str, list[tuple[float, float]]] = {}
    if board.exists():
        for net, pos in extract_pad_positions(board).items():
            if len(pos) > 2:
                cases[f"board:{net}"] = pos
    cases.update({f"synthetic:{k}": v for k, v in synthetic_cases().items()})

    results = [permutation_trial(n, p, mod) for n, p in sorted(cases.items())]

    def roll(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n_cases": len(rows),
            "n_cases_with_tied_distances": sum(
                1 for r in rows if r["ties"]["n_tied_distance_pairs"]
            ),
            "n_cases_with_tied_merges": sum(1 for r in rows if r["ties"]["n_tied_merges"]),
            "partition_flips": sum(r["partition_flips"] for r in rows),
            "canonical_polygon_flips": sum(r["canonical_polygon_flips"] for r in rows),
            "sexpr_multiset_flips": sum(r["sexpr_multiset_flips"] for r in rows),
            "zone_sequence_flips": sum(r["zone_sequence_flips"] for r in rows),
            "trials": len(rows) * N_PERMUTATIONS,
        }

    summary = {
        "board": str(board),
        "permutations_per_case": N_PERMUTATIONS,
        "seed": SEED,
        "real_board_nets": roll([r for r in results if r["case"].startswith("board:")]),
        "synthetic": roll([r for r in results if r["case"].startswith("synthetic:")]),
        "hull_ring_order_probe": hull_ring_order_probe(mod),
        "cases": results,
    }
    json.dump(summary, sys.stdout, indent=2, default=list)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
