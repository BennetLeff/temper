#!/usr/bin/env python3
"""Validate the bilinear transfer model against (1) direct full-chain SPICE AC runs with the
actual stage53-equivalent DUT elements at off-grid frequencies and (2) the committed transient
results in ../solver-resolution-fixed-local/stage53-results.csv (uncalibrated complex Z and ADC
peak amplitudes).  Writes results/transfer_validation.json."""
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np

import chain_spice as cs
import vi_model as vm

HERE = Path(__file__).resolve().parent
TRANSIENT = HERE / "../solver-resolution-fixed-local/stage53-results.csv"
CASES = {  # name -> (DUT element lines, frequency, Z function)
    "stage100n": (["CDUT hi low 100n"], 50000.0, lambda f: 1 / (2j * np.pi * f * 100e-9)),
    "stage500n": (["CDUT hi low 500n"], 50000.0, lambda f: 1 / (2j * np.pi * f * 500e-9)),
    "stage9u": (["CDUT hi low 9u"], 1000.0, lambda f: 1 / (2j * np.pi * f * 9e-6)),
    "stagecoil": (["LDUT hi dmid 50u", "RDUTS dmid low 0.5"], 50000.0,
                  lambda f: 0.5 + 2j * np.pi * f * 50e-6),
    "coil_nopan_40k": (["LDUT hi dmid 66.3u", "RDUTS dmid low 0.193", "CDUTW hi low 50p"], 40000.0,
                       lambda f: 1 / (1 / (0.193 + 2j * np.pi * f * 66.3e-6) + 2j * np.pi * f * 50e-12)),
    "tank_offgrid": (["LDUT hi dmid 41.97u", "RDUTS dmid dm2 2.4", "CDUTT dm2 low 500n"], 34730.0,
                     lambda f: 2.4 + 2j * np.pi * f * 41.97e-6 + 1 / (2j * np.pi * f * 500e-9)),
}


def direct(name, lines, f):
    lines0, _ = cs.netlist(cs.CONFIGS["base"], 100.0, noise=False)
    body = []
    for l in lines0:
        if l.startswith("RDUT "):
            body += lines
        elif l.startswith("Vdds "):
            body.append("Vdds dds0 0 DC 0.3 AC 1")
        else:
            body.append(l)
    stem = f"val_{name}z"
    head = ["RevC virtual instrument direct DUT validation",
            f".include {cs.MODELS}/opa2810_a.lib", f".include {cs.MODELS}/opa810_a.lib",
            f".include {cs.MODELS}/ths4551.lib",
            ".options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear", f".include {cs.SEED_INC}"]
    ctl = [".control", "set klu", "set wr_singlescale", "set wr_vecnames", "set numdgt=15",
           "set filetype=ascii", "op", f"write {stem}_op.raw all", f"ac lin 1 {f} {f}",
           f"wrdata {stem}.dat real(v(aadc_p)-v(aadc_m)) imag(v(aadc_p)-v(aadc_m)) "
           f"real(v(badc_p)-v(badc_m)) imag(v(badc_p)-v(badc_m))", "quit", ".endc", ".end"]
    os.chdir(cs.WORK)
    (cs.WORK / ".spiceinit").write_text((HERE / "spiceinit").read_text())
    Path(f"{stem}.cir").write_text("\n".join(head + body + ctl) + "\n")
    r = subprocess.run([str(cs.OP_GUARD), "order", stem, f"{stem}.cir", f"{stem}-ordered.cir"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    with open(f"{stem}.log", "w") as log:
        subprocess.run([cs.NGSPICE, "-b", f"{stem}-ordered.cir"], stdout=log, stderr=log, check=True)
    if re.search(r"\berror\b|aborted", Path(f"{stem}.log").read_text(), re.I):
        raise RuntimeError(f"{stem} log reports an error")
    chk = subprocess.run([str(cs.OP_GUARD), "check", f"{stem}_op.raw"], capture_output=True, text=True)
    if chk.returncode:
        raise RuntimeError(chk.stderr)
    a = np.loadtxt(f"{stem}.dat", skiprows=1).reshape(-1)
    for p in Path(".").glob(f"{stem}-order*.raw"):
        p.unlink()
    return complex(a[1], a[2]), complex(a[3], a[4]), int(r.stdout.split()[1]), chk.stdout.strip()


def main():
    tr = vm.transfer("base")
    trans = {}
    for row in Path(TRANSIENT).read_text().splitlines()[1:]:
        c = row.split(",")
        trans[c[0]] = c
    header = Path(TRANSIENT).read_text().splitlines()[0].split(",")
    out = {}
    for name, (lines, f, zf) in CASES.items():
        a_sp, b_sp, order, opchk = direct(name, lines, f)
        HA, HB = tr.H([f], [zf(f)], names=["dds"])
        adc = 1 / (1 + 1j * f / vm.Transfer.ADC_BW_HZ)  # model includes ADC pole; SPICE does not
        a_m, b_m = HA[0, 0] / adc, HB[0, 0] / adc
        zraw_sp = vm.feedback(100, f) * a_sp / b_sp
        zraw_m = vm.feedback(100, f) * a_m / b_m
        rec = dict(frequency_hz=f, spice_order=order, op_check=opchk,
                   spice_A_peak_v=abs(a_sp) * 0.3, spice_B_peak_v=abs(b_sp) * 0.3,
                   model_vs_spice_A_rel=abs(a_m / a_sp - 1), model_vs_spice_B_rel=abs(b_m / b_sp - 1),
                   uncal_z_spice=[zraw_sp.real, zraw_sp.imag], uncal_z_model=[zraw_m.real, zraw_m.imag],
                   true_z=[zf(f).real, zf(f).imag])
        if name in trans:
            c = dict(zip(header, trans[name]))
            zt = complex(float(c["uncalibrated_fit_re_ohm"]), float(c["uncalibrated_fit_im_ohm"]))
            rec["transient"] = c
            rec["transient_A_peak_rel_diff"] = abs(abs(a_sp) * 0.3 / float(c["a_peak_v"]) - 1) if "a_peak_v" in c else None
            rec["transient_B_peak_rel_diff"] = abs(abs(b_sp) * 0.3 / float(c["b_peak_v"]) - 1) if "b_peak_v" in c else None
            if zt is not None:
                rec["ac_vs_transient_uncal_z_abs_diff_ohm"] = abs(zraw_sp - zt)
                rec["ac_vs_transient_uncal_z_rel_diff"] = abs(zraw_sp - zt) / abs(zt)
        out[name] = rec
        print(name, json.dumps({k: v for k, v in rec.items() if k not in ("transient",)}, default=str))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/transfer_validation.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
