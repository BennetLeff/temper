#!/usr/bin/env python3
"""Execute the immutable Net-41 corridor declaration in scratch storage.

Rust owns candidate identity, order, exact coverage, hard-veto order, terminal
classification, and route selection. This runner stages complete KiCad
projects, invokes geometry/oracle instruments, and writes Rust-returned
evidence. It never edits the production board or DRC ceiling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/net41-corridor-execution-20260901"
DECLARATION_EVIDENCE = ROOT / "docs/evidence/net41-route-layer-corridor-20260831"
PREDECESSOR = ROOT / "docs/evidence/r14-hv-domain-refloorplan-20260831"
BOARD = ROOT / "pcb/temper.kicad_pcb"
DRC_CEILING = ROOT / "power_pcb_dataset/drc_ceiling.json"
DOMAIN_MANIFEST = ROOT / "elec/domain_manifest.yaml"
NETLIST = ROOT / "elec/build/default.net"
DRU = ROOT / "pcb/temper.kicad_dru"
ROUTE_NET = 41
ROUTE_LAYER = "In3.Cu"
ROUTE_WIDTH_MM = 0.5
VIA_SIZE_MM = 0.9
VIA_DRILL_MM = 0.3
VIA_SPAN = ["In3.Cu", "F.Cu"]
ROUTE_NET_NAME = "discharge.r_snub1-p2"
MOVABLE_REFS = ("J1", "R45", "R58", "R66", "SW1", "U22")
AFFECTED_REFS = frozenset((*MOVABLE_REFS, "R14"))

SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_drc_determinism as drc_determinism  # noqa: E402
import route_board  # noqa: E402
import temper_design_bundle_python as design_bundle  # noqa: E402
import temper_drc_rs  # noqa: E402
import temper_geometry  # noqa: E402
import temper_quality_oracle  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from temper_placer.core.pad_geometry import shape_code  # noqa: E402
from temper_placer.io.fab_body_extraction import extract_fab_bodies  # noqa: E402
from temper_placer.io.kicad_metadata import extract_kicad_metadata  # noqa: E402
from temper_placer.io.real_board import load_real_board_placement  # noqa: E402
from temper_placer.requirements.validators._copper import _component_pads  # noqa: E402
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    verify_iec60335_compliance,
)
from temper_placer.validation.netlist_reconciliation import (  # noqa: E402
    extract_board_netlist,
    parse_design_netlist,
    reconcile,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def run_checked(
    command: list[str], *, env: dict[str, str] | None = None, timeout_s: int = 1800
) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        raise RuntimeError(
            f"instrument timed out after {timeout_s}s ({' '.join(command)}):\n{output}"
        ) from error
    if result.returncode != 0:
        raise RuntimeError(f"instrument failed ({' '.join(command)}):\n{result.stdout}")
    return result.stdout


def pcbnew_environment() -> tuple[str, dict[str, str]]:
    interpreter = os.environ.get("TEMPER_PCBNEW_PYTHON", "/usr/bin/python3.12")
    root = Path.home() / ".local/opt/kicad-10.0.5/root"
    if not Path(interpreter).is_file() or not root.is_dir():
        raise RuntimeError("live pcbnew interpreter or relocated KiCad root is unavailable")
    library_dirs = sorted({str(path.parent) for path in root.rglob("*.so*")})
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(library_dirs + [env.get("LD_LIBRARY_PATH", "")])
    env["PYTHONPATH"] = str(root / "usr/lib/python3/dist-packages")
    env["KICAD_STOCK_DATA_HOME"] = str(root / "usr/share/kicad")
    env["TEMPER_PCBNEW_PYTHON"] = interpreter
    return interpreter, env


def instrument_row(
    name: str,
    state: str,
    detail: str,
    subject_sha256: str,
    payload: object,
) -> dict[str, object]:
    return {
        "name": name,
        "state": state,
        "detail": detail,
        "subject_sha256": subject_sha256,
        "receipt_sha256": sha256_bytes(canonical_bytes(payload)),
    }


def preflight(board_sha256: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    instruments: list[dict[str, object]] = []
    try:
        output = run_checked(["make", "extensions-check"])
        if "PASSED -- 10/10 extension module(s) fresh." not in output:
            raise RuntimeError("extension freshness command omitted its 10/10 pass receipt")
        payload = {
            "command": "make extensions-check",
            "verified": "10/10 extension modules fresh and importable",
        }
        instruments.append(
            instrument_row(
                "pyo3-extensions",
                "trusted",
                "all discovered pyo3 extensions are fresh and importable",
                board_sha256,
                payload,
            )
        )
    except Exception as error:  # instrument errors become terminal evidence
        payload = {"command": "make extensions-check", "error": str(error)}
        instruments.append(
            instrument_row(
                "pyo3-extensions", "error", str(error), board_sha256, payload
            )
        )

    try:
        _interpreter, env = pcbnew_environment()
        oracle = run_checked(
            [
                str(ROOT / ".venv/bin/python"),
                "scripts/check_pad_world_position_oracle.py",
                "--verify-live-oracle",
            ],
            env=env,
        )
        pass_line = next(
            line.strip() for line in oracle.splitlines() if line.startswith("PASS")
        )
        payload = {
            "oracle": "pcbnew-live-asymmetric-45-degree",
            "pass_line": pass_line,
        }
        instruments.append(
            instrument_row(
                "pcbnew-rotation-oracle",
                "trusted",
                f"live pcbnew oracle passed: {pass_line}",
                board_sha256,
                payload,
            )
        )
    except Exception as error:
        payload = {"oracle": "pcbnew-live-asymmetric-45-degree", "error": str(error)}
        instruments.append(
            instrument_row(
                "pcbnew-rotation-oracle", "error", str(error), board_sha256, payload
            )
        )

    drc_receipt: dict[str, object]
    try:
        run_checked([str(ROOT / ".venv/bin/python"), "scripts/generate_kicad_dru.py"])
        version = run_checked(["kicad-cli", "--version"]).strip()
        drc_runs = drc_determinism.measure(BOARD, 3)
        raw_drc_analysis = drc_determinism.analyse(drc_runs)
        # Exact set cardinality is itself nondeterministic. The receipt pins
        # the admission-relevant fact: whether more than one set was seen.
        drc_analysis = [
            {
                **{key: value for key, value in row.items() if key != "digests"},
                "distinct_set_count_at_least": 2 if len(row["digests"]) > 1 else 1,
            }
            for row in raw_drc_analysis
        ]
        capped = [row["category"] for row in drc_analysis if row["at_cap"]]
        unstable = [
            row["category"]
            for row in drc_analysis
            if not row["count_stable"] or not row["set_stable"]
        ]
        failures = [
            *(f"reporting cap {category}" for category in capped),
            *(f"repeated-set disagreement {category}" for category in unstable),
        ]
        drc_receipt = {
            "schema_version": "temper-net41-baseline-drc-preflight/v1",
            "board_sha256": board_sha256,
            "kicad_cli_version": version,
            "sample_count": len(drc_runs),
            "categories": drc_analysis,
            "capped_categories": capped,
            "unstable_categories": unstable,
            "trusted_for_candidate_admission": not failures,
        }
        detail = (
            f"version {version}; 3 repeated normalized runs are untrusted: "
            + "; ".join(failures)
            if failures
            else f"version {version}; 3 repeated normalized sets are uncapped and agree"
        )
        instruments.append(
            instrument_row(
                "baseline-kicad-drc",
                "error" if failures else "trusted",
                detail,
                board_sha256,
                drc_receipt,
            )
        )
    except Exception as error:
        drc_receipt = {
            "schema_version": "temper-net41-baseline-drc-preflight/v1",
            "board_sha256": board_sha256,
            "trusted_for_candidate_admission": False,
            "error": str(error),
        }
        instruments.append(
            instrument_row(
                "baseline-kicad-drc", "error", str(error), board_sha256, drc_receipt
            )
        )
    return instruments, drc_receipt


def evidence_kwargs() -> dict[str, bytes]:
    required = [BOARD, DRC_CEILING, DOMAIN_MANIFEST, NETLIST, DRU]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing campaign input(s): {missing}")
    return {
        "declaration_bytes": (DECLARATION_EVIDENCE / "declaration.json").read_bytes(),
        "basis_bytes": (DECLARATION_EVIDENCE / "design-basis.json").read_bytes(),
        "board_bytes": BOARD.read_bytes(),
        "predecessor_receipt_bytes": (PREDECESSOR / "terminal-receipt.json").read_bytes(),
        "predecessor_manifest_bytes": (PREDECESSOR / "pre-route-manifest.json").read_bytes(),
        "domain_manifest_bytes": DOMAIN_MANIFEST.read_bytes(),
        "netlist_bytes": NETLIST.read_bytes(),
        "kicad_dru_bytes": DRU.read_bytes(),
    }


def stage_project(scratch: Path) -> Path:
    project = scratch / "project"
    project.mkdir(parents=True, exist_ok=True)
    for path in (BOARD.with_suffix(".kicad_pro"), DRU, ROOT / "pcb/fp-lib-table"):
        shutil.copy2(path, project / path.name)
    shutil.copytree(ROOT / "pcb/libs", project / "libs", dirs_exist_ok=True)
    return project


def exact_placement_board(
    source: str,
    placements: dict[str, list[float]],
    endpoint_x_mm: float,
) -> str:
    declared = [(ref, *placements[ref]) for ref in MOVABLE_REFS]
    declared.append(("R14", endpoint_x_mm, 249.56, 270.0))
    return design_bundle.parse_engine.update_declared_footprint_positions_exact_py(
        source, declared
    )


def applicable_selv_pads(board_path: Path) -> tuple[list[tuple[str, tuple, str]], int]:
    placement, domains, _stats = load_real_board_placement(
        board_path, DOMAIN_MANIFEST, NETLIST
    )
    outline = placement["board"]["outline"]
    origin_x = min(point[0] for point in outline)
    origin_y = min(point[1] for point in outline)
    pads: list[tuple[str, tuple, str]] = []
    total_selv = 0
    for component in placement["components"]:
        pad_layers = {str(row["number"]): str(row["layer"]) for row in component["pads"]}
        for pad in _component_pads(component):
            domain = domains.get(pad.net)
            if domain is None or getattr(domain, "value", str(domain)) != "LV_CONTROL":
                continue
            total_selv += 1
            layer = pad_layers.get(str(pad.number))
            if layer is None:
                raise RuntimeError(f"missing layer for SELV pad {pad.ref}.{pad.number}")
            if layer != "all" and layer not in VIA_SPAN:
                continue
            spec = (
                pad.width,
                pad.height,
                shape_code(pad.shape),
                pad.cx + origin_x,
                pad.cy + origin_y,
                pad.rotation_rad,
                pad.roundrect_ratio,
            )
            pads.append((f"{pad.ref}.{pad.number}", spec, layer))
    # Every LV_CONTROL pad is route-applicable: inner-layer/THT pads can see
    # the In3.Cu segments, and F.Cu pads can see the terminal In3.Cu->F.Cu
    # via. A 19-pad denominator would silently omit the latter population.
    if total_selv != 240 or len(pads) != 240:
        raise RuntimeError(
            f"SELV pad denominator drift: total={total_selv}, route-applicable={len(pads)}"
        )
    return pads, total_selv


def measure_candidate(candidate: dict[str, object], pads: list[tuple[str, tuple, str]]) -> dict:
    points = [tuple(map(float, point)) for point in candidate["route_points"]]
    distances: list[tuple[float, str]] = []
    for index, (start, end) in enumerate(zip(points, points[1:], strict=True)):
        for label, spec, layer in pads:
            if layer == "all" or layer == ROUTE_LAYER:
                value = temper_geometry.pad_to_capsule_distance_py(
                    spec, start, end, ROUTE_WIDTH_MM
                )
                distances.append((float(value), f"{label}<->segment[{index}]"))
    endpoint = points[-1]
    for label, spec, layer in pads:
        if layer == "all" or layer == "F.Cu":
            value = temper_geometry.pad_to_capsule_distance_py(
                spec, endpoint, endpoint, VIA_SIZE_MM
            )
            distances.append((float(value), f"{label}<->terminal-via"))
    if not distances:
        raise RuntimeError("candidate clearance denominator is empty")
    minimum, closest = min(distances)
    return {
        "candidate_id": candidate["candidate_id"],
        "minimum_clearance_mm": minimum,
        "minimum_creepage_lower_bound_mm": minimum,
        "route_length_mm": sum(
            math.dist(a, b) for a, b in zip(points, points[1:], strict=True)
        ),
        "closest_pair": closest,
        "pairs_examined": len(distances),
    }


def materialize_candidate(base_text: str, instruction: dict[str, object]) -> str:
    placements = [
        (
            row["reference"],
            row["x_mm"],
            row["y_mm"],
            row["rotation_deg"],
        )
        for row in instruction["footprint_positions"]
    ]
    moved = design_bundle.parse_engine.update_declared_footprint_positions_exact_py(
        base_text, placements
    )
    return design_bundle.parse_engine.replace_declared_route_with_points_py(
        moved,
        instruction["candidate_id"],
        instruction["route_net"],
        instruction["route_layer"],
        instruction["route_width_mm"],
        instruction["via_size_mm"],
        instruction["via_drill_mm"],
        instruction["via_span"],
        instruction["fixed_ref"],
        instruction["fixed_pad_number"],
        instruction["moving_ref"],
        instruction["moving_pad_number"],
        instruction["old_segment_tstamps"],
        instruction["old_via_tstamp"],
        [tuple(point) for point in instruction["route_points"]],
    )


def footprint_positions(text: str) -> dict[str, tuple[float, float, int]]:
    return {
        str(row["ref"]): (
            float(row["x"]),
            float(row["y"]),
            round(float(row["angle"]) / 90.0) % 4,
        )
        for row in design_bundle.parse_engine.extract_footprint_info_py(text)
    }


def overlap_map(geometries, positions) -> dict[str, float]:
    refs = sorted(set(geometries) & set(positions))
    polygons = {
        ref: geometries[ref].get_global_polygon(*positions[ref][:2], positions[ref][2])
        for ref in refs
    }
    overlaps = {}
    for left, right in combinations(refs, 2):
        area = float(polygons[left].intersection(polygons[right]).area)
        if area > 1e-8:
            overlaps[f"{left}<->{right}"] = area
    return overlaps


def safety_signature(row) -> tuple[str, ...]:
    refs = sorted((str(row.ref_a), str(row.ref_b)))
    return (
        *refs,
        str(row.metric),
        str(row.insulation_type),
        str(row.boundary),
        str(row.pair_kind),
    )


def safety_measure(board_path: Path) -> tuple[dict, dict[tuple[str, ...], float], dict]:
    placement, domains, stats = load_real_board_placement(
        board_path, DOMAIN_MANIFEST, NETLIST
    )
    result = verify_iec60335_compliance(placement, domains)
    values = {safety_signature(row): float(row.measured_mm) for row in result.violations}
    receipt = {
        "errors": result.error_count,
        "warnings": result.warning_count,
        "coverage_ratio": stats["coverage_ratio"],
        "matched_components": stats["matched_components_in_placement"],
        "total_components": stats["total_components"],
        "components_without_pads": stats["components_without_pads"],
        "signatures": [
            {"identity": list(identity), "measured_mm": value}
            for identity, value in sorted(values.items())
        ],
    }
    return placement, values, receipt


def containment_failures(geometries, positions, outline) -> list[str]:
    board = Polygon(outline)
    failures = []
    for reference in AFFECTED_REFS:
        if reference not in geometries or reference not in positions:
            failures.append(f"{reference}:missing-geometry")
        elif not board.covers(
            geometries[reference].get_global_polygon(
                *positions[reference][:2], positions[reference][2]
            )
        ):
            failures.append(reference)
    return sorted(failures)


def topology_snapshot(board_text: str) -> dict[str, object]:
    return json.loads(
        design_bundle.regional_topology_snapshot_json_py(
            board_text.encode(), DOMAIN_MANIFEST.read_bytes()
        )
    )


def repeated_drc_receipt(board_path: Path, baseline: dict[str, object]) -> tuple[dict, bool, int]:
    runs = drc_determinism.measure(board_path, 3)
    raw = drc_determinism.analyse(runs)
    categories = [
        {
            **{key: value for key, value in row.items() if key != "digests"},
            "distinct_set_count_at_least": 2 if len(row["digests"]) > 1 else 1,
        }
        for row in raw
    ]
    capped = [row["category"] for row in categories if row["at_cap"]]
    unstable = [
        row["category"]
        for row in categories
        if not row["count_stable"] or not row["set_stable"]
    ]
    baseline_max = {
        row["category"]: max(int(value) for value in row["counts"])
        for row in baseline.get("categories", [])
    }
    hard_rules = {
        "shorting_items",
        "clearance",
        "creepage",
        "hole_clearance",
        "copper_edge_clearance",
    }
    hard_regressions = []
    for row in categories:
        rule = str(row["category"]).split(":", 1)[-1]
        observed = max(int(value) for value in row["counts"])
        if rule in hard_rules and observed > baseline_max.get(row["category"], observed):
            hard_regressions.append(
                {
                    "category": row["category"],
                    "baseline_max": baseline_max.get(row["category"]),
                    "candidate_max": observed,
                }
            )
    payload = {
        "board_sha256": sha256(board_path),
        "sample_count": len(runs),
        "categories": categories,
        "capped_categories": capped,
        "unstable_categories": unstable,
        "hard_rule_regressions": hard_regressions,
    }
    return payload, not capped and not unstable, len(hard_regressions)


def inspect_materialized_candidate(
    candidate_path: Path,
    instruction: dict[str, object],
    baseline: dict[str, object],
    baseline_drc: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    subject = sha256(candidate_path)
    text = candidate_path.read_text(encoding="utf-8")
    payloads: dict[str, object] = {}
    receipts: list[dict[str, object]] = []

    def record(name: str, payload: object, state: str = "trusted") -> None:
        payloads[name] = payload
        receipts.append(
            instrument_row(
                name,
                state,
                f"{name} executed against {subject}",
                subject,
                payload,
            )
        )

    snapshot = topology_snapshot(text)
    connected = snapshot["net41_component_count"] == 1 and not snapshot[
        "net41_isolated_pad_ids"
    ]
    record("connectivity", snapshot)
    expected_selv_categories = {"pads", "tracks", "vias", "zones"}
    selv_counts = snapshot["selv_object_counts"]
    complete_selv = (
        set(selv_counts) == expected_selv_categories
        and selv_counts == baseline["topology"]["selv_object_counts"]
        and sum(selv_counts.values()) > 0
    )
    record(
        "selv-denominator",
        {
            "object_counts": selv_counts,
            "identity_digest": snapshot["selv_identity_digest"],
            "complete": complete_selv,
        },
    )

    placement, safety, safety_payload = safety_measure(candidate_path)
    baseline_safety = baseline["safety"]
    new_safety = sorted(set(safety) - set(baseline_safety))
    worsened_safety = sorted(
        identity
        for identity in set(safety) & set(baseline_safety)
        if safety[identity] < baseline_safety[identity] - 1e-9
    )
    safety_payload.update(
        new_signatures=[list(row) for row in new_safety],
        worsened_signatures=[list(row) for row in worsened_safety],
    )
    record("safety-signatures", safety_payload)

    route_geometry_valid = (
        snapshot["net41_segment_count"] == len(instruction["route_points"]) - 1
        and snapshot["net41_via_count"] == 1
        and snapshot["net41_zone_count"] == 0
        and instruction["route_layer"] == ROUTE_LAYER
        and instruction["route_width_mm"] == ROUTE_WIDTH_MM
        and instruction["via_size_mm"] == VIA_SIZE_MM
        and instruction["via_drill_mm"] == VIA_DRILL_MM
        and instruction["via_span"] == VIA_SPAN
    )
    required_current = float(temper_drc_rs.get_net_current(ROUTE_NET_NAME))
    capacity = float(
        temper_geometry.ipc2221b_current_capacity_a_py(
            ROUTE_WIDTH_MM, 1.0, 10.0, True
        )
    )
    current_capacity_valid = capacity >= required_current
    record(
        "route-geometry-current-capacity",
        {
            "route_geometry_valid": route_geometry_valid,
            "required_current_a": required_current,
            "capacity_a": capacity,
            "capacity_valid": current_capacity_valid,
        },
    )

    positions = footprint_positions(text)
    contained = containment_failures(
        baseline["bodies"], positions, placement["board"]["outline"]
    )
    record("containment", {"failures": contained})
    body = overlap_map(baseline["bodies"], positions)
    courtyard = overlap_map(baseline["courtyards"], positions)
    new_body = sorted(set(body) - set(baseline["body_overlaps"]))
    worsened_body = sorted(
        pair
        for pair in set(body) & set(baseline["body_overlaps"])
        if body[pair] > baseline["body_overlaps"][pair] + 1e-8
    )
    new_courtyard = sorted(set(courtyard) - set(baseline["courtyard_overlaps"]))
    worsened_courtyard = sorted(
        pair
        for pair in set(courtyard) & set(baseline["courtyard_overlaps"])
        if courtyard[pair] > baseline["courtyard_overlaps"][pair] + 1e-8
    )
    record(
        "body-courtyard-overlap",
        {
            "new_body": new_body,
            "worsened_body": worsened_body,
            "new_courtyard": new_courtyard,
            "worsened_courtyard": worsened_courtyard,
        },
    )
    canonical_instruction = json.loads(
        temper_quality_oracle.validate_corridor_materialization_instruction_json_py(
            **baseline["inputs"], instruction_json=json.dumps(instruction)
        )
    )
    mutation_scope_valid = canonical_instruction == instruction
    record(
        "mutation-scope",
        {
            "candidate_id": instruction["candidate_id"],
            "source_board_sha256": baseline["source_sha256"],
            "scratch_board_sha256": subject,
            "rust_instruction_sha256": sha256_bytes(canonical_bytes(instruction)),
            "validated": mutation_scope_valid,
        },
    )
    drc_payload, drc_trusted, hard_regression_count = repeated_drc_receipt(
        candidate_path, baseline_drc
    )
    record(
        "normalized-kicad-drc",
        drc_payload,
        "trusted" if drc_trusted else "indeterminate",
    )
    aggregate_state = (
        "error"
        if any(row["state"] == "error" for row in receipts)
        else "indeterminate"
        if any(row["state"] == "indeterminate" for row in receipts)
        else "trusted"
    )
    evidence = {
        "candidate_id": instruction["candidate_id"],
        "scratch_board_sha256": subject,
        "instrument_state": aggregate_state,
        "instrument_detail": "all declared pre-route instruments executed",
        "receipts": receipts,
        "admission": {
            "connected": connected,
            "complete_selv_denominator": complete_selv,
            "new_safety_signature_count": len(new_safety),
            "worsened_safety_signature_count": len(worsened_safety),
            "route_geometry_valid": route_geometry_valid,
            "current_capacity_valid": current_capacity_valid,
            "containment_failure_count": len(contained),
            "new_body_overlap_count": len(new_body),
            "worsened_body_overlap_count": len(worsened_body),
            "new_courtyard_overlap_count": len(new_courtyard),
            "worsened_courtyard_overlap_count": len(worsened_courtyard),
            "mutation_scope_valid": mutation_scope_valid,
            "drc_capped": bool(drc_payload["capped_categories"]),
            "drc_repeated_sets_agree": drc_trusted,
            "drc_hard_rule_regression_count": hard_regression_count,
            "netlist_reconciled": False,
        },
    }
    return evidence, payloads


PRE_ROUTE_INSTRUMENTS = (
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "normalized-kicad-drc",
    "route-geometry-current-capacity",
    "safety-signatures",
    "selv-denominator",
)

POST_ROUTE_INSTRUMENTS = (
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "netlist-reconciliation",
    "normalized-kicad-drc",
    "pad-connectivity",
    "route-geometry-current-capacity",
    "router-completion",
    "safety-signatures",
    "selv-denominator",
)


def unavailable_materialization_evidence(
    candidate_id: str, scratch_hash: str, error: Exception | str
) -> tuple[dict[str, object], dict[str, object]]:
    payload = {"candidate_id": candidate_id, "error": str(error)}
    receipts = [
        instrument_row(name, "error", str(error), scratch_hash, payload)
        for name in PRE_ROUTE_INSTRUMENTS
    ]
    admission = {
        "connected": False,
        "complete_selv_denominator": False,
        "new_safety_signature_count": 0,
        "worsened_safety_signature_count": 0,
        "route_geometry_valid": False,
        "current_capacity_valid": False,
        "containment_failure_count": 0,
        "new_body_overlap_count": 0,
        "worsened_body_overlap_count": 0,
        "new_courtyard_overlap_count": 0,
        "worsened_courtyard_overlap_count": 0,
        "mutation_scope_valid": False,
        "drc_capped": False,
        "drc_repeated_sets_agree": False,
        "drc_hard_rule_regression_count": 0,
        "netlist_reconciled": False,
    }
    return (
        {
            "candidate_id": candidate_id,
            "scratch_board_sha256": scratch_hash,
            "instrument_state": "error",
            "instrument_detail": str(error),
            "receipts": receipts,
            "admission": admission,
        },
        dict.fromkeys(PRE_ROUTE_INSTRUMENTS, payload),
    )


def unavailable_route_evidence(
    candidate_id: str, input_hash: str, error: Exception | str, *, state: str
) -> tuple[dict[str, object], dict[str, object]]:
    payload = {"candidate_id": candidate_id, "error": str(error)}
    receipts = [
        instrument_row(name, state, str(error), input_hash, payload)
        for name in POST_ROUTE_INSTRUMENTS
    ]
    admission = {
        "connected": False,
        "complete_selv_denominator": False,
        "new_safety_signature_count": 0,
        "worsened_safety_signature_count": 0,
        "route_geometry_valid": False,
        "current_capacity_valid": False,
        "containment_failure_count": 0,
        "new_body_overlap_count": 0,
        "worsened_body_overlap_count": 0,
        "new_courtyard_overlap_count": 0,
        "worsened_courtyard_overlap_count": 0,
        "mutation_scope_valid": False,
        "drc_capped": False,
        "drc_repeated_sets_agree": False,
        "drc_hard_rule_regression_count": 0,
        "netlist_reconciled": False,
    }
    return (
        {
            "candidate_id": candidate_id,
            "input_board_sha256": input_hash,
            "routed_board_sha256": None,
            "execution_state": "instrument-error" if state == "error" else "indeterminate",
            "detail": str(error),
            "router_reported_complete": False,
            "pad_connectivity_complete": False,
            "receipts": receipts,
            "admission": admission,
        },
        dict.fromkeys(POST_ROUTE_INSTRUMENTS, payload),
    )


def route_and_inspect_candidate(
    candidate_path: Path,
    instruction: dict[str, object],
    baseline: dict[str, object],
    baseline_drc: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], Path | None]:
    input_hash = sha256(candidate_path)
    try:
        report = route_board.route_once(
            candidate_path,
            route_board.DEFAULT_RULES,
            keep_existing_copper=True,
            target_nets=[ROUTE_NET_NAME],
            enable_nlayer_astar_spike=True,
        )
    except Exception as error:
        evidence, payloads = unavailable_route_evidence(
            instruction["candidate_id"], input_hash, error, state="error"
        )
        return evidence, payloads, None
    content = report.get("routed_pcb_content") or ""
    if not content:
        evidence, payloads = unavailable_route_evidence(
            instruction["candidate_id"],
            input_hash,
            "router emitted no review board",
            state="indeterminate",
        )
        return evidence, payloads, None

    routed_path = candidate_path.with_name("temper-routed.kicad_pcb")
    routed_path.write_text(content, encoding="utf-8")
    pre_evidence, payloads = inspect_materialized_candidate(
        routed_path, instruction, baseline, baseline_drc
    )
    output_hash = sha256(routed_path)
    input_scope = design_bundle.parse_engine.non_target_content_sha256_py(
        candidate_path.read_text(encoding="utf-8"), ROUTE_NET
    )
    output_scope = design_bundle.parse_engine.non_target_content_sha256_py(content, ROUTE_NET)
    mutation_valid = input_scope == output_scope
    mutation_payload = {
        "input_non_target_sha256": input_scope,
        "output_non_target_sha256": output_scope,
        "byte_identical": mutation_valid,
    }
    payloads["mutation-scope"] = mutation_payload
    for index, row in enumerate(pre_evidence["receipts"]):
        if row["name"] == "mutation-scope":
            pre_evidence["receipts"][index] = instrument_row(
                "mutation-scope",
                "trusted",
                "Rust non-target fingerprint compared before and after scoped routing",
                output_hash,
                mutation_payload,
            )
            break
    pre_evidence["admission"]["mutation_scope_valid"] = mutation_valid

    net_results = report.get("net_route_results") or {}
    target_verdict = net_results.get(ROUTE_NET_NAME)
    disposition = getattr(target_verdict, "disposition", None)
    router_complete = (
        report.get("target_nets") == [ROUTE_NET_NAME]
        and report.get("attempted") == 1
        and report.get("routed") == 1
        and ROUTE_NET_NAME not in report.get("unrouted_nets", [])
        and disposition == "connected"
    )
    router_payload = {
        "target_nets": report.get("target_nets"),
        "attempted": report.get("attempted"),
        "routed": report.get("routed"),
        "unrouted_nets": report.get("unrouted_nets"),
        "verified_disposition": disposition,
        "wall_s": report.get("wall_s"),
        "complete": router_complete,
    }
    payloads["router-completion"] = router_payload
    pre_evidence["receipts"].append(
        instrument_row(
            "router-completion",
            "trusted",
            "bounded public target-net router returned a verified disposition",
            output_hash,
            router_payload,
        )
    )
    pad_payload = report.get("pad_connectivity") or {}
    pad_complete = ROUTE_NET_NAME in pad_payload.get("fully_connected_nets", [])
    payloads["pad-connectivity"] = pad_payload
    pre_evidence["receipts"].append(
        instrument_row(
            "pad-connectivity",
            "trusted",
            "independent pad-connectivity audit executed",
            output_hash,
            pad_payload,
        )
    )
    reconciliation = reconcile(
        extract_board_netlist(routed_path), parse_design_netlist(NETLIST)
    )
    reconciliation_payload = {
        "finding_count": len(reconciliation.findings),
        "findings": [
            {
                "kind": row.kind,
                "severity": row.severity,
                "detail": row.detail,
                "refs": list(row.refs),
                "paths": list(row.paths),
            }
            for row in reconciliation.findings
        ],
        "design_components": reconciliation.design_components,
        "board_components": reconciliation.board_components,
        "matched_paths": reconciliation.matched_paths,
    }
    reconciled = not reconciliation.findings
    payloads["netlist-reconciliation"] = reconciliation_payload
    pre_evidence["receipts"].append(
        instrument_row(
            "netlist-reconciliation",
            "trusted",
            "instance-path and net-membership reconciliation executed",
            output_hash,
            reconciliation_payload,
        )
    )
    pre_evidence["admission"]["netlist_reconciled"] = reconciled
    receipt_states = {row["state"] for row in pre_evidence["receipts"]}
    execution_state = (
        "instrument-error"
        if "error" in receipt_states
        else "indeterminate"
        if "indeterminate" in receipt_states
        else "conclusive"
    )
    evidence = {
        "candidate_id": instruction["candidate_id"],
        "input_board_sha256": input_hash,
        "routed_board_sha256": output_hash,
        "execution_state": execution_state,
        "detail": "bounded target-net route and all post-route instruments completed",
        "router_reported_complete": router_complete,
        "pad_connectivity_complete": pad_complete,
        "receipts": pre_evidence["receipts"],
        "admission": pre_evidence["admission"],
    }
    return evidence, payloads, routed_path


def run(scratch: Path) -> tuple[dict, str, dict]:
    board_before = sha256(BOARD)
    ceiling_before = sha256(DRC_CEILING)
    instruments, baseline_drc = preflight(board_before)
    inputs = evidence_kwargs()
    candidate_set = json.loads(
        temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
            inputs["declaration_bytes"], inputs["predecessor_manifest_bytes"]
        )
    )
    candidates = candidate_set["candidates"]
    if len(candidates) != 2880:
        raise RuntimeError(f"Rust candidate cardinality drift: {len(candidates)}")

    if all(row["state"] == "trusted" for row in instruments):
        return run_trusted_campaign(
            scratch,
            inputs,
            candidate_set,
            instruments,
            baseline_drc,
            board_before,
            ceiling_before,
        )

    # Instrument failure precedes screening by contract. The Rust terminal
    # authority validates the declaration and exact named preflight receipts,
    # but deliberately does not credit any candidate measurement or verdict.
    screening_request = {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": [],
        "route_budget": 12,
    }
    campaign_request = {
        "schema_version": "temper-corridor-campaign-request/v1",
        "screening": screening_request,
        "preflight": instruments,
        "materialized": [],
        "routed": [],
        "production_board_sha256_after": sha256(BOARD),
        "drc_ceiling_sha256_before": ceiling_before,
        "drc_ceiling_sha256_after": sha256(DRC_CEILING),
    }
    terminal_text = temper_quality_oracle.execute_corridor_campaign_json_py(
        **inputs, campaign_request_json=json.dumps(campaign_request)
    )
    terminal = json.loads(terminal_text)
    manifest = {
        "schema_version": "temper-net41-corridor-candidate-manifest/v1",
        "declaration_hash": candidate_set["declaration_hash"],
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "coverage": {
            "declared": len(candidates),
            "measured": terminal["measured_count"],
            "prefilter_survivors": terminal["prefilter_survivor_count"],
            "materialized": terminal["materialized_count"],
            "pre_route_survivors": terminal["pre_route_survivor_count"],
            "routed": terminal["routed_count"],
            "admitted": terminal["admitted_count"],
        },
        "screen_results": [],
        "prefilter_measurements": [],
        "materialized_results": [],
        "instrument_state": instruments,
        "production_authorities": {
            "board_sha256_before": board_before,
            "board_sha256_after": sha256(BOARD),
            "drc_ceiling_sha256_before": ceiling_before,
            "drc_ceiling_sha256_after": sha256(DRC_CEILING),
            "changed": board_before != sha256(BOARD) or ceiling_before != sha256(DRC_CEILING),
        },
    }
    return manifest, terminal_text, baseline_drc


def run_trusted_campaign(
    scratch: Path,
    inputs: dict[str, bytes],
    candidate_set: dict[str, object],
    instruments: list[dict[str, object]],
    baseline_drc: dict[str, object],
    board_before: str,
    ceiling_before: str,
) -> tuple[dict, str, dict]:
    """Execute the live candidate path after a fully trusted preflight."""
    candidates = candidate_set["candidates"]
    predecessor = json.loads(inputs["predecessor_manifest_bytes"])
    parent_rows = {
        row["predecessor_placement_id"]: row
        for row in predecessor["results"]
        if row["east_shift_mm"] == 4.0
    }
    if len(parent_rows) != 60:
        raise RuntimeError(f"expected 60 exact predecessor placements, got {len(parent_rows)}")

    project = stage_project(scratch)
    source = inputs["board_bytes"].decode()
    project_board = project / "temper.kicad_pcb"
    project_board.write_text(source, encoding="utf-8")
    baseline_placement, baseline_safety, baseline_safety_receipt = safety_measure(
        project_board
    )
    baseline_positions = footprint_positions(source)
    bodies = extract_fab_bodies(project_board)
    courtyards = extract_kicad_metadata(project_board).courtyards
    baseline = {
        "inputs": inputs,
        "source_sha256": board_before,
        "topology": topology_snapshot(source),
        "safety": baseline_safety,
        "safety_receipt": baseline_safety_receipt,
        "bodies": bodies,
        "courtyards": courtyards,
        "body_overlaps": overlap_map(bodies, baseline_positions),
        "courtyard_overlaps": overlap_map(courtyards, baseline_positions),
        "outline": baseline_placement["board"]["outline"],
    }
    bases = scratch / "bases"
    bases.mkdir(parents=True, exist_ok=True)
    measurements = []
    detailed_measurements = {}
    by_group: dict[tuple[str, float], list[dict]] = {}
    for candidate in candidates:
        key = (candidate["placement_id"], float(candidate["endpoint_x_mm"]))
        by_group.setdefault(key, []).append(candidate)
    for group_index, ((placement_id, endpoint_x), rows) in enumerate(by_group.items(), 1):
        parent = parent_rows[placement_id]
        base_text = exact_placement_board(source, parent["placements"], endpoint_x)
        base_path = bases / f"{placement_id}-{endpoint_x:.2f}.kicad_pcb"
        base_path.write_text(base_text, encoding="utf-8")
        staged_board = project / "temper.kicad_pcb"
        staged_board.write_text(base_text, encoding="utf-8")
        pads, _total = applicable_selv_pads(staged_board)
        for candidate in rows:
            measured = measure_candidate(candidate, pads)
            measurements.append({key: measured[key] for key in (
                "candidate_id", "minimum_clearance_mm", "minimum_creepage_lower_bound_mm", "route_length_mm"
            )})
            detailed_measurements[candidate["candidate_id"]] = measured
        if group_index % 20 == 0 or group_index == 1:
            print(f"prefilter groups {group_index}/{len(by_group)}", flush=True)

    screening_request = {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": measurements,
        "route_budget": 12,
    }
    screen = json.loads(
        temper_quality_oracle.validate_and_screen_corridor_evidence_json_py(
            **inputs, screening_request_json=json.dumps(screening_request)
        )
    )
    survivors = screen["clearance_creepage_prefilter_subset"]
    materialized: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    candidate_paths: dict[str, Path] = {}
    instructions: dict[str, dict[str, object]] = {}
    candidate_lookup = {row["candidate_id"]: row for row in candidates}

    candidate_root = scratch / "candidates"
    candidate_root.mkdir(parents=True, exist_ok=True)
    for index, candidate_id in enumerate(survivors, 1):
        candidate_dir = candidate_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for name in ("temper.kicad_pro", "temper.kicad_dru", "fp-lib-table"):
            shutil.copy2(project / name, candidate_dir / name)
        libraries = candidate_dir / "libs"
        if not libraries.exists():
            libraries.symlink_to(project / "libs", target_is_directory=True)
        candidate_path = candidate_dir / "temper.kicad_pcb"
        try:
            instruction_json = (
                temper_quality_oracle.corridor_materialization_instruction_json_py(
                    **inputs, candidate_id=candidate_id
                )
            )
            instruction = json.loads(
                temper_quality_oracle.validate_corridor_materialization_instruction_json_py(
                    **inputs, instruction_json=instruction_json
                )
            )
            if candidate_lookup[candidate_id]["route_points"] != instruction["route_points"]:
                raise RuntimeError("screened candidate geometry differs from Rust instruction")
            candidate_path.write_text(
                materialize_candidate(source, instruction), encoding="utf-8"
            )
            evidence, payloads = inspect_materialized_candidate(
                candidate_path, instruction, baseline, baseline_drc
            )
            instructions[candidate_id] = instruction
        except Exception as error:
            if not candidate_path.exists():
                candidate_path.write_text(source, encoding="utf-8")
            evidence, payloads = unavailable_materialization_evidence(
                candidate_id, sha256(candidate_path), error
            )
        candidate_paths[candidate_id] = candidate_path
        materialized.append(evidence)
        manifest_rows.append(
            {
                "candidate_id": candidate_id,
                "scratch_board": str(candidate_path.relative_to(scratch)),
                "scratch_board_sha256": sha256(candidate_path),
                "instrument_payloads": payloads,
            }
        )
        if index % 20 == 0 or index == 1:
            print(f"materialized candidates {index}/{len(survivors)}", flush=True)

    routed: list[dict[str, object]] = []
    routed_manifest_rows: list[dict[str, object]] = []

    campaign_request = {
        "schema_version": "temper-corridor-campaign-request/v1",
        "screening": screening_request,
        "preflight": instruments,
        "materialized": materialized,
        "routed": routed,
        "production_board_sha256_after": sha256(BOARD),
        "drc_ceiling_sha256_before": ceiling_before,
        "drc_ceiling_sha256_after": sha256(DRC_CEILING),
    }
    terminal_text = temper_quality_oracle.execute_corridor_campaign_json_py(
        **inputs, campaign_request_json=json.dumps(campaign_request)
    )
    terminal = json.loads(terminal_text)
    pre_route_ids = [
        row["candidate_id"] for row in terminal["materialized"] if row["accepted"]
    ]
    # A non-trusted materialization is terminal: do not route around missing
    # higher-stage evidence. Otherwise route the Rust-returned deterministic
    # prefix, consulting Rust after each attempt so evidence stops at the
    # first admitted route.
    materialization_trusted = all(
        row["instrument_state"] == "trusted" for row in materialized
    )
    if materialization_trusted:
        for candidate_id in pre_route_ids[:12]:
            evidence, payloads, routed_path = route_and_inspect_candidate(
                candidate_paths[candidate_id],
                instructions[candidate_id],
                baseline,
                baseline_drc,
            )
            routed.append(evidence)
            routed_manifest_rows.append(
                {
                    "candidate_id": candidate_id,
                    "routed_board": (
                        str(routed_path.relative_to(scratch)) if routed_path else None
                    ),
                    "instrument_payloads": payloads,
                }
            )
            campaign_request["routed"] = routed
            terminal_text = temper_quality_oracle.execute_corridor_campaign_json_py(
                **inputs, campaign_request_json=json.dumps(campaign_request)
            )
            terminal = json.loads(terminal_text)
            if terminal["status"] in {"completed", "instrument-error"} or evidence[
                "execution_state"
            ] != "conclusive":
                break
    manifest = {
        "schema_version": "temper-net41-corridor-candidate-manifest/v1",
        "declaration_hash": screen["declaration_hash"],
        "candidate_set_digest": screen["candidate_set_digest"],
        "coverage": {
            "declared": len(candidates),
            "measured": screen["evaluated_count"],
            "prefilter_survivors": len(survivors),
            "materialized": len(materialized),
            "pre_route_survivors": terminal["pre_route_survivor_count"],
            "routed": terminal["routed_count"],
            "admitted": terminal["admitted_count"],
        },
        "screen_results": screen["results"],
        "prefilter_measurements": [
            detailed_measurements[candidate["candidate_id"]] for candidate in candidates
        ],
        "materialized_results": manifest_rows,
        "routed_results": routed_manifest_rows,
        "instrument_state": instruments,
        "production_authorities": {
            "board_sha256_before": board_before,
            "board_sha256_after": sha256(BOARD),
            "drc_ceiling_sha256_before": ceiling_before,
            "drc_ceiling_sha256_after": sha256(DRC_CEILING),
            "changed": board_before != sha256(BOARD) or ceiling_before != sha256(DRC_CEILING),
        },
    }
    return manifest, terminal_text, baseline_drc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scratch",
        type=Path,
        default=Path("/tmp/compound-engineering-1000/net41-corridor-execution-20260901"),
    )
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    manifest, terminal_text, baseline_drc = run(args.scratch.resolve())
    baseline_drc_bytes = canonical_bytes(baseline_drc)
    terminal_bytes = terminal_text.encode()
    manifest["terminal_receipt_sha256"] = sha256_bytes(terminal_bytes)
    manifest_bytes = canonical_bytes(manifest)
    manifest_path = EVIDENCE / "candidate-manifest.json"
    terminal_path = EVIDENCE / "terminal-receipt.json"
    baseline_drc_path = EVIDENCE / "baseline-drc-preflight.json"
    if args.replay:
        if baseline_drc_path.read_bytes() != baseline_drc_bytes:
            raise SystemExit("replay mismatch: baseline DRC preflight differs")
        if manifest_path.read_bytes() != manifest_bytes:
            raise SystemExit("replay mismatch: candidate manifest differs")
        if terminal_path.read_bytes() != terminal_bytes:
            raise SystemExit("replay mismatch: terminal receipt differs")
        print("REPLAY PASS", json.loads(terminal_text)["status"], sha256_bytes(terminal_bytes))
        return 0
    baseline_drc_path.write_bytes(baseline_drc_bytes)
    manifest_path.write_bytes(manifest_bytes)
    terminal_path.write_bytes(terminal_bytes)
    terminal = json.loads(terminal_text)
    print("TERMINAL", terminal["status"], terminal["reason"])
    print("MANIFEST", sha256_bytes(manifest_bytes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
