# Bench conducted-EMI pre-compliance (stage 19b): procedure

Companion to `README.md` (model, predicted lines in `results.json: bench_predictions_nominal`). Pre-compliance only: it does not replace a lab test. It is written to slot into `firmware/components/power/COMMISSIONING.md` after the tank-ceiling gates (22 A first; 22 → 24 → 26 → 28 A only through that file's raising gates). Nothing here is to be run on a unit that has not passed the existing bring-up steps and the inlet module's own safety checks.

**Limits compared against** (repo transcription of 47 CFR 18.307(a), induction cooking; confirm Canadian/Mexican requirements with the lab, README section 2): 9-50 kHz 110 dBµV QP; 50-150 kHz 90→80 dBµV QP (log); 150-500 kHz 66→56 QP / 56→46 AV; 0.5-5 MHz 56 / 46; 5-30 MHz 60 / 50 dBµV; ISM bands 6.78 / 13.56 / 27.12 MHz excluded.

**Bench pass line:** every measured line ≤ limit − 6 dB (QP and AV) in every configuration below. A line between limit − 6 dB and the limit is a "hold": fix before the lab. Model-vs-bench: any line more than 6 dB above `bench_predictions_nominal` means a model input is wrong (update `emi_s19b.py` inputs, section B1) before any hardware change.

## Equipment

| Item | Requirement |
|---|---|
| LISN | two-line V-network, 50 µH ∥ 50 Ω (CISPR 16-1-2); for 9-150 kHz the 50 µH + 5 Ω ∥ 50 Ω network, current rating ≥ 20 A (28 A tests: ≥ 30 A or a de-rated 20 A part with the ceiling held at 22 A), PE terminal bonded to the reference ground plane. Verify the LISN impedance/transfer with the tracking generator before use |
| Receiver | EMI test receiver (CISPR 16-1-1) with QP, AV and peak detectors, or a spectrum analyser with those detectors and a 9 kHz-30 MHz preselector/limiter; 10 dB pad + transient limiter on each line, calibrated out |
| Reference | 2 m × 2 m bonded ground plane, EUT on a non-conductive 0.8 m table, 0.4 m from a vertical plane, power cord 1 m, excess folded in a 0.3-0.4 m bundle (per the lab's CISPR 16-2-1 / ANSI C63.4 layout; use the layout the lab will use) |
| CM/DM discriminator | one of: a CM/DM separator (0°/180° hybrid) on the two LISN outputs, or L and N measured separately and combined offline as CM = (L+N)/2, DM = (L−N)/2 in complex terms, using the receiver's I/Q or vector measurement if available. The model reports CM and DM, so the split is the most useful single diagnostic |
| Variac | isolated, 120 V ±10 % (108-132 V), 127 V for Mexico; true-RMS power analyser on the mains side |
| Pan loads | the standard load the lab will use for induction cooking (ask: CISPR 14-1/ANSI C63.4 pan and water mass) plus the repo's low-R pan class and a high-R pan; **no-pan** with the firmware's 22 A clamp (COMMISSIONING step 9a.6 covers the clamp); never run the no-pan 28 A fault case |
| Meter | LCR meter ≥ 100 kHz, 10 pF-1 nF range, guarded fixture, for step B1 |
| Probes | current probe (Rogowski or clamp, ≥ 30 MHz) on the PE lead and on L and N at the inlet; HV differential probe at the tank; all via isolation |

## Receiver settings

| Band | Detector set | RBW | Scan | Notes |
|---|---|---|---|---|
| 9-150 kHz (CISPR band A) | Peak max-hold prescan, then QP on lines within 10 dB of the limit | 200 Hz | step ≤ RBW/2; dwell ≥ 1 mains cycle per step (≥ 17 ms) on max-hold, ≥ 1 s per final point | the 35-60 kHz fundamental and 2×fs..4×fs lines are here; the 9-50 kHz limit is 110 dBµV and 50-150 kHz is 90→80 dBµV (QP only; no AV limit exists below 150 kHz) |
| 150 kHz-30 MHz (band B) | Peak prescan; then QP and AV final on lines within 10 dB of the AV limit | 9 kHz | step ≤ 4.5 kHz; dwell ≥ 1 mains cycle per step for the prescan | AV is the binding limit (QP is 10 dB looser); use the receiver's CISPR AV detector, not video averaging of a spectrum |
| 30 kHz-1 MHz zoom | peak, 200 Hz RBW | 200 Hz | span 20 kHz around each line | resolves the 120 Hz line-modulation sidebands: the line carrier reads about 3.9 dB below the envelope crest. The model uses the crest, so the measured line should read ≤ the prediction |

Every line is measured on L and N and against the 6 dB pass line. Use the final QP/AV measurement only on frequencies where the peak prescan is within 10 dB of the limit.

## Configurations (record each as a CSV + screenshot with receiver settings)

Run each configuration at 120 V and 132 V (and 127 V once), each in the three loads below:

| # | Load | Current ceiling | Frequency control |
|---|---|---|---|
| C1 | pan present, power request that gives ≈ 22 A tank RMS (firmware ceiling) | 22 A default | normal loop (swept 60 → 35 kHz at 250 Hz per half cycle) |
| C2 | same | 22 A | **held** at 35, 40, 45, 50, 55, 60 kHz in turn (test override, if provided; otherwise vary the pan R and power until the loop settles at each fs and record the settled fs) |
| C3 | pan present, ceiling raised to 28 A through the COMMISSIONING raising gates only | 28 A | normal loop and held at 35-45 kHz |
| C4 | **no pan**, firmware no-pan clamp | 22 A | normal loop |
| C5 | low power (≈ 200-300 W request) and burst-mode (20 s period) | any | normal loop; check the burst envelope on the max-hold trace |
| C6 | the same as C1 with the inlet module **bypassed** (clearly labelled test only, reduced power ≤ 300 W) | ≤ 300 W | normal loop; this should show the model's large excess and calibrates it |

## Steps

**B1. Coil→PE capacitance (before powering; the dominant uncertainty).** With the coil harness disconnected from the board, measure at 100 kHz and 1 MHz: coil stud J2 to PE and J5 to PE separately (other stud floating), and J2+J5 shorted to PE, in the assembled enclosure, with and without the pan on the glass; repeat with the coil at its production gap. Record the sum and the split. Compare with the model's 50 pF (25 + 25 pF) nominal. If sum ≤ 50 pF and split ≥ 40/60, the predicted 7.8 dB nominal margin stands; if > 100 pF or one-sided, expect a 9-150 kHz CM failure and go to README recommendation 3 (shield / CM choke) before the scan. Also measure tab-to-sink capacitance of one Q3/Q6 and one Q2/Q5 position (expect 5-9 pF with the AlN tile), and BR1 case-to-sink.

**B2. Baseline.** LISN + receiver ambient with the EUT off and powered (standby), both lines. Note any line within 6 dB of the limit that is not from the cooker (PS1-PS3 only: PS1/PS2 IRM-20, PS3 IRM-60 with the blower).

**B3. PS1/PS2/PS3 alone.** Mains on, bridge disabled (no PWM): scan 150 kHz-30 MHz. The model bounds them at their own class B limit through the filter (README section 3); this checks that bound, which no repo datasheet can.

**B4. Safety interlock.** Confirm the current probes and LISN are rated for the test; keep the EUT's PE bond intact; keep the leakage budget (README: Y 9.1 nF per line, 0.48 mA/line at 140 V) in mind and do not add Y capacitance at the bench without the leakage meter.

**B5. Swept and held scans (C1, C2).** For each held fs record the fundamental (CM expected: 87 dBµV at 35 kHz down to 80 dBµV at 60 kHz in the model, limit 110 / 90 / 88), the 2fs line (DM-dominated, 75 dBµV at 35 kHz, limit 87), and 3fs, 4fs lines to 500 kHz. **fs = 50-60 kHz at the highest current is the case that matters:** limit 90 → 88 dBµV, model margin 8-11 dB. Compare L, N, CM, DM with `bench_predictions_nominal`.

**B6. 28 A (C3).** Only after COMMISSIONING's 24/26 A gates pass. Record the 150 kHz 4th-harmonic DM line (model 22.3 dB margin) and the 70 kHz 2fs line (9.8 dB at 35 kHz). Also record the bus-current waveform (current probe on a DC-link lead, 100 MHz scope) to check the 2fs..4fs lines against the model's rectified-sine source (model: 2nd harmonic within 1.4 dB of the device-level run).

**B7. No-pan (C4) and burst (C5).** Expect lower fundamental CM (71 dBµV at 60 kHz) and DM-dominated 70 kHz line (75 dBµV). Burst mode adds spectral spreading; compare QP and AV.

**B8. Module-off calibration (C6).** The model predicts a ≥ 38 dB shortfall at 70-150 kHz without the module. If the measured shortfall is more than 10 dB smaller, the source is overestimated (or the board filter is better than modelled); if larger, a source is missing.

**B9. Mitigation trials (only if a hold appears), one change at a time, re-scan 9-150 kHz:** (a) coil-side shield returned to bus_n; (b) stronger module CM choke (3.2 mH); (c) Y changes within the leakage budget; (d) do **not** add DC-bus-to-PE Y (the model's REC1 worsens the 60 kHz line). Record before/after on the same fs.

## Data to bring back

For each configuration: receiver settings file, L/N peak traces (CSV), final QP/AV table for lines within 10 dB of the limit, the held fs, tank RMS and mains power from the analyser, B1 capacitances, and photos of the layout. Update `emi_s19b.py` inputs (`coil_PE`, tab C, module DM L) with the measured values and rerun; commit the new `results.json` as `results-bench-YYYYMMDD.json`.

## What the model can and cannot tell you

It predicts the line spectrum at the crest of the line cycle with ideal CW equivalence and a lumped filter. Above ≈ 1-3 MHz it is not predictive (no harness/board parasitics, no ring, no PS emission); the bench is the only evidence there. The coil capacitance and chassis distance are assumed. Do not treat a bench pass here as certification: the lab confirms the limit set, the load, the layout and the QP/AV on the final unit.

## Added 2026-10-13: earthed-pan robustness run
The model margin with the pan earthed through a user (coil-to-PE 91–102 pF) is 1.7–2.6 dB at the 60 kHz fundamental (QP, CM). This is not a compliance configuration.

Run 28 A at fs 55–60 kHz with the pan strapped to the LISN ground by 1 m of wire, and record the 9–150 kHz margin. If it is below 0 dB, evaluate the coil-side shield or the 3.2 mH CM choke (README recommendations).
