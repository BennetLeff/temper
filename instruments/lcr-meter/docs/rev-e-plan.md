# Rev E plan and decision log

Rev E carries out the Tier 2 items of the [Rev D audit](rev-d-audit.md). The goals, in order, are agent drivability (everything controllable over USB) and accuracy at Temper's frequencies (1–1.5 kHz and 27–60 kHz). Rev D stays the orderable baseline until Rev E has the same depth of in-box evidence.

## Sequence

Each step settles what the next one builds on. Re-laying out before the circuit is final would mean doing it twice.

| Step | Item | Depends on | Settled by |
|---|---|---|---|
| 1 | Acquisition and source architecture: keep the ADS9224R and replace the AD9833 with a coherent DAC (option S), or replace ADC, FDAs, DDS and gain stage with one codec (option C) | — | Part survey ([acquisition survey](rev-e-acquisition-survey.md)), then a virtual-instrument model of the chosen chain run through the real host |
| 2 | Firmware-selected ranges | — (independent of step 1) | Switch survey ([range switching](rev-e-range-switching.md)), then the stability matrix rerun with the switch parasitics |
| 3 | Single-cable USB power | Step 1 (whether the raw-5 V 5VA rail survives) | Power budget against the USB limit, then a power-spur rerun |
| 4 | Compact power island and smaller board | Steps 1–3 | Hand layout; layout audit, extracted-parasitic stability rerun, DRC/ERC/parity |

## Decision criteria for step 1

The virtual-instrument study sets what matters: electronic noise is 30–2000× below every target; the errors that set the verdicts are standard values, contact resistance and source harmonics aliased onto the measured tone. Every linear error, including channel crosstalk and filter delay, is removed by the per-frequency three-standard calibration. So the choice is decided by:

1. **Spurs at the measured frequency.** Source harmonics and images, and sampling aliases. A codec's decimation filter removes aliasing; a coherent DAC removes the DDS truncation spurs.
2. **Frequency coverage.** 60 kHz is required for Temper; 100 kHz is kept unless the cost is large.
3. **Stability between calibration and measurement** (gain and phase drift with temperature).
4. **Agent value.** Multi-tone excitation measures several frequencies in one capture; DC coupling removes the settle wait.
5. **Evidence to redo, and cost.** Option C replaces most of the qualified acquisition chain.

## Decisions

| Date | Decision | Basis |
|---|---|---|
| 2026-10-20 | Tier 1 audit fixes are applied to Rev D; Rev D stays the baseline | [rev-d-audit.md](rev-d-audit.md), **Applied** |
| 2026-10-20 | Step order 1 → 2 → 3 → 4 as above; steps 1 and 2 run in parallel | Dependencies in the table above |
| 2026-10-20 | **Step 1: option C, a TAC5112 codec (pin- and register-compatible with the TAC5212), at 187.5 kHz (12 MHz BCLK = 120 MHz/10)** | [Survey](rev-e-acquisition-survey.md): both options cap near 85 kHz (the PCM5102A passband at 187.5 kHz is 84.4 kHz), so coverage does not separate them. Option C's digital anti-alias filter removes the aliased-harmonic term that set the 21 mΩ coil-R bound. ADC and DAC share one frame clock. Its noise costs 1.5–2.6× at equal capture time, worst 5.5 % of a tolerance ([noise check](../validation/rev-e-codec/README.md)). It removes the ADS9224R, two THS4551s, the AD9833 and the OPA810 stage. TAC5112 rather than TAC5212 for stock (181 vs 1 at JLC). Lost: 85–100 kHz. |
| 2026-10-20 | Codec harmonic distortion is not a gate | Harmonics of the test tone sit at 2f, 3f… and the fit at f rejects them; the digital filter stops them aliasing back. Only gain compression could matter, and THD+N −97 dB bounds it far below calibration error. |
| 2026-10-20 | **Step 2: three Panasonic TQ2SA-L2-5V-Z dual-coil latching DPDT relays (C2684450), one per range, replacing JP1–JP6 one for one** (pole 1 SOURCE_BUF → RG100/RG5K/RG100K, pole 2 TIA_OUT → RF100/RF5K/RF100K; C104 stays local and unswitched). Four GPIOs (shared RESET, three SET) on AO3400A + 1N4148WS. Firmware boots into the 100 kΩ range. Fallback: G6K-2F-Y-TR DC5 (C47190), non-latching | [Range switching](rev-e-range-switching.md): open-contact capacitance ≤ 0.28 pF (conservative reading of the isolation curve; 0.14 pF on a series-C basis). Worst leakage into the 100 kΩ range is 0.55 % of feedback admittance at 100 kHz, acting as extra C104, which calibration removes. Contact-resistance spread is ≤ 164 ppm gain on the 100 Ω range. Analog switches fail on Ron (1.7–4.8 % of 100 Ω) or on 77–187 pF hanging on TIA_OUT. A latching relay draws no coil current near the TIA. |
| 2026-10-20 | One stability campaign covers relays and the codec input load together | Both load TIA_OUT. The relay case list (range-switching §6) is run with the codec channel-B input network in place of the THS4551, so the front end is drawn first |

