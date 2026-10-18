# Independent design review, 2026-10-18 (fresh Opus reviewer, read-only)

Model output, kept verbatim. Findings and their handling: DECISIONS 79 and controller DECISIONS C49. Items it could not verify are open.

# Independent review: native-21 power board (s53) + controller J13 merge (uncommitted, ctrl-j13)

Sources read: `ps-integrate/.../frozen/default.net` and `resolved-components.json` (the net's libsource fields are stale, OPEN-ITEMS B14, so values come from the MPNs), `audit.rs` SELV/BARRIER tables, `ledger.json` (all 387 checks: I recomputed each ratio, and none disagrees with its inputs), OPEN-ITEMS, DECISIONS 71/76, CONTROLLER-REQUEST.md, the `ctrl-j13` working-tree diff (`controller.ato`, `controller_parts.ato`, `controller_calcs.py`, `verify_controller.py`), its new `frozen/` and `evidence/`, and the firmware pin diff.

## Findings

### F1. MAJOR: the J13 merge renumbered 223 controller refdes, and the order package is stale and now points at the wrong parts
- The new parts took the low designators (D1 d_bias, R1 r_bias_pd, R2 r_bias_ser, C1 c_bias, D2 d_merge). Every later D/R/C shifted (old vs new `frozen/default.net`: 223 renames).
- `ORDER.md:55,63,93,95,130` tells JLC to consign R39 (Rref RG2012V-431-W-T1), or to mark it DNP. Rref is now **R41**. The new **R39 is `thermal.open_top`**, the reference resistor of the heatsink open-NTC comparator. Following ORDER.md would DNP or hand-fit the wrong part.
- `fab/` was not regenerated. `fab/bom-jlcpcb.csv` (87 lines) has no SS14 and no 1 MΩ, so the committed gerbers, BOM and CPL are the pre-merge board, with J4.1 = v15_selv. That board does not power up on an s38+ power board.
- `pcb/libs/Diode_SMD.pretty/D_SMA.kicad_mod` is untracked.
- **Fix (smallest):** give the five new parts explicit high designators (e.g. D60, R200–R202, C200) so nothing renumbers. Then re-run make.py/fab, re-check ORDER.md refdes, and commit the footprint.

### F2. MAJOR: the merge does not show CONTROLLER-REQUEST item 1, and PS3 derating was not re-checked with the logic load
- Item 1 asks that "a blower start (5.46 A bound) or stall cannot pull the logic rail below its brown-out threshold".
- **What the merge provides.** SS14 plus the existing 100 µF gives **1.11 ms** of hold-up (`evidence/controller_calcs.json` merge_rail.holdup_ms_to_buck_stop).
- **What the calcs show.** The same file shows U2's start draw bound is **3.96–5.46 A** at 15 V against PS3's OCP low corner of **4.6 A** (ps3_budget, IRM-60 basis). An overload hiccup lasts hundreds of ms.
- **Consequence.** A blower start at U2's current limit, or a shorted or stalled fan, can now hiccup PS3 and reset the whole controller in a loop. Stage 16 separated the rails to prevent exactly this. It fails safe (RAIL_OK and the driver VDDI UVLO drop the stage), but the unit stops working.
- **Derating.** `merge_rail` checks only ≤ 65 W. It never re-runs `ps3_within_derated_60C` with the merged load: **44.55 W against 45.0 W** on the 60 °C curve that ps3_budget uses (99 %). The request asked for PS3 air ≤ 58 °C after the extra 4.8 W.
- **Stale comments.** `controller.ato:348-353` still says "blower start or stall cannot brown out v15_selv / the logic" and still names PS3 as IRM-60-15ST.
- **Fix:**
  - Add the derated-power check and a U2-start-vs-PS3-OCP check.
  - Either lengthen U2 soft-start (c_ss_12 10 nF → ~100 nF) so the start draw stays under OCP, or accept and record the reset-on-fan-fault behaviour.
  - Keep request item 5's bench scope.

### F3. MINOR: the J4.1 TVS sits directly on the pin, so 15 V on J4.1 destroys it
- `d_bias` (ESD5Z3.3, VRWM 3.3 V) is on `bias_good_j4` at the connector, ahead of the 10 k.
- Any pre-s38 power board (PS1 drives 15 V on J4.1), or the old bench procedure that put 15 V on J4.1, forces amps into a SOD-523 part. COMMISSIONING now forbids it, but nothing in hardware does.
- **Fix:** swap the order: J4.1 → 10 k → node with the TVS, 1 nF and GPIO35, keeping the 1 MΩ at J4.1. The level changes by < 1 % (10 k against 1.22 MΩ), and 15 V then puts only ~1.2 mA into the TVS.

### F4. MINOR: the ledger mislabels the gate drivers as a functional HOT-to-HOT barrier
- The ledger note for `2EDR8259XXUMA1` says "the barrier is HOT-to-HOT functional here, so no approval is relied on for safety".
- The netlist says otherwise. U1/U2 pin 4 GNDI = selv_gnd and pins 3/8 VDDI = v3v3 (J4.3, SELV); outputs are on n_ls / n_ha / n_hb. They are reinforced SELV↔HOT barriers (audit.rs BARRIER_PARTS agrees).
- The certifier packet's A3 #15 asks to confirm UL files for Chipanalog and RECOM (RECOM is HOT-to-HOT here), but not Infineon E311313 (U1/U2), TI (U4) or Vishay (U36).
- The hardware is adequately rated (VIOWM 1250 Vrms); this is a certification-record error.
- **Fix:** correct the note and add U1/U2/U4/U36 to A3 #15.

### F5. MINOR: the controller FMEA still argues from UCC21550 properties
- Controller `DECISIONS.md:346,348,354` still cite VCCI UVLO 2.35–2.65 V and "50 kΩ UCC21550 internal" input pull-downs.
- **The request's "restate the line" was not done.** The 2EDR8259X has VDDI UVLO on ≤ 2.95 V and off ≥ 2.55 V, and DIS has an internal pull-down (open = enabled). R73/R76 cover the DIS case.
- **The open-conductor case.** The PWM pull-downs (rpd_pwm_*, 10 k) are on the controller side of the harness. The power board has no pull-down at U1/U2 INA/INB (pwm_* nets are J4 ↔ driver only).
- **Fix:** restate the rows. If the 2EDR datasheet gives no input pull-down, add 10–47 k at U1/U2 IN pins on the power board.

### F6. MINOR: the merge is not recorded, and verification runs against a stale power-board snapshot
- There is no controller DECISIONS entry (C49) for the merge.
- `verify_controller.check_j4` compares against the native-21 snapshot of 2026-10-08, with pin 1 overridden by hand. `check_v3v3` budgets the power board's 3.3 V load from that snapshot (U40/U46, R135 and the stage 48–50 parts are missing).
- **Fix:** re-pin the snapshot to the s53 frozen net.

### Power board
I found **no BLOCKER or MAJOR** in the PERMIT, gate-drive or barrier circuits as committed.

## Checked and found sound
- **PERMIT → DIS (both legs).**
  - The logic: J4.9 → R6/R14 100 Ω, R7/R15 100 k pull-downs → U22/U23 NAND(permit, BIAS_GOOD) → DIS (2EDR: active high). R73/R76 10 k pull DIS up to v3v3.
  - BIAS_GOOD = heartbeat pump AND PERMIT (R135 100 k → U46.A, U40 buffer).
  - On the controller: PERMIT = U37 AND(latch Q, RUN_EN). RUN_EN has a 4.7 k pull-down, PERMIT a 10 k pull-down, and U37 has Ioff.
  - No path enables a driver with PERMIT low.
- **Floating J4 pins.**
  - J4.9 open → low (2 × 100 k + R135).
  - J4.10 open → controller 10 k pull-up = fault.
  - J4.3 open → driver VDDI UVLO. Any back-feed through the IN pins is also seen by R73/R76, which hold DIS high.
  - J4.1 open → 1 MΩ reads low.
  - ct_zc stuck at either level → one of the two capacitive-mode checks fails, so it reveals itself.
- **HOT5 loss.** The CA-IS3720 defaults high, so bus_fault goes high (fault).
- **Power-up and brown-out order.**
  - TPS3823 asserts from ~1.1 V, which clears the latch, and RUN_EN is held low.
  - Falling rail: TPS3703 (3.146 V, 1 ms filter) → TPS3823 (~2.9 V) → 2EDR VDDI UVLO off (≥ 2.55 V).
  - A PS3 hiccup ends in this safe state.
  - Firmware keeps no heat state in NVS, so there is no auto-restart.
- **Gate network.**
  - 68 Ω on, 1 Ω + PMEG6030 off, 10 k gate–source, 4.7 nF C0G Cgs.
  - DT 49.9 k → 499 ns ±15 %, with STP.
  - The 8 V output UVLO is backed by the bias-monitor heartbeat (≤ 90 µs).
- **GPIO35** on WROOM-1U-**N8** (no octal PSRAM) is usable. The BIAS_GOOD high level is 0.817·VDD against VIH 0.75·VDD.
- **Merge diode.** SS14 orientation is right (pin 1 = K on v15_selv), and 40 V/1 A is ample. At OVP 20.25 V the parts hold: 25 V caps (81 %), TPS62933 30 V, TLV760 30 V, AD8436 36 V.
- **Barrier and leakage.**
  - Barrier crossings in the netlist are only U1/U2, U4, U9, U32, U36 and T1; transfer caps C153–C178 are all v3v3–selv_gnd.
  - Y caps are 2 × 2.2 nF to PE, and SELV is bonded to PE by R38 0 Ω (functional).
  - Touch current is 0.2412 / 0.25 mA on the model.
- **Ledger.** No check fails at release. The tightest are thin: C12-family temperature 0.992, J1 0.982, FET dv/dt max-Qrr 0.974 (bench D-8).
- **FET VDS.** The VDS check omits the stacked-event static bus (489 V with the D3 clamp, 512 V without: 0.75 / 0.79 of 650 V). It still passes the 0.8 screen, but it should be listed.

## Could not verify (no datasheets offline, scripts not run)
- 2EDR8259X: internal IN pull-downs, the STP truth table, and the DIS-to-output delay (the ledger says the last is unspecified).
- ESD5Z3.3 leakage hot. The calc uses 50 nA at 25 °C; the high level tolerates ≈ 1.1 µA at 3.135 V.
- MPM-65-15ST OCP point and derating curve.
- Layout creepage and clearance (8.047 mm D5 minimum), and the HF (IEC 60664-4) working-voltage basis for the tank nets (certifier A3 #11).
- The T1 insulation basis: 5 kVrms, but no working-voltage or UL file (a ledger gap).
- The CA-IS3720 pin mapping.
- The touch-current model itself, which has only an 8.8 µA margin and needs the bench.
