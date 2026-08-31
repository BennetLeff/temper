#!/usr/bin/env python3
"""Corrected, fixed-obstacle-clear bounded neighborhood family."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

import search as s


OUT = s.CAMPAIGN / "corrected"
OPTIONS = {
    "J1": ((103, 242.5, 180), (104, 242.5, 180), (103, 243, 180),
           (104, 243, 180), (105, 243, 180), (103, 243.5, 180),
           (104, 243.5, 180), (105, 243.5, 180), (106, 243.5, 180)),
    "R45": ((93, 244, 270), (93.5, 244, 270)),
    "R58": ((91, 242.5, 90), (91.5, 242.5, 90)),
    "R66": ((102, 249.5, 180), (102.5, 249.5, 180), (103, 249.5, 180)),
    "SW1": ((102, 247.5, 180), (102.5, 247.5, 180), (103, 247.5, 180)),
    "U22": ((105.5, 249, 180), (106, 249, 180), (106.5, 249, 180)),
}


def qpos(placement):
    return {r: (v[0], v[1], int(v[2] / 90) % 4) for r, v in placement.items()}


def new_overlaps(geometries, base_positions, placement):
    current = dict(base_positions)
    current.update(qpos(placement))
    base = s.overlap_map(geometries, base_positions)
    now = s.overlap_map(geometries, current)
    return sorted(set(now) - set(base))


def option_polygons(geometries, ref, option):
    return geometries[ref].get_global_polygon(option[0], option[1], int(option[2] / 90) % 4)


def rank(p):
    displacement = sum(math.dist(p[r][:2], s.BASE_POS[r][:2]) for r in s.MOVABLE)
    return (-p["J1"][1], abs(p["J1"][0] - 105), displacement, tuple(p[r] for r in s.MOVABLE))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    text = s.SOURCE.read_text(encoding="utf-8")
    base_positions = s.footprint_positions(text)
    bodies = s.extract_fab_bodies(s.SOURCE)
    courts = s.extract_kicad_metadata(s.SOURCE).courtyards
    base_safe, base_safe_stats = s.req_safe(s.SOURCE)

    fixed_refs = sorted(set(base_positions) - set(s.MOVABLE))
    fixed_polys = {
        kind: {
            ref: geometries[ref].get_global_polygon(*base_positions[ref][:2], base_positions[ref][2])
            for ref in fixed_refs if ref in geometries
        }
        for kind, geometries in (("body", bodies), ("courtyard", courts))
    }
    option_polys = {
        kind: {
            (ref, option): option_polygons(geometries, ref, option)
            for ref in s.MOVABLE for option in OPTIONS[ref]
        }
        for kind, geometries in (("body", bodies), ("courtyard", courts))
    }

    # U2 declaration is persisted before any corrected candidate board is
    # materialized. Every individual option must clear every fixed object;
    # then the full Cartesian product is filtered for movable/movable pairs.
    individual_failures = []
    for ref in s.MOVABLE:
        for option in OPTIONS[ref]:
            for kind in ("body", "courtyard"):
                poly = option_polys[kind][(ref, option)]
                fixed_hits = [other for other, other_poly in fixed_polys[kind].items() if poly.intersection(other_poly).area > 1e-8]
                if fixed_hits:
                    individual_failures.append({"ref": ref, "option": option, "kind": kind, "hits": fixed_hits})
    if individual_failures:
        raise RuntimeError(f"individual slot is not fixed-clear: {individual_failures}")

    full = [dict(zip(s.MOVABLE, row, strict=True)) for row in itertools.product(*(OPTIONS[r] for r in s.MOVABLE))]
    valid = []
    for p in full:
        collision = False
        for kind in ("body", "courtyard"):
            for a, b in itertools.combinations(s.MOVABLE, 2):
                if option_polys[kind][(a, p[a])].intersection(option_polys[kind][(b, p[b])]).area > 1e-8:
                    collision = True
                    break
            if collision:
                break
        if collision:
            continue
        valid.append(p)
    valid.sort(key=rank)
    if len(valid) > 96:
        valid = valid[:96]

    declaration = {
        "status": "declared-before-materialization",
        "supersedes_calibration_manifest": str(s.CAMPAIGN / "manifest.json"),
        "fence_mm": s.FENCE,
        "movable_refs": list(s.MOVABLE),
        "options": OPTIONS,
        "full_cartesian_size": len(full),
        "fixed_obstacle_clear_options": True,
        "mutually_body_and_courtyard_clear_combinations": len(valid),
        "placement_screen_budget": 96,
        "placements_selected": len(valid),
        "routed_promotion_budget": 24,
        "ordering": "(-J1_y, abs(J1_x-105), total displacement, placement tuple)",
    }
    (OUT / "declaration.json").write_text(json.dumps(declaration, indent=2, sort_keys=True) + "\n")

    s.CAMPAIGN = OUT
    results = []
    for i, p in enumerate(valid, 1):
        cid = f"C{i:03d}"
        board = s.materialize(cid, p)
        gap, pair = s.k1_j1_gap(board)
        safe, safe_stats = s.req_safe(board)
        new_safe = sorted(set(safe) - set(base_safe))
        worsened = sorted(sig for sig in set(safe) & set(base_safe) if safe[sig] < base_safe[sig] - 1e-9)
        rec = {
            "id": cid, "board": str(board), "sha256": s.sha(board),
            "placements": {r: list(p[r]) for r in s.MOVABLE},
            "k1_j1_gap_mm": gap, "k1_j1_closest_pair": pair,
            "new_body_overlaps": [],
            "new_courtyard_overlaps": [],
            "req_safe": safe_stats,
            "new_req_safe_signatures": [list(x) for x in new_safe],
            "worsened_req_safe_signatures": [list(x) for x in worsened],
            "placement_pass": gap >= 13.1 and not new_safe and not worsened,
        }
        results.append(rec)
        print(cid, f"gap={gap:.9f}", f"new-safe={len(new_safe)}", f"worse={len(worsened)}", f"pass={rec['placement_pass']}", flush=True)

    survivors = [r["id"] for r in results if r["placement_pass"]]
    manifest = declaration | {
        "source": str(s.SOURCE), "source_sha256": s.sha(s.SOURCE),
        "official_j1_footprint_sha256": "578ba6321290aead39a60428eed317d8e0eb2b23759774ccc9090a41e82a8285",
        "baseline_req_safe": base_safe_stats,
        "placement_survivors": survivors,
        "results": results,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("SURVIVORS", survivors)


if __name__ == "__main__":
    main()
