"""Apply the nine spike/Phase-A agents' measured corrections to classification.csv.

Every entry names the PR that measured it, so a reviewer can trace each verdict
change back to its evidence. Run once; it is idempotent.
"""

from __future__ import annotations

import csv
import pathlib

HERE = pathlib.Path(__file__).parent

FIX: dict[str, tuple[str, str]] = {
    "constraints_spatial_index": (
        "PORT",
        "S2/#743 CORRECTION: issues NO kNN query -- three query_ball_point radius "
        "queries, k absent. 0 accept/reject differences in 1,200 probes; the real "
        "divergence is scipy's return_sorted=None default, driven to zero by "
        "return_sorted=True at :233,:252,:266 (a precondition, not a blocker)",
    ),
    "_zone_pour_stitch": (
        "PORT",
        "S2/#743: the k=1 query does select emitted copper (a crafted tie flips a "
        "segment endpoint, dmin bit-identical) but is unreachable -- _emit_zone_pours "
        "always passes cluster=False, 0 queries across 8 configurations. DORMANT "
        "HAZARD: reactivates for a netclass with clearance == 0, of which none exists",
    ),
    "channel_mapping": (
        "PORT",
        "S3/#744 CORRECTION: nx.shortest_path at :339,:343 is unreachable (dominated "
        "by 'if not channel_sequence: return None'), so DELETE the branch rather than "
        "port it -- it is not stable even within Python (256 tied paths, 32/32 "
        "permutations differ). Removing it drops networkx from the module entirely",
    ),
    "routing_space": (
        "PORT",
        "S1/#747: narrowing measured -- contains(board,p) & ~OR intersects(obs_i,p) "
        "matches production on 598,400/598,400 cells incl. the eroded C-space path. "
        "DEGRADED by S4/#746: channel_skeleton stays Python and still needs a real "
        "MultiPolygon, so one lazy GEOS consumer remains",
    ),
    "obstacle_map": (
        "PORT",
        "S1/#747: unary_union falls out under the narrowing; Point.buffer vertices are "
        "exactly reconstructible as a 4q-gon (0/16 and 0/32 mismatches, class B1 only). "
        "buffer(0) at :108 and LineString.buffer at :137 stay Python -- 2 kept lines",
    ),
    "placement_audit": (
        "GLUE",
        "S1/#747 CORRECTION: not a GEOS blocker at all -- advisory diagnostics whose "
        "output reaches only a verbose print. JUSTIFIED-KEEP",
    ),
    "via_placement": (
        "GLUE",
        "#749 CORRECTION: two abs() subtractions is its entire arithmetic. Pinned "
        "anyway because it PRODUCES the Via objects the other six DFM modules consume",
    ),
    "quality/corridor": (
        "RETIRE",
        "#750: compares two coordinate frames (board-relative courtyards vs "
        "page-absolute traces). bitaxe_ultra identifies 739 channels and assigns 0 "
        "tracks; both published scores near-constant on 4/5 corpus boards. Both else "
        "arms of _identify_channels unreachable (97,522 if / 0 else over 200k pairs). "
        "It measures nothing",
    ),
    "constraints_design_rules": (
        "SPLIT",
        "S5/#748 CORRECTION: my kiutils citation pointed at a verdict whose pattern is "
        "io/**, not router_v6/**. kiutils.board.Board has no netClasses in 1.4.8 so the "
        "parse branch is unreachable for ANY input; parse_from_file and infer_zones "
        "have zero callers repo-wide. Splits 90 PORT / 20 Phase-3 seam / 40 "
        "BLOCKED(GEOS via ZoneManager STRtree) / 64 DEAD / 36 PORT-or-Phase-3",
    ),
    "zone_emission": (
        "BLOCKED",
        "S5/#748: the scipy blocker is DELETED (3,904 permutation trials, 0 partition "
        "flips; _cluster_positions unreachable -- all 16 zone-eligible nets are "
        "continuity-exempt). But the survey MISSED a GEOS boundary: "
        "_convex_hull_from_positions runs on every zone regardless of clustering -- "
        "2,141/3,904 byte flips with identical copper. Reclassified scipy -> GEOS",
    ),
    "channel_skeleton": (
        "BLOCKED",
        "S4/#746 CORRECTION: the recorded gate had NEVER been run, and a plan described "
        "it as 'pre-spiked'. GEOS Voronoi IS deterministic (20 repeats, 3 seeds, 8 "
        "permutations). The real blocker is edge_id built from unrounded float repr at "
        "constraint_model.py:325-337 -- geometry agrees to 1.05e-15, identifiers 0/12. "
        "Narrowing = 1nm quantisation + canonical edge ordering",
    ),
    "topology_solver": (
        "SPLIT",
        "#745 CORRECTION: not wholly dead. 45 stmts retired; SolverStatus and "
        "TopologicalSolution are LIVE on the production path (_pipeline_route.py:41,:349) "
        "-- 24 stmts are ELSEWHERE contracts",
    ),
    "topology_extraction": (
        "SPLIT",
        "#745: extract_topology_solution and _extract_net_topology (36 stmts) retired -- "
        "_pipeline_route.py:368,377 constructs the types directly. NetTopology and "
        "TopologyGraph (20 stmts) are live ELSEWHERE contracts",
    ),
    "metrics/octilinear": (
        "DEAD",
        "#745 CORRECTION: 'imported nowhere in src/' was true of SYMBOLS, not the "
        "module -- metrics/__init__.py re-exports it, so it WAS loaded at runtime via "
        "gates.py:960 -> metrics.slop_linter. Retired regardless: no symbol has a caller",
    ),
    "sat_model": (
        "DEAD",
        "#745: _pipeline_route.py:281 sets sat_model = None unconditionally. CORRECTION "
        "to method: scripts/bmc_adoption_gate.py was a live consumer reading it as TEXT "
        "-- a channel the import graph could not see",
    ),
    "_astar_heuristics": (
        "PORT",
        "2026-08-07 KTD8 OVERTURNED by 0b7c850c: an exact Rust EDT "
        "(Felzenszwalb-Huttenlocher, the same algorithm scipy runs) measured "
        "BIT-EXACT against scipy -- max abs diff 0.0, 0 differing cells over "
        "7,435,980, and 1.6-1.7x faster including the FFI boundary. The prior "
        "rejection was of the APPROXIMATE edt crate (max diff 2.0-2.236), not of "
        "the approach. distance_transform_edt (:100) was this module's only scipy "
        "binding, so the blocker clears outright. Evidence: "
        "docs/evidence/2026-08-07-exact-edt-rust-spike.md",
    ),
    "routability_check": (
        "BLOCKED",
        "2026-08-07 PARTIAL -- bucket deliberately UNCHANGED. KTD8 "
        "(distance_transform_edt :395) is overturned by 0b7c850c, bit-exact vs "
        "scipy; see docs/evidence/2026-08-07-exact-edt-rust-spike.md. But this "
        "module carries a SECOND, unrelated binding -- scipy.ndimage.label (:341) "
        "-- that no spike has addressed. Clearing one of two blockers does not "
        "unblock a module; label is now the sole remaining blocker here",
    ),
}


def main() -> None:
    path = HERE / "classification.csv"
    with path.open() as fh:
        rows = list(csv.DictReader(fh))

    seen = set()
    for row in rows:
        if row["module"] in FIX:
            row["bucket"], row["reason"] = FIX[row["module"]]
            seen.add(row["module"])

    missing = set(FIX) - seen
    if missing:
        raise SystemExit(f"modules not found in classification.csv: {sorted(missing)}")

    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["module", "bucket", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"applied {len(seen)} corrections")


if __name__ == "__main__":
    main()
