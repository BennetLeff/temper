#!/usr/bin/env python3
"""3D-model gate: every body the fit gates see comes from a tracked file, and no model silently drops out of the STEP.

    python3 -I model_gate.py BOARD.kicad_pcb STEP.log ENVELOPES.json --kiprjmod DIR [--json OUT]

Stage 53 (s52 footprint/3D review item 22, a new error class): L1, C3 and C4 resolved through ${KIPRJMOD}/models3d/,
an untracked copy of the tracked PS/models3d/. A clean checkout would export the STEP without them, KiCad only logs
"Could not add 3D model for L1." in step.log, and the FIT gate would pass without L1's 41 mm body. This gate fails when:
  * a model path does not resolve to a file (KIPRJMOD and KICAD10_3DMODEL_DIR substituted), unless the reference has a
    model-less envelope in ENVELOPES.json (courtyard x datasheet height, read by the fit gates instead);
  * a model resolves inside this repository to a file git does not track;
  * step.log reports "Could not add 3D model for REF" for a REF without an envelope;
  * a footprint has no model and no envelope, except bodiless board-only items (test points, mounting holes, fiducials).
Exit 1 on any failure.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

KICAD3D = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels"
BODILESS = re.compile(r"^(TP|H|FID)\d+$")


def footprints(text):
    """(reference, [model paths]) per footprint, from the board file's footprint blocks."""
    out = []
    starts = [m.start() for m in re.finditer(r"\n\t\(footprint ", text)] + [len(text)]
    for a, b in zip(starts, starts[1:]):
        blk = text[a:b]
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if ref:
            out.append((ref.group(1), re.findall(r'\(model "([^"]+)"', blk)))
    return out


def resolve(path, kiprjmod):
    p = path.replace("${KIPRJMOD}", str(kiprjmod)).replace("${KICAD10_3DMODEL_DIR}", KICAD3D)
    if "${" in p:
        return None
    return Path(p).resolve()


def tracked(p, repo):
    r = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", str(p)], capture_output=True)
    return r.returncode == 0


def check(board_text, step_log, envelopes, kiprjmod, repo):
    fails, rows = [], []
    for ref, models in footprints(board_text):
        if not models:
            if ref not in envelopes and not BODILESS.match(ref):
                fails.append(f"{ref}: no 3D model and no envelope")
            continue
        for m in models:
            p = resolve(m, kiprjmod)
            ok = p is not None and p.is_file()
            inrepo = ok and p.is_relative_to(repo)
            tr = tracked(p, repo) if inrepo else None
            rows.append({"ref": ref, "model": m, "resolved": str(p), "exists": ok, "tracked": tr})
            if not ok and ref not in envelopes:
                fails.append(f"{ref}: model {m} does not resolve to a file and {ref} has no envelope")
            if inrepo and not tr:
                fails.append(f"{ref}: model {m} resolves to {p}, which git does not track")
    dropped = sorted(set(re.findall(r"Could not add 3D model for (\S+?)\.?\s*$", step_log, re.M)))
    for ref in dropped:
        if ref not in envelopes:
            fails.append(f"{ref}: STEP export dropped its 3D model (step.log) and it has no envelope")
    return fails, rows, dropped


def main():
    a = sys.argv[1:]
    board, log, env = Path(a[0]), Path(a[1]), json.loads(Path(a[2]).read_text())
    kiprjmod = Path(a[a.index("--kiprjmod") + 1]).resolve()
    repo = Path(subprocess.run(["git", "-C", str(kiprjmod), "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, check=True).stdout.strip()).resolve()
    fails, rows, dropped = check(board.read_text(), log.read_text(), env, kiprjmod, repo)
    res = {"models": len(rows), "files": len({r["resolved"] for r in rows}), "dropped_in_step": dropped,
           "envelopes": sorted(env), "failures": fails}
    if "--json" in a:
        Path(a[a.index("--json") + 1]).write_text(json.dumps(res, indent=1) + "\n")
    print(f"MODELS {'PASS' if not fails else 'FAIL'}: {len(rows)} model refs, {res['files']} files, "
          f"dropped in STEP {dropped} (envelopes {sorted(env)}), failures {len(fails)}")
    for f in fails:
        print("  ", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
