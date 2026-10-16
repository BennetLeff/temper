67. **Stage 48 (candidate 48): the four TPS70950 ENs on dividers and on the Q1 grade, a REF25 watchdog on U14's second
    channel, BIAS_GOOD read back on J4.1, and end-of-line test pads (2026-10-16; draft for the integrator). Board
    23209767 (copper key 659ccad1). Card REJECT against s47 on cost alone (+$1.69 / board); every gate passes and
    pin_absmax is now an ordinary gate.**
    Records: `11-candidates/c48-ldo-en-ref-watch/README.md` (chain `runs-native21/s48/chain6.out`, CHAIN_DONE,
    `SPINE_OWNER=selv`).
    - **S19, EN within its rating.** U3 / U37 / U38 / U39 had EN tied to IN: 15.46 V / 17.43 V against EN abs max 7 V
      ("Do not connect EN to VIN", SBVS186H 7.4 p.13).
      - Now 100 k / 27 k from each LDO's own IN to its own GND (R136-R143, existing Basic lines).
      - EN: U3 2.987-3.413 V (3.681 V at the span-OV corner); U37-U39 3.414-3.845 V (4.111 V). That is ±1 % + 100 ppm/K
        over 100 K adverse, plus a 1 µA pull-up bound.
      - Every EN stays between VEN(HI) 0.9 V and the 6.5 V recommended maximum; 6.5 V is reached only at IN 29.5 V.
      - Floating EN (allowed by TI) was rejected: the 300 nA typical pull-up loses to a few MΩ of contamination on this
        uncoated board.
      - `pin_absmax` reads 0 failures. `pin_absmax_expected.json` is empty, so the gate now rejects any new violation.
    - **Grade: TPS70950QDBVRQ1** (SLVSCE6D rev. D; LCSC C485909) on all four sockets.
      - ±1 % over TJ −40..125 °C (5.5 p.5); the plain part holds ±1 % only to 85 °C.
      - Same DBV pinout and pads. Abs max VIN 32 V, EN 7 V, TJ 150 °C (5.1 p.3). ψJB 40.7 K/W (5.4 p.4, new chip).
      - JLC 11,607 in stock; $0.682 at 2,000 (+$1.49 / board over C96028).
    - **U3 on its junction (B3).** U3 deposits its 0.160 W bound, and its gated row is pad copper + 0.160 W × 40.7 K/W
      against TJ 125 °C.
      - **Release c17.5 @ 61: 109.7 °C, +15.3 K.** c22: 109.6 °C (+15.4 K); c28: 121.6 °C (+3.4 K, ratchet only).
      - Cross-check: the body model's DBV network (RthJB 39.5 K/W) gives 109.2 °C on the same basis.
      - U3 had to move beside C26 (its old slot had no routable corridor), next to the RES_A copper. U3.2 (GND) now leaves
        0.4 mm both ways: west to its Kelvin via, and east under the body to C48.2 and its via (SLVSCE6D 7.4.1.2,
        "heavier copper ... plated through-holes").
      - **U3's heat goes into pads 1 / 2 / 3 / 5**, because pin 4 is NC, "No internal connection" (Table 4-1 p.3). This is
        R5's sense-finger rule. Heated, the isolated NC pad floated to the junction node and became the row's "pad
        copper". Runs 3-5 then read 124.8 / 116.4 / 124.1 °C as the 0.25 mm mesh drew the GND run near it differently
        (a 3 × Δmesh term of 15.5 / 9.6 / 15.3 K, against 4.0 K now). `test_b3_hot_copper` pins the pad list.
      - Side effects: U5 is at 91.8 °C (89.1 at s47; +33.2 K). The legacy 1 mm point peaks (on the card, not compared)
        now sit on U3's single heated cell: nominal_h10 171.3 → 177.6 °C.
      - Release margin overall unchanged at +1.0 K (R10); `b3_ratings` PASS.
    - **H1, REF25 watchdog.** R144 63.4 k / R145 11.7 k (0.1 %, existing lines) into U14 INB− (pin 4). OUTB joins OUTA on
      HOT5_UV_RAW.
      - Trips at REF25 2.526-2.610 V, which is 9.7 mV over REF25's 2.5162 V maximum.
      - With U5 open, REF25 is ≥ 2.845 V: always caught. The watchdog adds 33.5 µA; U5 keeps ≥ 0.1075 mA (IRMIN 65 µA).
      - **U14 VDD and C48 moved from V15_LS to HOT5.** A pin 4-5 bridge then puts ≤ 5.5 V on INB− (abs max 7 V) and
        trips. VIT is specified the same at VDD 1.8-18 V, and OUTA is driven low below UVLO (SBVS187G 6.5 p.6).
        `FAULT-INTERFACE.md` is updated.
    - **H2, BIAS_GOOD → J4.1** through R146 220 k (1206, at the connector).
      - 220 k so that a J4.1-J4.9 harness short holds PERMIT_GATE at 0.68 V < VIL 0.8 V.
      - The hand-laid branch changes layer four times. **C176-C178** (CC0603KRX7R9BB104, the C169-C175 line) are the
        SELV transfer caps for three of them; C174 serves the fourth. Return-path opens stay at 7.
      - The SELV spine lock is reissued on board 596ba3bf, and C176-C178 join `frozen_refs`.
      - **Firmware requirement, not implemented:** the controller reads J4.1 high-Z (pull-down ≥ ~1 MΩ). It must read
        low before the heartbeat, high before PERMIT, and stay high while PERMIT is held. It needs a GPIO assignment;
        `firmware/` is unchanged (host tests 31 / 31).
    - **H3-H5, end-of-line pads.**
      - TP41-TP51: 11 of the 12 monitor taps. TP52: REF25. Reference pads TP53-TP59. TP1-TP40 keep their numbers.
      - TP6 / TP28 moved to the bottom side.
      - No pad for `monitor_ls-ov` (probed at C67.1) or for U26.6 3P2V (no copper; probed at the pin toe).
      - `BRINGUP-PROBES.md`: 34 signal pads (22 at s47).
    - **Card against s47.**
      - Every gate passes. Return-path opens 7 = 7; acute corners 22 = 22; fuse copper 0.993 = 0.993.
      - Kelvin band 66.75 → 66.46 A: U14's IDD on HOT5 and the watchdog current; floor 64.17 A.
      - Right-angle corners 49 → 53 (+4, allowance 5); any-angle 272.6 → 281.6 mm.
      - parts_usd_at_500_v2 173.99 → 175.68; placements 358 → 372.
      - Ledger 3 / 91 / 0 / 0 PASS (TPS70950QDBVRQ1 PARTIAL; its TJ row keyed to the B3 margins).
      - CPL audit OK 298 / CORRECTED 32 / NEEDS-PREVIEW 31. U3 settles at 180°.
    - **Proposed: adopt with a cost override**, as for stages 45 and 47. It removes the four EN abs-max violations (the
      reason pin_absmax was a release gate), puts four LDOs on a grade rated for their temperature, and makes a REF25 fault
      announce itself. The cost is $1.69 per board. The card cannot score any of these as a gain.
    - **Open:**
      - Controller firmware and pin assignment for J4.1 (above).
      - FMEA re-run of the H1 / H2 rows on this board.
      - Bench check of U3's junction: thermocouple on U3.2 at the release case.
      - TI's "CIN close to the pins" (7.4.1 p.19) is UNCHECKED: C25 stays ~12 mm away, as at s47, and the input cap is
        not needed for stability (7.1.1 p.17).
      - The EasyEDA land for C485909 was fetched once for the CPL audit.
    - **Reverses if:**
      - the controller cannot spare a GPIO for J4.1 (R146 then stays as a harmless NC-pin load);
      - bench or a finer model puts U3 above 125 °C at the release case. U3 then needs a copper pour on In1 / B.Cu, or
        the WSON-6 DRV package with its thermal pad (RθJA 82.5 against 176.5 K/W, 5.4 p.4).
