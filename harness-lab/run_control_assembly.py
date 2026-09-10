"""P3 U3 apparatus-only routing and verification pass for the control assembly.

The live construction model is transport-blocked (Zen HTTP 429), so this is
an explicit APPARATUS-ONLY scripted pass, not an autonomous construction. It
routes the shared supply/return through :class:`run_block.BlockSession`
itself -- the same bounded, budgeted, atomically-staged native ``replace_copper``
operation, not a parallel bypass -- refills zones through KiCad, and runs the
plan's mandatory local checks.

What is verified here (plan U3 scenarios 1-7):

1. physical connectivity of both blocks and the inter-block supply/return;
2. opens, cross-domain shorts, antenna-keepout intrusion, and narrowed
   required power paths are detected;
3. zone refill + layer remapping cannot turn a visually connected path into
   an accepted but electrically open one (measured, never estimated);
4. a newly introduced violation is detected even when an old one is removed;
5. the production board digest is unchanged and outside-region geometry is
   exact (now including a scratch full-board overlay);
6. no old placeholder or orphan copper survives in the assembled section;
7. a change in only one candidate view fails the cross-view comparison
   (assembly view vs scratch overlay view).

The pass labels its own artifacts ``apparatus-only-assisted``. It does not
claim a qualified cooker. The scratch overlay is a *scratch copy* of the
production board (R6): the production board is never written, and the overlay
itself is an instrument that reports the section's integration debt rather
than suppressing it (see the integration report).
"""

from __future__ import annotations

import hashlib
import json
import re
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
import run_block  # noqa: E402

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


DRC_SAMPLES = 3


def drc_stable_set(board: Path, out_dir: Path, samples: int = DRC_SAMPLES) -> tuple:
    """Repeat kicad-cli DRC and intersect the finding sets.

    kicad-cli is nondeterministic run-to-run (measured here: ~64 of 660
    findings on a byte-identical board vary, almost all ``unconnected_items``
    item pairings). A single-run set difference manufactures phantom
    introduced/resolved findings, so the compared set is the intersection
    across ``samples`` runs and the observed run counts + union are retained.
    """
    runs = []
    for index in range(samples):
        report = run_drc(board, out_dir / f"run-{index}")
        runs.append(drc_finding_set(report))
    stable = set.intersection(*runs) if runs else set()
    union = set.union(*runs) if runs else set()
    return stable, {
        "samples": samples,
        "per_run_counts": [len(run) for run in runs],
        "intersection": len(stable),
        "union": len(union),
        "unstable": len(union) - len(stable),
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


def check_power_width(
    extract: dict, power_nets: list, signal_nets: tuple = ()
) -> dict:
    """Scenario 2: required paths are not narrowed below their applicable floor.

    Power nets (the +15V feed, +3V3 output and shared return) carry the 0.6 mm
    floor; switching/feedback/bootstrap nets carry the 0.3 mm signal floor.
    ``power_nets`` alone is the original MCU-era call shape (floor 0.6), so the
    existing callers keep their meaning.

    Sub-0.6 copper on a *signal* net is recorded separately as
    ``inherited_below_power_floor`` rather than silently absorbed: it is
    inherited prototype geometry that meets the signal floor but not the power
    one, and it must stay visible in the apparatus evidence (KTD5/R7).
    """
    narrow = []
    inherited = []
    for track in extract["tracks"]:
        if track["kind"] != "segment":
            continue
        net = track["net"]
        if net in power_nets:
            if track["width_mm"] < POWER_WIDTH_MM - 1e-9:
                narrow.append({"uuid": track["uuid"], "net": net,
                               "width_mm": track["width_mm"],
                               "floor_mm": POWER_WIDTH_MM})
        elif net in signal_nets:
            if track["width_mm"] < SIGNAL_WIDTH_MM - 1e-9:
                narrow.append({"uuid": track["uuid"], "net": net,
                               "width_mm": track["width_mm"],
                               "floor_mm": SIGNAL_WIDTH_MM})
            elif track["width_mm"] < POWER_WIDTH_MM - 1e-9:
                inherited.append({"uuid": track["uuid"], "net": net,
                                  "width_mm": track["width_mm"],
                                  "signal_floor_mm": SIGNAL_WIDTH_MM,
                                  "power_floor_mm": POWER_WIDTH_MM,
                                  "note": "inherited prototype copper; meets the signal "
                                          "floor, below the power floor; signal net by "
                                          "function"})
    return {
        "status": "pass" if not narrow else "fail",
        "narrow": narrow,
        "floor_mm": POWER_WIDTH_MM,
        "signal_floor_mm": SIGNAL_WIDTH_MM,
        "power_nets": sorted(power_nets),
        "signal_nets": sorted(signal_nets),
        "inherited_below_power_floor": inherited,
    }


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


def route_supply_return(session, target: dict) -> dict:
    """Route gnd (F.Cu zone) and +3V3 (F.Cu bus + inner-layer run).

    Every mutation goes through ``run_block.BlockSession`` (the shared bounded
    native operation, budget, atomic staging, protected-context and Rust check
    path) -- there is no direct ``_native_replace_copper`` bypass. The routed
    +3V3 net is a required *power* path, so every segment -- newly routed and
    inherited prototype copper alike -- is widened to the 0.6 mm floor.
    """
    board = session.board
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
            {"start_mm": [x, bus_y], "end_mm": [x, y], "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
        )
    segments.append(
        {"start_mm": [bus_min, bus_y], "end_mm": [bus_max, bus_y],
         "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
    )
    # U2 VCC3V3 pad: approach it from the left of the module pad column.
    if u2_vcc:
        pad = u2_vcc[0]
        trunk_x = bus_min - 2.0
        segments.append(
            {"start_mm": [bus_min, bus_y], "end_mm": [trunk_x, bus_y],
             "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
        )
        segments.append(
            {"start_mm": [trunk_x, bus_y], "end_mm": [trunk_x, pad[1]],
             "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
        )
        segments.append(
            {"start_mm": [trunk_x, pad[1]], "end_mm": [pad[0], pad[1]],
             "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
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
        {"start_mm": via_b, "end_mm": target_pad, "width_mm": POWER_WIDTH_MM, "layer": "F.Cu"}
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
    # Inherited prototype +3V3 copper is a required power path too: raise every
    # retained segment to the assembly power floor so the whole net meets 0.6mm.
    for segment in merged["segments"]:
        segment["width_mm"] = max(float(segment["width_mm"]), POWER_WIDTH_MM)
    plus3_result = session.call(
        "replace_copper",
        {"net": "buck-vcc-1", "segments": merged["segments"],
         "vias": merged["vias"], "zones": []},
    )
    if not plus3_result.get("mutation_committed"):
        raise RuntimeError(f"BlockSession refused the +3V3 route: {plus3_result}")
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
    gnd_result = session.call(
        "replace_copper",
        {"net": "gnd", "segments": merged["segments"],
         "vias": merged["vias"], "zones": [zone]},
    )
    if not gnd_result.get("mutation_committed"):
        raise RuntimeError(f"BlockSession refused the gnd route: {gnd_result}")
    return {
        "bounded_operation": "replace_copper dispatched by run_block.BlockSession "
        "(shared budget, atomic staging, native DRC + Rust check)",
        "contract_kind": getattr(session, "kind", "assembly"),
        "plus3": {"segments": len(merged["segments"]), "vias": len(vias),
                  "width_mm": POWER_WIDTH_MM},
        "gnd": {"zones": 1},
        "session": {
            "actions": session.actions,
            "revision_after": session.revision,
            "plus3_verdict": plus3_result.get("native_verdict"),
            "plus3_action": plus3_result.get("mutation_index"),
            "gnd_verdict": gnd_result.get("native_verdict"),
            "gnd_action": gnd_result.get("mutation_index"),
        },
    }


# ---------------------------------------------------------------------------
# Scratch full-board overlay (KTD3): production board COPY + section.
# ---------------------------------------------------------------------------

# Canonical source path -> native production ref the section instance replaces.
# Taken from target-context.json existing_section_instances. The MCU bindings
# C40/C41/R72 are marked provisional in that context and MUST be re-bound when
# pcb/blocks/mcu/ is re-admitted (parallel MCU regeneration).
SECTION_NATIVE_BINDING = {
    "buck.buck": "U3",
    "buck.l_out": "L2",
    "buck.c_in": "C9",
    "buck.c_boot": "C10",
    "buck.c_out1": "C11",
    "buck.c_out2": "C12",
    "buck.c_out_hf": "C13",
    "buck.r_fb_top": "R16",
    "buck.r_fb_bot": "R17",
    "mcu.mcu": "U27",
    "mcu.c_vcc1": "C39",
    "mcu.c_vcc2": "C40",
    "mcu.c_en": "C41",
    "mcu.r_en": "R71",
    "mcu.r_boot": "R72",
    "mcu.r_sda_pullup": "R73",
    "mcu.r_scl_pullup": "R74",
    "mcu.btn_reset": "SW1",
    "mcu.btn_boot": "SW2",
}

# Combined supplied/reference nets -> the native production rail they join.
# Only the two shared supplies are aliased; every other section net stays
# isolated (a future interface), never silently merged by similar name.
SECTION_NET_ALIAS = {"buck-vcc": "+15V", "buck-vcc-1": "+3V3"}
SECTION_NET_ALIAS_REVERSE = {v: k for k, v in SECTION_NET_ALIAS.items()}

# Native copper belonging to a replaced placeholder is removed with it. A
# track is native-placeholder copper when an endpoint sits on one of that
# placeholder's pads (same rule the U2 prototype import uses).
_OVERLAY_SCRIPT = r"""
import json, sys
from pathlib import Path
import pcbnew
base_path, section_path, instruction_path, output_path = map(Path, sys.argv[1:5])
instr = json.loads(instruction_path.read_text())
net_map = instr["net_map"]
native_refs = set(instr["native_refs"])

def load(p):
    return pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(p), None)

def fpmap(board):
    return {f.GetReference(): f for f in board.GetFootprints()}

def point_tuple(v):
    return (v.x, v.y)

def get_net(board, name):
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net

base = load(base_path)
section = load(section_path)
base_fps = fpmap(base)
section_fps = fpmap(section)

# 1. Remove native placeholder copper touching a replaced placeholder pad.
removed_uuids = []
removed = 0
for ref in sorted(native_refs):
    fp = base_fps.get(ref)
    if fp is None:
        raise ValueError("base is missing native placeholder " + ref)
    pad_pts = {point_tuple(p.GetPosition()) for p in fp.Pads()}
    for track in list(base.GetTracks()):
        ends = {point_tuple(track.GetStart()), point_tuple(track.GetEnd())}
        if pad_pts & ends:
            removed_uuids.append(track.m_Uuid.AsString())
            base.Delete(track)
            removed += 1

# 2. Replace the placeholder footprint with the section footprint, renamed to
#    the native ref and re-netted onto the production rails.
replaced = []
for item in instr["replace_footprints"]:
    sref, nref = item["section_ref"], item["native_ref"]
    src = section_fps.get(sref)
    if src is None:
        raise ValueError("section is missing " + sref)
    clone = pcbnew.Cast_to_FOOTPRINT(src.Duplicate(False))
    clone.SetReference(nref)
    for pad in clone.Pads():
        pad.SetNet(get_net(base, net_map.get(pad.GetNetname(), pad.GetNetname())))
    old = base_fps.get(nref)
    if old is not None:
        base.Remove(old)
    base.Add(clone)
    replaced.append({"section_ref": sref, "native_ref": nref})

# 3. Import the section's own copper (segments, vias and filled zones).
imported_tracks = []
for track in section.GetTracks():
    item = track.Duplicate()
    item.SetNet(get_net(base, net_map.get(track.GetNetname(), track.GetNetname())))
    base.Add(item)
    imported_tracks.append(item.m_Uuid.AsString())
imported_zones = []
for zone in section.Zones():
    if zone.GetIsRuleArea():
        continue
    item = zone.Duplicate()
    item.SetNet(get_net(base, net_map.get(zone.GetNetname(), zone.GetNetname())))
    base.Add(item)
    imported_zones.append(item.m_Uuid.AsString())

pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(output_path), base)
print(json.dumps({
    "deleted_native_tracks": removed,
    "deleted_native_uuids": sorted(removed_uuids),
    "replaced_footprints": replaced,
    "imported_track_uuids": sorted(imported_tracks),
    "imported_zone_uuids": sorted(imported_zones),
}, sort_keys=True))
"""


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_overlay_instruction(source_map: dict) -> dict:
    """Bind every section instance to the native placeholder it replaces."""
    by_path = source_map["entries"]
    missing = [p for p in SECTION_NATIVE_BINDING if p not in by_path]
    if missing:
        raise RuntimeError(f"overlay binding names paths absent from source map: {missing}")
    replace = []
    native_refs = []
    combined_to_native: dict[str, str] = {}
    for path, native_ref in sorted(SECTION_NATIVE_BINDING.items()):
        combined = by_path[path]["reference"]
        replace.append({"section_ref": combined, "native_ref": native_ref})
        native_refs.append(native_ref)
        combined_to_native[combined] = native_ref
    if len(set(native_refs)) != len(native_refs) or len(combined_to_native) != 19:
        raise RuntimeError("overlay binding is not a 19-instance bijection")
    return {
        "schema": "control-assembly.overlay-instruction.v1",
        "rule": "remove each native placeholder and its local copper, insert the "
                "source-derived section instance under the native ref, join only the "
                "shared +15V/+3V3/gnd rails, keep every other section net isolated",
        "native_refs": sorted(native_refs),
        "replace_footprints": replace,
        "net_map": dict(SECTION_NET_ALIAS),
        "binding": SECTION_NATIVE_BINDING,
        "rebind_required_after": "pcb/blocks/mcu/ re-admission; C40/C41/R72 bindings "
                                 "are provisional in target-context.json",
    }


def transplant_overlay(base: Path, section: Path, instruction: dict, output: Path) -> dict:
    """Native KiCad object transfer: placeholder removal + section insertion."""
    instruction_path = output.parent / "overlay-instruction.json"
    _write_json(instruction_path, instruction)
    result = subprocess.run(
        [
            harness.KICAD_PYTHON,
            "-c",
            _OVERLAY_SCRIPT,
            str(base),
            str(section),
            str(instruction_path),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"overlay transplant failed: {result.stderr[-1200:]}")
    return json.loads(result.stdout)


def stage_overlay_context(directory: Path, package_dir: Path) -> dict:
    """Constant DRC/library context for the base and overlay boards.

    Starts from the production ``pcb/fp-lib-table`` and overrides the five
    nicknames the section vendors so its footprints resolve, then copies both
    the project libraries and the candidate libraries. The *same* context is
    used for the baseline and the overlay so any constant resolution error
    cancels in the finding-set delta.
    """
    directory.mkdir(parents=True, exist_ok=True)
    production = (REPO / "pcb" / "fp-lib-table").read_text(encoding="utf-8")
    assembly = (package_dir / "fp-lib-table").read_text(encoding="utf-8")
    assembly_nicks = set(re.findall(r'\(name\s+"([^"]+)"\)', assembly))
    kept_lines = [
        line
        for line in production.splitlines()
        if not re.search(r'\(name\s+"([^"]+)"\)', line)
        or re.search(r'\(name\s+"([^"]+)"\)', line).group(1) not in assembly_nicks
    ]
    body = "\n".join(kept_lines).rstrip()
    if body.endswith(")"):
        body = body[:-1].rstrip()
    merged = body + "\n" + assembly.split("(fp_lib_table", 1)[1].lstrip()
    _write_text(directory / "fp-lib-table", merged)
    if (REPO / "pcb" / "libs").is_dir():
        shutil.copytree(REPO / "pcb" / "libs", directory / "libs", dirs_exist_ok=True)
    shutil.copytree(
        package_dir / "candidate-libs", directory / "candidate-libs", dirs_exist_ok=True
    )
    return {
        "fp_lib_table": str((directory / "fp-lib-table").relative_to(REPO)),
        "overridden_nicknames": sorted(assembly_nicks),
    }


def _canon_net(net: str) -> str:
    return SECTION_NET_ALIAS_REVERSE.get(net, net)


def section_extract(
    board: Path,
    identity_by_ref: dict,
    *,
    track_uuids: set | None = None,
    zone_uuids: set | None = None,
) -> dict:
    """Canonical owned-section extract keyed by canonical source identity.

    Independently reads the saved board natively. Pads are keyed
    ``<source_path>.<pad>`` and nets are canonicalized back to the combined
    names; tracks/vias/zones carry no UUID (identity is geometry + net), so an
    identical object in both views compares equal.
    """
    extract = native_extract(board)
    pads: dict = {}
    for footprint in extract["footprints"]:
        path = identity_by_ref.get(footprint["reference"])
        if path is None:
            continue
        for pad in footprint["pads"]:
            pads[f"{path}.{pad['number']}"] = {
                "net": _canon_net(pad["net"]),
                "x_mm": round(float(pad["position_mm"][0]), 6),
                "y_mm": round(float(pad["position_mm"][1]), 6),
            }
    tracks = []
    vias = []
    for track in extract["tracks"]:
        if track_uuids is not None and track["uuid"] not in track_uuids:
            continue
        if track["kind"] == "segment":
            tracks.append(
                {
                    "net": _canon_net(track["net"]),
                    "layer": track["layer"],
                    "width_mm": round(float(track["width_mm"]), 6),
                    "start_mm": [round(float(v), 6) for v in track["start_mm"]],
                    "end_mm": [round(float(v), 6) for v in track["end_mm"]],
                }
            )
        else:
            vias.append(
                {
                    "net": _canon_net(track["net"]),
                    "position_mm": [round(float(v), 6) for v in track["position_mm"]],
                    "diameter_mm": round(float(track["width_mm"]), 6),
                }
            )
    zones = []
    for zone in extract["zones"]:
        if zone_uuids is not None and zone["uuid"] not in zone_uuids:
            continue
        zones.append(
            {
                "net": _canon_net(zone["net"]),
                "layer": zone["layer"],
                "filled": bool(zone["filled"]),
            }
        )
    return {
        "pads": pads,
        "tracks": sorted(tracks, key=lambda i: json.dumps(i, sort_keys=True)),
        "vias": sorted(vias, key=lambda i: json.dumps(i, sort_keys=True)),
        "zones": sorted(zones, key=lambda i: json.dumps(i, sort_keys=True)),
        "endpoints": {},
    }


def section_endpoints(
    board: Path,
    identity_by_ref: dict,
    board_net: dict | None = None,
) -> dict:
    """Interface endpoints as canonical source-identity clusters.

    ``board_net`` maps the combined net name to the name the board carries
    (the overlay joins the production ``+15V``/``+3V3`` rails), so the lookup
    is by the view's own net identity, never by string coincidence.
    """
    connectivity = native_connectivity(board)
    board_net = board_net or {}
    endpoints: dict = {}
    for name, spec in REQUIRED_INTERNAL.items():
        net = board_net.get(spec["net"], spec["net"])
        entry = connectivity["nets"].get(net, {})
        clusters = []
        for cluster in entry.get("clusters", []):
            canon = []
            for pad in cluster:
                ref, _, num = pad.rpartition(".")
                path = identity_by_ref.get(ref)
                if path is None:
                    # A production pad pulled in by joining a shared rail; the
                    # comparison is over the owned section, so it is not part
                    # of the canonical endpoint cluster.
                    continue
                canon.append(f"{path}.{num}")
            if canon:
                clusters.append(sorted(canon))
        endpoints[name] = {"net": _canon_net(net), "clusters": sorted(clusters)}
    return endpoints


def outside_region_invariance(
    base: Path, overlay: Path, native_refs: set, imported_uuids: set, deleted_uuids: set
) -> dict:
    """Production geometry outside the replaced placeholders is unchanged."""
    base_ex = native_extract(base)
    overlay_ex = native_extract(overlay)
    base_fp = {f["reference"]: f for f in base_ex["footprints"]}
    overlay_fp = {f["reference"]: f for f in overlay_ex["footprints"]}
    problems = []
    for ref in sorted(set(base_fp) - native_refs):
        if ref not in overlay_fp:
            problems.append({"kind": "footprint_missing", "ref": ref})
            continue
        left, right = base_fp[ref], overlay_fp[ref]
        left_val = json.dumps(
            [left["position_mm"], round(left["angle_deg"], 6),
             sorted((p["number"], p["net"]) for p in left["pads"])],
            sort_keys=True,
        )
        right_val = json.dumps(
            [right["position_mm"], round(right["angle_deg"], 6),
             sorted((p["number"], p["net"]) for p in right["pads"])],
            sort_keys=True,
        )
        if left_val != right_val:
            problems.append({"kind": "footprint_changed", "ref": ref})
    base_tracks = {t["uuid"]: t for t in base_ex["tracks"]}
    overlay_tracks = {t["uuid"]: t for t in overlay_ex["tracks"]}

    def geometry(track: dict) -> str:
        keys = ["kind", "layer", "width_mm"]
        keys += (
            ["start_mm", "end_mm"]
            if track["kind"] == "segment"
            else ["position_mm", "drill_mm"]
        )
        return json.dumps({k: track.get(k) for k in keys}, sort_keys=True)

    net_reassigned = []
    for uuid, track in base_tracks.items():
        if uuid in deleted_uuids:
            continue
        other = overlay_tracks.get(uuid)
        if other is None:
            problems.append({"kind": "track_missing", "uuid": uuid})
            continue
        if geometry(track) != geometry(other):
            problems.append({"kind": "track_changed", "uuid": uuid})
        elif track["net"] != other["net"]:
            # KiCad's load/save silently re-propagates a track's net from the
            # pads it touches. Geometry outside the replaced placeholders is
            # unchanged; a net change is recorded (and DRC-checked) rather than
            # silently absorbed.
            net_reassigned.append(
                {"uuid": uuid, "base_net": track["net"], "overlay_net": other["net"]}
            )
    return {
        "status": "pass" if not problems else "fail",
        "problems": problems[:50],
        "problem_count": len(problems),
        "net_reassigned": net_reassigned,
        "net_reassigned_count": len(net_reassigned),
        "checked_footprints": len(set(base_fp) - native_refs),
        "checked_tracks": len(base_tracks) - len(deleted_uuids & set(base_tracks)),
    }


def build_cross_view_report(
    assembly_board: Path,
    overlay_board: Path,
    source_map: dict,
    imported: dict,
    finding_delta: dict,
    invariance: dict,
    overlay_context: dict,
) -> dict:
    """Compare the owned section extracted independently from both views."""
    assembly_identity = {
        entry["reference"]: path for path, entry in source_map["entries"].items()
    }
    overlay_identity = {v: k for k, v in SECTION_NATIVE_BINDING.items()}
    assembly = section_extract(assembly_board, assembly_identity)
    overlay = section_extract(
        overlay_board,
        overlay_identity,
        track_uuids=set(imported["imported_track_uuids"]),
        zone_uuids=set(imported["imported_zone_uuids"]),
    )
    assembly["endpoints"] = section_endpoints(assembly_board, assembly_identity)
    overlay["endpoints"] = section_endpoints(
        overlay_board, overlay_identity, SECTION_NET_ALIAS
    )
    mismatches = compose_blocks.compare_views(assembly, overlay)
    return {
        "schema": "control-assembly.cross-view-report.v1",
        "rule": "compare canonical source identities, transformed pad geometry, "
        "tracks/vias/zones and interface endpoints in target coordinates; a "
        "difference in only one view fails",
        "assembly_view": {
            "path": str(assembly_board.relative_to(REPO)),
            "sha256": _sha256(assembly_board),
        },
        "overlay_view": {
            "path": str(overlay_board.relative_to(REPO)),
            "sha256": _sha256(overlay_board),
            "base": "pcb/temper.kicad_pcb (copied; production digest verified exact)",
        },
        "overlay_context": overlay_context,
        "binding": SECTION_NATIVE_BINDING,
        "rebind_required_after": "pcb/blocks/mcu/ re-admission (C40/C41/R72 provisional)",
        "categories": list(compose_blocks.COMPARE_CATEGORIES),
        "status": "pass" if not mismatches else "fail",
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:50],
        "overlay_finding_delta": finding_delta,
        "outside_region_invariance": invariance,
        "context_dependent_zones": "zone fill is context-dependent; the comparison "
        "binds zone identity (net/layer/filled) and verifies native connectivity in "
        "each view rather than comparing filled polygons",
    }


def build_overlay(work_dir: Path) -> dict:
    """Copy the production board, apply the ledger, insert the section, refill."""
    overlay_dir = work_dir / "overlay"
    if overlay_dir.exists():
        shutil.rmtree(overlay_dir)
    overlay_dir.mkdir(parents=True)
    context = stage_overlay_context(overlay_dir, PACKAGE)
    base = overlay_dir / "base.kicad_pcb"
    shutil.copyfile(PRODUCTION_BOARD, base)
    section = work_dir / "control-assembly-routed.kicad_pcb"
    source_map = json.loads((PACKAGE / "source-map.json").read_text())
    instruction = build_overlay_instruction(source_map)
    overlay = overlay_dir / "overlay.kicad_pcb"
    imported = transplant_overlay(base, section, instruction, overlay)
    # Refill BOTH views with the identical native command. Comparing a
    # refilled overlay against an unrefilled base manufactures phantom
    # unconnected/zone findings (the fill state differs, not the section).
    base_refill = run_refill(base, overlay_dir / "base-refill")
    refill = run_refill(overlay, overlay_dir / "refill")
    return {
        "base": base,
        "overlay": overlay,
        "imported": imported,
        "instruction": instruction,
        "overlay_context": context,
        "base_refill_returncode": base_refill["returncode"],
        "refill_returncode": refill["returncode"],
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

    # Every mutation below goes through the shared bounded native operation
    # (run_block.BlockSession); no direct _native_replace_copper bypass.
    session_dir = work_dir / "session"
    if session_dir.exists():
        shutil.rmtree(session_dir)
    run_block.prepare_assembly(session_dir, PACKAGE)
    session = run_block.BlockSession(session_dir)
    baseline_drc = run_drc(candidate, work_dir / "baseline")
    baseline_drc_set, baseline_drc_stability = drc_stable_set(
        candidate, work_dir / "baseline"
    )
    baseline_erc = run_erc(SCHEMATIC, work_dir / "baseline")
    baseline_erc_set = erc_finding_set(baseline_erc)
    try:
        routing = route_supply_return(session, target)
        session_revision = session.revision
        session_actions = session.actions
    finally:
        session.close()
    shutil.copyfile(session.board, candidate)
    refill = run_refill(candidate, work_dir / "refill")

    routed_drc = run_drc(candidate, work_dir / "routed")
    routed_drc_set, routed_drc_stability = drc_stable_set(
        candidate, work_dir / "routed"
    )
    routed_erc = run_erc(SCHEMATIC, work_dir / "routed")
    routed_erc_set = erc_finding_set(routed_erc)

    connectivity = native_connectivity(candidate)
    extract = native_extract(candidate)
    keepout = target["reserved_regions_mm"]["antenna_keepout"]
    signal_nets = tuple(
        n for n in REQUIRED_CONNECTED_NETS if n not in run_block.ASSEMBLY_POWER_NETS
    )
    checks = {
        "required_connectivity": check_required_connectivity(connectivity),
        "inter_block": check_inter_block(connectivity),
        "antenna_keepout": check_keepout(extract, keepout),
        "power_width": check_power_width(
            extract, list(run_block.ASSEMBLY_POWER_NETS), signal_nets
        ),
        "no_placeholder_leftover": check_no_mcu_buck_placeholder(extract, ledger),
        "production_digest": production_digest_exact(),
    }

    # Scratch full-board overlay: production board COPIED, ledger applied,
    # section inserted, refilled; then the independent cross-view comparison.
    source_map = json.loads((PACKAGE / "source-map.json").read_text())
    overlay = build_overlay(work_dir)
    overlay_base_set, overlay_base_stability = drc_stable_set(
        overlay["base"], work_dir / "overlay" / "baseline"
    )
    overlay_set, overlay_stability = drc_stable_set(
        overlay["overlay"], work_dir / "overlay" / "routed"
    )
    overlay_delta = finding_set_delta(overlay_base_set, overlay_set)
    invariance = outside_region_invariance(
        overlay["base"],
        overlay["overlay"],
        set(overlay["instruction"]["native_refs"]),
        set(overlay["imported"]["imported_track_uuids"]),
        set(overlay["imported"]["deleted_native_uuids"]),
    )
    cross_view = build_cross_view_report(
        candidate,
        overlay["overlay"],
        source_map,
        overlay["imported"],
        overlay_delta,
        invariance,
        overlay["overlay_context"],
    )
    summary = {
        "schema": "control-assembly.u3-verification.v1",
        "status": "apparatus-only-assisted",
        "live_model": False,
        "live_model_blocker": "Zen FreeUsageLimitError HTTP 429; no autonomous construction occurred",
        "routing": routing,
        "session": {
            "runner": "run_block.BlockSession",
            "contract_kind": getattr(session, "kind", "assembly"),
            "actions": session_actions,
            "revision_after": session_revision,
            "operations_log": str((session_dir / "operations.jsonl").relative_to(REPO)),
            "protected_sha256": json.loads(
                (session_dir / "task-contract.json").read_text()
            )["protected_sha256"],
            "note": "all PCB mutations used the shared bounded native replace_copper "
            "operation, budget and atomic staging; no direct native bypass",
        },
        "refill": {"returncode": refill["returncode"]},
        "overlay": {
            "status": "produced",
            "base": str(overlay["base"].relative_to(REPO)),
            "board": str(overlay["overlay"].relative_to(REPO)),
            "board_sha256": _sha256(overlay["overlay"]),
            "base_refill_returncode": overlay["base_refill_returncode"],
            "refill_returncode": overlay["refill_returncode"],
            "native_tracks_removed": overlay["imported"]["deleted_native_tracks"],
            "footprints_replaced": len(overlay["imported"]["replaced_footprints"]),
            "bound_after": "pcb/blocks/mcu/ re-admission (C40/C41/R72 provisional)",
            "finding_delta": overlay_delta,
            "stability": {
                "baseline": overlay_base_stability,
                "routed": overlay_stability,
                "note": "intersection across DRC_SAMPLES runs per view; both views "
                "refilled with the identical native command",
            },
            "outside_region_invariance": invariance,
            "production_digest_after_overlay": production_digest_exact(),
            "cross_view_status": cross_view["status"],
            "cross_view_mismatch_count": cross_view["mismatch_count"],
        },
        "drc": {
            "baseline_findings": len(baseline_drc_set),
            "routed_findings": len(routed_drc_set),
            "delta": finding_set_delta(baseline_drc_set, routed_drc_set),
            "unconnected_baseline": len(baseline_drc.get("unconnected_items", [])),
            "unconnected_routed": len(routed_drc.get("unconnected_items", [])),
            "schematic_parity_baseline": len(baseline_drc.get("schematic_parity", [])),
            "schematic_parity_routed": len(routed_drc.get("schematic_parity", [])),
            "schematic_parity_enabled": True,
            "stability": {
                "baseline": baseline_drc_stability,
                "routed": routed_drc_stability,
                "note": "compared sets are the intersection across DRC_SAMPLES runs "
                "(kicad-cli is nondeterministic run-to-run)",
            },
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
    _write_json(work_dir / "cross-view-report.json", cross_view)
    _write_json(work_dir / "overlay-instruction.json", overlay["instruction"])
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
        "overlay_board": {
            "path": str(overlay["overlay"].relative_to(REPO)),
            "sha256": _sha256(overlay["overlay"]),
        },
        "cross_view_report": {
            "path": str((work_dir / "cross-view-report.json").relative_to(REPO)),
            "sha256": _sha256(work_dir / "cross-view-report.json"),
        },
        "verdict": "apparatus-only; not a qualified cooker",
    }
    _write_json(work_dir / "candidate-binding.json", binding)
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
