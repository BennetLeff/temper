#!/usr/bin/env python3
"""Neutrality table for REFACTOR-PROOF.md: normalised hashes of each chain artefact before / after the refactor.

    python3 refactor_table.py BEFORE_BUILD BEFORE_TRACKED BEFORE_EXTRA AFTER_BUILD AFTER_TRACKED [TAG]

BEFORE_*: the pre-refactor chain's build dir, its snapshot of the tracked outputs (unit-relative paths) and the
necks / OCP / scorecard outputs; AFTER_BUILD: refactor_same_input.sh's OUT (holds its own necks / OCP / scorecard);
AFTER_TRACKED: the unit (the tracked outputs as that run left them). Prints a Markdown table; exit 1 on any difference.
Hash = sha256 of the normalised content (refactor_compare.py), first 12 hex digits.
"""
import glob
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refactor_compare as rc  # noqa: E402


def nhash(p: Path) -> str:
    n = p.name
    if n.endswith(".kicad_pcb"):
        return rc.pcb_hash(p)[:12]
    if n.endswith(".zip"):
        return hashlib.sha256(json.dumps(rc.zip_members(p)).encode()).hexdigest()[:12]
    if n.endswith(".json") or n.endswith(".json.gz"):
        return hashlib.sha256(json.dumps(rc.norm(rc.load_json(p)), sort_keys=True).encode()).hexdigest()[:12]
    return hashlib.sha256(rc.DATE.sub(b"", p.read_bytes())).hexdigest()[:12]


def main(a):
    bb, bt, be, ab, at = map(Path, a[:5])
    tag = a[5] if len(a) > 5 else "native21s31"
    ts = tag.replace("native21", "")
    K = "validation-results/02-protection-timing/kelvin"
    T4 = "validation-results/04-board-current-thermal/round5-native21/outputs"
    B3 = "validation-results/04-board-current-thermal/round5-native21/b3/outputs"
    rows = [("board (section.kicad_pcb, uuid-normalised, fills included)", bb / "section.kicad_pcb", ab / "section.kicad_pcb")]
    for f in ("copper-dump.json", "pads-board.json", "evidence.json", "barrier-gate-rust.json", "jlc-dfm.json",
              "bypass-check.json", "native21-all-copper.json.gz", "power_copper.json.gz", "res-a-creepage.json",
              "pi-distances.json", "return-path.json", "barrier.txt"):
        rows.append((f, bb / f, ab / f))
    rows.append(("d5-audit.json", bt / "native-21/verification/d5-audit.json", ab / "d5-audit.json"))
    rows.append((f"Gerber ZIP (date lines removed)", bt / "validation-results/08-manufacturing-package/native-21/fab/native-21-gerbers.zip",
                 ab / "fab/native-21-gerbers.zip"))
    rows.append(("drill-report.txt", bt / "validation-results/08-manufacturing-package/native-21/fab/drill-report.txt",
                 ab / "fab/drill-report.txt"))
    for f in (f"plane-{tag}.json", f"budget-{tag}.json"):
        rows.append((f"kelvin {f}", bt / K / f, at / K / f))
    for p in sorted(glob.glob(str(bt / T4 / "*.json"))):
        f = Path(p).name
        if f != "cache.json":
            rows.append((f"task04 {f}", Path(p), at / T4 / f))
    for p in sorted(glob.glob(str(bt / B3 / "*.json"))):
        f = Path(p).name
        if f != "cache.json":
            rows.append((f"B3 {f}", Path(p), at / B3 / f))
    rows.append((f"necks {ts}_necks.json", be / f"{ts}_necks.json", ab / f"{ts}_necks.json"))
    rows.append(("OCP pickup result.json", be / "ocp-result.json", ab / "ocp-result.json"))
    rows.append(("scorecard.json", be / "scorecard.json", ab / "scorecard.json"))
    bad = 0
    print("| artefact | before | after | equal? |\n|---|---|---|---|")
    for label, x, y in rows:
        hx, hy = nhash(x), nhash(y)
        ok, why = rc.compare(x, y)
        bad += not ok
        print(f"| {label} | `{hx}` | `{hy}` | {'yes' if ok else 'NO: ' + why[:120]} |")
    print(f"\n{len(rows)} artefacts, {bad} different")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
