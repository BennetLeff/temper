# DECISIONS draft, candidate 39 (number set on integration; next free is 55)

55. **Stage 42 (candidate 39): the DECISIONS 54 gate network, built on s41 (2026-10-15; draft). Adopt over the card's
    laminate REJECT. The regression is the network's own heat, which item 54 accepted, and the still-air ceiling becomes
    20.0 A at bay 55 °C / 18.3 A at bay 61 °C.** Records: `validation-results/11-candidates/c39-gate-network/README.md`.
    Board native21s42 `9e075b4b`, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS).
    - **Scorecard against s41: REJECT on `b3_laminate_margin_K` only** (−25.2 → −30.6 K, tolerance 1.0).
      - Better: `b3_rated_part_margin_K` −64.1 → −33.4 K. Every other gate and performance metric is unchanged:
        - DRC 0 / 0, barrier, RES_A 13.375 mm, D5 8.047 / 8.507 mm;
        - Kelvin 67.77–116.44 A, OCP pickup 4.17 A, fuse-copper 0.993;
        - task 04 39 / 0, return path 15, EMI, touch, CMTI.
      - Cost: +$0.14 / +$0.11 at 5 / 500 boards, one more BOM line (93), 753 vias (−1).
    - **Built:**
      - R10 / R12 / R18 / R20 → UniRoyal 25121WF680JT4E, 68 Ω 1 W 2512 (C50371), turned 180° on the same axis, centre
        y 12.4.
      - C55 / C56 / C62 / C63 → Murata GRM1885C1H472JA01D, 4.7 nF C0G 0603 (C85980).
      - Gate runs re-laid locally (`patches21.edit_base42`): gate down x g − 2.15 into pad 2; OUT under the body to pad 1.
      - Pull-downs 0.5 mm west and north. R11 is turned 180° with its sw_a via at (59.6, 13.3), which keeps the leg-A
        In1 fuse neck at 3.88 mm (2.87 on s41). The first build's via at (59.4, 9.7) cut it to 2.42 mm, ratio 0.882.
      - R10's redundant sw_a stub via is removed.
    - **Why the laminate moved** (s42 copper with the s41 heat file, `scripts/heat_swap.sh`):
      - The copper alone is neutral to better: FET row c28 −25.2 → −22.8 K, c22 block +1.2 → +4.3 K.
      - The network's +0.68 W (c28 basis: R_on 0.140 → 0.217 W ×4, R_off 0.036 → 0.063 W ×4, RECOM / U26 / PS2 +16 %
        charge) costs c28 −4.1 / −7.8 K (block / FET row) and c22 −11.1 K (block).
      - At c22 the hottest laminate is now R12's own gate pad.
      - No copper change on this candidate recovers it. The levers are listed below.
    - **B3 rows, s41 → s42 (bay 55 °C):**

      | | c22 | c28 |
      |---|---|---|
      | Laminate, 1 mm block | +1.2 → −6.8 K | −25.1 → −30.6 K |
      | Laminate, FET row | +1.1 → −3.5 K | −25.2 → −30.6 K |
      | C40 | −2.7 → −6.0 K | −24.6 → −27.8 K |
      | R_on terminal derating (worst) | −39.6 (1206) → −6.2 K (2512) | −64.1 → −33.4 K |
      | R_off R58 terminal derating | +19.4 → +1.8 K | −7.7 → −25.4 K |

    - **Still-air ceilings** (c36's I_trip² method, `scripts/ceilings.py`):
      - bay 55 °C: all gated rows **0.0 → 20.0 A** (laminate block, R10 derating). On s41 the 1206 gate resistors failed
        with no tank current. Laminate + film 21.1 → 20.0 A.
      - bay 61 °C, solved at 61 (not shifted): **18.3 A** (R10 derating), laminate + film 18.4 A.
      - So the commissioned still-air ceiling, still open with the owner since items 46 / 51 / 53 (≤ 18 A requested), is
        **≤ 20.0 A at bay 55 °C and ≤ 18.3 A at bay 61 °C** on this board. The 22 A c22 point is no longer supported in
        still air.
    - **Datasheet ledger (3 / 31 / 58 / 1):**
      - IPW65R018CFD7 VIOLATION → PARTIAL. S4 meets 70 V/ns and 1,300 A/µs at typical Qrr (49.7 V/ns, 244 A/µs). The
        maximum-Qrr basis stays open for the D-8 bench.
      - **25121WF680JT4E is the one VIOLATION:** at c22 its terminal (138.1 °C) allows 0.199 W, and 0.217 W is 109 %
        against the 80 % rule. It clears at the ≤ 20 A ceiling above or with airflow.
      - GRM1885C1H472JA01D is PARTIAL: its temperature is bounded only by the FET-row copper.
    - **Decision: adopt s42 as board of record; the laminate REJECT is overridden.** The S4 per-edge diode limits are a
      device-ruggedness case that item 54 made the binding one, and the thermal cost is item 54's own heat, measured here.
      Holding s41 keeps an S4 overrun of 1.6× diF/dt and a gate resistor that fails with no tank current.
    - **Open (not built):**
      - local spreading copper on the R_on pads (both nets are low-voltage to their own potential group);
      - airflow over the FET row;
      - the R_on power basis: charge split 0.217 W against the study's simulated ~0.17 W, to be settled by a gate-row IR
        reading on the bench;
      - the D-8 double-pulse bench for maximum Qrr;
      - the hardware capacitive-mode detector (`CONTROLLER-REQUEST.md`, requirement only).
    - **Release condition:** unchanged from items 46 / 51 / 53. The B3 gate still fails on c28 everywhere and, at c22, on
      the laminate, C40 and the R_on derating rows. The commissioned ceiling decision above is what closes c22.
