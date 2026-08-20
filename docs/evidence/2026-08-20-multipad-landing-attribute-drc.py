"""Attribute a routed board's DRC violations to the vias that are NEW
relative to a baseline board.

The multi-pad landing fix adds one via per landed intermediate pad. Those
vias must not buy connectivity with a clearance violation, so this asks the
question directly rather than inferring it from a total: run kicad-cli DRC on
both boards, take the set of vias present in AFTER but not in BEFORE, and
report how many violations have an item within ``--radius`` mm of one.

Read-only. Uses the same staging + DRU-regeneration protocol as
docs/evidence/2026-08-19-per-pairing-route-measure-board.py.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--before", required=True, type=Path)
ap.add_argument("--after", required=True, type=Path)
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--scratch", required=True, type=Path)
ap.add_argument("--radius", type=float, default=1.0)
ap.add_argument("--json-out", default=None, type=Path)
args = ap.parse_args()

sys.path.insert(0, str(args.repo / "scripts"))
sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
from generate_kicad_dru import generate_dru  # noqa: E402

PCB_DIR = args.repo / "pcb"

VIA_RE = re.compile(
    r"\(via[^\n]*?\(at ([\d.eE+-]+) ([\d.eE+-]+)\)[^\n]*?\(layers \"([^\"]+)\" \"([^\"]+)\"\)"
    r"[^\n]*?\(net (\d+)\)"
)


def vias(path: Path) -> collections.Counter:
    out: collections.Counter = collections.Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if "(via " not in line:
            continue
        m = VIA_RE.search(line)
        if m:
            out[
                (round(float(m.group(1)), 3), round(float(m.group(2)), 3),
                 m.group(3), m.group(4), int(m.group(5)))
            ] += 1
    return out


def stage(board: Path, dst: Path, dru_text: str) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(board, dst / "temper.kicad_pcb")
    shutil.copy(PCB_DIR / "temper.kicad_pro", dst / "temper.kicad_pro")
    shutil.copy(PCB_DIR / "fp-lib-table", dst / "fp-lib-table")
    shutil.copytree(PCB_DIR / "libs", dst / "libs")
    (dst / "temper.kicad_dru").write_text(dru_text, encoding="utf-8")


def drc(board_dir: Path) -> dict:
    from temper_placer.validation._drc_api import _single_threaded_kicad_env

    out = board_dir / "_drc.json"
    with _single_threaded_kicad_env() as env:
        subprocess.run(
            ["kicad-cli", "pcb", "drc", "--all-track-errors", "--format", "json",
             "--output", str(out), str(board_dir / "temper.kicad_pcb")],
            capture_output=True, text=True, timeout=900,
            env=env if env is not None else None,
        )
    return json.loads(out.read_text())


def items(v: dict) -> list[tuple[float, float]]:
    pts = []
    for it in v.get("items", []):
        pos = it.get("pos") or {}
        if "x" in pos and "y" in pos:
            pts.append((float(pos["x"]), float(pos["y"])))
    return pts


dru_text = generate_dru()
reports = {}
for label, board in (("before", args.before), ("after", args.after)):
    d = args.scratch / f"attr_{label}"
    stage(board, d, dru_text)
    reports[label] = drc(d)

before_vias, after_vias = vias(args.before), vias(args.after)
new_vias = sorted((after_vias - before_vias).elements())
gone_vias = sorted((before_vias - after_vias).elements())

print(f"vias before={sum(before_vias.values())} after={sum(after_vias.values())}")
print(f"NEW vias ({len(new_vias)}):")
for x, y, l1, l2, net in new_vias:
    print(f"  ({x:9.4f}, {y:9.4f})  {l1:6s} -> {l2:6s}  net {net}")
print(f"vias present before but gone after: {len(gone_vias)}")

r2 = args.radius ** 2


def attribute(report: dict) -> tuple[collections.Counter, collections.Counter]:
    near: collections.Counter = collections.Counter()
    far: collections.Counter = collections.Counter()
    for v in report.get("violations", []):
        pts = items(v)
        hit = any(
            (px - x) ** 2 + (py - y) ** 2 <= r2
            for px, py in pts
            for x, y, _l1, _l2, _n in new_vias
        )
        (near if hit else far)[v["type"]] += 1
    return near, far


out: dict = {
    "new_vias": [
        {"x": x, "y": y, "from": l1, "to": l2, "net": n} for x, y, l1, l2, n in new_vias
    ],
    "vias_before": sum(before_vias.values()),
    "vias_after": sum(after_vias.values()),
    "radius_mm": args.radius,
}
for label in ("before", "after"):
    near, far = attribute(reports[label])
    total = collections.Counter(v["type"] for v in reports[label].get("violations", []))
    out[label] = {
        "total": sum(total.values()),
        "by_category": dict(total.most_common()),
        "near_new_via_positions": dict(near.most_common()),
        "near_total": sum(near.values()),
        "unconnected_items": len(reports[label].get("unconnected_items", [])),
    }
    print(
        f"\n{label}: {sum(total.values())} violations, "
        f"{sum(near.values())} of them with an item within {args.radius}mm of a "
        f"NEW via position"
    )
    for k, v in near.most_common():
        print(f"    near: {k:26s} {v}")

delta_near = out["after"]["near_total"] - out["before"]["near_total"]
delta_total = out["after"]["total"] - out["before"]["total"]
print(
    f"\nDRC total {out['before']['total']} -> {out['after']['total']} "
    f"({delta_total:+d}); of that, {delta_near:+d} sits within {args.radius}mm of a "
    f"new landing via and {delta_total - delta_near:+d} does not."
)
out["delta_total"] = delta_total
out["delta_near"] = delta_near

if args.json_out:
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.json_out}")
