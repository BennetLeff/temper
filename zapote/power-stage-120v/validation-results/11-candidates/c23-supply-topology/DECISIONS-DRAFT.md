# Draft for DECISIONS.md (not entered; the integration lead numbers and adopts it)

48. **Stage 38 (candidate 23): the DECISIONS 47 supply change set built on s35; L1 kept (2026-10-15).** Records:
    `validation-results/11-candidates/c23-supply-topology/README.md`. Board native21s38 `b5bf428d`, chain CHAIN_DONE
    (`SPINE_OWNER=selv`). Scorecard ACCEPT against s35:
    - cheaper: parts $206.44 → $202.24 at 500, BOM lines 94 → 93, placements 349 → 348;
    - better: EMI 10.5 → 12.4 dB, touch current 0.974 → 0.241 mA;
    - nothing worse. The B3 ratings margins are unchanged (−56.4 / −38.9 K); the release gate stays open.

    **Built:**
    1. **PS1 deleted.** V15_SELV is gone, and J4.1 is not connected (single-pin SELV net `j4_nc1`). The controller
       must merge J13 into its logic rail and drop the J4.1 input before it powers a stage-38 board
       (`CONTROLLER-REQUEST.md` addendum 2).
    2. **PS2 → MEAN WELL MPM-20-24** on the unchanged IRM-20 footprint. Case 219A is identical: MPM-20-SPEC
       2024-10-30 p.4 = IRM-20-SPEC p.3.
       - Ledger: 44 % of 21.6 W; 90 % of the p.3 derating holds to 70.3 °C local air; 53 % of 264 VAC.
       - Approvals: IEC 60601-1 (2 × MOPP) and IEC 60335-1, no UL file, so it is a certifier item.
       - Sourcing: JLC C6675337 holds 5,047; the card uses the DigiKey basis, $12.60 at 500.

    **Not built:**
    3. **L1 stays TDK B82726S2203A020; the SCF31X is not taken.** Its 45 × 42 mm body does not fit the 47.96 × 32.81 mm
       slot without moving C1 / C5 / F1. That is compaction, which DECISIONS 47 item 6 rules out. Rating (68 %) and
       height (33 mm) are fine. DigiKey holds only 68. The robust variant (11.51 dB) waits for a re-layout, and L1
       still sets the 29-week build date.

    **Off-board, counted in the verdicts:**
    4. The D-22 module Y is removed and its choke becomes the SCF31X 5.68 mH (`MODULE-REQUEST.md`). PS3 is the
       MPM-65-15ST. Both are counted in the leakage and EMI results: touch 0.2412 mA (budget 0.25, margin 8.8 µA);
       s19b nominal 12.37 dB and minimum 8.19 dB.
       - Leakage rises to 0.653 mA with the module Y kept, and to 0.324 mA with an IRM-60 in PS3.
       - The scripts that write the scorecard inputs now model the s38 system: `leakage_budget.py`, and
         `emi_s19b.py` `MODULE_S38` with sensitivities relative to the nominal parts. Their s35 rows reproduce the
         committed 0.9741 mA / 10.48 dB.

    **Layout:**
    5. **The freed PS1 area stays clear.**
       - L_FILT: re-laid to F2 at 40.5 mm (was 60.5 mm), which removes one acute corner.
       - N_FILT: its J11 via becomes 0.85 / 0.3 at (256.8, 116.6). The old 0.6 ring had sat inside PS1.2, and on
         its own it failed task 04's topology preflight.
    6. **SELV spine lock re-issued by the selv lane.** The new baseline is `spine-baseline-native21s38-all-copper`.
       The only differences are J4.1's net and the v15_selv antipads filled in selv_gnd / v3v3.

    **Process:** the co-design study's manifest is now pinned to its base 0aecdc56f.

    **Reverses if:**
    - a controller cannot take the J13 merge (PS1 returns);
    - the module Y must stay (the leakage limit fails);
    - the certifier rejects the MPM approval basis.
