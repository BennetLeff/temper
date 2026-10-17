# Board-split options vs the stage-20 single board (2026-10-13)

**Provenance.** The analysis was done by the r3-split agent, whose tool refused to write this file, so the lead saved it from the agent's report.
- Every number comes from `scripts/` and is regenerated into `results/` (rerun with `python3 -I scripts/<name>.py`). The detailed tables are in [`results/summary.md`](results/summary.md).
- Board fabrication cost is a labelled model range, not a quote: JLC publishes no price for this spec.
- The F6 gate decks were rerun read-only with ngspice from the repo's committed native-21 s9b2 decks.

## Options

| Option | What moves | New board |
|---|---|---|
| **S1: inlet module** | J1, F1, RV1, C1/C2, R1/R2, L1 and C3/C4 (10 parts) join the off-board D-22 inlet module. BR1 and J6 stay. A harness carries L_FILT, N_FILT and PE | 2-layer, 2 oz, about 18,200 mm² |
| S2-A: high / low power, drivers on the power board | G08 sense, G09 CT/ZC, G10 J4 (59 parts) | 4-layer, 1 oz, about 52 × 52 mm |
| S2-B: high / low power, drivers on the drive board | G05–G10 less PS2 (272 parts) | 4-layer, 1 oz, about 103 × 103 mm |
| S2-L: SELV-only interface board (variant the FMEA found) | G09 SELV side and J4 (22 parts) | 4-layer, 38 × 38 mm |

## Summary (USD per board, against the single board)

| | S1 | S2-A | S2-B | S2-L |
|---|---|---|---|---|
| Fabrication delta at 500 (model, UNVERIFIED) | +0.89 to +1.07 (−0.33 to +0.07 if the freed area is reclaimed) | +0.19 to +0.31 | +0.75 to +1.01 | +0.10 to +0.20 |
| Parts added, at 500 | +5.51 (4.80 of it allowances: harness, lug, fixings) | +1.67 | +2.60 | +1.38 |
| JLC assembly, at 500 / at 5 | −0.26 / −1.78 | +0.45 / +14.88 | +0.43 / +13.05 | +0.44 / +13.36 |
| Labour added (assumed at $45/h) | +6.00 | +3.00 | +3.75 | +2.25 |
| **Total excluding fabrication, at 500 / at 5** | **+11.25 / +10.12** | **+5.12 / +19.75** | **+6.78 / +19.82** | +4.07 / +17.06 |
| Against the existing plan (board plus a separate D-22 module, $15 carrier allowance) | **−8.4 to −8.6 at 500** | n/a | n/a | n/a |
| S4 worst die VDS (limit 520 V) / off-gate (limit 1.9 V) | unchanged | unchanged | leg B 490.2 → 457–480 V; 1.145 → 0.6–0.9 V (gate decks, +3 to +15 nH connector) | unchanged |
| OCP Kelvin floor margin (3.55 A) | unchanged | contact resistance −0.07 to −0.55 A, plus pickup up to −1.7 to −3.4 A | same as S2-A | unchanged |
| EMI (10.5 dB), leakage, fusing ratio | unchanged (EMI 10.479 dB for Y-path L 15–125 nH) | unchanged | unchanged | unchanged |
| Board heat moved | −1.23 W (L1; 2.0–2.7 W real) | −0.23 W | −4.03 W onto a second thermal zone | −0.13 W |
| New safety items | second line-voltage PCB with PE; harness; 24 A terminal | **an open KELVIN_N pin blinds the OCP** (fail-unsafe); HOT sense connector; barrier on two boards | all of S2-A, plus 400 V nodes on a 2.54 mm header, high-side islands on board 2, an open CT secondary, an open `off_h` losing the F6 turn-off path | SELV only |
| **Verdict** | **conditional GO, replacing the separate D-22 module** | NO-GO | NO-GO | NO-GO (no benefit) |

## Findings

- **The gate loop is not what rules out S2.** In the repo's own F6 decks, +10 / +20 nH across the full 252-case set per leg gives no failure. Worst die VDS is 471.6 V and worst off-gate 0.570 V (`results/gate_full.json`).
- **What rules S2 out:**
  - **Fail-unsafe OCP on an open Kelvin contact.** OCP_NODE floats to the 2.5 V reference against a 1.2037 V threshold.
  - **The pickup and contact-resistance budget.**
  - **The 8 mm barrier spread across two boards and a connector,** which the 2D D5 gate cannot check.
  - **A second PCBA order,** about $13–15 per board at 5 and $0.44 at 500 in fees, plus labour.
- **The connectors are cheap** ($1.4–3 per board). Fabrication deltas are within about ±$1 at 500. Neither drives the result.
- **S1's value is iteration and system cost, not board cost.** The open G01 items become changes to a small 2-layer board instead of the 290 × 190 mm 4-layer POFV board:
  - F10 (the module DM inductor has no MPN);
  - F5's Y rework;
  - g01 P1's SC-20-201 swap;
  - the zero-stock L1.

  Against the plan that already needs a separate D-22 module, S1 saves about $8.5 per board at 500.
- **Scoring trap for S1.** The single-board scorecard would show a spurious −$41.82 at 500 and −5 hand lines, because those parts move to a new BOM. Score S1 on system cost: board plus module plus harness.

## Conditions for S1

- **Certifier:** accepts a second line-voltage PCB and a 15 A harness.
- **Laminate:** the JLC CTI question (DECISIONS 22) applies to both boards.
- **Enclosure (temper-f7):** confirm the cord-entry side (D-22 says left; the enclosure plan has a right-wall inlet), a module space of about 135 × 135 × 50 mm, and the harness route.
- **Harness landing:** the real copper gain comes from landing the harness near BR1 (x 81.7), which removes about 200 mm of 2 oz AC feed copper. That needs a re-layout.

## Not verified

- **Pricing:** the JLC bare-board price for this spec (the only sourced figure is $70.6/m² for 4 layers, 2024); harness, lug and stand-off prices (allowances); connector contact resistance and voltage ratings for the generic headers.
- **Models:** the gate-loop result rests on provisional FEM matrices and a DC-resistance driver model, with no connector-to-power-loop coupling. OCP pickup at a real connector position needs the F8 FEM. The S1 EMI model has no harness element.
- **Gates not run:** the post-split outline, fit, D5, barrier and B3 gates need the chain.
