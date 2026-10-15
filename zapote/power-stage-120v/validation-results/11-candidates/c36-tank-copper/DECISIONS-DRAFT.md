# DECISIONS draft, candidate 36 (number set on integration; next free is 53)

53. **Stage 41 (candidate 36): tank / FET-row copper at R5, built on s40 (2026-10-15; draft). c22 laminate passes;
    C40 and c28 stay open on 2 oz outer copper; the 0.5 mΩ shunt is not adopted.** Records:
    `validation-results/11-candidates/c36-tank-copper/README.md`. Board native21s41 `d4b2445c`, chain CHAIN_DONE with no
    spine owner (SPINE_LOCK PASS). Scorecard ACCEPT against s40 (better `b3_laminate_margin_K` −38.3 → −25.2 K; nothing
    worse; parts, BOM, cost, vias identical).
    - **Built** (`patches21.edit_base41`, outlines `native-21/layout/stage41_pours.json` from `scripts/pours41.py`):
      1. F.Cu hv_ret spreader at R5.4: 86 mm², x 34.3–43, y 13.3–25.5, stopping 1.5 mm short of C40.2.
      2. F.Cu leg_ret from R5.1 east to Q3.1.
      3. New B.Cu leg_ret pour over R5.1's via field and Q6.3.
      4. The In1 leg-A neck under Q3.2 widened to y 14.7.
      5. Two of R5.4's six hv_ret vias moved north-west, so the sw_b B.Cu lane rises over R5. Its 4.4 mm pinch between
         R5.4 and C40.2 goes away.

      Nothing changes in the LS pocket, the HS-B band, the gate networks or the SELV side.
    - **B3 ratings rows, s40 → s41 (bay 55 °C):**

      | | c22 | c28 |
      |---|---|---|
      | Laminate, 1 mm block | −2.6 → **+1.2 K** | −38.3 → −25.1 K |
      | Laminate, FET row | −1.7 → **+1.1 K** | −28.2 → −25.2 K |
      | C40 | −3.2 → −2.7 K | −25.4 → −24.6 K |
      | C38 | −0.2 → +0.1 K | −22.5 → −22.2 K |
      | R5 terminal | +23.6 → +31.0 K | −20.8 → −9.1 K |

      Gate resistors (candidate 39): R12 derating −39.7 → −39.6 K at c22, −64.1 K at c28, unchanged; R12 element
      +15.7 → +18.3 K at c22.
    - **Still-air ceiling** (bay 55 °C; I_trip² interpolation between c22 and c28, which reproduces item 51's 21.5 /
      21.0 A on s38 and s40):
      - laminate 21.5 → **22.3 A**;
      - laminate + film 21.0 → **21.1 A** (C40 limits);
      - the gate-R derating row has no ceiling with 1206 parts.
      Bay 61 °C is not recomputed.
    - **Other metrics:**
      - Task 04: leg_a −15 % (1.72 → 1.46 mΩ); sw_b −1.2 %; hv_mixed +3.9 / +5.8 %, the cost of the via move, already
        in the rows above. bus_p span 2.835 %.
      - Fuse rows: hv_ret neck 3.10 → 2.89 mm, I²t 2492 → 2159 A²s against 1710; min ratio 0.993, unchanged.
      - Unchanged: Kelvin band 67.77–116.44 A, OCP pickup 4.17 A, D5 8.047 / 8.507 mm, RES_A 13.375 mm, return-path
        opens 15.
    - **Targets of item 51 not met:**
      - c22 C40 (−2.7 K);
      - every c28 laminate and film row (−25 K).

      Variants (pours only, extra vias) and what-ifs on the s40 base show that no 2 oz outer layout reaches them:
      - 3 oz outer copper would give c22 C40 +4.0 K and c28 laminate −9.6 K, but JLC offers 1 / 2 oz outer copper on
        multilayer boards only (capabilities page and copper-weight article, fetched 2026-10-15).
      - C40's rise is mostly the sw_b lane (11.9 K) and its own heat (3.85 K).
    - **0.5 mΩ shunt (CSS2H-2512R-L500F, same datasheet and footprint): not adopted.** It gives +0.9 K (c22 laminate),
      +2.3 K (C40) and +6.4 K (c28 laminate). But:
      - OCP pickup goes 4.17 → 8.35 A, over the 6.5 A gate;
      - with the same-trip divider the band low corner falls to 37.2 A, under the 64.17 A floor;
      - the floor-holding divider gives a 77–167 A band;
      - comparator Vos ±4 mV becomes ±16 A.

      It needs an OCP front-end rework. The controller-side constants for that case are in `CONTROLLER-REQUEST.md`.
      Today no controller constant reads R5.
    - **Release condition:** unchanged from items 46 / 51. The B3 gate still fails on R12 (candidate 39), on C40 at c22
      and on c28. The commissioned still-air ceiling request (≤ 18 A, or the measured ceiling once candidates 36 and 39
      land) stays with the owner. On this board, film and laminate alone would allow about 21 A at bay 55 °C.
    - **Reverses if:**
      - a 3 oz outer (or 6-layer with heavier outer) build is bought: re-run `scripts/basis_variant.py` with that
        stack-up;
      - the OCP front end is reworked for 0.5 mΩ;
      - the bench or FEM shows the hv_ret via move costs more than the body model's +4–6 % hv_mixed loss.
