# coil-r1 fit study: the R1 coil in the R43 enclosure, its leads, lugs, bench layout and printed former (2026-10-21)

**Status: modelled only.** Nothing physical exists yet. Every number below comes from a script in this folder, named next to it, or from a datasheet quoted in [Sources](#sources) with its read date. R43 (`output/temper-manufacturing-r43/`) was read and never written: its `src/` is imported read-only for the route-fillet helper, and every one of its STEP files is checked against its catalogue hash first.

**Inputs decided before this study:**
- **Litz:** Remington 260/38LITZ, unserved, OD 0.090 in (2.29 mm) maximum, MW 80-C, 155 °C.
- **Ferrite:** PC95 bars 90 × 15 × 5.
- **Coil-1 former:** resin print (Formlabs Rigid 10K or High Temp) in five 72° segments.

**Bundle tolerance (assumed).** The unserved bundle has no serve to hold it round. The design value is the published **maximum, 2.29 mm**. The band assumed for the measured mean is **2.15–2.45 mm**:
- −6 % for a bundle that runs under its maximum;
- +7 % for ovality: an unserved 5 × 52 bundle pressed into a notch spreads wider than a round gauge reads.

**Rule:** do not re-cut the former if the measured mean is ≤ notch − 0.1 mm, that is ≤ 2.39 mm on the CNC former and ≤ 2.49 mm printed. Above that, run `cad/former.py --bundle <OD>`.

| Tool (`.venv/bin/python -B fit/...`) | Output | Runtime |
|---|---|---|
| `r1_parts.py` | R1 former, winding (crossover and both lead exits), leads, NTC bead and lugs in R43's world frame (library) | — |
| `screen_r1_in_r43.py` | `results/r1-in-r43-screen.json`, `screen.log` | ~10 min |
| `extract_board_near_lugs.py` | `inputs/board_c53int_near_J2J5.step/.json` (36 board solids round J2/J5, from the stage-53 board the R43 fit gate measured) | run once |
| `lug_board.py` | `results/lug_board.json` | ~1 min |
| `bench_leads.py` | `results/bench_leads.json` | ~1 min |
| `litz_order.py` | `results/litz_order.json` | s |
| `segments_check.py` | `results/segments.json` | s |
| `render_fit.py` | `renders/fit_lug_J2_T1.png`, `renders/fit_crossing.png` | ~1 min |

`cad/former.py --bundle 2.29`, `cad/check_former.py`, `cad/template.py` and `cad/render.py` were re-run, so `cad/out/` and `renders/former_R1_*` are the R1 at 2.29 mm.

## 1. R1 in R43: interference screen

**Method.** The same as R43's `check_integration.py --all-pairs`, restricted to every pair the substitution touches:
- the replaced parts are former, winding, J2/J5 leads, J2/J5 lugs and coil-NTC bead;
- each was intersected solid by solid with every R43 part whose box it reaches, and with each other;
- dispositions use R43's own expected-interference rows (same vocabulary, same volume limits). Rows that needed a new limit are listed in `DISPOSITIONS` in the script, each with its reason.

There are four configurations: CNC or print former, each with the winding at R1 (6.46 outer turns) or as wound with the spare turn (7.46).

**Result: 0 unresolved in all four configurations** (`results/r1-in-r43-screen.json`). The screen found **four new issues on the way**. Each was fixed in the geometry, not dispositioned:

| Found | Cause | Fix (in `cad/former.py` unless stated) |
|---|---|---|
| Former × J2 lead, 17.2 mm³ | The sleeved lead (OD 3.55) bends down into the J2 rim hole at its 10.65 mm radius and grazed the rim's inner face | The rim hole is Ø4.6 (`LEAD_HOLE_R`) and is drawn out ±12 mm along the rim (`LEAD_SLOT`), so the lead can arrive from either side. The −0.5 trim lead returns the other way. After the fix the lead is 0.80 mm from the rim (0.12 mm in the spare state) |
| Print former × carrier-ear M3 screw, 73.1 mm³ | The 229° joint's rim boss reached over the 225° lug and refilled its Ø3.4 hole | The bosses are cut clear of each lug hole and its screw head (Ø6.5) |
| Comb end slivers 0.02–0.57 mm (both routes) | A notch 0–0.6 mm from a comb strip's free end (r32, r84, r92) left a sliver that cannot be printed or machined. R43 has the same slivers | Slivers under 0.6 mm are cut away with the notch (`MIN_END_TOOTH`). Holding the turn at the 103° spoke with polyimide tape until it is bonded covers it |
| Lead models over the roof | The J2 tube included the spiral run-out, and the J5 sleeve sat on the hub roof | Modelling only (`r1_parts.lead`): the sleeve starts where the lead leaves the winding |

**Hits that remain, all dispositioned:**

| Pair | mm³ (CNC/R1) | Disposition (R43 vocabulary) | Limit |
|---|---|---|---|
| former × R43 coil-NTC lead | 0.39 | DOCUMENTED_BONDED_INTERFACE (R43 row) | 3.0 |
| winding × J2 lead | 17.86 (18.49 spare) | DOCUMENTED_CONDUCTOR_CONTINUITY. The sleeved lead's start cap sits over the bundle end. **New limit:** R43's 15 mm³ was for a 2.4 lead on a 2.4 bundle | 40 |
| winding × J5 lead | 4.03 | DOCUMENTED_CONDUCTOR_CONTINUITY (R43 row) | 15 |
| J2/J5 lead × lug | 111.28 each | DOCUMENTED_UNVERIFIED_CABLE_ENTRY. The sleeve runs inside the lug's heat-shrink for its last 10 mm. **New limit:** R43's 60 mm³ had no shrink | 130 |

**Pairs under 1 mm (not hits):**
- **Unchanged from R43's geometry:** former to the glass TCO 0.6, to the PEEK body 0.5, wave spring 0.6, gap key 0.59, and the carrier screws and spacers it seats on (0.0).
- **New:**
  - J2 lead to the rim 0.80, or 0.12 with the spare turn wound;
  - J2 lead to the carrier 0.83, and J5 lead to the carrier 0.65. Both leads are still bending as they pass the Ø7 drop holes; on the vertical they clear by 1.6;
  - NTC bead to its bore 0.225, by design.

**Stack against the glass (Z, mm).** Source: `screen` → `stack`.

| | R43 / EM model (bundle 2.4) | R1 at 2.29 |
|---|---|---|
| Bundle centre | 100.20 | **100.145** |
| Winding top / gap to glass underside (Z106) | 101.40 / 4.60 | **101.29 / 4.71** |
| Comb top / gap to glass | 101.60 / 4.40 | **101.49 / 4.51** |
| Centre-lead crossing top / gap to glass | 104.5 / 1.5 (bare 2.4 lead, 0.5 mm over the comb plane) | **104.84 / 1.16** (Varglas No. 9 sleeve, OD ≤ 3.55, resting on the turns) |
| Bundle centre to pan base (Z110, on 4 mm glass) | 9.80 (the EM model) | **9.855** |

- **Effect on the EM model:** the bundle sits 0.055 mm lower than the model assumed. `model/fidelity.py`'s bundle_z +0.3 case moves free-air L −0.74 % and loaded L −1.37 %; scaled linearly to −0.055 mm, that is **+0.14 % free and +0.25 % on the 430 pan**. That is noise: no re-solve.
- **Crossing:** the centre lead is now closer to the glass than in R43, because the sleeve is thicker. That is an open item (§7). The crossing ray (−125°) and the gap-ring run have no comb, which is why the lead may rest on the turns.
- **Crossover** (`r1_parts.crossover`): the notch table fixes the bundle only at the spokes. The bundle leaves the 67° spoke's last inner notch at r82.5 and enters the 103° spoke's first outer notch at r93.5. A tangent-continuous S across that free span has a **smallest radius of 35.6 mm (15.5 × bundle)**. A straight chord between the nominal 75°/90° section ends would kink by 17° and 32°.

## 2. Leads and harness

**Bend rule.** The minimum bend radius is **3 × the sleeved lead's OD = 10.65 mm**. Sources:
- NASA-STD-8739.4A w/ Change 4, Table 7-1: installed harness of AWG 10 or smaller, minimum 3 × OD, optimum 10 ×. This is the same factor R43 used, applied here to the sleeved OD rather than the bare bundle.
- New England Wire gives 5 × OD for static installations (11.45 mm on the bare bundle).

No Litz maker publishes a Litz-specific rule (searched 2026-10-21).

| Lead (R43 route, R1 exits, Ø3.55 sleeved) | Developed (winding end to barrel top) | Tightest bend | Largest achievable | Cut length (developed + 7.1 in the barrel + 25 for one re-termination, rounded up to 5) |
|---|---|---|---|---|
| J2 (outer end → chord → rim slot → drop) | **72.7 mm** | 10.65 | 16.0 | **105 mm** |
| J5 (centre: crossing on −125° → gap ring → drop) | **163.6 mm**, including 6.4 mm of bare bundle where it lifts off the first turn | 10.65 | 13.2 | **200 mm** |

R43's list gave 58.6/151.4 mm developed and 110/205 cut. The difference: the lug barrel top is now Z41.8, not Z57.1. The real lug's barrel is shorter than R43's 25 mm envelope, and the 7466004R seat is 1.3 mm higher than the THR model.

**Litz per coil and the spool** (`litz_order.py`):

| Item | Length |
|---|---|
| Winding R1 | 9.253 m (ring model 9.269) |
| Spare turn, wound then trimmed | + 0.732 m |
| Bench leads (§4) | + 0.464 m |
| Strip in barrel, one re-termination per lead, 50 mm handling | + 0.114 m |
| **Total per coil** | **10.56 m** |

- **Order:** 2 coils + 3 × 1 m W9 qualification samples + a 10 % practice start = **25.2 m**.
- **Spool choice:** a 1 lb spool (76 ft, 23.2 m) does **not** cover two coils with the qualification samples. **Order the 2.5 lb spool** (189 ft, 57.6 m, $455.20): it covers the order plus three more coils from one lot.
- **Cheapest alternative:** 1 lb + 8 oz (34.7 m, $290.51). It covers the order, but the two spools may come from two lots.

## 3. Lugs on J2/J5

**Terminal: Würth 7466004R** (datasheet rev 001.003, 2023-07-03; read 2026-10-21):
- **Mechanical:** M4 thread through the part. Body Ø7.0 × 5.0 mm above the PCB, 6.0 mm overall, with a Ø5.0 × 1.0 spigot in a Ø5.2 non-plated hole.
- **Assembly:** tightening torque **1.2 N·m**. The design guide gives 2.9 N·m minimum breaking torque and a 300–410 N tearing force.
- **Ratings:** 50 A max at 20 °C, −55 to +150 °C.
- **No limit on lug width, washer or screw head** is stated in the datasheet or in the REDCUBE SMD design guide. The Ø7 face is the only bearing surface, and Würth's catalogue pairs the part with its WA-CLUG 55804025 (W 7.5).
- **Lug seat:** Z32.6, which is the board top + 5.0. R43 modelled 31.3, from the THR part's KiCad model.

**Choice: Panduit P14-8RHT6-C, formed 90° up, barrel outboard, insulated with Alpha Wire FIT-350 PVDF heat-shrink.**
- **Lug data:** 18–14 AWG, #8 stud. Ring OD 7.9, tongue 0.8, barrel ID 2.3, brazed seam. Copper, nickel-plated, **343 °C**, cULus.
- **Heat-shrink:** two layers. The 3/16 in tube goes over the barrel and 10 mm of sleeve; the 1/4 in tube goes from the sleeve over the barrel and the bend to the ring edge. FIT-350 is UL 224 150 °C / 600 V, rated −55 to 175 °C.
- **Why this lug** (`lug_board.py`, exact solids against the stage-53 board):

| Lug as modelled | To CT T1 (gate 1.0 mm) | J2–J5 lug | Verdict |
|---|---|---|---|
| R43 envelope (control: re-measured) | **0.50** | — | Reproduces the power stage's ratchet entry |
| **Panduit P14-8RHT6-C, upturned, shrink** | **1.90** | barrel axis 7.9 from the stud, barrel top Z41.8 | **Clears the gate.** The T1 ratchet row goes stale when R44 adopts the lug |
| TE 1577639-1 (PEEK, 260 °C, in stock) upturned | **0.00, touches T1** | Ø6.05 PEEK sleeve, axis 8.7 mm | Rejected for J2 |

- **Exposed metal J2–J5:** ring, washer and screw head. That leaves **6.0 mm** between the Ø9 washers at any rotation, against ≥ 5.0. The ring is 7.9 wide, against ≤ 10.
- **Bend direction:** form the tongue **away from the barrel side**. The barrel then stands outboard; bent the other way, it stands over the screw head.
- **Assumed geometry:** inner bend radius 1.0 and barrel OD 3.3. Check both on the first formed lug at W9.
- **Insulation:** this is the "bare upturned ring + ≥ 150 °C heat-shrink over barrel and bend" option that ASSEMBLY.md allows, except for one difference. ASSEMBLY.md says *dual-wall*, and no adhesive-lined tubing at ≥ 150 °C was found (HOT-LIMITS.md). Two recovered PVDF layers are proposed instead. **The power-stage owner must accept that** (§7).
- **Stock (DigiKey, 2026-10-21):** **0 in stock** (active, $0.90). Alternatives in order:
  1. **ABB/T&B B86U.** Factory 90° ring, 16–14 AWG, #8, 7.9 wide, tin. The only catalogue 90° part found, but 1,000 minimum at $2,072 with no temperature rating published.
  2. **Würth WA-CLUG 55804025.** In stock 1,199, 125 °C tin, DIN tubular with a 1.3 mm palm, formed the same way.
  3. **TE 1577639-1, on J5 only.**
- **Screw stack:** ISO 7045 M4 × 8 A2 pan head + DIN 125-A washer + DIN 127-B spring washer, 1.2 N·m:
  - stack 2.5 mm;
  - 5.5 mm of the 6.0 mm thread engaged;
  - tip 0.5 mm below the board top, so 1.1 mm inside a 1.633 mm board: it does not protrude.

**Termination: solder-pot strip and tin, then crimp. Do not solder the crimp.**
- **Solder pot:** the MW 80-C solderable polyurethane/polyamide enamel comes off in the pot. That is the only way every strand of an unserved Litz is bared and wetted, which is why the build guide's pot step stays.
- **Pot temperature:** Remington states none (data sheet rev 3/25/25). Start at the RMC figure of ~400 °C and find the time on scrap.
- **Crimp:** the tinned end goes into the 2.3 mm barrel with the matched Panduit tool. Confirm the tool number at order.
- **Do not solder the crimp:** solder wicks up the bundle, makes a stiff section and a fatigue point at the barrel mouth, and would cook the shrink.
- **Known risk:** solder-tinned strands under a crimp can cold-flow and lose pressure over thermal cycles. So W9 qualification adds 10 cycles to 130 °C and a re-read of the 4-wire R (BUILD-AND-MEASURE W9).

## 4. Bench layout and lead length (coil 1)

**Placement rule (stated):** no part of the native-21 board, tongue included, may see more coil field than the board sees installed in R43. The reference is the installed R1 coil's |B| at R43's under-coil check point (r60, Z80), **11.88 µT/A** from `coil_model` with the enclosure on. The bench field comes from the same model in free air.

| Item | Bench layout (`bench_leads.py`) |
|---|---|
| Coil | In front of the board, axis at board **(202, 298) mm** (KiCad frame; front edge y140), lead exits facing J2/J5. Nearest board point 155 mm from the axis, which sees 11.79 µT/A |
| Bench sink (511-3M, rear edge) | 309 mm from the axis, 1.46 µT/A |
| Height | Former underside **51.8 mm above the board top**; winding plane 59.0 mm. Leads run level at 33.3 mm, 2.0 mm over the tallest part under them (a 29.5 mm film capacitor under the J5 run) |
| Spacer | Plywood or MDF ring support under the rim and the four lugs, nylon M3, **open for ~70° over the lead exits**. The leads drop straight out of the coil at the R43 drop points |
| **J2 lead** | **160 mm** developed, bend ≥ 10.65 → **cut 195 mm** (free length from the outer end) |
| **J5 lead** | **305 mm** developed → **cut 340 mm** (free centre lead at W3) |

**What the bench leads add** (40 kHz, `litz.py` with 260 × 0.1007):
- **L:** +0.17 µH of loop L (paired run 0.55 µH/m plus the unpaired 31 mm ends), 0.2 % of 81 µH.
- **R:** 0.464 m of lead in all, against the 0.4 m already in the coil model's R. That adds **+0.56 mΩ R_dc and +0.57 mΩ R_ac at 25 °C** (+0.92 / +0.93 at 100 °C). The model's R_dc for this Litz was 85.2 mΩ, so the bench coil should read about **85.8 mΩ**. At the datasheet's maximum resistivity, which is 6 % above nominal, it should read about **91 mΩ**. Both are under the 100 mΩ limit.
- **Measurement method:** both are below the instruments' resolution at M2 and M5. Measure L with the leads in the bench dress (twisted together, lugs on) and record the dress.

**Tune loop: the half-turn states are not what tune.py listed.**
- **Why:** the J2 exit is fixed at −94.3°. A half-turn trim leaves the end 180° away, so the lead must come back about 171° clockwise along the rim, over the comb tops.
- **Effect:** that return cancels part of a turn. The model, with the return as a partial ring, gives **73.9 µH** for "−0.5", not 76.8.
- **Change:** `model/tune.py` now applies that ratio and prefers whole outer turns: 7.46, 6.46 or 5.46.

**Cut the leads later, or wind a second coil? Wind a second coil.**
- Coil 1 is on a printed former, which is for bench and low power only (README D6, HOT-LIMITS).
- The enclosure coil is coil 2 on the G11 CNC former, wound with the enclosure cut lengths (J2 105, J5 200).
- Coil 1's bench leads *can* be cut to enclosure length for a fit check: one re-termination is allowed for in the cut length. But coil 1 should not be the one installed for sustained heating.

## 5. Printed segments (`segments_check.py`)

| Check | Result |
|---|---|
| Joint features | **Rim:** 6° half-lap with a Ø3.2 pin hole at r125 for a 3 mm G10 or bamboo pin. **Hub:** none before this study (butt face only). **Added:** a hub boss (±8°, r22–29, Z0–5) with a Ø2.2 pin hole at r25.5 for a 2 mm G10 or glass-fibre pin; walls 2.4 / 2.4, and 0.4 mm short of the bar channel. Each joint is now pinned at both ends; bond the faces (§ assembly below) |
| Notch or comb tooth on a joint | **None.** Joints are at mid-gap; the nearest comb strip is 7.9 mm from a joint plane |
| Bar channel across a joint | **None.** The nearest channel edge is 1.5 mm from a joint plane; each segment carries two whole spokes |
| Turns over a roofed seam | Near the hub, neighbouring spoke roofs merge (r < 31.1), so the first turn crosses each joint seam on the roof (r27.8–31.6, 6 places). Sand the seams flush before winding |
| Teeth at 2.29 (print, notch + 0.3) | **Inner 1.224, outer 0.721 mm**. CNC: 1.324 / 0.821. At the band edges, print 0.561–0.861 outer. **No end slivers** after the fix |
| Wall rule | Formlabs' design guide (Form 4, Grey) gives **0.2 mm** minimum supported and unsupported walls. The former keeps a stricter 0.6 mm (`MIN_END_TOOTH`), so the thinnest tooth, 0.72 mm, has 3.6× the guide's minimum |
| Segment solids | One solid each; adjacent overlap 0.000 mm³; the volumes add up to the printed body (69.5 cm³); largest footprint 161.6 × 106.9 mm |
| Fixing | Segments 1–4 each carry one carrier lug (315°/45°/135°/225°). **Segment 5 has none**: it is held by its two pinned and bonded joints. That is why the joints are bonded, not just pinned |

**Assembly:**
1. Dry-fit the five segments with pins on a flat glass plate.
2. Bond the laps and butt faces with a structural two-part epoxy, clamped flat.
3. Cure, sand the hub seams flush, then fit the bars.

On the bench spacer and in the carrier, screw all four lugs (nylon M3).

**Material:** Rigid 10K (UV + thermal post-cure) is the pick. Its HDT is **218 °C at 0.45 MPa / 110 °C at 1.8 MPa**, modulus 10 GPa, elongation 1 % (Formlabs TDS Rev 04).
- **Against High Temp:** that resin has a similar 0.45 MPa HDT (238 °C) but only 2.8 GPa and 101 °C at 1.8 MPa. Stiffness holds the comb pitch under winding tension.
- **Cost:** Rigid 10K is brittle (1 % elongation). Press the bundle in with the tamper, never lever on a tooth, and print a spare segment 5.
- **Limit:** the printed former is still a bench former. The winding limit stays ≤ 130 °C (README D4).

## 6. R43 coil parts to update in the next enclosure revision

R44 is reserved for other work, so these are listed, not made:

1. **`sensor_coil_former`:**
   - the R1 notch table (14.47 + 6.46, spare turn) at the measured bundle;
   - comb top 101.49;
   - J2 rim hole Ø4.6 with the ±12 mm slot;
   - no end slivers;
   - NTC pad re-derived (bead centre r86.27, wall 2.0).
2. **`sensor_coil_litz_winding`:** R1, bundle 2.29, the S crossover between the 67° and 103° spokes, 9.25 m.
3. **`harness_coil_lead_to_J2/J5`:**
   - sleeved OD 3.55;
   - centre crossing resting on the turns (Z103.07);
   - barrel top Z41.8;
   - developed 72.7 / 163.6 mm and cut 105 / 200 mm;
   - the harness list row "Litz in braided fibreglass sleeve" becomes "Varglas Silicone Rubber C-1 No. 9".
4. **`electronics_coil_lug_J2/J5`:** the formed Panduit lug at the 7466004R seat Z32.6, replacing the R26 25 mm envelope at Z31.3.
   - The drops move 0.1 mm toward the studs, to (−9, 142.6) and (−9, 173.4), still inside the Ø7 carrier and Ø10 barrier holes.
   - The power stage's `r43-expected-hits.json` T1 row (0.5 mm) then goes stale (1.9 mm).
5. **`sensor_coil_winding_NTC` and `harness_NTC_coil_to_thermal_sense`:**
   - the bead moves with the R1 bore (r86.27);
   - the R43 NTC lead's start still sits in the new counterbore (0.39 mm³ bonded); re-route it from the R1 bore.
6. **Expected-interference rows:** winding × J2 lead limit 40 mm³, lead × lug limit 130 mm³ (§1).
7. **Carrier drop holes:** the sleeved leads pass the Ø7 holes at 0.65–0.83 mm while still bending. Chamfer the hole tops 1 × 45° or open them to Ø8.

## 7. Open questions

1. **Heat-shrink in place of dual-wall.** Two layers of PVDF (FIT-350, UL 224 150 °C) are proposed in place of ASSEMBLY.md's "dual-wall ≥ 150 °C" tubing, which was not found. The power-stage owner must accept that for the M6 insulation requirement.
2. **Panduit P14-8RHT6-C stock.** DigiKey showed 0 on 2026-10-21. If no distributor has it, use Würth 55804025 (125 °C), or buy the B86U only if a 1,000-piece lot is acceptable.
3. **Centre-lead crossing 1.16 mm under the glass** (R43: 1.5). The glass underside reaches 230–250 °C in the fry case. Options:
   - Varglas **No. 10** (ID 2.59 min; about 0.3 mm diametral clearance on 2.29 Litz, so slide it on with the end taped) gives about 1.4 mm;
   - production should consider an under-crossing.

   Measure the crossing-lead temperature in first power.
4. **Remington strip temperature** is not published. It is found on scrap at W9.
5. **Lug form:** the assumed inner bend radius (1.0) and barrel OD (3.3) set the T1 clearance (1.9 mm). Measure the first formed lug.
6. **One-piece print:** a printer bureau with a large-format SLA machine could print the former in one piece, removing the joints. The build volume was not checked.

## Sources

Read 2026-10-21. Live PDF or page unless noted.

- **Würth 7466004R datasheet rev 001.003** (https://www.we-online.com/components/products/datasheet/7466004R.pdf):
  - "Tightening Torque 1.2 N*m", "Rated Current IR @ 20 °C 50 A max.", "Operating Temperature -55 °C up to +150 °C";
  - drawing: M4 through, 5.0 body, 6.0 overall, Ø7.0 / Ø5.0;
  - no lug-width statement.
- **REDCUBE SMD Terminals Design Guide** (https://www.we-online.com/components/media/o153698v410%20BCF_REDCUBESMDDesignGuide_EN.pdf):
  - M4 through thread: "Max. tightening torque [Nm] 1,2", "Min. breaking torque 2,9";
  - tearing force "max. … 410 N … on average … above 300 N".
- **Würth WA-CLUG 55804025 datasheet** (2024-11-29): W 7.5, Ø4.3, ID 2.3, H 1.3, 2.5 mm², −30 to +125 °C. DigiKey: 1,199 in stock, $0.96.
- **Panduit P14-8RHT6-C** (https://www.panduit.com/en/products/wire-termination/electrical-terminals/ring-terminals/p204319.html):
  - 18–14 AWG, #8, OD 7.9, tongue 0.8, ID 2.3, brazed, nickel-plated copper, 343 °C, 2000 V, cULus;
  - DigiKey: 0 in stock, $0.90, active.
- **TE 1577639-1 drawing rev B and TE page:** Ø4.34 for #8/M4, 8.71 ring, tongue 0.80, 22.99 max, insulation Ø6.05 max, insulation support 2.30–3.18, PEEK 0–260 °C. DigiKey: 1,648 in stock, $7.30, 24 weeks.
- **ABB B86U** (https://empower.abb.com/ecatalog/ec/EN_NA/p/B86U): "Non-Insulated Heavy Duty Ring Terminal with 90 Degree Bend … Width .31 Inches, Bolt Hole #8, Wire Range 16-14 AWG … Tin Plated, 1,000 Pack". DigiKey: 1,000 minimum, $2,072.07.
- **Alpha Wire FIT-350-3/16 customer spec** (https://static.rapidonline.com/pdf/560382_v1.pdf): supplied ≥ 0.187 in, recovered ≤ 0.093 in, wall 0.010 in, "UL Standard 224 150°C / 600 VRMS VW-1", −55 to 175 °C, 800 V/mil. The 1/4 in size (recovered 0.125, wall 0.012) comes from a search snippet only.
- **Varflex Varglas Silicone Rubber** (https://www.varflex.com/varglas-silicone-rubber; data sheet and size table PDFs):
  - −73 to +200 °C;
  - Grade C-1 "2500v min. avg., 1500v min. indiv.";
  - No. 9 ID 0.114–0.124 in; Grade C wall 0.008 in min;
  - No. 10 ID 0.102–0.112 in.
- **NASA-STD-8739.4A w/ Change 4** (https://standards.nasa.gov/sites/default/files/standards/NASA/A/4/nasa-std-87394a_w_change_4_0.pdf), Table 7-1: "Overall harness (with AWG size 10 or smaller without coaxial cable)", 10 × OD optimum, 3 × OD minimum.
- **New England Wire glossary, bend radius:** "5x the outer diameter for static (one time) installations".
- **Formlabs Rigid 10K TDS** (FLRG1001 Rev 04): UV + thermal 218 °C at 0.45 MPa, 110 °C at 1.8 MPa, 10 GPa, 1 %.
- **Formlabs High Temp product page:** post-cured at 160 °C: 238 / 101 °C, 2.8 GPa, 2.3 %.
- **Formlabs Form 4 design guide** (third-party mirror of Formlabs' white paper): minimum supported and unsupported wall 0.2 mm, minimum clearance 0.4 mm.
- **Remington 260/38LITZ page and data sheet rev 3/25/25:**
  - spools 2 oz / 9 ft $33.25 … 1 lb / 76 ft $187.65, 2.5 lb / 189 ft $455.20, 5 lb / 378 ft $800.25, 10 lb / 756 ft $1,434.06;
  - 0.090 in OD, 0.00281 Ω/ft max at 20 °C, MW 80-C, 155 °C;
  - no strip temperature stated.
