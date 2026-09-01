#!/usr/bin/env python3
"""Run the bounded, scratch-only R14/high-voltage pre-route campaign.

Rust owns declaration order and semantic board mutation.  This file only
stages the KiCad project, invokes repository-owned instruments, and writes
their receipts.  It never writes the production board or footprint library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLACER = ROOT / "packages/temper-placer/src"
if str(PLACER) not in sys.path:
    sys.path.insert(0, str(PLACER))

import temper_design_bundle_python as tdb  # noqa: E402
import temper_geometry  # noqa: E402
import temper_quality_oracle  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from temper_placer.core.pad_geometry import pad_pair_distance, shape_code  # noqa: E402
from temper_placer.io.fab_body_extraction import extract_fab_bodies  # noqa: E402
from temper_placer.io.kicad_metadata import extract_kicad_metadata  # noqa: E402
from temper_placer.io.real_board import load_real_board_placement  # noqa: E402
from temper_placer.requirements.validators._copper import _component_pads  # noqa: E402
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    verify_iec60335_compliance,
)

EVIDENCE = Path(__file__).resolve().parent
PREDECESSOR = ROOT / "docs/evidence/k1-j1-domain-refloorplan-20260831"
PRODUCTION_BOARD = ROOT / "pcb/temper.kicad_pcb"
DOMAIN_MANIFEST = ROOT / "elec/domain_manifest.yaml"
NETLIST = ROOT / "elec/build/default.net"
CANONICAL_J1 = PREDECESSOR / "approved-j1-footprint.kicad_mod"
BOARD_READY_J1 = PREDECESSOR / "approved-j1-board-footprint.kicad_sexpr"
GENERATED_DRU = ROOT / "pcb/temper.kicad_dru"
J1_LIBRARY = ROOT / "pcb/libs/Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod"
DRC_CEILING = ROOT / "power_pcb_dataset/drc_ceiling.json"
SHIFTS_MM = (4.0, 4.5, 5.0, 5.5)
PLACEMENT_BUDGET = 240
ROUTED_PROMOTION_BUDGET = 8
MOVABLE_REFS = ("J1", "R45", "R58", "R66", "SW1", "U22")
AFFECTED_REFS = frozenset((*MOVABLE_REFS, "R14"))
ROUTE_NET_INDEX = 41
ROUTE_NET_NAME = "discharge.r_snub1-p2"
ROUTE_LAYER = "In3.Cu"
ROUTE_WIDTH_MM = 0.5
FIXED_ENDPOINT = (112.0, 218.0)
MOVING_VIA_TSTAMP = "80dc97ff-4224-5905-925a-d96851a93537"
MOVING_PAD_NUMBER = "2"
MOVING_VIA_SIZE_MM = 0.9
MOVING_VIA_DRILL_MM = 0.3
SEGMENT_TSTAMPS = (
    "6f0fc0cf-21f3-5002-9a69-56e731267c8b",
    "6cafd89e-ca83-57ec-851d-d155c9d0b3b2",
    "550d69a3-4b61-50f5-835d-36d0a3ed4d4b",
    "048519f5-d649-5114-98f6-60724a55aada",
    "267034c2-04fd-54e2-a5de-91f83f88e089",
    "951c86e1-1293-542d-b329-e84b974e7b78",
    "8177ba34-5cc4-5224-9e26-550776d71d3d",
    "4db32563-63fa-505b-a69d-47be9cfdd1e2",
    "69ea8cbb-c6cb-5c53-8c15-24a24f25c4ba",
    "8eb327f7-4a2b-5805-a4c9-dcf2d58c3d08",
    "9282fe61-caff-564e-b085-478bcc27b15f",
    "b1bd3aea-e461-5343-8750-23146ea08f18",
    "9f8ea5c7-cd34-5c39-9394-f618be359f8e",
    "91582a5b-645a-5caa-80b2-f6272ef47f6f",
    "7b5bff49-d260-58c8-b8f0-0691a7e84809",
)
PINNED_PREDECESSOR_HASHES = {
    "build_authority.py": "add550df27ce87608ceac15b369c61bd308e3c549e1eb3b47ae111712b259e0d",
    "search.py": "1cbf2fe7eeabb959134000c654c39ef858fdfb2a11db35a3c55d83d8b99267b2",
    "search_v2.py": "6674b24e2b634f698daadf218d3c70c3c06116556c0058d44c3d0ae11fd01d17",
    "declaration.json": "3edeb18206004e98d07903860c5ff1bf377e96c9b97b845d1ae2c98cce1a833f",
    "manifest.json": "f7a56e454007eebf342357b5fad6892a681f8a41d0be5d0702540cce81e9e95b",
    "negative-certificate.md": "3a72b4bb740687a52221e8efa449ba689b5e475e520846c5f646ef6c370e063e",
}
INSTRUMENT_STATE = {
    "extensions": "10/10 fresh immediately before the campaign",
    "pinned_rotation_oracle": "PASS: 10 registered sites, 16 probes, pcbnew 10.0.5 corpus",
    "live_rotation_oracle": "TOOL ERROR: no interpreter with pcbnew bindings was available",
    "kicad_cli_version": "10.0.5",
    "baseline_drc_runs": 3,
    "baseline_drc_errors_each": 406,
    "baseline_drc_warnings_each": 402,
    "baseline_drc_saturated_category": "silk_overlap=199",
}
CLASSIFICATION_REASON = (
    "The complete declared pre-route family has no survivor, but required live-oracle "
    "evidence is unavailable and the baseline DRC contains a capped category. The result "
    "therefore narrows the next design step without certifying topology impossibility."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def verify_generated_inputs() -> dict[str, str]:
    required = {
        "netlist": (NETLIST, "make netlist"),
        "kicad_dru": (GENERATED_DRU, ".venv/bin/python scripts/generate_kicad_dru.py"),
        "domain_manifest": (DOMAIN_MANIFEST, None),
    }
    missing = [
        f"{path.relative_to(ROOT)} (generate with `{command}`)" if command else str(path.relative_to(ROOT))
        for path, command in required.values()
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError("required campaign input is missing: " + "; ".join(missing))
    return {name: sha256(path) for name, (path, _) in required.items()}


def block_span(text: str, start: int) -> tuple[int, int]:
    depth = 0
    quoted = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise ValueError(f"unbalanced block at {start}")


def embedded_footprint(text: str, ref: str) -> str:
    marker = f'(property "Reference" "{ref}")'
    at = text.find(marker)
    if at < 0 or text.find(marker, at + 1) >= 0:
        raise ValueError(f"expected one embedded footprint {ref}")
    start = text.rfind("(footprint ", 0, at)
    return text[slice(*block_span(text, start))]


def verify_predecessor() -> dict[str, str]:
    actual = {name: sha256(PREDECESSOR / name) for name in PINNED_PREDECESSOR_HASHES}
    if actual != PINNED_PREDECESSOR_HASHES:
        raise RuntimeError(f"predecessor artifact hash drift: {actual}")
    canonical = CANONICAL_J1.read_text(encoding="utf-8")
    required_fragments = (
        '(start -2.95 -2.85)',
        '(end 10.45 3.9)',
        '(start -2.45 -2.35)',
        '(end 9.95 3.4)',
        '(at 0 0)',
        '(at 2.5 0)',
        '(at 5 0)',
        '(at 7.5 0)',
        '(size 1.7 1.95)',
        '(drill 0.95)',
        'JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.wrl',
    )
    missing = [fragment for fragment in required_fragments if fragment not in canonical]
    if missing:
        raise RuntimeError(f"canonical J1 footprint is incomplete: {missing}")
    return actual


def stage_authority(scratch: Path) -> Path:
    scratch.mkdir(parents=True, exist_ok=True)
    for suffix in (".kicad_pro", ".kicad_dru"):
        shutil.copy2(PRODUCTION_BOARD.with_suffix(suffix), scratch / f"temper{suffix}")
    shutil.copy2(ROOT / "pcb/fp-lib-table", scratch / "fp-lib-table")
    shutil.copytree(ROOT / "pcb/libs", scratch / "libs", dirs_exist_ok=True)

    board = scratch / "temper.kicad_pcb"
    replacement = BOARD_READY_J1.read_text(encoding="utf-8").rstrip("\n").lstrip(" ")
    authority = tdb.parse_engine.replace_footprint_block_by_reference_py(
        PRODUCTION_BOARD.read_text(encoding="utf-8"), "J1", replacement
    )
    board.write_text(authority, encoding="utf-8")
    expected = "5ef29bfda80ac96cd490bed0b8881835f807eba3fa60b2b126eefc16eaf26e8a"
    if sha256(board) != expected:
        raise RuntimeError(f"authority board hash drift: {sha256(board)} != {expected}")
    embedded = embedded_footprint(board.read_text(encoding="utf-8"), "J1")
    for fragment in (
        '(fp_rect (start -2.95 -2.85) (end 10.45 3.9)',
        '(fp_rect (start -2.45 -2.35) (end 9.95 3.4)',
        '(pad "1" thru_hole roundrect (at 0 0) (size 1.7 1.95) (drill 0.95)',
        '(pad "4" thru_hole oval (at 7.5 0) (size 1.7 1.95) (drill 0.95)',
        'JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.wrl',
    ):
        if fragment not in embedded:
            raise RuntimeError(f"embedded J1 differs from canonical semantic field: {fragment}")
    return board


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
    out = {}
    for a, b in combinations(refs, 2):
        area = float(polys[a].intersection(polys[b]).area)
        if area > 1e-8:
            out[f"{a}<->{b}"] = area
    return out


def safety_signature(row) -> tuple[str, ...]:
    refs = sorted((str(row.ref_a), str(row.ref_b)))
    return (*refs, str(row.metric), str(row.insulation_type), str(row.boundary), str(row.pair_kind))


def safety_measure(board: Path):
    placement, domains, stats = load_real_board_placement(board, DOMAIN_MANIFEST, NETLIST)
    result = verify_iec60335_compliance(placement, domains)
    values = {safety_signature(v): float(v.measured_mm) for v in result.violations}
    receipt = {
        "errors": result.error_count,
        "warnings": result.warning_count,
        "coverage_ratio": stats["coverage_ratio"],
        "matched_components": stats["matched_components_in_placement"],
        "total_components": stats["total_components"],
        "components_without_pads": stats["components_without_pads"],
    }
    return placement, domains, values, receipt


def k1_j1_gap(placement) -> tuple[float, str]:
    components = {c["ref"]: c for c in placement["components"]}
    rows = []
    for a in _component_pads(components["K1"]):
        for b in _component_pads(components["J1"]):
            distance = pad_pair_distance(
                (a.width, a.height, a.shape, a.cx, a.cy, a.rotation_rad, a.roundrect_ratio),
                (b.width, b.height, b.shape, b.cx, b.cy, b.rotation_rad, b.roundrect_ratio),
            )
            rows.append((distance, f"{a.label}<->{b.label}"))
    return min(rows)


def route_to_selv_clearance(board: Path, placement, domains) -> dict[str, object]:
    parsed = tdb.parse_engine.parse_kicad_pcb(board.read_text(encoding="utf-8"))
    traces = [t for t in parsed.traces if t.net == ROUTE_NET_NAME and t.layer == ROUTE_LAYER]
    vias = [v for v in parsed.vias if v.net == ROUTE_NET_NAME]
    if len(traces) != len(SEGMENT_TSTAMPS) or len(vias) != 1:
        raise RuntimeError(f"route parse cardinality drift: traces={len(traces)} vias={len(vias)}")

    outline = placement["board"]["outline"]
    origin_x = min(point[0] for point in outline)
    origin_y = min(point[1] for point in outline)
    rows: list[tuple[float, str]] = []
    for component in placement["components"]:
        pad_layers = {str(row["number"]): str(row["layer"]) for row in component["pads"]}
        for pad in _component_pads(component):
            domain = domains.get(pad.net)
            if domain is None or getattr(domain, "value", str(domain)) != "LV_CONTROL":
                continue
            cx = pad.cx + origin_x
            cy = pad.cy + origin_y
            pad_spec = (
                pad.width,
                pad.height,
                shape_code(pad.shape),
                cx,
                cy,
                pad.rotation_rad,
                pad.roundrect_ratio,
            )
            pad_layer = pad_layers.get(str(pad.number))
            if pad_layer is None:
                raise RuntimeError(f"missing layer declaration for {pad.ref}.{pad.number}")
            if pad_layer == "all" or pad_layer == ROUTE_LAYER:
                for index, trace in enumerate(traces):
                    distance = temper_geometry.pad_to_capsule_distance_py(
                        pad_spec, trace.start, trace.end, trace.width
                    )
                    rows.append((float(distance), f"{pad.ref}.{pad.number}<->net41.segment[{index}]"))
            for index, via in enumerate(vias):
                if "F.Cu" not in via.layers and pad_layer != "all":
                    continue
                distance = temper_geometry.pad_to_capsule_distance_py(
                    pad_spec, via.position, via.position, via.diameter
                )
                rows.append((float(distance), f"{pad.ref}.{pad.number}<->net41.via[{index}]"))
    if not rows:
        raise RuntimeError("route-to-SELV denominator is empty")
    distance, pair = min(rows)
    return {
        "minimum_mm": distance,
        "closest_pair": pair,
        "pairs_examined": len(rows),
        "denominator": "LV_CONTROL pad copper intersecting the declared route layers",
    }


def containment_failures(geometries, positions, outline) -> list[str]:
    board = Polygon(outline)
    failures = []
    for ref in AFFECTED_REFS:
        if ref not in geometries or ref not in positions:
            failures.append(f"{ref}:missing-geometry")
            continue
        polygon = geometries[ref].get_global_polygon(*positions[ref][:2], positions[ref][2])
        if not board.covers(polygon):
            failures.append(ref)
    return sorted(failures)


def run(scratch: Path) -> dict[str, object]:
    generated_inputs = verify_generated_inputs()
    predecessor_hashes = verify_predecessor()
    source = stage_authority(scratch / "authority")
    source_text = source.read_text(encoding="utf-8")
    predecessor_manifest = json.loads((PREDECESSOR / "manifest.json").read_text())
    placement_rows = {row["id"]: row["placements"] for row in predecessor_manifest["results"]}
    declarations = temper_quality_oracle.declare_regional_candidates_py(
        list(placement_rows), list(SHIFTS_MM), PLACEMENT_BUDGET
    )
    if len(declarations) != PLACEMENT_BUDGET:
        raise RuntimeError(f"Rust declaration returned {len(declarations)} rows")

    baseline_placement, baseline_domains, baseline_safety, baseline_safety_receipt = safety_measure(source)
    baseline_positions = footprint_positions(source_text)
    bodies = extract_fab_bodies(source)
    courtyards = extract_kicad_metadata(source).courtyards
    baseline_body = overlap_map(bodies, baseline_positions)
    baseline_courtyard = overlap_map(courtyards, baseline_positions)
    outline = baseline_placement["board"]["outline"]

    results = []
    for ordinal, candidate_id, placement_id, shift_mm in declarations:
        placements = placement_rows[placement_id]
        placement_tuples = [(ref, *placements[ref]) for ref in MOVABLE_REFS]
        moved = tdb.parse_engine.update_footprint_positions_py(source_text, placement_tuples)
        candidate_text = tdb.parse_engine.replace_declared_route_and_move_footprint_py(
            moved,
            "R14",
            ROUTE_NET_INDEX,
            ROUTE_LAYER,
            ROUTE_WIDTH_MM,
            FIXED_ENDPOINT,
            MOVING_VIA_TSTAMP,
            MOVING_PAD_NUMBER,
            MOVING_VIA_SIZE_MM,
            MOVING_VIA_DRILL_MM,
            list(SEGMENT_TSTAMPS),
            shift_mm,
        )
        candidate_dir = scratch / "placements" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for name in ("temper.kicad_pro", "temper.kicad_dru", "fp-lib-table"):
            shutil.copy2(source.parent / name, candidate_dir / name)
        shutil.copytree(source.parent / "libs", candidate_dir / "libs", dirs_exist_ok=True)
        candidate = candidate_dir / "temper.kicad_pcb"
        candidate.write_text(candidate_text, encoding="utf-8")

        placement, domains, safety, safety_receipt = safety_measure(candidate)
        gap_mm, gap_pair = k1_j1_gap(placement)
        route_clearance = route_to_selv_clearance(candidate, placement, domains)
        positions = footprint_positions(candidate_text)
        body = overlap_map(bodies, positions)
        courtyard = overlap_map(courtyards, positions)
        new_body = sorted(set(body) - set(baseline_body))
        worsened_body = sorted(
            pair for pair in set(body) & set(baseline_body)
            if body[pair] > baseline_body[pair] + 1e-8
        )
        new_courtyard = sorted(set(courtyard) - set(baseline_courtyard))
        worsened_courtyard = sorted(
            pair for pair in set(courtyard) & set(baseline_courtyard)
            if courtyard[pair] > baseline_courtyard[pair] + 1e-8
        )
        new_safety = sorted(set(safety) - set(baseline_safety))
        worsened_safety = sorted(
            sig for sig in set(safety) & set(baseline_safety)
            if safety[sig] < baseline_safety[sig] - 1e-9
        )
        affected_safety = sorted(
            (sig, distance) for sig, distance in safety.items()
            if sig[0] in AFFECTED_REFS or sig[1] in AFFECTED_REFS
        )
        contained = containment_failures(bodies, positions, outline)
        placement_pass, rejection_reasons = temper_quality_oracle.evaluate_pre_route_candidate_py(
            gap_mm,
            route_clearance["minimum_mm"],
            len(affected_safety),
            len(new_safety),
            len(worsened_safety),
            len(new_body),
            len(worsened_body),
            len(new_courtyard),
            len(worsened_courtyard),
            len(contained),
        )
        results.append(
            {
                "ordinal": ordinal,
                "id": candidate_id,
                "predecessor_placement_id": placement_id,
                "east_shift_mm": shift_mm,
                "sha256": sha256_text(candidate_text),
                "placements": placements,
                "r14_position": [118.64 + shift_mm, 249.56, 270.0],
                "k1_j1_gap_mm": gap_mm,
                "k1_j1_closest_pair": gap_pair,
                "route_to_selv": route_clearance,
                "safety": safety_receipt,
                "affected_safety_violations": [
                    {"signature": list(sig), "measured_mm": distance}
                    for sig, distance in affected_safety
                ],
                "new_safety_signatures": [list(sig) for sig in new_safety],
                "worsened_safety_signatures": [list(sig) for sig in worsened_safety],
                "new_body_overlaps": new_body,
                "worsened_body_overlaps": worsened_body,
                "new_courtyard_overlaps": new_courtyard,
                "worsened_courtyard_overlaps": worsened_courtyard,
                "containment_failures": contained,
                "placement_pass": placement_pass,
                "rejection_reasons": rejection_reasons,
            }
        )
        if ordinal % 20 == 0 or ordinal == 1:
            print(
                f"{candidate_id} {ordinal}/{len(declarations)} "
                f"k1-j1={gap_mm:.4f} route-selv={route_clearance['minimum_mm']:.4f} "
                f"affected={len(affected_safety)} pass={placement_pass}",
                flush=True,
            )

    survivors = [row["id"] for row in results if row["placement_pass"]]
    rejection_counts: dict[str, int] = {}
    for row in results:
        for reason in row["rejection_reasons"]:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    declaration = {
        "status": "executed",
        "family": "first",
        "predecessor_commit": "6b89c315468b658b26eb6b68abf1442964792537",
        "predecessor_hashes": predecessor_hashes,
        "generated_inputs": generated_inputs,
        "production_board_sha256": sha256(PRODUCTION_BOARD),
        "authority_board_sha256": sha256(source),
        "canonical_j1_footprint_sha256": sha256(CANONICAL_J1),
        "board_ready_j1_footprint_sha256": sha256(BOARD_READY_J1),
        "predecessor_placement_count": len(placement_rows),
        "east_shifts_mm": list(SHIFTS_MM),
        "cardinality": len(declarations),
        "placement_screen_budget": PLACEMENT_BUDGET,
        "routed_promotion_budget": ROUTED_PROMOTION_BUDGET,
        "route": {
            "net_index": ROUTE_NET_INDEX,
            "net_name": ROUTE_NET_NAME,
            "layer": ROUTE_LAYER,
            "width_mm": ROUTE_WIDTH_MM,
            "fixed_endpoint": list(FIXED_ENDPOINT),
            "moving_via_tstamp": MOVING_VIA_TSTAMP,
            "moving_pad_number": MOVING_PAD_NUMBER,
            "moving_via_size_mm": MOVING_VIA_SIZE_MM,
            "moving_via_drill_mm": MOVING_VIA_DRILL_MM,
            "segment_tstamps": list(SEGMENT_TSTAMPS),
            "transform": "x += east_shift_mm * clamp((y - 218)/(252.5225 - 218), 0, 1)",
        },
        "ordering": "placement_id lexical, east_shift_mm ascending",
    }
    return {
        **declaration,
        "baseline_safety": baseline_safety_receipt,
        "placement_survivors": survivors,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "results": results,
    }


def declaration_from_manifest(manifest: dict[str, object]) -> dict[str, object]:
    omitted = {"results", "baseline_safety", "placement_survivors", "rejection_counts"}
    return {key: value for key, value in manifest.items() if key not in omitted}


def build_terminal_receipt(
    manifest: dict[str, object], declaration_path: Path, manifest_path: Path
) -> dict[str, object]:
    results = manifest["results"]
    if not isinstance(results, list) or not results:
        raise RuntimeError("terminal receipt requires a non-empty result set")
    k1_gaps = [float(row["k1_j1_gap_mm"]) for row in results]
    route_gaps = [float(row["route_to_selv"]["minimum_mm"]) for row in results]
    closest_pairs = {str(row["route_to_selv"]["closest_pair"]) for row in results}
    shared_closest_pair = next(iter(closest_pairs)) if len(closest_pairs) == 1 else None
    survivors = manifest["placement_survivors"]
    return {
        "status": "stopped-indeterminate",
        "scope": "R14/high-voltage first-family pre-route campaign",
        "declaration_sha256": sha256(declaration_path),
        "pre_route_manifest_sha256": sha256(manifest_path),
        "semantic_replay_sha256": sha256_text(json.dumps(manifest, sort_keys=True)),
        "coverage": {
            "declared_candidates": int(manifest["cardinality"]),
            "evaluated_candidates": len(results),
            "placement_survivors": len(survivors),
            "routed_candidates": 0,
            "authorized_expansions": 0,
        },
        "measurements": {
            "k1_j1_gap_mm": {
                "minimum": min(k1_gaps),
                "maximum": max(k1_gaps),
                "required_minimum": 13.1,
                "passing_candidates": sum(value >= 13.1 for value in k1_gaps),
            },
            "net41_to_selv_pad_clearance_mm": {
                "minimum": min(route_gaps),
                "maximum": max(route_gaps),
                "required_minimum": 12.6,
                "passing_candidates": sum(value >= 12.6 for value in route_gaps),
                "shared_closest_pair": shared_closest_pair,
                "denominator": "LV_CONTROL pad copper intersecting the declared route layers",
            },
            "rejection_counts": manifest["rejection_counts"],
        },
        "expansion_decision": {
            "authorized": False,
            "reason": (
                "The shared route-to-SELV pad-copper veto involves already-movable J1 and "
                "the declared net-41 chain; the safety veto set also contains multiple "
                "distinct relationships. No one canonical fixed object satisfied the "
                "expansion contract."
            ),
        },
        "instrument_state": INSTRUMENT_STATE,
        "production_authorities": {
            "board_sha256": sha256(PRODUCTION_BOARD),
            "j1_library_footprint_sha256": sha256(J1_LIBRARY),
            "drc_ceiling_sha256": sha256(DRC_CEILING),
            "changed": False,
        },
        "classification_reason": CLASSIFICATION_REASON,
    }


def validate_terminal_receipt(
    actual: dict[str, object], expected: dict[str, object]
) -> None:
    if actual != expected:
        mismatched = sorted(
            key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)
        )
        raise RuntimeError(f"terminal receipt mismatch in field(s): {mismatched}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scratch",
        type=Path,
        default=Path("/tmp/compound-engineering-1000/r14-hv-domain-refloorplan-20260831/campaign"),
    )
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    manifest = run(args.scratch.resolve())
    declaration = declaration_from_manifest(manifest)
    declaration_path = EVIDENCE / "declaration.json"
    manifest_path = EVIDENCE / "pre-route-manifest.json"
    receipt_path = EVIDENCE / "terminal-receipt.json"
    if args.replay:
        expected_declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
        if declaration != expected_declaration:
            raise SystemExit("replay mismatch: regenerated declaration differs")
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest != expected:
            raise SystemExit("replay mismatch: regenerated semantic manifest differs")
        expected_receipt = build_terminal_receipt(manifest, declaration_path, manifest_path)
        actual_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        validate_terminal_receipt(actual_receipt, expected_receipt)
        print("REPLAY PASS", sha256_text(json.dumps(manifest, sort_keys=True)))
        return 0
    declaration_path.write_text(json.dumps(declaration, indent=2, sort_keys=True) + "\n")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    receipt = build_terminal_receipt(manifest, declaration_path, manifest_path)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SURVIVORS", manifest["placement_survivors"])
    print("MANIFEST", sha256(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
