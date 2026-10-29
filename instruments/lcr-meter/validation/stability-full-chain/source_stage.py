#!/usr/bin/env python3
"""Rev E U5 (OPA810) difference stage: C34/C35 as one 270 pF part vs two 560 pF C0G in series.

python3 validation/stability-full-chain/source_stage.py    (ngspice on PATH; writes source_stage.json)

Deck: the generated codecbase case
  final_codec_r100_matched_stray1000_revd_risolo22_none_caplead4.87_local100_lead21.65_tia.cir
(codec-template.cir + Rev D extracted board string), so the X5 stage sees the same models, rails and
loads as every other Rev E loop.  Three things per variant:
  1. X5 return ratio, same two-injection bridge method and formula as loop_matrix.rs (return_ratio,
     bridge 100 ohm, injection at the inverting input srcfb).  Self-check first: the unmodified deck's
     TIA loop must reproduce its committed row in matrix-final_codecbase.md (19.5149 MHz / 95.04 deg).
  2. Differential DAC -> EXCITE / SOURCE gain and phase at 45 Hz ... 85 kHz.
  3. Common-mode DAC -> EXCITE (the 1.65 V codec common mode the stage must reject), with the two
     capacitor strings at opposite 5 % tolerance corners.
Series variants model the midpoint node: copper to GND and each capacitor's ESL plus its trace.
"""
import cmath
import json
import math
import pathlib
import re
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE / "final_codec_r100_matched_stray1000_revd_risolo22_none_caplead4.87_local100_lead21.65_tia.cir"
REF_ROW = (19.5149e6, 95.04)          # matrix-final_codecbase.md, same deck, TIA loop
BRIDGE = 100.0
FREQS = [45.0, 100.0, 1e3, 10e3, 27e3, 60e3, 85e3]
# DAC-image band: the modulator multiples (1.5-12 MHz) and twice them, for rev_e_spurs-style image error.
HF = sorted(set([round(10 ** (4 + i * (math.log10(30e6) - 4) / 120)) for i in range(121)]
                + [300e3, 1e6, 2e6, 4e6, 6e6, 8e6, 12e6, 16e6]))
# U5 part: the as-built OPA197 (2026-10-29) or the OPA810 it replaced.  TI's OPAx197 macro-model
# (sources/ti/models/OPAx197.LIB) has pin order IN+ IN- VCC VEE OUT.
U5_LIB = HERE.parents[1] / "sources/ti/models/OPAx197.LIB"


def strings(c34, c35):
    """Netlist lines for the ground leg (acin-0) and feedback (excite-srcfb) capacitors.
    Each argument: ('single', C) or ('series', Ca, Cb, Cmid_to_gnd, L_each)."""
    out = []
    for name, a, b, spec in (("sb", "acin", "0", c34), ("sf", "excite", "srcfb", c35)):
        if spec[0] == "single":
            out.append(f"C{name} {a} {b} {spec[1]:.6g}")
        else:
            _, ca, cb, cmid, l = spec
            out += [f"L{name}a {a} {name}_la {l:.6g}", f"C{name}a {name}_la {name}_mid {ca:.6g}",
                    f"C{name}b {name}_mid {name}_lb {cb:.6g}", f"L{name}b {name}_lb {b} {l:.6g}",
                    f"C{name}m {name}_mid 0 {cmid:.6g}",
                    f"R{name}m {name}_mid 0 1e11"]     # C0G insulation resistance >= 10 GOhm: DC path
    return out


def deck(variant_lines, mode, tag, work, u5="OPA810", freqs=None):
    freqs = FREQS if freqs is None else freqs
    s = BASE.read_text()
    if u5 == "OPA197":
        assert "X5 acin srcfb excite vp vn OPA810" in s
        s = s.replace("X5 acin srcfb excite vp vn OPA810", "X5 acin srcfb vp vn excite OPAx197")
        s = s.replace(".include ../../sources/ti/models/opa810_a.lib",
                      ".include ../../sources/ti/models/opa810_a.lib\n.include ../../sources/ti/models/OPAx197.LIB")
    s = s.replace(".include ../../sources", f".include {HERE.parents[1] / 'sources'}")
    seed = HERE / "codec-seed.inc"
    if u5 == "OPA197":   # the seed's OPA810-internal guesses (x5.*) do not exist in the OPA197 model
        seed = HERE / "codec-seed-u5-opa197.inc"
    s = s.replace(".include codec-seed.inc", f".include {seed}")
    s = s.split(".control")[0]
    if mode != "tia":   # restore the TIA, drop its probe
        s = s.replace("X7A 0 probe_f tia vp vn OPA2810", "X7A 0 sum tia vp vn OPA2810")
        s = "\n".join(l for l in s.splitlines()
                      if not re.match(r"(Rbridge|Iinj|Iinj2) |\.nodeset v\(probe_f\)", l)) + "\n"
    s = "\n".join(l for l in s.splitlines() if not re.match(r"C(sb|sf) ", l)) + "\n"
    s += "\n".join(variant_lines) + "\n"
    if mode == "source":
        if u5 == "OPA197":
            s = s.replace("X5 acin srcfb vp vn excite OPAx197", "X5 acin probe_f vp vn excite OPAx197")
        else:
            assert "X5 acin srcfb excite vp vn OPA810" in s
            s = s.replace("X5 acin srcfb excite vp vn OPA810", "X5 acin probe_f excite vp vn OPA810")
        s += (f"Rbridge srcfb probe_f {BRIDGE}\nIinj 0 srcfb DC 0 AC 1\nIinj2 0 probe_f DC 0 AC 0\n"
              ".nodeset v(probe_f)=0.00007590665\n")
    if mode in ("tia", "source"):
        node = "sum" if mode == "tia" else "srcfb"
        ctl = (f"ac dec 120 1 1G\nlet ve=v({node})\nlet vf=v(probe_f)\n"
               f"wrdata {tag}_e.dat real(ve) imag(ve) real(vf) imag(vf)\n"
               f"alter Iinj ac=0\nalter Iinj2 ac=1\nac dec 120 1 1G\nlet ve=v({node})\nlet vf=v(probe_f)\n"
               f"wrdata {tag}_f.dat real(ve) imag(ve) real(vf) imag(vf)\n")
    else:
        if mode == "diff":
            s = s.replace("Vdacp dacp0 0 DC 1.65 AC 0", "Vdacp dacp0 0 DC 1.65 AC 0.5")
            s = s.replace("Vdacm dacm0 0 DC 1.65 AC 0", "Vdacm dacm0 0 DC 1.65 AC 0.5 180")
        else:
            s = s.replace("Vdacp dacp0 0 DC 1.65 AC 0", "Vdacp dacp0 0 DC 1.65 AC 1")
            s = s.replace("Vdacm dacm0 0 DC 1.65 AC 0", "Vdacm dacm0 0 DC 1.65 AC 1")
        ctl = "".join(f"ac lin 1 {f:g} {f:g}\nwrdata {tag}_{i}.dat real(v(excite)) imag(v(excite)) "
                    f"real(v(source)) imag(v(source))\n" for i, f in enumerate(freqs))
    s += (".control\nset klu\noptran 1 0 0 0 0 0\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\n"
          f"wrdata {tag}_dc.dat v(excite) v(source) v(srcfb) v(acin)\n" + ctl + "quit\n.endc\n.end\n")
    (work / f"{tag}.cir").write_text(s)
    (work / ".spiceinit").write_text((HERE / ".spiceinit").read_text())   # ngbehavior=ps for the TI models
    r = subprocess.run(["ngspice", "-b", f"{tag}.cir"], cwd=work, capture_output=True, text=True)
    (work / f"{tag}.log").write_text(r.stdout + r.stderr)
    assert r.returncode == 0, (tag, r.stderr[-2000:])


def rows(path):
    lines = path.read_text().split("\n")[1:]
    return [[float(x) for x in l.split()] for l in lines if l.strip()]


def return_ratio(z11, z21, z12, z22, r):
    det = z11 * z22 - z12 * z21
    gd = (2 / r) * det
    return (gd - z12 - z21) / (z11 + z22 - gd)


def loop(work, tag):
    e, f = rows(work / f"{tag}_e.dat"), rows(work / f"{tag}_f.dat")
    pts, prev = [], None
    for a, b in zip(e, f):
        assert a[0] == b[0]
        t = return_ratio(complex(a[1], a[2]), complex(a[3], a[4]), complex(b[1], b[2]), complex(b[3], b[4]), BRIDGE)
        ph = math.degrees(cmath.phase(t))
        if prev is not None:
            while ph - prev > 180:
                ph -= 360
            while ph - prev < -180:
                ph += 360
        prev = ph
        pts.append((a[0], 20 * math.log10(abs(t)), ph, abs(1 + t)))
    cross = []
    for a, b in zip(pts, pts[1:]):
        if (a[1] >= 0 > b[1]) or (a[1] < 0 <= b[1]):
            k = a[1] / (a[1] - b[1])
            fq = math.exp(math.log(a[0]) + k * math.log(b[0] / a[0]))
            ph = a[2] + k * (b[2] - a[2])
            pm = (180 + ph + 180) % 360 - 180
            cross.append({"f_hz": fq, "phase_margin_deg": pm, "dir": "down" if b[1] < a[1] else "up"})
    m = min(pts, key=lambda p: p[3])
    return {"crossings": cross, "min_abs_1_plus_t": m[3], "at_hz": m[0],
            "t_db_at_85khz": next(p[1] for p in pts if p[0] >= 85e3)}


def transfer(work, tag, freqs=None):
    out = {}
    for i, f in enumerate(FREQS if freqs is None else freqs):
        r = rows(work / f"{tag}_{i}.dat")[0]
        out[f] = {"excite": complex(r[1], r[2]), "source": complex(r[3], r[4])}
    return out


C270, C560, TOL = 270e-12, 560e-12, 0.05
VARIANTS = {
    # name: (c34 spec, c35 spec)
    "HEAD 270p single": (("single", C270), ("single", C270)),
    "280p ideal": (("single", C560 / 2), ("single", C560 / 2)),
    "2x560p series, mid 0.5 pF, 1.5 nH each": (("series", C560, C560, 0.5e-12, 1.5e-9),) * 2,
    "2x560p series, mid 2 pF, 3 nH each (stress)": (("series", C560, C560, 2e-12, 3e-9),) * 2,
}
CM_CORNERS = {
    "HEAD 270p, C34 +5 % / C35 -5 %": (("single", C270 * 1.05), ("single", C270 * 0.95)),
    "HEAD 270p, C34 -5 % / C35 +5 %": (("single", C270 * 0.95), ("single", C270 * 1.05)),
    "2x560p, C34 string +5 % / C35 string -5 %": (("series", C560 * 1.05, C560 * 1.05, 0.5e-12, 1.5e-9),
                                                  ("series", C560 * 0.95, C560 * 0.95, 0.5e-12, 1.5e-9)),
    "2x560p, C34 string -5 % / C35 string +5 %": (("series", C560 * 0.95, C560 * 0.95, 0.5e-12, 1.5e-9),
                                                  ("series", C560 * 1.05, C560 * 1.05, 0.5e-12, 1.5e-9)),
}


def main():
    res = {"deck": BASE.name, "bridge_ohm": BRIDGE, "freqs_hz": FREQS, "variants": {}, "cm_corners": {}}
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        # self-check: committed TIA row
        deck(strings(("single", C270), ("single", C270)), "tia", "selfcheck", work)
        sc = loop(work, "selfcheck")["crossings"][0]
        assert abs(sc["f_hz"] / REF_ROW[0] - 1) < 1e-3 and abs(sc["phase_margin_deg"] - REF_ROW[1]) < 0.05, sc
        res["selfcheck_tia"] = {"reproduced": sc, "committed": {"f_hz": REF_ROW[0], "phase_margin_deg": REF_ROW[1]}}
        print(f"self-check TIA loop: {sc['f_hz']/1e6:.4f} MHz / {sc['phase_margin_deg']:.2f} deg "
              f"(committed {REF_ROW[0]/1e6:.4f} MHz / {REF_ROW[1]:.2f} deg)")
        ref = None
        for i, (name, (c34, c35)) in enumerate(VARIANTS.items()):
            lines = strings(c34, c35)
            deck(lines, "source", f"v{i}_loop", work)
            deck(lines, "diff", f"v{i}_diff", work)
            deck(lines, "cm", f"v{i}_cm", work)
            lp, tr, cm = loop(work, f"v{i}_loop"), transfer(work, f"v{i}_diff"), transfer(work, f"v{i}_cm")
            ref = ref or tr
            row = {"x5_loop": lp, "diff": {}, "cm_excite_db": {}}
            for f in FREQS:
                g = tr[f]["excite"]
                row["diff"][f] = {"excite_gain": abs(g), "excite_phase_deg": math.degrees(cmath.phase(g)),
                                  "vs_head_db": 20 * math.log10(abs(g) / abs(ref[f]["excite"])),
                                  "vs_head_deg": math.degrees(cmath.phase(g / ref[f]["excite"])),
                                  "source_over_excite": abs(tr[f]["source"] / g)}
                row["cm_excite_db"][f] = 20 * math.log10(abs(cm[f]["excite"]))
            res["variants"][name] = row
            c = lp["crossings"]
            print(f"\n{name}\n  X5 loop: " + "; ".join(f"{x['f_hz']/1e6:.3f} MHz / {x['phase_margin_deg']:.2f} deg ({x['dir']})" for x in c)
                  + f"; min |1+T| {lp['min_abs_1_plus_t']:.3f} at {lp['at_hz']/1e6:.1f} MHz")
            for f in FREQS:
                d = row["diff"][f]
                print(f"  {f:>7g} Hz  gain {d['excite_gain']:.5f}  phase {d['excite_phase_deg']:+8.3f} deg  "
                      f"vs HEAD {d['vs_head_db']:+.4f} dB {d['vs_head_deg']:+.3f} deg  CM {row['cm_excite_db'][f]:+.1f} dB")
        for i, (name, (c34, c35)) in enumerate(CM_CORNERS.items()):
            deck(strings(c34, c35), "cm", f"cm{i}", work)
            cm = transfer(work, f"cm{i}")
            res["cm_corners"][name] = {f: 20 * math.log10(abs(cm[f]["excite"])) for f in FREQS}
            print(f"CM corner {name}: " + ", ".join(f"{f:g} Hz {res['cm_corners'][name][f]:+.1f} dB" for f in (1e3, 27e3, 85e3)))
        # U5 OPA810 -> OPA197.  The OPA197 operating point does not converge (strict Newton, as committed)
        # on the 2x560 pF strings; on OPA810 the strings and an ideal 280 pF agree within 0.03 dB to 16 MHz
        # (below), so the OPA197 rows use 280 pF.
        u5 = {}
        for part, (name, spec) in (("OPA810", ("2x560p series", VARIANTS["2x560p series, mid 0.5 pF, 1.5 nH each"])),
                                   ("OPA810 ", ("280p ideal", VARIANTS["280p ideal"])),
                                   ("OPA197", ("280p ideal", VARIANTS["280p ideal"]))):
            tag = f"u5_{part.strip()}_{name[:4]}"
            lines = strings(*spec)
            deck(lines, "source", tag + "_loop", work, u5=part.strip())
            deck(lines, "diff", tag + "_hf", work, u5=part.strip(), freqs=HF)
            lp, tr = loop(work, tag + "_loop"), transfer(work, tag + "_hf", HF)
            u5[f"{part.strip()} {name}"] = {
                "x5_loop": lp,
                "dac_to_source": {f: [tr[f]["source"].real, tr[f]["source"].imag] for f in HF},
                "dac_to_excite": {f: [tr[f]["excite"].real, tr[f]["excite"].imag] for f in HF}}
            pm = min(c["phase_margin_deg"] for c in lp["crossings"] if c["dir"] == "down")
            g0 = abs(tr[HF[0]]["excite"])
            print(f"U5 {part.strip()} {name}: loop {pm:.2f} deg; DAC->EXCITE re 10 kHz " + ", ".join(
                f"{f/1e6:g} MHz {20*math.log10(abs(tr[f]['excite'])/g0):+.2f} dB" for f in (1e6, 4e6, 8e6, 12e6, 16e6)))
        res["u5_parts"] = u5
    (HERE / "source_stage.json").write_text(json.dumps(res, indent=1, default=str) + "\n")


if __name__ == "__main__":
    main()
