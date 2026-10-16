71. **Stage 50 (c50-permit-gate): drive U46.A (hsb_good) from PERMIT through R135, 100 k, in place of the stage-40 10 k
    pull-up to v3v3 (2026-10-16; draft for the integrator). OPEN-ITEMS B13 H2, option P. Board 4876c42e (copper key
    095e5b732746). Card ACCEPT against s49; every gate passes; spine_lock PASS with no reissue.**
    Records: `11-candidates/c50-permit-gate/README.md` (review, fd358959d) and `c50-permit-gate/stage50/README.md` (build;
    chain `runs-native21/s50/chain1.out`, CHAIN_DONE, `SPINE_OWNER=selv`).
    - **Change.**
      - Source: Heartbeat `signal permit`; `rgate = new R100k0603`, `rgate.p1 ~ permit`; `hb.permit ~ PERMIT`.
      - Parts: R135 moves from the 0603WAF1002T5E line to the existing 0603WAF1003T5E line, with the same footprint.
      - Kept: the net name HSB_GOOD (a rename would change spine track keys); U46 untouched.
      - Layout (`patches21.edit_base50`): the F.Cu v3v3 stub R135.1 → (32.5, 109.675) is deleted and its via kept (C168.1
        and the B.Cu v3v3 run share it). A 0.25 mm F.Cu permit stub runs R135.1 → (33.95, 108.3), with a T at a new
        vertex of PERMIT's leg-B trace.
      - Clearances on the built board: 0.95 mm stub, 0.60 mm pad (rule 0.2 mm). Everything is outside the spine region.
    - **Why (the c50 review numbers):**
      - **Coverage.** Guaranteed field coverage of the bias-monitor chain goes from 13.8 % to **36.9 %**, the same as the
        TPS3808 delay option S. P proves U40 stuck-high / Y-VCC on every idle control tick and before every start; S
        proves it once per mains power-on.
      - **Stop path.** PERMIT gains a second, independent stop path through the heartbeat. Hold falls below U40 VT−min
        in **≤ 90.3 µs, or ≤ 122.9 µs with one pump cap shorted** (SPICE, 96 corners). The direct ns path through
        U22/U23 A is unchanged: DIS = NOT(PERMIT ∧ bias_ok), the same truth table.
      - **Start.** PERMIT ↑ to hold ≥ VT+max takes **≤ 11.76 µs**. Drivers are enabled ≤ 13.6 µs after PERMIT, plus the
        2EDR8259X DIS-to-output delay (C39). GPIO35 goes high **≤ 0.53 ms** after PERMIT ↑ and low **≤ 0.36 ms**
        after PERMIT ↓.
      - **Boot race.** The race goes away by construction: RUN_EN, and with it PERMIT, is low through every reset, so
        BIAS_GOOD is low at every boot.
    - **R135 = 100 k, not 10 k.** The one new double-fault path is U37 Hi-Z (announced) plus a v3v3-level source on
      hsb_good.
      - With 10 k this holds PERMIT at 1.58 V, inside U22/U23's undefined band (> VIL 0.8 V).
      - With 100 k it holds PERMIT at **0.27 V**.
      - U46.A levels at 100 k (SCES546E 5.5): high 2.92 V against VT+max 1.95 V; low 0.20 V against VT−min 0.89 V.
      - The R100k × ~15 pF edge is ≤ 1.8 µs (E), on a Schmitt input.
      - No new single point on the c24 basis.
    - **TP19 now reads low while PERMIT is low.** At idle, bias health is visible only as the hb_rx square wave at U46.2 /
      U32.13. B8 and COMMISSIONING H2 must drive J4.9 high with the PWM idle.
    - **Cost $0.** No line added or removed. 0603WAF1003T5E goes 8 → 9 and 0603WAF1002T5E 10 → 9, −$0.002 / board at
      500. `parts_usd_at_500_v2` stays 169.49.
    - **Board.**
      - Equal to s49 on D5 (8.047 / 8.507 mm), RES_A outer (13.375 mm), Kelvin band after 69.18 A, the B3 margins,
        bank_air 0.967, coil pickup 4.17 A and necks 0.993 / 1.021.
      - `track_any_angle_mm` 281.6 → 280.2: the deleted stub was 0.025 mm off vertical.
      - The bands on this board's own solve equal BAND_BEFORE (71.59-114.58 A; `stage50/scripts/bands50.py --check`).
      - pin_absmax: `hsb_good` is hull [selv_gnd, permit]. Ledger PASS 3 / 92 / 0 / 0 (U46 function text corrected).
      - `audit.rs` adds the test `stage50_heartbeat_gated_by_permit`: R135.1 on v3v3, or the 10 k part, fails.
    - **Firmware (separate lane, not in this stage).** The review's §5 start sequence must land before or with this
      board: check 2 off PAN_DET entry, check 3 keyed to PERMIT, RUN_EN raised with the pads low before the PWM (C39). As
      the firmware stands, check 2 refuses every start: fail-safe, but the hob does not run.
    - **Bench (review §6):** PERMIT ↑ → DIS ↓ ≤ 13.6 µs + the DIS-to-output delay; GPIO35 ↑ ≤ 0.53 ms; PERMIT ↓ → TP19 ↓
      ≤ 90 µs; GPIO35 ↓ ≤ 0.36 ms; 20 starts at 25 °C and hot.
    - **Reverses if:**
      - the bench stop or start times miss these bounds;
      - or firmware cannot key checks 2 / 3 to PERMIT. Then fall back to the 10 k v3v3 pull-up (s49) and option S.
