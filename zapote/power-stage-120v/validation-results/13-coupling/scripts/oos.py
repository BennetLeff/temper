#!/usr/bin/env python3
"""Out-of-sample check: does the coupling model written on stage 32 predict the ripple of the stages adopted after it?

    python3 -I validation-results/13-coupling/scripts/oos.py [--stage TAG ...] [--frozen DIR]   (after combine.py)

The frozen model is the stage-32 run (--frozen, default 13-coupling/results-s32/: combined.json, verification.json,
history.json, byte-identical to the stage-32 audit's committed SHA256SUMS). It was written before stages 35-43 existed.
The cases are combine.eval_cases on this run's history.json (adopted chain 19c -> TAG, every stage labelled with the
same rule: an (intended group, other group) pair is positive if the other group's territory took >= 2 changed routed
items or DECISIONS records a ripple between them). 'old' = stages up to 32 (the frozen model's own history, relabelled
on the audited stage's territories), 'new' = stages after 32. Stage 43 (the global cleanup pass) has no outside group,
so it adds no case.
For the frozen model and for this run's model: ROC AUC per layer and combined on old / new / all cases and on distinct
pairs, a seeded bootstrap 95 % interval on the new cases (2000 resamples of cases), recall and false alarm at the frozen
model's thresholds (tau 0.20 and its median-positive tau) on the new distinct pairs, the score and within-stage rank of
every new positive, the AUC's sensitivity to stage 38 and to the ripple threshold (5 / 10 items instead of 2), and the
metric check (moved scorecard metrics against the intended groups' read lists) with the frozen model's read lists.
Controls: the frozen files are the committed stage-32 results (sha256 against their SHA256SUMS); the frozen model
reproduces its own committed AUC on its own history.json; this run's old + new cases are all of combine.json's cases.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import stages as STG  # noqa: E402

FROZEN_STAGE = "native21s32"
LAYERS = ("combined", "electrical", "physical", "physics", "verification")


def matrices(cb):
    import combine as CB
    G = CB.G
    comb = np.array([[cb["combined"][i][j] for j in G] for i in G])
    lay = {k: np.array([[cb["layer_matrices"][k][i][j] for j in G] for i in G]) for k in cb["layer_matrices"]}
    return comb, lay


def score(ev, cases_from):
    import combine as CB
    labels = [e["positive"] for e in ev]
    out = {"n_cases": len(ev), "n_positive": sum(labels)}
    out["auc"] = {k: CB.auc([e[k] for e in ev], labels) for k in LAYERS}
    seen = {}
    for e in ev:
        k = tuple(sorted((e["from"], e["to"])))
        seen[k] = seen.get(k, False) or e["positive"]
    out["distinct_pairs"] = len(seen)
    out["distinct_positive"] = sum(seen.values())
    sc = {k: next(e["combined"] for e in ev if tuple(sorted((e["from"], e["to"]))) == k) for k in seen}
    out["auc_distinct_pairs_combined"] = CB.auc([sc[k] for k in seen], [seen[k] for k in seen])
    out["distinct"] = {f"{a}-{b}": {"positive": seen[(a, b)], "combined": sc[(a, b)]} for a, b in sorted(seen)}
    return out


def boot(ev, n=2000, seed=1):
    import combine as CB
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(ev), len(ev))
        s = [ev[i]["combined"] for i in idx]
        lab = [ev[i]["positive"] for i in idx]
        a = CB.auc(s, lab)
        if a is not None:
            vals.append(a)
    return {"resamples": len(vals), "auc_combined_p2p5": float(np.percentile(vals, 2.5)),
            "auc_combined_p97p5": float(np.percentile(vals, 97.5)), "share_above_0p5": float(np.mean(np.array(vals) > 0.5))}


def thresholds(distinct, taus):
    pos = [v["combined"] for v in distinct.values() if v["positive"]]
    neg = [v["combined"] for v in distinct.values() if not v["positive"]]
    return [{"tau": t, "recall": sum(1 for x in pos if x >= t) / len(pos) if pos else None,
             "false_alarm": sum(1 for x in neg if x >= t) / len(neg) if neg else None,
             "positives": len(pos), "negatives": len(neg)} for t in taus]


def main():
    C.init()
    if C.TAG == FROZEN_STAGE:
        print(f"oos: {FROZEN_STAGE} is the frozen model's own stage; nothing out of sample")
        return
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", default=str(C.HERE.parent / f"results-{STG.short(FROZEN_STAGE)}"))
    a = ap.parse_args()
    import combine as CB
    ctl = C.Controls()
    FZ = Path(a.frozen)
    sums = dict(reversed(ln.split()) for ln in (FZ / "SHA256SUMS").read_text().splitlines())
    for f in ("combined.json", "verification.json", "history.json"):
        h = hashlib.sha256((FZ / f).read_bytes()).hexdigest()
        ctl.check(f"frozen {f} is the committed stage-32 result (SHA256SUMS)", sums.get(f) == h, h[:12])
    fcb = json.loads((FZ / "combined.json").read_text())
    fve = json.loads((FZ / "verification.json").read_text())
    fhi = json.loads((FZ / "history.json").read_text())
    fcomb, flay = matrices(fcb)
    own = CB.eval_cases(fhi, fcomb, flay)
    own_auc = CB.auc([e["combined"] for e in own], [e["positive"] for e in own])
    ctl.check("frozen model reproduces its own committed AUC on its own history", abs(own_auc - fcb["empirical"]["auc_by_layer"]["combined"]) < 5e-5,
              f"{own_auc:.4f} on {len(own)} cases")
    hi = C.load("history.json")
    cb = C.load("combined.json")
    comb, lay = matrices(cb)
    chain = [t for t, _ in STG.chain_upto(C.TAG)]
    old_st = set(chain[:chain.index(FROZEN_STAGE) + 1])
    res = {}
    for name, (M, L) in (("frozen_s32_model", (fcomb, flay)), (f"{STG.short(C.TAG)}_model", (comb, lay))):
        ev = CB.eval_cases(hi, M, L)
        old = [e for e in ev if e["stage"] in old_st]
        new = [e for e in ev if e["stage"] not in old_st]
        if name != "frozen_s32_model":
            ctl.check(f"{name}: old + new cases are combine.json's cases", len(old) + len(new) == cb["empirical"]["n_cases"],
                      f"{len(old)} + {len(new)}")
        res[name] = {"old": score(old, "old"), "new": score(new, "new"), "all": score(ev, "all"),
                     "new_bootstrap": boot(new)}
        # sensitivity of the new-case AUC: without stage 38 (its positives are one re-laid mains pair, 2 items per
        # territory), and with the territory ripple threshold raised from 2 to 5 / 10 changed items
        terr = {st["to"]: st["changed_items_by_territory"] for st in hi["stages"]}
        sens = {"new_without_s38": CB.auc([e["combined"] for e in new if e["stage"] != "native21s38"],
                                          [e["positive"] for e in new if e["stage"] != "native21s38"])}
        for k in (5, 10):
            lab = [e["documented_ripple"] or terr[e["stage"]].get(e["to"], 0) >= k for e in new]
            sens[f"new_ripple_ge_{k}_items"] = {"auc_combined": CB.auc([e["combined"] for e in new], lab), "positives": sum(lab)}
        res[name]["new_sensitivity"] = sens
        taus = sorted({0.2, round(fcb["empirical"]["tau_median_positive"], 3), round(cb["empirical"]["tau_median_positive"], 3)})
        res[name]["new_thresholds"] = thresholds(res[name]["new"]["distinct"], taus)
        res[name]["all_thresholds"] = thresholds(res[name]["all"]["distinct"], taus)
        if name == "frozen_s32_model":
            rows = []
            for st in sorted({e["stage"] for e in new}, key=chain.index):
                cs = sorted((e for e in new if e["stage"] == st), key=lambda e: -e["combined"])
                for k, e in enumerate(cs):
                    if e["positive"]:
                        rows.append({"stage": st, "from": e["from"], "to": e["to"], "combined": e["combined"],
                                     "rank_in_stage": k + 1, "stage_cases": len(cs), "observed": e["observed_copper_ripple"],
                                     "documented": e["documented_ripple"],
                                     **{k2: e[k2] for k2 in ("electrical", "physical", "physics", "verification")}})
            res[name]["new_positives"] = rows
            res[name]["new_cases_by_stage"] = {st: {"cases": sum(1 for e in new if e["stage"] == st),
                                                    "positive": sum(1 for e in new if e["stage"] == st and e["positive"])}
                                               for st in sorted({e["stage"] for e in new}, key=chain.index)}
    # metric check with the frozen read lists
    retrig = fve["retriggers_by_group"]
    glob = set(fve["global_metrics"])
    on_card = set(fve["group_x_metric_share"])
    mrows = []
    for st in hi["stages"]:
        if st["to"] in old_st:
            continue
        I = st["intended_groups"]
        pred = {m for g in I for m in retrig[g]}
        basis = st.get("metrics_moved_basis_change", {})
        moved = sorted(m for m in st["metrics_moved"] if not m.startswith("ledger_") and m not in basis)
        mrows.append({"stage": st["to"], "intended": I,
                      "moved_on_s32_card": [m for m in moved if m in on_card and m not in glob],
                      "predicted": [m for m in moved if m in on_card and m not in glob and m in pred],
                      "not_predicted": [m for m in moved if m in on_card and m not in glob and m not in pred],
                      "moved_not_on_s32_card": [m for m in moved if m not in on_card],
                      "basis_change": sorted(basis)})
    mc = {"rows": mrows, "moved": sum(len(r["moved_on_s32_card"]) for r in mrows),
          "predicted": sum(len(r["predicted"]) for r in mrows)}
    out = {"method": C.method(__doc__), "frozen_dir": str(FZ.name), "frozen_own_history_auc": own_auc,
           "old_stages": sorted(old_st, key=chain.index), "new_stages": [t for t in chain if t not in old_st],
           "not_adopted": STG.NOT_ADOPTED, "models": res, "metric_check_frozen": mc, "controls": ctl.rows}
    h = C.write("oos.json", out)
    for name, r in res.items():
        print(name, "| old AUC", {k: round(v, 3) for k, v in r["old"]["auc"].items() if v is not None}, r["old"]["n_cases"], r["old"]["n_positive"])
        print(name, "| new AUC", {k: (round(v, 3) if v is not None else None) for k, v in r["new"]["auc"].items()}, r["new"]["n_cases"],
              r["new"]["n_positive"], "distinct", r["new"]["distinct_pairs"], r["new"]["distinct_positive"],
              round(r["new"]["auc_distinct_pairs_combined"] or 0, 3), "boot", {k: round(v, 3) for k, v in r["new_bootstrap"].items()})
        print(name, "| new sensitivity", r["new_sensitivity"])
        print(name, "| all AUC", {k: round(v, 3) for k, v in r["all"]["auc"].items()}, r["all"]["n_cases"], r["all"]["n_positive"])
        for t in r["new_thresholds"]:
            print("   new tau", t)
    for r in res["frozen_s32_model"]["new_positives"]:
        print("   new positive", r)
    print("metric check (frozen read lists):", mc["predicted"], "/", mc["moved"], [(r["stage"], r["not_predicted"], r["moved_not_on_s32_card"]) for r in mrows])
    print("oos.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
