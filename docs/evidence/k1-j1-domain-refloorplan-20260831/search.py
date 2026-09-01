#!/usr/bin/env python3
"""Bounded scratch-only K1/J1 neighborhood placement campaign."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import shutil
from dataclasses import asdict
from pathlib import Path

import temper_design_bundle_python as tdb

from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.io.fab_body_extraction import extract_fab_bodies, extract_fab_body_coverage
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.real_board import load_real_board_placement
from temper_placer.requirements.validators.clearance import verify_iec60335_compliance
from temper_placer.requirements.validators._copper import _component_pads


ROOT = Path("/home/bennet/Desktop/temper/.worktrees/fix-isolation-barrier-safety")
CAMPAIGN = Path("/tmp/compound-engineering-1000/k1-j1-refloorplan-20260831")
SOURCE_DIR = Path("/tmp/compound-engineering-1000/k1-j1-candidates/authority")
SOURCE = SOURCE_DIR / "temper.kicad_pcb"
MOVABLE = ("J1", "R45", "R58", "R66", "SW1", "U22")
FENCE = {"x_min": 90.0, "x_max": 108.5, "y_min": 239.0, "y_max": 253.0}

# Twelve official-J1 anchors. Rotation 180 intentionally points J1.4 west,
# away from the fixed x=113.55..118.64 In3.Cu HV route.
J1_OPTIONS = tuple(
    (x, y, 180.0)
    for y in (242.5, 243.0, 243.5)
    for x in (103.0, 104.0, 105.0, 106.0)
)
R45_OPTIONS = ((94.2, 244.01, 270.0),)
R58_OPTIONS = ((91.48, 242.62, 90.0),)
R66_OPTIONS = (
    (98.8, 246.7, 180.0),
    (99.4, 246.7, 180.0),
    (98.8, 247.3, 180.0),
    (99.4, 247.3, 180.0),
)
SW1_OPTIONS = (
    (102.72, 247.3, 180.0),
    (103.72, 247.3, 180.0),
)
U22_OPTIONS = (
    (100.3, 249.4, 180.0),
    (100.3, 250.0, 180.0),
    (101.0, 249.4, 180.0),
    (101.0, 250.0, 180.0),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def footprint_positions(text: str) -> dict[str, tuple[float, float, int]]:
    return {
        str(row["ref"]): (
            float(row["x"]),
            float(row["y"]),
            round(float(row["angle"]) / 90.0) % 4,
        )
        for row in tdb.parse_engine.extract_footprint_info_py(text)
    }


def overlap_map(geometries, positions) -> dict[str, float]:
    refs = sorted(set(geometries) & set(positions))
    polys = {
        ref: geometries[ref].get_global_polygon(*positions[ref][:2], positions[ref][2])
        for ref in refs
    }
    out: dict[str, float] = {}
    for a, b in itertools.combinations(refs, 2):
        area = float(polys[a].intersection(polys[b]).area)
        if area > 1e-8:
            out["<->".join((a, b))] = area
    return out


def pad_spec(pad) -> tuple[float, float, str, float, float, float, float]:
    ratio = 0.147059 if pad.component_ref == "J1" and pad.number == "1" else 0.25
    return (
        float(pad.size[0]), float(pad.size[1]), str(pad.shape),
        float(pad.position[0]), float(pad.position[1]),
        math.radians(float(pad.rotation)), ratio,
    )


def k1_j1_gap(board: Path) -> tuple[float, str]:
    placement, _, _ = load_real_board_placement(
        board, ROOT / "elec/domain_manifest.yaml", ROOT / "elec/build/default.net"
    )
    components = {c["ref"]: c for c in placement["components"]}
    a = _component_pads(components["K1"])
    b = _component_pads(components["J1"])
    rows = [
        (
            pad_pair_distance(
                (x.width, x.height, x.shape, x.cx, x.cy, x.rotation_rad, x.roundrect_ratio),
                (y.width, y.height, y.shape, y.cx, y.cy, y.rotation_rad, y.roundrect_ratio),
            ),
            f"{x.label}<->{y.label}",
        )
        for x in a for y in b
    ]
    return min(rows)


def safety_signature(row) -> tuple[str, ...]:
    refs = sorted((str(row.ref_a), str(row.ref_b)))
    return (
        *refs,
        str(row.metric), str(row.insulation_type),
        str(row.boundary), str(row.pair_kind),
    )


def req_safe(board: Path) -> tuple[dict[tuple[str, ...], float], dict[str, object]]:
    placement, domains, stats = load_real_board_placement(
        board, ROOT / "elec/domain_manifest.yaml", ROOT / "elec/build/default.net"
    )
    result = verify_iec60335_compliance(placement, domains)
    values = {safety_signature(v): float(v.measured_mm) for v in result.violations}
    return values, {
        "errors": result.error_count,
        "warnings": result.warning_count,
        "coverage_ratio": stats["coverage_ratio"],
        "matched_components": stats["matched_components_in_placement"],
        "total_components": stats["total_components"],
        "components_without_pads": stats["components_without_pads"],
    }


def materialize(candidate_id: str, placements: dict[str, tuple[float, float, float]]) -> Path:
    dst = CAMPAIGN / "placements" / candidate_id
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("temper.kicad_pro", "temper.kicad_prl", "temper.kicad_dru", "fp-lib-table"):
        shutil.copy2(SOURCE_DIR / name, dst / name)
    if not (dst / "libs").exists():
        shutil.copytree(ROOT / "pcb/libs", dst / "libs")
    tuples = [(ref, *placements[ref]) for ref in MOVABLE]
    text = tdb.parse_engine.update_footprint_positions_py(
        SOURCE.read_text(encoding="utf-8"), tuples
    )
    board = dst / "temper.kicad_pcb"
    board.write_text(text, encoding="utf-8")
    return board


def rank_key(item):
    placements = item
    # KTD1: prefer J1 farther north/east only as much as needed, then lower-x
    # small parts (farther from fixed HV copper), then minimum displacement.
    jx, jy, _ = placements["J1"]
    displacement = sum(
        math.dist(placements[r][:2], BASE_POS[r][:2]) for r in MOVABLE
    )
    return (-jy, abs(jx - 105.0), sum(placements[r][0] for r in ("R66", "SW1", "U22")), displacement, tuple(placements[r] for r in MOVABLE))


BASE_TEXT = SOURCE.read_text(encoding="utf-8")
BASE_POS = {ref: (x, y, q * 90.0) for ref, (x, y, q) in footprint_positions(BASE_TEXT).items()}


def main() -> None:
    CAMPAIGN.mkdir(parents=True, exist_ok=True)
    bodies = extract_fab_bodies(SOURCE)
    coverage = extract_fab_body_coverage(SOURCE, footprint_positions(BASE_TEXT))
    courtyards = extract_kicad_metadata(SOURCE).courtyards
    base_positions = footprint_positions(BASE_TEXT)
    base_body = overlap_map(bodies, base_positions)
    base_court = overlap_map(courtyards, base_positions)
    base_safe, base_safe_stats = req_safe(SOURCE)

    full: list[dict[str, tuple[float, float, float]]] = []
    for values in itertools.product(J1_OPTIONS, R45_OPTIONS, R58_OPTIONS, R66_OPTIONS, SW1_OPTIONS, U22_OPTIONS):
        full.append(dict(zip(MOVABLE, values, strict=True)))
    # Stratified KTD1 sample: every J1 anchor is represented by the first
    # eight ranked neighborhood packings.  This makes the connector-only
    # R6 bound exhaustive even though mechanical screens cover 96/384.
    selected = []
    for j1 in J1_OPTIONS:
        group = sorted((p for p in full if p["J1"] == j1), key=rank_key)
        selected.extend(group[:8])
    results = []
    for idx, placements in enumerate(selected, 1):
        cid = f"P{idx:03d}"
        board = materialize(cid, placements)
        pos = footprint_positions(board.read_text(encoding="utf-8"))
        body = overlap_map(bodies, pos)
        court = overlap_map(courtyards, pos)
        gap, pair = k1_j1_gap(board)
        new_body = sorted(set(body) - set(base_body))
        new_court = sorted(set(court) - set(base_court))
        rec: dict[str, object] = {
            "id": cid,
            "board": str(board),
            "sha256": sha(board),
            "placements": {r: list(placements[r]) for r in MOVABLE},
            "k1_j1_gap_mm": gap,
            "k1_j1_closest_pair": pair,
            "new_body_overlaps": new_body,
            "new_courtyard_overlaps": new_court,
            "placement_pass": gap >= 13.1 and not new_body and not new_court,
        }
        if rec["placement_pass"]:
            safe, safe_stats = req_safe(board)
            new_safe = sorted(set(safe) - set(base_safe))
            worsened = sorted(sig for sig in set(safe) & set(base_safe) if safe[sig] < base_safe[sig] - 1e-9)
            rec.update({
                "req_safe": safe_stats,
                "new_req_safe_signatures": [list(x) for x in new_safe],
                "worsened_req_safe_signatures": [list(x) for x in worsened],
                "safety_pass": not new_safe and not worsened,
            })
        else:
            rec["safety_pass"] = False
        results.append(rec)
        print(cid, f"gap={gap:.9f}", f"body+={len(new_body)}", f"court+={len(new_court)}", f"safe={rec['safety_pass']}", flush=True)

    survivors = [r["id"] for r in results if r["placement_pass"] and r["safety_pass"]]
    manifest = {
        "source": str(SOURCE),
        "source_sha256": sha(SOURCE),
        "official_j1_footprint_sha256": "578ba6321290aead39a60428eed317d8e0eb2b23759774ccc9090a41e82a8285",
        "fence_mm": FENCE,
        "movable_refs": list(MOVABLE),
        "immutable_fixed_obstacles": ["K1", "U8", "discharge.r_snub1-p2 In3.Cu route", "Edge.Cuts", "all other board objects"],
        "declared_cartesian_size": len(full),
        "placement_screen_budget": 96,
        "coverage_fraction": f"96/{len(full)}",
        "routed_promotion_budget": 24,
        "ordering": "J1_OPTIONS order, then first 8 neighborhood packings by (-J1_y, abs(J1_x-105), sum movable-low-voltage x, total displacement, placement tuple)",
        "options": {
            "J1": J1_OPTIONS, "R45": R45_OPTIONS, "R58": R58_OPTIONS,
            "R66": R66_OPTIONS, "SW1": SW1_OPTIONS, "U22": U22_OPTIONS,
        },
        "fab_coverage": {"complete": coverage.complete, "present": len(coverage.present), "missing": coverage.missing, "invalid": coverage.invalid},
        "baseline": {
            "body_overlaps": base_body, "courtyard_overlaps": base_court,
            "req_safe": base_safe_stats,
        },
        "placement_survivors": survivors,
        "results": results,
    }
    (CAMPAIGN / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SURVIVORS", survivors)
    print(CAMPAIGN / "manifest.json")


if __name__ == "__main__":
    main()
