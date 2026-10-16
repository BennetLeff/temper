#!/usr/bin/env python3
"""Scoped chain: re-run only the steps whose inputs changed against a benchmark build, reuse the rest by content key.

    python3 -I scoped_chain.py classify --bench-ref REF                          # input classes + provisional plan
    python3 -I scoped_chain.py run TAG PASSDIR BUILDDIR --bench-build DIR [--bench-ref REF] [--dry-run]
    python3 -I scoped_chain.py card --plan BUILDDIR/scoped-plan.json --fresh CARD.json --bench-card BENCH.json --out OUT.json
    python3 -I scoped_chain.py manifest BUILDDIR TAG          # chain.sh calls this last: the build's keys, for later reuse
    python3 -I scoped_chain.py decide BUILDDIR PLAN.json      # chain.sh calls this in scoped mode, after copper_key

The benchmark is a full-chain build (BENCH_BUILD with its scoped-manifest.json) and the git commit it was built from
(--bench-ref, default: the manifest's git_head). The candidate is this working tree.

Decision rules (depmap.json carries the step table and the path rules):
  1. Every changed path is classified. A path no rule knows, a stackup change or a change to the chain itself
     -> FULL: chain.sh runs unscoped.
  2. A changed board input (frozen netlist / BOM, layout, copper.json, placement, rules, libraries) -> the board is
     rebuilt, and every safety gate and export runs on it (DRC, barrier, D5, DFM, bypass, RES_A, PI, return path, spine,
     fit, fab, Kelvin). With no board input changed the benchmark build is reused (same board_sha256) and only the
     steps whose own scripts changed rerun, plus every cheap step.
  3. The expensive thermal steps (task 04, B3, ceiling sweep, B3 ratings) run only when their content key differs from
     the benchmark manifest's: canonical copper key + the step's files (scripts, heat inputs, stack-up, firmware
     header) + upstream keys. On a rebuilt board B3 forces task 04 (thermal.py's same-board check).
  4. Manual card inputs (F1 necks, OCP pickup, audit.rs) are carried from the benchmark card while their key holds;
     otherwise the scoped card marks them STALE and the verdict is not final.
The scoped card names, per entry, recomputed / reused (with the key) / stale. The full chain stays mandatory at merge.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoped_lib as L  # noqa: E402

KP = os.environ.get("KICAD_PY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
R5 = L.UNIT / "validation-results/04-board-current-thermal/round5-native21"
BARRIER_BIN = os.environ.get("ZAPOTE_POWER_BARRIER_BIN", "/Users/bennet/Desktop/temper/target-shared/debug/zapote-power-barrier")


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "-"


def npz_sha() -> str:      # as regate.sh computes it
    h = hashlib.sha256()
    for f in sorted(glob.glob(str(R5 / "outputs/*.npz"))):
        h.update(open(f, "rb").read())
    return h.hexdigest()


def board_keys(build: Path) -> dict:
    out = build / "net-keys.json"
    if not out.exists() or json.loads(out.read_text()).get("board_sha256") != sha_file(build / "section.kicad_pcb"):
        subprocess.run([KP, str(Path(__file__).resolve().parent / "net_keys.py"), str(build / "section.kicad_pcb"), str(out)],
                       check=True, capture_output=True)
    return json.loads(out.read_text())


def extra() -> dict:
    return {"sheet_barrel": os.environ.get("SHEET_BARREL", ""), "barrier_bin": sha_file(Path(BARRIER_BIN))}


def cmd_manifest(a):
    b = Path(a.build).resolve()
    nk = board_keys(b)
    sk = L.step_keys(L.Tree(None), nk, extra())
    head = subprocess.run(["git", "-C", str(L.REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(L.REPO), "status", "--porcelain", "--", L.PS], capture_output=True, text=True).stdout
    m = {"schema": "native21.scoped-manifest.v1", "tag": a.tag, "build": str(b), "board_sha256": nk["board_sha256"],
         "full_chain": not os.environ.get("SCOPED_PLAN"),
         "copper_key": nk["copper_key"], "copper_key_canonical": nk["copper_key_canonical"],
         "git_head": head, "git_dirty_paths": [x[3:] for x in dirty.split("\n") if x],
         "keys": sk["keys"], "step_files": sk["files"], "npz_sha256": npz_sha(),
         "margins_board": json.loads((R5 / "b3-ratings/margins.json").read_text()).get("board_sha256")
         if (R5 / "b3-ratings/margins.json").exists() else None,
         "net_keys": str(b / "net-keys.json")}
    (b / "scoped-manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    print(f"scoped manifest: {b / 'scoped-manifest.json'} (board {nk['board_sha256'][:12]}, copper {nk['copper_key_canonical'][:12]})")


def provisional(bench_ref: str) -> dict:
    paths = L.changed_paths(L.Tree(bench_ref), L.Tree(None))
    return L.plan(paths, None, None, None), paths


def cmd_classify(a):
    pl, paths = provisional(a.bench_ref)
    print(f"mode {pl['mode']}; {len(paths)} changed paths")
    print("classes:", "; ".join(L.input_classes(pl["by_class"], None, [])))
    for c, ps in sorted(pl["by_class"].items()):
        print(f"  {c}: {len(ps)}", ", ".join(sorted(ps))[:300])
    for s, d in pl["steps"].items():
        print(f"  {d['do']:6s} {s:15s} {d['why'][:110]}")


def finalize(pl: dict, build: Path, bench: dict) -> dict:
    """Post-build: keyed / manual decisions from the candidate's keys against the benchmark manifest, plus the local
    artefacts a reuse needs (the task-04 heat files are gitignored; a reuse needs the ones the manifest names)."""
    nk = board_keys(build)
    sk = L.step_keys(L.Tree(None), nk, extra())
    rebuilt = nk["board_sha256"] != bench["board_sha256"]
    bd = None
    if Path(bench["net_keys"]).exists():
        bd = L.board_diff(json.loads(Path(bench["net_keys"]).read_text()), nk)
    paths = [p for c in pl["by_class"].values() for p in c]
    new = L.plan(paths, bench["keys"], sk["keys"], bd, rebuilt_board_differs=rebuilt, cand_tag=pl.get("tag"))
    if new["steps"]["task04"]["do"] == "REUSE" and npz_sha() != bench["npz_sha256"]:
        new["steps"]["task04"] = {"do": "RUN", "why": "task-04 key holds but the local outputs/*.npz are not the manifest's"}
    if new["steps"]["b3_ratings"]["do"] == "REUSE":
        mb = json.loads((R5 / "b3-ratings/margins.json").read_text()).get("board_sha256") if (R5 / "b3-ratings/margins.json").exists() else None
        if mb != bench.get("margins_board"):
            new["steps"]["b3_ratings"] = {"do": "RUN", "why": "ratings key holds but margins.json is not the benchmark's"}
    if new["steps"]["b3_study"]["do"] != "REUSE" and new["steps"]["task04"]["do"] == "REUSE" and rebuilt:
        new["steps"]["task04"] = {"do": "RUN", "why": "forced: B3 recomputes on a rebuilt board (same-board check)"}
    new["candidate_keys"], new["benchmark_keys"] = sk["keys"], bench["keys"]
    new["board_diff"] = bd
    new["input_classes"] = L.input_classes(new["by_class"], bd, [])
    new["benchmark"] = {k: bench[k] for k in ("tag", "build", "board_sha256", "git_head")}
    return new


def cmd_decide(a):
    p = Path(a.plan)
    pl = json.loads(p.read_text())
    bench = json.loads(Path(pl["bench_manifest"]).read_text())
    # B3's heat inputs are key inputs: generate them first (cheap, as the thermal block does)
    subprocess.run([sys.executable, "make_heat_sources.py"], cwd=R5 / "b3", check=True, capture_output=True)
    new = finalize(pl, Path(a.build).resolve(), bench)
    new["bench_manifest"], new["tag"] = pl["bench_manifest"], pl.get("tag")
    p.write_text(json.dumps(new, indent=1) + "\n")
    for s in L.KEYED + ["necks", "ocp_pickup", "audit_rs"]:
        d = new["steps"][s]
        print(f"scoped {d['do']:6s} {s:14s} {d['why'][:100]}" + (f" [{d['proof'][:12]}]" if d.get("proof") else ""))


def cmd_run(a):
    bench_build = Path(a.bench_build).resolve()
    man = bench_build / "scoped-manifest.json"
    if not man.exists():
        raise SystemExit(f"{man}: no manifest (the benchmark must be a full chain.sh build of this version)")
    bench = json.loads(man.read_text())
    if not bench.get("full_chain") and not a.allow_scoped_bench:
        raise SystemExit(f"{man}: the benchmark is a scoped build; benchmark against a full-chain build (or --allow-scoped-bench)")
    if bench.get("git_dirty_paths"):
        print("note: the benchmark was built from a dirty tree:", ", ".join(bench["git_dirty_paths"])[:200])
    ref = a.bench_ref or bench["git_head"]
    pl, paths = provisional(ref)
    pl["bench_manifest"] = str(man)
    pl["tag"] = a.tag
    b = Path(a.build).resolve()
    print(f"scoped: mode {pl['mode']} against {bench['tag']} ({ref[:12]}); {len(paths)} changed paths")
    print("  classes:", "; ".join(L.input_classes(pl["by_class"], None, [])))
    chain = Path(__file__).resolve().parents[1] / "chain.sh"
    env = dict(os.environ)
    for s, d in pl["steps"].items():
        print(f"  {d['do']:6s} {s:15s} {d['why'][:110]}")
    if a.dry_run:
        return
    if pl["mode"] != "FULL":
        if pl["mode"] == "REUSE-BUILD":
            if b.exists():
                raise SystemExit(f"{b} exists; the scoped run copies the benchmark build there")
            shutil.copytree(bench_build, b, symlinks=True)
            if sha_file(b / "section.kicad_pcb") != bench["board_sha256"]:
                raise SystemExit("benchmark build's board is not the manifest's")
        b.mkdir(parents=True, exist_ok=True)
        (b / "scoped-plan.json").write_text(json.dumps(pl, indent=1) + "\n")
        env["SCOPED_PLAN"] = str(b / "scoped-plan.json")
    r = subprocess.run(["sh", str(chain), a.tag, a.passdir, str(b)], env=env)
    raise SystemExit(r.returncode)


def cmd_card(a):
    pl = json.loads(Path(a.plan).read_text())
    out = L.scoped_card(json.loads(Path(a.fresh).read_text()), json.loads(Path(a.bench_card).read_text()), pl)
    out["scoped"]["input_classes"] = pl.get("input_classes")
    out["scoped"]["final"] = not out["scoped"]["stale"] and pl["mode"] != "FULL"
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    sc = out["scoped"]
    print(f"scoped card: {len(sc['recomputed'])} recomputed, {len(sc['reused'])} reused, {len(sc['stale'])} stale"
          + ("" if not sc["stale"] else " -> NOT FINAL: " + ", ".join(sc["stale"])))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("classify"); p.add_argument("--bench-ref", required=True); p.set_defaults(f=cmd_classify)
    p = sp.add_parser("run"); p.add_argument("tag"); p.add_argument("passdir"); p.add_argument("build")
    p.add_argument("--bench-build", required=True); p.add_argument("--bench-ref"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-scoped-bench", action="store_true")
    p.set_defaults(f=cmd_run)
    p = sp.add_parser("card"); p.add_argument("--plan", required=True); p.add_argument("--fresh", required=True)
    p.add_argument("--bench-card", required=True); p.add_argument("--out", required=True); p.set_defaults(f=cmd_card)
    p = sp.add_parser("manifest"); p.add_argument("build"); p.add_argument("tag"); p.set_defaults(f=cmd_manifest)
    p = sp.add_parser("decide"); p.add_argument("build"); p.add_argument("plan"); p.set_defaults(f=cmd_decide)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
