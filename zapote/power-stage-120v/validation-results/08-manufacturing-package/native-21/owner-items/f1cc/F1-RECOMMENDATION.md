# F1 for a 120–127 V~ nameplate: recommendation (native-21, 2026-10-08)

Read-only study. Nothing in the repo or on the board was edited. The board facts come from the stage-11 `section.kicad_pcb`, read with KiCad 10's Python (scripts `region.py`, `copper.py`, `zones.py` and `fit.py` are next to this file). Downloaded datasheets are in `dl/` (scratch only, not to be committed). `[UNVERIFIED]` marks a figure that did not come from a manufacturer document I read myself.

## 1. Decision

| Item | Today | Recommended |
|---|---|---|
| F1 fuse | Eaton MDA-25-R, 6.3 × 32 mm, 10 kA @ 125 Vac / 1.5 kA @ 250 Vac | **Littelfuse KLDR025** (order no. KLDR025.TXP, 10-pack): UL Class CC, 25 A time-delay, 600 Vac, **200 kA**, UL Listed. **Approved alternate: Eaton Bussmann LP-CC-25** (same class, same ratings). |
| F1 clips | 2 × Littelfuse 01220088Z (6.3 mm, 30 A), 34.21 × 7.62 mm pattern | **2 × Littelfuse 01250003H** (125 series, beryllium copper, tin-plated, **30 A max**, for 13/32 in / 10.3 mm midget-size fuses) |
| F1 footprint | KiCad stock `Fuseholder_Clip-6.3x32mm_Littelfuse_102_122_Inline_P34.21x7.62mm_D1.98mm_Horizontal` | **New custom footprint**: 4 slotted PTH, 41.76 mm outer span (§4). KiCad 10 ships no 10 × 38 clip footprint. |
| Board | — | **Small ECO**: F1 moves and grows, C1 moves 0.6 mm, two F.Cu pour outlines are redrawn, then refill and re-verify (§5). No other part moves. |
| Enclosure inlet fuse | MDA-30-R in a 6.3 × 32 holder | **Delete it** if nothing else is fed from the inlet ahead of J1. If the enclosure keeps one: **KLDR030 / LP-CC-30 in a Littelfuse 5710CC (057100CCL) Class CC panel holder**: Ø22.6 mm cutout plus 2 × Ø4.37 mm holes on 33.3 mm centres, 34.0 mm deep behind the panel, 19.3 mm in front (§6.1). |

**Why Class CC and not a footprint-keeping 6.3 × 32 part.** A Class CC fuse is a Listed branch-circuit fuse rated 200 kA at 600 Vac. That ends the "which interrupting rating applies at 127 V" question for UL, CSA and NOM alike (UL 248-4 is tri-national like 248-1), with about 24 × margin over the worst cord-limited bound (8.4 kA, §2). It is time-delay, as the brief asked, and every figure I use for it comes from a manufacturer sheet I read. The only 6.3 × 32 candidate I found with a high rating above 125 V, the Littelfuse 505, is fast-acting. Its data is unverified today because Littelfuse's PDF returned 403. It is kept as the fallback in §3.3, not the plan of record.

## 2. Requirement recap

- **Interrupting:** ≥ **8.4 kA** at a nominal 127 V, i.e. a rating at ≥ 127 Vac. A rating at 250 V or higher removes the nominal-voltage argument entirely.
  - The enclosure's updated cord-limited bound, with a 127 V + 10 % (≈ 140 V) source corner, is **4.7–8.4 kA** (1.8 m / 1.0 m 14 AWG cord, stiff source). It supersedes the 4.26–7.66 kA quoted in DECISIONS.
  - **The +10 % NOM supply tolerance is an assumption, not confirmed** (to be checked against NMX-J-098-ANCE / the NOM body). The recommendation does not depend on it: 200 kA covers any plausible value.
- **Continuous:** ≥ 15 A RMS at ≥ 50 °C internal ambient, after the maker's derating.
- **Pulses:** the board's own inrush and the line-to-line surge test must stay far below the fuse's melting I²t (§3.4).

## 3. Candidates

### 3.1 Comparison

| Part | Size / class | AC voltage, interrupting rating | Melting / clearing I²t | Speed | Agency | Source (what I read) |
|---|---|---|---|---|---|---|
| **Littelfuse KLDR025** | 10.3 × 38.1, Class CC (UL 248-4) | 600 V, **200,000 A rms sym.** (DC 300 V, 20 kA) | **226.0 / 1,710 A²s** | Time-delay, ≥ 12 s at 200 % | UL Listed E81895; CSA LR29862 | KLDR datasheet **Rev 092821** (© 2021): p.1 ratings; p.2 UL/CSA files; p.3 ordering KLDR025.TXP/.HXP; p.4 opening times (135 %: 60 min max; 200 %: 12 s min); p.5 I²t table; p.6 current-limiting table and temperature derating curve. Third-party mirror (chipdip) of the Littelfuse PDF. |
| **Eaton Bussmann LP-CC-25** | 10.3 × 38.1, Class CC | 600 V, **200,000 A** (300 Vdc, 20 kA) | Not on the sheet [UNVERIFIED] | Time-delay, 12 s at 200 % | UL Listed 248-4, Guide JDDZ, File E4273; CSA C22.2 No. 248.4, File 53787 | Bussmann Data Sheet 1023, form LP-CC, dated 10-2-02 (old, but the ratings match Eaton's current SKU text, which gives 200 kA @ 600 Vac and 20 kA @ 300 Vdc). p.1 let-through table: at 10 kA prospective, 25 A lets through **870 A** apparent RMS and 30 A lets through **1,000 A**. |
| Mersen ATDR25 | Class CC | 600 V, 200 kA | — | Time-delay | — | Distributor listings only [UNVERIFIED]. Second alternate once its datasheet is read. |
| Eaton Bussmann FNM-25 | 10 × 38 midget, supplemental | 250 V, **10 kAIC @ 250 Vac** | — | Time-delay | Not stated on the sheet [UNVERIFIED] | Eaton product specification sheet FNM-25 (© 2024), via a distributor. Fits the same clips. Adequate (10 kA > 8.4 kA) but with only 1.19 × margin, so not preferred. |
| Eaton Bussmann FNQ-25 / Littelfuse FLQ025 | Midget, supplemental, 500 V | 10 kA @ 500 Vac | — | Time-delay | — | Distributor listings [UNVERIFIED]. Fits the same clips; same 10 kA margin note as FNM. |
| **Littelfuse 0505025.MXP** | **6.3 × 32 (keeps the F1 footprint)** | **500 Vac/Vdc, 20 kA** (one listing says 30 kA) | Nominal melting **145 A²s** | **Fast-acting** | "Recognized to UL/CSA/NMX 248-1 and 248-14" (distributor text) | Littelfuse product page and distributor listings via search; the datasheet PDF returned 403 [all UNVERIFIED]. |
| Littelfuse 358 | 6.3 × 32, time-lag, 500 V | 1.5 kA | — | Time-lag | — | Search listing: about 3.15–10 A only [UNVERIFIED]. Fails on both current and interrupting rating. |
| Eaton MDA-25-R (today) | 6.3 × 32 | 10 kA @ 125 Vac, 1.5 kA @ 250 Vac | 734.7 typ. melting | Time-delay | cULus Recognized E19180 | Repo `sourcing/F1-J3-PARTS.md` (Eaton TD 2002, Nov 2025). Fails at 127 V nominal. |

**The 6.3 × 32 search, done first as asked.** Eaton's MDA/ABC and Littelfuse's 326/314 top out at 1.5 kA or below at 250 V. The Littelfuse 358 time-lag 500 V series is 1.5 kA and ≤ 10 A. The only 6.3 × 32 mm fuse at ≥ 25 A with ≥ 5 kA above 125 Vac that I found is the **Littelfuse 505 (fast-acting)**. No **time-delay** 6.3 × 32 mm 25 A fuse with ≥ 5 kA at 250 Vac turned up.

### 3.2 KLDR025 carrying capacity (p.6 curve, read off the plot)

The curve shows about 5 % downrating at 40 °C, **about 10 % at 50 °C**, about 13 % at 60 °C and about 18 % at 70 °C.

- With a 25 % continuous margin: 25 A × 0.75 × 0.90 = **16.9 A at 50 °C** (≥ 15 A). At 70 °C it is ≈ 15.4 A, so 70 °C is the practical limit.
- With the NEC 80 % convention: 25 × 0.8 × 0.90 = 18.0 A.
- A 20 A Class CC gives only 13.5–14.4 A. So **25 A is the right size**, the same conclusion as for the 326 and MDA parts.
- Dissipation at 15 A is roughly 1 W [estimate, UNVERIFIED]. Confirm in the temperature-rise test of the fuse in its clips.

### 3.3 Fallback: Littelfuse 0505025.MXP, if the ECO is blocked

Its listed 20 kA at 500 Vac covers any 127 V branch fault, and it drops into today's 01220088Z clips. The change would be BOM-only. Before adopting it:

1. Read the Littelfuse 505 datasheet in a browser, as was done for Eaton. Confirm the 025 interrupting rating, the agency marks for 025, the I²t and the derating.
2. Get the owner to accept a **fast-acting** fuse. §3.4 shows the inrush is about 1 % of its melting I²t, so time-delay is not electrically needed.
3. Have the lab accept a Recognized supplemental fuse, which is the same open question MDA-25-R has today.

### 3.4 Pulse check (my estimates, not datasheet values)

| Pulse | Basis | I²t | KLDR025 (226 A²s) | 505-25 (145 A²s) | MDA-25-R (735 A²s) |
|---|---|---|---|---|---|
| Plug-in at crest, bus film caps | 140 V × √2 into 5.4–8 µF (2 × B32656G0275J000 2.7 µF + X caps, assumed ≤ 1 µF each) through 2–10 µH (cord + CMC leakage, the repo's 9 µH sensitivity) | **0.24–0.99 A²s** (145–396 A peak, 13–28 µs) | ≤ 0.4 % | ≤ 0.7 % | ≤ 0.13 % |
| PS1/PS2 IRM-20 cold start | MEAN WELL typical inrush, order of 1 A²s [UNVERIFIED] | ~1 A²s | < 1 % | < 1 % | < 1 % |
| Surge through RV1 (line-to-line, after F1) | IEC 61000-4-5 8/20 µs at 1 kA peak (2 kV/2 Ω, the severe case; 1 kV L-L gives 0.5 kA) | **12.2 A²s** at 1 kA; 3.0 A²s at 0.5 kA | 5.4 % | 8.4 % | 1.7 % |

All are well under the usual few-pulse withstand of about 30–40 % of melting I²t. Surge withstand is the only place the Class CC is weaker than MDA-25-R. It still passes with margin, and no pulse case forces a time-delay part.

## 4. Clips and footprint

### 4.1 Clip choice

| Clip | Rating | Pattern (maker's drawing) | Verdict |
|---|---|---|---|
| **Littelfuse 01250003H** (125 series) | **30 A max**, beryllium copper, tin-plated, ear style, for 13/32 in midget-size fuses. Voltage: 250 V per the Littelfuse product page [UNVERIFIED, not on the PDF]. Agency: the PDF shows E14721 for the 105/125 columns ambiguously, with "N/A" for 106 [UNVERIFIED for 125]. LCSC C223911 (stock not checked). | Littelfuse "105/106/125 Series" datasheet, **Revised 02/07/18** (LCSC copy; a 03/12/13 copy agrees). Recommended mounting: per clip, 2 slots **Ø1.20 × 2.5** at **10.80** mm, outer span **41.76** mm. Ear 0.70 × 2.00, pin length 3.60. Body 11.10 along the axis × 12.50 across, height **18.50** above the seat. | **Chosen.** It matches the 30 A clip rating already accepted for 01220088Z, and has the smallest courtyard. |
| Schurter CSO 0751.0507 (THT, tinned) / 0751.0505 (silver) | **32 A, 1500 Vac/Vdc**, UL File E39328, designed to UL 4248-1 / CSA C22.2 No. 4248.1 | Schurter CSO datasheet dated 08.05.2017 (Farnell copy): pins Ø2.35 at 15 mm pitch, 4 in line, **45 mm** total, clip centres 30 mm, centre Ø3.4 hole. Clip 12 × 13.8 mm, **24.8 mm** tall. | **Alternate**, if the lab wants a clip with a clear voltage rating and agency file. Courtyard is about 50 × 14.8 mm and 6 mm taller; it overlaps R1 and C1 more, and its RV1 gap is 0.95 mm. |
| Bussmann 1A3400-09 | **20 A max** for 13/32 in, spring bronze | Bussmann PCB clip sheet (SB04208, 6-30-04): A = 1.625 in (41.28 mm) for 1½ in fuses, tabs 0.405 in, holes 2.31–2.41 mm, for 3.18 mm board | **Rejected**: under 25 A. |
| Littelfuse 01000056Z (named in the brief) | 5 × 20 mm clip, 10 A, 250 V | Distributor listings | **Wrong part**: not a 10 × 38 clip. |
| Littelfuse 01060001Z (106 series) | 15 A (2018) / 20 A (2013) | same sheet | Rejected: current too low. |
| Littelfuse 124 series (01240041H THT) | 63 A, 10 × 38 | Datasheet 403; search summary only [UNVERIFIED] | Possible heavy-duty alternate once read. |

Class CC fuses fit midget (non-rejection) clips: the rejection feature only stops midget fuses from entering Class CC holders. Check that the rejection-tip end seats and is retained in a sample.

### 4.2 Footprint `Fuseholder_Clip-10.3x38mm_Littelfuse_125_Inline_P41.76x10.80mm_Slot1.2x2.5mm_Horizontal` (new, custom)

Origin at the fuse centre, X along the fuse axis.

| Element | Spec |
|---|---|
| Pads 1 (fuse end A, net ac_l_in) | 2 × PTH at x = +10.08 and +20.88, y = 0 |
| Pads 2 (fuse end B, net l_f) | 2 × PTH at x = −10.08 and −20.88, y = 0 |
| Hole | **oval slot 1.20 (X) × 2.50 (Y)**. The ear is 0.70 × 2.00, so the clearance is 0.25 mm per side. |
| Copper pad | oval **2.40 (X) × 3.70 (Y)**, both copper layers plus inner-layer flashing per stack rule. The 0.60 mm ring meets the PTH ≥ 0.254 mm DFM gate. |
| Fab outline | clip bodies 11.10 × 12.50 centred at x = ±15.48; fuse body 38.1 × 10.3 |
| Courtyard | **±22.6 (X) × ±6.75 (Y)**, i.e. 45.2 × 13.5 mm |
| Height (3D) | clip 18.5 mm above the board top. Fuse axis height not given [measure a sample]. |

**Recommended position: centre (252.00, 7.25), rotation 0.**

| Feature | Position |
|---|---|
| l_f pads | x 231.12 and 241.92 |
| ac_l_in pads | x 262.08 and 272.88, the end nearest J1 |
| Courtyard | x 229.40–274.60, y 0.50–14.00 |

## 5. Board fit check and ECO scope

### 5.1 The area today (stage 11)

| Part / copper | Position or extent |
|---|---|
| Edge.Cuts | y = 0 along the rear edge. Board 1.653 mm, 4 layers, copper-edge rule 0.5 mm. |
| F1 now | centre 244.5, 6.00. Pads at 227.40 / 235.01 (l_f) and 253.99 / 261.61 (ac_l_in). Courtyard 225.60–263.40 × 1.76–10.23. |
| J3 | courtyard right edge x = **223.00** (pads l_filt and tco_l) |
| J1 | courtyard left edge x = **277.87**. Pad 1 is ac_l_in (280.95, 7.50). |
| **Free span between J3 and J1** | **54.87 mm**, against 45.2 mm needed |
| C1 (X-cap) | courtyard **y ≥ 13.61** for x 235.96–263.05. Pad 1 l_f (238.25, 19.5); pad 2 ac_n_in (260.75, 19.5). |
| R1 | courtyard y ≥ 13.82, x 223.68–228.32 |
| RV1 | courtyard y ≥ 15.95, x ≥ 264.45. Pad 1 l_f at (276.5, 24.25). |
| L1 | courtyard y ≥ 28.45 |
| F.Cu pour ac_l_in | 251.5–283.0 × 0.6–8.9 |
| F.Cu pour l_f | top block 223.5–237.5 × 0.6–9.0; down-leg 229.5–240 to L1/C1; strip **240–279.5 × 12.1–15.1** across to the RV1 leg (273.5–279.5, down to 26.5) |
| Other layers | B.Cu: ac_n_in pour (239.5–289.4 × 3.5–40) and l_filt pour (to x 236). In1/In2: hv_ret and bus_p planes. |
| Rules | HOT↔HOT between potential groups **3.2 mm** (`section.kicad_dru`). ac_l_in and l_f are separate nets with no same-group exception, which is correct: the full line voltage appears across them once F1 opens. |

### 5.2 Results at (252.00, 7.25), from `fit.py`

| Check | Result |
|---|---|
| J3 | clear by 6.4 mm; l_f pad edge to J3 tco_l pad > 8 mm |
| J1 | courtyard gap 3.27 mm; ac_l_in is the same net |
| R1 | courtyard gap 1.08 mm |
| RV1 | courtyard gap 1.95 mm |
| **C1** | **courtyard overlap 0.39 mm** → move C1 |
| New pads vs every other-net pad and track | ≥ 5.4 mm (closest: R1 pad 2 xbleed_mid) |
| Clip envelope vs xbleed_mid track | 3.62 mm in plan; the clip flare is well above the board |
| Board edge | pad copper ≥ 5.4 mm from the edge; clip body 1.0 mm from the edge (today's clip: 1.78 mm) |

Centres x = 250 and 247.5 were also tried. Both overlap R1, and x = 250 brings the clip envelope 1.9 mm (in plan) from the xbleed_mid track. x = 252 is the best of those tried.

### 5.3 ECO list, in placement-engineer terms

1. **F1:** swap to the new footprint (§4.2), move from (261.605, 6.00, 180°) to **(252.00, 7.25, 0°)**, with pad 1 (ac_l_in) on the J1 side.
2. **C1: move +0.60 mm in y**, to (238.25, 20.10).
   - The courtyard clears F1 (14.21 vs 14.00) and L1 (gap 2.46 mm).
   - Pad 1 stays 3.4 mm from the B.Cu ac_n_in track at y = 25.0. A full 1.0 mm move would break that (3.0 mm < 3.2 mm) without a reroute, so **0.6 mm is the move**.
   - Pad 2 rises to 3.8 mm clear of the l_f strip.
3. **F.Cu ac_l_in pour:** redraw to about x 257–283 × 0.6–9.1, covering the new pads at 262.08 / 272.88 and J1 pad 1. Its left edge must stay ≥ 3.2 mm from the l_f pad at 241.92 (edge 243.12).
4. **F.Cu l_f pour:**
   - Extend the top block from x ≤ 237.5 to **x ≤ 243.5** to take the pad at 241.92.
   - Lower the top edge of the strip under the ac_l_in clip from 12.1 to **≥ 12.3** (3.2 mm from the pad edge at y 9.10), for x ≈ 257.6–277.6.
   - The strip may widen downwards to 15.7 now that C1 has moved.
5. **Refill all zones**:
   - The B.Cu ac_n_in pour gains a 3.2 mm antipad around the l_f pad at 241.92.
   - In1 (hv_ret) and In2 (bus_p) gain antipads at the four new holes.
6. **Re-verify** with the repo's normal gates: DRC/barrier (HOT 3.2 / 8 mm), JLC DFM (slotted PTH: order note), copper parity, BOM regeneration, plus `verify_source` and audit after the atopile change (F1 MPN, footprint, F1-CLIP line → 01250003H).

**One open item, which needs the clip's 3D shape.** The strip under the ac_l_in clip assumes that the clip's metal near the board (the U-base and ears) stays within ≈ ±2 mm of the axis below about 3 mm height, as the side view shows. In plan, the 12.5 mm flare sits over the strip (y ≤ 13.5), but it is at least ~8–10 mm above the board.

- **Check:** get the 125 clip STEP or measure a sample, and confirm a ≥ 3.2 mm air path from the clip to the l_f strip.
- **If it fails:** carry the l_f-to-RV1 link under the ac_l_in clip on **B.Cu** instead: a 3 mm strip at y 12–15 from x ≈ 255 to 279.5, with ≥ 6 vias at each end for surge current. The ac_n_in B.Cu pour then routes J1 pad 2's current around the right side, through a corridor of about 6.7 mm (x 282.7–289.4).

**ECO scope:** one footprint changed, one part moved 0.6 mm, two F.Cu pour outlines edited, then refill. No routing change on other nets. No change to the L1/C1/RV1/J1/J3 topology or to the barrier geometry, which is HOT-only in this corner. It is a BOM/source change (2 MPNs, 1 footprint). F1 and its clips stay hand-assembled.

## 6. Coordination with the enclosure inlet fuse

**Facts:**
- Both fuses carry the same current, with no branch between them on this board. The fault current available at F1 is essentially the same as at the inlet. So **each fuse that can be asked to interrupt a fault must carry its own adequate rating**, and a series rating should not be the basis.
- Selectivity is not achievable with these sizes:
  - Class CC: KLDR025 clears at 1,710 A²s; KLDR030 melts at 299.6 A²s.
  - MDA: MDA-25-R melts at 734.7 A²s, and MDA-30-R's 1,096.7 A²s melting is below the 25 A part's clearing.
  - For a high-current fault, either or both open. That is acceptable, because both are inside one appliance and any opening means service.
  - In the overload range the 25/30 A time-delay curves sit about 1.2 × apart, so expect F1 first, without guaranteed coordination.

**Recommendation to the enclosure team:**

1. **Preferred: delete the inlet fuse,** provided the inlet feeds nothing but J1.
   - F1 (Class CC, 200 kA) is then the appliance's overcurrent device.
   - The inlet-to-J1 leads are an extension of the cord, protected by the branch breaker: size them like the cord (≥ 14 AWG, ≥ 105 °C as the enclosure requires).
   - This removes one holder, one part and the coordination question.
2. **If an inlet fuse is kept** (user-accessible fuse wanted, or other loads tap the inlet):
   - Use **KLDR030 / LP-CC-30** (Class CC 30 A, 200 kA) in a **Littelfuse 5710CC** Class CC 600 V / 30 A panel-mount holder (§6.1).
   - The MDA-30-R holder cannot take a 10 × 38 fuse, so the panel cut-out changes.
   - Do **not** keep MDA-30-R: it has the same 1.5 kA problem at 127 V.
3. **Not recommended: inlet Class CC as the only high-interrupting fuse, with F1 left as MDA-25-R.**
   - On LP-CC data a 30 A inlet fuse would let through about 0.71–0.91 kA apparent RMS over the 4.7–8.4 kA range (interpolated from the 5 kA / 10 kA rows), inside MDA's 1.5 kA.
   - But this is a series (up-over-down) combination that only a lab test or acceptance can establish. Keep it as the documented fallback from DECISIONS, not the plan.

**Mechanical items for the enclosure team, whichever option:**
- The F1 envelope is now **45.2 × 13.5 mm**, centred at board (252.0, 7.25). Height is **18.5 mm** above the PCB top (clip top; confirm the fuse top with a sample).
- The ac_l_in clip metal sits **1.0 mm** inside the rear board edge. Keep ≥ 8 mm to any PE/chassis metal (D5) and check the lid clearance.

### 6.1 Panel-mount Class CC holder for the inlet (D-22 module end face)

Source for everything in this section: Littelfuse POWR-GARD datasheet "571 & 572 Series Panel-Mount Fuse Holders", **Rev: 021819** (© 2019), **page 1 of 1**. Third-party copy (cdn.components.ru); littelfuse.com/571 refused automated fetch. Inches are converted as printed on the sheet.

**Ratings (both series):**
- **600 V; 30 A for Class CC and Midget fuses**; dielectric strength 4,000 V min.
- Tin-plated brass terminals: combination solder and quick-connect. Black thermoplastic, UL94 V-0.
- **UL Recognized, File E14721**, and "UL Recognized for branch circuit protection" for the Class CC versions (5710CC/571RCC and 5720CC/572RCC). **CSA Certified, File LR7316.**
- The Class CC versions take a 13/32 × 1½ in fuse only. The rejection feature stops anyone fitting a midget fuse, including the old MDA-type service fuse, which is a useful property for a user-replaceable fuse.

**The two options:**

| | **Recommended: Littelfuse 5710CC** (order no. **057100CCL**; watertight 5710CCP / 057100CCLXP; right-angle rear terminal 571RCC / 05710RCCL) | Alternate: Littelfuse 5720CC (order no. **057200CCL**; watertight 5720CCP / 057200CCLXP; right-angle 572RCC / 05720RCCL) |
|---|---|---|
| Mounting | Flange with 2 screws | Snap-in, no hardware |
| **Panel cutout** | **Ø0.890 in (22.6 mm)** round hole, plus **2 × Ø0.172 in (4.37 mm)** screw holes on **1.310 in (33.3 mm)** centres, on the hole's diameter line | **Double-D**: **0.913 in (23.2 mm)** across the round, **0.756 in (19.2 mm)** across the flats (Greenlee #61092 punch). The sheet recommends **14–18 gauge panel** (≈ 1.2–1.9 mm). |
| Flange | 1.74 × 1.12 in (44.20 × 28.45 mm) | Ø1.20 in (30.5 mm) |
| Knob | Ø0.92 in (23.37 mm) | — |
| **Depth behind panel** | **1.34 in (34.04 mm)**, flange seat to the rear terminal tip, straight-terminal version | **2.10 in (53.3 mm)**, flange seat to the rear terminal tip |
| **Front protrusion** | **2.10 − 1.34 = 0.76 in (19.3 mm)**, flange plus knob (derived from the 2.10 in / 53.34 mm overall length) | **0.69 in (17.5 mm)** (overall length 2.40 in / 61.0 mm) |
| Side terminal | 0.86 in (21.84 mm) from the rear end | — |

**Why 5710CC:**
- It needs about 19 mm less depth behind the end face.
- Its screw flange does not depend on panel gauge. 572's snap fit is specified for 14–18 gauge sheet; a moulded plastic end face is likely thicker.
- Use the **P (watertight) variant** if the end face needs sealing. The sheet says the watertight version must be front-panel mounted.
- 571RCC (right-angle rear terminal) is available if the lead dress needs it. Its exact depth is not dimensioned on the sheet [check the CAD].

**Wiring:** cord **Line → the rear (bottom) terminal**, **Load → the side terminal** toward J1. That is the "Line/Load" labelling on the drawing, and it leaves the knob end dead when the carrier is withdrawn.

**Fuse:** KLDR030 (or LP-CC-30). The coordination note in §6 applies: no selectivity against F1 for heavy faults.

**Not chosen:** Bussmann HPF-RR (screw knob, 600 V / 30 A, Class CC; distributor data says "30A (20A max)", body Ø1.78 × 2.69 in) and HPS-RR (bayonet, Ø1.78 × 2.41 in). Eaton's data sheets 2114 (HPF) and its HPS sheet did not download, so their cutouts are unverified. The "20 A max" note on HPF-RR also needs checking before it could be an alternate.

## 7. Follow-ups

- **Certifier inquiry (`sourcing/inquiries/F1-CERTIFIER.md`):**
  - Questions 1 and 4 (125 V figure at 127 V) become moot with a Listed Class CC fuse. Rewrite the fuse facts.
  - Keep question 3, on the open clips: the 01250003H agency category and voltage rating, and a Class CC fuse in non-rejection PCB clips as supplementary protection.
  - Keep the temperature-rise question at 15 A.
- **Record on adoption:** a DECISIONS entry, plus a `sourcing/F1-J3-PARTS.md` section citing KLDR Rev 092821 pp.1–6 and Littelfuse 105/106/125 Rev 02/07/18.
- **Verify before release:**
  - Read the LP-CC-25 current sheet for I²t and derating, so the alternate is fully verified.
  - Read the 01250003H voltage rating and agency file on Littelfuse's own page.
  - Measure the clip profile (§5.3).
