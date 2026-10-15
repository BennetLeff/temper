#!/usr/bin/env python3
"""Back-test of the scoped chain on real history: would it have reused a step whose scorecard entries changed?

    python3 -I backtest.py [--runs RUNS_DIR] [--kicad-py KP] [--out results.json]

Cases (git, this repository):
  * stage pairs - the candidate's tree (its records commit, which carries its card) against the tree it branched from
    (the parent of its stage commit) and the benchmark card of record there: s28->s29, s30->s31 (parts only),
    s35->s38, s38->s40, s40->s41, s41->s42, s42->s43;
  * re-score pairs - one stage's card re-written by a later commit (model, gate or desk change on the same build):
    the tree and card before against the tree and card after.
Board keys come from each card's build directory (net_keys.py on BUILD/section.kicad_pcb, whose SHA-256 must equal
the card's board_sha256); runs that no longer exist are reported, not guessed.

For every case the policy plan (scoped_lib.plan) and a strict plan (only the steps whose own reads changed, per the
13-coupling read sets) are computed. A MISS is a step the plan reuses (or a manual step it carries) whose card
entries differ between the two cards. Exit 1 on any policy-plan miss.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoped_lib as L  # noqa: E402

KP_DEFAULT = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
BENCH_DIR = "validation-results/10-benchmark"
VER = json.loads((L.UNIT / "validation-results/13-coupling/results/verification.json").read_text()) \
    if (L.UNIT / "validation-results/13-coupling/results/verification.json").exists() else None

STAGES = [  # (bench tag, cand tag, stage commit, records commit)
    ("s28", "s29", "1ee3b9d50", "1ee3b9d50"),
    ("s30", "s31", "38e856ef3", "38e856ef3"),
    ("s35", "s38", "7f1fe9d3a", "d5ffb67af"),
    ("s38", "s40", "95e24e554", "eab58d456"),
    ("s40", "s41", "57fc55409", "27f461868"),
    ("s41", "s42", "5ff4aded2", "139d6443c"),
    ("s42", "s43", "719084486", "cb7d7a76e"),
]
RESCORES = [  # (tag, card before, card after)
    ("s35", "65c6bd08e", "d98e7f570"), ("s35", "d98e7f570", "de794f21d"), ("s35", "de794f21d", "352efaf14"),
    ("s35", "352efaf14", "fc8e4fd33"), ("s38", "d5ffb67af", "f8cca7d21"), ("s38", "f8cca7d21", "59281e65a"),
    ("s42", "139d6443c", "bc326ab57"), ("s42", "bc326ab57", "3367e789b"), ("s42", "3367e789b", "710572d54"),
    ("s43", "cb7d7a76e", "dc074c47c"),
]


def card_at(commit: str, tag: str) -> dict | None:
    r = subprocess.run(["git", "-C", str(L.REPO), "show", f"{commit}:{L.PS}/{BENCH_DIR}/scorecard-native21{tag}.json"],
                       capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def netkeys(card: dict, cache: Path, kp: str) -> dict | None:
    b = Path(card["build"]) / "section.kicad_pcb"
    sha = card.get("board_sha256")
    f = cache / f"{(sha or 'none')[:16]}.json"
    if f.exists():
        return json.loads(f.read_text())
    if not b.exists() or hashlib.sha256(b.read_bytes()).hexdigest() != sha:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    subprocess.run([kp, str(Path(__file__).resolve().parent / "net_keys.py"), str(b), str(f)], capture_output=True)
    return json.loads(f.read_text()) if f.exists() else None


def reads_changed(step: str, bd: dict, bom: list[str]) -> bool:
    rd = L.STEPS[step].get("reads")
    if not rd or bd is None:
        return False
    nets, parts, anyb = set(), set(), False
    if rd.get("board") == "all":
        anyb = bd["copper_changed"] or bool(bd["parts_geom"])
    if rd.get("parts") == "all":
        anyb = anyb or bool(bd["parts_geom"] or bd["parts_value_only"])
    if rd.get("bom") == "all":
        anyb = anyb or bool(bd["parts_value_only"] or bom)
    for m in rd.get("verification_metrics", []):
        if VER and m in VER["reads"]:
            nets |= set(VER["reads"][m]["nets"])
            parts |= set(VER["reads"][m]["parts"])
    nets |= set(rd.get("net_fill", []))
    parts |= set(rd.get("parts_geom", []))
    return anyb or bool(nets & set(bd["nets_fill"])) or bool(parts & (set(bd["parts_geom"]) | set(bd["parts_value_only"]) | set(bom)))


def strict_plan(pl: dict, bd: dict, bom: list[str]) -> dict:
    """Steps whose own file inputs or board reads changed; keyed / manual steps as in the policy plan."""
    trig = {s for c in ("input", "build") for p, ss in pl["by_class"].get(c, {}).items() for s in ss}
    out = {}
    for s, v in L.STEPS.items():
        d = pl["steps"][s]
        if pl["mode"] == "FULL" or v["policy"] in ("keyed", "manual") or s == "card":
            out[s] = d
        elif v["policy"] == "rebuild":
            out[s] = d
        elif s in trig or reads_changed(s, bd, bom) or (s in ("core_exports", "copper_key", "heat_sources", "probe_erc") and pl["mode"] == "REBUILD"):
            out[s] = {"do": "RUN", "why": "reads changed" if s not in trig else "inputs changed"}
        else:
            out[s] = {"do": "REUSE", "why": "strict: reads unchanged"}
    return out


def judge(steps: dict, a: dict, b: dict, card_changed: bool) -> tuple[list, list, list, list]:
    """Over every card entry of either card: (misses, reused-and-unchanged, recomputed-and-changed, undetermined).
    A reused entry that differs is a MISS, unless scorecard.py / its desk inputs changed between the two trees: the
    scoped card then recomputes the entry from the reused outputs (or flags it stale), so the back-test cannot tell a
    formula change from a wrong reuse and lists it as undetermined."""
    miss, hit, moved, und = [], [], [], []
    for grp in ("gates", "performance", "cost"):
        for k in sorted(set(a.get(grp, {})) | set(b.get(grp, {}))):
            e = f"{grp}.{k}"
            x, y = a.get(grp, {}).get(k, "<absent>"), b.get(grp, {}).get(k, "<absent>")
            d = L.entry_decision(e, steps)
            row = {"entry": e, "producers": L.producers(e), "do": d["do"], "bench": x, "cand": y}
            if d["do"] == "REUSE":
                if x == y:
                    hit.append(row)
                elif card_changed:
                    und.append(row)
                else:
                    miss.append(row)
            elif x != y:
                moved.append(row)
    return miss, hit, moved, und


def run_case(name, base, cand, bench_card, cand_card, kp, cache):
    bt, ct = L.Tree(base), L.Tree(cand)
    paths = L.effective_changes(bt, ct, L.changed_paths(bt, ct))
    nb, nc = netkeys(bench_card, cache, kp), netkeys(cand_card, cache, kp)
    bd = L.board_diff(nb, nc) if nb and nc else None
    bom = L.bom_diff(bt.read("native-21/frozen/default.csv"), ct.read("native-21/frozen/default.csv"))
    kb = L.step_keys(bt, nb)["keys"] if nb else None
    kc = L.step_keys(ct, nc)["keys"] if nc else None
    pl = L.plan(paths, kb, kc, bd, rebuilt_board_differs=(bench_card["board_sha256"] != cand_card["board_sha256"]),
                cand_tag=cand_card["tag"])
    sp = strict_plan(pl, bd, bom) if bd else None
    card_changed = any("card" in ss for c in ("input",) for ss in pl["by_class"].get(c, {}).values())
    miss, hit, moved, und = judge(pl["steps"], bench_card, cand_card, card_changed)
    smiss, shit, _, sund = judge(sp, bench_card, cand_card, card_changed) if sp else ([], [], [], [])
    cls = L.input_classes(pl["by_class"], bd, bom)
    wall = lambda st: sum((L.STEPS[s]["wall_s"] or 0) for s, d in st.items() if d["do"] in ("RUN", "RUN?"))
    return {"case": name, "base": base, "cand": cand, "mode": pl["mode"], "input_classes": cls,
            "paths": {c: sorted(v) for c, v in pl["by_class"].items()},
            "board_diff": None if bd is None else {k: (v if not isinstance(v, list) else {"n": len(v), "items": v[:40]}) for k, v in bd.items()},
            "board_keys_available": bool(bd), "bom_changed": bom,
            "plan": {s: d for s, d in pl["steps"].items()},
            "reused": sorted(s for s, d in pl["steps"].items() if d["do"] == "REUSE"),
            "run": sorted(s for s, d in pl["steps"].items() if d["do"] in ("RUN", "RUN?")),
            "stale": sorted(s for s, d in pl["steps"].items() if d["do"] == "STALE"),
            "strict_reused": sorted(s for s, d in (sp or {}).items() if d["do"] == "REUSE"),
            "misses": miss, "strict_misses": smiss, "reused_entries_checked": len(hit), "strict_entries_checked": len(shit),
            "undetermined": und, "strict_undetermined": sund, "card_inputs_changed": card_changed,
            "recomputed_entries_that_moved": moved,
            "step_seconds_run": wall(pl["steps"]), "step_seconds_strict": wall(sp) if sp else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kicad-py", default=KP_DEFAULT)
    ap.add_argument("--cache", default=str(Path(__file__).resolve().parent / "backtest-netkeys"))
    ap.add_argument("--out")
    a = ap.parse_args()
    cache = Path(a.cache)
    res = []
    for bt, ctag, stage, rec in STAGES:
        base = f"{stage}~1"
        bc, cc = card_at(base, bt), card_at(rec, ctag)
        if not bc or not cc:
            res.append({"case": f"{bt}->{ctag}", "error": "card missing"}); continue
        res.append(run_case(f"{bt}->{ctag}", base, rec, bc, cc, a.kicad_py, cache))
    for tag, c0, c1 in RESCORES:
        bc, cc = card_at(c0, tag), card_at(c1, tag)
        res.append(run_case(f"{tag} re-score {c0[:9]}->{c1[:9]}", c0, c1, bc, cc, a.kicad_py, cache))
    nmiss = sum(len(r.get("misses", [])) for r in res)
    for r in res:
        if "error" in r:
            print(r["case"], r["error"]); continue
        print(f"{r['case']:34s} {r['mode']:11s} keys={'y' if r['board_keys_available'] else 'n'} "
              f"reuse={','.join(r['reused']) or '-'} stale={','.join(r['stale']) or '-'} "
              f"miss={len(r['misses'])} strict_miss={len(r['strict_misses'])} checked={r['reused_entries_checked']}/{r['strict_entries_checked']} "
              f"undetermined={len(r['undetermined'])}/{len(r['strict_undetermined'])}")
        print("   strict reuse:", ",".join(r["strict_reused"]) or "-")
        print("   classes:", "; ".join(r["input_classes"]))
        for m in r["misses"]:
            print("   MISS", m)
        for m in r["strict_misses"]:
            print("   strict miss", m)
        for m in r["undetermined"] + [x for x in r["strict_undetermined"] if x not in r["undetermined"]]:
            print("   undetermined (scorecard changed)", m)
    if a.out:
        Path(a.out).write_text(json.dumps({"cases": res, "policy_misses": nmiss,
                                            "strict_misses": sum(len(r.get("strict_misses", [])) for r in res)}, indent=1) + "\n")
    print(f"policy-plan misses: {nmiss}")
    raise SystemExit(1 if nmiss else 0)


if __name__ == "__main__":
    main()
