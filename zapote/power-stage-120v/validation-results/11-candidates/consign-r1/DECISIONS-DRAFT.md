# DECISIONS draft: consign-r1 assembly routes (owner, 2026-10-18)

Draft for the integration session to number and merge into `zapote/power-stage-120v/DECISIONS.md`. Proposed as one numbered
item with the sub-decisions below. Study: `README.md` (this folder). Applied on `study/consign-r1` to the order files through
the generator (`08-manufacturing-package/native-21/scripts/apply_lcsc.py`: ORDER_PLAN, ORDER_VARIANT; CONSIGN emptied), then
`cpl-rotation-audit/audit.py`, `fab/cpl-jlcpcb-order.csv`, `owner-items/order/scripts/proto_stock.py` and
`cpl_preview_checklist.py`; prose in `fab/FAB-NOTE.md`, `PROTOTYPE-LOT.md`, `owner-items/order/ORDER-PACKAGE.md`. The frozen
netlist and copper are unchanged (board `82af7bd93e62…`, copper key `b7a0bc5790b9`).

---

**NN. Prototype-lot assembly routes: JLC does as much as possible (consign-r1, owner 2026-10-18).**
Owner: "JLC to do as much as possible, and through-hole hand work is fine when it can't be avoided." The owner's bench is
through-hole only. Result: JLC assembles 92 of the 95 BOM lines (19 Basic, 73 Extended), every fitted THT part included; the
owner fits BR1, RV1, the F1 clips and the F1 cartridge. Stock at 20 boards: 0 short (`proto-stock-s52-20boards.csv`, dated read
`sourcing/STOCK-2026-10-18-consign-r1.csv`). JLC policy read verbatim (help pages updated 2026-09-09): Global Sourcing has no
batch promise and can cancel a part that "doesn't support assembly"; pre-order has no custom lot numbers; one MPN from different
sources can't be mixed in one order; parts must be in JLC's warehouse before the PCBA order.

- **D1. JLC Global Sourcing** for U41 / U42 (RECOM R24C2T25/R-R, JLC number C9900245652; the auto-match C22466894 "R24C2T25-R"
  is a different product and is rejected), the bank C21–C23 / C151 / C152 (TDK B32643H8104J000, private-library stock, no public
  number), C5 / C6 (C3802167), L1 (C7084710), D3 / D17 (Good-Ark 30KPA150CA; no LCSC number, so JLC's Littelfuse-branded
  C19111562 is not matched), F2 (C3163739), J2 / J5 (C6708126), and J6 (C5481600) if JLC lists a supplier. Why: each has
  authorised-distributor stock ≥ need at 20 boards on 2026-10-18 and no JLC stock; JLC buying them removes the owner's
  distributor buys and the SMD hand-soldering of U41 / U42 the owner's bench can't do.
  **Reverses if** JLC cancels or can't source a line before the PCBA order: that line goes back to consign (the owner buys it
  from the named distributor and ships it), or, for J6, to Do Not Place and owner hand-solder.
- **D2. The FETs are consigned and JLC solders them.** Q2 / Q3 / Q5 / Q6 IPW65R018CFD7 come from the single 120-piece DigiKey
  lot (D-8 lot traceability): 84 shipped to JLC (80 placements + 4 spare), 36 kept for D-8 and rework. All 80 placements come
  from the consigned stock (JLC holds 6, and one MPN can't mix sources). Order remark: seat the package on the lead shoulders.
  **Reverses if** JLC refuses the consigned TO-247 row or the shoulder-seating remark: the owner hand-solders the FETs from the
  same lot (through-hole, preheated board).
- **D3. Pre-order reserve** for C1 / C2 (R463N410050N1K, C3299886, JLC 46 against 40), T1 (CST3015-200ED, C50132500, 64 against
  20) and U5 (LM4050AEM3-2.5/NOPB, C2156518, 50 against 20). Why: JLC's own stock covers the lot with thin margin; reserving
  stops another buyer emptying it before the order. **Reverses if** JLC stock falls below need before the reserve is placed:
  then Global Sourcing (C1 / C2: Newark 1,298) or, for T1 (no distributor listing), Coilcraft direct and consign.
- **D4. J3 / J11 are ordered as JST B2P3-VH-H(LF)(SN), C160900** (JLC 5,610), an order-file change only. JST eVH.pdf (sha
  d51e669c) p.4 model-number key, Header (Standard type): "Color: No indication…Natural (White), … H…Gray": the suffix is the
  housing colour; ratings unchanged. The natural part had 0 at JLC on 2026-10-18 (983 on 10-15). The source (`parts.ato`) and
  the frozen netlist keep B2P3-VH(LF)(SN); `apply_lcsc.py` ORDER_VARIANT does the swap. The ledger's gated entry stays on the
  frozen MPN (the gate keys on `frozen/default.csv`) and `alternates["B2P3-VH-H(LF)(SN)"]` records the ordered variant.
  **Reverses if** JLC restocks the natural part ≥ 40 at order (drop ORDER_VARIANT), or a later stage changes the source MPN (then
  re-key the main ledger entry and delete the alternate).
- **D5. JLC hand-solders J1 and C38–C41** (and every other fitted THT part: J3 / J11, J4, C1–C6, L1, PS2, R130, D3 / D17, the
  bank, the FETs). Why: owner preference; all are JLC stock or Global Sourcing. **Reverses if** JLC's quote refuses a THT line:
  that line becomes owner hand work on the preheated board.
- **D6. BR1 is Do Not Place at JLC; the owner fits it before mains.** BR1 is the only mains-to-bus path. With it out, PS2 runs
  from mains while the bus is fed from a bench DC supply, so nothing back-feeds PS2's output (bring-up with BR1 not fitted:
  `firmware/components/power/COMMISSIONING.md`, commission-s53, 2026-10-18). BOM line has no LCSC number, so JLC can't match it.
  **Reverses if** bring-up stops using a bench DC bus (first light from mains): then BR1 can go back to JLC (C526644, JLC
  1,579).
- **D7. RV1 and the two F1 clips stay with the owner** (through-hole, bottom preheat ≥ 100 °C). RV1: JLC's C1527834 package
  does not match our drawing (decision 2026-10-17); its BOM line now carries no LCSC number. Clips: not source components, so no
  BOM / CPL line (`fab/hand-assembly-extras.csv`). **Candidate (c), splitting the clips into BOM components so JLC solders them,
  is deferred:** a stage is not worth it now, since the owner needs a bottom preheater for BR1 anyway. **Reverses if** BR1 goes
  back to JLC (D6) and the owner would otherwise need no preheater: then (c) is worth a stage.
- **D8. U41 / U42 have no through-hole option and are JLC's (D1).** The study found no pin-compatible THT bias module; the
  JLC-stocked MGJ2 / R24P2 look-alikes are YLPTEC / EVISUN copies, not Murata / RECOM. No hot-air gear is needed on the owner's
  bench. **Reverses if** Global Sourcing can't supply R24C2T25/R-R: then the owner consigns the Mouser stock and JLC still
  places it (the owner can't hand-solder SSOP-36).
- **D9. S25 timing (open: decided here as a draft, for the integration session to confirm).** DECISIONS 76 made S25 (C22 bank
  temperature) a pre-build gate because the bank was consigned and outside the JLC order. With D1 the bank is in the PCBA order.
  Draft: S25 runs on the first JLC-built board before the rest of the lot is powered; if it fails, the owner reworks the lot to
  KNSCHA in the x 190.5 holes, which stay open for that (order remark), on a preheated board. **Reverses if** the rework of a
  2000 V film bank in 2 oz copper is judged unacceptable: then order the bank line Do Not Place and fit it after S25 (owner hand
  work), or build one board first.

Order remarks (all three order documents carry the same text): "Q2/Q3/Q5/Q6 (TO-247): seat the package on the lead shoulders,
not flush on the board. Trim every through-hole lead to 2.5 mm or less below the board bottom after soldering. The bank
C21–C23/C151/C152 goes in the 22.5 mm holes (pad 2 at x 185.5); leave the five x 190.5 holes open and unsoldered. BR1 is Do Not
Place: leave BR1, RV1 and the F1 clips unfitted. Tick H on the bank-fit silk mark."

Scorecard effect (for the re-score; computed from the new `fab/bom-jlcpcb.csv` with scorecard.py's `cost()` rules):
`jlc_extended_lines` 68 → 73, `hand_or_consign_lines` 19 → 18, `consign_lines` 8 → 5, `bom_lines_short_proto` 0 → 0;
`parts_usd_at_500_v2` 175.04 → 174.99 (J3 / J11 variant, `bom_pricing.py`).
