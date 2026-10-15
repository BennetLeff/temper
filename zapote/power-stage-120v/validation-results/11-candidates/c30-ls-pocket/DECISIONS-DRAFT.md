# Draft for DECISIONS.md (not entered; the integration lead numbers and adopts it)

52. **Stage 40 (candidate 30): U44 becomes the ISO6721FB HS-B -> LS link (30a) and C161 reaches the n_ls plane (30b),
    built on s38 (2026-10-15).** Records: `validation-results/11-candidates/c30-ls-pocket/README.md`. Board native21s40
    `33ed17f3`, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS against the s38 baseline). Scorecard ACCEPT
    against s38:
    - cheaper: parts $202.24 -> $202.21 at 500, BOM lines 93 -> 92, JLC extended lines 67 -> 66;
    - better: return-path open changes 18 -> 15, acute corners 205 -> 199, right angles 103 -> 101, fold-backs 44 -> 43;
    - within tolerance: B3 laminate -38.0 -> -38.3 K, rated part -63.9 -> -64.1 K. `b3_ratings` fails on both boards
      (DECISIONS 51), so the release gate stays where 51 left it. Placements 348 -> 351, vias 747 -> 754.
    - unchanged: D5 8.047 / 8.507 mm, RES_A 13.375 mm, Kelvin band 67.77-116.44, OCP pickup 4.17 A, fuse ratio 0.993,
      EMI 12.4 dB, touch 0.241 mA, enclosure fit, task 04 39 / 0. Ledger violations stay at 1 (IPW65R018CFD7).

    **Built:**
    1. **30a: heartbeat M1b as drawn (FMEA §6a, recorded as §6c).** `HighBiasSelv` and its CA-IS3720LW go. U44 is an
       ISO6721FBDR `HighBiasLink` like U43 (C159 / C160 its caps), carrying HS-B's verdict (MON_GOOD_HB) to the LS
       domain. D20 (BAT54S, MID -> K2 half) ANDs it into the LS good node beside D18. R135 (10 k) holds U46's HSB_GOOD
       input at v3v3, so U46 is the buffer only. One reinforced HOT -> SELV crossing fewer.
    2. **C168, 100 nF v3v3 / selv_gnd, transfer cap for pwm_hb's via at (34.4, 110.6).** The removed isolator's SELV
       decoupler served it at 2.0 mm; without a replacement the change measured 16.5 mm and failed the asserted
       `return_path19` limit.
    3. **30b: C161's own via (0.42 mm) lands in the In1 n_ls LS-block plane.** `bypass_check.py` counts only vias that
       land in a filled pour of the net on a non-F layer; U45's 6.0 mm exception is retired (3.0 mm, as every other row).
       Under the new rule s38 fails U45 at 5.97 mm.

    **Layout:**
    4. **U44 at (3.25, 47.25, 270) in U42's pocket**, the only legal straddling pose (`spot_scan.py`). U42 (RECOM
       R24C2T25) keeps its part and pose.
    5. **The vote moves beside U43.** No legal via exists at x 56-125, y 44-51, and the LS In1 corridor is full, so
       MON_GOOD_HB could not reach the LS block. D18 and D20 sit beside U43; the GOOD node takes MON_GOOD_HA's old
       corridor lane. One corridor trace now carries both HS vetoes (FMEA §6c; neutral under 19.11.2's component
       faults).
    6. **Return paths.** MON_GOOD_HA's four open changes close (F n_ls pour over an In1 n_ls patch, U41 heat-spread
       pours extended to x 46.35, which keeps 8 mm to SELV). The GOOD node is now counted and keeps one open change at
       U45.1 (104.4, 99.65), the only legal via spot in an In1 island.

    **Gates:** `return_path19.py` reports MON_GOOD_HB and the GOOD node; `bypass_check.py` plane-landing rule and ISO6721
    U44 rows; ledger: CA-IS3720LW removed, U44 on the ISO6721FBDR row, D20 / R135 / C168 on existing rows.

    **Not done:** the other 14 return-path opens (SELV / Kelvin nets outside HS-B / LS). The QUEUE's -$1.93 is not
    reached: the card shows -$0.03 at 500.

    **Reverses if:**
    - the certifier wants HS-B's verdict on its own SELV crossing (the stage 30 §6b arrangement) rather than voted in the
      LS domain;
    - a corridor fault that silences both HS vetoes at once is judged credible beyond 19.11.2's component faults (then
      the vote returns to the LS block and MON_GOOD_HB needs an In2 route, which the s38 copper does not have);
    - the B3 tolerance on the FET row (0.2-0.4 K worse here) becomes binding once candidate 36 lands.
