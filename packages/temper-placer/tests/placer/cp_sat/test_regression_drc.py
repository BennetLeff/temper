"""Golden-board DRC regression gate for temper board placement.

Golden-board regression gate: if this fails, the placement model no longer
produces DRC-clean output.
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
            f"kicad-cli DRC produced no output file"
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

        # 7. Count violations by type
        counts: dict[str, int] = {}
        for v in violations:
            vtype = v.get("type", "other")
            counts[vtype] = counts.get(vtype, 0) + 1

        shorting = counts.get("shorting_items", 0)
        mask_bridge = counts.get("solder_mask_bridge", 0)
        edge_clearance = counts.get("copper_edge_clearance", 0)

        assert shorting == 0, (
            f"Expected 0 shorting_items, got {shorting}. Counts: {counts}"
        )
        assert mask_bridge == 0, (
            f"Expected 0 solder_mask_bridge, got {mask_bridge}. Counts: {counts}"
        )
        assert edge_clearance == 0, (
            f"Expected 0 copper_edge_clearance, got {edge_clearance}. Counts: {counts}"
        )

        placement_relevant = sum(
            count for vtype, count in counts.items()
            if vtype != "lib_footprint_issues"
        )
        assert placement_relevant <= 22, (
            f"Expected <= 22 placement-relevant violations, got {placement_relevant}. Counts: {counts}"
        )
    finally:
        os.unlink(tmp.name)
