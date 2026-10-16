#!/usr/bin/env python3
"""Re-derive the ten-group assignment for the audited stage's board (default the board of record).

    python3 -I validation-results/13-coupling/scripts/assign.py [--stage TAG --root DIR ...]   (common.init options)

Rule: common.assign_stage = the stage-19c map_groups rule plus the stage 20+ rules introduced up to the audited stage
(common.RULES: R1-R4 at stage 32, R5 at stage 40). Every part that is new since 19c, removed, reassigned, or whose
electrical / physical neighbourhood votes for another group is listed with the rule.
Electrical vote: sum over the part's non-rail nets of 1/(k-1) per neighbouring part (k = parts on the net), by group.
Physical vote: the group of the nearest other part's courtyard (edge gap).
Writes results/assignment.json. Controls: every netlist component and every placed part is assigned exactly once;
the 19c assignment is reproduced for every surviving part except the rule-listed ones; courtyards contain their pads.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def main():
    C.init()
    ctl = C.Controls()
    comps, nets = C.netlist()
    prt = C.parts()
    plc = C.placement()
    old = json.loads((C.VR / "11-candidates/groups.json").read_text())["assignment"]
    asg, rule = {}, {}
    for p in prt:
        g, r = C.assign_stage(p["path"], p["group"])
        asg[p["ref"]] = g
        rule[p["ref"]] = r
    ctl.check("every parts.json entry assigned", all(asg.values()), f"{sum(1 for v in asg.values() if v)}/{len(prt)}")
    ctl.check("netlist components == parts.json refs", set(comps) == set(asg), f"netlist {len(comps)}, parts {len(asg)}")
    ctl.check("every part placed", all(p["path"] in plc for p in prt), f"placement {len(plc)}")
    ctl.check("no duplicate refs", len(prt) == len({p['ref'] for p in prt}))
    ctl.check("netlist paths == parts.json paths", all(comps[p["ref"]]["path"] == p["path"] for p in prt))

    # 19c reproduction: surviving parts keep their group unless a stage 20+ rule applies
    moved = {r: (old[r], asg[r]) for r in asg if r in old and old[r] != asg[r]}
    unexplained = [r for r in moved if rule[r].startswith("R0")]
    ctl.check(f"19c assignment reproduced for surviving parts (except R1-R{len(C.rules_for())})", not unexplained,
              f"unexplained {unexplained}")

    # courtyard control (courtyards file is the stage's chain's)
    cy = C.courtyards()
    pb = C.pads_board()
    bad = [p["ref"] + "." + p["pad"] for p in pb if p["ref"] in asg and p["ref"] in cy and not (
        cy[p["ref"]][0] - 0.05 <= p["x"] <= cy[p["ref"]][2] + 0.05 and cy[p["ref"]][1] - 0.05 <= p["y"] <= cy[p["ref"]][3] + 0.05)]
    ctl.check(f"stage-{C.N} pads inside their courtyard boxes", not bad, f"{len(bad)} outside: {bad[:5]}")
    ctl.check("every assigned part has a courtyard", all(r in cy for r in asg), str([r for r in asg if r not in cy][:5]))

    # electrical vote (non-rail nets)
    ref_nets = defaultdict(set)
    for n, nodes in nets.items():
        for r, _ in nodes:
            ref_nets[r].add(n)
    vote_e = {}
    for r in asg:
        acc = Counter()
        for n in ref_nets[r]:
            if C.net_class(n) == "rail":
                continue
            others = {x for x, _ in nets[n]} - {r}
            if not others:
                continue
            for o in others:
                acc[asg[o]] += 1.0 / len(others)
        vote_e[r] = acc
    # physical vote: nearest other courtyard
    import math

    def gap(a, b):
        dx = max(a[0] - b[2], b[0] - a[2], 0.0)
        dy = max(a[1] - b[3], b[1] - a[3], 0.0)
        return math.hypot(dx, dy)
    vote_p = {}
    for r in asg:
        best = min(((gap(cy[r], cy[o]), o) for o in asg if o != r), key=lambda t: (t[0], t[1]))
        vote_p[r] = (asg[best[1]], best[1], round(best[0], 2))

    listed = {}
    for r in sorted(asg, key=lambda s: (s.rstrip("0123456789"), int("".join(ch for ch in s if ch.isdigit()) or 0))):
        e = vote_e[r]
        etop = max(e.items(), key=lambda t: (t[1], t[0]))[0] if e else None
        eshare = round(e[asg[r]] / sum(e.values()), 3) if e else None
        why = []
        if r not in old:
            why.append("new since 19c")
        if r in moved:
            why.append(f"reassigned {moved[r][0]} -> {moved[r][1]}")
        if e and etop != asg[r]:
            why.append(f"electrical vote {etop} (own-group share {eshare})")
        if why:
            listed[r] = {"group": asg[r], "path": next(p["path"] for p in prt if p["ref"] == r), "mpn": comps[r]["mpn"],
                         "rule": rule[r], "why_listed": why,
                         "electrical_vote": {g: round(v, 3) for g, v in sorted(e.items())},
                         "nearest_courtyard": {"ref": vote_p[r][1], "group": vote_p[r][0], "gap_mm": vote_p[r][2]}}
    removed = {r: old[r] for r in old if r not in asg}
    counts = Counter(asg.values())
    new_parts = sorted(r for r in asg if r not in old)
    ambiguous_e = sorted(r for r, v in listed.items() if any(w.startswith("electrical") for w in v["why_listed"]))
    out = {
        "board": f"native-21 stage {C.N} ({C.TAG})", "board_sha256": C.BOARD_SHA,
        "netlist_sha256": C.sha_file(C.N21 / "frozen/default.net"),
        "rule": C.rule_text(),
        "rules": sorted(set(rule.values())),
        "assignment": dict(sorted(asg.items())),
        "group_part_counts": {g: counts[g] for g in C.GIDS},
        "parts_total": len(asg),
        "new_since_19c": new_parts,
        "removed_since_19c": dict(sorted(removed.items())),
        "reassigned_since_19c": {r: list(v) for r, v in sorted(moved.items())},
        "listed_parts": listed,
        "electrically_ambiguous": ambiguous_e,
        "controls": ctl.rows,
    }
    h = C.write("assignment.json", out)
    print(f"parts {len(asg)}; per group {dict(sorted(counts.items()))}; new {len(new_parts)}; removed {len(removed)}; "
          f"reassigned {len(moved)}; listed {len(listed)}; electrically ambiguous {len(ambiguous_e)}; sha {h[:12]}")
    ctl.finish()


if __name__ == "__main__":
    main()
