#!/usr/bin/env python3
"""Stage-14 migration of the frozen copper (copper_base.json and copper.json), applied once.

The SN6507 / T2 / T3 push-pull bias is replaced by one isolated module per high side
(DECISIONS 2026-10-09). The two switch trunks keep their hand-routed path (route21.py T_LINES:
In1 band under the core plane, F.Cu drops at each transformer) and carry the module primary nets
instead: bias_sw1 -> n_ls, bias_sw2 -> en_hs; v24_raw stays. Tracks that end on a removed part's
pad (U35, T2, T3) are dropped, so the remaining-connection passes re-join the trunk ends to the
module pins. Copper on nets that no longer exist is dropped, and so is any track whose pad-named end
now carries another net (stage 14 reuses freed designators for the new parts).

    python3 native-21/layout/stage14_migrate.py     (idempotent: a second run changes nothing)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENAME = {"bias_sw1": "n_ls", "bias_sw2": "en_hs"}   # en_hs then dropped: each module has its own enable divider
GONE_NETS = {"bias_ha-raw", "bias_hb-raw", "bias_ha-rect", "bias_hb-rect", "bias_ha-sa", "bias_ha-sb",
             "bias_hb-sa", "bias_hb-sb", "bias_sn1", "bias_sn2", "clk", "sr", "ss", "dc",
             "bias_ha.split-nr", "bias_hb.split-nr", "en_hs"} | \
            {f"bias_h{x}.split.ldo-p{n}" for x in "ab" for n in (2, 6, 11, 12, 17, 18, 19)}
# Dead In2 runs that served T3 (the routing passes pruned them as dangling every time): dropped here so
# the P_HB In2 run down x = 19.3 (patches21.add_stage14) can take their corridor.
DEAD = {("sw_b", "In2.Cu", (17.2, 51.4)), ("n_hb", "In2.Cu", (18.6, 52.0))}
GONE_REFS = {"U35", "T2", "T3", "U27", "U28", "L2", "L3", "D10", "D11", "D12", "D13", "C130"}


def pin_nets():
    """(ref, pad) -> net from the frozen netlist (designators freed in stage 14 are reused by new parts)."""
    import re
    t = (HERE.parent / "frozen/default.net").read_text()
    out = {}
    for name, body in re.findall(r'\(net \(code "\d+"\) \(name "([^"]*)"\)(.*?)(?=\(net \(code|\Z)', t, re.S):
        for ref, pad in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body):
            out[(ref, pad)] = name
    return out


PIN_NET = pin_nets()


def stale_end(t):
    """A pad-named end whose pad now carries another net (a reused designator) or no longer exists."""
    for q in t["points"]:
        if isinstance(q, str):
            ref, pad = q.split(".", 1)
            if PIN_NET.get((ref, pad)) != t["net"]:
                return True
    return False


def migrate(path):
    d = json.loads(path.read_text())
    stats = {"tracks_dropped": 0, "vias_dropped": 0, "zones_dropped": 0, "renamed": 0}
    tracks = []
    for t in d["tracks"]:
        if t["net"] in GONE_NETS or any(isinstance(p, str) and p.split(".")[0] in GONE_REFS for p in t["points"]):
            stats["tracks_dropped"] += 1
            continue
        if t["net"] in RENAME:
            t["net"] = RENAME[t["net"]]
            stats["renamed"] += 1
        if stale_end(t) or (t["net"], t["layer"], tuple(t["points"][0])) in DEAD:
            stats["tracks_dropped"] += 1
            continue
        tracks.append(t)
    vias = []
    for v in d["vias"]:
        if v["net"] in GONE_NETS:
            stats["vias_dropped"] += 1
            continue
        if v["net"] in RENAME:
            v["net"] = RENAME[v["net"]]
            stats["renamed"] += 1
        vias.append(v)
    zones = [z for z in d["zones"] if z["net"] not in GONE_NETS]
    # R4 (bus bleed, busbleed_mid / hv_ret) moved to (288.0, 103.5), 270 deg: its pad-escape rects
    # follow it (the bleed run enters pad 1 from above, the hv_ret link leaves pad 2 to D17.2).
    d["escapes"] = [e for e in d.get("escapes", []) if e["ref"] != "R4"] + [
        {"ref": "R4", "pad": "1", "rect": [287.1, 100.0, 288.9, 102.9]},
        {"ref": "R4", "pad": "2", "rect": [283.0, 104.1, 288.9, 106.9]}]
    stats["zones_dropped"] = len(d["zones"]) - len(zones)
    d["tracks"], d["vias"], d["zones"] = tracks, vias, zones
    path.write_text(json.dumps(d, indent=1) + "\n")
    return stats


if __name__ == "__main__":
    for name in ("copper_base.json", "copper.json"):
        print(name, migrate(HERE / name))
