#!/usr/bin/env python3
"""Rev E option C noise check: TAC5112/TAC5212 codec in place of AD9833 + OPA810 stage + THS4551 + ADS9224R.

Reuses the Rev D virtual instrument (../virtual-instrument, transfer 'riso22') and its fitted-phasor
noise method (noise_budget.phasor_noise): E|dP|^2 = 2 S1(f0) / T, dZ/Z = dA/A - dB/B per alias.
Changes for the codec chain:
  - the source chain (AD9833, RC reconstruction, coupling, OPA810 x6) is replaced by the codec DAC
    driving the U6A source-buffer input at the Rev D amplitude.  DAC noise = full scale / 10^(DR/20)
    over 20 kHz (datasheet), times WIDEBAND_DAC (ASSUMED x2: no DAC noise figure above 20 kHz is
    published), plus a gain/level stage with OPA810-class noise at noise gain 2 (ASSUMED);
  - the FDA groups are removed: the codec's differential inputs take channel A (HIGH - LOW) and
    channel B (TIA output, attenuated by K_B so 3.6 Vpp fits the codec input; ASSUMED 0.7);
  - codec ADC noise from the wideband SNR integrated to 85 kHz against 2 Vrms differential full scale
    (TAC5112 91 dB, TAC5212 89 dB; sources/rev-e/TAC5112.txt, TAC5212.txt "Wideband Mode");
  - analog noise is not folded at the output rate (the decimation filter removes > 90 dB, survey
    §Option C); it is folded around multiples of the modulator rate F_MOD (ASSUMED 6.144 MHz, not
    published) through an external one-pole anti-alias RC at F_AA (design choice 500 kHz).
Output: results/noise_codec.json and a table of worst-case 1-sigma noise per Temper target, codec vs
the Rev D SAR chain at equal capture time.
"""
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VI = HERE.parent / "virtual-instrument"
sys.path.insert(0, str(VI))
import vi_model as vm  # noqa: E402
import noise_budget as nb  # noqa: E402
from summarize import TARGETS  # noqa: E402

CONFIG = "riso22"
WIDEBAND_DAC = 2.0
K_B = 0.7
F_MOD = 6.144e6
F_AA = 500e3
DAC_FS_RMS = 2.0          # differential line-out full scale (TAC5x12 p1)
CODECS = {"TAC5112": dict(adc_snr_db=91.0, dac_dr_db=114.0), "TAC5212": dict(adc_snr_db=89.0, dac_dr_db=120.0)}
AFE = ["en_x6a", "en_x6b", "en_x7b", "en_x7a", "in_x7a_m", "nr_RG", "nr_RF", "nr_Risolo", "dut"]


def codec_phasor_noise(dut, hz, codec, T, o=vm.NoiseOpts()):
    c = CODECS[codec]
    tr = vm.transfer(CONFIG)
    f0 = vm.frequency_hz(vm.frequency_word(hz))
    z0 = dut.z(f0)
    # Source amplitude at the U6A input equal to Rev D's: DDS amplitude times the DDS -> U6A-input gain.
    Hd_a, _ = tr.H([f0], [z0], names=["dds"])
    Hx_a, Hx_b = tr.H([f0], [z0], names=["en_x6a"])
    amp = o.dds_amp_v * abs(Hd_a[0, 0] / Hx_a[0, 0])
    A0, B0 = amp * Hx_a[0, 0], K_B * amp * Hx_b[0, 0]
    # DAC + level stage noise referred to the U6A input, scaled with the signal from full scale.
    dac_density = DAC_FS_RMS / 10 ** (c["dac_dr_db"] / 20) / math.sqrt(20e3) * WIDEBAND_DAC
    dac_density *= amp / (DAC_FS_RMS * math.sqrt(2))
    stage_density = 2 * o.opa810_en
    src_psd = dac_density ** 2 + stage_density ** 2
    var = {}
    # Direct band (no output-rate folding) plus modulator-rate aliases through the anti-alias pole.
    fl = [(f0, False)] + [(m * F_MOD + s * f0, s < 0) for m in range(1, 8) for s in (1, -1)]
    for f, mirror in fl:
        zf = dut.z(np.array([f]))
        HA, HB = tr.H([f], zf, names=AFE)
        aa = 1.0 / abs(1 + 1j * f / F_AA) ** 2 if f != f0 else 1.0
        S = vm.densities(tr, np.array([f]), zf, o)[[tr.names.index(n) for n in AFE]]
        S[0] = S[0] + src_psd  # en_x6a carries the DAC and level-stage noise as well
        if mirror:
            g = np.conj(HA[:, 0]) / A0 - K_B * np.conj(HB[:, 0]) / B0
        else:
            g = HA[:, 0] / A0 - K_B * HB[:, 0] / B0
        for n, v in zip(AFE, (2 / T) * S[:, 0] * np.abs(g) ** 2 * aa):
            key = "source (DAC + level stage + U6A)" if n == "en_x6a" else n
            var[key] = var.get(key, 0.0) + float(v)
    adc_rms = 2.0 / 10 ** (c["adc_snr_db"] / 20)
    s_adc = adc_rms ** 2 / 85e3
    var["codec ADC"] = (2 / T) * s_adc * (1 / abs(A0) ** 2 + 1 / abs(B0) ** 2)
    tot = sum(var.values())
    sig = abs(z0) * math.sqrt(tot / 2)
    return dict(dut=dut.name, hz=hz, z_true=[float(z0.real), float(z0.imag)], sigma_rel_z=math.sqrt(tot),
                sigma_x_ohm=sig, sigma_r_ohm=sig, a_peak_v=abs(A0), b_peak_v=abs(B0),
                a_fs=abs(A0) / (DAC_FS_RMS * math.sqrt(2)), b_fs=abs(B0) / (DAC_FS_RMS * math.sqrt(2)),
                var_share={k: v / tot for k, v in var.items()})


def main():
    rows, detail = [], []
    for tid, dn, freqs, q, tol, unit, _ in TARGETS:
        row = dict(target=tid, quantity=q, tolerance=tol, unit=unit)
        for label in ("SAR", *CODECS):
            worst = 0.0
            for hz in freqs:
                dut = vm.DUTS[dn]
                base = nb.phasor_noise(CONFIG, dut, hz, acq=vm.Acq(boxcar=True))
                T = vm.DEFAULT_COUNT / (vm.SAMPLE_BASE_HZ / base["divider"])
                r = base if label == "SAR" else codec_phasor_noise(dut, hz, label, T)
                if label != "SAR":
                    detail.append(dict(codec=label, capture_s=T, **r))
                worst = max(worst, nb.sigma_in_units(q, unit, r, dn, hz))
            row[f"sigma_{label}"] = worst
            row[f"2sigma_over_tol_{label}"] = 2 * worst / tol
        rows.append(row)
    out = dict(assumptions=dict(wideband_dac=WIDEBAND_DAC, k_b=K_B, f_mod_hz=F_MOD, f_aa_hz=F_AA, config=CONFIG,
                                capture="equal to the Rev D SAR capture time at each point (16384 boxcar outputs)"),
               targets=rows, points=detail)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/noise_codec.json").write_text(json.dumps(out, indent=1))
    print(f"{'target':34s} {'tol':>9s}  2sigma/tol: SAR     TAC5112  TAC5212")
    for r in rows:
        print(f"{r['target']:34s} {r['tolerance']:9.3g}  {r['2sigma_over_tol_SAR']*100:7.2f}% "
              f"{r['2sigma_over_tol_TAC5112']*100:7.2f}% {r['2sigma_over_tol_TAC5212']*100:7.2f}%")


if __name__ == "__main__":
    main()
