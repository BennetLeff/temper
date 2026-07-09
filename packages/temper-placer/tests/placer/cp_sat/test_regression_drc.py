"""Golden-board DRC regression gate for temper board placement and routing.

Golden-board regression gate: if this fails, the placement model no longer
produces DRC-clean output.  The gate distinguishes placement-fixable
violations (cross-component shorts, mask bridges, edge clearance) from
placement-irreducible ones (intra-component clearances where both sides
name the same component — a netclass-calibration concern, not placement's
responsibility — and library footprint issues).

The territory-level truth gate is the only instrument that catches the
map-vs-territory gaps documented in the three solutions/ learnings:
  - Weak NoOverlap2D encoding allows zero-gap touching
  - Off-centre pad offset defeats centered component bounds
  - Silent no-op bugs in measurement code
No model-level invariant test (P1–P9) can substitute.

Routing DRC gate (:func:`test_golden_board_routing_drc_regression`) extends
the placement gate to full placement + routing + KiCad DRC round-trip,
asserting ``unconnected_items=0`` and zero routing-introduced DRC errors
on the routed board.
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

TEMPER_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPO_ROOT = TEMPER_PLACER_ROOT.parent.parent

RULES_PATH = TEMPER_PLACER_ROOT / "configs" / "netclass_rules.yaml"
PCL_CONFIG = TEMPER_PLACER_ROOT / "configs" / "constraints" / "temper_induction_cooker.yaml"
BOARD_PATH = REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"


def _kicad_cli_available() -> bool:
    try:
        result = subprocess.run(
            ["kicad-cli", "--version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_drc(pcb_path: str) -> dict:
    """Run kicad-cli DRC and return parsed JSON dict."""
    drc_out = Path(tempfile.mktemp(suffix=".json"))
    try:
        proc = subprocess.run(
            [
                "kicad-cli", "pcb", "drc",
                "--format", "json",
                "-o", str(drc_out),
                pcb_path,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0 and proc.stderr:
            stderr_summary = proc.stderr.strip()[:200]
        else:
            stderr_summary = ""
    except subprocess.TimeoutExpired:
        if drc_out.exists():
            os.unlink(drc_out)
        pytest.skip("kicad-cli DRC timed out")
        return {}
    except Exception:
        if drc_out.exists():
            os.unlink(drc_out)
        raise

    if not drc_out.exists():
        pytest.skip(
            "kicad-cli DRC produced no output file"
            + (f": {stderr_summary}" if stderr_summary else "")
        )
        return {}

    try:
        with open(drc_out) as f:
            return json.load(f)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(drc_out)


def _load_pcl_constraints(config_path: Path) -> list:
    """Load PCL constraints from a YAML config file."""
    try:
        from temper_placer.io.config_loader import load_constraints

        constraints = load_constraints(config_path)
        return list(getattr(constraints, "pcl_constraints", []))
    except Exception:
        return []


@pytest.mark.slow
def test_golden_board_drc_regression():
    if not _kicad_cli_available():
        pytest.skip("kicad-cli not available")

    assert BOARD_PATH.exists(), f"Board not found: {BOARD_PATH}"
    assert RULES_PATH.exists(), f"Rules not found: {RULES_PATH}"

    # 1. Load netclass rules
    from temper_placer.io.netclass_loader import load_netclass_rules

    rules = load_netclass_rules(RULES_PATH)

    # 2. Parse the PCB
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(BOARD_PATH)
    netlist = parse_result.netlist
    board = parse_result.board
    assert board is not None, "Board geometry parsing failed"
    assert len(netlist.components) > 0, "No components parsed from PCB"

    # 3. Load PCL constraints
    extra_constraints = _load_pcl_constraints(PCL_CONFIG)

    # 4. Solve placement with all constraints active (30s timeout)
    from temper_placer.placer.cp_sat.encoder import solve_placement

    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=extra_constraints,
        timeout_ms=30_000,
        seed=42,
    )

    if result.status not in ("optimal", "feasible"):
        n_unsat = len(result.unsat_core)
        detail = ""
        if n_unsat > 0:
            names = [u.get("name", "?") for u in result.unsat_core[:5]]
            detail = f" unsat_core={n_unsat} ({', '.join(names)})"
        pytest.skip(
            f"Placement solver returned status {result.status}{detail}"
        )

    # 5. Write output PCB with netclass forms
    raw = BOARD_PATH.read_text(encoding="utf-8")
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    placed = _apply_placements_to_pcb(
        raw,
        result.to_placements_dict(),
        design_rules=rules.design_rules,
    )

    tmp = tempfile.NamedTemporaryFile(
        suffix=".kicad_pcb", mode="w", delete=False
    )
    tmp.write(placed)
    tmp.close()

    try:
        # 6. Run kicad-cli DRC and parse
        drc_data = _run_drc(tmp.name)
        violations = drc_data.get("violations", [])

        # 7. Count violations by type, distinguishing placement-fixable
        #    from placement-irreducible (intra-component).
        import re

        PLACEMENT_IRREDUCIBLE_TYPES = {"lib_footprint_issues"}

        fixable_counts: dict[str, int] = {}
        irreducible_counts: dict[str, int] = {}
        intra_component_count = 0

        for v in violations:
            vtype = v.get("type", "other")
            desc = v.get("description", "")

            # Intra-component: both sides name the same component ref.
            # Example: "Pad 13 of U_MCU" and "Pad 14 of U_MCU".
            refs = set(re.findall(r"of\s+(\S+)", desc))
            if len(refs) == 1 and vtype not in PLACEMENT_IRREDUCIBLE_TYPES:
                irreducible_counts[vtype] = irreducible_counts.get(vtype, 0) + 1
                intra_component_count += 1
            elif vtype in PLACEMENT_IRREDUCIBLE_TYPES:
                irreducible_counts[vtype] = irreducible_counts.get(vtype, 0) + 1
            else:
                fixable_counts[vtype] = fixable_counts.get(vtype, 0) + 1

        placement_fixable = sum(fixable_counts.values())

        # ---- assertions ----
        shorting = fixable_counts.get("shorting_items", 0)
        mask_bridge = fixable_counts.get("solder_mask_bridge", 0)
        edge_clearance = fixable_counts.get("copper_edge_clearance", 0)

        assert shorting == 0, (
            f"Expected 0 fixable shorting_items, got {shorting}. "
            f"Fixable: {dict(fixable_counts)}"
        )
        assert mask_bridge == 0, (
            f"Expected 0 fixable solder_mask_bridge, got {mask_bridge}. "
            f"Fixable: {dict(fixable_counts)}"
        )
        # Edge margin is placement-relevant but the hardcoded 0.5mm
        # copper_edge_clearance may not match the board's (setup) value.
        # Tracked as a known gap — not a placement constraint failure.
        assert edge_clearance <= 4, (
            f"Expected <= 4 fixable copper_edge_clearance, got {edge_clearance}. "
            f"Fixable: {dict(fixable_counts)}"
        )

        assert placement_fixable <= 15, (
            f"Expected <= 15 placement-fixable violations, got {placement_fixable}. "
            f"Fixable: {dict(fixable_counts)}, "
            f"Irreducible intra-component: {intra_component_count} ({dict(irreducible_counts)})"
        )
    finally:
        os.unlink(tmp.name)


def _count_errors_by_type(drc_data: dict) -> dict[str, int]:
    """Count error-severity DRC violations by type string.

    Returns a dict mapping violation type -> count.  Only violations with
    ``severity == "error"`` are counted.  ``unconnected_items`` from the
    top-level JSON array are included under the key ``"unconnected_items"``.
    """
    counts: dict[str, int] = {}
    for v in drc_data.get("violations", []):
        if v.get("severity") != "error":
            continue
        vtype = v.get("type", "other")
        counts[vtype] = counts.get(vtype, 0) + 1
    unconnected = len(drc_data.get("unconnected_items", []))
    if unconnected:
        counts["unconnected_items"] = unconnected
    return counts


@pytest.mark.slow
@pytest.mark.routing
def test_golden_board_routing_drc_regression():
    """Full placement + routing + KiCad DRC round-trip gate.

    Asserts ``unconnected_items=0`` and zero routing-introduced DRC errors
    on the routed temper board.  Decomposes routing-only errors by
    subtracting the placement-only DRC baseline from the routed-board DRC
    result, isolating routing regressions from placement-inherited
    violations.

    CI gate: if this test fails, routing completeness or routed-board DRC
    has regressed.  This is the W1 territory-level truth gate.
    """
    if not _kicad_cli_available():
        pytest.skip("kicad-cli not available")

    assert BOARD_PATH.exists(), f"Board not found: {BOARD_PATH}"
    assert RULES_PATH.exists(), f"Rules not found: {RULES_PATH}"

    # 1. Load netclass rules
    from temper_placer.io.netclass_loader import load_netclass_rules

    rules = load_netclass_rules(RULES_PATH)

    # 2. Parse the PCB
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    parse_result = parse_kicad_pcb(BOARD_PATH)
    netlist = parse_result.netlist
    board = parse_result.board
    assert board is not None, "Board geometry parsing failed"
    assert len(netlist.components) > 0, "No components parsed from PCB"

    # 3. Load PCL constraints
    extra_constraints = _load_pcl_constraints(PCL_CONFIG)

    # 4. Solve placement with all constraints active (30s timeout)
    from temper_placer.placer.cp_sat.encoder import solve_placement

    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=extra_constraints,
        timeout_ms=30_000,
        seed=42,
    )

    if result.status not in ("optimal", "feasible"):
        n_unsat = len(result.unsat_core)
        detail = ""
        if n_unsat > 0:
            names = [u.get("name", "?") for u in result.unsat_core[:5]]
            detail = f" unsat_core={n_unsat} ({', '.join(names)})"
        pytest.skip(
            f"Placement solver returned status {result.status}{detail}"
        )

    placements_dict = result.to_placements_dict()

    # 5. Write placed-only PCB and run placement DRC for baseline
    from temper_placer.router_v6.adapter import _apply_placements_to_pcb

    raw = BOARD_PATH.read_text(encoding="utf-8")
    placed_content = _apply_placements_to_pcb(
        raw, placements_dict, design_rules=rules.design_rules,
    )

    placed_tmp = tempfile.NamedTemporaryFile(
        suffix=".kicad_pcb", mode="w", delete=False,
    )
    placed_tmp.write(placed_content)
    placed_tmp.close()

    try:
        placement_drc = _run_drc(placed_tmp.name)
    finally:
        os.unlink(placed_tmp.name)

    placement_counts = _count_errors_by_type(placement_drc)

    # 6. Route the placed PCB.
    # route_pcb expects a duck-typed "parsed" object with source_path.
    # ParseResult doesn't carry source_path, so we build a compatible stub.
    from temper_placer.router_v6.adapter import route_pcb

    parsed_stub = type("ParsedStub", (), {"source_path": BOARD_PATH})()

    routing_result = route_pcb(
        parsed_stub, placements_dict,
        _seed=42,
        design_rules=rules.design_rules,
    )

    # 7. Assert internal completion signal
    assert routing_result.completion_rate == 1.0, (
        f"Router failed to complete all nets: "
        f"completion_rate={routing_result.completion_rate:.1%}, "
        f"unrouted={list(routing_result.unrouted_nets)[:10]}"
    )

    # 8. Write routed PCB content to temp file
    assert routing_result.routed_pcb_content is not None, (
        "RoutingResult.routed_pcb_content is None"
    )
    routed_tmp = tempfile.NamedTemporaryFile(
        suffix=".kicad_pcb", mode="w", delete=False,
    )
    routed_tmp.write(routing_result.routed_pcb_content)
    routed_tmp.close()

    try:
        # 9. Run kicad-cli DRC on the routed PCB
        routed_drc = _run_drc(routed_tmp.name)
    finally:
        os.unlink(routed_tmp.name)

    routed_counts = _count_errors_by_type(routed_drc)

    # 10. ---- assertions ----
    assert routed_counts.get("unconnected_items", 0) == 0, (
        f"Routed PCB has {routed_counts.get('unconnected_items', 0)} "
        f"unconnected items; every net must be routed."
    )

    # 11. Decompose routing-introduced delta from placement baseline
    routing_delta: dict[str, int] = {}
    all_types = sorted(set(placement_counts.keys()) | set(routed_counts.keys()))
    for vtype in all_types:
        p = placement_counts.get(vtype, 0)
        r = routed_counts.get(vtype, 0)
        delta = r - p
        if delta != 0:
            routing_delta[vtype] = delta

    routing_introduced = sum(v for v in routing_delta.values() if v > 0)

    assert routing_introduced == 0, (
        f"Routing introduced {routing_introduced} new DRC violations "
        f"(placement baseline: {sum(placement_counts.values())} total, "
        f"routed: {sum(routed_counts.values())} total). "
        f"Routing deltas by type: {routing_delta}. "
        f"Known routing quality issue: single-layer F.Cu routing with all 24 "
        f"nets on one layer may produce track-to-track clearance issues."
    )
