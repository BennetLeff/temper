# provenance: agent/hole-edge-placement-constraints, stacked on
# agent/per-pairing-placement-route @ bc3a19b06. Board sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
# verified unmodified before and after every run. See
# docs/evidence/2026-08-19-hole-geometry-placement-constraints.md
"""Dump kicad-cli DRC violations with descriptions AND attribute each to geometry.

Same staging contract as docs/evidence/2026-08-19-per-pairing-route-measure-board.py
(fp-lib-table + libs + regenerated DRU + single-thread KICAD_CONFIG_HOME).
Read-only with respect to pcb/.
"""
from __future__ import annotations
import argparse, collections, json, re, shutil, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--pcb", type=Path, required=True)
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--scratch", type=Path, required=True)
ap.add_argument("--types", default="")
ap.add_argument("--limit", type=int, default=25)
ap.add_argument("--json-out", type=Path, default=None)
args = ap.parse_args()

PCB_DIR = args.repo / "pcb"
sys.path.insert(0, str(args.repo / "scripts"))
from generate_kicad_dru import generate_dru
from temper_placer.validation._drc_api import _single_threaded_kicad_env

dst = args.scratch / ("detail_" + args.pcb.stem)
if dst.exists(): shutil.rmtree(dst)
dst.mkdir(parents=True)
shutil.copy(args.pcb, dst / "temper.kicad_pcb")
shutil.copy(PCB_DIR / "temper.kicad_pro", dst / "temper.kicad_pro")
shutil.copy(PCB_DIR / "fp-lib-table", dst / "fp-lib-table")
shutil.copytree(PCB_DIR / "libs", dst / "libs")
(dst / "temper.kicad_dru").write_text(generate_dru(), encoding="utf-8")

out = dst / "_drc.json"
with _single_threaded_kicad_env() as env:
    r = subprocess.run(["kicad-cli","pcb","drc","--all-track-errors","--format","json",
                        "--output",str(out),str(dst/"temper.kicad_pcb")],
                       capture_output=True, text=True, timeout=900, env=env)
if not out.exists():
    raise SystemExit(f"DRC failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
data = json.loads(out.read_text())
viols = data.get("violations", [])
print(f"{args.pcb.name}: {len(viols)} violations, "
      f"{len(data.get('unconnected_items',[]))} unconnected_items")
cats = collections.Counter(v["type"] for v in viols)
for c, n in cats.most_common():
    print(f"  {c:28s} {n}")
wanted = [t for t in args.types.split(",") if t]
for t in wanted:
    sel = [v for v in viols if v["type"] == t]
    print(f"\n--- {t}: {len(sel)} ---")
    for v in sel[:args.limit]:
        print(f"  [{v.get('severity','')}] {v.get('description','')}")
        for it in v.get("items", []):
            print(f"      * {it.get('description','')}  @ {it.get('pos',{})}")
if args.json_out:
    args.json_out.write_text(json.dumps(data), encoding="utf-8")
    print(f"\nwrote {args.json_out}")
"""Per-category, per-item attribution of a kicad-cli DRC JSON.

For each violation, classify the geometry it names:

  ROUTER-ONLY  every named item is copper the ROUTER emitted this run
               (Track / Via / Blind via / Zone / Polygon-on-Edge.Cuts)
  PAD-INVOLVED at least one named item is a footprint Pad (placement geometry)
  OTHER        footprint silkscreen/courtyard/library items etc.

A category whose violations are 100% ROUTER-ONLY cannot be fixed by moving
footprints in the placer, because no placement geometry appears in any of
them. This is a direct read of kicad-cli's own item descriptions.
"""


def classify_item(desc: str) -> str:
    d = desc.strip()
    if d.startswith("Pad "):
        return "pad"
    if re.match(r"^(Blind via|Micro via|Via|Track|Arc|Zone|Polygon|Rule Area)\b", d):
        return "router_or_board"
    return "other"


# --- per-item attribution -------------------------------------------------
by_cat = collections.defaultdict(collections.Counter)
for v in viols:
    kinds = {classify_item(it.get("description", "")) for it in v.get("items", [])}
    if not kinds:
        bucket = "OTHER"
    elif "pad" in kinds:
        bucket = "PAD-INVOLVED"
    elif kinds == {"router_or_board"}:
        bucket = "ROUTER-ONLY"
    else:
        bucket = "OTHER"
    by_cat[v["type"]][bucket] += 1
tot = collections.Counter({c: sum(b.values()) for c, b in by_cat.items()})
print(f"\n{'category':28s} {'total':>6s} {'ROUTER-ONLY':>12s} {'PAD-INVOLVED':>13s} {'OTHER':>7s}")
for cat, n in tot.most_common():
    b = by_cat[cat]
    print(f"{cat:28s} {n:6d} {b['ROUTER-ONLY']:12d} {b['PAD-INVOLVED']:13d} {b['OTHER']:7d}")
