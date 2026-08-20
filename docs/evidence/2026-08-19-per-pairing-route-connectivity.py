# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""Post-hoc connectivity census of a routed board.

Reproduces, from `--board` alone, the two connectivity metrics in the brief:

  * "nets with >=2 pins fully pad-connected"  (baseline 60/139)
  * "nets with zero copper emitted"           (baseline 63)

Both are pure `pad_connectivity_audit.audit_pcb_file` post-processing, using
the SAME partition as
`git show origin/analysis/mechanism-a-zero-copper:docs/evidence/2026-08-19-mechanism-a-analyze.py`
section 2:

    multi = pad_count >= 2
    zero  = multi and not has_any_copper
    A     = zero  and not zone_layers      <- the "63"

Read-only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    audit = audit_pcb_file(args.board)

    multi = {n: r for n, r in audit.items() if r.pad_count >= 2}
    with_copper = {n: r for n, r in multi.items() if r.has_any_copper}
    fully = {n: r for n, r in multi.items() if r.fully_connected}
    zero = {n: r for n, r in multi.items() if not r.has_any_copper}
    a_set = {n: r for n, r in zero.items() if not r.zone_layers}

    pads_total = sum(r.pad_count for r in multi.values())
    pads_conn = sum(r.pads_connected for r in multi.values())

    # route_board.py's headline "N/139 nets fully pad-connected" counts EVERY
    # audited net, including the 27 single-pad nets that are vacuously
    # connected. Reported separately from the >=2-pad figure so the brief's
    # 60/139 and the mechanism-A tables can both be read off one run.
    fully_all = {n: r for n, r in audit.items() if r.fully_connected}

    out = {
        "label": args.label,
        "board": str(args.board),
        "nets_total": len(audit),
        "nets_multi_pad": len(multi),
        "nets_with_copper": len(with_copper),
        "nets_fully_pad_connected": len(fully),
        "nets_fully_pad_connected_all_nets": len(fully_all),
        "nets_zero_copper": len(zero),
        "nets_zero_copper_zero_zone": len(a_set),
        "pads_connected": pads_conn,
        "pads_total": pads_total,
        "zero_copper_nets": sorted(zero),
        "zero_copper_zero_zone_nets": sorted(a_set),
    }

    print(f"=== {args.label or args.board} ===")
    print(f"nets (all)                        {out['nets_total']}")
    print(f"  fully pad-connected (ALL nets)  "
          f"{out['nets_fully_pad_connected_all_nets']}/{out['nets_total']}"
          f"   <- route_board.py's headline convention")
    print(f"nets with >=2 pads                {out['nets_multi_pad']}")
    print(f"  fully pad-connected             {out['nets_fully_pad_connected']}"
          f"/{out['nets_multi_pad']}")
    print(f"  carrying segment/via copper     {out['nets_with_copper']}")
    print(f"  ZERO segment/via copper         {out['nets_zero_copper']}")
    print(f"  ZERO copper AND ZERO zone       {out['nets_zero_copper_zero_zone']}")
    print(f"pads connected                    {out['pads_connected']}/{out['pads_total']}")

    if args.json_out:
        args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
