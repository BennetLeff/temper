#!/usr/bin/env python3
"""Monte Carlo of the complete measurement: synthesized captures -> REAL host binary
(calibrate / validate / analyze) or the verified host-equivalent replica.

Structure per scenario: boards x calibrations x repeats.
  board      : SPICE tolerance draw (base_inst1..6; 0 = nominal) + ADC gain/offset/INL/aperture
               mismatch draw + one physical standard set (value error and parasitics)
  calibration: fresh insertions/noise for short, std1, std2 -> host calibrate; check -> validate
  repeat     : fresh insertion/noise for each DUT sweep -> host analyze
Writes results/mc_<scenario>.csv (one row per DUT, frequency and capture).

    mc.py baseline            (real host; 7 boards x 5 calibrations x 3 repeats)
    mc.py corner              (real host; worst-case standards, DDS SNR 55 dB, noise x1.5)
    mc.py whatif              (replica; every configuration on the nominal board)
    mc.py leadmove            (replica; Rev C vs R_iso 22, lead C 100/200 pF moved +/-20 %)
"""
import csv
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import vi_model as vm

HERE = Path(__file__).resolve().parent
HOST = HERE / "work/bin/temper-lcr"
RESULTS = HERE / "results"
F0_NOPAN = round(vm.tank_f0("tank_nopan"))
F0_PAN = round(vm.tank_f0("tank_pan"))
FREQS = [1000.0, float(F0_NOPAN), float(F0_PAN), 35000.0, 40000.0, 50000.0, 60000.0]
DUT_LIST = ["coil_nopan", "coil_pan", "coil_pan_lowR", "cap100n", "bank500n", "bus9u",
            "tank_nopan", "tank_pan"]


@dataclass(frozen=True)
class StdModel:
    """Calibration-standard and fixture realism (ESTIMATES, see README)."""
    value_sigma: float = 2e-4       # entered value vs true (DMM-characterized), 1 sigma
    value_corner: float = 0.0       # if > 0: deterministic worst sign pattern of this size
    l_mean: float = 1.5e-9          # unknown series inductance of resistor standards
    l_sigma: float = 1.0e-9
    l_corner: tuple = ()            # (std1, std2, check) inductance if set
    short_r: float = 0.3e-3
    short_l: float = 2e-9
    contact_max: float = 2e-3       # per-insertion contact resistance ~ U(0, contact_max)


@dataclass(frozen=True)
class Scenario:
    name: str
    config: str = "base"
    pipeline: str = "host"
    boards: tuple = (0, 1, 2, 3, 4, 5, 6)
    n_cal: int = 5
    n_rep: int = 3
    stds: tuple = (20.0, 100.0, 47.0)
    std_model: StdModel = StdModel()
    opts: vm.NoiseOpts = vm.NoiseOpts()
    acq: vm.Acq = vm.Acq()
    dut_config: str = ""            # transfer tag for DUT captures (lead moved after cal)
    duts: tuple = tuple(DUT_LIST)
    freqs: tuple = tuple(FREQS)
    seed: int = 1


def standard_set(sc: Scenario, rng):
    m = sc.std_model
    s1, s2, chk = sc.stds
    if m.value_corner:
        errs = (m.value_corner, -m.value_corner, m.value_corner)
    else:
        errs = tuple(rng.normal(0, m.value_sigma, 3))
    if m.l_corner:
        ls = m.l_corner
    else:
        ls = tuple(max(0.0, x) for x in rng.normal(m.l_mean, m.l_sigma, 3))
    mk = lambda name, r, e, l: vm.Dut(name, "R", r=r * (1 + e), l=l, c=0.2e-12, nominal=r)
    return dict(short=vm.Dut("short", "R", r=m.short_r, l=m.short_l),
                std1=mk("std1", s1, errs[0], ls[0]), std2=mk("std2", s2, errs[1], ls[1]),
                chk=mk("chk", chk, errs[2], ls[2]))


def with_contact(d, rng, m: StdModel):
    rc = rng.uniform(0, m.contact_max)
    return vm.Series(d.name, (d, vm.Dut("contact", "R", r=rc)))


def capture(sc, d, inst, rng):
    """Synthesize one sweep; returns list of (word, div, a, b)."""
    out = []
    for hz in sc.freqs:
        out.append(vm.synth_channels(d, hz, inst, sc.opts, sc.acq, rng))
    return out


def replica_raw(cap, range_ohm=100):
    res = []
    for word, div, a, b in cap:
        rate = (vm.SAMPLE_BASE_HZ / div)
        z, pa, pb = vm.raw_z(a, b, word, rate, range_ohm)
        res.append(z)
    return res


def write_sweep(path, cap):
    recs = [vm.record_json(w, d, a, b) for w, d, a, b in cap]
    with open(path, "w") as fh:
        json.dump(dict(setup=vm.setup_json(100), records=recs), fh)


def host(*args):
    r = subprocess.run([str(HOST), *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def run_unit(job):
    sc, board, cal = job
    rng_board = np.random.default_rng([sc.seed, board, 0])
    stds = standard_set(sc, rng_board)          # same physical standards for every calibration
    inst = vm.draw_instance(board, sc.config)
    inst_dut = replace(inst, transfer_tag=sc.dut_config) if sc.dut_config else inst
    rng = np.random.default_rng([sc.seed, board, cal + 1])
    m = sc.std_model
    caps = {k: capture(sc, with_contact(stds[k], rng, m), inst, rng) for k in ("short", "std1", "std2", "chk")}
    s1n, s2n, chkn = sc.stds
    rows = []
    # replica calibration (always computed; compared with the host where the host runs)
    raw = {k: replica_raw(v) for k, v in caps.items()}
    rcal = [vm.cal_coeffs(raw["short"][i], raw["std1"][i], s1n, raw["std2"][i], s2n)
            for i in range(len(sc.freqs))]
    tmp = Path(tempfile.mkdtemp(prefix=f"mc_{sc.name}_{board}_{cal}_", dir=HERE / "work"))
    try:
        host_ok = sc.pipeline == "host"
        if host_ok:
            for k, v in caps.items():
                write_sweep(tmp / f"{k}.json", v)
            rc, out, err = host("calibrate", tmp / "short.json", tmp / "std1.json", s1n,
                                tmp / "std2.json", s2n, tmp / "cal.json")
            if rc:
                raise RuntimeError(f"host calibrate failed: {err}")
            rc, out, err = host("validate", tmp / "chk.json", tmp / "cal.json", chkn, 1.0)
            chk_lines = [l for l in out.splitlines() if "complex error" in l]
        # check standard via replica as well
        for i, hz in enumerate(sc.freqs):
            zc = vm.correct(raw["chk"][i], rcal[i])
            rows.append(dict(scenario=sc.name, board=board, cal=cal, rep=0, dut="chk_standard", freq=hz,
                             true_re=chkn, true_im=0.0, meas_re=zc.real, meas_im=zc.imag,
                             host_re="", host_im="", valid=1,
                             host_validate=(chk_lines[i] if host_ok and i < len(chk_lines) else "")))
        for dn in sc.duts:
            d = vm.DUTS[dn]
            for rep in range(sc.n_rep):
                cap = capture(sc, with_contact(d, rng, m), inst_dut, rng)
                rz = replica_raw(cap)
                hz_vals = [None] * len(sc.freqs)
                valid = [1] * len(sc.freqs)
                if host_ok:
                    write_sweep(tmp / "dut.json", cap)
                    rc, out, err = host("analyze", tmp / "dut.json", tmp / "cal.json")
                    ms = json.loads(out)
                    hz_vals = [complex(x["impedance_ohm"]["re"], x["impedance_ohm"]["im"]) for x in ms]
                    valid = [int(x["valid"]) for x in ms]
                for i, hz in enumerate(sc.freqs):
                    f_act = vm.frequency_hz(vm.frequency_word(hz))
                    zt = d.z(f_act)
                    zr = vm.correct(rz[i], rcal[i])
                    rows.append(dict(scenario=sc.name, board=board, cal=cal, rep=rep, dut=dn, freq=hz,
                                     true_re=float(np.real(zt)), true_im=float(np.imag(zt)),
                                     meas_re=zr.real, meas_im=zr.imag,
                                     host_re=hz_vals[i].real if hz_vals[i] is not None else "",
                                     host_im=hz_vals[i].imag if hz_vals[i] is not None else "",
                                     valid=valid[i], host_validate=""))
    finally:
        for p in tmp.glob("*"):
            p.unlink()
        tmp.rmdir()
    return rows


def run(sc: Scenario, workers=3):
    jobs = [(sc, b, c) for b in sc.boards for c in range(sc.n_cal)]
    rows = []
    with Pool(workers) as pool:
        for r in pool.imap_unordered(run_unit, jobs):
            rows += r
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"mc_{sc.name}.csv"
    rows.sort(key=lambda r: (r["dut"], r["freq"], r["board"], r["cal"], r["rep"]))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.12g}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"{path.relative_to(HERE)}: {len(rows)} rows")


WORST = StdModel(value_corner=1e-3, l_corner=(5e-9, 0.0, 5e-9), short_r=2e-3, short_l=5e-9,
                 contact_max=6e-3)
WORST_OPTS = vm.NoiseOpts(dds_snr_db=55.0, opa_scale=1.5)


def scenarios(which):
    if which == "baseline":
        return [Scenario("baseline")]
    if which == "corner":
        return [Scenario("corner", boards=(0, 3), n_cal=3, std_model=WORST, opts=WORST_OPTS)]
    if which == "whatif":
        nb = dict(pipeline="replica", boards=(0,), n_cal=16, n_rep=3, std_model=StdModel(value_sigma=0.0,
                  l_mean=0.0, l_sigma=0.0, short_r=0.0, short_l=0.0, contact_max=0.0))
        return [
            Scenario("wi_base", **nb),
            Scenario("wi_r33", config="r33", stds=(6.8, 33.0, 15.0), **nb),
            Scenario("wi_r33_20mA", config="r33", stds=(6.8, 33.0, 15.0), acq=vm.Acq(amp_scale=0.367), **nb),
            Scenario("wi_gain2", config="gain2", **nb),
            Scenario("wi_again4", config="again4", **nb),
            Scenario("wi_amp2", acq=vm.Acq(amp_scale=2.0), **nb),
            Scenario("wi_boxcar", acq=vm.Acq(boxcar=True), **nb),
            Scenario("wi_gain2_boxcar", config="gain2", acq=vm.Acq(boxcar=True), **nb),
            Scenario("wi_riso22", config="riso22", **nb),
            Scenario("wi_base_c200", config="base_c200", **nb),
            Scenario("wi_riso22_c200", config="riso22_c200", **nb),
        ]
    if which == "leadmove":
        out = []
        nb = dict(pipeline="replica", boards=(0,), n_cal=3, n_rep=2, std_model=StdModel(value_sigma=0.0,
                  l_mean=0.0, l_sigma=0.0, short_r=0.0, short_l=0.0, contact_max=0.0))
        for arch in ("base", "riso22"):
            for c, lo, hi in ((100, 80, 120), (200, 160, 240)):
                for moved in (lo, hi):
                    out.append(Scenario(f"lm_{arch}_c{c}_to{moved}", config=f"{arch}_c{c}",
                                        dut_config=f"{arch}_c{moved}", **nb))
        return out
    raise SystemExit(f"unknown scenario set {which}")


if __name__ == "__main__":
    for sc in scenarios(sys.argv[1] if len(sys.argv) > 1 else "baseline"):
        run(sc, workers=3)
