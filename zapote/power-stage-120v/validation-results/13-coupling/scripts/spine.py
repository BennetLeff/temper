#!/usr/bin/env python3
"""Did the SELV-spine lock keep the spine still, the way the stage-28 OCP lock kept OCP pickup at 4.17 A?

    python3 -I validation-results/13-coupling/scripts/spine.py [--stage TAG ...]   (after history.py)

The lock (native-21/layout/selv_spine_lock.json, gate native-21/layout/gates/spine_lock.py) came after stage 32 (commit
5b379ff51, the WS4 <-> WS5 contract of this audit): every later chain checks the board's spine copper against a
baseline. Here the gate's own scope function (spine_lock.items / check, loaded from ROOT, unchanged) is applied to every
consecutive pair of the adopted chain 19c -> TAG, before and after the lock:
  default scope   what a lane that does not own the spine may not touch: every track / via of a net touching the region
                  x 30-110 / y 130-180, every pad centred in it, J4 and the SELV transfer caps, zone fills inside it;
  owner scope     what even the SELV lane must keep: the contract nets and the selv_gnd / v3v3 planes.
Per stage: items removed / added and zone fills changed, the nets they are on, the stage's intended groups
(history.json) and whether a SELV lane owned the change (DECISIONS 50: stage 38 re-issued the lock). Beside it, the
contract's 'must not move' card values (return path, D5) and the changed routed items history.json placed in G09 / G10
territory (the spine's groups). The chain's own SPINE_LOCK verdicts (BUILDDIR/spine-lock.json) are read where present.
Controls: the gate's scope reproduces the chain's own verdict and locked-item count for the audited stage; the lock's
baseline export is the board the lock names.
"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import stages as STG  # noqa: E402

CONTRACT_METRICS = ("return_path_open_changes", "return_path_worst_asserted_mm", "d5_hot_selv_mm", "d5_hot_pe_mm")
OWNER_STAGES = {"native21s38": "selv lane, candidate 23 (DECISIONS 50 item 6: lock re-issued, J4.1 net and v15_selv antipads)"}
LOCK_AFTER = "native21s32"          # the lock gate landed after stage 32 (5b379ff51); every later chain ran it


def main():
    C.init()
    lock_path = C.N21 / "layout/selv_spine_lock.json"
    if not lock_path.exists():
        print(f"no SELV-spine lock at {C.TAG}'s root: nothing to check (the lock came after stage 32)")
        return
    ctl = C.Controls()
    lock = json.loads(lock_path.read_text())
    gate = C.load_mod(C.N21 / "layout/gates/spine_lock.py", "spine_lock_cpl")
    hi = C.load("history.json")
    chain = [t for t, _ in STG.chain_upto(C.TAG)]
    after = chain[chain.index(LOCK_AFTER) + 1:]
    base = json.load(gzip.open(C.PS / lock["baseline"]))
    ctl.check("lock baseline export is the board the lock names", base["board_sha256"] == lock["baseline_board_sha256"],
              base["board_sha256"][:8])
    prims = {t: json.load(gzip.open(C.N21 / f"verification/{t}-all-copper.json.gz"))["primitives"] for t in chain}
    own = gate.check(base["primitives"], prims[C.TAG], lock, None)
    chain_v = json.loads((C.BUILD / "spine-lock.json").read_text()) if (C.BUILD / "spine-lock.json").exists() else None
    ctl.check(f"{C.TAG}: the gate's scope reproduces the chain's SPINE_LOCK verdict and locked-item count",
              chain_v is not None and own["pass"] == chain_v["pass"] and own["locked_items"] == chain_v["locked_items"],
              f"pass {own['pass']}, {own['locked_items']} locked items (chain {chain_v and chain_v['locked_items']})")
    srow = {s["to"]: s for s in hi["stages"]}
    rows = []
    for a, b in zip(chain, chain[1:]):
        res = {}
        for scope in (None, "selv"):
            r = gate.check(prims[a], prims[b], lock, scope)
            nets = Counter(x[1] if x[0] in ("track", "via") else x[2] for x in r["removed"] + r["added"])
            res["default" if scope is None else "owner"] = {
                "removed": len(r["removed"]), "added": len(r["added"]), "zone_diffs": r["zone_diffs"],
                "changed": len(r["removed"]) + len(r["added"]) + len(r["zone_diffs"]), "nets": dict(sorted(nets.items())),
                "locked_items_before": r["locked_items"]}
        st = srow[b]
        build = None
        for d in sorted(STG.RUNS.glob(f"{STG.short(b)}/*/spine-lock.json")):
            v = json.loads(d.read_text())
            if v.get("candidate_board") == st["board_to"][:8]:
                build = {"file": str(d.relative_to(STG.RUNS)), "owner": v["owner"], "pass": v["pass"],
                         "baseline_board": v["baseline_board"], "n_removed": v["n_removed"], "n_added": v["n_added"],
                         "zone_diffs": v["zone_diffs"]}
        card_a, card_b = C.card(a) if (C.VR / f"10-benchmark/scorecard-{a}.json").exists() else None, \
            C.card(b) if (C.VR / f"10-benchmark/scorecard-{b}.json").exists() else None
        contract = {m: [card_a["performance"].get(m) if card_a else None, card_b["performance"].get(m) if card_b else None]
                    for m in CONTRACT_METRICS}
        rows.append({"from": a, "to": b, "locked": b in after, "spine_owner": OWNER_STAGES.get(b),
                     "intended_groups": st["intended_groups"], "spine": res, "chain_spine_lock": build,
                     "selv_territory_items": {g: st["changed_items_by_territory"].get(g, 0) for g in ("G09", "G10")},
                     "contract_metrics": contract})
        d_ = res["default"]
        print(f"{STG.short(a)}->{STG.short(b)} {'LOCKED' if b in after else 'free  '} owner {bool(OWNER_STAGES.get(b))!s:5} "
              f"spine changed {d_['changed']:4d} (owner scope {res['owner']['changed']:3d}) nets {list(d_['nets'])[:8]} "
              f"| G09/G10 territory items {rows[-1]['selv_territory_items']}")
    copper_pre = [r for r in rows if not r["locked"] and srow[r["to"]]["routed_copper_changed_nets"]]
    post_lanes = [r for r in rows if r["locked"] and not r["spine_owner"]]
    summary = {
        "pre_lock_copper_stages": len(copper_pre),
        "pre_lock_copper_stages_touching_spine": sum(1 for r in copper_pre if r["spine"]["default"]["changed"]),
        "pre_lock_spine_items_changed": sum(r["spine"]["default"]["changed"] for r in copper_pre),
        "post_lock_non_owner_stages": [r["to"] for r in post_lanes],
        "post_lock_non_owner_spine_items_changed": sum(r["spine"]["default"]["changed"] for r in post_lanes),
        "post_lock_owner_stages": {r["to"]: r["spine"]["default"]["changed"] for r in rows if r["locked"] and r["spine_owner"]},
        "post_lock_selv_territory_items_non_owner": sum(sum(r["selv_territory_items"].values()) for r in post_lanes),
        "contract_metrics_post_lock": {m: [r["contract_metrics"][m][1] for r in rows if r["locked"]] for m in CONTRACT_METRICS},
    }
    out = {"method": C.method(__doc__), "lock": {k: lock[k] for k in ("region", "contract_nets", "plane_nets", "frozen_refs",
                                                                       "baseline", "owner_lanes")},
           "stages": rows, "summary": summary, "audited_stage_vs_baseline": {k: own[k] for k in ("owner", "locked_items", "pass")},
           "controls": ctl.rows}
    h = C.write("spine.json", out)
    print("summary", json.dumps(summary))
    print("spine.json", h[:12])
    ctl.finish()


if __name__ == "__main__":
    main()
