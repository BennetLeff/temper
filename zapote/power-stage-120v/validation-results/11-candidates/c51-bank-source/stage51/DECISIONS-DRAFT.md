73. **Stage 51 (c51-bank-source): fit KNSCHA MMK104J3DF1KN208G2 on a dual-pitch bank footprint and keep TDK
    B32643B8104J000 as the documented drop-in for the 28 A route (2026-10-16; draft for the integrator). Board 9afc509b
    (copper key 3a4c616e7870). Card REJECT against s50 on bank_air and the vendor-curve bank ratios and on cost
    (+$0.28 / board): a sourcing override. Every gate passes.**
    Records:
    - `11-candidates/c51-bank-source/README.md`: the sourcing study, copied from the bank-src lane;
    - `c51-bank-source/stage51/README.md`: the build. Chain `runs-native21/s51/chain1.out`, CHAIN_DONE, `SPINE_OWNER=selv`.

    **Why.**
    - The owner rejected B32643B8104J000 because it cannot be sourced: JLC 0, a 28-week lead and MOQ 2080.
    - KNSCHA MMK104J3DF1KN208G2 (JLC C528962) is the best in-stock 2 kV part: **4,952 at JLC against 2,500 for 500 boards,
      read 2026-10-16**, $0.3035 at 1000+. It is the only stocked 2 kV part whose vendor publishes a current curve.
    - No second stocked part qualifies. KEMET R75 has 1,804 across DigiKey / Newark and fails on heat at 1.444.

    **Change.**
    - **Footprint** `temper:Bank_Film_DualPitch_P22.5_P27.5_Radial`:
      - pad 1 (RES_A) at x 163.0, round;
      - two pad-2 (SW_B) holes, at x 185.5 (P22.5, TDK) and x 190.5 (P27.5, KNSCHA), both on sw_b;
      - drills 1.2 mm for both 0.8 ± 0.05 mm leads, ring 0.6 mm against JLC's 0.254 mm PTH rule;
      - courtyard / silk over the union of both bodies.
    - **Rows** stay at the s49 y 53.2–113.2, 15 mm pitch. The TDK 14.5 mm body still fits (0.5 mm gaps); KNSCHA's
      11.5 mm leaves 3.5 mm.
    - **No copper edit:** the new hole sits on the widened s49 sw_b strip.
    - **Board unchanged from s50:** D5 8.047 / 8.507 mm, RES_A outer 13.375 mm, barrier 0, DRC 0 / 0, Kelvin
      69.18 A, B3 release +1.3 K. The new holes are 8.229 mm plan view from SELV copper and 20.0 mm from PE.
    - **BOM / CPL:** KNSCHA fitted (C528962, OK in the CPL audit). TDK is not fitted and is **off the pre-order list**.
      Its ledger audit moves to `alternates`.

    **Margins (this board).**
    - **Voltage passes, as c34** (both 2000 V):
      - F3 R0/R1 1693.2 V against 1700 V (0.996 of 0.85 VR, +6.8 V);
      - double fault 1607.1 / 2000 V;
      - no-pan 775 / 1200 V (0.646);
      - dV/dt 0.157.
    - **Current does not reach 28 A:**
      - vendor ratio 0.978 at 28 A / 35 kHz (c34 0.831);
      - bank_air strict **1.221** (c34 0.967), 0.869 with the gap-flow credit;
      - release in still air 0.958 with radiation, 1.209 without (18.375 A).

    **Ceiling consequence.**
    - **22 A strict.** At 22 A the gate is 0.959 and the vendor ratio 0.768. The strict gate crosses 1.00 at 22.9 A.
    - **24 A if the bench shows the gap credit.** At 24 A the gap-credit gate is 0.745 and the vendor ratio 0.838. The
      85 % rule binds at 24.3 A.
    - **28 A needs the TDK alternate fitted** (same footprint, no re-layout: bank_air 0.967, vendor 0.831), **or a
      better-rated part.** The new OPEN-ITEMS row S28 tracks this (S26 / S27 are taken on ps-integrate).
    - This caps the commissioned ladder above the shipped 17.5 A. It does not change the release.

    **Bench items** (KNSCHA publishes none per part; pre-lot, with S25):
    1. the current rating basis: rise at 6.2 A / 35 kHz on one part;
    2. ESR / tan δ at 35 / 40 kHz, at 25 °C and about 80 °C (the rating implies ≤ 10.7 mΩ; strict 22 A tolerates 11.6 mΩ);
    3. behaviour above 85 °C ambient (the derating to 105 °C is ASSUMED linear);
    4. the gap-flow credit at 28 A under the S24 flow: the worst interior part ≤ 10 K over local air, and the gap
       velocity;
    5. body dimensions on 10 parts (the gap width drives the credit).

    **Approval basis.** A HOT-side tank part: no UL / ENEC file is required, and KNSCHA lists none (no AEC either). The
    spec gives flammability grade B; a UL 94 V-0 case is reported by the study but not read in the spec.

    **Reverses if:**
    - the bench fails item 1 or 2 at 22 A strict: the bank would not hold its own cap. Fit the TDK alternate (owner
      pre-order) or find a better-rated part;
    - TDK B32643B8104J000 (or another part qualified for 28 A on P22.5 / P27.5) becomes stocked at a usable lead and MOQ:
      fit it on the same footprint, with no re-layout;
    - the product needs 28 A commissioned before a second part is found: the TDK pre-order is back on the list.
