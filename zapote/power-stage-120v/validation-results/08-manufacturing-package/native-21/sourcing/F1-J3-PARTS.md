# F1 fuse clips and J3 TCO connector: part research (2026-10-08, review M7 / M8)

Ratings are from manufacturer datasheets (some read through distributor mirrors, because the
makers' sites refused automated fetches). [UNVERIFIED] marks a distributor figure or an estimate.

## F1: 6.3 × 32 mm clips for the 20 A 0326020.MXP

- Present footprint `Fuseholder_Clip-6.3x32mm_Littelfuse_102071`. Littelfuse **102071** clip:
  **10 A** max (520/521/102071 datasheet rev 02/16/15 p.1). Littelfuse **01020071Z**: **15 A** max
  (102/122 datasheet rev 06/26/18 p.1). Both are below the 14–16.5 A RMS line current, and neither
  was in the BOM.
- **Chosen: 2 × Littelfuse 01220088Z** (122 series, BeCu tin-plated, with ears): **30 A** max, UL
  E14721, listed for 326-series fuses (rev 06/26/18 p.1). Pattern 34.21 mm outer to outer, 7.62 mm
  per clip, Ø1.98 holes, which is KiCad stock
  `Fuse:Fuseholder_Clip-6.3x32mm_Littelfuse_102_122_Inline_P34.21x7.62mm_D1.98mm_Horizontal`.
  Alternate 01220083Z (silver-plated). Not stocked at JLC: buy from a distributor, hand-solder.
- **Fuse re-sized to 0326025.MXP (25 A).** The 325/326 datasheet (rev 04/29/19, p.3): "Rerating
  depicted in this curve is in addition to the standard derating of 25% for continuous operation";
  the curve reads ~100 % at 25 °C, ~97 % at 50 °C (read off the plot). 20 A × 0.75 × 0.97 ≈
  14.5 A continuous, below the 14–16.5 A RMS line current; 25 A gives ≈ 18.2 A. The p.2 table lists
  025. at 250 V, 400 A @ 250 Vac, the same marks as 020. (one distributor lists 1500 A, which is
  the table's "W" high-I²t variant). Downstream: CMC 20 A, terminal 24 A IEC, BR1 25 A all carry
  16.5 A; the branch breaker covers wiring overload. No LCSC listing; the cartridge is inserted by
  hand into the clips.
- **OPEN: breaking capacity at 125 Vac.** The p.2 table gives 020 "400A@250Vac, 10KA@125Vac,
  600A@125Vdc", but 025 / 030 only "400A@250Vac, 10KA@60Vdc, 600A@125Vdc": the 25 A part has no
  125 Vac figure, so 400 A applies, and a 120 V branch outlet can deliver more (flagged by the
  enclosure session, R20 DECISIONS M5). The 20 A part keeps 10 kA but carries only ~14.5 A
  continuous. Candidate: Eaton Bussmann **MDA-25-R** (6.3 × 32 ceramic time-delay, UL 248-14):
  distributors list 1.5 kA @ 250 Vac and some 10 kA @ 125 Vac [UNVERIFIED: Eaton's datasheet
  (Technical Data 2002) refused automated fetches 2026-10-08]. Same clips, so a BOM-only change.
  Close by reading Eaton's sheet, or by asking Littelfuse for 0326025's 125 Vac rating.

## J3: TCO loop connector (line voltage across the pins when the TCO is open)

- Present JST B2P-VH: 3.96 mm pitch, **1.26 mm** copper gap.
- **Chosen: JST B2P3-VH(LF)(SN)** (unshrouded; the shrouded B2P3-VH-FB-B, LCSC C158009, has a 14.9 × 10.8 mm courtyard that does not fit between PS2 and F1). Same series and rating: This is JST's standard VH header with the even posts
  omitted (VH datasheet p.6 item 3①, p.3 note 2), 7.92 mm pitch, **250 V AC/DC, 10 A**, 1,500 VAC
  for 1 min, polarized and latching (VH datasheet p.1). (C158009 is the shrouded -FB-B, not this
  part.) Mates with **VHR-3M**
  (contact lances covered) with cavity 2 empty, and **SVH-21T-P1.1** / **SVH-41T-P1.1** crimps.
  Copper gap with 2.7 mm pads: **5.22 mm**. Footprint: KiCad stock `JST_VH_B2P3-VH_1x02_P7.92mm_Vertical`.
  No LCSC number found for the unshrouded part [UNVERIFIED]: buy from a distributor, hand-solder.
- Fallback: Phoenix GMSTBVA 2,5/2-G-7,62 (1766770) with GMSTB 2,5/2-ST-7,62 (1766990): 630 V /
  12 A, friction retention only.
