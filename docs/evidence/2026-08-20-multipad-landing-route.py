"""Route one board through ``route_board.route_once`` (every default) and
record, per net, what the pad-layer landing pass actually saw.

Observe-only with respect to routing: the single monkeypatch wraps
``_astar_nlayer._attempt_pad_layer_landing`` and forwards its arguments and
return value unchanged, recording the net's pads, the route's emitted
endpoints and the vias the landing pass inserted. Used to measure the
terminus-only-landing defect before a fix and the same numbers after it, on
the same two placements.

Read-only with respect to ``pcb/temper.kicad_pcb`` (route_once strips copper
into a temp file; the board is only ever read).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--repo", required=True, type=Path)
ap.add_argument("--pcb", default=None, type=Path)
ap.add_argument("--board-out", required=True, type=Path)
ap.add_argument("--trace-out", required=True, type=Path)
args = ap.parse_args()

sys.path.insert(0, str(args.repo / "scripts"))

TRACE: dict = {"nets": {}}


def _install():
    from temper_placer.router_v6 import _astar_nlayer as N

    orig = N._attempt_pad_layer_landing

    def probe(net_name, route_path, pad_centers_per_net, grids, tolerance_mm=0.05, **kw):
        attempted, blocked = orig(
            net_name, route_path, pad_centers_per_net, grids, tolerance_mm, **kw
        )
        pads = pad_centers_per_net.get(net_name) or []
        before_vias = list(route_path.via_positions or ())
        after_vias = list(attempted.via_positions or ())
        segs = list(route_path.segments or ())
        # The vias this pass added, split into the two ends (which the pass
        # has always handled) and the interior pads (the 2026-08-20 fix).
        # A terminus insertion goes to index 0 / the end of via_positions;
        # every interior one is appended after those, and its position is
        # the pad centre.
        terminus_pts = set()
        if segs:
            terminus_pts = {
                (round(segs[0][0], 4), round(segs[0][1], 4)),
                (round(segs[-1][0], 4), round(segs[-1][1], 4)),
            }
        before_ct: dict = {}
        for v in before_vias:
            before_ct[(round(v[0], 4), round(v[1], 4))] = (
                before_ct.get((round(v[0], 4), round(v[1], 4)), 0) + 1
            )
        added = []
        for v in after_vias:
            key = (round(v[0], 4), round(v[1], 4))
            if before_ct.get(key):
                before_ct[key] -= 1
                continue
            added.append(key)
        rec = {
            "n_pads": len(pads),
            "pads": [[round(p[0], 4), round(p[1], 4), p[3]] for p in pads],
            "n_segments": len(segs),
            "first": list(segs[0]) if segs else None,
            "last": list(segs[-1]) if segs else None,
            "vias_before": len(before_vias),
            "vias_after": len(after_vias),
            "vias_added": added,
            "vias_added_interior": [p for p in added if p not in terminus_pts],
            "blocked": list(blocked),
        }
        TRACE["nets"].setdefault(net_name, []).append(rec)
        return attempted, blocked

    N._attempt_pad_layer_landing = probe


def main() -> None:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    _install()
    import route_board

    pcb = args.pcb if args.pcb is not None else args.repo / "pcb" / "temper.kicad_pcb"
    rules = args.repo / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"

    t0 = time.perf_counter()
    r = route_board.route_once(pcb, rules)
    wall = time.perf_counter() - t0

    content = r.pop("routed_pcb_content", "") or ""
    args.board_out.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(args.board_out.read_bytes()).hexdigest()

    TRACE["route_summary"] = {k: v for k, v in r.items() if k != "routed_pcb_content"}
    TRACE["wall_s"] = round(wall, 1)
    TRACE["board_sha256"] = digest
    TRACE["source_pcb"] = str(pcb)
    args.trace_out.write_text(json.dumps(TRACE, default=str), encoding="utf-8")
    print(
        f"wall={wall:.1f}s segments={r['segments']} vias={r['vias']} "
        f"zones={r['zones']}\nboard sha256 {digest}"
    )


main()
