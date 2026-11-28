# Bench heatsink r1: thermal mount for the first native-21 boards

**2026-11-28: fab package for the clamp bar (JLCCNC) and the FR-4 pads (JLCPCB) is in `fab/`; see §12.** Nothing was ordered or uploaded.

**2026-11-25 (stage 57, DECISIONS 87): the FET holes are 1.8 mm.** Lead play grows 0.15 mm, so the thickest FET shim is 2.2 mm (was 2.0). Every verdict in `results/` is unchanged; re-run with `scripts/bench_*.py`. The bracket slots need ± 1.05 mm in y (was ± 0.90; they have ± 2.0).

**2026-11-25 (DECISIONS 91): reversed DECISIONS 86 — JLC again solders Q2 / Q3 / Q5 / Q6 (consigned).** §2's FET remark and the JLC-soldered gauge-and-shim procedure below apply again (with the stage-57 1.8 mm hole caveat above: only the center drain shoulder seats, and the thickest shim is 2.2 mm).

Study, 2026-10-18. Branch `study/bench-sink-r1`, from `codex/power-stage-integration` @ f9d945326.

**Purpose.** A bench sink and mount that let the owner run COMMISSIONING steps 3–8 and 9a ("heat a pan"):
- on an isolation transformer, or on an isolated current-limited DC supply;
- on the native-21 stage-53 board;
- without the production M11 AlN stack.

**Owner decisions, 2026-10-18 (revision 2 of this study).**
1. **JLC solders Q2, Q3, Q5 and Q6** (consigned from one DigiKey lot). The sink, strip and clamp are fitted to the soldered devices afterwards. This replaces revision 1's "seat on the sink, then solder".
2. **BR1 is DNP at JLC.** The owner fits it (through-hole) before COMMISSIONING step 5, on a board whose FETs are already soldered and possibly already clamped. While BR1 is out, PS2 runs from the isolation transformer and the bus from the isolated DC supply, with no back-feed path.
3. **Bench TCO: the DF110S on the sink, with spares** (it is one-shot).

**Status.** No hardware has been built or bought. No supplier was contacted, nothing was pushed, and no Rust or layout build was run.

**Rule for this file.** Every number below comes from a committed tool, named in its row, or is a parameter in `scripts/bench_params.py`. Parameters carry a source tag (`sources/SOURCES.md`) or are marked EST.

| tool (run from this folder) | output |
|---|---|
| `python3 -I scripts/bench_tolerance.py` (exits 1 if anything fails to close) | `results/tolerance.md`, `.json` |
| `python3 -I scripts/bench_thermal.py` | `results/thermal.md`, `.json` |
| `python3 -I scripts/bench_insulation.py` (exits 1 on any fail) | `results/insulation.md`, `.json` |
| `python3 -I scripts/bench_cad.py` | `results/bench-sink-r1.dxf`, `.svg`, `results/drill-table.md` |
| `python3 -I scripts/compare_mounts.py` (revision 3: common sink vs per-device sinks vs thick gap pad) | `results/compare.md`, `.json` |
| `python3 -I scripts/shim_select.py gaps.csv` (at assembly; exits 1 on a reject) | the fit sheet for the measured board (`example-gaps.csv` shows the format) |
| `~/.local/share/temper/cadenv/bin/python -I scripts/bench_bar_step.py`, then `bench_bar_drawing.py`, then `bench_bar_verify.py` (build123d; exit 1 on a disagreement or FAIL) | `fab/clamp-bar/`: STEP, PDF, DXF, `step-check.md` (§12) |
| `~/.local/share/temper/kikit-venv/bin/python -I scripts/bench_pads_gerber.py`, then `cadenv/bin/python -I scripts/bench_pads_verify.py` (KiCad 10 + KiKit; gerbv; exit 1 on a FAIL) | `fab/pads/`: two Gerber zips, renders, `pads-check.md` (§12) |

All tools use the standard library only and each runs in about a second. `bench_thermal.py` imports the device study's `thermal.py` loss models and asserts on their constants. `bench_mech.py` holds the soldered-lead mechanics shared by the others.

## 0. Answer

**Revision 3 (coordinator, 2026-10-18): one sink per device was evaluated against the shim design. The bench keeps one
common sink with selected shims** (D10, `results/compare.md`). Per-device sinks lose on three counts:
- **No catalogue part fits.** Every TO-247 sink in the DigiKey read is 19.4 mm or wider; the 18 mm pitch allows 14.15–17.50 mm. Per-device would mean custom sliced sinks and clips: more hand work, not less.
- **The catalogue sinks that fit the size class fail 22 A.** With natural convection the hottest FET sink reaches 111–173 °C, above the 95 °C firmware trip; even 8 °C/W at 500 LFM gives 108 °C. Only 35–42 mm-wide parts hold it.
- **Sensing breaks.** BR1's 25.52 W needs its own sink at ≤ 1.96 °C/W. That makes BR1's sink the hottest, so the TCO and NTC would sit there and see none of the FETs.

A thick soft gap pad (GAP PAD 5000S35, no shims) was also checked. Its usable window, 0.635 mm at 0.125 in, misses the no-remark spread. It only works after the same gauging, at Rcs 4.15 °C/W.

**Does the SIL PAD 2000 strip plus the spring clamp still close every JLC-soldered tab? No. With a selected shim per device, yes.**

Source: `results/tolerance.md`.

- **Per-device tab offset.** A soldered TO-247's tab plane sits up to **± 1.050 mm** from the footprint. The terms are:
  - JLC hole position ± 0.075;
  - lead play in the 1.8 mm hole (stage 57), ± 0.055–0.775 (finished hole 1.72–1.93, lead 1.0–1.4 × 0.38–0.89; the minimum is corner-limited, c60);
  - package A1, ± 0.20.
- **Spread across the four FETs** (what one flat sink face must meet):
  - **0.270–0.570 mm** if JLC honours the order remark (§2);
  - **1.800–2.100 mm** if it does not.
- **What can close a gap once the device is soldered: 0.0195 mm.** That is 0.010 of strip compliance (EST) plus 0.0095 of elastic lead translation. A soldered device is up to 11 924 N/mm stiff in translation, so the clamp cannot move it.
- **The fix.** A shim under the strip at each device, selected from feeler-gauge measurements in 0.025 mm steps, leaves ≤ 0.0125 mm: it closes. Clamp force is kept inside 60–102 N by choosing the FR-4 pad per device:
  - 1.6 mm pad for shims 0–0.897 mm;
  - 0.8 mm pad for 0.596–1.467 mm;
  - no pad for 1.306–2.337 mm.

  Together these cover the worst 2.100 mm spread.
- **Lean.** The clamp straightens lean elastically. The inspection limit is **0.0112 rad (0.64°) per device relative to the row mean**, which is a 0.179 mm gap difference between the gauge heights. At that limit the strip still sees ≥ 45.0 N. Board bow is common to all four devices, up to 0.0547 rad; a floating sink takes it.

**Thermal: the bound case still runs.** The bound is the design shim (2.2 mm, three greased faces) at the lowest guaranteed force (45 N) on every FET at once (`results/thermal.md`). Results at 30 °C ambient, natural convection, ZVS loss basis D:

| ceiling | sink | Tj FET (bound) | Tj BR1 |
|---|---|---|---|
| **17.5 A** (ships) | **72.8 °C** | **87.1 °C** | 97.4 °C |
| 17.5 A at 40 °C ambient | 83.8 °C, so **fan** | 99.2 °C | 108.5 °C |
| **22 A** (headroom) | 85.7 °C, so **fan** | 111.6 °C | 110.3 °C |
| 28 A | 125.7 °C without a fan | 183.3 °C: **not allowed without the fan and a measured interface** | 150.3 °C |

- **Fan rule.** To hold the sink ≤ 80 °C (6 K under the TCO's 86 °C hold), R_SA must be ≤ 1.073 / 0.825 / 0.564 °C/W at 17.5 / 22 / 28 A. The 511-3M is 0.90 °C/W without a fan, so the fan is needed above 17.5 A.
- **28 A** needs the fan, and needs §7's measured Rcs to beat the bound. With the sink held at 86 °C the bound gives 132.8 °C; at the 95 °C firmware trip it gives 144.3 °C.
- **Lost ZVS.** The sink-sensed trips do not protect the junction: the bound Tj is 179.0 °C at the 95 °C firmware trip, 17.5 A. Step 4's ZVS check and the lag latch protect that case.

**Insulation (`results/insulation.md`).** Everything passes:
- with the sink face anywhere in **0.531–2.631 mm**;
- with shims under the strip;
- with bodies floated up to 1.0 mm;
- with any of the three pad options.

Tightest values: creepage 4.2 mm (floor 4.0); clearance 3.334 mm for the spring with no pad (floor 1.3); BR1 lead 3.789 mm. The SIL PAD 2000 is rated 9.1× the 622.4 V peak stress.

**BR1 fit with the FETs in place (§6.3).** BR1 is seated on the strip by its own screw before it is soldered, so its fit needs no tolerance from JLC. Its shim behind the strip ranges from −0.610 to 1.490 mm; a negative value is taken by leaning BR1 back 0.0362 rad in its holes. **Preheat: a benchtop hot-air bottom preheater** under a window extension beside BR1, with the board bottom at BR1 held at 100–110 °C (`bench_params.PREHEAT_BOARD_C`). The TCO comes off the sink while soldering.

**Commits.**
- revision 1: c5a448069, 21aa9ed23, 878ffc59d, 49a5de610;
- revision 2: a4e1f3ae5 (tools and results), 9c4dcf404 (README, BOM, sources);
- revision 3: the mount comparison (`compare_mounts.py`, D10); see the git log.

## 1. The mount

- **Sink.** Wakefield-Vette **511-3M**, fins vertical, bonded to **PE**.
  - It **floats** on two brackets: an M4 pivot through each outer fin in a Ø8 hole with a fender washer, plus a second M4 in a Ø8 hole to lock the tilt.
  - The clamp pulls it onto the soldered row, and it settles on the most-proud tab. Then it is locked.
  - Lower edge 4.5 ± 0.3 mm above the board top, set with a gauge.
  - Face y between 0.531 and 2.631 depending on the row; nominal 1.581 (`tolerance.md`).
- **Insulator.** One continuous **SIL PAD 2000 (0.010 in)** strip, 114.5 × 30 mm, behind Q5, Q6, Q3, Q2 and BR1. It hangs 2.5 mm below the sink's lower edge.
- **Shims.**
  - A **selected shim under the strip at each FET**: 16 × 22 mm, ≤ 3 layers, greased, lower edge 1.0 mm above the sink edge.
  - **BR1's shim** (28 × 17 mm) is selected at its dry fit.
  - `shim_select.py` turns the measured gaps into shim thicknesses and pad choices.
- **Clamp.** Screwless.
  - A 6061 3/8 × 1 in bar on two 10 mm spacers.
  - Four Lee LC 055E 03 S springs in 7 mm pockets.
  - FR-4 pads of 1.6 mm, 0.8 mm or none on the package fronts.
  - A 6.5 mm slot in the bar gives a driver access to BR1's screw.
- **BR1.** M3 × 10 SHCS into a tapped sink hole, ≤ 0.56 N·m. The hole is drilled at the measured seat height of a loose part plus the GBJ's S (hole centre 10.8–11.2 mm above the body bottom) plus 0.2 mm.
- **Sensors.**
  - Vishay NTCALUG01A NTC on M3, on the sink face.
  - **Cantherm DF110S** TCO in the J3 loop, under two layers of 3M 5413 and a cushioned loop clamp.
  - Order 1 + 4 spares.
- **Fan.** 120 mm, used above 17.5 A or above 30 °C ambient. It is never credited for a pass.
- **Base.** Plywood baseplate.
  - Nylon M3 standoffs at H1 and H3–H8; H2, H9 and H10 empty.
  - A window under the device row, plus an extension beside BR1 (x 75–115, y 22–45) for the bottom preheater.

The drawing is `results/bench-sink-r1.dxf` (and `.svg`); dimensions are in `results/drill-table.md`.

## 2. JLC order: remark and BOM changes

**What JLC publishes (read 2026-10-18; `sources/SOURCES.md`).**
- Its assembly capabilities page says THT parts are assembled using wave soldering, and that unused holes are protected from solder ingress.
- Its assembly FAQ says parts marked "wave soldering" are assembled manually.
- **No published THT seating, lean or coplanarity rule was found.** Two searches and the capabilities and FAQ pages were checked. So nothing in this design relies on JLC's seating. The remark below narrows the spread if honoured; the shims close it either way.

**Remark to add to the PCBA order** (owner to submit):

> Q2, Q3, Q5, Q6 (TO-247, consigned): please insert each fully, body resting on its lead shoulders and standing perpendicular to the board. Before soldering, push each one toward the board's rear edge (the side its metal tab faces) so the leads bear on that side of their holes, and hold it there while soldering; a straight bar laid across the four tab faces is ideal. Required: tab faces coplanar within 0.2 mm and perpendicular within 1°. Do not bend or trim the leads above the board. BR1: do not fit (DNP); leave its four holes free of solder.

**JLC BOM.** Deselect BR1 (DNP). The prototype lot's BR1 parts are kept for the owner's fit.

**If the remark is honoured,** the spread is 0.270 mm with lot A1 and 0.570 mm with datasheet A1. One or two shim layers and the 1.6 mm pad cover it (`tolerance.md`).

## 3. Decisions

Each decision gives what was chosen, the data behind it, and what would reverse it.

### D1. Sink: Wakefield-Vette 511-3M on floating brackets

- **Data.**
  - 132.33 mm wide `[WAK]`, so it covers the whole row (−12.0 to 120.33).
  - 76.2 mm long along z, fins vertical, 0.90 °C/W natural.
  - Milled base.
  - DigiKey had 25 at $40.69.
- **Why it floats.** The soldered row sets where the sink face must be: anywhere in 0.531–2.631, with up to 0.0547 rad of common tilt (`tolerance.md`). A sink that floats in y and tilt during clamping finds that position itself. The clamp loop is internal: bar, springs, devices, strip, sink. The sink is locked afterwards.
- **Reverses if:**
  - stock runs out: use the 511-6M, same profile;
  - §7's natural R_SA is above 1.073 °C/W: run the fan at 17.5 A too.

### D2. Insulator: SIL PAD 2000, one strip, with selected shims under it

- **Data.** Under the bound, Tj at 17.5 A and 30 °C (`thermal.md`):

  | strip | Tj | Rcs, strip only |
  |---|---|---|
  | SIL PAD 2000 | 87.1 °C | 0.876–1.489 °C/W |
  | K-10 | 89.4 °C | – |

  The shim stack adds 0.953 °C/W (small tab) or 0.592 °C/W (large tab). SP2000's rating is 9.1× the peak stress.
- **Why shims rather than a thicker conformable pad.**
  - A gap filler thick enough to absorb the 1.8 mm worst spread would itself add more than the shim stack.
  - Its compression would vary with each device's gap, so the pressure would too.
  - Shims are flat, conductive, cheap, and re-selectable at every refit.
- **Where the shims go.** Under the strip, on the sink face: they are PE. The strip stays one continuous piece over them, so no new creepage edge appears. Every shim-related path passes (`insulation.md`): tab bottom edge to shim lower edge 6.104 mm, tab top to shim top 9.264 mm.
- **Reverses if:**
  - the remark is honoured and §7's gaps all come out ≤ 0.0195 mm: no shims (unlikely, from the stack);
  - a large step creases the strip at assembly: lay a second strip over the creased zone, or reduce the step with the remark.

### D3. Screwless spring clamp, with a pad chosen per device

- **Data.** Zero-shim device: 68.4–85.4 N. A shim moves the package front toward the bar, adding 18.51 N/mm (`tolerance.md`). The three pad options keep 60–102 N and stay off solid over 0–2.337 mm of shim.
- **Lean.** Straightening a device to the inspection limit costs 13.7 N of spring force, leaving ≥ 45.0 N on the strip (acceptance 45–102).
- **Insulation.** The spring-to-tab paths pass with every pad option. The tightest is 3.334 mm clearance with no pad (`insulation.md`).
- **Bar access slot at BR1.** It sits beyond the last spring, between Q2's pocket and the right end screw, where the bar carries only the end reaction.
- **Reverses if:** §7 shows uneven pressure. Re-gauge, and re-select that device's shim.

### D4. Sink potential: bonded to PE

Unchanged from revision 1.
- A strip fault on the isolated secondary earths one point, which the power-on line-to-PE check finds.
- The touchable sink stays at PE, and the NTC sees no HOT stress.
- Floating and HOT-tied sinks were rejected; see revision 1 in git (49a5de610).
- Tab-to-PE capacitance is 21.1–33.5 pF per tab (`insulation.md`), so the bench's common-mode readings are pessimistic for production.

### D5. TCO: Cantherm DF110S on the sink, in the J3 loop; 1 fitted + 4 spare

- **Ratings.** Tf 110 °C (+0/−5), so it trips at 105–110 °C, above the hardware band's 104.6 °C top. Th is 86 °C, so the sink stays ≤ 80 °C.
- **Why spares.** It is one-shot: an over-temperature trip, or overheating it while soldering (the limit is Tf − 24 °C, `[CAN]`), consumes one. Four spares cost $3.48 at the 2026-10-18 read.
- **During BR1 soldering** it comes off the sink (§6.3).
- **Reverses if:** production fixes a Microtemp G4A rating. Then match the bench part to it.

### D6. Fan: 120 mm Cooltron, never credited

Required for any run above 17.5 A or above 30 °C ambient. R_SA needed for an 80 °C sink: 0.825 °C/W at 22 A and 0.564 °C/W at 28 A (`thermal.md`).

### D7. NTC on the sink face at (77.8, 40)

Unchanged. No HOT stress on it.

### D8. JLC solders the FETs; the sink comes afterwards (owner decision 1)

**Consequence.** There is no seat-before-solder any more. Seating, lean and coplanarity become inspection items.

**Seating.**
- The drain shoulder (b2 2.57–3.43 mm) cannot enter the 1.72–1.93 mm finished hole, so a fully pushed body still stands at L1 (3.85–4.50 mm). Since stage 57 a small gate or source shoulder (b1 down to 1.60 mm) can enter its hole, so pins 1 and 3 no longer guarantee squareness; the drain shoulder spans the hole, and the seating fixture (S32) sets squareness.
- A body floating up is accepted to 1.0 mm. The strip-top creepage allows 2.26 mm (`tolerance.md`).

**Inspection on receipt.** Per FET, check:
- body height;
- lean relative to the row mean ≤ 0.0112 rad;
- then the shim fit, with `shim_select.py`.

A device outside the lean limit is re-seated by the owner (§6.2, last step), or the board goes back to JLC.

### D9. BR1 DNP, owner-fitted at COMMISSIONING step 4b (owner decision 2; COMMISSIONING @ 77baeaa03 on study/commission-s53)

- **Hole position.** The sink's BR1 hole is drilled at machining time from a loose part's measured seat height, not match-drilled in place. That avoids chips near the board and works with the FETs already clamped.
- **Shim.** BR1's shim is selected at its dry fit.
- **Driver access.** Through the bar's slot.
- **Preheat.** From below, through the window extension, while the iron works the leads in the main window.

### D10. One common sink with selected shims, not one sink per device (revision 3, coordinator request)

All numbers here are from `results/compare.md` (`compare_mounts.py`).

**Data.**
- **Fit.** A per-device sink must be 14.15–17.50 mm wide: wide enough to cover the tab metal, narrow enough for the 18 mm pitch at Q5/Q6 and Q3/Q2. The DigiKey TO-247 sinks read on 2026-10-18 are 19.4–41.6 mm wide. None fits.
- **Thermal, with each sink's own datasheet R, at 30 °C ambient** (sink / Tj in °C):

  | sink | 17.5 A, natural | 22 A, natural | 22 A, forced |
  |---|---|---|---|
  | Ohmite WV-T247-101E (9.0 natural, 8.0 @ 500 LFM) | 74 / 83 | 126 / 145 | 108 / 125 |
  | HSK-045-09 (8.21 natural) | 69 / 78 | 111 / 129 | – |
  | Ohmite R2A-CT4-38E (35 mm wide, 1.0 @ 800 LFM) | – | – | 36 / 47 |
  | Ohmite FA-T220-38E (42 mm wide, 3.8 natural) | – | 57 / 70 | – |

  A FET sink carrying the TCO would need ≤ 6.03 °C/W at 22 A. Only the 35–42 mm parts hold 22 A, and those cannot fit.
- **Sensing.**
  - BR1 dissipates 25.52 W and would need its own ≤ 1.96 °C/W sink. That makes it the hottest sink, so the TCO and NTC go there and see none of the FETs.
  - A fan-shadowed or slipped FET sink would then overheat with no sink-sensed trip.
  - The common sink's NTC sees every device's heat. Neither design senses a bad interface; §7's calibration run does.
- **Leads.** A sink hanging on its soldered device must weigh ≤ 83 g, from the leads' 27.8 N·mm elastic moment at an estimated 34 mm lever. Otherwise it needs its own support, which brings back a per-device positioning fit.
- **Insulation.** At an 18 mm pitch, the 4 mm of pad needed beyond each tab edge makes neighbouring pads overlap. So the per-device design still needs one continuous strip, plus five PE bonds.
- **Gap pad.** GAP PAD 5000S35's data covers 10–30 % strain, a window of 0.102–0.635 mm. That misses the no-remark spread of 1.800–2.100 mm. The thickest sheet costs Rcs 4.15 °C/W, and you only learn whether it fits by gauging.

**Why the shim design stays.** It is the only option here that:
- closes every tab whatever JLC does;
- keeps a single sink that the NTC, TCO and fan all act on;
- uses catalogue parts.

Its hand work is bounded and scripted: 8 feeler readings, `shim_select.py`, then cut and grease the shims. The order remark (§2) is the lever that cuts it down. If honoured, the spread is 0.270–0.570 mm, so every device takes one or two layers on the 1.6 mm pad.

**What would reverse it:**
- a catalogue TO-247 sink 14.15–17.50 mm wide with R_SA ≤ 6.03 °C/W at the bench fan's airflow, ≤ 83 g or self-supporting, **and** accepting per-sink protection (a TCO per sink in series in the J3 loop, plus thermocouples);
- a later board with a wider FET pitch;
- a measured spread small enough for the gap-pad window, which would remove the shims but not the gauging.

## 4. Thermal results

Bound case: every FET carries the 2.2 mm design shim (brass, three faces greased at the conservative 0.413 °C·cm²/W) at the worst pressure corner. Full tables are in `results/thermal.md`. The most-proud FET has no shim and does better; §7 measures each device.

| strip | ceiling | basis | ambient | sink | P_FET | P_sink | Tj FET | Tj BR1 |
|---|---|---|---|---|---|---|---|---|
| SP2000 | 17.5 | D | 30 | 72.8 | 5.04 | 45.7 | 87.1 | 97.4 |
| SP2000 | 17.5 | D | 40 | 83.8 | 5.40 | 47.1 | 99.2 | 108.5 |
| SP2000 | 22 | D | 30 | 85.7 | 9.09 | 61.8 | 111.6 | 110.3 |
| SP2000 | 22 | D | 40 | 98.1 | 9.76 | 64.5 | 125.9 | 122.8 |
| SP2000 | 28 | D | 30 | 125.7 | 20.22 | 106.3 | 183.3 | 150.3 |

**Tj with the sink held at each trip** (bound):

| ceiling | basis | sink 86 | 95 | 104.6 | 110 |
|---|---|---|---|---|---|
| 17.5 | D | 101.6 | 111.4 | 121.9 | 127.8 |
| 17.5 | A (lost ZVS) | 169.2 | 179.0 | 189.4 | 195.3 |
| 22 | D | 112.0 | 122.4 | 133.4 | 139.7 |
| 28 | D | 132.8 | 144.3 | 156.6 | 163.4 |

**Reading the tables.**
- **17.5 A and 22 A:** with the fan holding the sink ≤ 86 °C, Tj stays ≤ 112.0 °C under the bound.
- **28 A:** stays under 150 °C only while the sink is held ≤ 95 °C, and above the 125 °C target in the bound. Go to 28 A only after §7 has measured the real stack.

**BR1 stack:** 0.663 °C/W in total (strip 0.364, shim 0.0385, grease 0.260).

## 5. Insulation (`results/insulation.md`)

**Stress bound:** 622.4 V peak (435.7 V worst die VDS + 186.7 V line peak). **Floors:** basic, creepage 4.0 mm, clearance 1.3 mm, 1250 V AC.

| insulator | rating / peak stress |
|---|---|
| SP2000 at a FET | 9.1 |
| SP2000 + GBJ case at BR1 | 49.2 |
| GBJ case alone at the screw | 18.9 |
| TCO under 2 × 5413 | 106.1 |

**New rows in revision 2:**
- sink face anywhere in its range: K3, 4.13 mm;
- shim lower and top edges: 6.104 and 9.264 mm;
- a floated body at the strip top: 5.264 mm;
- the three pad options: clearance 4.419 / 3.84 / 3.334 mm, creepage 7.495 / 6.765 / 6.055 mm;
- BR1 using its full lead play: 3.789 mm.

All pass.

## 6. Assembly procedure

Hand tools and a drill press. Dimensions are in `results/drill-table.md`.

### 6.1 Before the board arrives

1. **Measure a loose BR1.** Find its seated height: the distance from the body bottom to the underside of the lead feature that stops in a 1.6 mm hole. That is the 2.0–2.4 mm-wide H feature on the GBJ drawing.
2. **Machine the sink.**
   - M4 bar-screw holes, M3 NTC and TCO-clamp holes, M4 bond hole.
   - The BR1 M3 hole at v = (seat + 11.0 + 0.2) − 4.5.
   - Deburr and stone the face; a burr is the likeliest way to puncture 0.254 mm.
3. **Machine the bar:** pockets, end holes, and the 6.5 mm BR1 driver slot.
4. **Brackets:** Ø8 holes (pivot and lock).
5. **Baseplate:** window plus extension; standoff holes.
6. **Cut parts:**
   - the strip;
   - FR-4 pads, 4 × 1.6 mm and 4 × 0.8 mm;
   - punch the strip's Ø4 BR1 hole at the drilled position.

### 6.2 FET fit (JLC-soldered board)

1. **Receipt inspection.** For each FET, record:
   - body bottom height, which must be ≤ L1 max + 1.0;
   - visible lean.

   The JLC remark asks for coplanarity within 0.2 mm.
2. **Board onto the baseplate.** Nylon standoffs at H1 and H3–H8.
3. **Gauge the row.**
   - Hang the sink on its brackets, bolts loose. Bare face: no strip, no shims, no bar.
   - Set the lower edge with the 4.5 mm gauge. Push the sink lightly onto the row by hand.
   - At each FET, feeler-gauge the gap between the sink face and the package back at z 6.50 and z 22.55 (`tolerance.md`), from the side between packages.
   - Write `gaps.csv` (format: `example-gaps.csv`).
   - **Never tighten the clamp on an un-shimmed row.** A spring pushing a gapped device bends its leads far past their elastic limit (`bench_mech.py`).
4. **Run `python3 -I scripts/shim_select.py gaps.csv`.** It prints each device's shim (0.025 mm steps), its pad, and its predicted spring force, and checks lean against 0.0112 rad.
   - On a REJECT: re-seat that device, or return the board.
   - Re-seating: preheat the board (§6.3, step 4), melt the device's three joints together with a wide tip or one iron per joint, stand it against a square, and let it cool.
5. **Stack the sink face.**
   - Grease and lay each FET's shim stack, deburred, lower edge 1.0 mm above the sink edge.
   - Lay the strip over all of them: scribed line on the sink's lower edge, left end at u 9.0, Kapton tabs above z 32.
   - Leave BR1's position bare for now.
6. **Clamp.** Pads and springs per the fit sheet, bar onto its spacers, M4 × 25 screws tight.
   - Keep the bracket bolts loose while doing this: the floating sink settles on the row.
   - Then lock the pivot and tilt bolts.
   - Check that the lower edge is still 4.5 ± 0.3 mm.
7. **IR test before any bond.** Remove the commissioning hv_ret–PE tie first: steps 2–4 tie hv_ret to PE at one point (COMMISSIONING @ 77baeaa03), and the test would only measure the tie. With the PE lead off, short all three leads of each of the four FETs together on the unpowered board. Test at 500 V DC to the sink and to the bar.
   - Pass: ≥ 100 MΩ. This is the NTC datasheet's criterion, used as the bench criterion.
   - No 1250 V AC hipot on the board.
8. **Sensors and bond.**
   - TCO and NTC fitted as in revision 1: Kapton ×2, bends ≥ 3 mm from the body, crimp splices, VHR-3N to J3.
   - PE bond, then measure it. Pass: ≤ 0.1 Ω (IEC 60335-1 cl. 27.5, quoted from memory, EST).
   - Run the power-on line-to-PE check every session.

### 6.3 BR1 fit (COMMISSIONING step 4b; the FETs stay soldered and may stay clamped)

1. **Clear the holes and the tie.** BR1's four holes must be free of solder; JLC protects unused holes. The bench-DC supply does not use them: it lands on C6.1 (bus_p) and C6.3 (hv_ret) with short soldered tails (COMMISSIONING @ 77baeaa03, study/commission-s53). Remove the hv_ret–PE tie before 4b, as that commit says.
2. **Remove the TCO from the sink.** Loosen the loop clamp and let it hang on its leads, away from the sink. Its limit while soldering is Tf − 24 = 86 °C `[CAN]`. The bench keeps the sink ≤ 80 °C anyway.
3. **Dry-fit and shim.**
   - Lower BR1 vertically between the strip and the bar; there is room in y.
   - Feeler-gauge the gap between its back and the strip with BR1 vertical and its leads centred in their holes.
   - Run `shim_select.py` with a `BR1,g,` row to get the shim, rounded down.
   - Lift the strip's free right end, slide in the greased BR1 shim stack (Ø3.5 hole at the screw), and lay the strip back.
4. **Screw.** Fit BR1 with its M3 × 10 SHCS and an ISO 7092 small-series washer (6.0 mm OD; an ISO 7089 washer is 7.0 mm and does not pass the 6.5 mm slot) through the bar slot, using a 2.5 mm ball-end hex driver, ≤ 0.56 N·m.
   - BR1 hangs on the screw, with ≥ 0.2 mm under its seat features.
   - If the strip face lies beyond BR1's free position (negative shim), the screw leans BR1 back in its holes: up to 0.0362 rad, against 0.154 rad available (corner-limited play, c60; was 0.0187 / 0.423).
5. **Preheat.**
   - Stand the fixture on its left end.
   - Put the hot-air nozzle of a **benchtop hot-air bottom preheater** at the window extension (x 75–115, y 22–45).
     - Class: a PCB preheater with ≥ 600 W of heater, adjustable air temperature, and an input for a board thermocouple (EST spec).
   - Bring the board bottom beside BR1 to **100–110 °C** on a thermocouple taped to the board bottom 10 mm from pin 4. The ≥ 100 °C is from PROTOTYPE-LOT / FAB-NOTE; the 110 °C cap is EST, for the film caps.
   - Watch a sink thermocouple: it must stay ≤ 80 °C. Heat leaks into the sink through the clamped FETs. If it climbs, pause, or unclamp the bar for the soldering.
6. **Solder.**
   - Work through the main window: BR1's leads are at y 4.6, inside the window's y −2..22.
   - Use a temperature-controlled iron with a large chisel tip (EST spec: ≥ 80 W class), flux, and fill each barrel.
   - Trim the leads to ≤ 2.5 mm.
7. **Cool, then finish.**
   - Re-check the BR1 screw torque.
   - Refit the TCO; replace it from spares if it saw more than 86 °C or its continuity is in doubt.
   - Repeat the 500 V DC IR test, now with BR1's leads in the short, before step 5.

## 7. What the bench run measures

Revision 1's plan stands:
- **T0, body-diode heating.** Per-device Rcs and R_SA with and without the fan, before step 3.
- **During runs.** Sink thermocouples per device, IR on the package fronts, and total sink power to tell loss basis A from D.

Added in revision 2:
- **Per-device Rcs against its shim thickness** from the fit sheet. This shows whether the shim stack costs less than the bound's 0.953 °C/W, which decides whether 28 A is runnable.
- **Re-gauge after the first hot run.** Repeat the feeler gauging (clamp off) after the first 10-minute step-8 session. If any gap moved by more than 0.0195 mm, re-select.
- **Clamp check.** Measure the bar-to-package-front distance beside each pad with calipers. With the pocket depth and pad thickness this gives the spring's installed length; compare it with the fit sheet.

## 8. Hand-off to M11

Revision 1's items stand: Rcs calibration, clamp force uniformity, BR1 seat, loss basis, NTC offset, TCO margin. New:
- **Production must also meet a JLC-soldered row.** This study's stack says a single flat sink face cannot meet four soldered TO-247s in 1.8 mm holes: 0.270–2.100 mm spread against 0.0195 mm of compliance. M11's AlN stack therefore needs either:
  - per-device compliance (individually sprung insulators or tiles); or
  - an assembly step that fixes the tab plane before soldering: a soldering fixture or comb.

  The bench's measured gaps (the `gaps.csv` files) give M11 the real spread for JLC's process.
- **Where the order remark ends up.** Whether JLC honoured it (the measured spread against 0.270 / 1.800 mm) decides whether a remark is enough for production, or whether M11 needs a fixture.

## 9. BOM

Reads are from 2026-10-18; the raw reads and the blocked sites are in `sources/SOURCES.md`. Changes from revision 1 are in bold.

| # | part | qty | source / PN | stock read | unit price |
|---|---|---|---|---|---|
| 1 | Heatsink, Wakefield-Vette 511-3M | 1 | DigiKey 345-1205-ND | 25 | $40.69 |
| 2 | SIL PAD 2000, 0.010 in, 12 × 12 in sheet | 1 | DigiKey, Bergquist SP2000-0.010-00-1212 | 28 | $171.85 |
| 3 | Spring, Lee LC 055E 03 S | 6 | leespring.com, direct | not shown | $8.04 |
| 4 | 6061 flat bar 3/8 × 1 in, 6 in | 1 | DigiKey (marketplace), Remington 0.375X1.0FLT6061T6511-6 | 50 | $11.83 |
| 5 | G-10/FR-4 sheet 1/16 in, 6 × 6 in | 1 | DigiKey (marketplace), USA Industrials BULK-CS-GFR4-54 | 3 | $15.53 |
| 6 | **G-10/FR-4 sheet 1/32 in (0.8 mm pads)** | 1 | **not read**; any 1/32 in G-10 | – | – |
| 7 | Spacer, M4 × 10 mm aluminium, RAF M0539-4-AL | 4 | DigiKey | 223 | $1.29 |
| 8 | Thermal grease, Wakefield 120-SA | 1 | DigiKey 345-1006-ND | 4,984 | $5.55 |
| 9 | **TCO, Cantherm SDF-DF110S: 1 + 4 spare** | **5** | DigiKey 317-1131-ND | 1,377 | $0.87 |
| 10 | NTC lug, Vishay NTCALUG01A104GA | 2 | DigiKey 56-NTCALUG01A104GA-ND | 770 | $2.19 |
| 11 | Polyimide tape 3M 5413, 1/2 in × 5 yd | 1 | DigiKey 5413-0.5-5 | 23 | $33.04 |
| 12 | JST VHR-3N / SVH-21T-P1.1 | 2 / 6 | DigiKey | not shown | $0.10 / $0.042 |
| 13 | Fan, Cooltron FD1225B12W2-61-2NC1 | 1 | DigiKey (marketplace) | 36 | $22 (qty 2) |
| 14 | **Shim stock assortment, brass (or aluminium): 0.001–0.010 in in 0.001 steps, plus 0.015, 0.020, 0.030, 0.040, 0.050 in** | 1 set | McMaster, **PN not read** (site blocked) | – | – |
| 15 | **Feeler gauge set, 0.02–1.00 mm, blades ≥ 12.7 mm wide, long blades** | 1 | owner's tools, or local | – | – |
| 16 | **Benchtop hot-air bottom preheater** (class in §6.3) | 1 | owner's choice, **not read** | – | – |
| 17 | Aluminium angle 1-1/2 × 1-1/2 × 1/8 in, 2 × 70 mm; **M4 fender washers** | – | McMaster, **PN not read** | – | – |
| 18 | Nylon M3 × 15 male-female standoffs, nylon screws and nuts | 7 | McMaster, **PN not read** | – | – |
| 19 | Steel fasteners (as revision 1), **plus M3 × 10 SHCS + ISO 7092 M3 washer (6.0 OD) for BR1 and a 2.5 mm ball-end hex driver** | – | any | – | – |
| 20 | Loop clamp, wire, lugs, splices, plywood, polycarbonate cover, thermocouples, insulation tester, 4-wire ohmmeter | – | as revision 1 | – | – |

- **Removed:** the single 0.020 in aluminium BR1 shim. It is replaced by the selected shim stock.
- **Totals:** the DigiKey and Lee lines come to about $360 at these reads (arithmetic on the rows, not a tool). The preheater and shim set are not priced.

## 10. Owner's next steps

1. Add the remark in §2 to the JLC PCBA order. Set BR1 to DNP. Consign the four FETs from the one DigiKey lot.
2. Measure a loose BR1's seat height. Then machine the sink, bar, brackets and baseplate (§6.1).
3. Order BOM lines 1–13. Obtain the shim set, feeler gauges and a bottom preheater.
4. When the boards arrive: §6.2, saving `gaps.csv` and the `shim_select.py` sheet per board.
5. Run T0 (§7), then steps 3–4 with BR1 out. Then §6.3, then step 5.

## 11. Open questions

- **Q1. Lean and shims if the remark is ignored.** Will JLC honour the coplanarity remark? No published rule was found. If not, expect shims of up to 1.8 mm and the no-pad option on some devices.
- **Q2. TCO equivalence.** DF110S against the R43 Microtemp G4A. No G4A datasheet was read.
- **Q3. GBJ seat.** The seating feature's position is not on the drawing; measure a part (§6.1, step 1).
- **Q4.** Glass TCO on the bench, or the sink TCO only? The owner chose sink-only for the bench.
- **Q5. Gap-bridging width.** X = 1.5 mm was quoted from memory; C3 at 4.2 mm depends on it.
- **Q6. Unverified fit.** The McMaster part numbers are unread, and the 511-3M's outer-fin bolt fit is unverified.
- **Q7. Stock.** DigiKey had 28 SP2000 sheets; K-10 is the fallback (+2.3 K under the bound at 17.5 A).
- **Q8. Partial discharge** in the thin strip under the switching tabs was not assessed.
- **Q9. Answered.** The isolated DC supply lands on C6.1 / C6.3 with short soldered tails, and hv_ret is tied to bench PE at one point in steps 2–4 (COMMISSIONING @ 77baeaa03). For this mount:
  - the tie is removed before the IR test and before 4b;
  - with hv_ret at PE, the strip sees at most the step-3/4 bus voltage, inside the 622.4 V bound (`insulation.md`).
- **Q10. Soldered-lead mechanics.** The lead modulus, the allowed lead stress (200 MPa), the pivot at the board and the strip compliance are all EST. The lean limit and the "cannot close" verdict rest on them. The verdict holds across a wide margin (spread ≥ 0.270 mm against a budget of 0.0195 mm). The lean limit is the sensitive one.

## 12. Fab package: clamp bar and FR-4 pads (2026-11-28)

Follows `../jlc-mech-r1/README.md` §1 rows 1–2 and §2. Nothing was ordered, uploaded or sent.

**What was made.**
- **Clamp bar** (JLCCNC CNC). A build123d solid built from `bench_params.py` (`BAR`, `FET_X`, `SPRING_Z`, `SPRING["hole"]`, `POCKET_DEPTH`, `BAR_SCREW_X/Z`; new `BAR_HOLE_D` 4.5 and `POCKET_DEPTH_TOL` 0.05). It has four flat-bottom Ø9.53 × 7.00 pockets opening into face A (the spacer-seat face) and two Ø4.5 through-holes. **There is no BR1 driver slot** (jlc-mech-r1 §2, option a). The build script cross-checks every feature against `results/drill-table.md` and refuses to build on any disagreement. There was none.
  - The drawing is one A3 sheet at 2:1, projected (OCCT hidden-line) from the re-imported STEP. It has a view on face A, a right view, section A-A through the pockets and an isometric. Each dimension is measured on the STEP and must match `bench_params.py`.
  - The DXF holds the same sheet at 1:1 in model space: `$INSUNITS` 4, closed outlines, true circles.
- **FR-4 pads** (JLCPCB bare board). One zip per thickness, 1.6 and 0.8 mm. Each is a 60 × 48 mm panel: 3 × 2 pads of 14 × 16 mm, so 4 + 2 spares, and 30 pads per thickness at JLCPCB's 5-panel minimum.
  - A 5 mm frame, 2 mm milled gaps and a 0.5 mm router radius.
  - Each pad hangs on two 5 mm tabs, one on each 14 mm edge. Each tab has 7 Ø0.6 mouse-bites at 0.833 pitch (0.233 web), set 0.25 mm inside the pad edge.
- **`bench_cad.py`** now reads `BAR_HOLE_D` instead of a literal 4.5. Its outputs are byte-identical.

**Files** (sha256; all three generators are deterministic, so a re-run reproduces these bytes):

| file | sha256 |
|---|---|
| `fab/clamp-bar/bench-clamp-bar-r1.step` | `6bddbac3556de67f20b96d02b316f8b448e060f325fe2aae6a205d92ae8c386d` |
| `fab/clamp-bar/bench-clamp-bar-r1.pdf` | `d8f4a7de2c06466fd83427c8eeb211e445c912c6216a28e39598517f110659df` |
| `fab/clamp-bar/bench-clamp-bar-r1.dxf` | `1b2fe9e3fb9634bc73388775242fe4e09b11b29e0e86414225a2725f60cb00e8` |
| `fab/pads/bench-pads-1.6mm-r1.zip` | `257e869ee8647678b50270bd5e7136a73f1c468353a538a7690b589df0f65a41` |
| `fab/pads/bench-pads-0.8mm-r1.zip` | `66d5801ead1cc6376b639527d6aee464968f3c4111135b32d06ac4f66736f562` |

**Checks.**
- **`fab/clamp-bar/step-check.md`: 32 PASS, 0 FAIL.** The checks are on the re-imported STEP:
  - mm units, one solid;
  - bounding box 130.500 × 25.400 × 9.525;
  - volume 29272.284 mm³, equal to the analytic value;
  - only plane and cylinder faces;
  - pocket centres u 20.95 / 38.95 / 61.05 / 79.05, v 9.00, Ø9.5300, depth 7.0000 from face A, each floor a plane bounded by one circle of r 4.7650 (area 71.331, no drill point);
  - through-holes Ø4.5000 at u 4.00 / 126.50, v 12.70, z 0 to 9.525;
  - the slot location is solid metal.

  A mutation run (pocket depth 7.08, hole Ø4.6) makes it exit 1.
- **`fab/pads/pads-check.md`: 60 PASS, 0 FAIL**, from the zip files alone.
  - The Edge.Cuts is polygonised, and the board is cut along the NPTH mouse-bites. It breaks into 1 frame, 6 pads and 3 pad-to-pad bridges, which also shows every tab is fully perforated.
  - Each pad's routed outline is 14.000 × 16.000.
  - Gaps are 2.000; rails are 5.000.
  - Tabs are 5.6 mm perforated, centred on the edge (offset 0.000), with the bite row 0.250 inside it.
  - The modelled break residue is ≤ 0.039 mm: the router-radius fillet just outside the last bite. Sand it flush.
  - The copper layers are empty. Both mask layers open each whole pad. The silk is on the frame only.
  - gerbv renders every layer (`fab/pads/bench-pads-*-r1.png`). Its only message is the RS-274D format guess it prints for the empty copper files.

**Layers in each pad zip, and why.**
- Edge.Cuts (`.gm1`) and an NPTH Excellon carry all the geometry.
- F.Cu and B.Cu are present and empty, so the set reads as an ordinary 2-layer board with no copper.
- F.Mask and B.Mask open every pad plus 0.1 mm, so both pad faces are bare laminate (the thickness the tolerance stack uses). Mask stays on the frame only.
- F.SilkS carries the panel label and `JLCJLCJLCJLC` on the frame rails, so JLC's order number lands on the frame, not on a pad face.
- No paste and no PTH file.

**JLCPCB rules used** (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-28 by a web-fetch subagent):
- "FR4/Rogers/PTFE: 3 × 3 mm" minimum board, for thickness ≥ 0.6 mm. So 60 × 48 is far above it.
- Mouse-bites: "Panel board spacing: 1.6 or 2 mm"; "For breakaway with mouse-bites, the minimum width is 5mm"; "Recommended diameter of mouse bite is 0.5mm-0.8mm; Recommended distance between the two mouse-bites is 0.2-0.3mm"; "Minimum tooling edge width: 3 mm".
- "Min. Non-plated holes: 0.50mm"; "Min. Non-Plated Slots: 1.0mm".
- Thicknesses "0.4/0.6/0.8/1.0/1.2/1.6/2.0 mm". Tolerance "± 10%" at ≥ 1.0 mm, "± 0.1mm" below.
- V-cut needs a 70 × 70 panel, so it is not used.

**Order settings.**
- **JLCCNC.** Upload the STEP, plus the PDF as the 2D drawing (and the DXF).
  - CNC milling, **aluminium 6061-T6**.
  - Finish **as machined, deburred, no anodize, no coating**. The bar is PE-bonded through its screws and spacers.
  - Tolerance **ISO 2768-m**, with the drawing's **pocket depth 7.00 ± 0.05** from face A. Floors flat, corner R0.2 max.
  - No threads. **Quantity 2** (1 + spare).
- **JLCPCB.** One order per zip.
  - Base material **FR-4**, 2 layers, **thickness 1.6 mm** (or **0.8 mm** for the other zip), 60 × 48 mm, quantity 5.
  - Delivery format: panel by customer; the file is already a 3 × 2 panel with its frame. Surface finish: any (there is no copper).
  - Remove order number: "specify a location" (the `JLCJLCJLCJLC` text).
  - Remark: *"Bare FR-4 pressure pads: copper layers intentionally empty (no copper); mask openings over the pads intentionally leave bare laminate."*

**Open items.**
1. **The owner cuts the BR1 driver slot** after measuring BR1's seat height: 6.5 mm wide (two 6.5 holes + file), centred on u 105.20. Its v is set by the measured seat; at the EST seat it is v 3.4–11.4. An M3 SHCS head passes only within ±1.25 mm of the EST seat (jlc-mech-r1 §2).
2. **JLCPCB acceptance of a no-copper board is unconfirmed.** The help article returned 404, and the capabilities page says nothing about bare substrate or mask-free boards. If JLCPCB refuses it:
   - JLCCNC can machine the pads in "FR4" from the pad outline;
   - or BOM lines 5–6 (G-10 sheet) are hand-cut, as before.
3. **JLCPCB's 0.8 mm tolerance (± 0.1, so 0.70–0.90) is wider than `FR4_THIN_T` (0.71–0.87, EST).** The 1.6 mm tolerance (1.44–1.76) equals `FR4_T`. A scratch re-run of `bench_tolerance.py` and `bench_insulation.py` with 0.70–0.90 still passes both, and nothing committed was changed:
   - the 0.8 mm pad window becomes 0.606–1.437 mm (committed 0.596–1.467);
   - its force becomes 60.0–86.6 N (committed 60.0–85.9);
   - coverage of the 2.100 mm spread is still True;
   - the tightest 0.8-pad clearance is 3.832 mm (committed 3.84).

   `FR4_THIN_T` is left as is. Caliper each pad at assembly; `shim_select.py` already works per device.
4. The bar's end holes leave a 1.75 mm wall to the bar ends (u 4.0, Ø4.5), as the drill table has always had.
5. **Regression** (re-run 2026-11-28). `bench_tolerance.py` (exit 0, closes with shims = True), `bench_thermal.py`, `bench_insulation.py` (exit 0, all True) and `bench_cad.py` all regenerated `results/` byte-identical, so every verdict is unchanged.

