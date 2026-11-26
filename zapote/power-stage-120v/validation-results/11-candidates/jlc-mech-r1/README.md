# jlc-mech-r1: are Temper's mechanical parts ready for JLCCNC / JLC3DP?

Study, 2026-11-25. Audit only:
- Nothing was ordered, uploaded or sent, and no supplier was contacted.
- No CAD or workspace build was run. The only tool runs were reads: `ezdxf` opened two DXFs from `~/.local/share/temper/cadenv`.
- Nothing in `hardware/` was touched.

**Inputs.**
- `../bench-sink-r1/` at f57601ea4: README, `results/*.dxf|svg|md`, `scripts/bench_params.py`, `scripts/bench_cad.py`, `sources/`.
- `../../08-manufacturing-package/native-21/owner-items/m11/`.
- `../jlc-max-r1/README.md` (BR1 on boards #2 and up).
- Main checkout `output/temper-manufacturing-r43/` (quote package, catalog, `design/r43/HANDOFF.md`).
- `output/temper-airflow-r1/HANDOFF.md` (the R45 jet box).
- `output/temper-knob-contract/gc1-machined/`.

**R45 does not exist.** `output/` has no `temper-manufacturing-r44` or `-r45`; R44 is reserved for the owner-controls program (`output/temper-owned-controls/`). R43 (2026-10-12) is the latest enclosure. It was built on native-21 stage 13 with the M11 AlN stack, not on s57 with JLC-soldered FETs (OPEN-ITEMS S32).

## 0. Answer

**Only three items should go with the s57 bench lot. Only one of them, the clamp bar, is a real JLCCNC part.**
- **Clamp bar.** Small gap: a STEP file and a one-page drawing.
- **FR-4 pressure pads.** Small gap: an outline file. These are a JLCPCB bare-board job, not JLCCNC.
- **Sink drill template** (optional). It does not exist yet.

The bench sink itself is a catalogue Wakefield 511-3M:
- JLCCNC publishes no service for machining a customer-supplied part (§3).
- Its BR1 hole is drilled at a measured seat height by design.

So the owner drills and taps it, as `bench-sink-r1` §6.1 already plans. The brackets, plywood base, SIL PAD strip and shims are hand parts or parts selected at assembly.

**Nothing in the R43 enclosure should be ordered now.** Every R43 custom part either waits for a change that R45 has to make, or is outside what JLC offers:
- R45 changes: the s57 / S32 M11 interface, PS3 changing to MPM-90, the D-22 envelope growing to 130 × 85, the jet box with base flow (S24), UI Rev 2 and the knob contract;
- outside JLC: G11, PEEK, 301 spring steel, MIL-DTL-5541 chem film, glass, ceramic, moulded silicone.

The R43 sheet-metal files are in good shape (STEP plus mm DXFs with closed cut polylines). Their systematic gaps against JLCCNC are:
- US gauges (0.050 / 0.080 / 0.125 / 0.160 in) against JLCCNC's metric thickness list;
- chem film, which JLCCNC does not list. Its "conductive anodizing" is not a recognised PE-bond finish.

The knob contract's GC1-M1 metal parts are the one enclosure-side line that is nearly quotable at JLCCNC. They belong to the knob programme, not to s57 or R45.

## 1. Ranked table

Readiness:
- **ready now**: upload as is;
- **small gap**: hours of desk work, no new design decision;
- **not ready**: a design decision or a missing part model;
- **not JLC**: a process or material JLC does not publish.

| # | Part | Process | Readiness | Gaps | When |
|---|---|---|---|---|---|
| 1 | Bench clamp bar, 6061-T6, 130.5 × 25.4 × 9.525. 4 flat-bottom Ø9.53 × 7.0 pockets, 2 × Ø4.5 through, BR1 driver slot 6.5 wide | JLCCNC CNC | **small gap** | (a) No STEP. `bench_cad.py` is stdlib-only and writes 2D only; about 30 lines of build123d in `~/.local/share/temper/cadenv` (0.11.1 present) from `bench_params.BAR`, `POCKET_DEPTH` and the drill table would emit it. (b) No PDF: pocket depth 7.00 ± 0.05 needs a drawing (spring preload), plus hole positions. (c) **The slot depends on BR1's seat height** (§2). (d) Finish **as machined, deburred, no anodize**: the bar is on the PE layer, and anodize would isolate it from the sink's M4 screws. (e) Quantity not stated; order 2 (1 + spare). No threads, so no thread callouts are needed | **order with s57 bench lot** |
| 2 | FR-4 pressure pads, 14 × 16, 1.6 mm (× 4 + spares) and 0.8 mm (× 4 + spares) | JLCPCB bare FR-4 (no copper), or JLCCNC CNC in "FR4" | **small gap** | Needs a board outline per thickness, panelised with break tabs (EST: JLCPCB's minimum board size not read). The ±10 % thickness is already in `FR4_T` / `FR4_THIN_T`, so the shim windows hold. The fallback is BOM lines 5 and 6 (G-10 sheet, hand cut) | **order with s57 bench lot** (optional) |
| 3 | Sink drill template (proposed, not designed): a 132.33 × 76.2 plate with pilot holes at the drill-table u/v and a reference edge, so the owner can drill the 511-3M without a mill | JLCCNC sheet metal (304 or 5052, 2–3 mm) | **not ready** (does not exist) | It needs a STEP; JLCCNC's sheet-metal guideline says "3D (Required): STEP". Leave the BR1 hole off; it is scribed from the measured seat height. Worth it only if the owner has no drill press or DRO | with s57 bench lot, if wanted |
| 4 | Bench sink: Wakefield 511-3M (6063 base, bonded fins), drilled and tapped. 2 × M4 bar screws, M3 NTC, M3 TCO clamp, M4 PE bond, **BR1 M3 at measured height** | Catalogue part, then owner drill and tap | **not JLC** | JLCCNC publishes no secondary machining of supplied parts. A JLCCNC-machined replacement sink would lose the catalogue R_SA every thermal verdict uses. Drill-table defects are in §2 (depths exceed the 5.6 mm base; flatness parameter mis-scaled) | owner, after receipt (§6.1) |
| 5 | Sink brackets: 1-1/2 × 1-1/2 × 1/8 in Al angle, 2 × 70 mm, Ø8 pivot and lock holes | Hand (or JLCCNC sheet metal) | **not ready** for JLC | There is no bracket drawing: the Ø8 positions and the base fixing holes are undimensioned. The M4 holes through the sink's outer fin are **match-drilled** with the sink on its gauges. Bought angle and a hand drill is the right route | owner |
| 6 | Baseplate: plywood 400 × 300 × 18, window plus BR1 extension, standoff holes | Hand / local | **not JLC** | Wood; the window size comes from `bench_params.WINDOW*` | owner |
| 7 | SIL PAD 2000 strip, 114.5 × 30, plus a Ø4 hole punched at the drilled BR1 position | Hand cut from the sheet | **not JLC** | The punch position follows the BR1 hole | owner |
| 8 | FET shims (16 × 22) and BR1 shim (28 × 17), 0–2.2 mm in 0.025 steps | Hand, from shim stock | **not orderable blind** | Selected from feeler gaps by `shim_select.py` per board | owner, at assembly |
| 9 | Spacers M4 × 10 (RAF M0539-4-AL) | Purchased | n/a | – | BOM line 7 |
| 10 | Knob GC1-M1 shell, 6061-T6 (Ø56.30 × 10.56, 3 × M2 blind) and deck (Ø47.10 × 5.00, 3 × M2 through) | JLCCNC CNC, turned, with anodize | **small gap** | STEPs exist (`metal/*.step`). The shop sheet `Cotizacion-GC1-M1.pdf` is Spanish and dated 21 Nov. Its deck page describes the old "disco giratorio", but `deck_6061_x1.step` was re-exported 24 Nov as the stationary deck (BUILD.md), so **redraw the deck page**. JLCCNC states no minimum thread size; confirm M2 × 0.4-6H. Shell: clear anodize, threads masked. Deck: bare | knob line (independent of s57 and R45) |
| 11 | Knob brass spacers × 6 (3 mm) | JLCCNC CNC (brass H59) | **small gap** | STEP only, so a drawing is needed if any tolerance is tighter than the default | knob line |
| 12 | Knob polymer: carrier, dome cover, keeper A5, 3 + 3 clamps (PETG HF, owner FDM) | Owner A1, or JLC3DP | **small gap** if JLC3DP | PETG is not among the JLC3DP materials read. In the 60–80 °C knob envelope, the SLA resins (HDT 46–60 °C) are out; MJF PA12-HP (175 °C @ 0.45 MPa) or JLC Temp resin (101 °C) are the candidates, and changing the material reopens the snap and strain checks | knob line |
| 13 | Knob C17200 photo-etched guides, brass backing disc | Photo-etch / laser | **not JLC** | – | knob line |
| 14 | R43 M11 spreader bar, 6061, 117 × 7.8 × 59.4: PE ear, M4 clamp-comb holes, 4 × Ø3.4 bond holes with spot faces, flatness ≤ 0.03, Ra ≤ 0.8 | JLCCNC CNC | **not ready** | STEP exists. But: S32 (rigid 2 mm AlN tiles need ≤ 0.05 mm coplanarity, which JLC-soldered FETs cannot give); no PDF for the threads, flatness and grease or mask zones; the finish wants chem film with masks (not offered); geometry is still native-21 stage 13 | **defer to R45** |
| 15 | R43 FR-4 pressure strip 117 × 14 × 3.0 | JLCCNC "FR4" / JLCPCB | **not ready** | Tied to the M11 stack (S32) | defer to R45 |
| 16 | R43 clamp comb, 301 full-hard spring steel, ~0.5 | Sheet metal | **not JLC** | JLCCNC sheet stainless is 201 / 304 only | defer to R45; spring-steel shop |
| 17 | R43 sink S8, 6063 extrusion, 8 mm base, 15 × 1.5 fins on a 3.0 gap, 40 deep | Custom extrusion plus machining | **not ready** | Exists only as `electronics_native21_sink_ENVELOPE` (an allocation): no part model. Its 3 × 40 mm fin slots break JLCCNC's own cavity-depth rule ("five times their length") for a machined version | defer to R45 / native-22 |
| 18 | R43 sink cradle, 5052 2.0, formed C, float slot | JLCCNC sheet metal | **not ready** | Follows item 17. Chem film | defer to R45 |
| 19 | R43 fascia P3, 5052 3.0, 2 bends, D-holes, Grayhill counterbore from inside, 4 × PEM IFHA-M3-10, lens window | JLCCNC sheet metal | **not ready** | STEP exists, but there is no flat DXF in the package. The counterbore is a machining step on a bent part. PEM IFHA is not named by JLCCNC (it lists "riveting nuts, studs and screws ... M2.5-M10"). Chem film. The controls are changing (R44 owner controls, knob contract, UI Rev 2) | defer to R45 |
| 20 | R43 bottom chassis (baseplate), 0.080 in 5052, 3 bends, many PEMs (CLA, CLS, FH4 studs), 6 × Ø10 × 1.5 underside spot faces, M3 tapped | JLCCNC sheet metal | **not ready** | STEP plus DXF (mm, closed LWPOLYLINEs, CUT/BEND layers: good). Open: 2.03 mm is not on JLCCNC's list (2.0); spot faces and taps need a drawing; PEM part numbers need JLCCNC confirmation; chem film. The native-22 floorplan moves H1/H3/H4 (RELAYOUT S12), and D-22 asks R45 for 130 × 85 | defer to R45 / native-22 |
| 21 | R43 P1 seat ring (0.125 in, one piece, flatness 0.30) and P2 fence ring (0.160 in, black top, conductive underside) | JLCCNC sheet metal (laser cut) | **not ready** | Clean DXFs and STEP. Open: gauges (3.175 → 3.0, 4.064 → 4.0) change the glass stack; JLCCNC publishes no flatness; chem film (P1); masked black finish (P2) | defer to R45 |
| 22 | R43 P4 U-wrapper (0.050 in), rear service door (0.050 in), door exhaust rib, louver cassette (1.5 / 2.0) | JLCCNC sheet metal | **not ready** | 1.27 mm is not offered (1.2 or 1.5). Chem film; PEM FHA / CLS; perforations | defer to R45 |
| 23 | R43 airflow ducts: push hood (1.0, bends at 24° / 42° / 66°), exhaust plenum (1.0), coil bleed duct F2 (0.5) | JLCCNC sheet metal | **not ready** | STEP exists. S24: 28 A needs jets **plus** a both-face base flow, which is a second fan R43 does not have. The jet box adds a hood hole with 2 PEMs and a 30 × 25 plenum cut (airflow-r1 items 3–4). Non-90° bends to confirm. Chem film | defer to R45 |
| 24 | R45 jet box (R45-JET-BOX) and F3 feed duct: 1.0 mm walls, 8 × Ø3 jets, 10.5 × 7 manifold, 87 long | Prototype G11 machined and bonded; production PPS-GF40, UL 94 V-0, RTI ≥ 150 | **not ready** | Envelopes only (`temper-airflow-r1/cad/fit_check.py`). G11 is not a JLCCNC material (FR4 is). JLC3DP has no UL94 or RTI on any nylon or resin read, so it serves only as an **uncredited airflow test article** (MJF PA12-HP); it sits 1.0 mm from the FR-4 strip beside HOT tabs | defer to R45 |
| 25 | R43 brackets: PS3 bracket, PS3 J11 anchor, EMI module stand, inlet bulkhead, harness lane brackets and mains anchors, door hook brackets (301 half-hard) | JLCCNC sheet metal (5052); hook brackets not JLC | **not ready** | PS3 changes from IRM-60 to MPM-90 (REALIGNMENT, same 109 × 52 × 33.5 case, but clearances unchecked). The D-22 stand grows with the 130 × 85 module. The hook brackets are 301 (not offered). Chem film. US gauges | defer to R45 |
| 26 | R43 OLED carrier, 6061 CNC, M2 / M3 tapped, clear anodize | JLCCNC CNC | **not ready** | UI Rev 2 pending; "OLED electrical isolation to qualify" (catalog) | defer to R45 |
| 27 | R43 SELV tray, FR-4 1.6 V-0 routed bare board | JLCPCB bare board | **not ready** | The process is clean, but the tray follows the C51 controller (no layout yet) | defer to R45 |
| 28 | Coil former (G11, 10 mm, class 180), coil carrier (G11, 6.35 mm, 79 jets), coil plenum floors (G11, 1.5 mm) | CNC in G11 / FR5 | **not JLC** | JLCCNC plastics are ABS, FR4, PA6, PC, PMMA, POM and Bakelite, with no G11. JLC3DP nylons fall to 54–60 °C HDT at 1.8 MPa and state no UL94 or RTI, so they are **ruled out** beside the coil (reinforced insulation, RTI ≥ 150 °C) | defer; laminate CNC shop |
| 29 | Pan-sensor PEEK body, plunger, spring washer, gap key | CNC in PEEK | **not JLC** | No PEEK at JLCCNC. JLC3DP's FDM PEEK (HDT 144 °C @ 1.8 MPa, "UL94 V0" raw material) cannot hold the Ø0.8 / 1.5 features, and the cartridge sits under the pan | defer; PEEK turning shop |
| 30 | J13 barrier (Formex GK-62), sink Nomex 410 cover, glass top, lens, alumina cap, silicone boot, wave spring | Die-cut / glass / ceramic / moulding / spring | **not JLC** | – | defer to R45 vendors |
| 31 | R43 turned push-on D-bore knob | JLCCNC CNC | **do not order** | Superseded by the knob contract (row 10) | – |

R43's `design/metalwork/F10*/F12*` are R11 welded service-fixture blanks. They are not part of the current enclosure and are out of scope.

## 2. Bench-sink-r1 findings (fix before machining; none changes a committed verdict)

**DXF (`results/bench-sink-r1.dxf`) is a drawing sheet, not a fabrication file.**
- It has an ENTITIES section only: no HEADER, so no `$INSUNITS` (units are mm only by convention), and no layer table.
- It uses LINE, CIRCLE and TEXT only, with **no closed polylines**: `ezdxf` finds 0 LWPOLYLINEs.
- It mixes the assembly views A–C with the part views D–F on one sheet. Layers are OUTLINE, HIDDEN, INSUL, DIM, NOTE and PE; the sink and bar outlines are on PE.

None of this blocks the bar: JLCCNC CNC quotes from STEP. If the template (row 3) goes ahead, write a separate per-part DXF with closed outlines on a CUT layer and `$INSUNITS = 4`.

**Drill-at-measured-height and match-drilled features. None can be ordered blind.**

| Feature | Why it can't be ordered blind | Handling |
|---|---|---|
| Sink BR1 M3 hole, v = (seat + 11.0 + 0.2) − 4.5 | Board #1: seat height of a **loose** GBJ2510 (the drawing does not place the H feature). Boards #2 and up: BR1 is JLC-soldered (jlc-max-r1 §4), so the hole uses the **as-soldered** seat. jlc-max-r1 also says to re-derive the −0.610 … 1.490 mm shim range for a soldered BR1 | Owner drills it, after measuring. **One sink per BR1-fitted board**, or plug and re-drill. If the template is made, leave this hole off it |
| Bracket M4 holes through the outer fin | Match-drilled with the sink on its 4.5 mm gauges | Owner, at fit |
| SIL PAD Ø4 BR1 hole | Punched at the drilled hole | Owner |
| **Bar BR1 driver slot** (new finding) | `BAR_SLOT` is centred on `BR1_HOLE_Z` = 13.4, which uses `BR1_SEAT_Z_EST` 2.2. In the bar it runs v 3.4–11.4. An ISO 4762 M3 head (dk 5.5) passes the 6.5 slot only while the hole stays within **±1.25 mm** of the EST seat (v 6.15–8.65). The seat is unmeasured | **Two-step**, either way: (a) order the bar from JLCCNC with pockets and end holes only, and cut the slot at home after measuring (`drill-table.md` already says "two 6.5 holes + file"); or (b) lengthen the slot so it covers any plausible seat, after checking the bar section at the slot (EST; not checked here). Recommendation: (a) |
| Shims, pad choice | Set from the measured gaps | `shim_select.py` |

**Other defects in the committed drawing data:**
1. **Tap depths exceed the sink base.**
   - The drill table calls for bar screws "drill 3.3 × 10, tap M4 8", NTC and TCO "drill 2.5 × 6", and the bond "drill 3.3 × 7".
   - The 511-M milled base is A = 5.6 mm (`SINK_BASE_T`, Wakefield profile 6438-1). Every one of these breaks through into a fin channel or a fin root.
   - Fin positions are not modelled (pitch 8.7).
   - Restate them as "through the 5.6 base, full thread". Check each u against the fin pitch so that no hole lands on a bonded-fin root (the epoxy joint) and no screw tip touches a fin.
2. **`SINK_FLATNESS = 0.05 mm/mm` is 25× too coarse.**
   - It copies the Wakefield catalogue's own conversion ("0.002 in./in. (0.05 mm/mm)"); 0.002 in/in is 0.002 mm/mm.
   - No tool reads the parameter, so no verdict moves. The feeler-gauge shim selection measures the real face anyway.
   - Over the 58 mm FET row, 0.002 mm/mm is about 0.12 mm.
3. **The BR1 washer does not fit through the slot.**
   - §6.3 step 4 passes "M3 × 10 SHCS and flat washer through the bar slot". An ISO 7089 M3 washer is 7.0 mm OD, and the slot is 6.5 wide.
   - Fix: use an ISO 7092 small-series M3 washer (6.0 OD), or place the washer on BR1 before it is lowered in.
4. **Thermal face finish.**
   - The 511-3M ships "without finish" (Wakefield note 5) and is PE-bonded, so do not anodize it.
   - Anodize is not credited for insulation anywhere; the SIL PAD is the barrier. The README's "deburr and stone the face" stays the critical operation.

## 3. What JLCCNC and JLC3DP publish (read 2026-11-25 by web-fetch subagents; short quotes as returned)

**JLCCNC: files**
- CNC: "STP files are recommended as the basis for CNC machining" (https://jlccnc.com/help/article/introduction-of-stl-stp-file-formats).
- Sheet metal: "3D (Required): STEP (.step, .stp)"; 2D: "PDF, DWG, DXF, JPG, PNG" (https://jlccnc.com/help/article/sheet-metal-fabrication-guidelines).
- The CNC FAQ names "2D drawings in DWG or DXF format" (https://jlccnc.com/capabilities/cnc-machining-service). The design guideline says a "2D drawing annotated with tolerances must be provided" (https://jlccnc.com/help/article/CNC-Machining-Design-Guideline). So send a PDF and a DXF of the drawing.
- No page says a DXF alone is enough for laser-cut flats.

**JLCCNC: threads** (https://jlccnc.com/help/article/CNC-Machining-Design-Guideline)
- "Threaded holes should be annotated with the thread parameters and depth".
- Recommended thread length ≤ 3 × the hole diameter, with "an unthreaded length of at least half the hole diameter" in blind holes.
- Sheet metal: "Only metric M specifications are accepted" (https://jlccnc.com/help/article/sheet-metal-fabrication-file-requirements).
- No minimum thread size is stated.

**JLCCNC: tolerances and finish**
- "If no tolerance is provided, parts will be made with standard tolerance (±0.1mm or higher)" (design guideline).
- The capabilities page gives ISO 2768-m, tightest ±0.02, and roughness "Ra 0.8, with Ra 3.2 and Ra 1.6 also available" (https://jlccnc.com/capabilities/cnc-machining-service).
- Flatness and GD&T are not named, so put them on the PDF and ask.
- Sheet metal: general ±0.2, cutting ±0.1, bending ±0.3, angle +1.0°, holes ±0.1 (sheet-metal guidelines).

**JLCCNC: materials and sizes**
- CNC metals: 6061, 7075, SUS304, 45#, brass H59, copper T2.
- CNC plastics: ABS, FR4, PA6, PC, PMMA, POM, Bakelite. **No PEEK, no G10 or G11 by name** (https://jlccnc.com/help/catalog/2201-Plastic-CNC-Machining).
- Sheet metal: 5052 (the only aluminium), SS201, SS304, cold-rolled and galvanised steel, **no 301 or spring steel**.
- Sheet thicknesses: "0.5 / 0.8 / 1.0 / 1.2 / 1.5 / 2.0 / 2.5 / 3.0 / 4.0 / 5.0 / 6.0mm".
- Sheet maximum length 800 mm (https://jlccnc.com/help/article/materials-supported-in-sheet-metal-fabrication).
- CNC "Up to 950 × 560 × 120 mm for selected 3-axis machining setups".

**JLCCNC: finishes and hardware**
- Anodizing, hardcoat, "Conductive Anodizing" ("An anodizing process that creates a conductive surface coating"), bead blast and more. **Chromate conversion, chem film and Alodine are not mentioned** (https://jlccnc.com/capabilities/cnc-machining-service; https://jlccnc.com/capabilities/sheet-metal-fabrication).
- As machined: "Parts are machined and deburred, sharp edges are chamfered".
- Riveting: "riveting nuts, studs and screws with various specifications of M2.5-M10"; PEM is not named.

**JLCCNC: supplied parts.** No page covers secondary machining of a customer's part. Treat it as unavailable unless support says otherwise.

**JLC3DP: HDT as published, no service temperature, and UL94 only where noted** (pages under https://jlc3dp.com/help/article/)

| Material | Process | HDT | Notes |
|---|---|---|---|
| 8001 / Imagine Black / 8228 / 9600 / LEDO 6060 / 9000HE | SLA | 53 / 46 / 56.4 / 59 / 56 / 60 °C @ 0.45 MPa | "Not suitable for ... high temperatures" (8001) |
| JLC Temp | SLA | 101 °C @ 66 psi | – |
| PA12-HP | MJF | 175 °C @ 0.45 MPa | Tolerance ±0.3 within 100 mm |
| PA11-HP | MJF | 185 °C @ 0.45 MPa, **54 °C @ 1.82 MPa** | – |
| 3201PA-F / 1172 Pro / 3401GB | SLS | 147 / 179 / 150 °C @ 0.45 MPa | 3401GB: 60 °C @ 1.8 MPa |
| ABS / ASA / PLA | FDM | 98 (1.8 MPa) / 97.8 / 65 °C | – |
| PA12-CF | FDM | 105 °C @ 1.8 MPa | – |
| PEEK | FDM | 144 °C @ 1.8 MPa | "Flammability (raw material) UL94 V0" |

- Threaded inserts: M3 / M4 / M5 only; "Custom insert types and specifications are not supported"; insert hole wall ≥ 3.0 mm (/threaded-insert-service).
- Printed threads: "The minimum recommended thread for printing is M6" (/212-3D-Printing-Design-Guideline).

**Consequence.** No JLC3DP polymer states a UL94 rating for the printed part or an RTI. Under load the nylons fall to 54–60 °C. So no JLC3DP polymer may be credited as insulation, or used as structure near the coil, pan, sink or HOT copper (rows 24, 28 and 29). JLC3DP fits fit-check and airflow test articles, and cool parts (knob, row 12).

## 4. What would change this

- **JLCCNC confirms secondary machining of a supplied 511-3M.** Row 4 becomes a JLCCNC job for the fixed holes (two-step: BR1 left for the owner), and the template (row 3) is dropped.
- **JLCCNC confirms that its conductive anodizing is a chromate conversion** (MIL-DTL-5541 Class 3 equivalent), or the certifier accepts the coating for PE bonds. The R43/R45 sheet-metal rows lose their finish gap.
- **R45 is cut on s57 with an S32 answer.** Rows 14–27 are re-audited against it. The gauges must be restated in metric before any JLCCNC quote.
