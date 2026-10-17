58. **Stage 44 (candidate 44, SELV-spine lane): the SELV return-path pass, built on s43 (2026-10-15; adopt). Board of
    record s44, 2a84051f. Card ACCEPT against s43.** Records: `11-candidates/c44-selv-spine/README.md`. Chain
    CHAIN_DONE with `SPINE_OWNER=selv`.
    - **Opens 15 → 7 (OPEN-ITEMS S10).** All 8 SELV-net opens are closed: PERMIT ×3, BUS_FAULT, BUS_FAULT_ISO, BIAS_GOOD ×3.
      Each F↔B via of these slow SELV lines swaps the In1 v3v3 / In2 selv_gnd reference, and no cap was within 4.6–21 mm.
    - **The fix:**
      - seven 100 nF 0603 v3v3-selv_gnd transfer caps, **C169–C175** (`c_ref_xfer_6..12`), 1.10–2.60 mm from their vias;
      - each on its own plane vias 0.85 mm off the pad;
      - BUS_FAULT's U13 drop via moves 0.97 mm down its trunk (no cap pose within 3 mm of the old spot);
      - BIAS_GOOD's U40 In2 hop runs on to its leg-A drop, and its pour-edge via (no pour on either side) is removed.
    - **Card:**
      - better: `return_path_open_changes` 15 → 7, acute corners 23 → 22;
      - costs: parts $202.32 → $202.38 at 500, placements 351 → 358, vias 753 → 765. The caps share the existing JLC Basic
        line C14663 (no new BOM line or MPN);
      - unchanged: D5 8.047 / 8.507, RES_A 13.375, worst asserted 2.72 mm, Kelvin 67.77, OCP pickup 4.17 A, fuse ratio
        0.993, EMI 12.4 dB, touch 0.241 mA, CMTI 1.579, jet strip 1.72 mm;
      - B3 release +1.2 K, laminate −30.2 K, rated part −32.3 K, `b3_ratings` PASS (2 of 132 rows move 0.1 K).
      - Cleanup pass: 0 edits (idempotent).
    - **Left (7, HOT side, not this lane):** bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, the GOOD node at U45.1.
      - Their vias sit off the In1 `ocp_kelvin_p` / `n_ls` pours, with In2 / B bare.
      - Closing them needs HOT-domain Kelvin / n_ls copper on the stage-28-locked OCP nets.
      - That is a WS4 / G08 pass with the OCP pickup and Kelvin re-checked. S10 stays open for those 7.
    - **SELV-spine lock re-issued** (baseline `spine-baseline-native21s44`, board f27d5bba = the run-1 copper):
      - owner-scope differences: only C170 / C174's 4 plane vias and stubs, and 3.155 mm² of plane antipad per plane;
      - frozen_refs gains C169–C175.
    - **Gates tightened:**
      - `return_path19.XFER_CAPS` adds C169–C175 (pad-to-plane via ≤ 1.6 mm);
      - `audit.rs` IDENTITY and the net loop cover `c_ref_xfer_5..12`; new test `stage44_selv_transfer_caps_hold`, 86 / 86.
    - **Reverses if:** a lane needs the C169–C175 / BUS_FAULT via spots for other copper (then the opens come back), or
      bench SI shows the slow SELV lines need no transfer caps (−7 placements).
