#!/usr/bin/env python3
"""Run the sensor-r3 PCB checks (checks.py, copied from sensor-c1-impulse-mining 1431caad5 with
its two input paths pointed at this folder) on the AS-BUILT controller values.

The "proposed" design in checks.py is the CHANGE-REQUEST. This script reads the frozen netlist,
builds the same design dict from the captured parts (values, which side of the filter each part
lands on), records any difference from the proposal, substitutes it for "proposed" and runs
every item. Output: checks-as-built.json (exit 1 if a gate fails or a value differs).

    python3 evidence/sensor-r3-checks/run_as_built.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
sys.path.insert(0, str(UNIT / "tools"))
sys.path.insert(0, str(HERE))
from netlist import attach_resolved, parse_value, read_netlist  # noqa: E402

import checks  # noqa: E402

RREF_TC = {"RG2012V-431-W-T1": 5e-6, "RT0805BRD07430RL": 25e-6,    # RG2012 V code; Yageo RT 25 ppm
           "PTFR0805B430RN9": 10e-6}                                 # RESI PTFR N code = +/-10 ppm/C (C52)


def as_built() -> tuple[dict, dict]:
    nl = attach_resolved(read_netlist(UNIT / "frozen/default.net"), UNIT / "frozen/resolved-components.json")

    def ref(path):
        return nl.ref_of("rtd_pan." + path)

    def val(path):
        return parse_value(nl.value[ref(path)])[0]

    j3 = ref("j_rtd1")
    s_p, s_n = nl.net_of(j3, "2"), nl.net_of(j3, "3")

    def side(path, net):
        r = ref(path) if not path.startswith("/") else nl.ref_of(path[1:])
        return "cable" if net in (nl.net_of(r, "1"), nl.net_of(r, "2")) else "adc"
    rref = ref("r_ref")
    tol = parse_value(nl.value[rref])[1]
    d = dict(r1=val("r_s1p"), r2=val("r_s2p"), c1=val("c_s1"), c2=val("c_rtd_input"), ccm=val("c_cm_p"),
             rb=val("r_rtdin_p_bias"), rb_side=side("r_rtdin_p_bias", s_p),
             win_side=side("r_window_sense_p", s_p), cw=val("c_window"),
             div_side=side("r_low_bottom", s_n),
             rth_bottom="sn" if side("/r_runaway_bot", s_n) == "cable" else "gnd",
             cj=val("c_j_sp"), tvs=nl.mpn.get(ref("d_j_sp")) == "ESD5Z3.3T1G",
             rref=parse_value(nl.value[rref])[0], rref_tc=RREF_TC[nl.mpn[rref]], rref_tol=tol)
    # parts the proposal fixes outside the dict: symmetric filter legs, CM caps, J3 caps, rim trip
    extra = {"r_s1n": val("r_s1n"), "r_s2n": val("r_s2n"), "c_cm_n": val("c_cm_n"),
             "c_j": [val(p) for p in ("c_j_fp", "c_j_sp", "c_j_sn", "c_j_fn")],
             "rim_th_top": parse_value(nl.value[nl.ref_of("r_rim_th_top")])[0],
             "rim_th_bot": parse_value(nl.value[nl.ref_of("r_rim_th_bot")])[0],
             "rim_pullup": parse_value(nl.value[nl.ref_of("r_rim_pu")])[0],
             "runaway_top": parse_value(nl.value[nl.ref_of("r_runaway_top")])[0],
             "runaway_bot": parse_value(nl.value[nl.ref_of("r_runaway_bot")])[0],
             "rim_tvs": nl.mpn.get(nl.ref_of("d_rim"))}
    return d, extra


EXTRA_PROPOSED = {"r_s1n": 1000.0, "r_s2n": 1000.0, "c_cm_n": 1e-9, "c_j": [220e-9] * 4, "rim_th_top": 86.6e3,
                  "rim_th_bot": 10e3, "rim_pullup": 1000.0, "runaway_top": 20e3, "runaway_bot": 10e3,
                  "rim_tvs": "ESD5Z5.0T1G"}


def close(a, b):
    if isinstance(a, float) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-12)
    if isinstance(a, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    return a == b


def main() -> int:
    built, extra = as_built()
    prop = checks.DESIGNS["proposed"]
    diffs = {k: {"proposed": prop[k], "as_built": built.get(k)} for k in prop if not close(built.get(k), prop[k])}
    diffs.update({k: {"proposed": v, "as_built": extra[k]} for k, v in EXTRA_PROPOSED.items() if not close(extra[k], v)})
    checks.DESIGNS["proposed"] = built
    for fn in (checks.item1_range_resolution, checks.item1_accuracy, checks.item2_rate, checks.item3_self_heating,
               checks.item4_pickup, checks.item_faults, checks.item5_rim, checks.item6_protection,
               checks.item7_insulation, checks.item8_trips, checks.item9_cable_and_ratings,
               checks.firmware_constants):
        fn()
    summary = {k: v["pass"] for k, v in checks.CHECKS.items()}
    out = {"scope": "sensor-r3 checks.py on the as-built controller (frozen/default.net); 'proposed' = as built",
           "as_built_design": built, "as_built_extra": extra, "differences_from_change_request": diffs,
           "summary": summary, "checks": checks.CHECKS, "info": checks.CHECKS_INFO}
    (HERE / "checks-as-built.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for k, v in summary.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print("differences from the change request:", diffs or "none")
    return 0 if all(summary.values()) and not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
