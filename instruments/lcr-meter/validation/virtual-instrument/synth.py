#!/usr/bin/env python3
"""Synthesize a Temper LCR Rev C capture sweep in the exact host JSON format.

    synth.py --dut coil_nopan --freqs 1000,35000,40000,50000,60000 --seed 7 --out dut.json
    synth.py --dut R:47.0,1.5e-9 --freqs 40000 --seed 1 --out chk.json      (series R, L)
    synth.py --list

The record contains 16,384 simultaneous pairs at 1 MSPS / divider_for(f), the DDS tuning word
for f, a valid CRC32, 16-bit quantization/clipping and the per-board ADC aperture mismatch.  Board
instance 0 is nominal; 1..6 use SPICE tolerance draws (chain_spice.py --instance).  The module
functions in vi_model.py are the reusable backend (a later serial emulator can call
synth_channels() per CAPTURE command)."""
import argparse
import json
import sys

import numpy as np

import vi_model as vm


def parse_dut(spec):
    if spec in vm.DUTS:
        return vm.DUTS[spec]
    if spec.startswith("R:"):
        vals = [float(x) for x in spec[2:].split(",")]
        r, l = vals[0], (vals[1] if len(vals) > 1 else 0.0)
        return vm.Dut(f"R{r:g}", "R", r=r, l=l, nominal=r)
    if spec.startswith("C:"):
        vals = [float(x) for x in spec[2:].split(",")]
        return vm.Dut(f"C{vals[0]:g}", "cap", c=vals[0], tan_d=vals[1] if len(vals) > 1 else 0.0)
    raise SystemExit(f"unknown DUT {spec}; use --list, R:ohm[,henry] or C:farad[,tan_delta]")


def sweep(dut, freqs, config="base", instance=0, seed=0, range_ohm=100, opts=None, acq=None,
          unit="virtual-1", fixture="vfix-1"):
    opts = opts or vm.NoiseOpts()
    acq = acq or vm.Acq()
    if acq.boxcar:
        raise ValueError("boxcar samples are int32 sums; the protocol-1 host format cannot hold them")
    inst = vm.draw_instance(instance, config)
    rng = np.random.default_rng(seed)
    recs = []
    for hz in freqs:
        word, div, a, b = vm.synth_channels(dut, hz, inst, opts, acq, rng)
        recs.append(vm.record_json(word, div, a, b))
    return dict(setup=vm.setup_json(range_ohm, unit, fixture), records=recs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dut")
    ap.add_argument("--freqs", default="1000,35000,40000,50000,60000")
    ap.add_argument("--config", default="base", help="transfer model: base, r33, gain2, again4, r5k")
    ap.add_argument("--range", type=int, default=100, help="range written to the record (host identity)")
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--amp-scale", type=float, default=1.0)
    ap.add_argument("--dds-snr-db", type=float, default=60.0)
    ap.add_argument("--out")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, d in vm.DUTS.items():
            print(f"{k:14s} |Z(40 kHz)| = {abs(d.z(40e3)):.4g} ohm")
        return 0
    if not (a.dut and a.out):
        ap.error("--dut and --out are required")
    s = sweep(parse_dut(a.dut), [float(f) for f in a.freqs.split(",")], a.config, a.instance, a.seed,
              a.range, vm.NoiseOpts(dds_snr_db=a.dds_snr_db), vm.Acq(amp_scale=a.amp_scale))
    with open(a.out, "w") as fh:
        json.dump(s, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
