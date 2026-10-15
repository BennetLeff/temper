57. **Stage 43 (candidate 43): DECISIONS 48 cleanup pass on s42, snubber source MPN fixed, ledger re-cited to s43
    (2026-10-15; board of record s43, 61447816). Card ACCEPT against s42.** Records: `11-candidates/c43-cleanup/README.md`.
    - **Cleanup:** `track_cleanup21.py` (unchanged) on s42's copper and export: 621 edits on 100 nets; nothing excluded.
      - Right angles 100 → 49, acute 199 → 23, fold-backs 43 → 3, any-angle 675.0 → 272.6 mm; track −97.3 mm.
      - Deterministic (copper `e5f7f90e`); a second run on the s43 export makes 0 edits.
      - Gate networks: no spacing fell, every gate loop is shorter (−2.6 to −4.9 mm).
      - Fuse necks are identical; Kelvin, OCP pickup and the spine lock are unchanged.
    - **Chain CHAIN_DONE, no spine owner:** DRC 0 / 0 (s42 warning set); barrier 0; RES_A 13.375; D5 8.047 / 8.507; DFM 753
      vias; FIT clean; task 04 39 / 0 (hv_dc −0.011 %, res_a +0.043 %). TP3 / TP4 / TP7 (refs TP26 / TP29) move 0.5–1.0 mm.
    - **B3:** release margin +0.7 → **+1.2 K** (worst row now C40; R10 +3.1 K); laminate ratchet −30.7 → −30.2 K;
      rated-part −33.4 → −32.3 K; `b3_ratings` PASS. Heat inputs are unchanged: the R_on rows gain 1–4 K from copper alone,
      and R53 / R54 lose up to 0.7 K.
    - **Source:** C12 / C13 / C19 / C20 GRM31A5C3A102JW01D (no such Murata part) → YAGEO CC1206JKNPOCBN102, the C113872
      the order already placed.
      - Same 1206 footprint, nets and designators. atopile 0.2.69 offline, refrozen.
      - `audit.rs` IDENTITY plus `stage43_snubber_mpn_holds` (85 / 85); `verify_source.py` asserts it.
      - The BOM line is plain JLC Extended (`apply_lcsc.py`; STOCK addendum s43 and snapshot s43 re-key the existing rows).
    - **Card:** better on 3 B3 margins and 4 geometry metrics. `jlc_extended_lines` 67 → 68 is a counting correction: the
      line was always Extended but labelled "JLC substitute". Price and stock are unchanged.
    - **Ledger 3 / 32 / 58 / 0, gate PASS:**
      - CC1206JKNPOCBN102 re-keyed and its source-MPN gap closed.
      - GRM1885C1H472JA01D re-cited to the c18 release case (FET row 122.1 °C ≤ 125 °C); the c22 overrun (132.6 °C) is an
        `owner: airflow route (c22/c28)` gap.
      - Every margins.json citation follows the s43 rows. The c22 worst R_on is now R12 (136.1 °C, 0.976 of the derated
        power).
    - **Decision:** adopt s43 as the board of record. The OPEN-ITEMS B5 cleanup is done on the merged copper. Later lanes
      re-run the pass after they merge (it is idempotent).
