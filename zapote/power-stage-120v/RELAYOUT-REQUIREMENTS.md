# Enclosure re-layout: power-board requirements checklist

The enclosure work will move parts of the power board. This page collects
every requirement the simulation campaign has put on that re-layout, so that
nothing decided in [DECISIONS.md](DECISIONS.md) is lost when copper moves.
Each row links to its evidence. Start from **native-20** (values current as of
2026-10-05).

## Circuit changes to implement in the re-layout

| # | Requirement | Why / evidence |
| --- | --- | --- |
| L1 | **F6 negative gate bias, independently powered:** isolated +15/−6 V modules with a negative LDO to −2 V, 1 nF Cgs, 1 Ω + **PMEG6030EP** discharge branch per gate, rail-window monitor gating DIS, PS2 replaced (D-12 [ISOLATED-BIAS.md](validation-results/01-switching-parasitics/round17/delegation/out-D12/ISOLATED-BIAS.md)) | S4 hard turn-on and the S5 burst-start edge both fail without it. With it, all 288 + 216 model cases pass at 27/100/150 °C on both legs (FINDINGS F2/F6/F11; DECISIONS 2026-10-05) |
| L2 | Keep **R34 = 10.6 kΩ RT0603BRD0710K6L** and **R8/R16 = 330 Ω** | Shunt-OCP band and gate-off delay ([native-20](native-20/README.md)) |
| L3 | Keep **R9/R17 = 49.9 kΩ ±0.1 %** (443 ns nominal dead time) | F7, native-18 |

## Layout rules

| # | Rule | Why / evidence |
| --- | --- | --- |
| L4 | **Shunt Kelvin return:** the lead from **R5.2** into the HOT island carries all HOT-side supply current (≤ 21 mA) and sets the OCP trip error (each 10 mA across 0.1 Ω lowers the trip by ≈ 1 A). Either widen/parallel it to ≤ 50 mΩ, or star-return the AMC1311, the MC78L05 and the ISO7710 to R5.2 separately from the threshold divider (R35) and the reference (U5) | [kelvin/](validation-results/02-protection-timing/kelvin/README.md): today −2.19 A of trip shift, band 47.54–97.98 A |
| L5 | **Gate loops and power loops at least as tight as native-19.** The decision margins depend on the power-to-gate mutuals (M13/M14/M23/M24) and on the power-loop self-inductance; leg B's power loop is already larger than leg A's | round-17 d2 README; leg B S4 VDS 537 V without F6 |
| L6 | Keep C38–C41 local bus capacitors at their pads (ESL 1.06 nH typical) | D-7 |
| L7 | Do not change stackup or the FET footprints without re-running the FET geometry check | `leg_region_diff.py` flags |

## Enclosure items that touch the board

| # | Requirement | Evidence |
| --- | --- | --- |
| L8 | Forced-air sink RθSA ≤ 0.15 °C/W, ≥ 20 CFM, ≤ 1.0 °C/W per FET interface; dedicated duct coil → mains; fans on their own SELV 12 V supply | DECISIONS 2026-10-03 (cooling) |
| L9 | Reserve the 20 A DM + CM inlet filter module (110 × 80 × 50 mm, 8 W), out of the sink exhaust | DECISIONS 2026-10-05 (EMI) |
| L10 | Controller 3.3 V rail: power-board DC subtotal **41.657 mA** (native-20) | task 06 `interface_numbers.py` |

## After the re-layout (gates before any bench power)

1. `leg_region_diff.py native-20 → new board`. Any CHANGED leg means a FEM
   re-extraction of that leg (`campaign.py`; delete field files after each
   matrix).
2. Re-run the decision grids (S1/S2/S4/S5, both legs, F6 deck with PMEG6030EP)
   on the new matrices: `round17/d2/f6_legs.py --diode pmeg --temps 27,100,150`
   for both `--cases decision` and `--cases startup`.
3. Re-run `kelvin_plane.py` and `kelvin_budget.py` on a new copper export;
   the band minimum must stay ≥ 44 A.
4. Source audit (`audit.rs`), DRC with schematic parity, and ERC, as for native-20.

## Firmware requirements arising from the same decisions

- 180° fixed phase only; no phase shift (F9 closed by decision).
- Low power by line-synchronous half-cycle bursts with **T_burst ≥ max(2 s,
  4.6·d^3.2/0.65^3.2)**, 20 s default ([flicker screen](validation-results/07-conducted-emi/flicker/README.md)).
- On native-20 (unipolar drive): continuous operation only, until the
  first-edge capture passes (DECISIONS 2026-10-05, F6 addendum).
