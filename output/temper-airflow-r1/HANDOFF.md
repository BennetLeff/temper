# Handoff: board-face jets, for enclosure round R45

From temper-airflow-r1, 2026-10-15. **R45** is the next free enclosure round: R43 is the latest (`output/temper-manufacturing-r43`) and
R44 is reserved for the Codex owner-controls programme (`output/temper-owned-controls/`).

R45 forks R43, keeping the frozen-folder workflow from R43's `design/r43/HANDOFF.md`. It builds the change set below,
then reruns the R43 gate chain.

The reasons are in `DECISIONS.md` and the numbers in `README.md`. Every number traces to a JSON written by a script in
this folder.

## What R45 builds

World frame: R31 and later, as in `src/check_native21_pose.py`. On native-21, x_w = x_model − 141, y_w = 236 − y_model,
and the board top is at Z27.5.

| # | Part (new name) | What | Where (world mm) | Material | Notes |
|---|---|---|---|---|---|
| 1 | `electronics_board_jet_box` (R45-JET-BOX) | Closed jet manifold over the native-21 channel between the TO-247 row and the HF film caps. **Floor:** 1.0 mm thick, with 8 × Ø3.0 mm jets at X −135.5 + 11k (k = 0..7), Y 222.0. **Floor underside:** Z33.5, which is 6.0 mm above the board (H/D 2). **Manifold:** 10.5 × 7 mm inside, 1.0 mm walls, closed at the X−53 end, open at X−140 into item 2. | X−140..−53, Y213.5..225.5, Z33.5..42.5 | Prototype: G11/FR5, machined and bonded. Production: PPS-GF40 moulding, UL 94 V-0, RTI ≥ 150 °C. | **Gaps:** 1.0 mm to the FR-4 pressure strip, 1.2 mm to the film-cap bodies (R43 envelope), 6.0 mm to the board (`cad/fit-check.json`). **Mounting:** cantilevered from item 2. A 1 mm locating rib bears on the FR-4 pressure strip's front face (Y226.5). It must not touch native-21 parts or the steel clamp comb. |
| 2 | `electronics_board_jet_feed_F3` (R45-F3-DUCT) | Feed duct from the push hood to item 1. **Leg A** runs −Y from the hood wall; **leg B** runs +X to the jet box. 12 × 14 mm inside. | Leg A X−178..−164, Y213.5..244.5; leg B X−178..−140, Y213.5..225.5; both Z29.5..45.5 | Same as item 1 | **Fixings:** to the hood wall with 2 × M3 (polymer flange on metal), plus one base bracket under the leg-A/B elbow. **Clearance:** 2.0 mm to the board edge and 5.7 mm to the wrapper. |
| 3 | Push-hood change (R45-C-PUSH-HOOD) | A 12 × 14 mm hole in the hood's −Y wall (Y244.5), plus 2 × M3 PEM for item 2. | X−177..−165, Z30.5..44.5 | 5052, as R32 | The hole's metal rim is 26.0 mm from native-21's components and 23.6 mm from the board. The hood stays bonded to PE. |
| 4 | Exhaust-plenum change (R45-C-PLENUM) | Bay vent: a 30 × 25 mm cut in the plenum's X−32 wall. This is the bay's exit for the jet air. | X−32 wall, Y330..360, Z25..50 | 5052, as R32 | The bottom edge sits 14 mm above the plenum floor (Z11), so liquid in the plenum cannot reach the bay. |
| 5 | Bay-air NTC (R45-BAY-NTC) | A Semitec 104GT-2 bead (the R40 NTC part) in bay air beside the jet box, on a lead to the controller. | Suggested (−95, 200, 55): above C40/C38, outside the jet stream, ≥ 10 mm from any part body | Bead in a PTFE sleeve | Needs a controller thermal-sense channel. The controller owner confirms a spare channel or adds one. |

`cad/fit_check.py` already models items 1–4 as plain envelopes against the R43 STEP:
- no overlap anywhere;
- F3 touches the hood (intended);
- the vent cut removes 750 mm³ of plenum wall.

R45 builds them as real parts in `src/r45_world.py`, with flat patterns or drawings, and adds them to the catalog and BOM.

## Firmware and controller (R45 records the request; the controller owner builds it)

1. **Board loop in the fan law:**
   - `drive = max(PI sink 88.6 °C, PI coil 140 °C, board floor)`;
   - the board floor is **0.55** (6.6 V) whenever the tank current setpoint is above the still-air release ceiling of 18.0 A.
   - At 0.55, `delivery.json` gives:
     - 0.48 CFM through the jets at 27.6 Pa;
     - h_top 100 W/m²K on the design basis;
     - an estimated 45.0 dB(A);
     - 2.8 W typical / 5.4 W maximum blower power.
2. **Loss of airflow:** on tach loss, or drive below the board floor, clamp the tank current to the still-air ceiling, using `TANK_CEILING_DEFAULT_A` 18 A. The power stage sets the allowed delay from the board's thermal time constant.
3. **Bay-air channel (item 5):** derate on measured bay air above 61 °C, using the ceiling table in `board-h-sweep.json` → `ceiling_by_h`.
   - **Still air:** 19.9 A at bay 55 °C, 18.2 A at bay 61 °C.
   - **With jets at the design h of 100 W/m²K:** 30.5 A at bay 55 °C, 28.5 A at bay 61 °C. Above 28 A is an extrapolation; the 28 A Kconfig cap still applies.

## Checks R45 reruns

1. R43's gate chain (`evidence/run_gates.sh`), especially `check_integration.py --all-pairs`, `check_assembly_sequence.py` and `check_cover_lift.py`.
   - The jet box goes in after the sink clamp and comes out before it. Check that native-21 can still be withdrawn with the jet box removed.
2. `evidence/airflow-r32/coil_thermal.py`, extended with the third branch. Use `delivery.py`'s `op3` as the reference.
   - Its results must reproduce `delivery.json`: 0.41 CFM at the floor and 0.48 CFM at 0.55.
3. `cad/fit_check.py` and `cad/channel_parts.py` from this folder, against the R45 STEP and the current power-stage board.
4. The power-stage clearance rules for any metal within 8 mm of native-21 conductors. The change set adds none; keep it that way.

## Bench (add to `design/r32/BENCH-PLAN.md`)

- **A1/A3 extension:**
  - jet flow at drive 0.458 / 0.55 / 1.0, against `delivery.json`;
  - smoke test: bay pressure above plenum pressure at floor drive, and no backflow through the vent with the blower stopped and the coil hot.
- **Board-face h:** a heated-plate or IR measurement under the jet box at drive 0.55. This decides whether the Martin × 0.6 design basis holds, against × 1.0.
- **Soak at 40 °C ambient and 28 A (power-stage request ask 3):** with thermocouples on C40, C38, R12, the laminate at R5.4, bay air at item 5, jet supply air and PS1 case.

## What the power stage must re-run (relayed by the parent; R45 does not edit their records)

See `DECISIONS.md` D6.

## Open item found by the bench kit (2026-10-15)

The channel side-wall and feed-duct sizes in this handoff don't fit its own
12 mm envelope. The jet bench kit (`bench/`, RIG.md and DECISIONS.md) had to
pick one set to build its replica. R45 must settle the geometry, and the
bench replica should be rebuilt to match if it changes, because the spent-jet
escape path affects h.
