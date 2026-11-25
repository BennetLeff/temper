# c57: D-22 inlet module scope, before any layout (2026-11-25)

Question: can D-22 be laid out now as the 2026-11-24 plan and the external review describe? **No: two inputs are missing (the
SCF31X DM leakage, the module envelope).** No board was drawn and nothing was bought.

| Step | Command (from `zapote/power-stage-120v`) | Result |
|---|---|---|
| EMI grid | `python3 -I scripts/run_grid.py RUNDIR` (16 runs, ~17 min) | `results/emi-grid.json`; control: c53 s3's 88 uH row reproduced to 1e-9 dB |
| toroid | `python3 -I scripts/toroid.py --check` | `results/toroid.json` |
| packing | `python3 scripts/packing.py` (ortools) | `results/packing.json` |

## EMI: worst-sensitivity margin, dB (rule: nominal and every sensitivity >= 6)
Prototype L1 (B82726S2243A020). Columns: SCF31X DM leakage as % of 5.68 mH (loop total; the model of record assumes 1 %).

| DM per line | 0.3 % | 0.5 % | 1 % | 2 % |
|---:|---:|---:|---:|---:|
| 49.7 uH | | | 2.62 | 5.34 |
| 77 uH | | | 5.25 (c53 s3) | **6.93** |
| 88 uH | 4.48 | 4.98 | **6.12** | **6.94** |
| 100 uH | 5.51 | | **6.95** | **6.94** |
| 110 uH | **6.28** | | 6.96 (c53 s3) | |

Production L1 (B82726S2203A020): 41 uH passes at 0.3 % (6.87) and 1 % (8.19); 49.7 uH passes at 0.3 % (8.20).

- The unmeasured leakage moves the result more than the choice between 88 and 100 uH. At 0.3 % even 100 uH misses; at 2 % 77 uH passes.
- With the production L1 the DECISIONS 32 part (WE-HCFT 74437636355602, 49.7 uH at 21 A) passes whatever the leakage in this range.
- KEMET LF0101 (4/22/2025) and the part's spec sheet (generated 11/25/2026) print no leakage and one common-mode curve: it must be measured.

## Toroid (external review's proposal): rejected
Magnetics 0077439A7, 100 uH at 21 A: 42 turns (45 at AL -8 %), past the guaranteed 50 % point (87 Oe). 3.2-3.5 W each at 15 A hot in
10 AWG (52-55 % winding factor), 4.7-5.1 W in 12 AWG, against 1.8 W. Copper only. Wound OD 52.4 mm at 40 %: does not stand in 50 mm.
0077083A7 stands (44.3 mm) but needs 98 turns, and no tried wire meets 1.8 W.

## Packing (bodies only; a necessary check, terminal sizes assumed)
Largest gap between all bodies, whole millimetres:

| Parts | 110 x 80 | 120 x 80 | 130 x 85 |
|---|---:|---:|---:|
| 2 x WE-HCFT 3635 + SCF31X-**JH** (flat, 45 x 42) | 0 | 1 | 3 |
| 2 x WE-HCFT 3635 + SCF31X-**JV** (vertical, 45 x 31 x 42 tall) | 1 | 2 | 4 |
| 2 x Codaca CPER3231-101MC + SCF31X-JV | 2 | 3 | 5 |
| 2 x 0077439A7 on edge + SCF31X-JV | 1 | 2 | 4 |

- **SCF31X-220-2R1A011JV** has the same table row as the JH (5.68 mH, 22 A, 4.39 mohm, 45 K, 500 VAC). Stock not read.
- Codaca CPER3231-101MC (rev 04/22/2026): Isat 23 A typ, 11 mohm max, "not authorized for use in any application related to safety". Not proposed.

## Recommendation
1. Measure DM leakage on 2 SCF31X samples (JV if stocked), at low level and under DC bias, before choosing the DM part.
2. Reserve **130 x 85 mm** in R45 (height 50 mm kept). Not checked against the R45 neighbours; R43's stand is X -150..-40, Y 296..376.
3. Leakage >= 1 %: WE-HCFT 74437636351012 passes at its typical 88 uH, by 0.12 dB at exactly 1 %. Below that: wait for the production
   L1, or run the recorded prototype EMI deviation.

## Measuring the leakage (2026-11-25, after the third external review)
Short one winding and measure the other: with k near 1 that reads L(1 - k^2), about 2 L (1 - k), which is the loop total the model
calls LDMADD (series-opposing reads 2 L (1 - k) directly). The resonance method works without an LCR meter: in parallel with 1 uF film
the expected frequencies are 38.6 kHz (0.3 %, 17.0 uH), 29.9 (0.5 %, 28.4), 21.1 (1 %, 56.8), 14.9 (2 %, 113.6).
- L takes the capacitor's error one for one, so 2-3 % needs a capacitor measured to that, not a 5 % or 10 % part. 10 % would still
  separate 0.5 % from 1 %; it would not settle 88 uH at exactly 1 % (0.12 dB of margin).
- It is a small-signal value. The 21 A check stays separate.

**JV height:** 42 mm tall against 33 for JH. The review's 1-3 mm of top clearance assumes the 50 mm includes the PCB and its standoffs; no
record in this repo says whether it does (c23 MODULE-REQUEST has no envelope). R45 must state it before JV is chosen over JH.
