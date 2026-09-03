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
import threading
from concurrent.futures import ThreadPoolExecutor
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
SCRIPTS = ROOT / "scripts"
J1_SUPPLEMENT = (
    ROOT / "docs/evidence/k1-j1-domain-refloorplan-20260831/approved-j1-footprint.kicad_mod"
)
J1_SUPPLEMENT_SHA256 = "050fe934d6208d5bd0e8d73da760c525c11185ac838b9c44b09b9cdf20f86a76"
FEASIBILITY_EVIDENCE = ROOT / "docs/evidence/net41-corridor-feasibility-20260902"
FEASIBILITY_CHECKPOINT_NAME = "pre-route-feasibility-checkpoint.json"
FEASIBILITY_RECEIPT_NAME = "feasibility-receipt.json"
FEASIBILITY_MANIFEST_NAME = "feasibility-manifest.json"
FEASIBILITY_EXIT_CODES = {
    "witness-clean": 0,
    "model-incomplete": 20,
    "instrument-error": 21,
    "stopped-indeterminate": 22,
    "witness-rejected": 23,
}
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# These imports include pyo3 modules (directly or through their Python
# adapters).  Keep them behind the executable bootstrap below: importing a
# broken .so before ``make extensions-check`` turns the intended diagnostic
# into an unhelpful ImportError and can leave callers believing a campaign
# was attempted.  Module imports still load the dependencies at the end of
# this file so the established test/import API remains unchanged.
RUNTIME_READY = False
RUST_FOOTPRINT_SCOPE: dict[str, object] = {}


def _load_runtime_dependencies() -> None:
    """Load extension-backed campaign dependencies exactly once."""
    global RUNTIME_READY, RUST_FOOTPRINT_SCOPE
    global drc_determinism, uncapped_drc, route_board, design_bundle
    global temper_drc_rs, temper_geometry, temper_quality_oracle, Polygon
    global shape_code, extract_fab_bodies
    global extract_fab_body_coverage_with_j1_supplement
    global extract_kicad_metadata, load_real_board_placement, _component_pads
    global verify_iec60335_compliance, extract_board_netlist
    global parse_design_netlist, reconcile

    if RUNTIME_READY:
        return

    import check_drc_determinism as loaded_drc_determinism
    import measure_uncapped_drc as loaded_uncapped_drc
    import route_board as loaded_route_board
    import temper_design_bundle_python as loaded_design_bundle
    import temper_drc_rs as loaded_drc_rs
    import temper_geometry as loaded_geometry
    import temper_quality_oracle as loaded_quality_oracle
    from shapely.geometry import Polygon as loaded_polygon

    from temper_placer.core.pad_geometry import shape_code as loaded_shape_code
    from temper_placer.io.fab_body_extraction import (
        extract_fab_bodies as loaded_extract_fab_bodies,
    )
    from temper_placer.io.fab_body_extraction import (
        extract_fab_body_coverage_with_j1_supplement as loaded_extract_fab_body_coverage,
    )
    from temper_placer.io.kicad_metadata import extract_kicad_metadata as loaded_extract_metadata
    from temper_placer.io.real_board import load_real_board_placement as loaded_load_placement
    from temper_placer.requirements.validators._copper import (
        _component_pads as loaded_component_pads,
    )
    from temper_placer.requirements.validators.clearance import (
        verify_iec60335_compliance as loaded_verify_compliance,
    )
    from temper_placer.validation.netlist_reconciliation import (
        extract_board_netlist as loaded_extract_board_netlist,
    )
    from temper_placer.validation.netlist_reconciliation import (
        parse_design_netlist as loaded_parse_design_netlist,
    )
    from temper_placer.validation.netlist_reconciliation import (
        reconcile as loaded_reconcile,
    )

    drc_determinism = loaded_drc_determinism
    uncapped_drc = loaded_uncapped_drc
    route_board = loaded_route_board
    design_bundle = loaded_design_bundle
    temper_drc_rs = loaded_drc_rs
    temper_geometry = loaded_geometry
    temper_quality_oracle = loaded_quality_oracle
    Polygon = loaded_polygon
    shape_code = loaded_shape_code
    extract_fab_bodies = loaded_extract_fab_bodies
    extract_fab_body_coverage_with_j1_supplement = loaded_extract_fab_body_coverage
    extract_kicad_metadata = loaded_extract_metadata
    load_real_board_placement = loaded_load_placement
    _component_pads = loaded_component_pads
    verify_iec60335_compliance = loaded_verify_compliance
    extract_board_netlist = loaded_extract_board_netlist
    parse_design_netlist = loaded_parse_design_netlist
    reconcile = loaded_reconcile
    RUST_FOOTPRINT_SCOPE = json.loads(
        temper_quality_oracle.corridor_footprint_scope_json_py()
    )
    RUNTIME_READY = True
_SILK_PROJECTION_LOCKS: dict[str, threading.Lock] = {}
_SILK_PROJECTION_LOCKS_GUARD = threading.Lock()


def _silk_projection_lock(projection_sha256: str) -> threading.Lock:
    with _SILK_PROJECTION_LOCKS_GUARD:
        return _SILK_PROJECTION_LOCKS.setdefault(projection_sha256, threading.Lock())


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _semantic_envelope_identity(samples: list[list[dict]]) -> dict[str, object]:
    """Return the compact Rust-owned identity needed to bind reusable evidence."""
    envelope = json.loads(
        temper_drc_rs.drc_evidence_envelope_json(json.dumps(samples, separators=(",", ":")))
    )
    identity: dict[str, object] = {
        "schema": envelope["schema"],
        "sample_count": envelope["sample_count"],
    }
    for level in ("family", "observation"):
        bag = envelope[level]
        identity[level] = {
            "stable": bag["stable"],
            "sample_digests": sorted(set(bag["sample_digests"])),
            "intersection_size": bag["intersection_size"],
            "union_size": bag["union_size"],
        }
    return identity


def _silk_scope_index(receipt: object) -> dict[str, object] | None:
    if not isinstance(receipt, dict):
        return None
    keys = (
        "schema",
        "source_sha256",
        "subject_sha256",
        "silk_projection_sha256",
        "instrument_context_sha256",
        "partition_manifest_sha256",
        "leaf_hashes",
        "expected_pair_count",
        "covered_pair_count",
        "complete",
    )
    return {
        "receipt_sha256": sha256_bytes(canonical_bytes(receipt)),
        **{key: receipt[key] for key in keys if key in receipt},
    }


def _instrument_payload_index(payloads: dict[str, object]) -> dict[str, object]:
    """Content-bind full transient payloads without duplicating them per candidate."""
    instruments: dict[str, object] = {}
    for name, payload in sorted(payloads.items()):
        payload_bytes = canonical_bytes(payload)
        entry: dict[str, object] = {
            "payload_sha256": sha256_bytes(payload_bytes),
            "payload_bytes": len(payload_bytes),
        }
        if name == "normalized-kicad-drc" and isinstance(payload, dict):
            samples = payload.get("semantic_samples")
            categories = payload.get("categories")
            entry["summary"] = {
                key: payload[key]
                for key in (
                    "board_sha256",
                    "sample_count",
                    "capped_categories",
                    "admission_comparison",
                )
                if key in payload
            }
            if isinstance(categories, list):
                category_keys = (
                    "category",
                    "at_cap",
                    "counts",
                    "count_stable",
                    "distinct_set_count_at_least",
                    "set_stable",
                    "intersection_size",
                    "union_size",
                    "raw_set_stable",
                    "raw_intersection_size",
                    "raw_union_size",
                )
                entry["summary"]["category_index"] = [
                    {key: category[key] for key in category_keys if key in category}
                    for category in categories
                    if isinstance(category, dict)
                ]
            if isinstance(samples, list):
                entry["summary"]["engineering_identity"] = _semantic_envelope_identity(samples)
            entry["summary"]["silk_scope"] = _silk_scope_index(
                payload.get("silk_scope_receipt")
            )
        instruments[name] = entry
    return {
        "schema": "temper-net41-instrument-payload-index/v1",
        "instruments": instruments,
    }


def _baseline_admission_context_sha256(baseline_drc: dict[str, object]) -> str:
    """Bind resume to engineering evidence while excluding provider-only churn."""
    samples = baseline_drc.get("semantic_samples")
    if not isinstance(samples, list):
        return sha256_bytes(canonical_bytes(baseline_drc))
    context = {
        "schema": "temper-net41-baseline-admission-context/v1",
        "receipt_schema": baseline_drc.get("schema_version"),
        "board_sha256": baseline_drc.get("board_sha256"),
        "kicad_cli_version": baseline_drc.get("kicad_cli_version"),
        "sample_count": baseline_drc.get("sample_count"),
        "capped_categories": baseline_drc.get("capped_categories"),
        "engineering_identity": _semantic_envelope_identity(samples),
        "silk_scope": _silk_scope_index(baseline_drc.get("silk_scope_receipt")),
        "trusted_for_candidate_admission": baseline_drc.get(
            "trusted_for_candidate_admission"
        ),
    }
    return sha256_bytes(canonical_bytes(context))


def _load_materialization_checkpoint(
    path: Path, *, candidate_id: str, board_sha256: str, instrument_context_sha256: str
) -> dict | None:
    """Load only a complete, content-bound pre-route measurement."""
    if not path.is_file():
        return None
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        checkpoint.get("schema") != "temper-net41-materialization-checkpoint/v4"
        or checkpoint.get("candidate_id") != candidate_id
        or checkpoint.get("scratch_board_sha256") != board_sha256
        or checkpoint.get("instrument_context_sha256") != instrument_context_sha256
        or checkpoint.get("evidence", {}).get("instrument_state") != "trusted"
        or checkpoint.get("instrument_payload_index", {}).get("schema")
        != "temper-net41-instrument-payload-index/v1"
    ):
        return None
    return checkpoint


def _write_materialization_checkpoint(path: Path, checkpoint: dict) -> None:
    """Atomically persist one conclusive candidate for exact resume."""
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_bytes(checkpoint))
    temporary.replace(path)


def _try_write_materialization_checkpoint(path: Path, checkpoint: dict) -> str | None:
    """Persist resume state without converting good instrument evidence into failure."""
    try:
        _write_materialization_checkpoint(path, checkpoint)
    except OSError as error:
        return str(error)
    return None


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


EXTENSION_BOOTSTRAP_EXIT_CODE = 70
_EXTENSION_FRESHNESS_RECEIPT = "PASSED -- 10/10 extension module(s) fresh."


def _bootstrap_executable_runtime() -> bool:
    """Certify native extensions before importing any extension-backed code.

    This is deliberately a separate gate from the campaign's instrument
    preflight.  A stale or unloadable pyo3 module can prevent that preflight
    from running at all, so the executable must stop before it can create
    campaign evidence.  The module-import path below remains available for
    tests and library callers, which have historically imported this script
    as a Python module.
    """
    try:
        output = run_checked(["make", "extensions-check"])
    except Exception as error:
        print(
            "BOOTSTRAP ERROR: pyo3 extension freshness check failed; "
            f"no campaign was started: {error}",
            file=sys.stderr,
        )
        return False
    if _EXTENSION_FRESHNESS_RECEIPT not in output:
        print(
            "BOOTSTRAP ERROR: pyo3 extension freshness check omitted its "
            "10/10 pass receipt; no campaign was started",
            file=sys.stderr,
        )
        return False
    try:
        _load_runtime_dependencies()
    except Exception as error:
        print(
            "BOOTSTRAP ERROR: certified pyo3 extensions could not be imported; "
            f"no campaign was started: {error}",
            file=sys.stderr,
        )
        return False
    return True


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


def semantic_samples(runs: list[dict[str, list[dict]]]) -> list[list[dict]]:
    """Flatten grouped raw runs without changing Rust-owned category identity."""
    return [[finding for category in sorted(run) for finding in run[category]] for run in runs]


def drc_admission_comparison(
    *,
    baseline_samples: list[list[dict]],
    candidate_samples: list[list[dict]],
    baseline_capped: list[str],
    candidate_capped: list[str],
    baseline_silk: dict | None,
    candidate_silk: dict | None,
    version: int = 2,
) -> dict:
    if version not in (2, 3):
        raise ValueError(f"unsupported DRC admission comparison version: {version}")
    request = {
        "baseline_samples": baseline_samples,
        "candidate_samples": candidate_samples,
        "baseline_capped_categories": baseline_capped,
        "candidate_capped_categories": candidate_capped,
        "baseline_silk_receipt": baseline_silk,
        "candidate_silk_receipt": candidate_silk,
    }
    request_json = json.dumps(request, separators=(",", ":"))
    if version == 3:
        return json.loads(temper_drc_rs.drc_admission_comparison_v3_json(request_json))
    return json.loads(temper_drc_rs.drc_admission_comparison_json(request_json))


def preflight(
    board_sha256: str, scratch: Path
) -> tuple[list[dict[str, object]], dict[str, object]]:
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
            instrument_row("pyo3-extensions", "error", str(error), board_sha256, payload)
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
        pass_line = next(line.strip() for line in oracle.splitlines() if line.startswith("PASS"))
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
            instrument_row("pcbnew-rotation-oracle", "error", str(error), board_sha256, payload)
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
        samples = semantic_samples(drc_runs)
        silk_receipt = None
        if any(category.removeprefix("W:") == "silk_overlap" for category in capped):
            silk_receipt = uncapped_drc.measure_silk_mutation_cone(
                source_board=BOARD,
                subject_board=BOARD,
                declared_refs=list(RUST_FOOTPRINT_SCOPE["affected_refs"]),
                use_declared_scope=True,
                scratch_dir=scratch / "baseline-silk-scope",
            )
        comparison = drc_admission_comparison(
            baseline_samples=samples,
            candidate_samples=samples,
            baseline_capped=capped,
            candidate_capped=capped,
            baseline_silk=silk_receipt,
            candidate_silk=silk_receipt,
        )
        unresolved = comparison["unresolved_cap_categories"]
        failures = [
            *(f"unresolved reporting cap {category}" for category in unresolved),
            *([] if comparison["semantic_repeats_agree"] else ["semantic repeat disagreement"]),
        ]
        drc_receipt = {
            "schema_version": "temper-net41-baseline-drc-preflight/v2",
            "board_sha256": board_sha256,
            "kicad_cli_version": version,
            "sample_count": len(drc_runs),
            "categories": drc_analysis,
            "capped_categories": capped,
            "semantic_samples": samples,
            "silk_scope_receipt": silk_receipt,
            "admission_comparison": comparison,
            "trusted_for_candidate_admission": not failures,
        }
        detail = (
            f"version {version}; DRC admission evidence is untrusted: " + "; ".join(failures)
            if failures
            else (
                f"version {version}; 3 semantic repeats agree; raw caps retained "
                "with complete scoped silk coverage"
            )
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
            instrument_row("baseline-kicad-drc", "error", str(error), board_sha256, drc_receipt)
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
    declared = [(ref, *placements[ref]) for ref in RUST_FOOTPRINT_SCOPE["movable_refs"]]
    declared.append(("R14", endpoint_x_mm, 249.56, 270.0))
    return design_bundle.parse_engine.update_declared_footprint_positions_exact_py(source, declared)


def _applicable_selv_pads_from_model(
    placement: dict[str, object], domains: dict[str, object]
) -> tuple[list[tuple[str, tuple, str]], int]:
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


def applicable_selv_pads(board_path: Path) -> tuple[list[tuple[str, tuple, str]], int]:
    placement, domains, _stats = load_real_board_placement(board_path, DOMAIN_MANIFEST, NETLIST)
    return _applicable_selv_pads_from_model(placement, domains)


def measure_candidate(candidate: dict[str, object], pads: list[tuple[str, tuple, str]]) -> dict:
    points = [tuple(map(float, point)) for point in candidate["route_points"]]
    distances: list[tuple[float, str]] = []
    for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
        for label, spec, layer in pads:
            if layer == "all" or layer == ROUTE_LAYER:
                value = temper_geometry.pad_to_capsule_distance_py(spec, start, end, ROUTE_WIDTH_MM)
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
        "route_length_mm": sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False)),
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
    placement, domains, stats = load_real_board_placement(board_path, DOMAIN_MANIFEST, NETLIST)
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
    for reference in RUST_FOOTPRINT_SCOPE["affected_refs"]:
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


def repeated_drc_receipt(
    board_path: Path, baseline: dict[str, object], *, comparison_version: int = 2
) -> tuple[dict, bool, dict]:
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
    samples = semantic_samples(runs)
    silk_receipt = None
    if any(
        category.removeprefix("W:") == "silk_overlap"
        for category in set(capped) | set(baseline["capped_categories"])
    ):
        declared_refs = list(RUST_FOOTPRINT_SCOPE["affected_refs"])
        bootstrap = uncapped_drc._rust_silk_scope_receipt(
            {
                "source_board": BOARD.read_text(encoding="utf-8"),
                "subject_board": board_path.read_text(encoding="utf-8"),
                "declared_refs": declared_refs,
                "use_declared_scope": False,
                "raw_global_capped": True,
                "instrument_context": uncapped_drc.silk_instrument_context(BOARD),
                "leaves": [],
            }
        )
        projection = bootstrap["silk_projection_sha256"]
        projection_root = board_path.parents[1] / "silk-projection-cache" / projection
        with _silk_projection_lock(projection):
            silk_receipt = uncapped_drc.measure_silk_mutation_cone(
                source_board=BOARD,
                subject_board=board_path,
                declared_refs=declared_refs,
                scratch_dir=projection_root,
                partition_seed=baseline.get("silk_scope_receipt"),
            )
    comparison = drc_admission_comparison(
        baseline_samples=baseline["semantic_samples"],
        candidate_samples=samples,
        baseline_capped=baseline["capped_categories"],
        candidate_capped=capped,
        baseline_silk=baseline.get("silk_scope_receipt"),
        candidate_silk=silk_receipt,
        version=comparison_version,
    )
    # Rust separates evidence availability from candidate admission. A
    # conclusive new/worsened hard finding or scoped silk finding is a real
    # candidate veto, not an instrument failure.
    trusted = comparison["instrument_conclusive"]
    payload = {
        "board_sha256": sha256(board_path),
        "sample_count": len(runs),
        "categories": categories,
        "capped_categories": capped,
        "semantic_samples": samples,
        "silk_scope_receipt": silk_receipt,
        "admission_comparison": comparison,
    }
    return payload, trusted, comparison


def inspect_materialized_candidate(
    candidate_path: Path,
    instruction: dict[str, object],
    baseline: dict[str, object],
    baseline_drc: dict[str, object],
    *,
    comparison_version: int = 2,
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
    connected = snapshot["net41_component_count"] == 1 and not snapshot["net41_isolated_pad_ids"]
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
        temper_geometry.ipc2221b_current_capacity_a_py(ROUTE_WIDTH_MM, 1.0, 10.0, True)
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
    contained = containment_failures(baseline["bodies"], positions, placement["board"]["outline"])
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
    drc_payload, drc_trusted, drc_comparison = repeated_drc_receipt(
        candidate_path, baseline_drc, comparison_version=comparison_version
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
            "drc_category_states": drc_comparison["category_states"],
            "drc_semantic_repeats_agree": drc_comparison["semantic_repeats_agree"],
            "drc_new_hard_observation_count": drc_comparison["new_hard_observation_count"],
            "drc_worsened_hard_observation_count": drc_comparison[
                "worsened_hard_observation_count"
            ],
            "drc_indeterminate_hard_comparison_count": drc_comparison[
                "indeterminate_hard_comparison_count"
            ],
            "drc_new_scoped_silk_finding_count": drc_comparison["new_scoped_silk_finding_count"],
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
        "drc_category_states": {},
        "drc_semantic_repeats_agree": False,
        "drc_new_hard_observation_count": 0,
        "drc_worsened_hard_observation_count": 0,
        "drc_indeterminate_hard_comparison_count": 1,
        "drc_new_scoped_silk_finding_count": 0,
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
        "drc_category_states": {},
        "drc_semantic_repeats_agree": False,
        "drc_new_hard_observation_count": 0,
        "drc_worsened_hard_observation_count": 0,
        "drc_indeterminate_hard_comparison_count": 1,
        "drc_new_scoped_silk_finding_count": 0,
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


def _feasibility_checkpoint_binding(binding: dict[str, object]) -> str:
    """Digest the complete replay boundary, including nested instrument data."""
    return sha256_bytes(canonical_bytes(binding))


def _write_feasibility_checkpoint(path: Path, checkpoint: dict[str, object]) -> None:
    """Atomically write the one-witness feasibility checkpoint."""
    _write_atomic_bytes(path, canonical_bytes(checkpoint))


def _write_atomic_bytes(path: Path, value: bytes) -> None:
    """Atomically write a mode output without exposing a partial receipt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _load_feasibility_checkpoint(
    path: Path, *, binding: dict[str, object]
) -> dict[str, object] | None:
    """Reuse only a checkpoint whose every authority and payload is unchanged."""
    if not path.is_file():
        return None
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(checkpoint, dict):
        return None
    if checkpoint.get("schema") != "temper-net41-feasibility-checkpoint/v1":
        return None
    if checkpoint.get("binding") != binding:
        return None
    if checkpoint.get("binding_sha256") != _feasibility_checkpoint_binding(binding):
        return None
    return checkpoint


def _validate_feasibility_replay(
    scratch: Path,
    checkpoint_path: Path,
    receipt_path: Path,
    manifest_path: Path,
    baseline_drc_path: Path,
) -> dict[str, object]:
    """Validate a stored feasibility result against current authorities."""
    if not all(
        path.is_file()
        for path in (checkpoint_path, receipt_path, manifest_path, baseline_drc_path)
    ):
        raise ValueError("checkpoint, baseline DRC, or feasibility output is missing")
    raw = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("binding"), dict):
        raise ValueError("checkpoint binding is missing")
    checkpoint = _load_feasibility_checkpoint(
        checkpoint_path, binding=raw["binding"]
    )
    if checkpoint is None:
        raise ValueError("checkpoint binding digest is invalid")
    binding = raw["binding"]
    receipt_bytes = receipt_path.read_bytes()
    baseline_drc_bytes = baseline_drc_path.read_bytes()
    baseline_drc = json.loads(baseline_drc_bytes)
    if not isinstance(baseline_drc, dict):
        raise ValueError("stored baseline DRC preflight is not an object")
    expected_baseline_hash = binding.get("baseline_drc_preflight_sha256")
    if expected_baseline_hash != sha256_bytes(baseline_drc_bytes):
        raise ValueError("stored baseline DRC preflight artifact drifted")
    baseline_row = next(
        (
            row
            for row in binding.get("preflight", [])
            if isinstance(row, dict) and row.get("name") == "baseline-kicad-drc"
        ),
        None,
    )
    if not isinstance(baseline_row, dict) or baseline_row.get("receipt_sha256") != sha256_bytes(
        canonical_bytes(baseline_drc)
    ):
        raise ValueError("stored baseline DRC preflight is not bound to its instrument receipt")
    if baseline_drc_bytes != canonical_bytes(baseline_drc):
        raise ValueError("stored baseline DRC preflight is not canonical")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_bytes)
    if checkpoint.get("receipt") != receipt:
        raise ValueError("stored checkpoint and receipt differ")
    if manifest.get("terminal_receipt_sha256") != sha256_bytes(receipt_bytes):
        raise ValueError("stored manifest does not bind the receipt bytes")
    current_inputs = evidence_kwargs()
    authorities = binding.get("authorities", {})
    if authorities.get("production_board_sha256") != sha256(BOARD):
        raise ValueError("production board drift invalidated feasibility replay")
    if authorities.get("drc_ceiling_sha256") != sha256(DRC_CEILING):
        raise ValueError("DRC ceiling drift invalidated feasibility replay")
    current_declaration = json.loads(
        temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
            current_inputs["declaration_bytes"],
            current_inputs["predecessor_manifest_bytes"],
        )
    )
    current_generated = current_declaration["generated_input_hashes"]
    if authorities.get("generated_input_sha256s") != current_generated:
        raise ValueError("generated input drift invalidated feasibility replay")
    current_rows, coverage, _placement, model_error = _feasibility_model_rows(BOARD)
    if binding.get("model_requirements") != current_rows:
        raise ValueError("model requirements drift invalidated feasibility replay")
    screening = binding.get("screening")
    authorities = binding.get("authorities")
    model_requirements = binding.get("model_requirements")
    preflight = binding.get("preflight")
    prepared_stored = binding.get("prepared_receipt")
    if not isinstance(screening, dict) or not isinstance(authorities, dict):
        raise ValueError("feasibility checkpoint is missing the prepare request binding")
    if not isinstance(model_requirements, list) or not isinstance(preflight, list):
        raise ValueError("feasibility checkpoint is missing bound model or preflight data")
    if not isinstance(prepared_stored, dict):
        raise ValueError("feasibility checkpoint is missing the prepared receipt binding")
    prepare_request = {
        "schema_version": "temper-corridor-feasibility-prepare/v1",
        "screening": screening,
        "authorities": authorities,
        "model_requirements": model_requirements,
        "preflight": preflight,
    }
    try:
        prepared_rederived = json.loads(
            temper_quality_oracle.prepare_corridor_feasibility_json_py(
                **current_inputs,
                feasibility_request_json=json.dumps(prepare_request),
            )
        )
    except Exception as error:
        raise ValueError(f"Rust prepare rederivation rejected the checkpoint: {error}") from error
    if prepared_rederived != prepared_stored:
        raise ValueError("Rust prepare rederivation differs from the bound prepared receipt")
    for field, label in (
        ("declaration_hash", "declaration hash"),
        ("candidate_set_digest", "candidate-set digest"),
    ):
        expected = binding.get(field)
        if (
            not isinstance(expected, str)
            or prepared_rederived.get(field) != expected
            or receipt.get(field) != expected
        ):
            raise ValueError(f"Rust prepare {label} differs from the checkpoint binding")
    witness = binding.get("witness")
    receipt_witness = receipt.get("witness")
    replay_witness = witness if witness is not None else receipt_witness
    model_complete = not model_error and bool(coverage) and coverage.complete
    if not model_complete:
        if receipt.get("terminal") != "model-incomplete" or witness is not None or receipt_witness is not None:
            raise ValueError("model coverage drift invalidated feasibility replay")
    elif replay_witness is not None:
        candidate_path = scratch / "feasibility-witness" / replay_witness["candidate_id"] / "temper.kicad_pcb"
        if not candidate_path.is_file() or binding.get("scratch_board_sha256") != sha256(candidate_path):
            raise ValueError("witness subject drift invalidated feasibility replay")
        instruments = binding.get("witness_instruments")
        evidence = binding.get("evidence")
        if not isinstance(instruments, list) or not isinstance(evidence, dict):
            raise ValueError("feasibility checkpoint is missing bound witness evidence")
        witness_request = prepared_rederived.get("witness")
        if not isinstance(witness_request, dict):
            raise ValueError("Rust prepare rederivation produced no witness")
        finalize_request = {
            "schema_version": "temper-corridor-feasibility-finalize/v1",
            "prepared": prepared_rederived,
            "authorities": authorities,
            "model_requirements": model_requirements,
            "screening": screening,
            "witness_id": witness_request["witness_id"],
            "declaration_ordinal": witness_request["declaration_ordinal"],
            "materialization_instruction": witness_request["materialization_instruction"],
            "scratch_board_sha256": sha256(candidate_path),
            "instruments": instruments,
            "evidence": evidence,
        }
        try:
            receipt_rederived = json.loads(
                temper_quality_oracle.finalize_corridor_feasibility_json_py(
                    **current_inputs,
                    feasibility_request_json=json.dumps(finalize_request),
                )
            )
        except Exception as error:
            raise ValueError(f"Rust finalize rederivation rejected the checkpoint: {error}") from error
        if receipt_rederived != receipt:
            raise ValueError("Rust finalize rederivation differs from the stored receipt")
    return receipt


def _exact_east_shift_parent_rows(predecessor: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return the legacy path's exact, unique east-shift parent population."""
    results = predecessor.get("results")
    if not isinstance(results, list):
        raise RuntimeError("predecessor manifest results are missing")
    rows = [
        row
        for row in results
        if isinstance(row, dict) and row.get("east_shift_mm") == 4.0
    ]
    if len(rows) != 60:
        raise RuntimeError(f"expected 60 exact predecessor placements, got {len(rows)}")
    ids = [row.get("predecessor_placement_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids):
        raise RuntimeError("exact predecessor placements must have non-empty IDs")
    if len(set(ids)) != len(ids):
        raise RuntimeError("exact predecessor placements contain duplicate IDs")
    return {row["predecessor_placement_id"]: row for row in rows}


def _feasibility_model_rows(
    board_path: Path,
) -> tuple[list[dict[str, object]], object, dict[str, object], str | None]:
    """Build complete Rust model rows before the candidate root is created."""
    refs = list(RUST_FOOTPRINT_SCOPE["affected_refs"])
    try:
        coverage = extract_fab_body_coverage_with_j1_supplement(
            board_path,
            refs,
            J1_SUPPLEMENT,
            J1_SUPPLEMENT_SHA256,
        )
        placement, domains, _stats = load_real_board_placement(
            board_path, DOMAIN_MANIFEST, NETLIST
        )
        components = {
            str(component.get("ref", component.get("reference", ""))): component
            for component in placement.get("components", [])
        }
        positions = footprint_positions(board_path.read_text(encoding="utf-8"))
        # applicable_selv_pads enforces and therefore proves the immutable
        # denominator; this mode does not duplicate its literal here.
        _applicable_selv_pads_from_model(placement, domains)
        rows = []
        for reference in refs:
            component = components.get(reference)
            pads = list(_component_pads(component)) if component is not None else []
            # ``load_real_board_placement`` deliberately carries only the
            # component's classified nets in ``component["nets"]`` while its
            # physical pads retain the full board annotation. The safety
            # validators use that same any-classified-net membership rule;
            # requiring every pad net here would turn the manifest's
            # intentional partial coverage into a false model failure.
            classified_domains = {
                domains[net]
                for net in component.get("nets", ())
                if net in domains
            } if component is not None else set()
            domain_complete = bool(component) and bool(pads) and len(classified_domains) == 1
            rows.append(
                {
                    "reference": reference,
                    "body_geometry": reference in coverage.present,
                    "position": reference in positions and component is not None,
                    "domain": domain_complete,
                    "complete_selv_denominator": True,
                }
            )
        missing = [
            f"{row['reference']}:{field}"
            for row in rows
            for field in ("body_geometry", "position", "domain", "complete_selv_denominator")
            if not row[field]
        ]
        return rows, coverage, placement, ", ".join(missing) if missing else None
    except Exception as error:  # model errors become Rust model-incomplete evidence
        return [
            {
                "reference": reference,
                "body_geometry": False,
                "position": False,
                "domain": False,
                "complete_selv_denominator": False,
            }
            for reference in refs
        ], None, {}, str(error)


def _feasibility_authorities(
    candidate_set: dict[str, object],
    board_hash: str,
    ceiling_hash: str,
    model_rows: list[dict[str, object]],
    preflight_rows: list[dict[str, object]],
) -> dict[str, object]:
    generated = candidate_set["generated_input_hashes"]
    tool_context = {
        "schema": "temper-net41-feasibility-tool-context/v1",
        "preflight": preflight_rows,
        "model_requirements": model_rows,
    }
    return {
        "production_board_sha256": board_hash,
        "drc_ceiling_sha256": ceiling_hash,
        "generated_input_sha256s": generated,
        "model_source_sha256s": [J1_SUPPLEMENT_SHA256],
        "tool_context_sha256": _feasibility_checkpoint_binding(tool_context),
    }


def _feasibility_baseline_binding(baseline_drc: dict[str, object]) -> str:
    """Return the exact artifact hash used to bind replay's baseline receipt."""
    return sha256_bytes(canonical_bytes(baseline_drc))


def _feasibility_screen(
    scratch: Path,
    inputs: dict[str, bytes],
    candidate_set: dict[str, object],
    source: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Measure the immutable family in Rust order without making candidates."""
    predecessor = json.loads(inputs["predecessor_manifest_bytes"])
    parent_rows = _exact_east_shift_parent_rows(predecessor)
    project = scratch / "project"
    project.mkdir(parents=True, exist_ok=True)
    project_board = project / "temper.kicad_pcb"
    project_board.write_text(source, encoding="utf-8")
    measurements: list[dict[str, object]] = []
    detailed: dict[str, object] = {}
    grouped: dict[tuple[str, float], list[dict]] = {}
    for candidate in candidate_set["candidates"]:
        grouped.setdefault(
            (candidate["placement_id"], float(candidate["endpoint_x_mm"])), []
        ).append(candidate)
    for (placement_id, endpoint_x), rows in grouped.items():
        parent = parent_rows.get(placement_id)
        if parent is None:
            raise RuntimeError(
                f"declared candidate placement_id has no exact predecessor parent: {placement_id}"
            )
        base_text = exact_placement_board(source, parent["placements"], endpoint_x)
        project_board.write_text(base_text, encoding="utf-8")
        # Placement changes can alter which pads are route-applicable.  Keep
        # the historical per-base measurement boundary; never reuse the
        # first group's denominator for another group.
        pads, _total = applicable_selv_pads(project_board)
        for candidate in rows:
            measured = measure_candidate(candidate, pads)
            detailed[candidate["candidate_id"]] = measured
            measurements.append(
                {
                    key: measured[key]
                    for key in (
                        "candidate_id",
                        "minimum_clearance_mm",
                        "minimum_creepage_lower_bound_mm",
                        "route_length_mm",
                    )
                }
            )
    request = {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": measurements,
        "route_budget": 12,
    }
    screen = json.loads(
        temper_quality_oracle.validate_and_screen_corridor_evidence_json_py(
            **inputs, screening_request_json=json.dumps(request)
        )
    )
    return request, {"verdict": screen, "measurements": detailed}


def _finding_identity(category: str, identity: object, multiplicity: int = 1) -> dict[str, object]:
    return {
        "category": category,
        "identity": json.dumps(identity, sort_keys=True, separators=(",", ":"))
        if not isinstance(identity, str)
        else identity,
        "multiplicity": multiplicity,
    }


def _sealed_check(
    *,
    category: str,
    state: str,
    trust: str,
    findings: list[dict[str, object]],
    receipt_sha256: str | None,
) -> dict[str, object]:
    payload = {
        "evaluation": state,
        "trust": trust,
        "findings": findings,
        "receipt_sha256": receipt_sha256,
    }
    return json.loads(
        temper_quality_oracle.seal_corridor_check_evidence_json_py(
            json.dumps(payload, separators=(",", ":"))
        )
    )


def _typed_pre_route_evidence(
    evidence: dict[str, object], payloads: dict[str, object]
) -> dict[str, object]:
    """Translate instrument observations into Rust-owned typed checks."""
    receipt_by_name = {
        row["name"]: row for row in evidence.get("receipts", []) if isinstance(row, dict)
    }

    def check_receipt(name: str) -> str | None:
        row = receipt_by_name.get(name)
        return row.get("receipt_sha256") if row else None

    def check(
        name: str,
        findings: list[dict[str, object]],
        *,
        instrument: str | None = None,
        force_indeterminate: bool = False,
    ) -> dict[str, object]:
        instrument = instrument or name
        row = receipt_by_name.get(instrument, {})
        trust = "error" if row.get("state") == "error" else (
            "indeterminate" if force_indeterminate or row.get("state") == "indeterminate" else "trusted"
        )
        # An indeterminate instrument may still have a complete, typed
        # payload (for example a v3 DRC receipt with unresolved cap metadata).
        # Preserve that evaluated payload and its exact identities; only a
        # genuinely absent payload is not-evaluated.
        if trust == "error":
            # Rust represents an errored instrument as NotEvaluated + Error,
            # but still requires the real instrument receipt to prove which
            # execution failed. Dropping this hash turns a genuine instrument
            # failure into an invalid lifecycle payload.
            return _sealed_check(
                category=name,
                state="not-evaluated",
                trust=trust,
                findings=[],
                receipt_sha256=check_receipt(instrument),
            )
        if trust != "trusted" and not findings and not check_receipt(instrument):
            return _sealed_check(
                category=name,
                state="not-evaluated",
                trust=trust,
                findings=[],
                receipt_sha256=None,
            )
        state = "completed-with-findings" if findings else "completed-clean"
        return _sealed_check(
            category=name,
            state=state,
            trust=trust,
            findings=findings,
            receipt_sha256=check_receipt(instrument),
        )

    admission = evidence.get("admission", {})
    safety_payload = payloads.get("safety-signatures", {})
    safety_findings = [
        _finding_identity("safety", identity)
        for key in ("new_signatures", "worsened_signatures")
        for identity in safety_payload.get(key, [])
    ]
    drc_payload = payloads.get("normalized-kicad-drc", {})
    comparison = drc_payload.get("admission_comparison", {})
    drc_findings = []
    for field in (
        "new_hard_observations",
        "worsened_hard_observations",
        "indeterminate_hard_comparisons",
        "new_scoped_silk_findings",
    ):
        for entry in comparison.get(field, []):
            if isinstance(entry, dict):
                # ``count`` is bag multiplicity, not finding identity. Keeping
                # it in the identity makes an unchanged physical finding look
                # like a new identity whenever its occurrence count changes.
                count = int(entry.get("count", 1))
                identity_entry = {key: value for key, value in entry.items() if key != "count"}
            else:
                count = 1
                identity_entry = entry
            drc_findings.append(
                _finding_identity("drc", {"kind": field, "entry": identity_entry}, count)
            )

    def bool_finding(key: str, identity: str) -> list[dict[str, object]]:
        return [] if admission.get(key) else [_finding_identity("gate-failure", identity)]

    containment_payload = payloads.get("containment", {})
    containment_findings = []
    for failure in containment_payload.get("failures", []):
        category = "containment-missing-model" if str(failure).endswith(":missing-geometry") else "containment-outside-board"
        containment_findings.append(_finding_identity(category, failure))
    overlap_payload = payloads.get("body-courtyard-overlap", {})
    body_findings = [
        _finding_identity("body-overlap", value)
        for key in ("new_body", "worsened_body")
        for value in overlap_payload.get(key, [])
    ]
    courtyard_findings = [
        _finding_identity("courtyard-overlap", value)
        for key in ("new_courtyard", "worsened_courtyard")
        for value in overlap_payload.get(key, [])
    ]
    return {
        "safety": check("safety", safety_findings, instrument="safety-signatures"),
        "drc": check(
            "drc",
            drc_findings,
            instrument="normalized-kicad-drc",
            force_indeterminate=not bool(comparison.get("instrument_conclusive", True)),
        ),
        "containment": check("containment", containment_findings),
        "body_overlap": check("body_overlap", body_findings, instrument="body-courtyard-overlap"),
        "courtyard_overlap": check(
            "courtyard_overlap", courtyard_findings, instrument="body-courtyard-overlap"
        ),
        "connectivity": check(
            "connectivity",
            bool_finding("connected", "connectivity"),
        ),
        "selv_denominator": check(
            "selv_denominator",
            bool_finding("complete_selv_denominator", "selv-denominator"),
            instrument="selv-denominator",
        ),
        "route_geometry": check("route_geometry", bool_finding("route_geometry_valid", "route-geometry"), instrument="route-geometry-current-capacity"),
        "current_capacity": check("current_capacity", bool_finding("current_capacity_valid", "current-capacity"), instrument="route-geometry-current-capacity"),
        "mutation_scope": check(
            "mutation_scope",
            bool_finding("mutation_scope_valid", "mutation-scope"),
            instrument="mutation-scope",
        ),
        "netlist_reconciliation": _sealed_check(
            category="netlist_reconciliation",
            state="not-evaluated",
            trust="indeterminate",
            findings=[],
            receipt_sha256=None,
        ),
    }


def _pre_route_instruments(evidence: dict[str, object]) -> list[dict[str, object]]:
    rows = {row["name"]: row for row in evidence.get("receipts", [])}
    return [rows[name] for name in PRE_ROUTE_INSTRUMENTS]


def run_pre_route_feasibility(scratch: Path) -> tuple[dict[str, object], str, dict[str, object]]:
    """Run the bounded prepare/one-witness/finalize feasibility protocol."""
    board_before = sha256(BOARD)
    ceiling_before = sha256(DRC_CEILING)
    inputs = evidence_kwargs()
    preflight_rows, baseline_drc = preflight(board_before, scratch)
    preflight_rows = sorted(preflight_rows, key=lambda row: ("baseline-kicad-drc", "pcbnew-rotation-oracle", "pyo3-extensions").index(row["name"]))
    project = stage_project(scratch)
    source = inputs["board_bytes"].decode()
    project_board = project / "temper.kicad_pcb"
    project_board.write_text(source, encoding="utf-8")
    model_rows, coverage, placement, model_error = _feasibility_model_rows(project_board)
    candidate_set = json.loads(
        temper_quality_oracle.declare_corridor_candidates_from_evidence_json_py(
            inputs["declaration_bytes"], inputs["predecessor_manifest_bytes"]
        )
    )
    if len(candidate_set["candidates"]) != 2880:
        raise RuntimeError(f"Rust candidate cardinality drift: {len(candidate_set['candidates'])}")
    authorities = _feasibility_authorities(
        candidate_set, board_before, ceiling_before, model_rows, preflight_rows
    )
    empty_screening = {
        "schema_version": "temper-regional-validated-screen-request/v4",
        "candidates": [],
        "route_budget": 12,
    }
    prepare_request = {
        "schema_version": "temper-corridor-feasibility-prepare/v1",
        "screening": empty_screening,
        "authorities": authorities,
        "model_requirements": model_rows,
        "preflight": preflight_rows,
    }
    # Model and preflight terminals are decided before any candidate root or
    # screen materialization is created.
    if model_error or not (coverage and coverage.complete):
        prepared = json.loads(
            temper_quality_oracle.prepare_corridor_feasibility_json_py(
                **inputs, feasibility_request_json=json.dumps(prepare_request)
            )
        )
        return _feasibility_result(
            scratch,
            inputs,
            candidate_set,
            authorities,
            model_rows,
            preflight_rows,
            baseline_drc,
            prepared,
            {"verdict": empty_screening},
            board_before,
            ceiling_before,
            model_error,
        )
    if any(row["state"] != "trusted" for row in preflight_rows):
        prepared = json.loads(
            temper_quality_oracle.prepare_corridor_feasibility_json_py(
                **inputs, feasibility_request_json=json.dumps(prepare_request)
            )
        )
        return _feasibility_result(
            scratch, inputs, candidate_set, authorities, model_rows, preflight_rows,
            baseline_drc, prepared, {"verdict": empty_screening}, board_before, ceiling_before,
            None,
        )
    screening_request, screen_data = _feasibility_screen(scratch, inputs, candidate_set, source)
    prepare_request["screening"] = screening_request
    prepared = json.loads(
        temper_quality_oracle.prepare_corridor_feasibility_json_py(
            **inputs, feasibility_request_json=json.dumps(prepare_request)
        )
    )
    if prepared["terminal"] != "witness-pending":
        return _feasibility_result(
            scratch, inputs, candidate_set, authorities, model_rows, preflight_rows,
            baseline_drc, prepared, screen_data, board_before, ceiling_before,
            None,
        )
    witness = prepared["witness"]
    candidate_root = scratch / "feasibility-witness"
    candidate_root.mkdir(parents=True, exist_ok=True)
    candidate_dir = candidate_root / witness["candidate_id"]
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for name in ("temper.kicad_pro", "temper.kicad_dru", "fp-lib-table"):
        shutil.copy2(project / name, candidate_dir / name)
    libraries = candidate_dir / "libs"
    if not libraries.exists():
        libraries.symlink_to(project / "libs", target_is_directory=True)
    candidate_path = candidate_dir / "temper.kicad_pcb"
    instruction = witness["materialization_instruction"]
    try:
        # The screen leaves the shared project board at its final base. Restore
        # the source subject before every baseline instrument, and keep the
        # whole baseline setup inside the materialization boundary. A failure
        # in any baseline instrument is evidence unavailability, not an
        # uncaught runner exception.
        project_board.write_text(source, encoding="utf-8")
        baseline_placement, baseline_safety, baseline_safety_receipt = safety_measure(project_board)
        baseline_positions = footprint_positions(source)
        bodies = coverage.present
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
        candidate_path.write_text(materialize_candidate(source, instruction), encoding="utf-8")
        witness_evidence, payloads = inspect_materialized_candidate(
            candidate_path, instruction, baseline, baseline_drc, comparison_version=3
        )
    except Exception as error:
        if not candidate_path.exists():
            candidate_path.write_text(source, encoding="utf-8")
        witness_evidence, payloads = unavailable_materialization_evidence(
            witness["candidate_id"], sha256(candidate_path), error
        )
    typed_evidence = _typed_pre_route_evidence(witness_evidence, payloads)
    finalize_request = {
        "schema_version": "temper-corridor-feasibility-finalize/v1",
        "prepared": prepared,
        "authorities": authorities,
        "model_requirements": model_rows,
        "screening": screening_request,
        "witness_id": witness["witness_id"],
        "declaration_ordinal": witness["declaration_ordinal"],
        "materialization_instruction": instruction,
        "scratch_board_sha256": sha256(candidate_path),
        "instruments": _pre_route_instruments(witness_evidence),
        "evidence": typed_evidence,
    }
    receipt = json.loads(
        temper_quality_oracle.finalize_corridor_feasibility_json_py(
            **inputs, feasibility_request_json=json.dumps(finalize_request)
        )
    )
    binding = {
        "declaration_hash": candidate_set["declaration_hash"],
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "generated_input_sha256s": authorities["generated_input_sha256s"],
        "model_requirements": model_rows,
        "model_requirements_sha256": receipt["model_requirements_sha256"],
        "authorities": authorities,
        "preflight": preflight_rows,
        # Keep the exact prepare output in the replay boundary.  Replaying
        # only the final receipt would allow a checkpoint to change prepare
        # semantics while preserving its outer hash.
        "prepared_receipt": prepared,
        "baseline_drc_preflight_sha256": _feasibility_baseline_binding(baseline_drc),
        "screening": screening_request,
        "witness": witness,
        "scratch_board_sha256": sha256(candidate_path),
        "instrument_payload_index": _instrument_payload_index(payloads),
        "witness_instruments": _pre_route_instruments(witness_evidence),
        "evidence": typed_evidence,
    }
    checkpoint = {
        "schema": "temper-net41-feasibility-checkpoint/v1",
        "binding": binding,
        "binding_sha256": _feasibility_checkpoint_binding(binding),
        "receipt": receipt,
    }
    _write_feasibility_checkpoint(scratch / FEASIBILITY_CHECKPOINT_NAME, checkpoint)
    manifest = _feasibility_manifest(
        candidate_set, authorities, model_rows, preflight_rows, receipt, candidate_path,
        payloads, screen_data,
    )
    manifest["checkpoint_binding_sha256"] = checkpoint["binding_sha256"]
    board_after = sha256(BOARD)
    ceiling_after = sha256(DRC_CEILING)
    manifest["production_authorities"] = {
        "board_sha256_before": board_before,
        "board_sha256_after": board_after,
        "drc_ceiling_sha256_before": ceiling_before,
        "drc_ceiling_sha256_after": ceiling_after,
        "changed": board_before != board_after or ceiling_before != ceiling_after,
    }
    if manifest["production_authorities"]["changed"]:
        raise RuntimeError("pre-route feasibility changed a production authority")
    return manifest, json.dumps(receipt, indent=2, sort_keys=True) + "\n", baseline_drc


def _feasibility_result(
    scratch: Path,
    inputs: dict[str, bytes],
    candidate_set: dict[str, object],
    authorities: dict[str, object],
    model_rows: list[dict[str, object]],
    preflight_rows: list[dict[str, object]],
    baseline_drc: dict[str, object],
    receipt: dict[str, object],
    screen_data: dict[str, object] | None,
    board_hash: str,
    ceiling_hash: str,
    model_error: str | None,
) -> tuple[dict[str, object], str, dict[str, object]]:
    """Serialize a zero-materialization terminal with the same bindings."""
    binding = {
        "declaration_hash": candidate_set["declaration_hash"],
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "generated_input_sha256s": authorities["generated_input_sha256s"],
        "model_requirements": model_rows,
        "model_requirements_sha256": receipt["model_requirements_sha256"],
        "authorities": authorities,
        "preflight": preflight_rows,
        "prepared_receipt": receipt,
        "baseline_drc_preflight_sha256": _feasibility_baseline_binding(baseline_drc),
        "screening": (screen_data or {}).get("verdict", {}),
        "witness": None,
        "scratch_board_sha256": None,
        "instrument_payload_index": _instrument_payload_index({}),
        "witness_instruments": [],
        "evidence": None,
    }
    _write_feasibility_checkpoint(
        scratch / FEASIBILITY_CHECKPOINT_NAME,
        {
            "schema": "temper-net41-feasibility-checkpoint/v1",
            "binding": binding,
            "binding_sha256": _feasibility_checkpoint_binding(binding),
            "receipt": receipt,
        },
    )
    manifest = _feasibility_manifest(
        candidate_set, authorities, model_rows, preflight_rows, receipt, None, {}, screen_data,
        model_error=model_error,
    )
    manifest["checkpoint_binding_sha256"] = _feasibility_checkpoint_binding(binding)
    manifest["production_authorities"] = {
        "board_sha256_before": board_hash,
        "board_sha256_after": sha256(BOARD),
        "drc_ceiling_sha256_before": ceiling_hash,
        "drc_ceiling_sha256_after": sha256(DRC_CEILING),
        "changed": board_hash != sha256(BOARD) or ceiling_hash != sha256(DRC_CEILING),
    }
    if manifest["production_authorities"]["changed"]:
        raise RuntimeError("pre-route feasibility changed a production authority")
    return manifest, json.dumps(receipt, indent=2, sort_keys=True) + "\n", baseline_drc


def _feasibility_manifest(
    candidate_set: dict[str, object], authorities: dict[str, object], model_rows: list[dict[str, object]],
    preflight_rows: list[dict[str, object]], receipt: dict[str, object], candidate_path: Path | None,
    payloads: dict[str, object], screen_data: dict[str, object] | None,
    *, model_error: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "temper-net41-feasibility-manifest/v1",
        "declaration_hash": candidate_set["declaration_hash"],
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "declared_count": len(candidate_set["candidates"]),
        "screened_count": len((screen_data or {}).get("verdict", {}).get("results", [])),
        "materialized_count": 1 if candidate_path else 0,
        "routed_count": 0,
        "terminal": receipt["terminal"],
        "reason": receipt["reason"],
        "model_error": model_error,
        "authorities": authorities,
        "model_requirements": model_rows,
        "preflight": preflight_rows,
        "witness": receipt.get("witness"),
        "candidate": str(candidate_path) if candidate_path else None,
        "instrument_payload_index": _instrument_payload_index(payloads),
    }


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
    reconciliation = reconcile(extract_board_netlist(routed_path), parse_design_netlist(NETLIST))
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
    instruments, baseline_drc = preflight(board_before, scratch)
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
    parent_rows = _exact_east_shift_parent_rows(predecessor)

    project = stage_project(scratch)
    source = inputs["board_bytes"].decode()
    project_board = project / "temper.kicad_pcb"
    project_board.write_text(source, encoding="utf-8")
    baseline_placement, baseline_safety, baseline_safety_receipt = safety_measure(project_board)
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
            measurements.append(
                {
                    key: measured[key]
                    for key in (
                        "candidate_id",
                        "minimum_clearance_mm",
                        "minimum_creepage_lower_bound_mm",
                        "route_length_mm",
                    )
                }
            )
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
    baseline_admission_context_sha256 = _baseline_admission_context_sha256(baseline_drc)

    def materialize_one(candidate_id: str) -> tuple[str, Path, dict, dict, dict | None]:
        candidate_dir = candidate_root / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        for name in ("temper.kicad_pro", "temper.kicad_dru", "fp-lib-table"):
            shutil.copy2(project / name, candidate_dir / name)
        libraries = candidate_dir / "libs"
        if not libraries.exists():
            libraries.symlink_to(project / "libs", target_is_directory=True)
        candidate_path = candidate_dir / "temper.kicad_pcb"
        instruction = None
        try:
            instruction_json = temper_quality_oracle.corridor_materialization_instruction_json_py(
                **inputs, candidate_id=candidate_id
            )
            instruction = json.loads(
                temper_quality_oracle.validate_corridor_materialization_instruction_json_py(
                    **inputs, instruction_json=instruction_json
                )
            )
            if candidate_lookup[candidate_id]["route_points"] != instruction["route_points"]:
                raise RuntimeError("screened candidate geometry differs from Rust instruction")
            candidate_path.write_text(materialize_candidate(source, instruction), encoding="utf-8")
            board_hash = sha256(candidate_path)
            instrument_context_sha256 = sha256_bytes(
                canonical_bytes(
                    {
                        "schema": "temper-net41-materialization-instrument/v4",
                        "baseline_admission_context_sha256": baseline_admission_context_sha256,
                        "instruction": instruction,
                    }
                )
            )
            checkpoint_path = candidate_dir / "pre-route-checkpoint.json"
            checkpoint = _load_materialization_checkpoint(
                checkpoint_path,
                candidate_id=candidate_id,
                board_sha256=board_hash,
                instrument_context_sha256=instrument_context_sha256,
            )
            if checkpoint is not None:
                evidence = checkpoint["evidence"]
                payload_index = checkpoint["instrument_payload_index"]
                instruction = checkpoint["instruction"]
            else:
                evidence, payloads = inspect_materialized_candidate(
                    candidate_path, instruction, baseline, baseline_drc
                )
                payload_index = _instrument_payload_index(payloads)
                # Persist every completed diagnostic atomically, but the
                # loader above reuses only Rust-conclusive trusted evidence.
                persistence_error = _try_write_materialization_checkpoint(
                    checkpoint_path,
                    {
                        "schema": "temper-net41-materialization-checkpoint/v4",
                        "candidate_id": candidate_id,
                        "scratch_board_sha256": board_hash,
                        "instrument_context_sha256": instrument_context_sha256,
                        "instruction": instruction,
                        "evidence": evidence,
                        "instrument_payload_index": payload_index,
                    },
                )
                if persistence_error:
                    print(
                        f"checkpoint persistence unavailable {candidate_id}: {persistence_error}",
                        flush=True,
                    )
        except Exception as error:
            if not candidate_path.exists():
                candidate_path.write_text(source, encoding="utf-8")
            board_hash = sha256(candidate_path)
            evidence, payloads = unavailable_materialization_evidence(
                candidate_id, board_hash, error
            )
            payload_index = _instrument_payload_index(payloads)
            unavailable_context_sha256 = sha256_bytes(
                canonical_bytes(
                    {
                        "schema": "temper-net41-materialization-instrument/v4",
                        "baseline_admission_context_sha256": baseline_admission_context_sha256,
                        "instruction": instruction,
                    }
                )
            )
            persistence_error = _try_write_materialization_checkpoint(
                candidate_dir / "pre-route-checkpoint.json",
                {
                    "schema": "temper-net41-materialization-checkpoint/v4",
                    "candidate_id": candidate_id,
                    "scratch_board_sha256": board_hash,
                    "instrument_context_sha256": unavailable_context_sha256,
                    "instruction": instruction,
                    "evidence": evidence,
                    "instrument_payload_index": payload_index,
                },
            )
            if persistence_error:
                print(
                    f"checkpoint persistence unavailable {candidate_id}: {persistence_error}",
                    flush=True,
                )
            print(f"materialization unavailable {candidate_id}: {error}", flush=True)
        return candidate_id, candidate_path, evidence, payload_index, instruction

    # Eight concurrent single-threaded KiCad processes are stable on the
    # production host. Twenty exhausted the version/config preflight and
    # converted valid candidates into instrument errors, so keep the default
    # beneath that measured process-pressure boundary.
    worker_count = min(8, os.cpu_count() or 1)
    configured_workers = os.environ.get("TEMPER_NET41_MATERIALIZE_WORKERS")
    if configured_workers is not None:
        worker_count = int(configured_workers)
        if worker_count < 1:
            raise RuntimeError("TEMPER_NET41_MATERIALIZE_WORKERS must be positive")
    print(
        f"materialization workers {worker_count}; ordered survivors {len(survivors)}",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = executor.map(materialize_one, survivors)
        for index, (candidate_id, candidate_path, evidence, payload_index, instruction) in enumerate(
            results, 1
        ):
            if instruction is not None:
                instructions[candidate_id] = instruction
            candidate_paths[candidate_id] = candidate_path
            materialized.append(evidence)
            manifest_rows.append(
                {
                    "candidate_id": candidate_id,
                    "scratch_board": str(candidate_path.relative_to(scratch)),
                    "scratch_board_sha256": sha256(candidate_path),
                    "instrument_payload_index": payload_index,
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
    pre_route_ids = [row["candidate_id"] for row in terminal["materialized"] if row["accepted"]]
    # A non-trusted materialization is terminal: do not route around missing
    # higher-stage evidence. Otherwise route the Rust-returned deterministic
    # prefix, consulting Rust after each attempt so evidence stops at the
    # first admitted route.
    materialization_trusted = all(row["instrument_state"] == "trusted" for row in materialized)
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
                    "instrument_payload_index": _instrument_payload_index(payloads),
                }
            )
            campaign_request["routed"] = routed
            terminal_text = temper_quality_oracle.execute_corridor_campaign_json_py(
                **inputs, campaign_request_json=json.dumps(campaign_request)
            )
            terminal = json.loads(terminal_text)
            if (
                terminal["status"] in {"completed", "instrument-error"}
                or evidence["execution_state"] != "conclusive"
            ):
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
    parser.add_argument(
        "--pre-route-feasibility",
        action="store_true",
        help="run the bounded Rust-owned pre-route feasibility witness protocol",
    )
    args = parser.parse_args()
    if __name__ == "__main__" and not _bootstrap_executable_runtime():
        return EXTENSION_BOOTSTRAP_EXIT_CODE
    if args.pre_route_feasibility:
        checkpoint_path = args.scratch.resolve() / FEASIBILITY_CHECKPOINT_NAME
        receipt_path = FEASIBILITY_EVIDENCE / FEASIBILITY_RECEIPT_NAME
        manifest_path = FEASIBILITY_EVIDENCE / FEASIBILITY_MANIFEST_NAME
        baseline_drc_path = FEASIBILITY_EVIDENCE / "baseline-drc-preflight.json"
        if args.replay:
            try:
                receipt = _validate_feasibility_replay(
                    args.scratch.resolve(),
                    checkpoint_path,
                    receipt_path,
                    manifest_path,
                    baseline_drc_path,
                )
            except (OSError, ValueError, json.JSONDecodeError) as error:
                raise SystemExit(f"feasibility replay invalid: {error}") from error
            receipt_bytes = receipt_path.read_bytes()
            print(
                "REPLAY PASS",
                receipt["terminal"],
                sha256_bytes(receipt_bytes),
            )
            return 0
        manifest, terminal_text, baseline_drc = run_pre_route_feasibility(args.scratch.resolve())
        terminal_bytes = terminal_text.encode()
        manifest["terminal_receipt_sha256"] = sha256_bytes(terminal_bytes)
        FEASIBILITY_EVIDENCE.mkdir(parents=True, exist_ok=True)
        _write_atomic_bytes(FEASIBILITY_EVIDENCE / "baseline-drc-preflight.json", canonical_bytes(baseline_drc))
        _write_atomic_bytes(manifest_path, canonical_bytes(manifest))
        _write_atomic_bytes(receipt_path, terminal_bytes)
        terminal = json.loads(terminal_text)
        print("TERMINAL", terminal["terminal"], terminal["reason"])
        print("MANIFEST", sha256_bytes(canonical_bytes(manifest)))
        return FEASIBILITY_EXIT_CODES[terminal["terminal"]]
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
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    baseline_drc_path.write_bytes(baseline_drc_bytes)
    manifest_path.write_bytes(manifest_bytes)
    terminal_path.write_bytes(terminal_bytes)
    terminal = json.loads(terminal_text)
    print("TERMINAL", terminal["status"], terminal["reason"])
    print("MANIFEST", sha256_bytes(manifest_bytes))
    return 0


# Preserve the long-standing import API for tests and Python callers.  The
# executable path intentionally skips this eager load and goes through the
# freshness-certified bootstrap in ``main`` first.
if __name__ != "__main__":
    _load_runtime_dependencies()


if __name__ == "__main__":
    raise SystemExit(main())
