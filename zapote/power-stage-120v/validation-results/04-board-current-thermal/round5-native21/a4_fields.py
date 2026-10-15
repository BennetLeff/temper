#!/usr/bin/env python3
"""Check (or sync) the gitignored task-04 heat fields (outputs/*-heat.npz) against the tracked results (DECISIONS 51).

    python3 a4_fields.py check                      exit 0 if the local fields are the ones outputs/ was computed with
    python3 a4_fields.py sync --from WORKTREE_ROOT  copy the fields of every case whose JSON is byte-identical there

The task-04 JSONs and outputs/cache.json travel with commits; the *-heat.npz fields beside them do not. After a merge or
cherry-pick, a worktree can hold another board's fields next to the new JSONs. B3 (thermal.remap_a4) then stops on its
energy check. The chain notices on its own (regate.sh compares cache.json's npz_sha256 and recomputes), but direct
use of B3 or b3-ratings/run_basis.py does not, so they call `check` first.

Checks: the set hash equals outputs/cache.json "npz_sha256" (the same hash regate.sh writes), and each case's field
energy (joule cells plus barrel heat) equals its JSON's loss_w.
"""
import argparse
import glob
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
REL = HERE.relative_to(HERE.parents[2])          # validation-results/04-board-current-thermal/round5-native21


def set_hash(out):
    h = hashlib.sha256()
    for f in sorted(glob.glob(str(out / "*.npz"))):
        h.update(open(f, "rb").read())
    return h.hexdigest()


def energy_errors(out):
    import numpy as np
    bad, n = [], 0
    for j in sorted(out.glob("*.json")):
        npz = j.with_name(j.stem + "-heat.npz")
        if not npz.exists():
            continue
        m = json.loads(j.read_text())
        if "loss_w" not in m:
            continue
        n += 1
        a = np.load(npz)
        s = sum(float(a[k].sum()) for k in a.files if k.endswith("_joule_w"))
        s += sum(sum(i["layer_joule_w"].values()) for i in m.get("barrel_heat_by_layer", []))
        if abs(s - m["loss_w"]) > 1e-8 * max(1.0, m["loss_w"]):
            bad.append(j.stem)
    return n, bad


def check(out=OUT):
    cache = json.loads((out / "cache.json").read_text())
    want, got = cache.get("npz_sha256"), set_hash(out)
    n, bad = energy_errors(out)
    ok = want == got and not bad
    board = cache.get("computed_on_board", "?")[:12]
    if ok:
        print(f"a4 fields OK: {n} cases, set hash matches cache.json (board {board})")
    else:
        print(f"a4 fields STALE: set hash {'matches' if want == got else 'differs from'} cache.json; "
              f"{len(bad)} of {n} cases fail the energy check {bad[:5]}\n"
              f"  outputs/ was computed on board {board}. Fix: copy the fields from a worktree that ran task 04 on it,\n"
              f"  `python3 {REL}/a4_fields.py sync --from <worktree root>`, or re-run task 04 on that board\n"
              f"  (`sh native-21/layout/gates/regate.sh BUILDDIR task04`).", file=sys.stderr)
    return ok


def sync(src_root):
    src = Path(src_root).resolve() / "zapote/power-stage-120v" / REL / "outputs"
    if not src.is_dir():
        sys.exit(f"no task-04 outputs at {src}")
    copied, skipped = 0, []
    for j in sorted(OUT.glob("*.json")):
        npz = j.with_name(j.stem + "-heat.npz")
        s_json, s_npz = src / j.name, src / npz.name
        if not s_npz.exists():
            continue
        if s_json.exists() and s_json.read_bytes() == j.read_bytes():
            shutil.copy2(s_npz, npz)
            copied += 1
        else:
            skipped.append(j.stem)
    print(f"copied {copied} fields from {src}; skipped (JSON differs) {skipped[:8]}")
    return check()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["check", "sync"])
    ap.add_argument("--from", dest="src")
    a = ap.parse_args()
    if a.cmd == "sync" and not a.src:
        ap.error("sync needs --from WORKTREE_ROOT")
    sys.exit(0 if (check() if a.cmd == "check" else sync(a.src)) else 1)


if __name__ == "__main__":
    main()
