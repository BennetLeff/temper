#!/usr/bin/env python3
"""Layer 1, electrical coupling: component-net bipartite graph of the stage-$n netlist.

    python3 -I validation-results/13-coupling/scripts/electrical.py      (after $assign)

Projection: clique expansion with weight 1/(k-1) per net per pair of distinct parts on it (k = parts on the net), so
every net adds exactly 1 to each of its parts' weighted degree and a 70-pin rail weighs no more per part than a
2-pin signal. Three variants: all nets; no_rails (supply / ground / plane rails removed: common.RAIL); and
no_rails_no_planes (also the poured power nets leg_ret, hv_ret, bus_p, sw_a, sw_b).
Per group pair: shared nets (with class: power path, rail, signal, sense), weighted cut (raw) and cut normalised by
the smaller group's volume; per group: conductance cut / min(vol, vol_rest).
Communities: networkx Louvain (seed 1, sorted node order; resolution sweep) and greedy modularity; modularity Q of the
ten-group partition against the detected partition, adjusted Rand index, and the parts whose community's majority
group differs from their own. Intra-group: components and Louvain sub-blocks of each group's own subgraph, the nets
that join the sub-blocks, and the normalised algebraic connectivity of its largest component.
Controls: weighted degree == number of multi-part nets per part (projection identity); Q of a seeded random
relabelling of the groups is near 0; the detected partition has higher Q than the group partition on every variant;
two Louvain runs with the same seed are identical.
"""
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx
import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

VARIANTS = {
    "all": lambda n: True,
    "no_rails": lambda n: C.net_class(n) != "rail",
    "no_rails_no_planes": lambda n: C.net_class(n) != "rail" and n not in C.PLANE_POWER,
}


def project(nets, keep, refs):
    G = nx.Graph()
    G.add_nodes_from(sorted(refs))
    multi = Counter()
    for n in sorted(nets):
        if not keep(n):
            continue
        rs = sorted({r for r, _ in nets[n]})
        k = len(rs)
        if k < 2:
            continue
        for r in rs:
            multi[r] += 1
        w = 1.0 / (k - 1)
        for a, b in combinations(rs, 2):
            if G.has_edge(a, b):
                G[a][b]["weight"] += w
                G[a][b]["nets"].append(n)
            else:
                G.add_edge(a, b, weight=w, nets=[n])
    return G, multi


def ari(a, b):
    """adjusted Rand index of two labelings (lists)."""
    from math import comb
    n = len(a)
    ct = Counter(zip(a, b))
    sa, sb = Counter(a), Counter(b)
    idx = sum(comb(v, 2) for v in ct.values())
    ea = sum(comb(v, 2) for v in sa.values())
    eb = sum(comb(v, 2) for v in sb.values())
    exp = ea * eb / comb(n, 2)
    mx = (ea + eb) / 2
    return (idx - exp) / (mx - exp) if mx != exp else 1.0


def louvain(G, res, seed=1):
    """Louvain on integer-relabelled nodes (sorted names): string hashing is randomised under python3 -I and
    networkx iterates sets of nodes inside the aggregation step, so string labels made the result vary run to run."""
    names = sorted(G.nodes())
    ix_ = {n: i for i, n in enumerate(names)}
    H2 = nx.Graph()
    H2.add_nodes_from(range(len(names)))
    H2.add_weighted_edges_from(sorted((min(ix_[a], ix_[b]), max(ix_[a], ix_[b]), d["weight"]) for a, b, d in G.edges(data=True)))
    cs = nx.community.louvain_communities(H2, weight="weight", resolution=res, seed=seed)
    return sorted((sorted(names[i] for i in c) for c in cs), key=lambda c: (-len(c), c[0]))


def greedy(G):
    names = sorted(G.nodes())
    H2 = nx.Graph()
    H2.add_nodes_from(range(len(names)))
    ix_ = {n: i for i, n in enumerate(names)}
    H2.add_weighted_edges_from(sorted((min(ix_[a], ix_[b]), max(ix_[a], ix_[b]), d["weight"]) for a, b, d in G.edges(data=True)))
    cs = nx.community.greedy_modularity_communities(H2, weight="weight")
    return sorted((sorted(names[i] for i in c) for c in cs), key=lambda c: (-len(c), c[0]))


def induced(G, nodes):
    """induced subgraph with a fixed node / edge order (networkx subgraph views iterate the node set's hash order)."""
    keep = set(nodes)
    H = nx.Graph()
    H.add_nodes_from(sorted(keep))
    for a, b, d in sorted(((min(a, b), max(a, b), d) for a, b, d in G.edges(data=True) if a in keep and b in keep), key=lambda t: (t[0], t[1])):
        H.add_edge(a, b, **d)
    return H


def fiedler(H):
    if H.number_of_nodes() < 3:
        return None
    L = nx.normalized_laplacian_matrix(H, nodelist=sorted(H.nodes()), weight="weight").toarray()
    ev = np.linalg.eigvalsh(L)
    return float(ev[1])


def main():
    C.init()
    ctl = C.Controls()
    alt = sys.argv[sys.argv.index("--alt") + 1] if "--alt" in sys.argv else None     # alternative partition (regroup.py)
    asg = C.load(f"assignment-{alt}.json" if alt else "assignment.json")["assignment"]
    GIDS = sorted(set(asg.values()))
    comps, nets = C.netlist()
    refs = sorted(asg)
    ref_nets = defaultdict(set)
    for n, nodes in nets.items():
        for r, _ in nodes:
            ref_nets[r].add(n)
    net_groups = {n: sorted({asg[r] for r, _ in nodes}) for n, nodes in nets.items() if nodes}

    # ---- shared nets per pair (variant independent)
    pair_nets = {}
    for i, j in combinations(GIDS, 2):
        L = [{"net": n, "class": C.net_class(n), "groups": g} for n, g in sorted(net_groups.items()) if i in g and j in g]
        pair_nets[f"{i}-{j}"] = {"nets": L, "by_class": dict(Counter(x["class"] for x in L))}

    out = {"board_sha256": C.BOARD_SHA, "method": C.method(__doc__),
           "net_classes": {n: C.net_class(n) for n in sorted(nets)},
           "pair_shared_nets": pair_nets, "variants": {}}
    for vname, keep in VARIANTS.items():
        G, multi = project(nets, keep, refs)
        deg = dict(G.degree(weight="weight"))
        bad = [r for r in refs if abs(deg[r] - multi[r]) > 1e-9]
        ctl.check(f"[{vname}] weighted degree == multi-part nets per part", not bad, f"{len(bad)} mismatches")
        gid = {r: asg[r] for r in refs}
        vol = Counter()
        for r in refs:
            vol[gid[r]] += deg[r]
        W = {i: {j: 0.0 for j in GIDS} for i in GIDS}
        for a, b, d in G.edges(data=True):
            ga, gb = gid[a], gid[b]
            W[ga][gb] += d["weight"]
            if ga != gb:
                W[gb][ga] += d["weight"]
        # W[i][i] counts each internal edge once
        total = sum(vol.values())
        cut = {i: sum(W[i][j] for j in GIDS if j != i) for i in GIDS}
        cond = {i: (cut[i] / min(vol[i], total - vol[i]) if min(vol[i], total - vol[i]) > 0 else None) for i in GIDS}
        norm = {i: {j: (W[i][j] / min(vol[i], vol[j]) if i != j and min(vol[i], vol[j]) > 0 else 0.0) for j in GIDS}
                for i in GIDS}
        # partitions (ignore parts isolated in this variant for community stats)
        H = induced(G, [r for r in refs if deg[r] > 0])
        iso = sorted(r for r in refs if deg[r] == 0)
        gpart = [sorted(r for r in H if gid[r] == g) for g in GIDS]
        gpart = [c for c in gpart if c]
        Qg = nx.community.modularity(H, gpart, weight="weight")
        rng = random.Random(7)
        lab = [gid[r] for r in sorted(H)]
        rng.shuffle(lab)
        rpart = defaultdict(list)
        for r, g in zip(sorted(H), lab):
            rpart[g].append(r)
        Qr = nx.community.modularity(H, list(rpart.values()), weight="weight")
        ok, detail, null = abs(Qr) < 0.05, f"Q_random {Qr:.4f}", None
        if not ok:      # one seeded draw past 0.05: judge it against the null of 200 seeded relabellings instead
            qs = []
            for k in range(200):
                lab_k = [gid[r] for r in sorted(H)]
                random.Random(1000 + k).shuffle(lab_k)
                part_k = defaultdict(list)
                for r, g in zip(sorted(H), lab_k):
                    part_k[g].append(r)
                qs.append(nx.community.modularity(H, list(part_k.values()), weight="weight"))
            mu, sd = float(np.mean(qs)), float(np.std(qs))
            z = (Qr - mu) / sd
            ok = abs(mu) < 0.02 and abs(z) <= 3.0 and Qg > mu + 10 * sd
            null = {"n": 200, "seeds": "1000-1199", "mean": mu, "sd": sd, "max": float(max(qs)), "z_seed7": z}
            detail += f"; null of 200 seeded relabellings mean {mu:.4f} sd {sd:.4f} (z {z:.2f}), Q_groups {Qg:.3f}"
        ctl.check(f"[{vname}] random relabelling modularity ~ 0", ok, detail)
        sweep = []
        best = None
        for res in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
            cs = louvain(H, res)
            q1 = nx.community.modularity(H, cs, weight="weight")
            comm = {r: k for k, c in enumerate(cs) for r in c}
            a = ari([gid[r] for r in sorted(H)], [comm[r] for r in sorted(H)])
            sweep.append({"resolution": res, "communities": len(cs), "Q_resolution1": nx.community.modularity(H, cs, weight="weight", resolution=1.0), "ARI_vs_groups": a})
            if res == 1.0:
                best = cs
        cs2 = louvain(H, 1.0)
        ctl.check(f"[{vname}] Louvain deterministic with seed", cs2 == best)
        Qd = nx.community.modularity(H, best, weight="weight")
        ctl.check(f"[{vname}] detected Q >= group Q", Qd >= Qg - 1e-9, f"Q_detected {Qd:.4f}, Q_groups {Qg:.4f}")
        gr = greedy(H)
        Qgr = nx.community.modularity(H, gr, weight="weight")
        comm = {r: k for k, c in enumerate(best) for r in c}
        comm_rows = []
        misfits = []
        for k, c in enumerate(best):
            cnt = Counter(gid[r] for r in c)
            maj = max(cnt.items(), key=lambda t: (t[1], t[0]))[0]
            mods = Counter(comps[r]["path"].split(".")[0] for r in c)
            comm_rows.append({"community": k, "size": len(c), "groups": dict(sorted(cnt.items())), "majority_group": maj,
                              "ato_modules": dict(sorted(mods.items())), "parts": c})
            for r in c:
                if gid[r] != maj:
                    misfits.append({"ref": r, "group": gid[r], "community": k, "community_majority": maj,
                                    "path": comps[r]["path"], "mpn": comps[r]["mpn"]})
        # groups split across communities
        split = {}
        for g in GIDS:
            cnt = Counter(comm[r] for r in H if gid[r] == g)
            split[g] = dict(sorted((str(k), v) for k, v in cnt.items()))
        # ato hierarchy partition (top-level module; leaf parts of the top level are their own module)
        hp = defaultdict(list)
        for r in sorted(H):
            hp[comps[r]["path"].split(".")[0]].append(r)
        Qh = nx.community.modularity(H, list(hp.values()), weight="weight")
        # intra-group structure
        intra = {}
        for g in GIDS:
            S = induced(G, [r for r in refs if gid[r] == g])
            S.remove_nodes_from([r for r in list(S) if S.degree(r, weight="weight") == 0])
            ccs = sorted((sorted(c) for c in nx.connected_components(S)), key=lambda c: (-len(c), c[0]))
            row = {"parts_total": sum(1 for r in refs if gid[r] == g), "parts_with_internal_edges": S.number_of_nodes(),
                   "components": len(ccs), "component_sizes": [len(c) for c in ccs],
                   "small_components": [c for c in ccs if len(c) <= 6][:12]}
            if ccs:
                big = induced(S, ccs[0])
                row["fiedler_normalised_largest"] = fiedler(big)
                if big.number_of_nodes() >= 4:
                    sub = louvain(big, 1.0)
                    row["louvain_subblocks"] = len(sub)
                    row["louvain_Q_inside"] = nx.community.modularity(big, sub, weight="weight")
                    sb = {r: k for k, c in enumerate(sub) for r in c}
                    joins = defaultdict(Counter)
                    for a, b, d in big.edges(data=True):
                        if sb[a] != sb[b]:
                            key = f"{min(sb[a], sb[b])}-{max(sb[a], sb[b])}"
                            for n in d["nets"]:
                                joins[key][n] += 1
                    row["subblocks"] = [{"block": k, "size": len(c), "ato_modules": dict(sorted(Counter(comps[r]["path"].rsplit(".", 1)[0] if "." in comps[r]["path"] else comps[r]["path"] for r in c).most_common(6))), "parts": c} for k, c in enumerate(sub)]
                    row["subblock_joins"] = {k: sorted(v) for k, v in sorted(joins.items())}
                    row["weak_joins"] = sorted(k for k, v in joins.items() if len(v) <= 2)
            intra[g] = row
        out["variants"][vname] = {
            "nets_kept": sum(1 for n in nets if keep(n) and len({r for r, _ in nets[n]}) >= 2),
            "parts_isolated": iso, "volume": dict(vol), "W_raw": W, "W_norm_min_volume": norm,
            "cut": cut, "conductance": cond,
            "Q_groups": Qg, "Q_detected_louvain": Qd, "Q_greedy": Qgr, "Q_ato_top_module": Qh, "Q_random_relabel": Qr,
            "ARI_detected_vs_groups": ari([gid[r] for r in sorted(H)], [comm[r] for r in sorted(H)]),
            "resolution_sweep": sweep, "communities": comm_rows, "misfits": misfits,
            "group_split_over_communities": split, "intra_group": intra,
        }
        if null:
            out["variants"][vname]["Q_random_null"] = null
        print(f"[{vname}] Q groups {Qg:.3f} | Louvain {Qd:.3f} ({len(best)} comms) | greedy {Qgr:.3f} | ato {Qh:.3f} | "
              f"ARI {out['variants'][vname]['ARI_detected_vs_groups']:.3f} | misfits {len(misfits)} | isolated {len(iso)}")
    out["controls"] = ctl.rows
    h = C.write(f"electrical-{alt}.json" if alt else "electrical.json", out)
    print("electrical" + (f"-{alt}" if alt else "") + ".json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
