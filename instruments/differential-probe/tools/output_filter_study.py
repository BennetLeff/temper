#!/usr/bin/env python3
"""Output-filter / bandwidth-jumper study for Rev C (TI vendor macromodels, ideal lumped divider).

Run from the probe directory: python3 tools/output_filter_study.py > validation/spice/output-filter-study.txt
Cases vary C61 (pole with R101 49.9 + R69 220) and an optional shunt COUT after R70 at the BNC
(the 1 m cable + scope stay lumped as 120 pF || 1 Mohm). Reports -3 dB, peaking, 60 kHz phase,
input-referred noise (integrated to 200 MHz / 20 MHz / 5 MHz) and common-mode feedthrough with a
1 % leg-N top-capacitor mismatch, plus a noise decomposition with stages made ideal.
Not a layout or bench result: no parasitics, no transmission-line cable.
"""
import math, subprocess, tempfile
from pathlib import Path

INC = Path("validation/spice/probe_lv_out.inc").read_text()
HDR = ".include sources/opa810_a.lib\n.include sources/opa2810_a.lib\n.include {inc}\nVP VP 0 4.8\nVN VN 0 -4.8068\n"
TMP = Path(tempfile.mkdtemp())
IDEAL = {
    "U3A": ("XU3A FILTER DRIVE DRIVE VP VN OPA2810", "EU3A DRIVE 0 FILTER 0 1"),
    "U3B": ("XU3B SUM_P SUM_N RAW VP VN OPA2810", "EU3B RAW 0 SUM_P SUM_N 1e6"),
    "U1": ("XU1A IN_P BUF_P BUF_P VP VN OPA2810\nXU1B IN_N BUF_N BUF_N VP VN OPA2810",
           "EU1A BUF_P 0 IN_P 0 1\nEU1B BUF_N 0 IN_N 0 1"),
}


def ng(body, ideal=()):
    inc = INC
    for k in ideal:
        a, b = IDEAL[k]
        assert a in inc, k
        inc = inc.replace(a, b)
    (TMP / "v.inc").write_text(inc)
    deck = TMP / "d.cir"
    deck.write_text("study\n" + HDR.format(inc=TMP / "v.inc") + body.replace("@", str(TMP) + "/"))
    subprocess.run(["ngspice", "-n", "-D", "ngbehavior=ps", "-b", str(deck)], capture_output=True, text=True, check=False)


def rows(name):
    p = TMP / name
    return [tuple(map(float, l.split())) for l in p.read_text().splitlines() if l.strip() and l.split()[0][0].isdigit()]


def near(r, f):
    return min(r, key=lambda x: abs(x[0] - f))


def case(c61, cout, fine, ideal=()):
    inst = f"X1 TP TN OUT RAW FINE SEL VP VN PROBE_LV FINE_RANGE={fine} BRANCH=1 R69=220 C61={c61} COUT={cout} CMIS={{cmis}}\n"
    ac = ".control\nset wr_singlescale\nac dec 200 10 200Meg\nlet m=mag(v(OUT))\nlet p=180/PI*vp(OUT)\nwrdata @{f} m p\nquit\n.endc\n.end\n"
    ng("VTP TP 0 DC 0 AC .5\nVTN TN 0 DC 0 AC .5 180\n" + inst.format(cmis=0) + ac.format(f="dm.tsv"), ideal)
    ng("VTP TP 0 DC 0 AC 1\nVTN TN 0 DC 0 AC 1\n" + inst.format(cmis=0.01) + ac.format(f="cm.tsv"), ideal)
    ng("VTP TP 0 DC 0 AC 1\nVTN TN 0 DC 0\n" + inst.format(cmis=0) +
       ".control\nnoise v(OUT) VTP dec 100 10 200Meg\nsetplot noise1\nlet od=onoise_spectrum\nwrdata @ns.tsv od\nquit\n.endc\n.end\n", ideal)
    dm, cm, ns = rows("dm.tsv"), rows("cm.tsv"), rows("ns.tsv")
    g0 = near(dm, 100)[1]
    bw = next(r[0] for r in dm if r[0] > 1e3 and r[1] < g0 / math.sqrt(2))
    pk = 20 * math.log10(max(r[1] for r in dm) / g0)
    ph = near(dm, 60e3)[2] - near(dm, 100)[2]

    def integ(fmax):
        s = 0.0
        for (f1, d1), (f2, d2) in zip(ns, ns[1:]):
            if f1 >= fmax:
                break
            s += (min(f2, fmax) - f1) * (d1 * d1 + d2 * d2) / 2
        return math.sqrt(s) / g0 * 1e3

    cmr = [20 * math.log10(near(cm, f)[1] / g0) for f in (1e6, 5e6, 10e6, 20e6)]
    dens = near(ns, 316e3)[1] / g0 * 1e6
    return bw, pk, ph, [integ(2e8), integ(2e7), integ(5e6)], cmr, dens


print(__doc__.strip().splitlines()[0])
print("\nA. Candidates (input-referred noise in mV rms; CM feedthrough in dB relative to the DC differential gain)")
print(f"{'case':24} {'range':5} {'-3dB MHz':>8} {'peak dB':>7} {'60k deg':>8} | {'noise full':>10} {'to 20M':>7} {'to 5M':>6} | {'CM 1M':>6} {'5M':>6} {'10M':>6} {'20M':>6}")
CASES = [("now: C61 100p", "100p", "1f"), ("jumper: C61 47p", "47p", "1f"),
         ("C61 47p + COUT 330p", "47p", "330p"), ("C61 33p + COUT 330p", "33p", "330p"),
         ("C61 100p + COUT 470p", "100p", "470p")]
for name, c61, cout in CASES:
    for fine in (0, 1):
        bw, pk, ph, n, cmr, _ = case(c61, cout, fine)
        print(f"{name:24} {'fine' if fine else 'wide':5} {bw / 1e6:8.2f} {pk:7.2f} {ph:+8.3f} | {n[0]:10.0f} {n[1]:7.0f} {n[2]:6.0f} | " + " ".join(f"{c:6.1f}" for c in cmr))
print("\nB. Noise decomposition, wide range, C61 100p, no COUT (stages replaced by ideal VCVS)")
for ideal in ((), ("U3A",), ("U3B",), ("U1",), ("U1", "U3B", "U3A")):
    _, _, _, n, _, dens = case("100p", "1f", 0, ideal)
    print(f"  ideal {'+'.join(ideal) or 'none':12}: full-band {n[0]:5.0f} mV rms, density at 316 kHz {dens:5.1f} uV/rtHz input-referred")
