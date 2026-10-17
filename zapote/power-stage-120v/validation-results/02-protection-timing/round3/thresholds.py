#!/usr/bin/env python3
"""Static threshold corners and reproducible 100k-sample component Monte Carlo.

One-off engineering analysis, not a permanent validation rule. The actual
frozen netlist supplies topology; frozen/default.csv supplies part identity.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import csv
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]
N = 100_000
SEED = 320102

# (nominal ohm, initial tolerance, maximum |TCR| / C)
RT = (None, 0.001, 25e-6)       # Yageo RT0603BRD07, thin film
RC = (None, 0.01, 100e-6)       # Yageo RC1206FR-07, thick film
SHUNT = (0.001, 0.01, 250e-6)  # Vishay WSK2512R0010FEA: F = 1%, 1m TCR
PARTS = {
    "R5": SHUNT, "R26": (470e3, *RC[1:]), "R27": (470e3, *RC[1:]),
    "R28": (470e3, *RC[1:]), "R29": (470e3, *RC[1:]),
    "R30": (15.8e3, *RT[1:]), "R32": (10e3, *RT[1:]),
    "R33": (10e3, *RT[1:]), "R34": (10.5e3, *RT[1:]),
    "R35": (10e3, *RT[1:]), "R36": (10e3, *RT[1:]),
    "R37": (140e3, *RT[1:]), "R39": (1.5, 0.01, 200e-6),
    "R40": (1e3, *RT[1:]), "R41": (1e3, *RT[1:]),
    "R43": (3.32e3, *RT[1:]), "R44": (10e3, *RT[1:]),
    "R45": (10e3, *RT[1:]), "R46": (3.32e3, *RT[1:]),
}


def thresholds(p: dict, ref: float, vos: float, v3v3: float = 3.3,
               clamp_v: float = 0.0) -> tuple:
    """Return (shunt A, CT positive A, CT negative A, OVP V).

    R32/R33 midpoint has Kelvin input -I*R5 and comparator IN+ at ocp_node.
    U7 IN+ is ovp_thresh and IN- is vsense_in. CT static transfer is R39/100;
    transient C42/CT magnetization belongs to the separate waveform model.
    """
    th_ocp = ref * p["R35"] / (p["R34"] + p["R35"])
    ocp = (ref * p["R33"] / p["R32"]
           - (th_ocp + vos) * (1 + p["R33"] / p["R32"])) / p["R5"]
    bias = v3v3 * p["R41"] / (p["R40"] + p["R41"])
    hi = v3v3 * p["R44"] / (p["R43"] + p["R44"])
    lo = v3v3 * p["R46"] / (p["R45"] + p["R46"])
    gain = p["R39"] / 100.0
    ct_pos = (hi - bias + vos + clamp_v) / gain
    ct_neg = (bias - lo + vos + clamp_v) / gain
    th_ovp = ref * p["R37"] / (p["R36"] + p["R37"])
    ovp = (th_ovp - vos) * (sum(p[f"R{i}"] for i in range(26, 30)) + p["R30"]) / p["R30"]
    return ocp, ct_pos, ct_neg, ovp


def input_bias_v(p: dict, index: int) -> float:
    """Adverse differential shift from 5 nA max on each TLV3201 input."""
    parallel = lambda a, b: a * b / (a + b)
    if index == 0:
        source = parallel(p["R32"], p["R33"]) + parallel(p["R34"], p["R35"])
    elif index in (1, 2):
        a, b = ("R43", "R44") if index == 1 else ("R45", "R46")
        source = 1000 + p["R39"] + parallel(p[a], p[b])
    else:
        source = parallel(p["R36"], p["R37"]) + parallel(
            sum(p[f"R{i}"] for i in range(26, 30)), p["R30"])
    return 5e-9 * source


def validate_inputs() -> dict:
    """Fail if the BOM identity or source net endpoints differ from the model."""
    bom = {}
    with (UNIT / "frozen/default.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            for ref in row["Designator"].split(","):
                bom[ref] = row["Comment"]
    expected_mpn = {
        "R5": "WSK2512R0010FEA", "R30": "RT0603BRD0715K8L",
        "R39": "RC1206FR-071R5L", "U5": "LM4040A25IDBZR",
        "U6": "TLV3201AIDBVR", "U7": "TLV3201AIDBVR",
        "U10": "TLV3201AIDBVR", "U11": "TLV3201AIDBVR",
    }
    expected_mpn.update({f"R{i}": "RC1206FR-07470KL" for i in range(26, 30)})
    expected_mpn.update({f"R{i}": "RT0603BRD0710KL" for i in (32, 33, 35, 36, 44, 45)})
    expected_mpn.update({"R34": "RT0603BRD0710K5L", "R37": "RT0603BRD07140KL",
                         "R40": "RT0603BRD071KL", "R41": "RT0603BRD071KL",
                         "R43": "RT0603BRD073K32L", "R46": "RT0603BRD073K32L"})
    for ref, mpn in expected_mpn.items():
        if bom.get(ref) != mpn:
            raise ValueError(f"BOM MPN changed: {ref}: {bom.get(ref)} != {mpn}")
    netlist = (UNIT / "frozen/default.net").read_text()
    net_blocks = re.findall(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)(?=\n    \(net |\n  \)\n\))',
                            netlist, re.S)
    net_nodes = {name: set(re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body))
                 for name, body in net_blocks}
    expected_nodes = {
        "ref25": {("R32", "1"), ("R34", "1"), ("R36", "1")},
        "ocp_kelvin_n": {("R5", "3"), ("R33", "2")},
        "ocp_node": {("R32", "2"), ("R33", "1"), ("U6", "3")},
        "ocp_thresh": {("R34", "2"), ("R35", "1"), ("U6", "4")},
        "ovp_thresh": {("R36", "2"), ("R37", "1"), ("U7", "3")},
        "vsense_in": {("R29", "2"), ("R30", "1"), ("U7", "4")},
        "ct_s1": {("T1", "3"), ("R39", "1"), ("R42", "1")},
        "ct_s2": {("T1", "4"), ("R39", "2"), ("R40", "2"), ("R41", "1")},
        "ct_sense_mon": {("R42", "2"), ("U10", "3"), ("U11", "4")},
        "ct_ref_hi": {("R43", "2"), ("R44", "1"), ("U10", "4")},
        "ct_ref_lo": {("R45", "2"), ("R46", "1"), ("U11", "3")},
        "v3v3": {("R40", "1"), ("R43", "1"), ("R45", "1")},
    }
    for name, required in expected_nodes.items():
        if not required <= net_nodes.get(name, set()):
            raise ValueError(f"Netlist topology changed at {name}: {required - net_nodes.get(name, set())}")
    return {"bom_mpn_checks": len(expected_mpn), "net_endpoint_groups": len(expected_nodes)}


def corner_values(temp_c: float, shunt_rise_c: float) -> dict:
    """Independent adverse tolerance and signed TCR limits per physical part."""
    values = {}
    for name, (nominal, tol, tcr) in PARTS.items():
        dt = temp_c - 25 + (shunt_rise_c if name == "R5" else 0)
        drift = tcr * abs(dt)
        values[name] = (nominal * (1 - tol) * (1 - drift),
                        nominal * (1 + tol) * (1 + drift))
    return values


def exact_corners(temp_c: float, shunt_rise_c: float) -> dict:
    # Each output depends on only its own part subset. Exhaust all vertices.
    groups = {
        "shunt_a": ("R5", "R32", "R33", "R34", "R35"),
        "ct_pos_a": ("R39", "R40", "R41", "R43", "R44"),
        "ct_neg_a": ("R39", "R40", "R41", "R45", "R46"),
        "ovp_v": ("R26", "R27", "R28", "R29", "R30", "R36", "R37"),
    }
    limits = corner_values(temp_c, shunt_rise_c)
    result = {}
    for index, (label, names) in enumerate(groups.items()):
        lo = (float("inf"), None)
        hi = (float("-inf"), None)
        for bits in itertools.product((0, 1), repeat=len(names)):
            p = {name: spec[0] for name, spec in PARTS.items()}
            p.update({name: limits[name][bit] for name, bit in zip(names, bits)})
            # TI A25I's full -40..85 C table gives ±19 mV; this is
            # conservative at both requested board temperatures.
            refs = ((2.5 - 0.020, 2.5 + 0.020) if index in (0, 3) else (2.5,))
            rails = ((3.135, 3.465) if index in (1, 2) else (3.3,))
            bias_shift = input_bias_v(p, index)
            for ref, rail, vos, bias_sign, clamp in itertools.product(
                refs, rails, (-0.004, 0.004), (-1, 1),
                ((-80e-6, 80e-6) if index in (1, 2) else (0.0,))
            ):
                value = thresholds(p, ref, vos + bias_sign * bias_shift,
                                   v3v3=rail, clamp_v=clamp)[index]
                case = {"resistor_high_bits": dict(zip(names, bits)),
                        "ref_v": ref, "v3v3_v": rail, "vos_v": vos,
                        "input_bias_v": bias_sign * bias_shift, "clamp_v": clamp}
                if value < lo[0]:
                    lo = value, case
                if value > hi[0]:
                    hi = value, case
        result[label] = {"min": lo[0], "min_corner": lo[1],
                         "max": hi[0], "max_corner": hi[1]}
    return result


def monte_carlo() -> dict:
    rng = np.random.default_rng(SEED)
    temp = rng.uniform(-10, 85, N)
    p = {}
    for name, (nominal, tol, tcr) in PARTS.items():
        dt = temp - 25 + (50 if name == "R5" else 0)
        p[name] = (nominal * (1 + rng.uniform(-tol, tol, N))
                   * (1 + rng.uniform(-tcr, tcr, N) * dt))
    # IC limits represented as 3 sigma, then clipped at their datasheet limits.
    ref_err = np.clip(rng.normal(0, 0.001 / 3, N), -0.001, 0.001)
    ref_tcr = np.clip(rng.normal(0, 100e-6 / 3, N), -100e-6, 100e-6)
    ref = 2.5 * (1 + ref_err + ref_tcr * (temp - 25))
    vos = [np.clip(rng.normal(0, 0.004 / 3, N), -0.004, 0.004) for _ in range(4)]
    clamp = rng.uniform(-80e-6, 80e-6, N)  # 80 nA max * 1 kΩ; conservative signed
    v3v3 = rng.uniform(3.135, 3.465, N)
    ref += rng.uniform(-.001, .001, N)  # LM4040 load-regulation allowance
    bias = [rng.uniform(-1, 1, N) * input_bias_v(p, i) for i in range(4)]
    values = (
        thresholds(p, ref, vos[0] + bias[0], v3v3=v3v3)[0],
        thresholds(p, ref, vos[1] + bias[1], v3v3=v3v3, clamp_v=clamp)[1],
        thresholds(p, ref, vos[2] + bias[2], v3v3=v3v3, clamp_v=clamp)[2],
        thresholds(p, ref, vos[3] + bias[3], v3v3=v3v3)[3],
    )
    return {name: {"p0_1": float(np.quantile(v, .001)),
                   "median": float(np.median(v)),
                   "p99_9": float(np.quantile(v, .999))}
            for name, v in zip(("shunt_a", "ct_pos_a", "ct_neg_a", "ovp_v"), values)}


def main() -> None:
    validation = validate_inputs()
    nominal = {name: spec[0] for name, spec in PARTS.items()}
    base = dict(zip(("shunt_a", "ct_pos_a", "ct_neg_a", "ovp_v"),
                    map(float, thresholds(nominal, 2.5, 0.0))))
    assert abs(base["shunt_a"] - 61) / 61 < .02, base
    assert abs(base["ovp_v"] - 280) / 280 < .02, base
    temps = {str(t): exact_corners(t, 50) for t in (-10, 85)}
    extrema = {name: {"min": min(temps[t][name]["min"] for t in temps),
                      "max": max(temps[t][name]["max"] for t in temps)}
               for name in base}
    sources = {
        "RT_0p1_25ppm": "https://www.yageogroup.com/component-documentation/download/specsheet/RT0603BRD0710KL",
        "RC_1pct_100ppm": "https://yageogroup.com/component-documentation/download/specsheet/RC0603FR-07470KL",
        "WSK_1m_1pct_250ppm": "https://www.vishay.com/docs/30108/wsk2512.pdf (p.2 technical specifications; F code p.1)",
        "LM4040A25_0p1pct_100ppm": "https://www.ti.com/lit/ds/symlink/lm4040.pdf (A25I table: initial ±2.5 mV, full range ±19 mV)",
        "RC1206_1p5ohm_200ppm": "https://www.mouser.com/datasheet/2/447/YAGOS01625_1-2572852.pdf (Yageo RC1206 V.3 p.5 Table 2, 1-10 ohm grade)",
        "TLV3201_4mV": "https://www.ti.com/lit/ds/symlink/tlv3201.pdf (SBOS561C pp.5-6)",
        "BAS116H_80nA": "https://assets.nexperia.com/documents/data-sheet/BAS116H.pdf (table 7, 75 V pulsed, 150 C)",
    }
    record = {
        "evidence_class": "bounded static circuit calculation plus distribution-assumed Monte Carlo",
        "revision": "44417ae1489fd00e2d652fd3b2c1582b76d17630",
        "board_sha256": hashlib.sha256((UNIT / "native-15/section.kicad_pcb").read_bytes()).hexdigest(),
        "netlist_sha256": hashlib.sha256((UNIT / "frozen/default.net").read_bytes()).hexdigest(),
        "bom_sha256": hashlib.sha256((UNIT / "frozen/default.csv").read_bytes()).hexdigest(),
        "source_citations": sources, "structural_input_checks": validation,
        "assumptions": ["R5 is 50 C above board ambient, ASSUMED pending A6",
                        "reference and comparator Gaussian 3 sigma at datasheet limits, clipped",
                        "resistor initial tolerance and signed TCR uniform and independent",
                        "CT 80 nA clamp leakage represented as signed 80 uV at R42=1k; datasheet limit is at 150 C, 75 V pulsed",
                        "CT static threshold uses ideal 1:100 burden gain; C42 frequency transfer is in SPICE timing, not these static bands",
                        "±1 mV LM4040 load-regulation allowance from REFERENCE-BIAS.md included",
                        "TLV3201 ±5 nA input bias on each input included via source Thevenin resistance",
                        "CT rail v3v3 is sampled/limited to 3.135–3.465 V per FAULT-INTERFACE.md",
                        "The -10 C corner is outside MC78L05AC's 0..125 C specified range; conditional extrapolation only"],
        "nominal": base, "temperature_corners": temps, "extreme": extrema,
        "monte_carlo": {"n": N, "seed": SEED, "temperature_distribution": "uniform -10 to +85 C",
                        "quantiles": monte_carlo()},
    }
    out = HERE / "outputs/thresholds.json"
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"nominal": base, "extreme": extrema,
                      "quantiles": record["monte_carlo"]["quantiles"]}, indent=2))


if __name__ == "__main__":
    main()
