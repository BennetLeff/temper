# EMI closure for the engineering prototype cohort

The earlier D19 “15 aborted, one unsettled” result is superseded by published D22 commit **7d1c97b92c0ed42be1c28a32d4ccaadd512d2238** on `codex/ps-r17-d22`, based on power-stage commit **fda5ab9ece24ef1ee6f2317604c5ca73367d5201**. All **16 declared diagnostic source cases** now pass numerical qualification. The proposed inlet stage has a minimum **9.280 dB CW-equivalent AV margin**, or **8.280 dB after the explicit 1 dB planning reserve**, within that model. This closes the numerical investigation; it does not release the installed filter or authorize powered testing.

[Published D22 evidence and runners](https://github.com/BennetLeff/temper/tree/7d1c97b92c0ed42be1c28a32d4ccaadd512d2238/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D22) remain authoritative. This intake reuses that work, with additional independent replay and selected fresh simulations. No source physics, PCB, firmware, operating current, exterior or market target was changed.

## Evidence reproduced on 2026-10-04

The [reproduction runner](../../../../../../zapote/power-stage-120v/prototype-closure/emi/verify-intake.sh) verifies the pinned checkout before using its original numerical implementation. See [verification receipt](verification.json).

| Check | Result |
| --- | --- |
| Recorded provenance | 24 input and 1,420 output SHA256 identities match |
| Intake hash gate | Eight copied JSON files and the source provenance manifest are pinned before loading analysis code; changed-copy/wrong-pin checks fail before simulation; seeded PASS receipts become INCOMPLETE on copied-input, PYTHONOPTIMIZE=1 and wrong-HEAD failures; forbidden source-checkout output is rejected without writes ([negative check](negative-check.json)) |
| Existing numerical regression suite | 10 tests pass, including truncation, source physics, coherent phases, PE reference and archive coverage |
| Raw nonlinear capture replay | 32 complete recorded captures: all 16 final cases and refinement references; FFT and prior-cycle FFT agree at rtol 1e-11 / atol 1e-12 |
| Fresh ngspice AC analysis | 12 decks: nominal and old-low-leakage scenarios, 35/60 kHz, A/B/DM ports; all saved vectors agree at rtol 1e-9 / atol 1e-12 |
| Archived exploratory/receiver spectra | Member coverage and hashes verified by upstream archive validator |

No nonlinear transient was newly simulated in this intake. The recorded waveforms were reanalyzed; the 12 AC simulations were newly run. Full raw evidence stays in the pinned published branch; compact input hashes and results are in [intake-manifest.json](../../../../../../zapote/power-stage-120v/prototype-closure/emi/intake-manifest.json). The source checkout remained clean.

The source uses a fixed 443 ns dead time; the full implemented timing tolerance is not swept here. The envelope is 170/198 V bus × 35/60 kHz × fixed RLC diagnostic R=2/100 Ω × ESL=1.06/10 nH. Finer timesteps (0.05–0.125 ns for selected final runs), rather than changing physics, resolve the old aborts and high-frequency movement. The upstream tests check cycle and timestep agreement separately. Both legs reuse leg A's matrix; this is not independent leg B/cross-leg validation, a real pan envelope, or qualification of 100/120 Hz mains modulation and burst control.

## Proposed hardware reservation

Reserve **110 × 80 × 50 mm (0.44 L)** and **8 W planning heat** for the filter itself. Upstream fuse, disconnect, cord restraint, covered terminals and their losses are additional; see [inlet integration](inlet-integration.md). Placement must separate filtered and unfiltered wiring and give each Y branch a short PE return.

| Part / quantity | Selected identity | Electrical basis and body dimensions |
| --- | --- | --- |
| Coupled choke / 1 | TDK B82726S2203A020 | 250 VAC, 20 A at 60°C/50 Hz; 1.6 mH per winding; typical leakage 18 µH; 45×25.5×41 mm |
| Input X / 1 | TDK B32923C3225K000 | 2.2 µF ±10%, X2 305 VAC; 26.5×14.5×29.5 mm; pitch 22.5 mm |
| Output and damping X / 2 | TDK B32924D3475K000 | Each 4.7 µF ±10%, X2 305 VAC; 31.5×21×31 mm; pitch 27.5 mm |
| Y branches / 2 each | TDK B32021A3472M000 and B32021A3222M000 | 4.7 nF and 2.2 nF, each Y2 300 VAC ±20%, parallel per conductor to PE; respectively 13×5×11 and 13×4×9 mm, pitch 10 mm |
| Damping / 1 | Vishay AC05000003908JAC00 | 3.9 Ω ±5%, 5 W at 40°C, body 18×Ø7.5 mm; series with one 4.7 µF X capacitor |
| Bleed / 2 | Vishay PR02000201502JA100 | 15 kΩ ±5%, 2 W at 70°C, 500 V AC/DC each; series across filtered L–N |

Ratings: [TDK choke pp. 2–5](https://product.tdk.com/system/files/dam/doc/product/emc/emc/line-filter/data_sheet/30/db/ind_2008/b82726s22x3.pdf), [TDK X parts pp. 3, 7–8, 11–13](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/emi/data_sheet/20/20/db/fc_2009/x2_b32921_928.pdf), [TDK Y parts pp. 2–5](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/emi/data_sheet/20/20/db/fc_2009/y2_b32021_026.pdf), [Vishay AC05](https://www.vishay.com/doc?28730=), [Vishay PR02 pp. 1–3](https://www.vishay.com/docs/28729/pr010203.pdf). These are body/pitch reservations, not finished manufacturing footprints. The ordinary AC05 is not the distinct AC-CS safety-fuse resistor.

At 15 A RMS, calculated choke copper loss is 2.025 W using typical cold DCR, or 2.7 W using an **assumed**, unguaranteed 6 mΩ/winding hot value. Local choke ambient must remain ≤60°C for this allocation. The hot, pulsed-input leakage and core-loss characteristics still need supplier data and measurement. The sensitivity sweep down to 9 µH is not a guaranteed saturation bound.

At 140 V/60 Hz, calculated additional line-frequency losses are 0.305 W in the damper and ≤0.688 W in the bleed pair. Each 4.7 µF branch carries approximately 0.273 A before adding switching harmonics. The Y additions alone allocate **0.437 mA** for one energized conductor at +20% capacitance; whole-appliance leakage, other supplies, existing Y parts and fault cases remain open. The healthy bleed calculation predicts 198 V→34 V in 0.901 s; ≤34 V at 1 s is a proposed engineering criterion, not a compliance verdict. It assumes all X branches remain connected and no backfeed; it gives no rectifier-isolated DC-link discharge credit.

Across the 416 harmonic-loss rows belonging to the 16 final qualified sources, the recorded maxima are 0.289 W damper HF loss, 0.00182 W added-choke HF copper loss, 2.101 A RMS HF current in the output X capacitor and 0.398 A RMS HF current in the input X capacitor. These maxima can occur in different sensitivity cases. The output capacitor therefore needs a roughly 2.12 A combined RMS screening check after quadrature addition of the 0.273 A line component, with the actual frequency distribution retained. Core and frequency-dependent winding/dielectric losses are not established by the constant-resistance model. [Pinned harmonic-loss evidence](https://github.com/BennetLeff/temper/blob/7d1c97b92c0ed42be1c28a32d4ccaadd512d2238/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D22/harmonic-loss-results.json).

Passive damping reduces the modeled DC-port impedance peak from 254.1 Ω to 29.65 Ω nominally. That is useful characterization, but not closed-loop stability: the AC fixture holds one rectifier pair conducting, uses typical RF/parasitic fits, and does not feed the changed filter impedance back into the nonlinear switching model. The 1 dB reserve is an allocation, not a statistical uncertainty bound. The original filter's worst modeled AV shortfall becomes 25.53 dB at 210 kHz over the expanded qualified source set.

## Installed geometry and remaining release gates

The original D22 module and harness reservations do not intersect either 20 mm-padded bridge-leg region in board coordinates. That supports retaining the local copper model **only under its original boundary assumptions**. It does not establish unchanged coupling after moving the board under the coil or adding a contact-bearing sink.

The concurrent cooling proposal places the board at R4 origin (-110.5,162), top z=32 mm; sink x[-112,88], y[94.515,162.515], z[12,72]; and filter reservation x[-140,-30], y[335,415], z[12,62]. These are a new installed arrangement, not D22's original coordinate frame. Require the actual device isolation material, thickness/compression, contact area, mounting hardware and electrical sink bond to derive switching-node-to-sink/chassis capacitance. Include coil-to-board/sink, wiring and PE impedances. Either bound these in a refreshed coupled model or rerun affected extraction; local copper identity alone is insufficient. A finished exhaust duct and ≤60°C filter ambient have not been demonstrated.

Before releasing the prototype filter for powered assembly:

1. Complete the fused inlet construction and coordination in [inlet-integration.md](inlet-integration.md). Freeze actual carrier footprints, terminal/insulation rules, routing, barriers, PE bond and final enclosure transform; inspect assembly access and wet/grease exposure.
2. Obtain hot biased choke leakage/CM impedance and loss information for the actual pulsed input. Verify X-capacitor frequency/current curves and case temperatures; qualify resistor repetitive reclose/surge pulses and open/short cases. Test the damper and bleed faults explicitly.
3. Bound filter interaction with the actual rectifier, source impedance, inrush, mains cycle and deployed controller modes. Use two-way nonlinear simulation and incremental input/output impedance evidence; require no growing oscillation or component overstress across the released operating envelope.
4. On guarded engineering prototypes, correlate source spectra and both LISN receiver ports with the installed assembly, hot/cold pans and permitted load/control transitions. Include actual sink isolation and earthing, CM/DM separation, mains voltage range, leakage and discharge. Measure real QP/AV with the applicable detector/bandwidth; the reported 150 kHz–30 MHz CW-equivalent line estimates are not detector compliance measurements. Retain ≥6 dB as the engineering margin objective, subject to the lab's applicable limits and uncertainty.

No assembled hardware exists. These physical gates remain open; no safe-operation, emissions or manufacturing release is claimed.
