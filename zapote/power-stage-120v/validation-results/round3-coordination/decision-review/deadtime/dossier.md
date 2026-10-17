# Decision C: UCC21550 dead time

## Recommendation

Evaluate a nominal 450 ns setting in the qualified switching and loss models, but hold any R9/R17 source or board change. The round-3 reference-inductance result gives a strong reason to test it; it does not establish timing and heat margins on native-15. The B1 heuristic-inductance case also has false turn-on after the partner turns on. A longer command gap cannot be credited as a cure for that mechanism without a qualified model and bench waveforms.

## Saved numerical evidence

- A1 completed 540 nominal grid cases plus bisections, at 27 C and reference board/ESL inductances with x0.5/x1/x3 sensitivity. The diagnostic requires incoming die |VDS| <= 0.05 VBUS throughout 20 ns before the incoming 7.5 V command crossing. The midpoints are model estimates, not guaranteed current limits.
- Nominal-L minimum switching current for that diagnostic, either direction: 348 ns = 21.99 A at 120 V, 21.46 A at 170 V, 20.93 A at 198 V. At 450 ns: 120 V = 11.09 A; 170 V = 11.09 A for DIR0 and 10.78 A for DIR1; 198 V = 10.78 A for either direction. Across all x0.5/x1/x3 thresholds, the 348 ns envelope is 20.66–21.99 A, and the 450 ns envelope is 10.78–11.09 A.
- The A1 inductance-independent edge criterion fails (maximum 10–90% edge-time shift 68.92% under x0.5/x3); board-specific ZVS/edge use is blocked. Its 450 ns, 170 V DIR1 threshold had a numerical boundary flip and was refined at 0.1 ns max step to 10.78125 ±0.15625 A.
- In the *old unrestricted full-power A5 event table*, 45,360 of 91,905 events have VBUS <120 V, below A1's domain. Of the remaining 46,545 event magnitudes, 7,898 (16.97%) are below 21 A and only 4 are below 11 A. This arithmetic illustrates why a longer dead time might matter but is **not a ZVS map**: the board-L condition failed, much of the line is outside domain, and a new 42 A peak limit changes the operating trajectories.
- A1 `turnoff_energy.csv` nominal-L, 170 V, 37 A: DIR0 model dissipative outgoing energy is 26.920 µJ at 348 ns versus 26.920 µJ at 450 ns; DIR1 is 19.439 versus 19.441 µJ. Across nominal L and 120/170/198 V, both directions, 10/15/20/37 A, the largest saved difference was 0.006 µJ. This is *not* a total loss comparison: integration ends at incoming command, counts outgoing device channel/epi/diode, and does not include extra incoming-body-diode dwell, recovery, hot properties or lost-ZVS turn-on.

## Manufacturer timing and diode limits

- Board/source R9 and R17 are 39 kΩ to UCC21550 DT. TI UCC21550 Rev C pp. 10, 25 gives `tDT(ns) ≈ 8.6 × RDT(kΩ) + 13`, so 39 kΩ -> 348.4 ns nominal; a **51 kΩ candidate** -> 451.6 ns nominal. That would be a test candidate, not an approved BOM change. A 1% 51 kΩ resistor changes the equation by ±4.39 ns before IC variation.
- TI publishes at RDT=50 kΩ a **399/443/487 ns min/typ/max** output dead time. A 450 ns *nominal* resistor does not guarantee 450 ns physically. The published table gives no explicit 51 kΩ min/max; interpolation or rescaling must be marked estimate, not guarantee. The component specification is driver-output 90%-fall to 10%-rise, over its specified table conditions; it is not the MOSFET die-current-off to next die-current-on interval. The driver chooses the longer of controller input dead time and programmed dead time. Check controller timing ownership before changing R9/R17.
- TI §8.2.2.8 explicitly requires in-system worst-case real VGS fall, rise and turn-on delay when selecting DT; the IC cannot fine-tune DT with operating conditions. A1 uses a 5 ns command ramp and 5/0.55 Ω approximate pull-up/down, not a timed UCC21550 model. Infineon CFD7 Rev 2 Table 5 gives typical `td(off)=198 ns` at 400 V, 58.2 A, 13 V, RG=1.8 Ω; not a worst-case bound for this board's 3.9 Ω and 15 V.
- Infineon CFD7 Table 7 at 25 C, 400 V, 58.2 A, 100 A/µs: VSD typical 1.0 V, Qrr typical/max 2.30/4.60 µC, trr typical/max 236/354 ns. These conditions differ from the 120–198 V model and controlled 42 A peak. Extra diode dwell and recovery must be measured/simulated on the board.
- A simple sensitivity illustration, **not a thermal upper bound**: at 60 kHz, 4 bridge commutations/cycle, a full 102 ns added diode interval at 42 A and typical 1 V would contribute ~1.03 W total (`4×60k×102ns×42A×1V`). Actual interval, diode voltage, recovery and current differ. At 60 kHz, two 450 ns intervals occupy 5.4% of each leg's period, versus 4.18% for 348 ns; the additional 1.22% can also change fundamental bridge voltage and tank-power control.

## Required next evidence before value selection

1. Establish a qualified board switching model: field-solved board/gate/common-source inductance, capacitor ESL, real UCC21550 output timing min/max and tolerance at cold/hot, and the controller's own PWM dead time. Cover 108 V rectified low-bus operation as well as 120/170/198 V, both directions, full current-limited waveform and low-load commutations.
2. For candidate 39 and 51 kΩ plus timing/process/resistor corners, plot real VGS (at die/source), incoming VDS, source/drain current, body-diode current/dwell, reverse-recovery and shoot-through; determine minimum ZVS current and how much of the controlled operating map is actually ZVS. Resolve B1 false turn-on separately.
3. Recompute device heat including conduction, outgoing turn-off, incoming turn-on when hard, diode forward and recovery, snubber and gate supply at hot Tj, using measured switching instant currents. Propagate into A6/B3 sink and board thermal screens. Bench measure actual OUT, VGS, VDS and switch node across both legs at low bus, cold/hot and staged load before locking R9/R17.

## Sources

- Local A1: `zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/a1-zvs/README.md`, `zvs_threshold.json`, `turnoff_energy.csv`, `complementary_leg.cir`.
- Local A5: `zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/round3/outputs/switching-events.csv`, `b4-status.md`.
- Local A6: `zapote/power-stage-120v/validation-results/03-loss-thermal-budget/round3/README.md`.
- Local B1: `zapote/power-stage-120v/validation-results/01-switching-parasitics/round3/b1-board-grid/README.md`.
- Board intent: `zapote/power-stage-120v/elec/src/power_stage_120v.ato` and `validation-plan/01-switching-parasitics.md`.
- [TI UCC21550 Rev C](https://www.ti.com/lit/ds/symlink/ucc21550.pdf) §§5.8, 7.4.2, 8.2.2.8, pp. 10, 25, 33.
- [Infineon IPW65R018CFD7 Rev 2.0](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf) Tables 5, 7, pp. 5–6.
