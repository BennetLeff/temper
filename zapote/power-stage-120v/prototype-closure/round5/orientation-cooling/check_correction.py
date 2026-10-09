"""Verify frozen correction receipts against explicit contact/thread expectations."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round5/orientation-cooling"
P = "BASE_BASE_R2_"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    r = json.loads((OUT / "checks.json").read_text())
    assert r["source_sha256"] == sha(HERE / "build_correction.py")
    for key in ("source", "native_source", "validation_context_source"):
        assert sha(ROOT / r[key]["path"]) == r[key]["sha256"]
    for key in ("native_hits", "context_hits", "airway_obstacles"):
        assert r[key] == [], key
    assert r["sink_solids"] == 1
    assert all(n == 1 for n in r["replacement_solid_counts"].values())
    assert r["pe_adapter_sha256"] == sha(HERE / "pe_bond.py")
    expected = {}

    def allow(a, b, volume):
        expected[frozenset((a, b))] = volume

    annulus = math.pi * (1.5**2 - 1.25**2)
    for side in ("LEFT", "RIGHT"):
        for z in (22, 62):
            allow(P + "CUSTOM_SINK", P + f"SINK_M3_{side}_{z}", annulus * 6)
    for label in ("Q2", "Q3", "Q5", "Q6", "BR_L", "BR_R"):
        allow(P + "CUSTOM_SINK", f"R5_{label}_ANCHOR_M3x12", annulus * 9)
        allow(f"R5_{label}_CLAMP_C_FRAME_6061", f"R5_{label}_PRESSURE_M3x10", annulus * 3)
    for rail, carriers, floors in (("-122p5", (0, 1), (2, 3)), ("128p5", (2, 3), (0, 1))):
        for i in carriers:
            allow(P + "CARRIER_RAIL_" + rail, P + f"CARRIER_M3x25_{i}", annulus * 5.4)
        for i in floors:
            allow(P + "CARRIER_RAIL_" + rail, P + f"FLOOR_MOUNT_SCREW_{i}", annulus * 6)
    for i in range(4, 8):
        allow(
            P + f"FLOOR_MOUNT_SCREW_{i}", P + f"CRADLE_M4_NUT_{i}", math.pi * (2**2 - 1.65**2) * 3
        )
    for side in ("LEFT", "RIGHT"):
        for i in (0, 1):
            for end in ("TOP", "BOTTOM"):
                allow(f"R5_{side}_FAN_POST_{i}", f"R5_{side}_FAN_{end}_M3_{i}", annulus * 6)
    allow(P + "CUSTOM_SINK", "R5_PE_SINK_M4x12_BOLT", math.pi * (2**2 - 1.65**2) * 8.7)
    allow(
        P + "SINK_DEDICATED_PE_STUD",
        "R5_PE_CRADLE_M4_NUT_ENVELOPE",
        math.pi * (2**2 - 1.65**2) * 3.2,
    )
    for y, side in ((167, "FRONT"), (173, "REAR")):
        allow(f"R5_PE_STRAIN_BASE_M3_{y}", f"R5_PE_STRAIN_SUPPORT_{side}", annulus * 6)
    assert all(c["distance_mm"] < 1e-6 for c in r["pe_terminal_contacts"]), r[
        "pe_terminal_contacts"
    ]
    assert not r["pe_vs_airway"]
    assert {(h["new"], h["context"]) for h in r["pe_tool_vs_new_parts"]} == {
        ("PE_cradle_socket", "BASE_PROPOSAL_FRONT_PROFILE"),
        ("PE_cradle_socket", "BASE_PROPOSAL_LEFT_WALL"),
    }
    # Explicit service stage: remove these detachable chamber panels before torquing cradle PE.
    assert not [
        h
        for h in r["pe_tool_vs_new_parts"]
        if h["context"] not in ("BASE_PROPOSAL_FRONT_PROFILE", "BASE_PROPOSAL_LEFT_WALL")
    ]
    deferred = {(h["new"], h["context"]) for h in r["packaging_deferred_context_hits"]}
    assert deferred == {
        (P + "CARRIER_RAIL_-122p5", "PAIRED_POST_M3x60_CS_285"),
        (P + "CARRIER_RAIL_-122p5", "PAIRED_POST_M3x60_CS_295"),
        ("BASE_PROPOSAL_LEFT_WALL", "OUT_FLOOR_M3x6_-126.0"),
        ("BASE_PROPOSAL_LEFT_WALL", "OUT_MACHINED_BRACKET_-128"),
    }
    actual = {
        frozenset((h["new"], h["context"])): h["volume_mm3"] for h in r["replacement_pair_hits"]
    }
    assert actual.keys() == expected.keys(), (
        actual.keys() - expected.keys(),
        expected.keys() - actual.keys(),
    )
    for pair, v in actual.items():
        assert abs(v - expected[pair]) < 1e-4, (pair, v, expected[pair])
    for c in r["contact_checks"]:
        assert c["proxy_to_source_distance_mm"] < 1e-7
        assert (
            abs(c["source_slice_contact_area_mm2"] - (336 if c["reference"] == "BR1" else 65.24))
            < 1e-4
        )
    native = json.loads((OUT / "native-contact-screen.json").read_text())
    board = ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"
    assert native["board_sha256"] == sha(board)
    assert len(native["windows"]) == 6 and all(
        x["nominal_outer_copper_clear"] for x in native["windows"]
    )
    for n in ("cooling-replacements", "cooling-rigid-context"):
        assert r[n]["valid"] and sha(OUT / (n + ".step")) == r[n]["sha256"]
    paths = list(HERE.glob("*")) + [
        OUT / n
        for n in (
            "checks.json",
            "interface.json",
            "removed_names.json",
            "native-contact-screen.json",
            "cooling-replacements.step",
            "cooling-rigid-context.step",
        )
    ]
    paths += [
        ROOT / "zapote/power-stage-120v/prototype-closure/round2/cooling/build_revision.py",
        ROOT / "zapote/power-stage-120v/prototype-closure/round3/packaging/build_proposal.py",
        ROOT / "zapote/power-stage-120v/prototype-closure/round4/catch/build_carrier.py",
    ]
    record = {
        "status": "NOMINAL_DIGITAL_CORRECTION_VERIFIED_WITH_DESIGN_AND_PHYSICAL_HOLDS",
        "release": False,
        "deferred_to_packaging": r["packaging_deferred_context_hits"],
        "pe_terminal_contacts": r["pe_terminal_contacts"],
        "pe_access_stage": "Remove chamber front, left and roof panels and top assembly before socket/Allen access; raw tool intersections retained in checks.json",
        "thread_pairs_analytically_verified": len(actual),
        "contact_scope": "Generic source-model planar contact only, not physical contact or supplier thermal evidence",
        "tool_access": "See positive tool intersections; top removal and staged population required",
        "files": {str(p.relative_to(ROOT)): sha(p) for p in paths if p.is_file()},
    }
    (OUT / "verification.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
