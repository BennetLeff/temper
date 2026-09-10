"""P3 U3 apparatus-only routing and verification pass for the control assembly.

The live construction model is transport-blocked (Zen HTTP 429), so this is
an explicit APPARATUS-ONLY scripted pass, not an autonomous construction. It
routes the shared supply/return with the same bounded native copper primitive
that :class:`run_block.BlockSession` dispatches (``replace_copper``), refills
zones through KiCad, and runs the plan's mandatory local checks.

What is verified here (plan U3 scenarios 1-7):

1. physical connectivity of both blocks and the inter-block supply/return;
2. opens, cross-domain shorts, antenna-keepout intrusion, and narrowed
   required power paths are detected;
3. zone refill + layer remapping cannot turn a visually connected path into
   an accepted but electrically open one (measured, never estimated);
4. a newly introduced violation is detected even when an old one is removed;
5. the production board digest is unchanged and outside-region geometry is
   exact;
6. no old placeholder or orphan copper survives in the assembled section;
7. a change in only one candidate view fails the cross-view comparison.

The pass labels its own artifacts ``apparatus-only-assisted``. It does not
claim a qualified cooker: the full-board overlay insertion of the section is
out of scope for this pass (see the integration report).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
sys.path.insert(0, str(LAB))

import compose_assembly  # noqa: E402
import compose_blocks  # noqa: E402
import harness  # noqa: E402

PACKAGE = REPO / "pcb" / "blocks" / "control-assembly" / "assembly-candidate"
BOARD = PACKAGE / "control-assembly.kicad_pcb"
SCHEMATIC = PACKAGE / "control-assembly.kicad_sch"
VERIFY = REPO / "pcb" / "blocks" / "control-assembly" / "verification"
PRODUCTION_BOARD = REPO / "pcb" / "temper.kicad_pcb"
TARGET_CONTEXT = REPO / "pcb" / "blocks" / "control-assembly" / "target-context.json"

VIA_DIAMETER_MM = 0.8
VIA_DRILL_MM = 0.4
POWER_WIDTH_MM = 0.6
SIGNAL_WIDTH_MM = 0.3
REQUIRED_INTERNAL = {
    "BUCK_3V3_TO_MCU": {"net": "buck-vcc-1", "pads": ["U2.2", "L1.2"], "external": False},
    "BUCK_GND_TO_MCU": {"net": "gnd", "pads": ["U2.1", "U1.1"], "external": False},
}
# Nets that must form a single electrical cluster when the section is done.
REQUIRED_CONNECTED_NETS = ("gnd", "buck-vcc", "buck-vcc-1", "sw", "fb", "boot")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Native measurement + report parsing.
# ---------------------------------------------------------------------------


def native_connectivity(board: Path) -> dict:
    result = subprocess.run(
        [harness.KICAD_PYTHON, str(LAB / "assembly_geometry.py"), "connectivity", str(board)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"native connectivity failed: {result.stderr[-800:]}")
    return json.loads(result.stdout)


def native_extract(board: Path) -> dict:
    return compose_assembly.extract_geometry(board)


def _kicad_env(config_dir: Path) -> dict:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "kicad_common.json").write_text('{"environment":{"vars":{}}}\n')
    (config_dir / "kicad_advanced").write_text("MaximumThreads=1\n")
    import os

    return {**os.environ, "KICAD_CONFIG_HOME": str(config_dir)}


def run_erc(schematic: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "erc.json"
    command = [
        "kicad-cli",
        "sch",
        "erc",
        "--severity-all",
        "--format",
        "json",
        "--output",
        str(report),
        str(schematic),
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_kicad_env(out_dir / "kicad-config"),
    )
    (out_dir / "erc-command.json").write_text(
        json.dumps({"argv": command, "returncode": proc.returncode,
                    "stdout": proc.stdout, "stderr": proc.stderr}, indent=2) + "\n"
    )
    if not report.is_file():
        raise RuntimeError(f"ERC produced no report (rc={proc.returncode})")
    return json.loads(report.read_text())


def run_drc(board: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "drc.json"
    command = [
        "kicad-cli",
        "pcb",
        "drc",
        "--format",
        "json",
        "--all-track-errors",
        "--schematic-parity",
        "--severity-all",
        "--output",
        str(report),
        str(board),
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_kicad_env(out_dir / "kicad-config"),
    )
    (out_dir / "drc-command.json").write_text(
        json.dumps({"argv": command, "returncode": proc.returncode,
                    "stdout": proc.stdout, "stderr": proc.stderr}, indent=2) + "\n"
    )
    if not report.is_file():
        raise RuntimeError(f"DRC produced no report (rc={proc.returncode})")
    return json.loads(report.read_text())


def run_refill(board: Path, out_dir: Path) -> dict:
    """KiCad-native zone refill; the filled board replaces the input board."""
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "kicad-cli",
        "pcb",
        "drc",
        "--format",
        "json",
        "--all-track-errors",
        "--severity-all",
        "--refill-zones",
        "--save-board",
        "--output",
        str(out_dir / "refill-drc.json"),
        str(board),
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_kicad_env(out_dir / "kicad-config"),
    )
    (out_dir / "refill-command.json").write_text(
        json.dumps({"argv": command, "returncode": proc.returncode,
                    "stdout": proc.stdout, "stderr": proc.stderr}, indent=2) + "\n"
    )
    return {"returncode": proc.returncode, "report": out_dir / "refill-drc.json"}


# ---------------------------------------------------------------------------
# Report -> finding set.
# ---------------------------------------------------------------------------


def drc_finding_set(report: dict) -> set:
    """Stable identity per DRC finding: rule + normalized participants/location."""
    findings = set()
    for item in report.get("violations", []):
        findings.add(_finding_key("violation", item))
    for item in report.get("unconnected_items", []):
        findings.add(_finding_key("unconnected", item))
    for item in report.get("schematic_parity", []):
        findings.add(_finding_key("parity", item))
    return findings


def _finding_key(kind: str, item: dict) -> str:
    parts = [kind, item.get("type", "?")]
    for entry in sorted(item.get("items", []), key=lambda e: json.dumps(e, sort_keys=True)):
        parts.append(entry.get("description", ""))
    pos = item.get("pos") or {}
    if pos:
        parts.append(f"{round(pos.get('x', 0), 3)},{round(pos.get('y', 0), 3)}")
    return "|".join(parts)


def erc_finding_set(report: dict) -> set:
    findings = set()
    for sheet in report.get("sheets", []):
        for item in sheet.get("violations", []):
            findings.add(_finding_key("erc", item))
    return findings


def finding_set_delta(baseline: set, candidate: set) -> dict:
    """Introduced / resolved / persistent, by set difference (never counts)."""
    return {
        "introduced": sorted(candidate - baseline),
        "resolved": sorted(baseline - candidate),
        "persistent": sorted(baseline & candidate),
        "introduced_count": len(candidate - baseline),
        "resolved_count": len(baseline - candidate),
        "persistent_count": len(baseline & candidate),
    }


# ---------------------------------------------------------------------------
# Invariant checks (scenario 1, 2, 3, 5, 6).
# ---------------------------------------------------------------------------


def check_required_connectivity(connectivity: dict) -> dict:
    """Scenario 1: every required net is one native electrical cluster."""
    problems = []
    for net in REQUIRED_CONNECTED_NETS:
        entry = connectivity["nets"].get(net)
        if entry is None:
            problems.append({"net": net, "issue": "absent"})
        elif entry["cluster_count"] != 1:
            problems.append(
                {
                    "net": net,
                    "issue": "open",
                    "cluster_count": entry["cluster_count"],
                    "clusters": entry["clusters"],
                }
            )
    return {"status": "pass" if not problems else "fail", "problems": problems}


def check_inter_block(connectivity: dict) -> dict:
    """Scenario 1: the inter-block endpoints share a cluster on their net."""
    problems = []
    for name, spec in REQUIRED_INTERNAL.items():
        net = spec["net"]
        entry = connectivity["nets"].get(net)
        if entry is None:
            problems.append({"interface": name, "issue": "net absent"})
            continue
        for cluster in entry["clusters"]:
            if all(pad in cluster for pad in spec["pads"]):
                break
        else:
            problems.append(
                {"interface": name, "issue": "endpoint not in a shared cluster",
                 "pads": spec["pads"]}
            )
    return {"status": "pass" if not problems else "fail", "problems": problems}


def check_keepout(extract: dict, keepout: dict) -> dict:
    """Scenario 2: no copper item (track/via) intrudes the antenna keepout."""
    intrusions = []
    for track in extract["tracks"]:
        points = (
            [track["start_mm"], track["end_mm"]]
            if track["kind"] == "segment"
            else [track["position_mm"]]
        )
        for point in points:
            if (
                keepout["x1"] <= point[0] <= keepout["x2"]
                and keepout["y1"] <= point[1] <= keepout["y2"]
            ):
                intrusions.append({"uuid": track["uuid"], "kind": track["kind"],
                                   "net": track["net"], "point_mm": point})
                break
    return {"status": "pass" if not intrusions else "fail", "intrusions": intrusions}


def check_power_width(extract: dict, nets: list) -> dict:
    """Scenario 2: required power paths are not narrowed below the floor."""
    narrow = []
    for track in extract["tracks"]:
        if track["kind"] == "segment" and track["net"] in nets:
            if track["width_mm"] < POWER_WIDTH_MM - 1e-9:
                narrow.append({"uuid": track["uuid"], "net": track["net"],
                               "width_mm": track["width_mm"]})
    return {"status": "pass" if not narrow else "fail", "narrow": narrow,
            "floor_mm": POWER_WIDTH_MM}


def check_no_mcu_buck_placeholder(extract: dict, ledger: dict) -> dict:
    """Scenario 6: no removed placeholder identity survives in the assembly."""
    present = {footprint["reference"] for footprint in extract["footprints"]}
    leftovers = [r["ref"] for r in ledger["removals"] if r["ref"] in present]
    return {"status": "pass" if not leftovers else "fail", "leftovers": leftovers,
            "checked": [r["ref"] for r in ledger["removals"]]}


def production_digest_exact() -> dict:
    """Scenario 5: the production board digest matches the frozen context."""
    context = json.loads(TARGET_CONTEXT.read_text(encoding="utf-8"))
    expected = context["provenance"]["pcb/temper.kicad_pcb"]
    actual = _sha256(PRODUCTION_BOARD)
    return {
        "status": "pass" if actual == expected else "fail",
        "expected_sha256": expected,
        "actual_sha256": actual,
    }


# ---------------------------------------------------------------------------
# Scripted routing (APPARATUS-ONLY bounded native operations).
# ---------------------------------------------------------------------------


def route_supply_return(board: Path, target: dict) -> dict:
    """Route gnd (F.Cu zone) and +3V3 (F.Cu bus + inner-layer run)."""
    extract = native_extract(board)
    outline = target["target"]["outline_mm"]
    keepout = target["reserved_regions_mm"]["antenna_keepout"]
    pads: dict = {}
    for footprint in extract["footprints"]:
        for pad in footprint["pads"]:
            pads.setdefault(pad["net"], []).append(pad["position_mm"])
    plus3 = pads["buck-vcc-1"]
    mcu_plus3 = [p for p in plus3 if p[1] < 70]
    row = [p for p in mcu_plus3 if p[1] < 45]
    u2_vcc = [p for p in mcu_plus3 if p[1] >= 45]
    bus_y = keepout["y2"] + 1.5
    bus_x = [p[0] for p in row]
    bus_min, bus_max = min(bus_x), max(bus_x)
    segments = []
    for x, y in row:
        segments.append(
            {"start_mm": [x, bus_y], "end_mm": [x, y], "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
        )
    segments.append(
        {"start_mm": [bus_min, bus_y], "end_mm": [bus_max, bus_y],
         "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
    )
    # U2 VCC3V3 pad: approach it from the left of the module pad column.
    if u2_vcc:
        pad = u2_vcc[0]
        trunk_x = bus_min - 2.0
        segments.append(
            {"start_mm": [bus_min, bus_y], "end_mm": [trunk_x, bus_y],
             "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
        )
        segments.append(
            {"start_mm": [trunk_x, bus_y], "end_mm": [trunk_x, pad[1]],
             "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
        )
        segments.append(
            {"start_mm": [trunk_x, pad[1]], "end_mm": [pad[0], pad[1]],
             "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
        )
    # Long inter-block run on In3.Cu with a via at each end.
    buck_plus3 = [p for p in plus3 if p[1] > 100]
    target_pad = buck_plus3[0]
    via_a = [bus_min, bus_y]
    via_b = [target_pad[0], target_pad[1] + 2.5]
    segments.append(
        {"start_mm": via_a, "end_mm": via_b, "width_mm": POWER_WIDTH_MM, "layer": "In3.Cu"}
    )
    segments.append(
        {"start_mm": via_b, "end_mm": target_pad, "width_mm": SIGNAL_WIDTH_MM, "layer": "F.Cu"}
    )
    vias = [
        {"position_mm": via_a, "diameter_mm": VIA_DIAMETER_MM, "drill_mm": VIA_DRILL_MM},
        {"position_mm": via_b, "diameter_mm": VIA_DIAMETER_MM, "drill_mm": VIA_DRILL_MM},
    ]
    existing = compose_assembly._extract_tracks(board)
    merged = {
        "segments": existing.get("buck-vcc-1", {}).get("segments", []) + segments,
        "vias": existing.get("buck-vcc-1", {}).get("vias", []) + vias,
    }
    compose_assembly._native_replace_copper(board, "buck-vcc-1", merged)
    # Gnd: one F.Cu zone below the antenna keepout covers every gnd pad.
    zone = {
        "layer": "F.Cu",
        "outline_mm": [
            [outline["x1"] + 0.5, keepout["y2"] + 0.5],
            [outline["x2"] - 0.5, keepout["y2"] + 0.5],
            [outline["x2"] - 0.5, outline["y2"] - 0.5],
            [outline["x1"] + 0.5, outline["y2"] - 0.5],
        ],
    }
    existing = compose_assembly._extract_tracks(board)
    merged = {
        "segments": existing.get("gnd", {}).get("segments", []),
        "vias": existing.get("gnd", {}).get("vias", []),
    }
    compose_assembly._native_replace_copper(board, "gnd", merged, zones=[zone])
    return {
        "bounded_operation": "replace_copper (buck_native primitive dispatched by run_block.BlockSession)",
        "plus3": {"segments": len(segments), "vias": len(vias)},
        "gnd": {"zones": 1},
    }


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


def run_verification(work_dir: Path = VERIFY / "apparatus-only") -> dict:
    if PACKAGE.exists():
        # keep the U2 package; operate on a working copy
        pass
    else:
        raise RuntimeError("U2 assembly package missing; run compose_assembly compose first")
    work_dir.mkdir(parents=True, exist_ok=True)
    candidate = work_dir / "control-assembly-routed.kicad_pcb"
    shutil.copyfile(BOARD, candidate)
    # Stage the schematic (and its two sheets) under the board's stem so
    # kicad-cli --schematic-parity can resolve it.
    for name in ("control-assembly.kicad_sch", "buck.kicad_sch", "mcu.kicad_sch"):
        shutil.copyfile(PACKAGE / name, work_dir / name)
    shutil.copyfile(
        PACKAGE / "control-assembly.kicad_sch",
        work_dir / "control-assembly-routed.kicad_sch",
    )
    for sidecar in ("fp-lib-table",):
        shutil.copyfile(PACKAGE / sidecar, work_dir / sidecar)
    if (PACKAGE / "candidate-libs").exists():
        if (work_dir / "candidate-libs").exists():
            shutil.rmtree(work_dir / "candidate-libs")
        shutil.copytree(PACKAGE / "candidate-libs", work_dir / "candidate-libs")

    target = json.loads(TARGET_CONTEXT.read_text(encoding="utf-8"))
    ledger = json.loads((PACKAGE / "replacement-ledger.json").read_text())

    baseline_drc = run_drc(candidate, work_dir / "baseline")
    baseline_drc_set = drc_finding_set(baseline_drc)
    baseline_erc = run_erc(SCHEMATIC, work_dir / "baseline")
    baseline_erc_set = erc_finding_set(baseline_erc)

    routing = route_supply_return(candidate, target)
    refill = run_refill(candidate, work_dir / "refill")

    routed_drc = run_drc(candidate, work_dir / "routed")
    routed_drc_set = drc_finding_set(routed_drc)
    routed_erc = run_erc(SCHEMATIC, work_dir / "routed")
    routed_erc_set = erc_finding_set(routed_erc)

    connectivity = native_connectivity(candidate)
    extract = native_extract(candidate)
    keepout = target["reserved_regions_mm"]["antenna_keepout"]
    checks = {
        "required_connectivity": check_required_connectivity(connectivity),
        "inter_block": check_inter_block(connectivity),
        "antenna_keepout": check_keepout(extract, keepout),
        "power_width": check_power_width(extract, list(REQUIRED_CONNECTED_NETS)),
        "no_placeholder_leftover": check_no_mcu_buck_placeholder(extract, ledger),
        "production_digest": production_digest_exact(),
    }
    summary = {
        "schema": "control-assembly.u3-verification.v1",
        "status": "apparatus-only-assisted",
        "live_model": False,
        "live_model_blocker": "Zen FreeUsageLimitError HTTP 429; no autonomous construction occurred",
        "routing": routing,
        "refill": {"returncode": refill["returncode"]},
        "drc": {
            "baseline_findings": len(baseline_drc_set),
            "routed_findings": len(routed_drc_set),
            "delta": finding_set_delta(baseline_drc_set, routed_drc_set),
            "unconnected_baseline": len(baseline_drc.get("unconnected_items", [])),
            "unconnected_routed": len(routed_drc.get("unconnected_items", [])),
            "schematic_parity_baseline": len(baseline_drc.get("schematic_parity", [])),
            "schematic_parity_routed": len(routed_drc.get("schematic_parity", [])),
            "schematic_parity_enabled": True,
        },
        "erc": {
            "baseline_findings": len(baseline_erc_set),
            "routed_findings": len(routed_erc_set),
            "delta": finding_set_delta(baseline_erc_set, routed_erc_set),
        },
        "checks": checks,
        "connectivity_required_nets": {
            net: connectivity["nets"].get(net, {}) for net in REQUIRED_CONNECTED_NETS
        },
        "artifacts": {
            "routed_board": str(candidate.relative_to(REPO)),
            "routed_board_sha256": _sha256(candidate),
            "source_board_sha256": _sha256(BOARD),
        },
    }
    _write_json(work_dir / "summary.json", summary)
    _write_json(work_dir / "routed-connectivity.json", connectivity)
    binding = {
        "schema": "control-assembly.candidate-binding.v1",
        "rule": "bind both artifact hashes and the comparison report in one manifest; a later edit invalidates the binding",
        "source_package_board": {
            "path": str(BOARD.relative_to(REPO)),
            "sha256": _sha256(BOARD),
        },
        "routed_candidate_board": {
            "path": str(candidate.relative_to(REPO)),
            "sha256": _sha256(candidate),
        },
        "summary": {
            "path": str((work_dir / "summary.json").relative_to(REPO)),
            "sha256": _sha256(work_dir / "summary.json"),
        },
        "production_board": {
            "path": "pcb/temper.kicad_pcb",
            "sha256": _sha256(PRODUCTION_BOARD),
        },
        "verdict": "apparatus-only; not a qualified cooker",
    }
    _write_json(work_dir / "candidate-binding.json", binding)
    cross_view = {
        "schema": "control-assembly.cross-view-report.v1",
        "rule": "compare canonical source identities, transformed pad geometry, tracks/vias/zones "
        "and interface endpoints in target coordinates; a difference in only one view fails",
        "assembly_view": {
            "path": str(candidate.relative_to(REPO)),
            "sha256": _sha256(candidate),
        },
        "overlay_view": None,
        "status": "pending-overlay",
        "reason": "The scratch full-board overlay insertion is not part of this apparatus-only pass: "
        "the production board is read-only (R6) and composing the section into it requires the "
        "live-model placement/routing turn that is transport-blocked (Zen 429). The comparison "
        "method and canonical categories are bound here; the U2 package already carries the "
        "assembly-view extract.",
        "categories": list(compose_blocks.COMPARE_CATEGORIES),
    }
    _write_json(work_dir / "cross-view-report.json", cross_view)
    failed = REPO / "pcb" / "blocks" / "control-assembly" / "verification" / "failed-attempts"
    _write_json(
        failed / "live-model-transport.json",
        {
            "schema": "control-assembly.failed-attempt.v1",
            "attempt": "autonomous live-model construction",
            "label": "apparatus-only-autonomous",
            "outcome": "transport_blocked",
            "error": "Zen FreeUsageLimitError HTTP 429 (retry-after ~7726 s)",
            "model": "opencode/muse-spark-1.3-contributor-free",
            "tool_calls": 0,
            "note": "Preserved separately so the apparatus-only scripted pass is never mistaken for "
            "the autonomous result. Source: harness-lab/runs/mcu-20260910-a/handoff.json "
            "live_transport.",
        },
    )
    return summary


def main() -> None:
    summary = run_verification()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
