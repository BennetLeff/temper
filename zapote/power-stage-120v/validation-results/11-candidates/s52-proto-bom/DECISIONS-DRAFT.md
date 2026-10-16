74. **Stage 52 (s52-proto-bom): the prototype BOM. The bank is TDK B32643H8104J000 in the dual-pitch footprint's
    22.5 mm hole, L1 is TDK B82726S2243A020, and C3 / C4 are Murata DE1E3RA222MJ4BH01F; a silk bank-variant fit mark is
    added (2026-10-16; draft for the integrator). Board 32665572 (copper key 3a4c616e7870, no copper edit). Card REJECT
    against s51 on EMI (12.4 → 11.1 dB), on the 35 kHz vendor ratio (0.978 → 0.985) and on cost (+$5.27 / board at 500).
    `bom_lines_short_proto` goes 1 → 0, so this is a sourcing override. Every gate passes.**
    Record: `11-candidates/s52-proto-bom/README.md`. Chain `runs-native21/s52/chain3.out`, CHAIN_DONE.

    **Why.** The 20-board lot had one short line on the 2026-10-16 read: L1 B82726S2203A020, with 0 authorised stock and
    29 weeks lead (OPEN-ITEMS B15). The bank and the Y caps were chosen in the same pass, on parts that are in stock now:
    - bank: DigiKey 306 against 100;
    - L1 2243: Mouser 62 / DigiKey 29 against 20;
    - Y caps: JLC C7170908 104 against 40.

    **Prototype BOM.**
    - **Bank C21–C23 / C151 / C152 → TDK B32643H8104J000** (B3264*H June 2026, owner-supplied, sha256 69b56e62). It is
      100 nF ±5 %, 2000 V DC / 700 V AC, P22.5, in a 14.5 × 29.5 × 26.5 mm body, rated TR 105 °C with Top,max 125 °C,
      AEC-Q200D and a UL 94 V-0 case.
      - It sits in the existing 22.5 mm hole. The CPL centre follows the fitted part's hole (x 174.25). The 3D model is
        the TDK body.
      - KNSCHA MMK104J3DF1KN208G2 stays the in-stock fallback on the 27.5 mm hole. B32643B8104J000 stays the 28 A part
        on the 22.5 mm hole. Both are kept in the ledger `alternates`.
    - **L1 → B82726S2243A020** (same sheet, drawing and footprint): 24 A, 0.75 mH, Lstray 8 µH, 3.2 mΩ.
      - Copper loss is 1.44 W at 15 A (2203: 2.03 W).
      - The 80 % rule holds to 82.5 °C local air (2203: 67.7 °C).
      - **The production part stays B82726S2203A020** (owner pre-order).
    - **C3 / C4 → DE1E3RA222MJ4BH01F** (Type RA H01F): Y1 400 V (P01F 300 V), the same body, pads and certificates
      (E37921 / 40043033 / CQC16001138225), and J4 crimped leads.
      - S1 stays 0.2412 mA, margin 8.8 µA.
      - Creepage is unchanged (same pads).

    **The 24 A strict ceiling** (this board's pads; s51 KNSCHA: 22 A).
    - Vendor ratio 0.844 and strict gate 0.862 at 24 A. The vendor ratio reaches 0.85 at 24.17 A.
    - At 26 A the gate passes (0.934) but the 85 % rule does not (0.915).
    - At 28 A: bank_air strict **1.006** (s51 1.221), vendor 0.985 / 0.935 at 35 / 40 kHz.
    - Release in still air at 18.375 A: 0.871 with radiation, 1.133 without.
    - Voltage passes as c34 (2000 V):
      - F3 0.996 of 0.85 VR (+6.9 V);
      - no-pan 0.646;
      - dV/dt 0.091.
    - The commissioned ladder above 17.5 A stops at 24 A on this bank. The release is unchanged.

    **EMI deviation and the module requirement.**
    - The 2243's 8 µH stray loses the board DM pole with C2. On s19b with today's 2 × 41 µH module DM inductors the
      margins are 6.03 dB nominal and 1.57 dB worst: INCONCLUSIVE (the 70 kHz line).
    - With **≥ 100 µH DM per line at 21 A** in the inlet module they are 11.14 / 6.95 dB: PASS.
    - MODULE-REQUEST.md item 3 now asks for it. The card reads that design point. No part is selected yet.
    - If the prototype module cannot carry it, the lot runs as a recorded EMI deviation, and bench pre-compliance
      decides.
    - Production (2203) keeps 12.37 dB.

    **Bank-variant fit mark** (owner-approved; `plan_board_only21.py`).
    - On F.SilkS beside the bank column's foot: "BANK FIT, TICK ONE:", with tick boxes **H = B32643H8104J000 24 A MAX** and
      **B = B32643B8104J000 28 A**.
    - Text 1.0 mm (the existing note size), stroke 0.15 mm (JLC minimum).
    - Clearances: 0.65 mm from the C152 courtyard, 3.47 mm from the nearest mask opening, 1.0 mm from other silk. It is
      outside every courtyard, so it stays visible with the parts fitted.
    - silk_on_land 0. The DRC silk counts equal s51; they are capped at 199, so `bank_mark52.py` is the evidence.
    - **Commissioning rule:**
      - the fitted bank part is recorded per board;
      - **a board marked H, or with no mark, is never commissioned above 24 A**;
      - a B board's 26 / 28 A steps stay bench-gated per step, and the mark raises nothing;
      - a KNSCHA board stops at 22 A.
      - The rule is in COMMISSIONING.md and OPEN-ITEMS S28.

    **Stock basis.** Dated reads from 2026-10-16:
    - `STOCK-2026-10-16-bank-s52.csv`: the bank, DigiKey 306 at 18:35Z;
    - `STOCK-2026-10-16.csv`: L1 and the Y caps;
    - survey rows in `STOCK-2026-10-13-addendum-s52.csv`.
    - The bank has no JLC / LCSC listing, so it is consigned.
    - Prototype short lines: **0**.

    **Production notes (not this lot).**
    - The 500-board shortfall stays at 13 lines (information only).
    - Bank: DigiKey 306 against 2,500; TDK 28-week lead, MOQ 2080. Production is the KNSCHA fallback (22 A strict) or
      the 28 A route (S28).
    - L1 2243: 62 + 29 against 500. Production L1 is the 2203 pre-order (29 weeks).
    - Cost at 500: bank $6.83 against $1.52; L1 −$0.67; Y caps +$0.64. `parts_usd_at_500_v2` 169.77 → 175.04.

    **Reverses if:**
    - the S25 pre-lot gate fails on C22 (the hottest interior B32643H): the lot falls back to KNSCHA (22 A strict) on the
      27.5 mm hole;
    - the inlet module cannot carry ≥ 100 µH DM per line and bench pre-compliance fails with the 2243: fit the 2203 (owner
      pre-order) and wait for it;
    - B82726S2203A020 arrives before the lot is built: fit it (12.37 dB, no module requirement);
    - B32643B8104J000 is sourced, or an 11-body re-floorplan lands (S28): 28 A becomes possible on B-marked boards, after
      the bench gates;
    - DigiKey stock of B32643H8104J000 falls below 100 before purchase: fit KNSCHA.
