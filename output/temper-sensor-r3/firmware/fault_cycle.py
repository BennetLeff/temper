"""DECISIONS.md D-FCYC (open item 3): MAX31865 manual fault-detection timing on the CR-1 board.

The board (zapote/controller C37, sensor-r3 CR-1, as built at controller-c1-crs
467917c38, `checks-as-built.json` "no difference from the change request") puts a
two-stage differential RC between J3 and RTDIN+/- (1.00 k / 100 nF C0G / 1.00 k /
100 nF C0G, 1 nF C0G from each pin to ground), 220 nF X7R on every J3 pin, the
499 k open-lead pull-ups, the 100 k / 10 nF window branch and the CR-3 runaway
divider on the connector side. C37 tells firmware not to use the automatic
fault-detection cycle and to use the manual one with a 5 ms wait.

The MAX31865 data sheet (19-6478 Rev 3, datasheets/max31865.pdf):
  "If the external RTD interface circuitry includes an input filter with a time
   constant greater than 100 us, the fault detection cycle timing should be
   controlled in the manual mode operation."  (Fault Detection Cycle (D3:D2))
  Manual: "first ensure that VBIAS has been on for at least 5 time constants.
   Next, write 100X100Xb ... [checks with FORCE- closed, then FORCE- opens] ...
   Again, wait at least 5 time constants, and then write 100X110Xb ... [checks with
   FORCE- open; FORCE- closes] ... D[3:2] self-clear to 00b."
  Comparisons (Fault Status bits): D5 REFIN- > 85 % VBIAS (FORCE- closed),
   D4 REFIN- < 85 % VBIAS (FORCE- open), D3 RTDIN- < 85 % VBIAS (FORCE- open).
  "after a fault detection cycle ... always allow for the settling time of the
   input filter before restarting the ADC ... at least five time constants plus an
   additional 1 ms" (Applications Information); Note 4: "For 15-bit settling, a wait
   of at least 10.5 time constants of the input RC network is required."
  Automatic cycle: 100 us internal delays, 550 us typ / 600 us max total
   (Electrical Characteristics, "Automatic Fault Detection Cycle Time").

This script takes the network from pcb/checks.py (build(), DESIGNS["proposed"], the
PCB agent's MNA model of exactly these parts, unchanged) and:
  1. assembles the descriptor system C dx/dt + G x = b for FORCE- closed and open,
     at every tolerance corner (filter C +/-5 % C0G, J3 caps +/-10 % X7R, CM caps
     +/-5 %, filter R +/-0.1 %, pull-ups +/-1 %, the unspecified FORCE- switch
     0.5 / 10 / 20 ohm, leads 0.9 / 1.1 x, element at -40 / 25 / 250 / 360 degC)
     and takes the slowest finite pole: tau_max;
  2. integrates the transients (backward Euler, 1 us) of the manual sequence:
     VBIAS on from rest, step 1 (FORCE- closed, D5), FORCE- open, step 2 (D4, D3),
     FORCE- closed, conversions restart; and finds, at the worst corner, the
     shortest waits that give a healthy element no fault bit and an open/shorted
     input its bit;
  3. runs the automatic cycle's 100 us timing on the same transients (it
     false-flags a healthy element: the evidence that it is invalid here);
  4. sets the firmware waits: step wait = max(5 ms (C37 / CR-7 floor),
     5 x tau_max, 2 x the worst required), restart wait = max(step wait,
     5 x tau_max + 1 ms, 10.5 x tau_max), rounded up to 0.5 ms; and gates them
     against firmware/components/sensors/include/rtd_service.h;
  5. writes the mock's analog model (firmware/components/temper_hal/mock/
     mock_max31865_afe.h, generated, deterministic): the per-input DC ratios of
     REFIN- and RTDIN- to VBIAS in each switch state from the MNA, and a single
     first-order time constant tau_mock chosen so that the mock reaches each 85 %
     comparator decision no sooner than the worst MNA corner does.

Writes fault-cycle.json. Run: python3 fault_cycle.py
"""
from __future__ import annotations

import itertools
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import scipy.linalg as sla

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "pcb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_compare as EC  # noqa: E402  (reference_platform on the evidence written)
import checks as K  # noqa: E402  (pcb/checks.py: MNA network of the CR-1 board)

RTD_H = REPO / "firmware" / "components" / "sensors" / "include" / "rtd_service.h"
MOCK_H = REPO / "firmware" / "components" / "temper_hal" / "mock" / "mock_max31865_afe.h"
DT = 1e-6
COMP = 0.85                      # data sheet: the fault comparators' 85 % x VBIAS
FLOOR_MS = 5.0                   # C37 / CR-7 / REQUIREMENTS R3.4: >= 5 ms between steps
AUTO_DELAY_S = 100e-6            # data sheet: the automatic cycle's internal delays
TEMPS = (-40.0, 25.0, 250.0, 360.0)
RSW = (0.5, 10.0, 20.0)          # FORCE- switch: not specified by the vendor (checks.py R_SW)
DESIGN = K.DESIGNS["proposed"]

# An open S- lead is not a fault-cycle condition on this board: RTDIN- is pulled to
# 0.894 VBIAS by the connector-side 499 k pull-up and the CR-3 runaway divider, above the
# 85 % comparator, while RTDIN+ sits at the element's voltage. The conversion then reads
# a negative difference, code 0 (RTD Low threshold: FAULT_PROBE_SHORT on the first
# conversion), and the hardware window trips in 13 ms (CR-1, pcb/checks.json).
NOT_A_CYCLE_CONDITION = ("sense_n_open",)

# Input conditions modelled for the mock and for detection (checks.py build() faults).
CASES = {
    "healthy": {},
    "element_open": {"elem_open": True},
    "sense_n_open": {"Sn_open": True},
    "force_p_open": {"Fp_open": True},
    "force_n_open": {"Fn_open": True},
    "sense_n_to_gnd": {"to_gnd": ["Sn"]},
    "force_p_to_gnd": {"to_gnd": ["Fp"]},
}


def net_for(rtd, rsw, lead_scale, ctol, faults, vb, switch_closed):
    d = dict(DESIGN)
    d["c1"] = DESIGN["c1"] * (1 + ctol["c1"])
    d["c2"] = DESIGN["c2"] * (1 + ctol["c2"])
    tol = {"cj_Fp": ctol["cj"], "cj_Sp": ctol["cj"], "cj_Sn": ctol["cj"], "cj_Fn": ctol["cj"],
           "ccmp": ctol["ccm"], "ccmn": ctol["ccm"], "r1p": ctol["r"], "r1n": -ctol["r"],
           "r2p": ctol["r"], "r2n": -ctol["r"], "rb": ctol["rb"]}
    f = dict(faults)
    if not switch_closed:
        f["fn_switch_open"] = True
    leads = {k: K.R_LEAD * lead_scale for k in ("Fp", "Sp", "Sn", "Fn")}
    return K.build(d, rtd, vb=vb, leads=leads, tol=tol, rsw=rsw, faults=f)


def matrices(net, names):
    """G, C, b over the node list `names` (ground excluded) plus one row per V source."""
    idx = {n: i for i, n in enumerate(names)}
    vs = [e for e in net.el if e[0] == "V"]
    inv = {v: k for k, v in net.nodes.items()}
    m = len(names) + len(vs)
    G = np.zeros((m, m))
    C = np.zeros((m, m))
    b = np.zeros(m)

    def ix(node_num):
        name = inv[node_num]
        return None if name == "0" else idx[name]

    k = len(names)
    for typ, a, bb, v in net.el:
        ia, ib = ix(a), ix(bb)
        if typ in ("Y", "C"):
            M = G if typ == "Y" else C
            for p, q, s in ((ia, ia, 1), (ib, ib, 1), (ia, ib, -1), (ib, ia, -1)):
                if p is not None and q is not None:
                    M[p, q] += s * v
        elif typ == "I":
            if ia is not None:
                b[ia] -= v
            if ib is not None:
                b[ib] += v
        else:
            if ia is not None:
                G[ia, k] += 1
                G[k, ia] += 1
            if ib is not None:
                G[ib, k] -= 1
                G[k, ib] -= 1
            b[k] = v
            k += 1
    return G, C, b


class System:
    """One corner and input case: the closed/open networks on a common node list."""

    def __init__(self, rtd, rsw, lead_scale, ctol, faults):
        self.args = (rtd, rsw, lead_scale, ctol, faults)
        nets = {(sw, vb): net_for(rtd, rsw, lead_scale, ctol, faults, vb, sw)
                for sw in (True, False) for vb in (0.0, K.VB_NOM)}
        names = sorted({n for nt in nets.values() for n in nt.nodes if n != "0"})
        self.names = names
        self.idx = {n: i for i, n in enumerate(names)}
        self.mats = {key: matrices(nt, names) for key, nt in nets.items()}
        self.n = len(names)

    def dc(self, sw, vb):
        G, C, b = self.mats[(sw, vb)]
        # nodes that only touch removed elements have empty rows: pin them to 0
        Gp = G.copy()
        for i in range(G.shape[0]):
            if not np.any(Gp[i]) and not np.any(C[i]):
                Gp[i, i] = 1.0
        return np.linalg.lstsq(Gp, b, rcond=None)[0]

    def step_matrix(self, sw, vb):
        G, C, b = self.mats[(sw, vb)]
        A = G + C / DT
        for i in range(A.shape[0]):
            if not np.any(A[i]):
                A[i, i] = 1.0
        return np.linalg.inv(A), C / DT, b

    def run(self, x0, sw, vb, t_end, probes):
        """Backward Euler from node state x0 (len n); returns {probe: array}, final x."""
        Ai, Cd, b = self.step_matrix(sw, vb)
        m = Ai.shape[0]
        x = np.zeros(m)
        x[: self.n] = x0[: self.n]
        steps = int(round(t_end / DT))
        out = {p: np.empty(steps) for p in probes}
        pi = {p: self.idx[p] for p in probes}
        for s in range(steps):
            x = Ai @ (b + Cd @ x)
            for p in probes:
                out[p][s] = x[pi[p]]
        return out, x

    def poles(self, sw):
        G, C, _ = self.mats[(sw, K.VB_NOM)]
        w = sla.eigvals(-G, C)
        w = w[np.isfinite(w)]
        w = w[np.abs(w) < 1e9]
        return np.sort(-1.0 / w.real)[::-1]


def corners():
    for rtd_t, rsw, ls, c1, c2, cj, ccm, r, rb in itertools.product(
            TEMPS, RSW, (0.9, 1.1), (-0.05, 0.05), (-0.05, 0.05), (-0.10, 0.10), (-0.05, 0.05),
            (-0.001, 0.001), (-0.01, 0.01)):
        yield {"T_C": rtd_t, "rsw": rsw, "lead_scale": ls,
               "ctol": {"c1": c1, "c2": c2, "cj": cj, "ccm": ccm, "r": r, "rb": rb}}


def first_time(arr, cond):
    """First index (s) from which cond holds for the rest of the record."""
    ok = cond(arr)
    bad = np.nonzero(~ok)[0]
    if len(bad) == 0:
        return 0.0
    if bad[-1] == len(arr) - 1:
        return math.inf
    return (bad[-1] + 1) * DT


def sequence(sysm, t_on, t_open, t_close):
    """VBIAS on from rest (switch closed) for t_on, open for t_open, closed again for t_close.
    Returns the probe waveforms of each phase."""
    probes = ["REFN", "Ap", "An", "BIAS"]
    x_rest = sysm.dc(True, 0.0)
    on, x1 = sysm.run(x_rest, True, K.VB_NOM, t_on, probes)
    op, x2 = sysm.run(x1, False, K.VB_NOM, t_open, probes)
    cl, _ = sysm.run(x2, True, K.VB_NOM, t_close, probes)
    return on, op, cl


def bits_at(on, op, t1, t2, vb=K.VB_NOM):
    """Fault bits of a cycle with step 1 at t1 after VBIAS on, step 2 at t2 after FORCE- opens."""
    i1 = min(int(round(t1 / DT)) - 1, len(on["REFN"]) - 1)
    i2 = min(int(round(t2 / DT)) - 1, len(op["REFN"]) - 1)
    bits = 0
    if on["REFN"][i1] > COMP * vb:
        bits |= 0x20
    if op["REFN"][i2] < COMP * vb:
        bits |= 0x10
    if op["An"][i2] < COMP * vb:
        bits |= 0x08
    return bits


def analyse():
    taus = []
    req = {"healthy_open_settle_s": 0.0, "detect_element_open_vbias_s": 0.0, "restart_15bit_s": 0.0}
    worst = {}
    auto_false = []
    n = 0
    T_ON, T_OPEN, T_CLOSE = 12e-3, 12e-3, 12e-3
    lsb = 1.0 / 32768
    dc_tables = {}
    for c in corners():
        rtd = K.pt(c["T_C"])
        h = System(rtd, c["rsw"], c["lead_scale"], c["ctol"], {})
        n += 1
        for sw in (True, False):
            p = h.poles(sw)
            taus.append((float(p[0]), sw, c))
        # transients are run on a sub-grid (every tolerance at its slow/fast extreme), the
        # pole search covers every corner
        slow = all(c["ctol"][k] > 0 for k in ("c1", "c2", "cj", "ccm"))
        fast = all(c["ctol"][k] < 0 for k in ("c1", "c2", "cj", "ccm"))
        if not (slow or fast) or c["ctol"]["r"] < 0 or c["ctol"]["rb"] < 0:
            continue
        on, op, cl = sequence(h, T_ON, T_OPEN, T_CLOSE)
        vb = K.VB_NOM
        t_open_ok = max(first_time(op["REFN"], lambda a: a >= COMP * vb),
                        first_time(op["An"], lambda a: a >= COMP * vb))
        ratio = (cl["Ap"] - cl["An"]) / (cl["BIAS"] - cl["REFN"])
        t_restart = first_time(ratio, lambda a: np.abs(a - ratio[-1]) <= 0.5 * lsb)
        for key, val in (("healthy_open_settle_s", t_open_ok), ("restart_15bit_s", t_restart)):
            if val > req[key]:
                req[key] = val
                worst[key] = c
        b_auto = bits_at(on, op, T_ON, AUTO_DELAY_S)
        if b_auto:
            auto_false.append({"corner": c, "bits": b_auto})
        eo = System(rtd, c["rsw"], c["lead_scale"], c["ctol"], CASES["element_open"])
        on_o, _, _ = sequence(eo, T_ON, 1e-4, 1e-4)
        t_det = first_time(on_o["REFN"], lambda a: a > COMP * vb)
        if t_det > req["detect_element_open_vbias_s"]:
            req["detect_element_open_vbias_s"] = t_det
            worst["detect_element_open_vbias_s"] = c
    taus.sort(key=lambda x: -x[0])
    tau_max = taus[0][0]
    return n, tau_max, taus[0], req, worst, auto_false


def detection(step_s, restart_s):
    """Fault bits per input case at the firmware's waits, nominal parts, 25 degC element and
    at the slow corner; and the automatic cycle's bits on a healthy element."""
    out = {}
    nominal = {"c1": 0.0, "c2": 0.0, "cj": 0.0, "ccm": 0.0, "r": 0.0, "rb": 0.0}
    slow = {"c1": 0.05, "c2": 0.05, "cj": 0.10, "ccm": 0.05, "r": 0.001, "rb": 0.01}
    for name, faults in CASES.items():
        row = {}
        for lab, ct, rsw in (("nominal", nominal, K.R_SW), ("slow_corner", slow, 20.0)):
            s = System(K.pt(25.0), rsw, 1.1, ct, faults)
            on, op, _ = sequence(s, step_s, step_s, 1e-4)
            b = bits_at(on, op, step_s, step_s)
            on2, op2, _ = sequence(s, 12e-3, 12e-3, 1e-4)
            ba = bits_at(on2, op2, 12e-3, AUTO_DELAY_S)
            xc = s.dc(True, K.VB_NOM)
            # With the element or FORCE+ open no current flows through R_REF, so
            # BIAS - REFN is solver roundoff (~1e-10 V) and the ratio is undefined
            # (its value and sign differ by platform): null, the fault bits carry it.
            den = xc[s.idx["BIAS"]] - xc[s.idx["REFN"]]
            ratio = (xc[s.idx["Ap"]] - xc[s.idx["An"]]) / den if abs(den) >= 1e-6 else None
            row[lab] = {"manual_bits": f"0x{b:02X}", "automatic_bits": f"0x{ba:02X}",
                        "conversion_ratio": None if ratio is None else round(float(ratio), 5)}
        out[name] = row
    return out


def dc_ratios():
    """REFIN- and RTDIN- over VBIAS, switch closed and open, per input case (nominal parts,
    element at 25 degC): the mock's DC targets."""
    nominal = {"c1": 0.0, "c2": 0.0, "cj": 0.0, "ccm": 0.0, "r": 0.0, "rb": 0.0}
    out = {}
    for name, faults in CASES.items():
        s = System(K.pt(25.0), K.R_SW, 1.0, nominal, faults)
        vb = K.VB_NOM
        xc = s.dc(True, vb)
        xo = s.dc(False, vb)
        xr = s.dc(True, 0.0)
        g = lambda x, nn: float(x[s.idx[nn]]) / vb  # noqa: E731
        out[name] = {"refn_closed": g(xc, "REFN"), "rtdin_n_closed": g(xc, "An"),
                     "refn_open": g(xo, "REFN"), "rtdin_n_open": g(xo, "An"),
                     "refn_rest": g(xr, "REFN"), "rtdin_n_rest": g(xr, "An")}
    return out


def tau_for_mock(req, ratios):
    """A single first-order tau such that the mock's healthy REFIN-/RTDIN- (from the closed DC
    point to the open one) reach 85 % no sooner than the worst MNA corner, and is at least
    tau_max. Crossing at t: target - (target - start) exp(-t/tau) = 0.85."""
    h = ratios["healthy"]
    taus = []
    for start, target in ((h["refn_closed"], h["refn_open"]), (h["rtdin_n_closed"], h["rtdin_n_open"])):
        if target > COMP and start < COMP:
            taus.append(req["healthy_open_settle_s"] / math.log((target - start) / (target - COMP)))
    return max(taus)


def header_define(name: str) -> float:
    m = re.search(rf"#define {name}\s+([0-9.]+)u?", RTD_H.read_text(encoding="utf-8"))
    return float(m.group(1)) if m else math.nan


def write_mock_header(tau_mock_s, tau_max_s, ratios):
    lines = [
        "/* Generated by output/temper-sensor-r3/firmware/fault_cycle.py - do not edit. */",
        "/*",
        " * MAX31865 analog front end on the zapote CR-1 board (C37) for the SPI mock",
        " * (mock_max31865.c): REFIN- and RTDIN- as fractions of VBIAS in each FORCE-",
        " * switch state, per input condition, from the pcb/checks.py MNA network",
        " * (nominal parts, element at 25 degC); and one first-order time constant that",
        " * reaches every 85 % comparator decision no sooner than the worst MNA corner",
        " * (fault-cycle.json mock).",
        " */",
        "#ifndef MOCK_MAX31865_AFE_H",
        "#define MOCK_MAX31865_AFE_H",
        "",
        f"#define MOCK_MAX31865_AFE_TAU_US {tau_mock_s * 1e6:.1f}f",
        "#define MOCK_MAX31865_AFE_COMPARATOR 0.85f",
        "/* The data sheet's minimum waits on this network: 5 tau_max (and the C37 5 ms",
        " * floor) between the manual steps; 5 tau_max + 1 ms and 10.5 tau_max before the",
        " * ADC restarts. The mock counts writes that come sooner. */",
        f"#define MOCK_MAX31865_AFE_STEP_MIN_US {math.ceil(max(FLOOR_MS * 1e3, 5 * tau_max_s * 1e6))}u",
        f"#define MOCK_MAX31865_AFE_RESTART_MIN_US "
        f"{math.ceil(max(5 * tau_max_s * 1e6 + 1000.0, 10.5 * tau_max_s * 1e6))}u",
        "",
        "typedef enum {",
    ]
    for name in CASES:
        lines.append(f"    MOCK_MAX31865_INPUT_{name.upper()},")
    lines += ["    MOCK_MAX31865_INPUT_COUNT", "} mock_max31865_input_t;", "",
              "typedef struct {", "    float refn_closed, rtdin_n_closed;", "    float refn_open, rtdin_n_open;",
              "    float refn_rest, rtdin_n_rest;", "} mock_max31865_afe_dc_t;", "",
              "static const mock_max31865_afe_dc_t k_mock_max31865_afe_dc[MOCK_MAX31865_INPUT_COUNT] = {"]
    for name, r in ratios.items():
        lines.append(f"    /* {name} */ {{{r['refn_closed']:.5f}f, {max(r['rtdin_n_closed'], 0.0):.5f}f, "
                     f"{r['refn_open']:.5f}f, {max(r['rtdin_n_open'], 0.0):.5f}f, "
                     f"{max(r['refn_rest'], 0.0):.5f}f, {max(r['rtdin_n_rest'], 0.0):.5f}f}},")
    lines += ["};", "", "#endif /* MOCK_MAX31865_AFE_H */", ""]
    MOCK_H.write_text("\n".join(lines), encoding="utf-8")


def ceil_half_ms(s: float) -> float:
    return math.ceil(s * 2e3 - 1e-9) / 2.0


def main() -> int:
    n, tau_max, tau_row, req, worst, auto_false = analyse()
    step_ms = ceil_half_ms(max(FLOOR_MS * 1e-3, 5 * tau_max, 2 * req["healthy_open_settle_s"],
                               2 * req["detect_element_open_vbias_s"]))
    restart_ms = ceil_half_ms(max(step_ms * 1e-3, 5 * tau_max + 1e-3, 10.5 * tau_max,
                                  2 * req["restart_15bit_s"]))
    ratios = dc_ratios()
    tau_mock = max(tau_for_mock(req, ratios), tau_max)
    write_mock_header(tau_mock, tau_max, ratios)
    det = detection(step_ms * 1e-3, restart_ms * 1e-3)
    fw_step = header_define("RTD_C1_FAULT_CYCLE_STEP_US") / 1e3
    fw_restart = header_define("RTD_C1_FAULT_CYCLE_RESTART_US") / 1e3
    checks = {
        "tau_max_above_100us_automatic_invalid": tau_max > 100e-6,
        "automatic_cycle_false_flags_healthy": len(auto_false) > 0,
        "firmware_step_wait_covers": fw_step >= step_ms,
        "firmware_restart_wait_covers": fw_restart >= restart_ms,
        "manual_cycle_healthy_clean": all(v["manual_bits"] == "0x00" for v in det["healthy"].values()),
        "manual_cycle_flags_every_fault_case": all(
            all(det[c][k]["manual_bits"] != "0x00" for k in det[c]) for c in CASES
            if c not in ("healthy",) + NOT_A_CYCLE_CONDITION),
        "sense_n_open_converts_below_the_low_threshold": all(
            det["sense_n_open"][k]["conversion_ratio"] is not None
            and det["sense_n_open"][k]["conversion_ratio"] <= 0.0 for k in det["sense_n_open"]),
        "mock_tau_not_faster_than_mna": tau_mock >= tau_max,
    }
    out = {
        "scope": __doc__.strip(),
        "datasheet": "Maxim MAX31865 19-6478 Rev 3 (datasheets/max31865.pdf, sha256 88f54041...95f7)",
        "board": "zapote/controller C37 (controller-c1-crs 467917c38): CR-1 as specified; pcb/checks.py "
                 "DESIGNS['proposed'] is that circuit (checks-as-built.json: no difference)",
        "corners": n,
        "tau_max_us": round(tau_max * 1e6, 1),
        "tau_max_at": {"switch_closed": tau_row[1], **tau_row[2]},
        "required_worst_us": {k: round(v * 1e6, 1) for k, v in req.items()},
        "required_worst_at": worst,
        "checks_py_wait_ms": 5.0,
        "firmware_waits_ms": {"step": step_ms, "restart": restart_ms,
                              "rule": "step = max(5 ms floor, 5 tau_max, 2 x worst required); restart = "
                                      "max(step, 5 tau_max + 1 ms, 10.5 tau_max, 2 x worst 15-bit settle)"},
        "firmware_header_ms": {"step": fw_step, "restart": fw_restart},
        "automatic_cycle": {"false_flagged_corners": len(auto_false),
                            "example": auto_false[0] if auto_false else None},
        "detection_at_firmware_waits": det,
        "mock": {"tau_us": round(tau_mock * 1e6, 1), "dc_ratios_25C": ratios,
                 "rule": "first order from the closed DC point to the open one reaches 85 % no sooner than "
                         "the worst MNA corner, and tau >= tau_max"},
        "checks": checks, "all_pass": all(checks.values()),
    }
    (HERE / "fault-cycle.json").write_text(json.dumps(EC.stamp(out), indent=1, default=float) + "\n", encoding="utf-8")
    print(f"corners {n}; tau_max {tau_max * 1e6:.1f} us; required (us): "
          + ", ".join(f"{k} {v * 1e6:.0f}" for k, v in req.items()))
    print(f"firmware waits: step {step_ms} ms, restart {restart_ms} ms (header {fw_step} / {fw_restart} ms); "
          f"mock tau {tau_mock * 1e6:.1f} us; automatic cycle false-flags {len(auto_false)} corners")
    for c, r in det.items():
        print(f"  {c:16s} " + "  ".join(f"{k}: manual {v['manual_bits']} auto {v['automatic_bits']}"
                                       for k, v in r.items()))
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print("ALL FAULT CYCLE CHECKS PASS" if out["all_pass"] else "FAULT CYCLE CHECK FAILURE")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
