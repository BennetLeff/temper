#!/usr/bin/env python3
"""Refuse S4 / S5 slew results with rows that have no switching edge inside the measurement window (stdlib only).

The gate-network harness (gn.py) and everything built on it (S6 study, b15, c55) measure the 20-80 % edge inside a fixed
window after the on command (0.75 us by default). With a slow turn-on network the commutation edge can fall after the
window: the row is still "complete", every c25 voltage screen passes, but `slew2080_Vns` is absent. A summary that takes the
max over the rows that have a value then under-reports the grid's edge without saying so. c55-device-trade section 1.3
found this: 144 of 336 CFD7 S4 rows at maximum Qrr had no edge, and the grid's 68.16 V/ns was really 68.58 V/ns.

Rule: a grid of complete S4 / S5 rows from a harness that measures `slew2080_Vns` gives a slew figure only if every one of
those rows has an edge. Otherwise the figure is refused; re-run the rows in the long window (gn.py `long=True`, c55 `s4L`).

Use:
  python3 -I s4_edges.py check FILE...   counts per file; exit 1 if any file has a row without an edge
  python3 -I s4_edges.py ratchet         every git-tracked result file under validation-results/ against
                                         s4_edges_known.json; exit 1 on an unregistered gapped file, a count that
                                         grew, or a registry entry that no longer matches (ratchet it down)
  from a script: load by path (python -I keeps the script's directory off sys.path), then
                 max_slew(rows) / require_edges(rows, where) / grid_report(rows)
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[1]                      # .../zapote/power-stage-120v
KNOWN = HERE / "s4_edges_known.json"
EDGE_CASES = ("S4", "S5")
SLEW = "slew2080_Vns"
# keys the slew-measuring harnesses write on every complete row; round17-era files carry none of them and are out of scope
MARKERS = (SLEW, "pass_dvdt96", "dvsw_abs")


class NoEdgeError(ValueError):
    pass


def load_rows(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = d.get("rows") if isinstance(d, dict) else d
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return None
    return rows


def measures_edges(rows):
    return any(k in r for r in rows for k in MARKERS)


def no_edge_rows(rows, cases=EDGE_CASES):
    """Complete rows of `cases` with no 20-80 % edge inside the window."""
    return [r for r in rows if r.get("case") in cases and r.get("status") == "complete" and r.get(SLEW) is None]


def counts(rows):
    return {c: len(no_edge_rows(rows, (c,))) for c in EDGE_CASES
            if any(r.get("case") == c and r.get("status") == "complete" for r in rows)}


def require_edges(rows, where="", cases=("S4",)):
    bad = no_edge_rows(rows, cases)
    if bad:
        r = bad[0]
        first = ", ".join(f"{k}={r.get(k)}" for k in ("case", "drv", "leg", "temp_C", "vbus", "dir", "dt_ns", "esl_nH"))
        raise NoEdgeError(f"{where}: {len(bad)} complete {'/'.join(cases)} row(s) have no 20-80 % edge in the window "
                          f"(first: {first}); the slew figure is refused, re-run these rows in the long window")


def max_slew(rows, case="S4", esl=None, where=""):
    """The grid's maximum 20-80 % slew for `case` (optionally one ESL), refused if any row of that case lacks an edge."""
    sel = [r for r in rows if r.get("case") == case and r.get("status") == "complete" and
           (esl is None or r.get("esl_nH") == esl)]
    if not sel:
        raise NoEdgeError(f"{where}: no complete {case} rows")
    require_edges(sel, where, (case,))
    return max(r[SLEW] for r in sel)


def grid_report(rows, case="S4"):
    """Summary fields for a results table: the count always, the slew only when every row has an edge."""
    sel = [r for r in rows if r.get("case") == case and r.get("status") == "complete"]
    n = len(no_edge_rows(sel, (case,)))
    out = {"no_edge_rows": n}
    if n:
        out["slew_refused"] = f"{n} of {len(sel)} {case} rows have no edge in the window; re-run in the long window"
    return out


def tracked_results():
    out = subprocess.run(["git", "-C", str(PS), "ls-files", "-z", "--", "validation-results/*.json"],
                         capture_output=True, text=True, check=True).stdout
    for rel in filter(None, out.split("\0")):
        p = PS / rel
        try:
            rows = load_rows(p)
        except (OSError, ValueError):
            continue
        if rows and measures_edges(rows):
            yield rel, rows


def ratchet(scan=None, known=None):
    """-> list of error strings (empty = pass)."""
    known = json.loads(KNOWN.read_text(encoding="utf-8")) if known is None else known
    reg = known.get("files", {})
    seen, errors = set(), []
    for rel, rows in (tracked_results() if scan is None else scan):
        c = {k: v for k, v in counts(rows).items() if v}
        if not c:
            if rel in reg:
                errors.append(f"{rel}: registered with {reg[rel]['counts']} but now has none; remove the entry")
            continue
        seen.add(rel)
        if rel not in reg:
            errors.append(f"{rel}: {c} row(s) without an edge, not registered; re-run in the long window "
                          f"(or register it in {KNOWN.name} with the reason its slew is not used)")
        elif c != reg[rel]["counts"]:
            errors.append(f"{rel}: no-edge rows {c} != registered {reg[rel]['counts']}")
    for rel in sorted(set(reg) - seen):
        if scan is None and not (PS / rel).is_file():
            errors.append(f"{rel}: registered but not found; remove the entry")
    return errors


def main(argv):
    if len(argv) >= 2 and argv[1] == "check":
        bad = 0
        for f in argv[2:]:
            rows = load_rows(f)
            if not rows or not measures_edges(rows):
                print(f"n/a   {f}: not a slew-measuring grid")
                continue
            c = counts(rows)
            bad += any(c.values())
            print(f"{'FAIL' if any(c.values()) else 'ok  '}  {f}: no-edge rows {c}")
        return 1 if bad else 0
    if len(argv) == 2 and argv[1] == "ratchet":
        errors = ratchet()
        for e in errors:
            print("FAIL", e)
        print("RESULT:", "FAIL" if errors else "PASS")
        return 1 if errors else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
