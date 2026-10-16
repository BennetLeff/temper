70. **Stage 49 (candidate 49): fit the c34 resonant bank, 5 × TDK B32643B8104J000 (2000 V, P22.5), and re-ratio the
    OCP divider to S23's B'-1.02 V (R33 7.5 k, R34 16 k, R35 11 k) (2026-10-16; draft for the integrator). Board 73702f18
    (copper key f704213432bf). Card ACCEPT against s48; every gate passes; D5, RES_A outer and return-path opens equal
    s48.**
    Records: `11-candidates/c49-c34-bank/README.md` (chain `runs-native21/s49/chain2.out`, CHAIN_DONE, `SPINE_OWNER=selv`).
    - **Bank (DECISIONS 68).** C21-C23 / C151 / C152 → B32643B8104J000, from TDK B3264*B (June 2026):
      - 2000 V DC / 500 V AC and 14.5 × 29.5 × 26.5 mm (p.11); e 22.5 mm (p.2);
      - Top,max 125 °C case (p.2, p.12); IRMS 8.3 A for ΔT ≤ 15 K (p.11 note 8); dV/dt 3800 V/µs (p.13);
      - a HOT-side tank part; no safety approval is needed.
      - Rows y 53.2-113.2 at 15.0 mm pitch, RES_A x 163.0, SW_B x 185.5. sw_b / res_a B.Cu strips re-cut.
      - **line_zc_raw (SELV)**: the run at y 121.27 moves to y 122.75, and the y 127.5 run dips to y 128.2 over
        x 157.7-171.3. These hold D5 HOT-SELV at 8.047 mm and RES_A outer at 13.375 mm; c34's 122.55 alone gave 8.025 /
        12.775 mm.
      - Pad 1 is round (a square corner came 8.035 mm from the In1 v3v3 plane).
      - The column spans y 45.95-120.45, a little over the y 46-119 air box: 5 courtyards at 15 mm pitch need it.
    - **F3 closes.** F3 scales with the OCP top: 1,683 V × top / 118.74 A gives 1,624-1,693 V over the R0 / R1 readings.
      That is ≤ 0.847 × 2000 V (rule 0.85; `audit.rs` S49_BANK_VR). The CT-failed double fault Z0,max × top is 1,461-1,523 V
      (R0 / R1), ≥ +393 V to 2000 V on every reading including R4. No-pan 775 V against VC(125 °C) 1000 V is the
      tightest row (0.775 / 0.8).
    - **Bank self-heating.** Vendor curve 0.831 / 0.816 (35 / 40 kHz). **`bank_air_ratio_28A_35k` 1.308 → 0.967**, now from
      B3 jetmix cases `c28_h20_jet100@61` / `c28_h15_jet100@55` solved on this board in the chain. The worst point is an
      interior cap under the design flow at 61 °C: ΔT 14.04 / 15 K, T_op 88.9 / 125 °C. B3 bank bodies (film_mmkp,
      ESR 8 mΩ): release 82.8 °C, c28 still air 106.2 °C (fitted bank: 90.4 / 126.0 °C against 110 °C). S25's pre-lot bench
      gate stays, with the c34 limits (ΔT ≤ 15 K, T_A + ΔT ≤ 125 °C).
    - **S23 B'-1.02 V** (BOM only, same 0603 pads): R33 RT0603BRD077K5L (C728597), R34 RT0603BRD0716KL (C326732), R35
      RT0603BRD0711KL (C728581, an existing line). R32 is unchanged.
      - Nominal trip 92.593 A, U6 VCM 1.204 → 1.0185 V, 1.75 A/mV.
      - On this board's solve: release R0 71.59-114.58 A, low after Kelvin 69.18 A (+5.01); R1 66.54 (+2.37). c28: R0
        68.09 (+3.92), R1 65.46 (+1.29).
      - `kelvin_band_low_A` 66.46 → 69.18. OVP is unchanged (top 287.47 / 287.62 V).
      - C30 τ 429 ns ≤ 500 ns; REF25 minimum current 98.8 µA > 65 µA; the H1 watchdog window 2.526-2.610 V stays below
        U5-open REF25 2.816 V. All are in `audit.rs`.
    - **S23 closes with the bench run at the new VCM** (Option C, s23-ocp-cm results.md section 4): n = 30 TLV3201AIDBVR,
      Δ = Vtrip,fall(1.0185 V) − Vtrip,fall(VCC/2) at ≥ 105 °C. The pass limit is 2.164 mV at c28 Q1 (1.953 mV in the physical
      HOT5 window), with k = 3.064. The spec-literal R4 reading still fails (−4.25 / −5.30 A); B' turns the bench run from a
      0.3 mV knife edge into a 2.2 mV window.
    - **Pre-order note (owner):**
      - B32643B8104J000: JLC C3781430 shows 0 stock; untaped MOQ 2080, 28 weeks. 2,500 + attrition for 500 boards, consigned.
      - TLV3201AIDBVR: JLC C105188 shows 3,221 (2026-10-16) against 2,500 needed across U6, U7, U10, U11, U12. Order with
        the bank, or confirm stock at kitting.
    - **Cost.** The card reads −$6.19 / board at 500 (175.68 → 169.49). That compares a DigiKey price for the old bank
      ($1.48848) with JLC's catalogue ladder for the new one ($0.248, listed with no stock). On one channel it is −$1.37
      (JLC) or −$0.90 (DigiKey $1.30931 at MOQ 2080). The new resistors are cents. Decision: accept the card's pricing
      as computed (it is the committed bom_pricing-v1 rule), and record the same-channel figures. The ACCEPT also stands
      on its seven performance gains alone.
    - **Records corrected:** `kelvin_budget.BAND_BEFORE["native21s48"]` carries the s47 solve (68.87-117.45 A). s48's own
      solve gives 68.63-117.70 A. It is left as committed, and the s49 entry is this board's own solve
      (`bands49.py --check`).
    - **For the integrator:** re-base the S21 temp-ratings rows on s49 (TNPW060311K7BEEA is R145 only; R35 joins
      RT0603BRD0711KL; R33 leaves RT0603BRD0710KL; the two new lines carry bands-s49 pad temperatures).
    - **Reverses if:** the S23 bench Δ at 1.0185 V fails at ≥ 105 °C (then fall back to the as-built divider and the
      17.5 A ceiling), or c34 cannot be sourced (DECISIONS 68's own condition).
