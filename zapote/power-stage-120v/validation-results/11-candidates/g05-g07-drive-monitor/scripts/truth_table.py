#!/usr/bin/env python3
"""Fail-safe truth tables for the BIAS_BAD chain: benchmark vs P1 vs P2.

    python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/truth_table.py
Writes ../results/truth_table.md and exits non-zero if an invariant breaks.

Logic-level model, 3 rails (LS, HS-A, HS-B). Per rail one of the states below. The analog effect of each state on the
monitor internals is given by hand from the schematic (f6_bias.ato RailMonitor) and is NOT simulated:

  OK          all four windows satisfied, 5 V LDO up
  NEG_UV/OV   SRC-N outside 1.80..2.21 V       -> a window comparator pulls 'good' low
  SPAN_UV/OV  P-N outside 16.2..17.9 V          -> a window comparator pulls 'good' low
  DEAD        P-N ~ 0 V: reference, comparators and 5 V LDO all dead
  LDO5_FAIL   P-N fine, 5 V LDO output 0 (ISO side 1 unpowered)
  TL431_OPEN  ref = P (17 V) -> halfref 8.5 V -> UV comparators see input << halfref -> pull low
  TL431_SHORT ref = 0 -> halfref 0 -> OV comparators see input > halfref -> pull low
  SLIVER      P-N between ~2.3 and ~3.0 V: LDO output >= ISO7710 UVLO (2.25 V) but below LM339B VCC min (3 V): comparator
              outputs are undefined (assumed released = 'good'), reference node ~2.4 V. NOT detected by the monitor in the
              benchmark either (see below); the driver's own UVLO (UCC21550 rising 6.5 V option A / 9.2 V option B, datasheet
              SLUSE89C p.1) holds both outputs low in this range.

Stages:
  benchmark: comparators -> 'good' pulled up by 1k from the 2.5 V reference -> D+NPN (needs ~1.4 V) -> IN pulled up to 5 V by 10 k
             (NPN on = IN low) -> ISO7710 (default HIGH) -> OUT=1 means BAD -> OR3 -> filter -> BIAS_BAD
  P1       : comparators release -> 'good' pulled to 5 V (10 k) -> SN74LVC1G10 as inverter -> ISO7710 IN (default HIGH) -> OR3 -> filter
  P2       : LS rail good-line as in P1 up to the comparators; HS rails: 'good' -> ISO6721FB (default LOW, side 2 on the LS 5 V) ;
             LS NAND3(good_LS, good_A, good_B) -> ISO7710 (default HIGH) IN -> OUT=1 means BAD -> filter (OR3 deleted)
"""
import itertools, os, sys
sys.dont_write_bytecode = True
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

STATES = ["OK", "NEG_UV", "NEG_OV", "SPAN_UV", "SPAN_OV", "DEAD", "LDO5_FAIL", "TL431_OPEN", "TL431_SHORT", "SLIVER"]

def internals(state):
    """-> dict(comps_release, ref_hi, v5_ok)  (comps_release: every comparator output released = no pull-down)"""
    return dict(
        comps_release=state in ("OK", "DEAD", "SLIVER", "LDO5_FAIL"),   # DEAD: LM339 unpowered, outputs high-Z
        ref_hi=state not in ("DEAD",),
        v5_ok=state not in ("DEAD", "LDO5_FAIL"),
    )

def benchmark_rail_bad(state):
    i = internals(state)
    npn_on = i["comps_release"] and i["ref_hi"]
    isoin = 0 if npn_on else 1                     # IN pulled to 5 V when the NPN is off
    return isoin if i["v5_ok"] else 1              # ISO7710 side 1 unpowered -> default HIGH = bad

def p1_rail_bad(state):
    """P1: comparator wired-AND 'good' (pulled to 5 V when all released) -> SN74LVC1G10 as inverter -> ISO7710 IN (default HIGH)"""
    i = internals(state)
    isoin = 0 if i["comps_release"] else 1
    return isoin if i["v5_ok"] else 1

def p2_rail_good(state):
    """P2: positive-logic 'good' straight into the HS isolator / LS NAND3; ISO6721FB unpowered -> default LOW = not good"""
    i = internals(state)
    good = 1 if i["comps_release"] else 0
    return good if i["v5_ok"] else 0

def bench(states):  return int(any(benchmark_rail_bad(s) for s in states))
def p1(states):    return int(any(p1_rail_bad(s) for s in states))
def p2(states, ls_v5_ok=True):
    ls, a, b = states
    good_ls = p2_rail_good(ls)
    # ISO6721FB: side 1 powered by the HS 5 V LDO, side 2 by the LS 5 V LDO (assumed up here)
    good_a, good_b = p2_rail_good(a), p2_rail_good(b)
    nand = int(not (good_ls and good_a and good_b))
    ls_up = internals(ls)["v5_ok"] and ls_v5_ok
    return nand if ls_up else 1                    # ISO7710 side 1 (LS 5 V) unpowered -> default HIGH = bad

def dis_benchmark(permit, bias_bad):
    """permit in {1, 0, 'float'}: float is held low by the 100 k pull-down. PERMIT-FET on -> raw DIS low; else 330 ohm pull-up -> high."""
    gate = 1 if permit == 1 else 0
    dis_raw = 0 if gate else 1
    return int(dis_raw or bias_bad)

def dis_p3(permit, bias_good):
    gate = 1 if permit == 1 else 0                 # 100 ohm + 100 k pull-down, now the NAND2 input instead of a FET gate
    return int(not (gate and bias_good))

def dis_table():
    rows, viol = [], []
    for permit in (1, 0, "float"):
        for bad in (0, 1):
            b, n = dis_benchmark(permit, bad), dis_p3(permit, 0 if bad else 1)
            rows.append((permit, bad, b, n))
            if b != n or (b == 0) != (permit == 1 and bad == 0):
                viol.append((permit, bad, b, n))
    return rows, viol

def main():
    rows, viol = [], []
    for st in itertools.product(STATES, repeat=3):
        want_bad = any(s != "OK" for s in st)
        b, a1, a2 = bench(st), p1(st), p2(st)
        slv = any(s == "SLIVER" for s in st)
        for name, v in (("benchmark", b), ("P1", a1), ("P2", a2)):
            if want_bad and not v and not slv:
                viol.append((name, st))
            if not want_bad and v:
                viol.append((name + " nuisance", st))
        if (b, a1, a2) != (b, b, b) :
            viol.append(("variants disagree", st, (b, a1, a2)))
    # SLIVER: all three variants must behave identically (no regression), and each is allowed to miss it
    print(f"{len(STATES)**3} rail-state combinations checked.")
    print("violations:", viol if viol else "none")

    lines = ["# BIAS_BAD truth tables (generated by scripts/truth_table.py)", "",
             "Single-rail rows (the other two rails OK). 1 = BIAS_BAD asserted (drive disabled).", "",
             "| rail state | benchmark | P1 | P2 | expected |", "|---|:-:|:-:|:-:|:-:|"]
    for s in STATES:
        st = (s, "OK", "OK")
        exp = "0" if s == "OK" else ("1" if s != "SLIVER" else "1 wanted; missed by all three, driver UVLO holds gate low")
        lines.append(f"| {s} | {bench(st)} | {p1(st)} | {p2(st)} | {exp} |")
    lines += ["", "Same, fault in an HS rail only (HS-A = state, LS and HS-B OK):", "",
              "| HS-A state | benchmark | P1 | P2 |", "|---|:-:|:-:|:-:|"]
    for s in STATES:
        st = ("OK", s, "OK")
        lines.append(f"| {s} | {bench(st)} | {p1(st)} | {p2(st)} |")
    lines += ["", "Loss of the LS 5 V LDO (U37) while the LS rail is fine: ",
              f"benchmark {bench(('LDO5_FAIL','OK','OK'))}, P1 {p1(('LDO5_FAIL','OK','OK'))}, P2 {p2(('LDO5_FAIL','OK','OK'))}"
              " (P2: LS LDO also powers the HS isolators' side 2 and the NAND3; ISO7710 side 1 unpowered -> default HIGH -> BAD)."]

    # single-component 'stuck at the inactive level' (undetected-fault) exposure, counted by rails masked
    lines += ["", "## Single output-stuck-at-'good' fault: how many rails' faults it hides", "",
              "| component (stuck in the not-asserting state) | benchmark | P1 | P2 |", "|---|:-:|:-:|:-:|",
              "| per-rail ISO7710 (U32) | 1 | 1 | 3 (it carries the combined status) |",
              "| per-rail ISO7710 (U33/U34) | 1 each | 1 each | n/a (ISO6721FB, hides 1 each) |",
              "| OR3 / NAND3 (U25) | 3 | 3 | 3 |",
              "| BIAS_BAD filter Schmitt (U40), DIS-OR (U22/U23) | 3 / 3 per leg | 3 / 3 per leg | 3 / 3 per leg |",
              "", "P2 adds one more 3-rail common point (U32) to a chain that already has three (U25-class, U40, DIS-OR). "
              "No new common point in P1. Both are the same class as the benchmark's existing U25/U40 single points; "
              "a power-up self-test (BIAS_BAD must read 1 before the bias is enabled, 0 after) already exercises U32's high state "
              "but not a stuck-low fault: needs the FMEA."]
    drows, dviol = dis_table()
    lines += ["", "## Driver DIS (1 = outputs disabled), both UCC21550 DIS pins identical", "",
              "| PERMIT | BIAS_BAD | benchmark (FET + 330 ohm + OR2) | P3 (NAND2, BIAS_GOOD) |", "|---|:-:|:-:|:-:|"]
    lines += [f"| {p} | {b} | {x} | {y} |" for p, b, x, y in drows]
    lines += ["", "DIS is 0 (drive allowed) only for PERMIT high and BIAS_BAD low, in both. PERMIT low, floating (100 k pull-down) or BIAS_BAD high disable. "
              "V3V3 absent: UCC21550 VCCI is below UVLO (2.55-2.85 V rising, SLUSE89C), outputs are held low in both.",
              "Violations: " + (str(dviol) if dviol else "none")]
    viol += dviol
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "truth_table.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:22]))
    sys.exit(1 if viol else 0)

if __name__ == "__main__":
    main()
