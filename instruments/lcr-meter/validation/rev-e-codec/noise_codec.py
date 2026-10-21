#!/usr/bin/env python3
"""Rev E option C noise check: TAC5112/TAC5212 codec in place of AD9833 + OPA810 stage + THS4551 + ADS9224R.

Reuses the Rev D virtual instrument (../virtual-instrument, transfer 'riso22'; the codec chain uses
'riso22_lo100', which adds the Rev E 100 pF from DUT_LO to ground) and its fitted-phasor
noise method (noise_budget.phasor_noise): E|dP|^2 = 2 S1(f0) / T, dZ/Z = dA/A - dB/B per alias.
Changes for the codec chain:
  - the source chain (AD9833, RC reconstruction, coupling, OPA810 x6) is replaced by the codec DAC
    driving the U6A source-buffer input at the Rev D amplitude.  DAC noise = full scale / 10^(DR/20)
    over 20 kHz (datasheet), times WIDEBAND_DAC (ASSUMED x2: no DAC noise figure above 20 kHz is
    published), plus a gain/level stage with OPA810-class noise at noise gain 2 (ASSUMED);
  - the FDA groups are removed: the codec's AC-coupled differential inputs take channel A
    (HIGH - LOW) and channel B (TIA - LOW), each through a 1k/1k divider (K = 0.5) so the
    unbalanced drive keeps the per-channel common-mode swing under the 1 Vpp of CM_TOL = 01
    (TAC5112 Table 7-10). CM_TOL = 01 costs "a few dB" of noise: CM_TOL_DB = 3 (ASSUMED);
  - the source is limited to SOURCE_PK = 1.7 V peak at SOURCE_BUF (Rev D: about 1.8 V);
  - firmware channel gain: 12 dB when the channel's peak at the pin stays under 0.8 of full
    scale, else 0 dB. 12 dB costs 2 dB of SNR (TAC5112 6.x, 104 -> 102 dB A-weighted), so the
    input-referred noise falls 10 dB;
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

CONFIG = "riso22"         # Rev D SAR chain
CODEC_CONFIG = "riso22_lo100"  # Rev E: fixed 100 pF DUT_LO to ground (TIA stability with the relays)
WIDEBAND_DAC = 2.0
K_A = K_B = 0.5
CM_TOL_DB = 3.0
SOURCE_PK = 1.7
FS_PK = 2.0 * math.sqrt(2)  # 2 Vrms differential input full scale
F_MOD = 6.144e6
F_AA = 500e3
DAC_FS_RMS = 2.0          # differential line-out full scale (TAC5x12 p1)
CODECS = {"TAC5112": dict(adc_snr_db=91.0, dac_dr_db=114.0), "TAC5212": dict(adc_snr_db=89.0, dac_dr_db=120.0)}
AFE = ["en_x6a", "en_x6b", "en_x7b", "en_x7a", "in_x7a_m", "nr_RG", "nr_RF", "nr_Risolo", "dut"]


def codec_phasor_noise(dut, hz, codec, T, o=vm.NoiseOpts()):
    c = CODECS[codec]
    tr = vm.transfer(CODEC_CONFIG)
    f0 = vm.frequency_hz(vm.frequency_word(hz))
    z0 = dut.z(f0)
    # Source amplitude at the U6A input equal to Rev D's: DDS amplitude times the DDS -> U6A-input gain.
    Hd_a, _ = tr.H([f0], [z0], names=["dds"])
    Hx_a, Hx_b = tr.H([f0], [z0], names=["en_x6a"])
    amp = o.dds_amp_v * abs(Hd_a[0, 0] / Hx_a[0, 0])
    amp *= SOURCE_PK / 1.8
    A0, B0 = K_A * amp * Hx_a[0, 0], K_B * amp * Hx_b[0, 0]
    # Open-circuit peaks at the pins set the clipping limit; the firmware gain uses the actual peak.
    gain = {ch: (4.0 if 4.0 * abs(v) <= 0.8 * FS_PK else 1.0) for ch, v in (("A", A0), ("B", B0))}
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
            g = K_A * np.conj(HA[:, 0]) / A0 - K_B * np.conj(HB[:, 0]) / B0
        else:
            g = K_A * HA[:, 0] / A0 - K_B * HB[:, 0] / B0
        for n, v in zip(AFE, (2 / T) * S[:, 0] * np.abs(g) ** 2 * aa):
            key = "source (DAC + level stage + U6A)" if n == "en_x6a" else n
            var[key] = var.get(key, 0.0) + float(v)
    adc_rms = 2.0 / 10 ** ((c["adc_snr_db"] - CM_TOL_DB) / 20)
    s_in = {ch: (adc_rms * (10 ** (2 / 20) if g > 1 else 1.0) / g) ** 2 / 85e3 for ch, g in gain.items()}
    var["codec ADC"] = (2 / T) * (s_in["A"] / abs(A0) ** 2 + s_in["B"] / abs(B0) ** 2)
    tot = sum(var.values())
    sig = abs(z0) * math.sqrt(tot / 2)
    return dict(dut=dut.name, hz=hz, z_true=[float(z0.real), float(z0.imag)], sigma_rel_z=math.sqrt(tot),
                sigma_x_ohm=sig, sigma_r_ohm=sig, a_peak_v=abs(A0), b_peak_v=abs(B0),
                a_fs=abs(A0) * gain["A"] / FS_PK, b_fs=abs(B0) * gain["B"] / FS_PK,
                gain_db={k: round(20 * math.log10(v)) for k, v in gain.items()},
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
    out = dict(assumptions=dict(wideband_dac=WIDEBAND_DAC, k_a=K_A, k_b=K_B, cm_tol_db=CM_TOL_DB, source_pk=SOURCE_PK,
                                f_mod_hz=F_MOD, f_aa_hz=F_AA, config=CONFIG, codec_config=CODEC_CONFIG,
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
