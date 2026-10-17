# Native-20 bench addendum: the measurements the 2026-10-05 decisions depend on

This page extends [BENCH-SWITCHING.md](BENCH-SWITCHING.md) and D-8's
double-pulse plan ([out-D8](../validation-results/01-switching-parasitics/round17/delegation/out-D8/README.md)):
the same fixture, safety preparation, instrument null check and raw-shot record
apply. D-8 was written for native-17. On native-20 its circuit mapping still
holds: leg copper is identical, and only R8/R16/R34 and R9/R17 values differ.
Each test below closes a specific open item. Run them in this order; stop at
the first failure.

| # | Test | Condition | Measure | Pass criterion | Closes |
| --- | --- | --- | --- | --- | --- |
| B0 | **Kelvin offset (DC)** | Bridge idle, bus 0 V, HOT side powered (V15_LS on, HOT5 up), worst-case load: AMC1311 and ISO7710 powered | V(R35.2) − V(R5.2) and V(U5.2) − V(R5.2) with a µV-resolution DMM, short Kelvin leads on the pads | ≤ 2.13 mV (budget, [kelvin/](../validation-results/02-protection-timing/kelvin/README.md)); if larger, recompute the band minimum: 49.73 A − 1.03 A/mV × e | Kelvin budget is a model |
| B1 | **PERMIT → gates-off timing** | Bus 0 V, drivers powered, PWM inputs held high (outputs on) | PERMIT at J4.9, Q1/Q4 gate, DIS (U1/U2 pin), OUTA/OUTB at both drivers; ≥ 500 MHz, ≤ 5 cm ground springs | PERMIT↓ → Q1 gate < 0.65 V in ≤ 181.6 ns; DIS > 2.3 V in ≤ 119.1 ns after that; PERMIT↓ → OUT < 10 % in ≤ 380 ns (allocation sum: 181.6 + 119.1 + 80) | D-31 ledger allocations (datasheet hard bound alone is 1.17 µs) |
| B2 | **S5 first-edge capture** (first power-up rule) | Current-limited DC source ≤ 50 V on J8/J10, no load current; single pulse on each device in turn, both legs | Partner VGS (isolated probe), both VDS, bus current | Partner VGS < 3.0 V. Repeat at 100 V and 170 V only after it passes. If 3.0 V is exceeded: stop bursts; native-20 stays on continuous operation; F6 is mandatory before burst firmware | FINDINGS F11; model gives 3.3–4.1 V unipolar |
| B3 | **S4 commutation** (D-8 rows S4 DIR=0/1) | As D-8; leg A, then leg B | As D-8 | As D-8 (520 V, 3.0 V) | F2 / D-24 answer (c): the physical recovery bound |
| B4 | **Shunt-OCP trip point and complete chain** | DPT inductor (100 µH) charged by one long pulse at 50 V bus until the shunt OCP trips (~73 A nominal at room temperature; ramp 0.5 A/µs) | Load current (calibrated), OCP_NODE, U6 output, BUS_FAULT (J4.10), PERMIT, DIS, driver OUT and VGS of the conducting device | Trip current inside the all-corner band 47.54–97.98 A (nominal ≈ 73 A, minus ≈ 1.03 A per mV of the B0 offset); comparator → conducting driver OUT < 10 % ≤ 573.2 ns (the D-31 ledger ends at the driver's DIS response; driver OUT → gate < 3 V is recorded separately); die VDS at turn-off ≤ 520 V | Task 02 decision B (R34 10.6 kΩ); D-31 timing |

## Notes

- **B2 is free inside B3**: the first pulse of every double-pulse shot is a
  hard turn-on into 0 A from idle, so capture the partner gate on pulse 1 of
  every B3 shot as well.
- **B4 energy:** ½ · 100 µH · (80 A)² = 0.32 J in the inductor at trip,
  inside D-8's fixture budget. The inductor must be pulse-rated ≥ 100 A (D-8
  specifies this). The interlock board must be connected for PERMIT to act;
  the controller is not needed (drive PWM from the pulse generator).
- **B4 at 50 V** keeps the turn-off overshoot small. The chain timing does not
  depend on bus voltage. Over-voltage survival at 280 V is already shown in
  the model (D-31: ≤ 350 V to 330 A).
- Record every shot per BENCH-SWITCHING.md's raw-record section, with the board
  identity (native-20 manifest SHA-256) and probe deskew.
- Leg B gets B2 and B3 too. Its power loop is larger, and its S4 VDS reached
  537 V in the model without F6.
