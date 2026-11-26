#!/usr/bin/env python3
"""Gate: tab-metal-to-tab-metal gap between adjacent TO-247 FETs on different nets (OPEN-ITEMS S34).

    python3 -I tools/check_tab_gaps.py [--board FILE] [--lot-e1 FILE] [--out FILE]
    python3 -I tools/check_tab_gaps.py --selftest

The 3.2 mm functional-creepage rule on the board only sees copper pads. Once TO-247s are mounted, their exposed tab
metal (E1 wide, centred on the middle lead) is a second conductor pair that nothing checks. This gate reads the FET
positions and pad-2 (drain = tab) nets from the board file and, for every adjacent same-facing pair on different tab
nets, computes

    centred gap = pitch - E1 max
    worst gap   = centred gap - 2 x (sideways lead play + hole position tolerance)

and compares it with FUNCTIONAL_CREEPAGE_MM. Nothing is copied: the numbers come from s32_calc.py (which imports
bench_params / bench_mech and reads FUNCTIONAL_CREEPAGE_MM out of tools/write_rules.py).

Ratchet (gate on coverage, not on 0 FAIL): tools/check_tab_gaps_baseline.json lists the known-open failing pairs. Exit 0
only if the failing set is a subset of the baseline, no baseline pair got worse by > 0.001 mm, and the board's FET set
and tab nets equal what the baseline recorded. Exit 1 otherwise, 2 on a broken input or a failed reproduction control.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PS = HERE.parent                                                # zapote/power-stage-120v
S32_DIR = PS / "validation-results/11-candidates/s32-jlc-fets-m11"
BOARD = PS / "validation-results/08-manufacturing-package/native-21/board-of-record-s57/section.kicad_pcb"
BASELINE = HERE / "check_tab_gaps_baseline.json"
DEFAULT_OUT = HERE / "check_tab_gaps.json"
SCRATCH = Path("/private/tmp/claude-501/-Users-bennet-Desktop-temper/2d2f46d7-ab36-499d-918e-e892acf7fab8/scratchpad")
WORSEN_TOL = 0.001                                              # mm
SAME_ROW_TOL = 0.5                                              # mm: pad-2 centres closer than this across the tab-width axis
S32_TOL = 0.0005                                                # mm: reproduction of s32-calc.json (3-decimal rounding)

_spec = importlib.util.spec_from_file_location("s32_calc", S32_DIR / "s32_calc.py")
S32 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S32)                                   # module level only; s32's main() (which writes) is not run


# ------------------------------------------------------------------------------------------------ board reading
def _tokens(text: str):
    """Minimal KiCad s-expression tokenizer: '(' ')' atoms and quoted strings (returned as ('s', value))."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            yield ("s", text[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            yield text[i:j]
            i = j


def _parse(text: str):
    stack: list[list] = [[]]
    for t in _tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1] if isinstance(t, tuple) else t)
    return stack[0][0]


def _footprint_blocks(text: str):
    """Yield the source text of each top-level (footprint ...) block by quote-aware paren matching."""
    for m in re.finditer(r'^\t\(footprint "', text, re.M):
        start = m.start() + 1
        depth, i, n = 0, start, len(text)
        while i < n:
            c = text[i]
            if c == '"':
                i += 1
                while text[i] != '"':
                    i += 2 if text[i] == "\\" else 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break
            i += 1


def _child(node, key):
    return next((c for c in node if isinstance(c, list) and c and c[0] == key), None)


def read_fets(board_text: str) -> list[dict]:
    """Every TO-247 footprint: ref, position, rotation, layer, pad-2 absolute centre and net, tab-width axis."""
    fets = []
    for block in _footprint_blocks(board_text):
        if not re.match(r'\(footprint "[^"]*TO-?247', block):
            continue
        fp = _parse(block)
        ref = next(c[2] for c in fp if isinstance(c, list) and c[:2] == ["property", "Reference"])
        layer = _child(fp, "layer")[1]
        if layer != "F.Cu":
            raise SystemExit(f"check_tab_gaps: {ref} is on {layer}; only F.Cu TO-247s are modelled (extend before trusting)")
        at = _child(fp, "at")
        x, y = float(at[1]), float(at[2])
        rot = (float(at[3]) if len(at) > 3 else 0.0) % 360.0
        pad2 = next((c for c in fp if isinstance(c, list) and c[:2] == ["pad", "2"]), None)
        if pad2 is None:
            raise SystemExit(f"check_tab_gaps: {ref} has no pad 2")
        pat = _child(pad2, "at")
        px, py = float(pat[1]), float(pat[2])
        th = math.radians(rot)
        # KiCad file frame: y down, rotation positive counter-clockwise on screen
        ax = x + px * math.cos(th) + py * math.sin(th)
        ay = y - px * math.sin(th) + py * math.cos(th)
        net = _child(pad2, "net")[1]
        fets.append(dict(ref=ref, rot=rot, layer=layer, x=round(ax, 6), y=round(ay, 6), tab_net=net,
                         u=(round(math.cos(th), 9), round(-math.sin(th), 9))))
    return fets


# ------------------------------------------------------------------------------------------------ the physics (all from s32_calc)
def adjacent_pairs(fets: list[dict]) -> list[tuple[dict, dict, float]]:
    """Consecutive same-facing parts along their tab-width axis, derived from positions only.

    Parts with the same rotation and layer face the same way. They share a row when their pad-2 centres lie within
    SAME_ROW_TOL across the width axis; within a row, neighbours in order along the axis are adjacent."""
    pairs: list[tuple[dict, dict, float]] = []
    facing: dict[tuple, list[dict]] = {}
    for f in fets:
        facing.setdefault((f["rot"], f["layer"]), []).append(f)
    for group in facing.values():
        ux, uy = group[0]["u"]
        along = lambda g: g["x"] * ux + g["y"] * uy            # noqa: E731
        across = lambda g: -g["x"] * uy + g["y"] * ux          # noqa: E731
        rows: list[list[dict]] = []
        for g in sorted(group, key=across):
            if rows and abs(across(g) - across(rows[-1][-1])) < SAME_ROW_TOL:
                rows[-1].append(g)
            else:
                rows.append([g])
        for row in rows:
            row.sort(key=along)
            pairs.extend((a, b, along(b) - along(a)) for a, b in zip(row, row[1:]))
    return pairs


def evaluate(fets: list[dict], e1_max: float) -> dict:
    """Per adjacent pair: centred gap, worst gap (flat and corner lead play), verdict against the functional creepage."""
    floor = S32.FUNC_CREEP
    x_flat = S32.X_PLAY                                         # FET_POS_TOL + HOLE_POS_TOL, bench_params
    x_corner = S32.BM.corner_play(S32.BM.hole_fin()[1], S32.T["c"][0], S32.T["b"][0]) + S32.P.HOLE_POS_TOL
    rows = []
    for a, b, pitch in adjacent_pairs(fets):
        centred = pitch - e1_max
        w_flat = centred - 2 * x_flat
        w_corner = centred - 2 * x_corner
        worst = min(w_flat, w_corner)
        row = dict(pair=f"{a['ref']}|{b['ref']}", nets=[a["tab_net"], b["tab_net"]], pitch_mm=round(pitch, 3),
                   centred_gap_mm=round(centred, 3), worst_gap_flat_play_mm=round(w_flat, 3),
                   worst_gap_corner_play_mm=round(w_corner, 3), worst_gap_mm=round(worst, 3), floor_mm=floor)
        if a["tab_net"] == b["tab_net"]:
            row["status"] = "SKIP_SAME_NET"
        else:
            row["status"] = "PASS" if worst >= floor - 1e-9 else "FAIL"   # 1e-9: float noise at the exact limit
        rows.append(row)
    return dict(pairs=rows, e1_max_mm=e1_max, floor_mm=floor, x_play_flat_mm=round(x_flat, 4),
                x_play_corner_mm=round(x_corner, 4),
                e1_limit_mm=round(18.0 - floor - 2 * x_flat, 3))


# ------------------------------------------------------------------------------------------------ ratchet
def ratchet(ev: dict, fets: list[dict], baseline: dict) -> dict:
    """Compare the evaluation with the committed baseline. Returns the findings; exit code is 1 if any list is non-empty."""
    known = baseline["known_open"]
    fail = {r["pair"]: r for r in ev["pairs"] if r["status"] == "FAIL"}
    found = dict(
        new_failures=sorted(p for p in fail if p not in known),
        worse=sorted(p for p in fail if p in known and fail[p]["worst_gap_mm"] < known[p]["worst_gap_mm"] - WORSEN_TOL),
        fet_set=[], nets=[], pair_set=[], stale=sorted(p for p in known if p not in fail))
    board_nets = {f["ref"]: f["tab_net"] for f in fets}
    base_nets = baseline["fets"]
    found["fet_set"] = sorted(set(board_nets) ^ set(base_nets))
    found["nets"] = sorted(r for r in board_nets if r in base_nets and board_nets[r] != base_nets[r])
    found["pair_set"] = sorted(set(r["pair"] for r in ev["pairs"]) ^ set(baseline["pairs_checked"]))
    for p, ent in known.items():
        if p in fail and ent["nets"] != fail[p]["nets"]:
            found["nets"].append(p)
    found["ok"] = not (found["new_failures"] or found["worse"] or found["fet_set"] or found["nets"] or found["pair_set"])
    return found


def cross_check_expected(fets: list[dict]) -> list[str]:
    """Hard-coded expectation (bench_params) vs the board: positions and tab nets. Fails loudly if the board moves."""
    errs = []
    P = S32.P
    by = {f["ref"]: f for f in fets}
    for ref, x in P.FET_X.items():
        f = by.get(ref)
        if f is None:
            errs.append(f"{ref} missing from the board")
            continue
        if abs(f["x"] - x) > 0.005:
            errs.append(f"{ref} tab x {f['x']} != bench_params.FET_X {x}")
        if f["tab_net"] != P.TAB_NET[ref]:
            errs.append(f"{ref} pad-2 net {f['tab_net']} != bench_params.TAB_NET {P.TAB_NET[ref]}")
    return errs


def reproduce_s32(ev: dict) -> list[str]:
    """Control: the gate's numbers must equal the committed s32-calc.json tab_to_tab rows (datasheet E1 max only)."""
    errs = []
    committed = json.loads((S32_DIR / "s32-calc.json").read_text())["tab_to_tab"]
    mine = {r["pair"]: r for r in ev["pairs"]}
    for c in committed:
        a, b = (re.match(r"(\w+)\(", s).group(1) for s in c["pair"].split("-"))
        r = mine.get(f"{a}|{b}")
        if r is None:
            errs.append(f"s32-calc.json pair {c['pair']} not found by the gate")
            continue
        for mk, ck in (("pitch_mm", "pitch"), ("centred_gap_mm", "metal_gap_centred_E1max"),
                       ("worst_gap_flat_play_mm", "metal_gap_worst_flat_play"),
                       ("worst_gap_corner_play_mm", "metal_gap_worst_corner_play")):
            if abs(r[mk] - c[ck]) > S32_TOL:
                errs.append(f"{r['pair']} {mk} {r[mk]} != s32-calc.json {ck} {c[ck]}")
    return errs


# ------------------------------------------------------------------------------------------------ driver
def load_e1(lot_file: Path | None) -> tuple[float, str]:
    e1 = S32.T["E1"][1]
    if lot_file is None:
        return e1, "datasheet max"
    d = json.loads(lot_file.read_text())
    v = d.get("e1_max_mm", d.get("E1_max"))
    if not isinstance(v, (int, float)) or not 10.0 < v < 20.0:
        raise SystemExit(f"check_tab_gaps: {lot_file} needs a numeric e1_max_mm in (10, 20)")
    return float(v), f"lot measurement ({lot_file.name}, datasheet max {e1})"


def run(board: Path, baseline: dict, e1: float, e1_src: str, quiet: bool = False) -> tuple[int, dict]:
    text = board.read_text()
    fets = read_fets(text)
    ev = evaluate(fets, e1)
    found = ratchet(ev, fets, baseline)
    exp = cross_check_expected(fets)
    ev.update(board=str(board.relative_to(PS)) if board.is_relative_to(PS) else board.name, board_sha256=hashlib.sha256(board.read_bytes()).hexdigest(), e1_source=e1_src,
              fets=[{k: f[k] for k in ("ref", "x", "y", "rot", "tab_net")} for f in fets], ratchet=found,
              expected_cross_check_errors=exp)
    code = 0 if found["ok"] and not exp else 1
    if not quiet:
        report(ev, found, exp, baseline)
    return code, ev


def report(ev: dict, found: dict, exp: list[str], baseline: dict) -> None:
    print(f"Tab-to-tab metal gap, adjacent TO-247 pairs  (E1 max {ev['e1_max_mm']} mm, {ev['e1_source']})")
    print(f"  floor {ev['floor_mm']} mm (write_rules.FUNCTIONAL_CREEPAGE_MM); lead play flat {ev['x_play_flat_mm']} / corner "
          f"{ev['x_play_corner_mm']} mm per device; E1 that closes the 18.0 pitch: <= {ev['e1_limit_mm']} mm")
    print(f"  {'pair':8s} {'nets':16s} {'pitch':>7s} {'centred':>8s} {'worst':>7s}  status")
    for r in ev["pairs"]:
        print(f"  {r['pair']:8s} {'/'.join(r['nets']):16s} {r['pitch_mm']:7.3f} {r['centred_gap_mm']:8.3f} "
              f"{r['worst_gap_mm']:7.3f}  {r['status']}")
    for e in exp:
        print(f"  EXPECTATION MISMATCH: {e}")
    for key, label in (("new_failures", "NEW failing pair (not in baseline)"), ("worse", "baseline pair got worse"),
                       ("fet_set", "FET set differs from baseline"), ("nets", "tab nets differ from baseline"),
                       ("pair_set", "adjacent-pair set differs from baseline")):
        for p in found[key]:
            print(f"  RATCHET FAIL: {label}: {p}")
    for p in found["stale"]:
        print(f"  note: baseline pair {p} now passes; remove it from check_tab_gaps_baseline.json to tighten the ratchet")
    known = [p for p in baseline["known_open"] if p not in found["stale"]]
    if known:
        print(f"  S34 is OPEN: {', '.join(known)} below {ev['floor_mm']} mm at worst lead play (baseline {baseline['open_item']}).")
        print(f"  Closes when the lot's E1 max <= {ev['e1_limit_mm']} mm (--lot-e1), or a barrier between tabs, or the certifier fault route.")
    elif baseline["known_open"]:
        print("  S34: every baseline pair passes now. Empty known_open in the baseline to close it.")
    else:
        print("  S34 closed: no failing pair, empty baseline.")
    print("  RESULT:", "OK (failing set within baseline)" if found["ok"] and not exp else "FAIL")


# ------------------------------------------------------------------------------------------------ selftest
def _move_fet(text: str, ref: str, dx: float) -> str:
    """Move one footprint by dx in x by editing its own (at x y) line; only inside that footprint's block."""
    i = text.index(f'(property "Reference" "{ref}"')
    j = text.rindex('(footprint "', 0, i)
    m = re.compile(r"\(at ([-\d.]+) ([-\d.]+)((?: [-\d.]+)?)\)").search(text, j)
    new = f"(at {float(m.group(1)) + dx:g} {m.group(2)}{m.group(3)})"
    return text[:m.start()] + new + text[m.end():]


def selftest() -> int:
    baseline = json.loads(BASELINE.read_text())
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sha0 = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    e1 = S32.T["E1"][1]
    results = []

    def check(name: str, cond: bool, detail: str) -> None:
        results.append(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {detail}")

    # (0) the real board with the real baseline is exit 0 and reproduces S32
    code, ev = run(BOARD, baseline, e1, "datasheet max", quiet=True)
    errs = reproduce_s32(ev)
    check("0 real board", code == 0 and not errs, f"exit {code}; S32 reproduction errors: {errs or 'none'}")

    fets = read_fets(BOARD.read_text())

    def synth(pitch: float, net_a: str, net_b: str):
        a = dict(ref="QX1", rot=0.0, layer="F.Cu", x=200.0, y=100.0, tab_net=net_a, u=(1.0, -0.0))
        b = dict(ref="QX2", rot=0.0, layer="F.Cu", x=200.0 + pitch, y=100.0, tab_net=net_b, u=(1.0, -0.0))
        bl = json.loads(json.dumps(baseline))
        bl["fets"].update({"QX1": net_a, "QX2": net_b})
        bl["pairs_checked"] = bl["pairs_checked"] + ["QX1|QX2"]
        return fets + [a, b], bl

    # (a) 17.0 mm pitch, different nets: NEW failure, exit 1 (baseline otherwise made to match the synthetic FET set)
    f, bl = synth(17.0, "bus_p", "sw_b")
    evx = evaluate(f, e1)
    found = ratchet(evx, f, bl)
    check("a 17.0 mm pitch, different nets", "QX1|QX2" in found["new_failures"] and not found["ok"],
          f"new_failures {found['new_failures']}, exit {0 if found['ok'] else 1}")
    # (b) same net: skipped
    f, bl = synth(17.0, "bus_p", "bus_p")
    evx = evaluate(f, e1)
    row = next(r for r in evx["pairs"] if r["pair"] == "QX1|QX2")
    found = ratchet(evx, f, bl)
    check("b same tab net", row["status"] == "SKIP_SAME_NET" and "QX1|QX2" not in found["new_failures"] and found["ok"],
          f"status {row['status']}, exit {0 if found['ok'] else 1}")
    # (c) lot E1 13.70 closes both pairs
    lot = SCRATCH / "selftest-lot-e1.json"
    lot.write_text(json.dumps({"e1_max_mm": 13.70}))
    e1_lot, src = load_e1(lot)
    code, evl = run(BOARD, baseline, e1_lot, src, quiet=True)
    wg = {r["pair"]: r["worst_gap_mm"] for r in evl["pairs"]}
    check("c --lot-e1 13.70", code == 0 and wg["Q5|Q6"] >= 3.2 and wg["Q3|Q2"] >= 3.2
          and all(r["status"] != "FAIL" for r in evl["pairs"]),
          f"worst gap Q5|Q6 {wg['Q5|Q6']}, Q3|Q2 {wg['Q3|Q2']}, stale baseline pairs {evl['ratchet']['stale']}")
    # (c2) the boundary: E1 13.72 sits exactly on the floor, 13.73 fails
    ev_edge = {r["pair"]: r["status"] for r in evaluate(fets, 13.72)["pairs"]}
    ev_over = {r["pair"]: r["status"] for r in evaluate(fets, 13.73)["pairs"]}
    check("c2 E1 boundary 13.72 / 13.73", ev_edge["Q5|Q6"] == "PASS" and ev_over["Q5|Q6"] == "FAIL",
          f"13.72 -> {ev_edge['Q5|Q6']}, 13.73 -> {ev_over['Q5|Q6']}")
    # (d) a board copy with one FET 1 mm closer
    for ref, pair in (("Q6", "Q5|Q6"), ("Q2", "Q3|Q2")):
        moved = SCRATCH / f"selftest-board-{ref}-closer.kicad_pcb"
        shutil.copyfile(BOARD, moved)
        # Q6 moves toward Q5 (-x); Q2 moves toward Q3 (-x)
        moved.write_text(_move_fet(moved.read_text(), ref, -1.0))
        code, evm = run(moved, baseline, e1, "datasheet max", quiet=True)
        w = next(r for r in evm["pairs"] if r["pair"] == pair)["worst_gap_mm"]
        check(f"d {ref} moved 1 mm closer", code == 1 and pair in evm["ratchet"]["worse"],
              f"{pair} worst {w} (baseline {baseline['known_open'][pair]['worst_gap_mm']}), exit {code}, worse {evm['ratchet']['worse']}")
    # (e) a pair that passes in the baseline never gets masked: Q6|Q3 pulled to 12 mm fails as NEW
    moved = SCRATCH / "selftest-board-Q3-closer.kicad_pcb"
    shutil.copyfile(BOARD, moved)
    moved.write_text(_move_fet(moved.read_text(), "Q3", -10.1))
    code, evm = run(moved, baseline, e1, "datasheet max", quiet=True)
    check("e Q3 moved 10.1 mm toward Q6", code == 1 and "Q6|Q3" in evm["ratchet"]["new_failures"],
          f"new_failures {evm['ratchet']['new_failures']}, exit {code}")
    # the real board file is untouched
    check("real board unmodified", hashlib.sha256(BOARD.read_bytes()).hexdigest() == sha0, f"sha256 {sha0[:12]}...")
    ok = all(results)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", type=Path, default=BOARD)
    ap.add_argument("--lot-e1", type=Path, help='JSON {"e1_max_mm": 13.70}: measured lot E1 max, replaces the datasheet max')
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--out", type=Path, help="default tools/check_tab_gaps.json (check_tab_gaps.lot.json with --lot-e1)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    baseline = json.loads(a.baseline.read_text())
    e1, src = load_e1(a.lot_e1)
    code, ev = run(a.board, baseline, e1, src)
    if not a.lot_e1:
        errs = reproduce_s32(ev)
        if errs:
            print("S32 REPRODUCTION CONTROL FAILED:\n  " + "\n  ".join(errs))
            return 2
        print("  control: gap numbers reproduce s32-calc.json tab_to_tab (pitch, centred, worst flat, worst corner) to 0.0005 mm")
    out = a.out or (HERE / "check_tab_gaps.lot.json" if a.lot_e1 else DEFAULT_OUT)
    out.write_text(json.dumps(ev, indent=1) + "\n")
    print(f"  wrote {out}")
    return code


if __name__ == "__main__":
    sys.exit(main())
