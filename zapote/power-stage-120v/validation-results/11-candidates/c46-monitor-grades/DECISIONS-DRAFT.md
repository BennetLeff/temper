62. **Stage 46 (candidate 46): rail-monitor ICs on 125 °C grades, BOM-only on s45 hot copper (2026-10-15; draft for the
    integrator). Board 7bfe8b76, copper identical to s45. Card REJECT against the (cold-copper) s45 card on B3 only.**
    Records: `11-candidates/c46-monitor-grades/README.md` (chain CHAIN_DONE, no spine owner).
    - **Change:** U17 / U19 / U21 TL431BIDBZR → **TL431BQDBZR** (C190245, 17,789 stock); U29–U31 LM339BIDR →
      **LM2901BIDR** (C22427890, **1,966** against 1,500: buy early). Same pads and pinouts; 6 instances; +$0.12 / board.
    - **U5 stays LM4040A25IDBZR:** no A-grade Q part exists. The C25Q (133 stock) would raise the OVP upper corner by
      2.16 V and cut the OCP floor margin to +3.0 A (+0.46 A at 105 °C).
    - **B3, hot copper:** monitor rows now clear 125 °C (worst U29 +22.1 K at c18 @ 61, +19.0 K at c28). Release margin
      −17.9 K (s45 hot) → **−0.7 K**, now bound by R10 2512 terminal derating. The `b3_ratings` gate stays FAIL on copper
      rows (laminate −51.1, rated part −51.3), the same as s45 on hot copper.
    - **Bands on the 125 °C basis** (divider values unchanged, controls reproduce s45 and the study to 1e-4):
      - rail margins WC: neg UV +0.060, neg OV +0.105, span UV **+0.057** (was +0.096), span OV +0.102 V;
      - span UV H catch MARGINAL (rail side under the 0.080 V target); span OV corner 18.643 V, +0.357 V under 19 V;
      - 2EDR8259X VDD 0.888 of 21 V.
    - **Ledger:** LM2901BIDR PARTIAL (was UNAUDITED LM339BIDR); 3 / 38 / 53 / 0 of 94. The hot-copper merge had left 30
      stale B3 citations in 10 entries; refreshed (`ledger_b3_refresh46.py`; applies to s45 too). The C0G caps' release
      check moved from the 126.1 °C FET-row bound to their own pad estimates (116.7 / 120.3 °C).
    - **Proposed: adopt.** It removes the monitor islands from the release failure at a cost of $0.12 per board. The card
      cannot see this, because its benchmark predates hot copper.
    - **Open:** the release (R10 / R20 / R12 copper rows) is the tank-ceiling decision; FMEA C1–C7; JLC preview of the 6
      CPL lines; B3 gate advisory MON_R still uses the s42 dividers.
    - **Reverses if:** LM2901BIDR stock cannot cover the build (fallback LM339BIDR with the 85 °C rows failing).
