39. **Six-layer phase A accepted on the data; adoption pending three checks (2026-10-14; draft, candidate 33).**
    - **What:** stage 32 (same outline, placement, parts) on JLC061622-1080A, six layers, 2 / 2 oz (`native-21/stackup-6L.json`):
      - In1 as today;
      - In2 bus_p / selv_gnd, so bus_p / hv_ret are a 0.30 mm core pair instead of 0.5 mm;
      - In3 signal plus a bus_p image under the bridge;
      - In4 images of v3v3, n_ha, n_hb, n_ls and ocp_kelvin_p, with no plane under the B-side switch nodes.

      Plan B (PLAN.md: In4 as the plane) was rejected on the loop screen: +2.90 / +1.67 nH plane-pair term.
    - **Method:** stage 32's routed copper is frozen as the base (`INCR21_FROZEN`, `c33-six-layer/passes33.sh`) plus
      `patches21.add_stage33` (images, stitch vias). One pass gave 0 unconnected and 0 errors. The chain `native21s33`
      (board 710c0a45) gave CHAIN_DONE with every gate clean. Both boards are scored on the stack depth basis (item 38).
      Step 0 closed the cache trap first: one model key for the task-04 and B3 caches (`d3956aa72`, `CACHE-PROOF.md`).
    - **Scorecard: ACCEPT against 19c, s32 and s32 restated.** Better, against s32 restated:
      - return-path open changes 18 -> 8;
      - worst asserted 2.72 -> 2.38 mm;
      - B3 c28_h25 134.9 -> 129.3 °C;
      - B3 nominal_h10 162.0 -> 155.1 °C;
      - OCP pickup 4.13 -> 3.72 A;
      - Kelvin band low 67.77 -> 67.79 A.

      Nothing is worse. Parts are identical. The bare board is $16.18 against $16.79 per board at 500 (POFV is free on
      6 L), but takes 10-11 days to build instead of 5-6. Task 04 bus_p span is 2.62 % (s32 2.85 %); necks 0.993; DFM
      719 vias.
    - **Not closed:**
      - 30b: C161 still reaches n_ls through about 4.5 mm of In1, because the In4 image is cut under bus_fault_hot.
      - 30a: not attempted.
      - 8 return-path opens remain where no pour reaches.
    - **Before adoption (the stack becomes the board of record, copper-s33 goes into layout/, FAB-NOTE moves to 6 L):**
      - FEM re-extraction of the commutation loops (the screen covers only the plane-pair term, -1.28 / -0.74 nH);
      - EMI / leakage re-check (the switch-node pF screen gives 303 -> 312);
      - a 6-layer Gerber quote of `native-21-gerbers-s33-6L.zip` (inner-copper line);
      - the CTI / insulation inquiry re-asked for the six-layer stack.
    - **Reverses if:** FEM or EMI on the six-layer copper is worse than s32, or the Gerber quote prices 6 L above 4 L
      POFV.
