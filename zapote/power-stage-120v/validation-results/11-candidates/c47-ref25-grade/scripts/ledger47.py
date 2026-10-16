#!/usr/bin/env python3
"""Stage 47 datasheet-ledger edit (U5 REF25 on its 125 C grade): run after scripts/bands47.py and the s47 chain.

    python3 -I scripts/ledger47.py    -> native-21/verification/datasheet-ledger/ledger.json (in place)

* LM4040A25IDBZR (UNAUDITED) -> LM4050AEM3-2.5/NOPB (U5), audited from TI SNOS455H: 5.1 p.4, 5.3 p.5, 5.4 p.5, 5.6 p.7,
  note 1 and note 5 p.11, 4 p.3, addendum p.25.
* Stresses: the cathode-current window at the REF25 corners (audit.rs reference_spec / the B3 gate's MONITOR_SELF, the
  same constants), power, and the local temperature from the B3 gated U5 row of this board (keyed citations into
  b3-ratings/margins.json, solved on the s47 board); the bands U5 sets at the s47 basis are recorded from
  results/bands-s47.md (informational stresses: their rules are design rules, not datasheet limits).
Re-running it on the edited ledger gives the same file.
"""
import sys as _s; _s.dont_write_bytecode = True
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
LEDGER = PS / "native-21/verification/datasheet-ledger/ledger.json"
RES = HERE.parent / "results"
B = json.loads((RES / "bands-s47.json").read_text())
MD = (RES / "bands-s47.md").read_text().splitlines()
MDREL = str((RES / "bands-s47.md").relative_to(PS))
MARGINS = PS / "validation-results/04-board-current-thermal/round5-native21/b3-ratings/margins.json"
KELVIN = PS / "validation-results/02-protection-timing/kelvin/kelvin_plane.py"
DS_SHA = "950d04912ac6cdab"
MPN = "LM4050AEM3-2.5/NOPB"
# REF25 operating point (audit.rs reference_spec / min / max_reference_cathode_current_ua; b3_ratings_gate MONITOR_SELF)
VMAX, VMIN = 2.5 + 0.015 + 0.0012, 2.5 - 0.015 - 0.0012      # SNOS455H 5.6 p.7: +-15 mV full range + 1.2 mV dVR/dIR
R_BIAS = 5600.0                                                # R31 0603WAF5601T5E, 1 %


def cite(prefix):
    hits = [i + 1 for i, l in enumerate(MD) if l.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return f"{MDREL}:{hits[0]}"


def currents():
    i_min = ((4.75 - VMAX) / (R_BIAS * 1.01) - (VMAX + 0.15) / (20000 * 0.999) - VMAX / (24300 * 0.999)
             - VMAX / (150000 * 0.999))
    i_max = ((5.15 - VMIN) / (R_BIAS * 0.99) - VMIN / (20000 * 1.001) - VMIN / (24300 * 1.001) - VMIN / (150000 * 1.001))
    i_ceil = (5.15 - VMIN) / (R_BIAS * 0.99)
    return round(i_min * 1e3, 4), round(i_max * 1e3, 4), round(i_ceil * 1e3, 4)


def b3_u5():
    """The gated B3 U5 row of this board per case; margins.json must be solved on the s47 board."""
    pin = re.search(r'"native21s47": "([0-9a-f]{64})"', KELVIN.read_text()).group(1)
    m = json.loads(MARGINS.read_text())
    assert set(m["board_sha256"].values()) == {pin}, ("margins.json is not the s47 board", m["board_sha256"], pin)
    out = {}
    for c, rows in m["cases"].items():
        hit = [r for r in rows if r["item"].startswith("U5: ")]
        assert len(hit) == 1 and MPN in hit[0]["item"], (c, hit)
        out[c] = hit[0]
    return out, str(MARGINS.relative_to(PS)), pin, m["basis"]["cases"]


def entry():
    i_min, i_max, i_ceil = currents()
    rows, rel, pin, basis = b3_u5()
    rel_case = next(c for c, v in basis.items() if v["role"] == "release")
    worst = max(rows, key=lambda c: rows[c]["est_c"])
    t_rel, t_all = round(rows[rel_case]["est_c"], 1), round(rows[worst]["est_c"], 1)
    key = lambda c: {"file": rel, "b3_row": {"case": c, "item": " ".join(rows[c]["item"].split()[:3])},
                     "est_c": round(rows[c]["est_c"], 1)}
    p_op, p_ceil = round(i_max * VMAX, 4), round(i_ceil * VMAX, 4)          # mW
    pd_lim = round((150.0 - t_all) / 326.0 * 1e3, 1)                        # mW, p.11 note 1 at the BASIS max
    basis_row = next(r for r in B["rows"] if r["ref25"] == MPN and r["network"].startswith("solved c17.5"))
    c28_row = next(r for r in B["rows"] if r["ref25"] == MPN and r["network"].startswith("solved c28"))
    l_basis = cite(f"| {MPN} | solved c17.5")
    l_c28 = cite(f"| {MPN} | solved c28")
    return {
        "mpn": MPN, "designators": ["U5"], "class": "SIGNAL",
        "function": "REF25, the 2.5 V shunt reference for the shunt-OCP threshold (R32-R35) and the bus OVP threshold "
                    "(R36 / R37), fed by R31 5.6 k from HOT5; the extended-range LM4050AEM3 since stage 47 (S17 hot copper; "
                    "LM4040A25IDBZR, -40..85 C, before)",
        "status": "PARTIAL",
        "datasheet": {"url": "https://www.ti.com/lit/ds/symlink/lm4050-n.pdf",
                      "revision": "TI SNOS455H, May 2000, revised March 2025", "fetched": "2026-10-15", "repo_copy": None,
                      "note": "u5-ref search download, copied to runs-native21/s47/dl; not committed. 5.1 p.4 abs max "
                              "reverse current 20 mA, forward 10 mA, PD 280 mW at TA 25 C, TJ 150 C; 5.3 p.5 extended "
                              "range TA = TJ -40..125 C; 5.4 p.5 DBZ RthJA 287 C/W (p.11 note 1: 326 C/W board mounted, "
                              "PDmax = (TJmax - TA) / RthJA); 5.6 p.7 (2.5 V, LM4050AEM3): VR 2.500 V +-2.5 mV at 25 C, "
                              "+-15 mV over the extended range (note 5 p.11: +-0.1 % +- 50 ppm/C x 100 K x VR), IRMIN 60 uA "
                              "at 25 C / 65 uA over temperature, dVR/dIR 1.2 mV for IRMIN..1 mA and 8 mV for 1..15 mA over "
                              "temperature, long-term 120 ppm / 1000 h typ, VHYST typical only; 4 p.3 DBZ 1 cathode, 2 "
                              "anode, 3 no internal connection (float or tie to pin 2); addendum p.25 LM4050AEM3-2.5/NOPB "
                              "SOT-23 (DBZ) -40 to 125 C, marking RCA",
                      "sha256_prefix16": DS_SHA},
        "ratings": [
            {"parameter": "Reverse current, abs max", "datasheet_limit": 20, "unit": "mA",
             "basis": "absolute maximum", "source": "5.1 p.4"},
            {"parameter": "Cathode current, top of the 1.2 mV regulation window", "datasheet_limit": 1.0, "unit": "mA",
             "basis": "dVR/dIR <= 1.2 mV for IRMIN <= IR <= 1 mA over temperature: the band analysis assumes this window "
                      "(IRMIN 65 uA over temperature is the floor, enforced by audit.rs)", "source": "5.6 p.7"},
            {"parameter": "Power dissipation, derated at the BASIS max local temperature", "datasheet_limit": pd_lim,
             "unit": "mW", "basis": f"PDmax = (150 C - {t_all} C) / 326 C/W (abs max 280 mW at 25 C)",
             "source": "5.1 p.4; p.11 note 1"},
            {"parameter": "Free-air / junction temperature max", "datasheet_limit": 125, "unit": "C",
             "basis": "extended temperature range, TA = TJ -40..125 C (industrial LM4050AIM3: 85 C)", "source": "5.3 p.5"},
            {"parameter": "Reverse breakdown voltage tolerance, extended range", "datasheet_limit": 0.015, "unit": "V",
             "basis": "+-15 mV over -40..125 C at IR 100 uA; the bands add the 1.2 mV current regulation (+-16.2 mV)",
             "source": "5.6 p.7; note 5 p.11"}],
        "stresses": [
            {"parameter": "Cathode current, operating minimum", "worst_case_value": i_min, "unit": "mA",
             "condition": "HOT5 4.75 V, R31 +1 %, the three load strings -0.1 % with OCP_KELVIN_N at -0.15 V, VR at its "
                          f"maximum {VMAX:.4f} V: >= the 0.065 mA IRMIN (5.6 p.7)", "evidence": "audit.rs"},
            {"parameter": "Cathode current, operating maximum", "worst_case_value": i_max, "unit": "mA",
             "condition": f"HOT5 5.15 V, R31 -1 %, loads +0.1 % at OCP_KELVIN_N 0 V, VR at its minimum {VMIN:.4f} V",
             "evidence": "audit.rs; validation-results/04-board-current-thermal/round5-native21/b3-ratings/b3_ratings_gate.py"},
            {"parameter": "Cathode current, ceiling (all loads open)", "worst_case_value": i_ceil, "unit": "mA",
             "condition": "the whole R31 current at HOT5 5.15 V, R31 -1 %, VR minimum", "evidence": "audit.rs"},
            {"parameter": "Power dissipation, ceiling", "worst_case_value": p_ceil, "unit": "mW",
             "condition": f"ceiling current x {VMAX:.4f} V (operating maximum {p_op} mW, 0.2 K at 326 C/W)",
             "evidence": "audit.rs"},
            {"parameter": "Local temperature, release case", "worst_case_value": t_rel, "unit": "C",
             "condition": f"B3 hot-copper gated row (pad-copper max + P x RthJA), {rel_case} at bay "
                          f"{basis[rel_case]['bay_c']:g} C; board {pin[:8]}", "evidence": [key(rel_case)]},
            {"parameter": "Local temperature, BASIS max", "worst_case_value": t_all, "unit": "C",
             "condition": f"same row, worst over the BASIS cases ({worst})", "evidence": [key(worst)]},
            {"parameter": "Bus OVP band set by REF25 (informational)", "worst_case_value": basis_row["ovp_band_V"][1], "unit": "V",
             "condition": f"upper corner, band {basis_row['ovp_band_V']} V with the R26-R37 network at its solved {rel_case} "
                          f"temperatures (the s47 band basis), against the 288.02 V must-not-rise rule; c28 solved "
                          f"{c28_row['ovp_band_V']} V", "evidence": f"{l_basis}; {l_c28}"},
            {"parameter": "Shunt OCP low corner after the Kelvin shift (informational)",
             "worst_case_value": basis_row["ocp_low_after_kelvin_A"], "unit": "A",
             "condition": f"band before the shift {basis_row['ocp_band_before_kelvin_A']} A at the s47 basis, "
                          f"{basis_row['ocp_floor_margin_A']:+.2f} A over the 64.17 A floor (c28 solved "
                          f"{c28_row['ocp_low_after_kelvin_A']} A, {c28_row['ocp_floor_margin_A']:+.2f} A)",
             "evidence": f"{l_basis}; validation-results/02-protection-timing/kelvin/kelvin_budget.py"}],
        "derating_rule": "Cathode current inside IRMIN..1 mA (the 1.2 mV regulation window the bands assume) and under the "
                         "20 mA abs max; dissipation under the derated PDmax; local temperature <= 125 C.",
        "checks": [
            {"id": "IR abs max", "rating": "Reverse current, abs max", "stress": "Cathode current, ceiling (all loads open)",
             "max_ratio": 1.0, "severity": "violation", "rule": f"{i_ceil} mA <= 20 mA", "ratio": round(i_ceil / 20, 4)},
            {"id": "IR regulation window", "rating": "Cathode current, top of the 1.2 mV regulation window",
             "stress": "Cathode current, ceiling (all loads open)", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{i_ceil} mA <= 1 mA", "ratio": round(i_ceil / 1.0, 4)},
            {"id": "PD", "rating": "Power dissipation, derated at the BASIS max local temperature",
             "stress": "Power dissipation, ceiling", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{p_ceil} mW <= {pd_lim} mW", "ratio": round(p_ceil / pd_lim, 4)},
            {"id": "temperature, release case", "rating": "Free-air / junction temperature max",
             "stress": "Local temperature, release case", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{t_rel} C <= 125 C (B3 gate row)", "ratio": round(t_rel / 125, 4)},
            {"id": "temperature, BASIS max", "rating": "Free-air / junction temperature max",
             "stress": "Local temperature, BASIS max", "max_ratio": 1.0, "severity": "violation",
             "rule": f"{t_all} C <= 125 C", "ratio": round(t_all / 125, 4)}],
        "layout_guidance": [
            {"item": "pin 3 (no internal connection) floats on its own net u_ref-nc (allowed by p.3; tying it to pin 2 "
                     "is TI's high-EMI recommendation, table note 1, a copper change not made here)",
             "enforced_by": "audit.rs"},
            {"item": "same SOT-23 pads and nets as the LM4040A25IDBZR (BOM-only stage)",
             "enforced_by": "audit.rs (IDENTITY) and validation-results/08-manufacturing-package/native-21/cpl-rotation-audit/audit.py"}],
        "gaps": [
            "the local temperature is the B3 body-model estimate (pad copper as the die / ambient proxy, hot copper, still "
            f"air at the BASIS bays), not a measurement; the bands take REF25 at the full -40..125 C row ({MDREL})",
            "long-term drift (120 ppm / 1000 h typical) and thermal hysteresis are typical-only and outside the band model",
            "other entries' bus-OVP stresses quote 286 V (alt-circuits-2026-10-09 ALT-D3.md:60), below this band's upper "
            "corner (287.45 V at the s47 basis; 288.02 V for the A25I on the committed basis): pre-existing, not re-cited here"],
        "finding": None,
        "notes": "JLC C2156518, extended, 50 in stock 2026-10-15 against 500 for 500 boards (LM4050QAEM3-2.5 C2157745 43, "
                 "C2157326 3): the 500-board lot is an owner pre-order (>= 550 incl. attrition) consigned to JLC; $3.4228 at "
                 "500+. The JLC listing's -40..85 C is wrong for the E suffix (TI 5.3 p.5, addendum p.25). Replaces "
                 "LM4040A25IDBZR (C9421) on the same DBZ pads: at the c17.5 @ 61 release case the A25I read 89.1 C "
                 "against 85 C (-4.1 K). Bands: " + MDREL + "."}


def main():
    led = json.loads(LEDGER.read_text())
    E = led["entries"]
    new = entry()
    out = {}
    for k, v in E.items():
        if k in ("LM4040A25IDBZR", MPN):
            if MPN not in out:
                out[MPN] = new
        else:
            out[k] = v
    led["entries"] = out
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print("ledger: entries", len(out))


if __name__ == "__main__":
    main()
