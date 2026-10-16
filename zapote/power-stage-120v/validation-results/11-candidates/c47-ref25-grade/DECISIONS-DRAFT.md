63. **Stage 47 (candidate 47): U5 (REF25) on its 125 °C grade, BOM-only on s46; the band network now sits at its solved
    temperature (2026-10-15; draft for the integrator). Board 4139c87b, geometry identical to s46 16a58861 (copper key
    d33d77ac). Card REJECT against s46 on the new Kelvin basis and on cost.**
    Records: `11-candidates/c47-ref25-grade/README.md` (chain `runs-native21/s47/chain47.log`, CHAIN_DONE, no spine
    owner).
    - **Change:** U5 LM4040A25IDBZR → **LM4050AEM3-2.5/NOPB** (TI SNOS455H, LCSC C2156518).
      - Rated TA = TJ −40..125 °C (5.3 p.5; addendum p.25).
      - ±15 mV full range plus 1.2 mV current regulation; IRMIN 65 µA (5.6 p.7).
      - Same DBZ pinout: pin 3 has no internal connection and floats on `u_ref-nc` (p.3).
      - Same pads; 1 instance; no divider change.
      - The JLC listing's −40..85 °C is wrong for the E suffix.
    - **B3:** U5 is now a gated row, keyed to the frozen MPN (`MONITOR_GRADES`).
      - 89.1 °C at c17.5 @ 61: **+35.9 K** against 125 °C (c28 @ 55: +20.3 K). The A25I read −4.1 K.
      - Self-heat 0.2 K: 0.238 mA × 2.5162 V × 326 K/W.
      - Release margin unchanged at +1.0 K (R10); `b3_ratings` PASS.
    - **New band basis, the solved network temperature.** The bands assumed the R26–R37 network at −10..85 °C. Hot-copper
      B3 puts R32–R35 at 93–96 °C and R30 / R36 / R37 at 92–93 °C at the release case, up to 102.9 °C at c28.
      - The band basis is now the −10 °C corner plus each resistor at its B3 estimate, with R5 at its element row.
      - With the A25I that network fails the 288.02 V OVP "must not rise" rule: 288.05 V at c28, and 288.75 V at a uniform
        105 °C.
      - **With the LM4050AEM3, at release: OCP 68.87–117.45 A before Kelvin, 66.75 A after (+2.58 A over 64.17); OVP
        272.64–287.45 V.**
      - At c28: 65.45 A (+1.28 A) and 272.47–287.62 V.
      - On the committed basis it would read 67.89 A and 287.58 V.
      - `kelvin_budget.BAND_BEFORE["native21s47"]` takes the release row.
    - **Card:** every gate and every thermal metric equals s46. Moves:
      - kelvin_band_low_A 67.77 → 66.75 (the basis change; like for like, +0.12 A on either basis);
      - parts_usd_at_500_v2 171.83 → **173.99 (+$2.16 / board)**;
      - lines_short_for_500 14 → 15 (U5 consign);
      - ledger 3 / 39 / 52 / 0 (LM4050AEM3 PARTIAL; the LM4040 was UNAUDITED).
    - **Sourcing:** JLC holds 50 (96 with the two Q1 orderables) against 500.
      - **Owner pre-order of ≥ 550 LM4050AEM3-2.5/NOPB**, consigned to JLC. The line keeps C2156518 for placement.
      - The STOCK addendum flags it `OWNER_PREORDER_CONSIGN`.
    - **Proposed: adopt with a cost override, as for stage 45.** U5 was the last over-rating monitor-class part at the
      release case. It is the only drop-in that holds both band rules with no retrim, and it covers the hotter network the
      old part fails on. The card cannot score a rating violation it has no row for. $2.16 per board is the price.
    - **Also tightened:**
      - `audit.rs` gains `reference_spec()` per MPN (the 2.520 V constant is gone), the 65 µA floor, a 1 mA
        regulation-window ceiling (0.481 mA), the U5 pin-3 float check and `stage47_ref25_grade_holds` (89 / 89);
      - `thresholds.validate_inputs(overrides=)`;
      - the CPL audit's declared EasyEDA pin-name alias. U5 settles 180°, unchanged.
    - **Open:**
      - FMEA re-run on the new reference (OVP / OCP rows at the s47 bands);
      - the owner pre-order;
      - JLC preview of U5: not needed for rotation, but the EasyEDA land is the narrower SOT-23;
      - pin 3 to anode, TI's high-EMI recommendation, needs a layout stage;
      - the ledger's 286 V bus-OVP stresses are below the 287.45–288.02 V band top (pre-existing);
      - U3 TPS70950 (unrated in the ledger) reads 106.7 / 124.3 °C pad against TJ 125 °C.
    - **Reverses if:**
      - the LM4050AEM3 lot cannot be bought. Fallbacks: the electrically equal LM4050QAEM3-2.5 or TL4050A25QDBZR, the same
        bands; or ADR5041B with R37 137 k under ADI's butterfly TC reading;
      - bench thermocouples put the R26–R37 network ≤ 85 °C, which restores the committed basis and the 67.89 A figure;
      - a layout stage moves U5 and its network out of the bias heat.
