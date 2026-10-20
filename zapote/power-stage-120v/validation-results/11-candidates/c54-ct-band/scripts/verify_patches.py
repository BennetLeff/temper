#!/usr/bin/env python3
"""c54-ct-band: check the proposed patches without touching the repository.

    python3 -I scripts/verify_patches.py            # writes results/verify-patches.txt
    python3 -I scripts/verify_patches.py --check    # exit 1 if the committed record differs

1. `git apply --check` of 01, 02, 03 and 05 against the working tree, and 01-05 in sequence on a temporary copy of the
   touched files (04 sits on 03).
2. The patched B3 ratings gate (03), run in memory on the committed s53 run files: every existing row and every metric
   must equal the committed margins.json; the new tank-CT rows are listed.
3. The patched heat-source generator (03, then 03 + 04), run in memory with its two output files redirected to the
   temporary directory: the R39-R46 rows.
4. The patched table tool (01 + 02) rendered in memory on the frozen s53 BOM with the patched tank_freq.h (B17 row),
   and the negative control: the patched table tool with the unpatched tank_freq.h must report a B17 finding.
Nothing is written under the repository except results/verify-patches.txt.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
PS = STUDY.parents[2]
REPO = PS.parents[1]
PATCHES = sorted((STUDY / "patches").glob("0*.patch"))
OUT = STUDY / "results/verify-patches.txt"
T = "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"


def touched(patch: Path) -> list[str]:
    return [l[6:].strip() for l in patch.read_text().splitlines() if l.startswith("+++ b/")]


def load_as(real: Path, src: str, name: str):
    """Execute src as if it were the file `real` (so its __file__-relative paths resolve into the repository)."""
    m = types.ModuleType(name)
    m.__file__ = str(real)
    sys.modules[name] = m
    exec(compile(src, str(real), "exec"), m.__dict__)
    return m


def run() -> str:
    L = []
    names = [p.name for p in PATCHES]
    assert names[:5] == ["01-bom-r44-r45-11k.patch", "02-firmware-peak-trip-max.patch", "03-b3-ct-network-rows.patch",
                         "04-b3-r39-heat-1to200.patch", "05-open-items-s29.patch"], names
    for p in PATCHES:
        if p.name.startswith("04"):
            continue
        r = subprocess.run(["git", "-C", str(REPO), "apply", "--check", str(p)], capture_output=True, text=True)
        L.append(f"git apply --check {p.name} (working tree): {'ok' if r.returncode == 0 else 'FAIL ' + r.stderr.strip()}")
    tmp = Path(tempfile.mkdtemp(prefix="c54-verify-"))
    try:
        tree = tmp / "tree"
        files = sorted({f for p in PATCHES for f in touched(p)})
        for f in files:
            (tree / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / f, tree / f)
        stages = {}
        for p in PATCHES:
            r = subprocess.run(["git", "apply", str(p)], cwd=tree, capture_output=True, text=True)
            L.append(f"git apply {p.name} (temporary copy, in sequence): {'ok' if r.returncode == 0 else 'FAIL ' + r.stderr.strip()}")
            stages[p.name[:2]] = {f: (tree / f).read_text() for f in files}

        # 2. patched gate on the committed runs
        gate_rel = f"{T}/b3-ratings/b3_ratings_gate.py"
        g = load_as(REPO / gate_rel, stages["03"][gate_rel], "c54_gate")
        out = g.run(REPO / T / "b3-ratings/runs", {c: b["bay_c"] for c, b in g.BASIS.items()})
        ref = json.loads((REPO / T / "b3-ratings/margins.json").read_text())
        L.append("")
        L.append("patched b3_ratings_gate.py on the committed s53 runs (board "
                 f"{sorted(set(out['board_sha256'].values()))[0][:12]}):")
        for c in out["cases"]:
            new = [r for r in out["cases"][c] if "tank-CT band" in r["item"]]
            old = [r for r in out["cases"][c] if "tank-CT band" not in r["item"]]
            same = sorted(json.dumps(r, sort_keys=True) for r in old) == sorted(json.dumps(r, sort_keys=True) for r in ref["cases"][c])
            L.append(f"  {c}: existing {len(old)} rows identical to margins.json: {same}; tank-CT rows (est / limit / margin):")
            for r in sorted(new, key=lambda r: r["item"]):
                L.append(f"    {r['item'].split(':')[0]} {r['est_c']:.1f} / {r['limit_c']:.1f} C / {r['margin_k']:+.1f} K  ({r['item'].split('; ')[-1][:-1]})")
        L.append(f"  metrics identical: {out['metrics'] == ref['metrics']}; pass {out['pass']} (committed {ref['pass']})")

        # 3. patched heat sources, outputs redirected
        mhs_rel = f"{T}/b3/make_heat_sources.py"
        orig = {r["ref"]: r for r in json.loads((REPO / T / "b3/inputs/native21-board-heat-sources.json").read_text())["parts"]}
        L.append("")
        L.append(f"heat rows (watts_nominal / watts_worst, mW); committed file: {len(orig)} parts, R39 "
                 f"{orig['R39']['watts_nominal'] * 1e3:.3f} / {orig['R39']['watts_worst'] * 1e3:.3f}")
        for tag in ("03", "04"):
            src = stages[tag][mhs_rel]
            assert src.count('HERE / "inputs"') == 4, "make_heat_sources output paths changed: redirect would miss"
            od = tmp / f"heat{tag}"
            src = src.replace('HERE / "inputs"', f'Path({str(od)!r})')
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                load_as(REPO / mhs_rel, src, f"c54_mhs{tag}")
            rows = {r["ref"]: r for r in json.loads((od / "native21-board-heat-sources.json").read_text())["parts"]}
            c28 = {r["ref"]: r for r in json.loads((od / "native21-board-heat-sources-c28.json").read_text())["parts"]}
            L.append(f"  after {tag}: {len(rows)} parts; " + "; ".join(
                f"{k} {rows[k]['watts_nominal'] * 1e3:.3f} / {rows[k]['watts_worst'] * 1e3:.3f}"
                for k in ("R39", "R40", "R41", "R43", "R44", "R45", "R46")) + f"; c28 R39 {c28['R39']['watts_nominal'] * 1e3:.3f}")
        tb_rel = f"{T}/b3-convergence/thermal_body.py"
        tb = load_as(REPO / tb_rel, stages["03"][tb_rel], "c54_tb")
        L.append(f"  thermal_body.spec_for(R44, RT0603BRD0710KL, R_0603) = {tb.spec_for('R44', 'RT0603BRD0710KL', 'Resistor_SMD:R_0603_1608Metric')}")

        # 4. table tool B17 row
        cbt_rel = "firmware/tools/commissioning_board_table.py"
        tf_rel = "firmware/components/power/include/tank_freq.h"
        L.append("")
        for label, tf in (("patched tank_freq.h (62.5 A)", tree / tf_rel), ("negative control: unpatched tank_freq.h (64.5 A)", REPO / tf_rel)):
            (tmp / "tf.h").write_text(tf.read_text() if tf != tree / tf_rel else stages["02"][tf_rel])
            src = stages["02"][cbt_rel].replace('TANK_FREQ_H = FIRMWARE / "components/power/include/tank_freq.h"',
                                                f'TANK_FREQ_H = Path({str(tmp / "tf.h")!r})')
            m = load_as(REPO / cbt_rel, src, "c54_cbt")
            block, findings = m.render()
            b17 = next(l for l in block.splitlines() if l.startswith("| B17"))
            L.append(f"table tool (01 + 02), {label}:")
            L.append(f"  {b17}")
            L.append(f"  findings on TANK_PEAK: {[f for f in findings if 'TANK_PEAK' in f]}")
    finally:
        shutil.rmtree(tmp)
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = run()
    if a.check:
        ok = OUT.exists() and OUT.read_text() == text
        print("PASS: verify-patches.txt reproduces" if ok else "FAIL: verify-patches.txt differs")
        return 0 if ok else 1
    OUT.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
