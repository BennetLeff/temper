#!/usr/bin/env python3
"""Copy the committed body-level B3 model (b3-convergence, stage 19b) into ../model/ and re-point it at the s32 board.

Only three textual patches, each asserted to apply exactly once:
  1. ROUND5 = the repo's round5-native21 folder (the copy lives outside the repo; the repo is read-only here);
  2. spec_for(): U1/U2 are Infineon 2EDR8259X since stage 29 (DECISIONS 31). No junction-to-board figure was
     taken from its datasheet here, so it is mapped to the UCC21550 DWK class values (ASSUMED; U1/U2 are 40+ K
     from any limit in every case, so this does not touch a verdict);
  3. nothing else: run_case / solve / metrics are the committed code.

part-bodies.json: the stage-19b extraction (body F.Fab boxes per footprint) is reused after checking, against the s32
pick-and-place file, that every part has the same footprint and position (x equal, KiCad pos-file y = -board y);
MPNs are refreshed from the s32 file. Exit 1 if any check fails.
"""
import csv
import json
import shutil
import sys
from pathlib import Path

from paths import CONV, FAB, MODEL, ROUND5


def patch_once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"prepare_model: patch '{what}' matched {n} times (expected 1)")
    return text.replace(old, new)


def main():
    MODEL.mkdir(parents=True, exist_ok=True)
    (MODEL / "inputs").mkdir(exist_ok=True)
    tb = (CONV / "thermal_body.py").read_text()
    tb = patch_once(tb, "ROUND5 = HERE.parent\n", f"ROUND5 = Path({str(ROUND5)!r})   # thermal-ratings audit: repo copy\n",
                    "ROUND5")
    tb = patch_once(tb, '    if mpn.startswith("UCC21550"):\n',
                    '    if mpn.startswith("UCC21550") or mpn.startswith("2EDR8259X"):   # audit: 2EDR8259X ASSUMED = DWK class\n',
                    "2EDR8259X")
    (MODEL / "thermal_body.py").write_text(tb)
    shutil.copyfile(CONV / "body_runs.py", MODEL / "body_runs.py")

    pb = json.loads((CONV / "inputs/part-bodies.json").read_text())
    pos = {r["Ref"]: r for r in csv.DictReader(open(FAB / "positions-kicad.csv"))}
    bad = []
    for ref, b in pb["parts"].items():
        r = pos.get(ref)
        if r is None:
            bad.append(f"{ref}: not on the s32 pick-and-place")
            continue
        if abs(float(r["PosX"]) - b["at"][0]) > 1e-3 or abs(-float(r["PosY"]) - b["at"][1]) > 1e-3:
            bad.append(f"{ref}: moved ({r['PosX']},{r['PosY']}) vs 19b {b['at'][:2]}")
        if not b["fp"].endswith(":" + r["Package"]):
            bad.append(f"{ref}: footprint {r['Package']} vs 19b {b['fp']}")
        b["mpn_19b"] = b["mpn"]
        b["mpn"] = r["Val"]
    if bad:
        raise SystemExit("prepare_model: part bodies do not carry over to s32:\n  " + "\n  ".join(bad))
    pb["audit_note"] = ("stage-19b bodies re-used for s32 after position/footprint check against "
                        "08-manufacturing-package/native-21/fab/positions-kicad.csv; mpn refreshed from that file")
    (MODEL / "inputs/part-bodies.json").write_text(json.dumps(pb, indent=1) + "\n")
    changed = {k: (v["mpn_19b"], v["mpn"]) for k, v in pb["parts"].items() if v["mpn_19b"] != v["mpn"]}
    print(f"prepare_model: {len(pb['parts'])} part bodies carried to s32; MPN changes since 19b: {changed}")


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
