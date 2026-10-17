60. **Stage 45 (candidate 45): the S16 rail-monitor fix, option 1c-4420, BOM-only on s44 (2026-10-15; draft for the
    integrator). Board 26ce9531, copper identical to s44. Card REJECT against s44 on cost alone (+1 BOM / Extended line).**
    Records: `11-candidates/c45-s16-monitor/README.md` (chain CHAIN_DONE, no spine owner).
    - **Change (×3 rails):**
      - U17 / U19 / U21 TL431AIDBZR → TL431BIDBZR;
      - R79 / R97 / R112 10 k → 4.42 k;
      - taps: neg UV 750 / 10 k, neg OV 2.94 k / 10 k, span UV 90.9 k / 11 k, span OV 104 k / 11 k;
      - same pads; `default.net` byte-identical; 24 instances change MPN.
    - **Bands** (re-derived from the frozen values with the S16 model; the 1c-4420 table reproduced to 1e-4):
      - span UV release ≤ 16.479 V against the 16.575 V rail minimum: **−0.229 → +0.096 V**;
      - span OV trip ≥ 17.569 V against the 17.425 V rail maximum: **−0.233 → +0.144 V**;
      - RSS +0.310 / +0.382 V; joint 6.0σ / 6.4σ (was 4.6σ / 4.7σ);
      - neg UV catch −0.015 → +0.060 V.
    - **Corners:** span-OV upper 18.60 V. That is inside the 19 V hot-load re-run (+0.40 V), and the 2EDR8259X VDD ratio is
      0.886 of 21 V. Span UV lower 15.569 V, MARGINAL (+0.069 V against 15.5 V).
    - **Card:** every gate and performance metric equals s44.
      - Cost: lines 93 → 94, Extended 68 → 69.
      - parts $202.38 → $201.60 is an estimate-basis artefact: on like-for-like JLC 2026-10-15 ladders the change is
        **+$0.181 / board**.
      - ACCEPT against s43 / s42; REJECT against s41 on the laminate ratchet (DECISIONS 55).
    - **Proposed: adopt with a cost override, as for S16 correctness.** The card has no metric for monitor tolerance.
      Buy RT0603BRD07750RL early (2,661 at JLC against 1,500 needed).
    - **Gates tightened:** `audit.rs` IDENTITY + `stage45_rail_monitor_values_hold` (87 / 87); `verify_source.py` values;
      ledger 3 / 37 / 54 / 0 of 94. **Open:** FMEA C1–C7 on s45; B3 probe rows at the monitors; JLC preview U17 / U19 / U21.
    - **Reverses if:** the islands are re-laid anyway (then amended candidate B, DECISIONS 59).
