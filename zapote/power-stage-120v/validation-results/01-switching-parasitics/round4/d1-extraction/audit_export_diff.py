#!/usr/bin/env python3
"""Quantify nominal pad-layer shapes removed by the FlashLayer-aware export."""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict

from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, digest

OLD = UNIT / "validation-results/04-board-current-thermal/round3/b3-thermal/inputs/native15-all-copper.json.gz"


def main() -> None:
    old=json.load(gzip.open(OLD,"rt"))
    new=json.load(gzip.open(COPPER,"rt"))
    if old["board_sha256"]!=BOARD_SHA or new["board_sha256"]!=BOARD_SHA:
        raise ValueError("board hash mismatch")
    old_keys={(x["ref"],x["net"],x["layer"]) for x in old["primitives"] if x["kind"]=="pad"}
    new_keys={(x["ref"],x["net"],x["layer"]) for x in new["primitives"] if x["kind"]=="pad"}
    expected={(x["ref"],x["net"],x["layer"]) for x in new["suppressed_pads"]}
    removed=sorted((old_keys-new_keys)&expected)
    old_only_other=sorted((old_keys-new_keys)-expected)
    if any(net for _,net,_ in old_only_other) or new_keys-old_keys:
        raise AssertionError("nonempty-net pad delta differs from KiCad flash oracle")
    grouped=defaultdict(list)
    for ref,net,layer in removed:
        grouped[net].append({"ref":ref,"layer":layer})
    by_net={net:{"suppressed_pad_layers":len(rows),"refs":sorted({row["ref"] for row in rows}),
                 "by_layer":dict(Counter(row["layer"] for row in rows))}
            for net,rows in sorted(grouped.items())}
    result={"board_sha256":BOARD_SHA,"old_export_sha256":digest(OLD),"new_export_sha256":digest(COPPER),
            "old_primitive_count":len(old["primitives"]),"new_primitive_count":len(new["primitives"]),
            "old_distinct_pad_layers":len(old_keys),"new_distinct_pad_layers":len(new_keys),
            "suppressed_distinct_pad_layers_in_old_export":len(removed),"suppressed_distinct_pad_layers_in_new_oracle":len(expected),
            "old_only_no_net_pad_layers":len(old_only_other),"suppressed_by_net":by_net,
            "caution":"This counts formerly exported nominal pad layers, not a quantified thermal or resistance error. Existing round-3 B3-derived solves require re-run on flashed geometry."}
    (HERE/"export-diff.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"suppressed":len(removed),"by_net":{k:v["suppressed_pad_layers"] for k,v in by_net.items()}},indent=2))


if __name__=="__main__":
    main()
