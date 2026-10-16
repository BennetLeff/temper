#!/usr/bin/env python3
"""Combine the four coupling layers, score the model against stages 19c -> $n, and count workstreams.

    python3 -I validation-results/13-coupling/scripts/combine.py      (after the five layer scripts)

Each layer gives a symmetric 10 x 10 matrix scaled to [0, 1] by its largest off-diagonal entry; a layer made of
several terms is the mean of its scaled terms:
  electrical  = mean(normalised cut, all nets; normalised cut, no rails)                     (electrical.json)
  physical    = mean(courtyard touch fraction <= 2 mm; routed copper in the other's territory; routed adjacency
                <= 0.5 mm; contested 10 mm corridor tiles; HOT / SELV net pairs inside 9 mm) (physical.json)
  physics     = mean(heat deposited within 5 mm; dv/dt overlap (adjacent layer + same layer <= 3.5 mm);
                return-path reference changes; coil-field pickup utilisation; RES_A creepage 1/margin) (physics.json)
  verification = shared non-global gate / metric reads                                       (verification.json)
combined = mean of the four layers. Pairs are ranked by combined.
Empirical check (history.json): for every stage that changed copper or parts, each (intended group, other group) pair
is positive if the other group's territory took >= 2 changed routed-copper items or DECISIONS records a ripple
between them; ROC AUC of each layer and of the combined score over those pairs. Metric check: metrics that moved at
each stage against the non-global metrics the intended groups re-trigger (verification.json).
Workstreams: at threshold tau, groups joined by a combined edge >= tau must be serialised (connected components =
workstreams); the largest set of groups with no edge >= tau between them can be changed concurrently. tau is set
from the history: the median combined score of the observed-ripple pairs. Six-layer scenario (c33 PLAN.md 'can
change'): the routing-room terms (routed interleave, routed adjacency, corridors, return-path changes, and the coil
pickup's plane-continuity term) set to zero as an upper bound on what two extra planes could cut; barrier, creepage,
electrical, thermal and verification terms kept.
Controls: every layer matrix is symmetric with a zero diagonal; AUC of a constant score is 0.5; the combined ranking is
reproduced from the stored layer matrices.
"""
import sys
from itertools import combinations
from pathlib import Path

import networkx as nx
import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

G = C.GIDS
N = len(G)
ix = {g: i for i, g in enumerate(G)}


def mat(d, sym=True):
    M = np.array([[float(d[i][j] or 0.0) for j in G] for i in G])
    np.fill_diagonal(M, 0.0)
    if sym:
        M = (M + M.T) / 2
    return M


def scale(M):
    m = M.max()
    return M / m if m > 0 else M


def auc(scores, labels):
    pos = [s for s, l_ in zip(scores, labels) if l_]
    neg = [s for s, l_ in zip(scores, labels) if not l_]
    if not pos or not neg:
        return None
    tot = 0.0
    for p in pos:
        for n in neg:
            tot += 1.0 if p > n else 0.5 if p == n else 0.0
    return tot / (len(pos) * len(neg))


def workstreams(M, tau):
    Gr = nx.Graph()
    Gr.add_nodes_from(G)
    for i, j in combinations(range(N), 2):
        if M[i, j] >= tau:
            Gr.add_edge(G[i], G[j])
    comps = sorted((sorted(c) for c in nx.connected_components(Gr)), key=lambda c: (-len(c), c))
    comp = nx.complement(Gr)
    cl = max(nx.find_cliques(comp), key=lambda c: (len(c), sorted(c)))   # max independent set of Gr
    return {"tau": tau, "edges": sorted(f"{a}-{b}" for a, b in Gr.edges()), "workstreams": comps, "n_workstreams": len(comps),
            "max_concurrent_set": sorted(cl), "n_max_concurrent": len(cl)}


def cluster(M, tau):
    Gw = nx.Graph()
    Gw.add_nodes_from(range(N))
    Gw.add_weighted_edges_from(sorted((i, j, float(M[i, j])) for i, j in combinations(range(N), 2)))
    out = {}
    for res in (1.0, 1.5, 2.0):
        cs = nx.community.louvain_communities(Gw, weight="weight", resolution=res, seed=1)
        cs = sorted((sorted(G[i] for i in c) for c in cs), key=lambda c: (-len(c), c))
        lab = {g: k for k, c in enumerate(cs) for g in c}
        inter = [float(M[i, j]) for i, j in combinations(range(N), 2) if lab[G[i]] != lab[G[j]]]
        intra = [float(M[i, j]) for i, j in combinations(range(N), 2) if lab[G[i]] == lab[G[j]]]
        worst = max(((float(M[i, j]), f"{G[i]}-{G[j]}") for i, j in combinations(range(N), 2) if lab[G[i]] != lab[G[j]]), default=(0, ""))
        out[str(res)] = {"clusters": cs, "n": len(cs), "max_inter": worst[0], "max_inter_pair": worst[1],
                         "mean_inter": float(np.mean(inter)) if inter else 0.0, "mean_intra": float(np.mean(intra)) if intra else 0.0,
                         "inter_edges_at_or_above_tau": sorted(f"{G[i]}-{G[j]}" for i, j in combinations(range(N), 2)
                                                               if lab[G[i]] != lab[G[j]] and M[i, j] >= tau)}
    return out


def eval_cases(hi, comb, layers):
    """Every (intended group, other group) pair of every stage that changed copper or parts, labelled positive if the other
    group's territory took >= 2 changed routed-copper items or DECISIONS records a ripple between them, with the model's
    scores; plus the documented ripple whose source is outside the stage's intended groups."""
    doc = {}
    for r in hi["documented_ripple"]:
        for a in r["from"]:
            for b in r["to"]:
                if a != b:
                    doc.setdefault((r["stage"], a, b), r["mechanism"])
    ev = []
    for st in hi["stages"]:
        I = set(st["intended_groups"])
        changed = bool(st["routed_copper_changed_nets"] or st["added"] or st["removed"] or st["moved"] or st["pour_fill_changed"])
        if not I or not changed:
            continue
        terr = {g for g, k in st["changed_items_by_territory"].items() if g != "open" and k >= 2}
        for a in sorted(I):
            for b in G:
                if b in I:
                    continue
                pos_obs = b in terr
                pos_doc = (st["to"], a, b) in doc
                ev.append({"stage": st["to"], "from": a, "to": b, "observed_copper_ripple": pos_obs, "documented_ripple": pos_doc,
                           "positive": pos_obs or pos_doc, "combined": float(comb[ix[a], ix[b]]),
                           **{lay: float(layers[lay][ix[a], ix[b]]) for lay in layers}})
    for (stg, a, b), mech in doc.items():
        st = next(s for s in hi["stages"] if s["to"] == stg)
        if a not in st["intended_groups"]:
            ev.append({"stage": stg, "from": a, "to": b, "observed_copper_ripple": False, "documented_ripple": True, "positive": True,
                       "combined": float(comb[ix[a], ix[b]]), **{lay: float(layers[lay][ix[a], ix[b]]) for lay in layers},
                       "note": "documented blocker / ripple source outside the stage's intended groups"})
    return ev


def main():
    C.init()
    ctl = C.Controls()
    el = C.load("electrical.json")
    ph = C.load("physical.json")
    fz = C.load("physics.json")
    ve = C.load("verification.json")
    hi = C.load("history.json")

    terms = {}
    terms["electrical"] = {
        "cut_norm_all": mat(el["variants"]["all"]["W_norm_min_volume"]),
        "cut_norm_no_rails": mat(el["variants"]["no_rails"]["W_norm_min_volume"]),
    }
    routed_il = {i: {j: sum(ph["interleave_mm2"]["by_layer_kind"][L]["routed"][i][j] for L in C.LAYERS) for j in G} for i in G}
    terms["physical"] = {
        "courtyard_touch_2mm": mat(ph["proximity"]["touch_fraction_2mm"]),
        "routed_interleave": mat(routed_il),
        "routed_adjacency": mat(ph["routed_adjacency_mm2"]["total"]),
        "corridor_tiles": mat(ph["corridors"]["pair_contested_tiles"]),
        "barrier_pairs_9mm": mat(ph["barrier"]["pair_weight_within_9mm"]),
    }
    dv = {i: {j: fz["dvdt"]["adjacent_layer_overlap_mm2"][i][j] + fz["dvdt"]["same_layer_within_3p5mm_mm2"][i][j] for j in G} for i in G}
    field = {i: {j: 0.0 for j in G} for i in G}
    for vic, v in fz["coil_field"]["victims"].items():
        field["G04"][vic] = field[vic]["G04"] = v["utilisation"]
    cre = {i: {j: 0.0 for j in G} for i in G}
    for g, v in fz["creepage_res_a"]["inverse_margin_by_group"].items():
        if g != "G04":
            cre["G04"][g] = cre[g]["G04"] = v
    terms["physics"] = {
        "heat_within_5mm": mat(fz["thermal"]["heat_within_5mm_W"]),
        "dvdt_overlap": mat(dv),
        "return_path_changes": mat(fz["return_path"]["pair_changes"]),
        "coil_field": mat(field),
        "res_a_creepage": mat(cre),
    }
    terms["verification"] = {"shared_reads": mat(ve["verification_coupling"])}
    for lay, ts in terms.items():
        for k, M in ts.items():
            ctl.check(f"{lay}.{k} symmetric, zero diagonal", np.allclose(M, M.T) and np.allclose(np.diag(M), 0))
    layers = {lay: np.mean([scale(M) for M in ts.values()], axis=0) for lay, ts in terms.items()}
    comb = np.mean([layers[k] for k in ("electrical", "physical", "physics", "verification")], axis=0)
    pairs = []
    for i, j in combinations(range(N), 2):
        pairs.append({"pair": f"{G[i]}-{G[j]}", "combined": float(comb[i, j]),
                      **{lay: float(layers[lay][i, j]) for lay in layers}})
    pairs.sort(key=lambda r: (-r["combined"], r["pair"]))
    comb2 = np.mean([np.mean([scale(M) for M in ts.values()], axis=0) for ts in terms.values()], axis=0)
    ctl.check("combined reproduced from the layer matrices", np.allclose(comb, comb2))

    # ---------------- empirical check
    ev = eval_cases(hi, comb, layers)
    labels = [e["positive"] for e in ev]
    aucs = {k: auc([e[k] for e in ev], labels) for k in ("combined", "electrical", "physical", "physics", "verification")}
    ctl.check("AUC of a constant score is 0.5", auc([1.0] * len(ev), labels) == 0.5)
    # distinct pairs view (a pair counted once, positive if ever positive)
    seen = {}
    for e in ev:
        k = tuple(sorted((e["from"], e["to"])))
        seen[k] = seen.get(k, False) or e["positive"]
    dp = [(k, v, float(comb[ix[k[0]], ix[k[1]]])) for k, v in seen.items()]
    auc_pairs = auc([s for _, _, s in dp], [v for _, v, _ in dp])
    pos_scores = sorted(s for _, v, s in dp if v)
    neg_scores = sorted(s for _, v, s in dp if not v)
    tau = float(np.median(pos_scores))
    # metric prediction
    retrig = ve["retriggers_by_group"]
    glob = set(ve["global_metrics"])
    mrows = []
    for st in hi["stages"]:
        I = st["intended_groups"]
        pred = sorted({m for g in I for m in retrig[g]})
        basis = st.get("metrics_moved_basis_change", {})
        moved = sorted(m for m in st["metrics_moved"] if m not in ("ledger_violations", "ledger_unaudited_safety_power")
                       and m not in glob and m not in basis)
        hit = [m for m in moved if m in pred]
        miss = [m for m in moved if m not in pred]
        mrows.append({"stage": st["to"], "intended": I, "moved": moved, "predicted_reads": len(pred), "moved_and_predicted": hit,
                      "moved_not_predicted": miss})
        g_moved = sorted(m for m in st["metrics_moved"] if m in glob and not m.startswith("ledger_"))
        if g_moved:                 # a global metric moves with any change: predicted by definition, counted apart
            mrows[-1]["moved_global"] = g_moved
        if basis:
            mrows[-1]["moved_basis_change"] = sorted(basis)
    moved_tot = sum(len(r["moved"]) for r in mrows)
    hit_tot = sum(len(r["moved_and_predicted"]) for r in mrows)
    # propagated: intended groups plus every group joined to one of them by combined >= tau
    for r in mrows:
        I = set(r["intended"])
        J = I | {G[j] for i in I for j in range(N) if comb[ix[i], j] >= tau}
        pred = sorted({m for g in J for m in retrig[g]})
        r["propagated_groups"] = sorted(J)
        r["propagated_predicted_reads"] = len(pred)
        r["moved_not_predicted_after_propagation"] = [m for m in r["moved"] if m not in pred]
    hit_prop = sum(len(r["moved"]) - len(r["moved_not_predicted_after_propagation"]) for r in mrows)
    # change type: BOM-only stages vs copper stages (history.json)
    ctype = {"bom_only": {"stages": [], "ripple_territories": 0, "metrics_moved": []},
             "copper": {"stages": [], "ripple_territories": 0, "metrics_moved": []}}
    for st in hi["stages"]:
        k = "copper" if (st["routed_copper_changed_nets"] or st["pour_fill_changed"] or st["moved"]) else "bom_only"
        ctype[k]["stages"].append(st["to"])
        ctype[k]["ripple_territories"] += len(st["ripple_groups_routed"])
        ctype[k]["metrics_moved"] += [f"{st['to'][8:]}:{m}" for m in st["metrics_moved"]]

    # threshold table: share of ripple pairs at or above tau (recall) and of quiet pairs at or above tau (false alarm)
    thr = []
    for t in (0.10, 0.15, 0.20, 0.25, 0.30, round(tau, 3), 0.35, 0.40, 0.45):
        w = workstreams(comb, t)
        thr.append({"tau": t, "recall": sum(1 for x in pos_scores if x >= t) / len(pos_scores),
                    "false_alarm": sum(1 for x in neg_scores if x >= t) / len(neg_scores) if neg_scores else None,
                    "n_workstreams": w["n_workstreams"], "n_max_concurrent": w["n_max_concurrent"], "max_concurrent_set": w["max_concurrent_set"]})

    # ---------------- group-level clustering (Louvain on the combined graph, integer labels, seed 1)
    clusters = cluster(comb, tau)
    # ---------------- workstreams
    ws_now = {f"{t:.3f}": workstreams(comb, t) for t in sorted({round(tau, 3), 0.2, 0.3, 0.4})}
    six = {lay: {k: M.copy() for k, M in ts.items()} for lay, ts in terms.items()}
    for k in ("routed_interleave", "routed_adjacency", "corridor_tiles"):
        six["physical"][k] = np.zeros((N, N))
    six["physics"]["return_path_changes"] = np.zeros((N, N))
    six["physics"]["coil_field"] = np.zeros((N, N))
    # keep each term's scale as today so the scenario is comparable (zeroed terms still count in the mean)
    lay6 = {lay: np.mean([six[lay][k] / (terms[lay][k].max() or 1) for k in ts], axis=0) for lay, ts in terms.items()}
    comb6 = np.mean([lay6[k] for k in ("electrical", "physical", "physics", "verification")], axis=0)
    ws_six = workstreams(comb6, round(tau, 3))
    ws_six["group_clusters"] = cluster(comb6, tau)
    ws_six["edges_removed_vs_now"] = sorted(set(workstreams(comb, round(tau, 3))["edges"]) - set(ws_six["edges"]))
    pairs6 = sorted(({"pair": f"{G[i]}-{G[j]}", "combined_now": float(comb[i, j]), "combined_six_layer_bound": float(comb6[i, j]),
                      "cut": float(comb[i, j] - comb6[i, j])} for i, j in combinations(range(N), 2)), key=lambda r: (-r["cut"], r["pair"]))
    out = {
        "method": C.method(__doc__),
        "layer_matrices": {lay: {G[i]: {G[j]: float(layers[lay][i, j]) for j in range(N)} for i in range(N)} for lay in layers},
        "term_matrices_raw": {lay: {k: {G[i]: {G[j]: float(M[i, j]) for j in range(N)} for i in range(N)} for k, M in ts.items()} for lay, ts in terms.items()},
        "combined": {G[i]: {G[j]: float(comb[i, j]) for j in range(N)} for i in range(N)},
        "ranked_pairs": pairs,
        "group_total_coupling": {g: float(comb[ix[g]].sum()) for g in G},
        "empirical": {"pairs_evaluated": ev, "n_cases": len(ev), "n_positive": sum(labels), "auc_by_layer": aucs,
                      "distinct_pairs": len(dp), "distinct_positive": sum(1 for _, v, _ in dp if v), "auc_distinct_pairs_combined": auc_pairs,
                      "positive_combined_scores": pos_scores, "negative_combined_scores": neg_scores,
                      "tau_median_positive": tau, "metric_check": mrows, "metrics_moved_total": moved_tot, "metrics_moved_predicted": hit_tot,
                      "metrics_moved_predicted_with_propagation": hit_prop, "change_type": ctype},
        "group_clusters": clusters,
        "threshold_table": thr,
        "workstreams_now": ws_now,
        "six_layer_bound": {"workstreams": ws_six, "pair_cut": pairs6,
                            "combined": {G[i]: {G[j]: float(comb6[i, j]) for j in range(N)} for i in range(N)}},
        "controls": ctl.rows,
    }
    h = C.write("combined.json", out)
    print("top pairs:", [(p["pair"], round(p["combined"], 3)) for p in pairs[:12]])
    print("AUC", {k: (round(v, 3) if v is not None else None) for k, v in aucs.items()}, "distinct-pair AUC", round(auc_pairs, 3),
          f"cases {len(ev)} pos {sum(labels)}; distinct pairs {len(dp)} pos {sum(1 for _, v, _ in dp if v)}; tau {tau:.3f}")
    print("metrics moved predicted", hit_tot, "/", moved_tot, "; with propagation", hit_prop)
    for r in thr:
        print("tau", r["tau"], "recall", round(r["recall"], 2), "false alarm", round(r["false_alarm"], 2), "ws", r["n_workstreams"], "max concurrent", r["n_max_concurrent"], r["max_concurrent_set"])
    print("change type", {k: (len(v["stages"]), v["ripple_territories"]) for k, v in ctype.items()})
    for k, v in clusters.items():
        print("clusters res", k, v["clusters"], "max inter", round(v["max_inter"], 3), v["max_inter_pair"], "inter>=tau", v["inter_edges_at_or_above_tau"])
    for t, w in ws_now.items():
        print("tau", t, "workstreams", w["n_workstreams"], w["workstreams"], "max concurrent", w["n_max_concurrent"], w["max_concurrent_set"])
    print("six-layer bound: workstreams", ws_six["n_workstreams"], ws_six["workstreams"], "max concurrent", ws_six["n_max_concurrent"], ws_six["max_concurrent_set"], "edges removed", ws_six["edges_removed_vs_now"])
    for k, v in ws_six["group_clusters"].items():
        print("six-layer clusters res", k, v["clusters"], "max inter", round(v["max_inter"], 3), v["max_inter_pair"], "inter>=tau", v["inter_edges_at_or_above_tau"])
    print("combined.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
