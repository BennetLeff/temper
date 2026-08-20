# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""Measure one routed .kicad_pcb the way the 339/282 and 778/606 figures were.

Protocol lifted verbatim from scripts/measure_uncapped_drc.py's
`make_scratch_board` + `run_kicad_drc` (the repo's own kicad-cli contract):

  * scratch dir gets the board + temper.kicad_pro + fp-lib-table + libs/,
    all renamed/placed so kicad-cli's project-resolution-by-filename works
    (without fp-lib-table, lib_footprint_issues reads 168 instead of 13)
  * pcb/temper.kicad_dru is REGENERATED from scripts/generate_kicad_dru.py's
    `generate_dru()` in-process and written into the scratch dir -- the
    ci_check_drc.py protocol -- never into pcb/
  * `kicad-cli pcb drc --all-track-errors --format json` under a pinned
    single-thread KICAD_CONFIG_HOME

DRC violations  = len(data["violations"])      <- the 778 / 606 figure
unconnected_items = len(data["unconnected_items"])  <- the 339 / 282 figure
These are TWO DISJOINT TOP-LEVEL KEYS in kicad-cli's JSON. `_drc_api.run_drc`
parses only "violations", so its error_count does NOT include the ratsnest
count; conflating them is the mistake this script exists to avoid.

`--samples N` re-runs DRC N times on the same bytes, because this repo
documents a +-1 flicker in the creepage count on identical input. Any delta
must clear the observed spread.

Read-only with respect to every board and to pcb/.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PCB_DIR: Path


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def layer_segment_counts(text: str) -> dict[str, int]:
    counts: collections.Counter = collections.Counter()
    for block in text.split("(segment ")[1:]:
        m = re.search(r"\(layer\s+\"?([A-Za-z0-9._]+)\"?\s*\)", block[:400])
        if m:
            counts[m.group(1)] += 1
    return dict(sorted(counts.items()))


def run_drc_raw(board_dir: Path, tag: str) -> dict:
    """kicad-cli DRC under the repo's OWN single-thread env helper.

    `_single_threaded_kicad_env` seeds its throwaway KICAD_CONFIG_HOME from
    the real user settings tree, so `kicad_common.json` -- and with it
    `${KICAD10_FOOTPRINT_DIR}`, which pcb/fp-lib-table's every uri expands
    through -- still resolves. A bare empty KICAD_CONFIG_HOME does NOT:
    every library fails to load and `lib_footprint_issues` reads ~165
    instead of 13, inflating the violation total by an amount that has
    nothing to do with the board.
    """
    from temper_placer.validation._drc_api import _single_threaded_kicad_env

    out = board_dir / "_drc_out.json"
    with _single_threaded_kicad_env() as env:
        r = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--all-track-errors", "--format", "json",
             "--output", str(out), str(board_dir / "temper.kicad_pcb")],
            capture_output=True, text=True, timeout=900,
            env=env if env is not None else None,
        )
    if not out.exists():
        raise RuntimeError(f"kicad-cli DRC failed (exit {r.returncode})\n"
                           f"{r.stdout}\n{r.stderr}")
    data = json.loads(out.read_text())
    out.unlink(missing_ok=True)
    return data


def stage(board: Path, dst: Path, dru_text: str) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(board, dst / "temper.kicad_pcb")
    shutil.copy(PCB_DIR / "temper.kicad_pro", dst / "temper.kicad_pro")
    shutil.copy(PCB_DIR / "fp-lib-table", dst / "fp-lib-table")
    if not (dst / "libs").exists():
        shutil.copytree(PCB_DIR / "libs", dst / "libs")
    (dst / "temper.kicad_dru").write_text(dru_text, encoding="utf-8")
    return dst / "temper.kicad_pcb"


def main() -> None:
    global PCB_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--scratch", type=Path, required=True)
    args = ap.parse_args()

    PCB_DIR = args.repo / "pcb"
    sys.path.insert(0, str(args.repo / "scripts"))
    from generate_kicad_dru import generate_dru

    dru_text = generate_dru()
    print(f"regenerated DRU: {len(dru_text.splitlines())} lines "
          f"(in-process; pcb/temper.kicad_dru not written)")

    text = args.pcb.read_text(encoding="utf-8")
    out: dict = {
        "label": args.label,
        "pcb": str(args.pcb),
        "sha256": sha256(args.pcb),
        "segments": text.count("(segment "),
        "vias": text.count("(via "),
        "zones": text.count("(zone "),
        "layer_segments": layer_segment_counts(text),
    }

    tag = args.label.replace("/", "_") or "run"
    board_dir = args.scratch / f"drc_{tag}"
    if board_dir.exists():
        shutil.rmtree(board_dir)
    stage(args.pcb, board_dir, dru_text)

    samples = []
    for i in range(args.samples):
        d = run_drc_raw(board_dir, f"{tag}_{i}")
        cats = collections.Counter(v["type"] for v in d.get("violations", []))
        unconn = d.get("unconnected_items", [])
        unconn_nets: collections.Counter = collections.Counter()
        for u in unconn:
            for it in u.get("items", []):
                m = re.search(r"\[([^\]]+)\]", it.get("description", "") or "")
                if m:
                    unconn_nets[m.group(1)] += 1
        samples.append({
            "violations": len(d.get("violations", [])),
            "unconnected_items": len(unconn),
            "by_category": dict(cats),
            "unconnected_by_net": dict(unconn_nets.most_common()),
        })

    out["samples"] = samples
    out["violations"] = [s["violations"] for s in samples]
    out["unconnected"] = [s["unconnected_items"] for s in samples]
    out["by_category"] = samples[-1]["by_category"]
    out["unconnected_by_net"] = samples[-1]["unconnected_by_net"]

    print(f"\n=== {args.label or args.pcb} ===")
    print(f"sha256           {out['sha256']}")
    print(f"segments {out['segments']}  vias {out['vias']}  zones {out['zones']}")
    print(f"layer segments   {json.dumps(out['layer_segments'])}")
    print(f"DRC violations   {out['violations']}  (n={args.samples} samples)")
    print(f"unconnected_items{out['unconnected']}")
    print("per-category (last sample):")
    for cat, n in collections.Counter(out["by_category"]).most_common():
        print(f"  {cat:28s} {n}")
    print("unconnected_items by net (top 15, last sample):")
    for net, n in list(out["unconnected_by_net"].items())[:15]:
        print(f"  {net:28s} {n}")

    if args.json_out:
        args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
