# coil-r1: build and measure the prototype coil

This procedure **supersedes R43's `design/r43/COIL-PROTOTYPE-BUILD.md`** for the items listed below. Everything else in that guide still holds: bar bonding, the coil-NTC pad and potting, the insulation test levels, and the thermal soak.

| Item | R43 guide | coil-r1 |
|---|---|---|
| Turns | 15.5 inner + 6.4 outer = 21.9; "70 µH, about 20 or 21.5 turns" | **14.47 + 6.46 = 20.93 turns (R1), wound with one spare outer turn (21.93), then trimmed to L.** R43's 21.93 turns give 87.7 µH free-air, not 70 µH (README D1) |
| Target L | 70 µH (or the 80 µH alternate) | **~81 µH free-air: accept 76–86 µH** (spec alternate B, README D2) |
| Start angle | text says +95° | **−95°** (the source is −95°; the R43 text was a typo, as the 2026-10-10 review found) |
| Inner end / crossover | "end at 90°, cross to 105°" (R36 angles) | **inner end 75°, outer start 90°**, as R37 modelled |
| Tuning | "remove whole outer turns, keep ≥ 6" (this cannot be followed: one turn off 6.46 leaves 5.46) | **unwind in half-turns from the outer end, never below 5.46 outer turns**; at 4.96 the cast-iron loaded L falls under the 41.5 µH floor (`model/results/trim_heating.json`) |
| Litz | custom 270 × 0.10, grade 200 | **First coils use stock solderable Litz** (ORDER-LIST.md). Grade 200 is for qualification. The comb notch and spacer sizes follow the **measured** bundle OD |
| Termination | solder pot then crimp, 12–10 AWG lug | **Panduit P14-8RHT6-C** (14 AWG barrel, 343 °C) formed 90° up, two layers of FIT-350 PVDF; solder-pot strip, then crimp; qualified on scrap with thermal cycles first (step W9; `fit/README.md` §3) |
| Leads | ~250 / ~150 mm, "braided fibreglass" | **Varglas Silicone Rubber C-1 No. 9** sleeve. Coil 1 (bench): **J5 340 mm, J2 195 mm** free. Enclosure coil: J5 200, J2 105 (`fit/README.md` §2, §4) |

Every number below has its source in `model/results/TABLES.md`, `cad/out/checks.json` or `fit/results/`. The modelled values are **not measurements**: the point of this procedure is to measure them.

## Fit (2026-10-21, `fit/README.md`)

| Result | Tool | What it changes here |
|---|---|---|
| R1 at bundle 2.29 substituted into R43: 0 unresolved hits (CNC/print, R1/spare). The fixes were the J2 rim slot, the comb end slivers, the joint bosses clear of the lug screws, and the hub pins | `fit/screen_r1_in_r43.py` | §0 former files regenerated; W8 lead dress |
| Stack: comb top Z101.49 (4.51 under the glass), winding top 101.29 (4.71), crossing lead top 104.84 (1.16) | same | M4 spacing; first-power crossing-lead thermocouple |
| Leads: bend ≥ 10.65 mm (3 × sleeved OD); bench J2 160 / J5 305 mm developed | `fit/bench_leads.py` | W3, W8, W9 |
| Lug: Panduit P14-8RHT6-C upturned, 1.9 mm from CT T1 (R43 envelope: 0.5) | `fit/lug_board.py` | W9 |
| Bench leads add +0.17 µH and +0.56 mΩ R_dc (25 °C) | `fit/bench_leads.py` | M2, M3 expectations |
| A half-turn trim with the fixed J2 exit gives 73.9 µH, not 76.8 | same, `model/tune.py` | §3: prefer whole outer turns |
| Printed segments: pinned at the rim and the hub, bonded; teeth 0.72 / 1.22 mm | `fit/segments_check.py` | §0 route B assembly |

## 0. Before you start

- **Former route** (README D6). Pick one:
  - **A, CNC G11:** `cad/out/former_R1_cnc.step`.
  - **B, printed:** `cad/out/former_R1_print_seg1..5.stl`, in PC, PA-CF or ASA, never PLA or PETG.
  - **C, no printer:** a 1.0 mm FR4 sheet cut to `cad/out/roof_sheet_R1.dxf`, with the 1:1 template `cad/out/template_R1_1to1.pdf`.

  All three put L within 1.2 % of each other (`model/fidelity.py`). That is less than one tuning step.
- **Measure the Litz OD before cutting or printing the former.** Use calipers at 5 places along a 1 m sample, with light pressure, and take the mean (call it OD).
  - Re-generate the former with `.venv/bin/python cad/former.py --bundle <OD>`. Notch width = OD + 0.2 for CNC, OD + 0.3 for print.
  - **Remington 260/38LITZ (the decided wire):** the files in `cad/out/` are cut for **2.29 mm** (the published maximum). Teeth at 2.29: outer 0.82 / inner 1.32 mm on CNC, 0.72 / 1.22 printed (`fit/results/segments.json`). Re-cut only if the measured mean exceeds **2.39 (CNC) / 2.49 (print)**: the notch is bundle + 0.2 / + 0.3, and up to 0.1 mm less clearance is accepted. The bundle is unserved and not round: measure across its widest direction too, and handle it gently on the comb.
  - With the RM Cybernetics 1000 × 0.05 (OD 2.55), the outer comb teeth get thin: 0.56 mm on CNC, 0.46 mm printed (`cad/out/checks.json`). For a printed former with OD > 2.45, print with a 0.25 mm nozzle, or skip the outer teeth and use the spacer cord of route C for the outer section only.
- **Printed former (route B) assembly** (`fit/README.md` §5):
  1. Dry-fit the five segments on a flat glass plate with the pins: 3 mm G10 at the five rim laps, 2 mm G10 or glass-fibre at the five hub bosses.
  2. Bond the laps and butt faces with structural two-part epoxy, clamped flat. Segment 5 carries no carrier lug, so it is held only by its bonded joints.
  3. Sand the five hub seams flush: the first turn crosses them on the roof.
  4. Fit the bars.
  5. Treat the comb gently. Rigid 10K is brittle (1 % elongation): press the bundle in with the tamper, never lever on a tooth.
- **Check the ferrite bars** (step M1) **before the former is cut.** R43's warning stands: the channels are 15.2 × 5.0 × 90.2.
- **Build the jig** from `cad/out/jig_dxf/` and `cad/out/jig_cutlist.csv` (renders: `renders/jig_assembly.png`).
  - Only wood glue and dowels above the top plate. The coil sits ~420 mm above the bench, and nothing metallic is within ~150 mm of it.
  - **Keep phones, steel tools, the tally counter and the LCR meter ≥ 300 mm from the coil while measuring.**

## 1. Winding (traveller)

Record each line on the traveller sheet (section 4) as you go.

1. **W1 Bars.** Bond the 10 bars into the channels with high-temperature silicone. On route C, bond them under the FR4 sheet on the template's blue outlines. Cure fully, since uncured silicone lets bars move.
2. **W2 Mount.**
   - Seat the former's hub on the J12 centring boss.
   - Screw the four lugs to the platter with nylon M3 screws.
   - Line the former's −95° direction up with the platter's long START tick. That direction is the ray from the centre through the J2 lead hole in the rim (J2 sits at −94.3°).
   - Turn the platter so the START tick sits at the J15 pointer. Zero the tally counter.
3. **W3 Centre lead.**
   - Leave **340 mm** of free lead for coil 1 (bench, `fit/results/bench_leads.json`: 305 mm developed + 7 mm in the barrel + 25 mm for one re-termination); **200 mm** for an enclosure coil. Slide the Varglas sleeve on before you start (it cannot go on over the lug later), taping the Litz end so the unserved strands do not catch. Take the lead up through the boss's lead slot and tie it to the J13 lead mast with a silicone band, never a metal clip.
   - Lay the first turn at **r27.4 at −95°** (template START mark), heading **counter-clockwise seen from above**.
4. **W4 Tension.**
   - Set the J9 felt brake so the wire pays off at **5–10 N**. To read it, hook a luggage scale to the wire between the spool and the PTFE eye and pull steadily until the spool turns: 0.5–1.0 kg.
   - This is a starting value, not a derived one. Use the lowest tension that keeps the bundle straight into each notch without flattening the serve, and **record what you used**.
   - The wire touches only the PTFE eye and wood. Never pinch it. Keep every bend radius ≥ 12 mm (5 × OD) on the bare bundle, and ≥ 10.65 mm (3 × the 3.55 mm sleeved OD, NASA-STD-8739.4A Table 7-1 minimum) on the sleeved leads.
5. **W5 Inner section, 14.47 turns, pitch 3.815.**
   - Turn the platter by the J16 peg and press each crossing into its notch with the J14 tamper, never a fingernail or metal.
   - Click the tally each time START passes the pointer.
   - **The inner section ends at tally 14 + 170°** (17 ticks past START). That is r82.6 at 75°.
   - Route C has no comb. Lay the bundle on the red ticks with a **spacer cord** wound alongside it, two-in-hand: monofilament of diameter **3.815 − OD** (1.4 mm for OD 2.4; 1.3 mm for OD 2.55).
   - Hold every second spoke crossing with a 10 mm strip of polyimide tape.
6. **W6 Crossover.** Go diagonally from r82.6 at 75° to **r93.4 at 90°** (tally 14 + 185°). Hold it with polyimide tape.
7. **W7 Outer section, 6.46 + 1 spare = 7.46 turns, pitch 3.311.**
   - Wind on into the spare notches. Route C spacer cord: **3.311 − OD** (0.9 mm for OD 2.4; 0.75 mm for OD 2.55).
   - **The R1 end is at tally 20 + 352°** (8° before START), at r114.8.
   - **The spare end is at tally 21 + 352°**, at r118.1, 9° before the J2 lead hole.
   - Do not bond anything yet.
8. **W8 Tune** (section 3). Measure, unwind to the chosen state, measure again. Only then:
   - bond: a silicone dab at every comb crossing (route C: a silicone bead along each bar line), then cure;
   - cut the outer lead so **195 mm** hangs free from the outer end for coil 1 on the bench (160 mm developed + barrel + one re-termination); 105 mm for an enclosure coil. The lead runs along the rim into the J2 rim slot (Ø4.6, drawn out ±12 mm along the rim) and straight down.

   Each half-turn removed moves the outer end 180° away from J2. The lead then runs back about 171° along the rim, over the comb tops, to the J2 slot, and that return cancels part of a turn: the model gives 73.9 µH for "−0.5", not 76.8 (`fit/bench_leads.py`). **Prefer whole outer turns** (7.46 / 6.46 / 5.46). If a half turn is used, dress the lead **before** the final L reading.
9. **W9 Leads and termination** (`fit/README.md` §3).
   - The Varglas No. 9 sleeve is already on (W3 / W8). Leave it 2 mm short of the strip.
   - **Form the lug first.** Panduit P14-8RHT6-C: bend the tongue 90° up, starting 0.5 mm past the ring edge, over a 1.0 mm radius. Bend it **away from the barrel side**, so the barrel stands outboard (bent the other way, it stands over the screw head). Check that the barrel axis sits 7.5–8.5 mm from the ring centre: the fit (1.9 mm to CT T1 on J2) assumes 7.9.
   - Slide on the heat-shrink: FIT-350 3/16 in (inner layer) and 1/4 in (outer layer).
   - Strip **solderable** enamel in a solder pot, 9 mm (the 7.1 mm barrel plus 2). Remington states no strip temperature: start at ~400 °C (RMC's figure) and find the time on scrap. Grade-200 enamel will not strip this way: that is why the first coils use solderable stock.
   - Crimp the tinned end in the 2.3 mm barrel with Panduit's matched tool. **Do not solder the crimp**: the solder wicks up the bundle and leaves a stiff section at the barrel mouth.
   - Recover the 3/16 in tube over the barrel and 10 mm of sleeve, then the 1/4 in tube from the sleeve over the barrel and bend to the ring edge. Only the ring stays bare (7.9 mm wide; ≥ 5.0 mm exposed-metal gap J2–J5 at any rotation with the Ø9 washers).
   - Fit on the 7466004R: ring, DIN 125-A washer, DIN 127-B spring washer, ISO 7045 M4 × 8, **1.2 N·m**. The tip stays 1.1 mm inside the board.
   - **Qualify on scrap first.**
     - Terminate both ends of a 1.00 m sample and measure its 4-wire R_dc. It must come within +5 % of n·π·d²/4 at the datasheet Ω/km. For Remington 260/38: ≤ 0.00281 Ω/ft at 20 °C = 9.22 mΩ for 1 m, so ≤ 9.7 mΩ. For RMC 1000 × 0.05: ≤ 8.9 Ω/km max, so ≤ 8.9 mΩ.
     - A higher reading means unconnected strands.
     - Then run **10 cycles to 130 °C** (an oven, lugs included), re-read R_dc and pull-test one lug by hand. Tinned strands under a crimp can cold-flow.
     - Repeat until two samples pass.
10. **W10 Coil NTC.** As R43 step 7. The −41° pad is regenerated for R1: bead centre r86.3, 2.0 mm of former to the last inner turn at r81.4 (`cad/out/checks.json`). Route C has no pad: tape a glass-bead NTC or thermocouple to the winding for bench use only.

## 2. Measurements

**Instruments** (ORDER-LIST.md §6):
- An LCR meter covering 20–60 kHz with Kelvin clips. The TH2830 (to 100 kHz) is the cheapest suitable one found.
- A 4-wire milliohm meter.
- An oscilloscope, a PP film capacitor and a function generator for the ring-down check.
- Glass-fibre K-type thermocouples with a logger.

Open/short-compensate the LCR at every frequency with the leads in their measuring position. Use 1 V, series model (Ls–Rs).

| Step | What | Model expects (R1, design Litz; stock Litz in brackets) | Pass level |
|---|---|---|---|
| **M1 bars** | Each bar: dimensions; then 20 turns of hookup wire wound tight round its middle, L at 10 kHz | 90 × 15 × 5; ten bars alike | bars within ±0.15 mm of 15.0 / 5.0; L within ±10 % of the median (reject outliers: unknown material or cracks) |
| **M2 free air** (on the jig: bars fitted, leads dressed) | L, Rs at 20/30/40/50/60 kHz | L 81.1 µH (R1); 89.9 with the spare turn. Flat (the free-air model has no frequency dependence; the installed no-pan L moves 0.1 % over 20–60 kHz through enclosure eddies). R_ac 84 / 85 / 87 / 89 / 91 mΩ at 25 °C (RMC 1000 × 0.05: ~91 at 40 kHz) | **76–86 µH** after tuning (spec alternate B: 72–88). Flat **±3 %** over 20–60 kHz (row 2). R_ac ≤ 0.193·(f/40 kHz)^0.55 Ω: **0.132 / 0.193 / 0.241 Ω at 20 / 40 / 60 kHz** (row 5). The LCR's R uncertainty at Q ≈ 230 is large (about ±|Z|×accuracy ≈ ±20 mΩ at 0.1 %), so M5 is the real R_ac check |
| **M3 R_dc** at 25 °C, 4-wire, lug to lug | R_dc | 83 mΩ (RMC 1000 × 0.05: 90; Elecify 1050/44: 86; **Remington 260/38 with the bench leads: 85.8, up to ~91 at the datasheet's maximum resistivity**, `fit/bench_leads.py`) | **≤ 0.100 Ω** (row 4). Above model +10 % means suspect terminations |
| **M4 loaded** | L, Rs at 20–60 kHz. Each pan centred, pan base **11.0 mm above the former roof top** (8.5 mm above the comb top at bundle 2.29: the Z110 − Z99 stack; `fit/results/r1-in-r43-screen.json`), on a 4 mm glass or non-metallic spacers | R1 at 40 kHz: cast iron 39.7 / **46.1** / 61.0 µH for µ 50 / 100 / 300; 430 36.7 / 49.4 / 62.7; carbon steel 32.9–44.4; aluminium 23.6 µH, 0.13 Ω. R_refl 2–6 Ω for ferrous pans | **≥ 41.5 µH on the cast-iron reference pan** (row 3). Ratio L_loaded/L_free in **0.47–0.77** (row 3b, alt B). Measure **every pan you will cook on**, plus an aluminium one; they calibrate the model (README D1) |
| **M5 ring-down R_ac** | Coil in series with a PP film capacitor (e.g. 0.22 µF 630 V), excited by a few-volt step from the function generator; scope across the capacitor; f0 and the 1/e envelope time τ | f0 ≈ 37.6 kHz at 81 µH / 0.22 µF; τ = 2L/R ≈ 1.9 ms at R ≈ 87 mΩ | R_total = 2L/τ. Subtract the capacitor ESR from its datasheet (PP: a few mΩ) and the generator's source resistance if it is left connected (use a relay or switch to disconnect it). Must also meet row 5 |
| **M6 installed** (only if a native-21 enclosure is available) | L no pan at 40 kHz, in the carrier | 77.0 µH (0.950 × free) | record |
| **M7 insulation** | R43's hipot, winding to bars/carrier screws; coil-NTC levels (3000 V rms 1 min after humidity, PD < 10 pC) if the pad is fitted | — | R43 guide |

## 3. Tune to inductance (step W8)

1. Measure free-air L at 40 kHz with the spare turn wound (M2, 40 kHz only), outer lead dressed in its final route.
2. Run `.venv/bin/python model/tune.py --L <measured> --outer 7.46`. It scales the model's trim curve by measured/model and lists every state with:
   - predicted L;
   - the model's loaded L on cast iron and 430;
   - rim heating share.

   It names the state nearest 81 µH inside 76–86 µH.

   | State | Outer turns | L free (µH) |
   |---|---|---|
   | R1 + spare | 7.46 | 89.9 |
   | R1 | 6.46 | 81.1 |
   | −0.5 | 5.96 | 76.8 |
   | −1 | 5.46 | 72.5 |

   Each half-turn is ≈ 4.3 µH (≈ 5 %). Rim share is 32 / 29 / 27 / 25 % on the 430 pan.
3. Unwind that many half-turns from the outer end, re-dress the lead, re-measure, and record.
4. **Limits:**
   - **Never below 5.46 outer turns.** At 4.96 the cast-iron loaded L is 39.8 µH, under the 41.5 µH floor.
   - If no allowed state lands in the window, the model is off by more than ~5 %:
     - keep the coil (it is still a measurement);
     - record the ratio;
     - cut the next former with a re-split inner section (whole inner turns keep the 75° crossover: 13.47 or 15.47 turns; `L_fit_coef_uH` in `model/results/free_air.json`, scaled by the measured ratio).
5. **Different stock Litz:** OD changes the bundle height by (OD − 2.4)/2: +0.075 mm for OD 2.55, an L effect below 0.2 % (`fidelity.py` bundle_z+0.3 gives −0.74 %). Strand construction changes R, not L. So the trim table holds for any of the listed Litz; only the R pass levels need the construction column of ORDER-LIST.md.

## 4. Traveller sheet (copy per coil)

```
Coil ID ____  date ____  former route A / B / C, ID ____  Litz: maker ____ construction ____ lot ____  OD (5 pts) __ __ __ __ __ mean ____
Bars: lot ____  M1 L (10 kHz, 20 t): __ __ __ __ __ __ __ __ __ __ median ____   dims ok Y/N
Tension used ____ N (scale reading ____ kg)   centre lead free length ____ mm
Inner end at tally 14 + 170 deg  Y/N    crossover to r93.4 @ 90 deg  Y/N    spare end at tally 21 + 352 deg  Y/N
Tune: L40 with spare ____ uH  -> tune.py ratio ____  -> state ____  -> L40 after ____ uH   final outer turns ____
M2 L (20/30/40/50/60): ____ ____ ____ ____ ____ uH   Rs: ____ ____ ____ ____ ____ mOhm   temp ____ C
M3 R_dc ____ mOhm @ ____ C       scrap termination qual: sample 1 ____ mOhm/m  sample 2 ____ mOhm/m
M4 pans (name, D, base thickness; L40 / Rs40 / L at 20 and 60 kHz): ______________________________________________
M5 ring-down: C ____ uF  f0 ____ kHz  tau ____ ms  -> R ____ mOhm
Bonded after tune Y/N   NTC fitted Y/N   M7 hipot ____
```

## 5. First power (on native-21; the power stage owns energisation)

These are additions to the energisation review, not a replacement for it:
- Run first at the shipping **17.5 A** ceiling.
- With stock class-155 Litz, **stop at 130 °C on any winding thermocouple** (README D4). Spec row 6's 150 °C mean applies to the class-200 qualification coil.
- **Do not put an aluminium pan on it** until the firmware has a pan-detect probe (README F3). The model puts the R1 coil at 28–36 A RMS at the loop's 60 kHz start, which crosses the CT trip band.
- Log f, lag, I_rms, P_in and the f_res fit for every pan in M4. Those logs plus M4 are the data that confirm or retire each model number.
