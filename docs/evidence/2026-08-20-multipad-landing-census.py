"""Pad-level connectivity census of a routed board, with the terminus vs
intermediate split that the terminus-only-landing defect predicts.

Reports, over the >=2-pad nets:

  * ``pads_connected`` / ``pads_total`` -- the established metric of
    docs/evidence/2026-08-19-per-pairing-route-connectivity.py (baselines
    171/496 committed, 215/496 model-E), kept so this census is directly
    comparable with the published figures.
  * **pads UNREACHED** = ``sum(pad_count - pads_connected)`` -- the number
    this task is actually about: pads the net's own segment+via copper does
    not join to the net's largest pad group.
  * the same, restricted to nets the router reported as ROUTED (has copper),
    because a pad on a net with no copper at all is a different mechanism.
  * for every net with copper and >2 pads, whether each unreached pad is a
    route TERMINUS or an INTERMEDIATE pad. Terminus/intermediate is decided
    from the route's own first/last emitted point (from the landing trace
    written by 2026-08-20-multipad-landing-route.py) when a trace is given,
    and otherwise from the net's own copper endpoints.

Read-only.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--board", required=True, type=Path)
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--trace", default=None, type=Path)
ap.add_argument("--label", default="")
ap.add_argument("--json-out", default=None, type=Path)
args = ap.parse_args()

import sys  # noqa: E402

sys.path.insert(0, str(args.repo / "packages" / "temper-placer" / "src"))
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file  # noqa: E402

audit = audit_pcb_file(args.board)
multi = {n: r for n, r in audit.items() if r.pad_count >= 2}
copper = {n: r for n, r in multi.items() if r.has_any_copper}

pads_total = sum(r.pad_count for r in multi.values())
pads_conn = sum(r.pads_connected for r in multi.values())
pads_unreached = pads_total - pads_conn

c_total = sum(r.pad_count for r in copper.values())
c_conn = sum(r.pads_connected for r in copper.values())

TRACE = json.loads(args.trace.read_text()) if args.trace else {"nets": {}}


def terminus_points(net: str) -> list[tuple[float, float]]:
    recs = TRACE.get("nets", {}).get(net) or []
    if not recs:
        return []
    rec = recs[-1]
    pts = []
    for key in ("first", "last"):
        v = rec.get(key)
        if v:
            pts.append((round(v[0], 3), round(v[1], 3)))
    return pts


role_rows = []
role = Counter()
for net, r in sorted(copper.items()):
    if r.pad_count <= 2:
        continue
    terms = terminus_points(net)
    unreached = {(round(p.position[0], 3), round(p.position[1], 3)) for p in r.unreached_pads}
    # Pad positions come from the same audit parse, so they compare exactly.
    for pad in r.unreached_pads:
        key = (round(pad.position[0], 3), round(pad.position[1], 3))
        role["unreached_TERMINUS" if key in terms else "unreached_INTERMEDIATE"] += 1
    n_term_reached = sum(1 for t in terms if t not in unreached)
    role_rows.append(
        {
            "net": net,
            "pads": r.pad_count,
            "connected": r.pads_connected,
            "unreached": r.pad_count - r.pads_connected,
            "n_terminus_pts": len(terms),
            "terminus_reached": n_term_reached,
        }
    )

fully = {n: r for n, r in multi.items() if r.fully_connected}
fully_all = {n: r for n, r in audit.items() if r.fully_connected}
zero = {n: r for n, r in multi.items() if not r.has_any_copper}
fake = {n: r for n, r in copper.items() if not r.fully_connected}

out = {
    "label": args.label,
    "board": str(args.board),
    "nets_total": len(audit),
    "nets_multi_pad": len(multi),
    "nets_fully_pad_connected": len(fully),
    "nets_fully_pad_connected_all_nets": len(fully_all),
    "nets_with_copper": len(copper),
    "nets_zero_copper": len(zero),
    "nets_copper_but_not_fully_connected": len(fake),
    "pads_total": pads_total,
    "pads_connected": pads_conn,
    "pads_unreached": pads_unreached,
    "pads_total_on_copper_nets": c_total,
    "pads_connected_on_copper_nets": c_conn,
    "pads_unreached_on_copper_nets": c_total - c_conn,
    "unreached_role_split": dict(role),
    "per_net_gt2": role_rows,
    "fake_completions": {
        n: [r.pads_connected, r.pad_count] for n, r in sorted(fake.items())
    },
}

print(f"=== {args.label or args.board} ===")
print(f"nets (all) {out['nets_total']}  fully connected (all) "
      f"{out['nets_fully_pad_connected_all_nets']}/{out['nets_total']}")
print(f"nets >=2 pads {out['nets_multi_pad']}  fully connected "
      f"{out['nets_fully_pad_connected']}/{out['nets_multi_pad']}")
print(f"nets with copper {out['nets_with_copper']}  of which NOT fully connected "
      f"{out['nets_copper_but_not_fully_connected']}")
print(f"pads connected {pads_conn}/{pads_total}   PADS UNREACHED {pads_unreached}")
print(f"  on copper-carrying nets: {c_conn}/{c_total}  UNREACHED "
      f"{c_total - c_conn}")
print(f"unreached role split (nets with copper and >2 pads): {dict(role)}")
print("\nper-net (copper, >2 pads):")
for row in role_rows:
    print(f"  {row['net']:34s} {row['connected']:3d}/{row['pads']:<3d} "
          f"unreached={row['unreached']:<3d} terminus_pts={row['n_terminus_pts']} "
          f"terminus_reached={row['terminus_reached']}")

if args.json_out:
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {args.json_out}")
