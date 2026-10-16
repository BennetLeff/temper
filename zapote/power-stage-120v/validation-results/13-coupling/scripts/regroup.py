#!/usr/bin/env python3
"""Alternative partitions: re-cut gate drive / bias / monitors (G05 / G06 / G07) by isolation island.

    python3 -I validation-results/13-coupling/scripts/regroup.py make       # writes results/assignment-<alt>.json
    python3 -I validation-results/13-coupling/scripts/electrical.py --alt islands   (and physical.py; also islands_selv)
    python3 -I validation-results/13-coupling/scripts/regroup.py compare    # writes results/regroup.json

The electrical communities (electrical.json, all nets) follow the isolation islands, not the functions: each of G05,
G06 and G07 has parts on the HS-A island (SW_A), the HS-B island (SW_B), the low-side (LOW) island and the SELV side.
Rule (pin domains from native-21/layout/domains.py over each part's pins):
  islands:       G05 / G06 / G07 parts become HSA (pins on SW_A, incl. U41 and U43), HSB (SW_B, incl. U42 and U44),
                 LS (LOW / HOT, incl. U1 / U2 drivers whose isolated outputs and supply are LS-referenced, U32, PS2, J3)
                 and SLOG (SELV-only drive / supervision logic); G01-G04, G08, G09, G10 unchanged.
  islands_selv:  as islands, with SLOG, G09 and G10 merged into one SELV-side group (SELV).
Compare: modularity (all nets, no rails), conductance, the largest normalised pair cut, courtyard contacts between
groups, routed copper in another group's territory, routed adjacency, contested corridor tiles, and the share of the
HOT / SELV pairs inside 9 mm that fall inside one group.
Controls: every part assigned once in each partition; 'current' reproduces electrical.json / physical.json numbers.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

ALTS = ("islands", "islands_selv")


def make():
    ctl = C.Controls()
    asg = C.load("assignment.json")["assignment"]
    comps, nets = C.netlist()
    dom, _ = C.domains()
    pins = defaultdict(Counter)
    for n, nodes in nets.items():
        for r, _p in nodes:
            pins[r][dom(n)] += 1
    rows = {}
    for alt in ALTS:
        new, why = {}, {}
        for r, g in asg.items():
            if g not in ("G05", "G06", "G07"):
                ng = g
                if alt == "islands_selv" and g in ("G09", "G10"):
                    ng = "SELV"
                new[r] = ng
                continue
            ds = set(pins[r])
            if r in ("U1", "U2"):
                ng = "LS"
            elif "SW_A" in ds:
                ng = "HSA"
            elif "SW_B" in ds:
                ng = "HSB"
            elif ds <= {"SELV"}:
                ng = "SLOG" if alt == "islands" else "SELV"
            else:
                ng = "LS"
            new[r] = ng
            why[r] = sorted(ds)
        ctl.check(f"[{alt}] every part assigned once", set(new) == set(asg) and all(new.values()))
        cnt = Counter(new.values())
        moved = {r: [asg[r], new[r], why.get(r)] for r in sorted(new) if asg[r] in ("G05", "G06", "G07") and len(why[r]) > 1}
        C.write(f"assignment-{alt}.json", {"rule": __doc__.split("Compare:")[0].strip(), "assignment": dict(sorted(new.items())),
                                           "group_part_counts": dict(sorted(cnt.items())), "straddlers": moved})
        rows[alt] = dict(sorted(cnt.items()))
        print(alt, dict(sorted(cnt.items())))
    ctl.finish()


def summary(el, ph, asg):
    gids = sorted(set(asg.values()))
    out = {"groups": len(gids), "sizes": dict(sorted(Counter(asg.values()).items()))}
    for v in ("all", "no_rails"):
        V = el["variants"][v]
        out[f"Q_{v}"] = V["Q_groups"]
        cond = [x for x in V["conductance"].values() if x is not None]
        out[f"mean_conductance_{v}"] = sum(cond) / len(cond)
        out[f"max_pair_norm_cut_{v}"] = max(V["W_norm_min_volume"][i][j] for i in gids for j in gids if i != j)
        tot_vol = sum(V["volume"].values())
        out[f"inter_group_cut_share_{v}"] = sum(V["cut"].values()) / tot_vol
    out["courtyard_contacts_2mm"] = sum(ph["proximity"]["pairs_within_2mm"][i][j] for i in gids for j in gids if i < j)
    routed = sum(ph["interleave_mm2"]["by_layer_kind"][L]["routed"][i][j] for L in C.LAYERS for i in gids for j in gids if i != j)
    out["routed_copper_in_other_territory_mm2"] = routed
    out["routed_adjacency_mm2"] = sum(ph["routed_adjacency_mm2"]["total"][i][j] for i in gids for j in gids if i < j)
    out["contested_corridor_pairs"] = sum(ph["corridors"]["pair_contested_tiles"][i][j] for i in gids for j in gids if i < j)
    rows = ph["barrier"]["pairs_within_9mm"]
    intra = 0
    for r in rows:
        gh = {asg_net for asg_net in r["hot_groups"]}
        gs = {asg_net for asg_net in r["selv_groups"]}
        intra += 1 if gh & gs else 0
    out["barrier_pairs_within_9mm"] = len(rows)
    out["barrier_pairs_inside_one_group"] = intra
    return out


def compare():
    ctl = C.Controls()
    res = {}
    base = C.load("assignment.json")["assignment"]
    res["current"] = summary(C.load("electrical.json"), C.load("physical.json"), base)
    for alt in ALTS:
        a = C.load(f"assignment-{alt}.json")["assignment"]
        res[alt] = summary(C.load(f"electrical-{alt}.json"), C.load(f"physical-{alt}.json"), a)
    el = C.load("electrical.json")
    ctl.check("current partition reproduces electrical.json Q (all nets)", abs(res["current"]["Q_all"] - el["variants"]["all"]["Q_groups"]) < 1e-12)
    for k in sorted(res):
        print(k, {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in res[k].items() if kk != "sizes"})
    C.write("regroup.json", {"method": C.method(__doc__), "partitions": res,
                             "straddlers": {alt: C.load(f"assignment-{alt}.json")["straddlers"] for alt in ALTS},
                             "controls": ctl.rows})
    ctl.finish()


if __name__ == "__main__":
    C.init()
    {"make": make, "compare": compare}[sys.argv[1]]()
