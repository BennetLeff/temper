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

### Eaton browser verification, 2026-10-08 (supersedes the unverified MDA claim above)

Read the official [Eaton Technical Data 2002](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-mda-time-delay-ceramic-tube-fuses-data-sheet.pdf), effective November 2025, in Chrome's native PDF viewer using computer use. The in-app browser rendered a blank view; Chrome loaded all six pages. Evidence screenshots: [ratings](eaton-browser-2026-10-08/page2-ratings.jpg), [approvals](eaton-browser-2026-10-08/page1-approvals.jpg), [temperature curve](eaton-browser-2026-10-08/page4-derating.jpg).

| Exact cartridge | Interrupting rating, p.2 | Typical melting I²t, p.2 | Agency scope, p.1 |
| --- | --- | --- | --- |
| MDA-25-R (proposed F1) | 10,000 A at 125 Vac; 1,500 A at 250 Vac; 10,000 A at 125 Vdc | 734.7 A²s | cULus Recognized, JDYX2/JDYX8, file E19180 |
| MDA-20-R (comparison) | Same voltage-specific interrupting ratings | 483.5 A²s | cULus Listed, JDYX/JDYX7, file E19180 |

These are primary-source verified values. For these parts, p.2 footnote 4 measures melting I²t at the interrupting rating and rated voltage. It is **typical melting**, not guaranteed total clearing. Page 3 gives a cartridge length of 31.75 ±0.79 mm and diameter of 6.35 ±0.1 mm. Page 4 supplies Eaton's own temperature curve; the earlier Littelfuse curve is not evidence for Eaton's thermal carrying capability.

**Replacement disposition:** datasheet access is resolved, but MDA-25-R remains conditional. The 10 kA AC figure stops at 125 Vac. This appliance includes 127 V operation and higher line corners; do not extrapolate the figure to those conditions. Accept only after the prospective-fault-current requirement at maximum line is bounded against the applicable rating (or Eaton supplies an applicable higher-voltage guarantee), and the Recognized-component/clip conditions, thermal carrying and clearing coordination are checked. No source, BOM export or board swap was made by this verification.

**Adopted, 2026-10-08 (DECISIONS.md, stage-8 entry):** F1 is now MDA-25-R in the source and BOM.
- It dominates 0326025 at every line voltage: 1.5 kA vs 400 A up to 250 Vac, and 10 kA vs 400 A up to 125 Vac.
- Eaton's p.4 curve reads ~96 % at 50 °C and ~93 % at 70 °C; with a 25 % continuous margin that is about 18 A at 50 °C.
- The conditions above stay open on F1 rather than blocking the swap: the fault-current bound at 127 V / high line against 1.5 kA, the Recognized-component and clip acceptance, and coordination with the upstream fuse.

**127 V corner (enclosure session, R23 `evidence/fuse/fault_current_bound.py`):** the cord-limited prospective fault current at the inlet, from a zero-impedance source through a 14 AWG cord, is 4.26 kA (1.8 m) or 7.66 kA (1.0 m), under 10 kA. With a 15 m branch it is about 0.46 kA, under even the 1.5 kA figure. F1 sits downstream of that. What remains is a certifier confirmation that the 125 Vac rating covers the 127 V (+6 %) corner under the nominal-voltage rule; it is not a part change.

### Plug/current decision, 2026-10-08

The recorded 16.5 A RMS input envelope exceeds a 15 A plug. A 25 A internal fuse does not limit normal appliance current to 15 A. The existing 15 A product target requires a cap on **total appliance RMS mains current**, including auxiliaries, throughout the line/pan envelope and with sensing/control tolerance allowed for. A fixed watt cap alone is insufficient without minimum line and minimum power factor: `P_input <= V_min * PF_min * I_limit`; pan output must additionally allow for losses and auxiliary power. The existing 22 A tank-current ceiling is a separate requirement.

Alternatively, retaining 16.5 A requires a 20 A plug/cord assembly and compatible supply. [Leviton 5366-C](https://leviton.com/products/5366-c), read in the browser, verifies NEMA 5-20P, 20 A, 125 Vac. The owner was asked to choose between the current cap and the changed connection. **Owner's choice, 2026-10-08: option 1** (15 A plug, total input ≤ 15 A RMS), sensed by a firmware estimate (DECISIONS.md: I_ps,est ≤ 12.4 A provisional). F1 stays MDA-25-R.

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
