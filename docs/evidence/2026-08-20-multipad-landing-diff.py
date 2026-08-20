"""Net-level and pad-level diff between two routed boards.

Answers the two questions the multi-pad landing fix has to answer together:
how many pads it attaches, and how many pads any OTHER net loses because the
extra landing copper claims a cell a later net needed (the router is
fail-closed with no rip-up, so more copper can block later nets).

Read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--before", required=True, type=Path)
ap.add_argument("--after", required=True, type=Path)
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--label", default="")
ap.add_argument("--json-out", default=None, type=Path)
args = ap.parse_args()

sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file  # noqa: E402

A = audit_pcb_file(args.before)
B = audit_pcb_file(args.after)

nets = sorted(set(A) | set(B))
gained: list[tuple[str, int, int, int]] = []
lost: list[tuple[str, int, int, int]] = []
for n in nets:
    a, b = A.get(n), B.get(n)
    if a is None or b is None or a.pad_count < 2:
        continue
    if b.pads_connected > a.pads_connected:
        gained.append((n, a.pads_connected, b.pads_connected, a.pad_count))
    elif b.pads_connected < a.pads_connected:
        lost.append((n, a.pads_connected, b.pads_connected, a.pad_count))


def totals(audit):
    multi = [r for r in audit.values() if r.pad_count >= 2]
    return {
        "pads_total": sum(r.pad_count for r in multi),
        "pads_connected": sum(r.pads_connected for r in multi),
        "nets_fully_connected_multi": sum(1 for r in multi if r.fully_connected),
        "nets_fully_connected_all": sum(1 for r in audit.values() if r.fully_connected),
        "nets_with_copper": sum(1 for r in multi if r.has_any_copper),
        "nets_zero_copper": sum(1 for r in multi if not r.has_any_copper),
    }


ta, tb = totals(A), totals(B)
out = {
    "label": args.label,
    "before": {"board": str(args.before), **ta},
    "after": {"board": str(args.after), **tb},
    "pads_gained": sum(g[2] - g[1] for g in gained),
    "pads_lost": sum(lo[1] - lo[2] for lo in lost),
    "nets_gained": [
        {"net": n, "before": x, "after": y, "pads": p} for n, x, y, p in gained
    ],
    "nets_lost": [{"net": n, "before": x, "after": y, "pads": p} for n, x, y, p in lost],
}

print(f"=== {args.label} ===")
for k in ta:
    print(f"  {k:32s} {ta[k]:5d} -> {tb[k]:5d}   ({tb[k] - ta[k]:+d})")
print(f"\nNETS THAT GAINED PADS ({len(gained)}, +{out['pads_gained']} pads):")
for n, x, y, p in gained:
    print(f"  {n:34s} {x:3d} -> {y:3d}  / {p}")
print(f"\nNETS THAT LOST PADS ({len(lost)}, -{out['pads_lost']} pads):")
for n, x, y, p in lost:
    print(f"  {n:34s} {x:3d} -> {y:3d}  / {p}")
print(f"\nNET PAD EFFECT: {out['pads_gained'] - out['pads_lost']:+d}")

if args.json_out:
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.json_out}")
