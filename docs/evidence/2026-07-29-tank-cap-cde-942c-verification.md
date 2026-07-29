# Tank capacitor re-sourced: verifying `942C16P1K-F` before implementing it — 2026-07-29

<!-- provenance: commit=0baca74a79a9f9bed464483db7d91d0302bcd2f4 dirty=true -->

**Base commit:** `0baca74a` (`origin/main`), branch `fix/tank-cap-resource` in
an isolated worktree. `dirty=true` because this document is committed together
with the change it describes.

**Task.** `docs/evidence/2026-07-28-coil-selection-research.md` §5.4 recommends
replacing the tank capacitors with **3 × CDE `942C16P1K-F`**, citing 34.2 A
permissible and 1.52× margin. That recommendation came from an agent. The
instruction was to **verify it from primary sources before implementing**, and
to stop and report rather than substitute something else if it did not verify.

**Verdict: it verifies, with one correction to the headline number and two
caveats that are not blocking.** The correction is that 34.2 A is the
un-transferred 100 kHz table figure; the honest figure at this tank's 47 kHz is
**28.6 A for the bank, 9.5 A per capacitor**, and the margin is **1.38×**, not
1.52×. The caveats are a tolerance regression (±5 % → ±10 %) and the fact that
CDE's rating, like WIMA's, assumes still-air natural convection.

Every figure below is tagged **[sourced]** (read from a manufacturer or
distributor document), **[chart-vector]** (recovered from the underlying vector
coordinates of a published chart), **[derived]** (arithmetic on the above) or
**[inferred]** (reasoning, not measurement).

---

## 1. Does the part exist, and is it orderable?

**Yes, on both counts, from two independent classes of source.**

### Manufacturer **[sourced]**

Cornell Dubilier (now Knowles), *"Type 942, Polypropylene Capacitors, for High
Pulse, Snubber"*, catalog `942C.pdf`
(https://www.cde.com/resources/catalogs/942C.pdf), printed page 2, **Ratings**
table, `1600 Vdc (460 Vac)` block. The row, verbatim:

```
Cap.   Catalog          D      L      d     Typical  Typical  dV/dt   IPEAK   IRMS
(µF)   Part Number      mm     mm     mm    ESR(mΩ)  ESL(nH)  (V/µs)  (A)     70 ºC 100 kHz (A)
.10    942C16P1K-F      22.5   34.0   1.0   4        24       3425    342     11.4
```

The same row appears in CDE's older sheet `PULSE-942C.pdf`
(https://www.cde.com/resources/catalogs/PULSE-942C.pdf) in inches —
`.100 | 942C16P1K | .887 (22.5) | 1.339 (34.0) | .040 (1.0) | 4 | 24 | 3425 |
342 | 11.4`. Two CDE documents, printed a catalogue generation apart, agree
digit for digit.

### The MPN decodes under CDE's own published scheme **[sourced]**

Same page, *"Part Numbering System"* diagram:

> `942` | Termination Code | Voltage Code | Capacitance Decimal Point |
> Significant Figures µF | Tolerance Code | RoHS Compliant Indicator
>
> Termination: `C` = Tinned Copper Wire, `F` = Insulated Stranded Wire,
> `H` = Copper Lugs
> Voltage: `6` = 600 Vdc, `8` = 850, `10` = 1000, `12` = 1200, `16` = 1600,
> `20` = 2000 Vdc
> Decimal Point: `S` = 0.0, `P` = 0., `W` = No decimal point
> Tolerance: `K` = ±10 %, `J` = ±5 %

`942C16P1K-F` → `942` / `C` tinned copper wire / `16` = 1600 Vdc / `P` = "0." /
`1` / `K` = ±10 % / `-F` RoHS. **0.10 µF at 1600 Vdc, ±10 %.** This is a
*consistency* check, not an existence check — which is why it is not the only
one done here.

### Distributor **[sourced]**

DigiKey product 1929475,
https://www.digikey.com/en/products/detail/cornell-dubilier-electronics-cde/942C16P1K-F/1929475
— manufacturer **Cornell Dubilier Knowles**, 0.1 µF, 1600 V DC / 460 V AC,
±10 %, 22.50 mm × 34.00 mm, PP metallized, −55 °C to +105 °C, ESR 4 mΩ,
lifecycle **Active**, **2,415 in stock**, $7.36/1 → $3.91/1000.

**Nothing about this part number is pattern-matched.** It was read off a
manufacturer ratings table, cross-checked against that manufacturer's own
part-numbering diagram, and confirmed as a live distributor line item, in that
order — the failure mode recorded in
`docs/evidence/2026-07-27-fabricated-mpn-audit.md` is specifically a
well-formed string that no distributor stocks, so the distributor check is the
one that carries the weight.

---

## 2. The number the whole decision turns on: 11.4 A is at **100 kHz**

This tank runs at 47 kHz. The 100 kHz figure has to be **transferred**, not
copied, and the coil-research recommendation copied it. This section is the
substantive correction to that recommendation.

### 2.1 What the IRMS column actually is

CDE's *Power Film Capacitor Application Guide*
(https://www.cde.com/resources/technical-papers/filmAPPguide.pdf), p.3
**[sourced]**:

> **RMS Current / Ripple Current (I_RMS)** — "The maximum operating rms
> current, **typically given at a specific reference frequency and
> temperature** in units of amperes rms"

> **Thermal Resistance (θcc, θca)** — "The total thermal resistance from core
> to case (θcc) and case to **ambient** (θca)… θca + θcc = ΔT / (I²rms · ESR)"

So the column is thermal, the frequency and temperature are a *reference*, and
the transfer to another frequency is the designer's job.

### 2.2 It is a still-air natural-convection rating, and the family proves it **[derived]**

Apply `P = I² · ESR` to every row of CDE's own 1600 Vdc block, take the
external can area (`πDL + 2πr²`), and read off the implied thermal resistance
on the hypothesis "70 °C is an **ambient**, the hot-spot limit is 85 °C
(`Full rated voltage at 85 °C` — 942C.pdf p.1), so ΔT = 15 K":

| Part | P = I²·ESR | can area | θ = 15 K / P | implied h = 1/(θ·A) |
|---|---|---|---|---|
| `942C16S22K-F` | 0.243 W | 1508 mm² | 61.7 °C/W | **10.7 W/m²K** |
| `942C16S33K-F` | 0.309 W | 1879 mm² | 48.5 °C/W | **11.0** |
| `942C16S47K-F` | 0.359 W | 2190 mm² | 41.8 °C/W | **10.9** |
| `942C16S68K-F` | 0.423 W | 2597 mm² | 35.4 °C/W | **10.9** |
| **`942C16P1K-F`** | **0.520 W** | **3199 mm²** | **28.9 °C/W** | **10.8** |
| `942C16P15K-F` | 0.594 W | 3623 mm² | 25.3 °C/W | **10.9** |
| `942C16P22K-F` | 0.696 W | 4264 mm² | 21.5 °C/W | **10.9** |
| `942C16P33K-F` | 0.884 W | 5395 mm² | 17.0 °C/W | **10.9** |
| `942C16P47K-F` | 1.066 W | 6503 mm² | 14.1 °C/W | **10.9** |

The implied heat-transfer coefficient is **10.7–11.0 W/m²K across a 21×
capacitance range and a 4× area range** — a 3 % spread. That is not a
coincidence of nine numbers; it is the signature of a single natural-convection
+ radiation model in still air, and it confirms three things at once:

1. The IRMS column **is** `sqrt(P_allowed / ESR)` with a fixed ΔT.
2. **70 °C is an ambient**, not a case temperature. (The alternative reading —
   70 °C case, 105 °C core — needs θcc ≈ 67 °C/W core-to-case on a 22 mm can,
   which is not physical.)
3. `P_allowed = 0.520 W` for `942C16P1K-F`, and `θ = 28.9 °C/W`. These are the
   two numbers the rest of this section uses.

### 2.3 Two independent readings of CDE's own curves give the 47 kHz transfer

**Method A — the product family's own `RMS Voltage vs Frequency` panels
[chart-vector].** `942C.pdf` p.4/5 plots six panels, one per rated voltage. The
curves are vector paths, so the page was converted to SVG with transforms
applied and every vertex mapped into page coordinates; axis calibration came
from the panels' own gridlines.

**Calibration validated independently, on all six panels.** Each curve's
low-frequency plateau is the rated AC voltage limit, so the plateau must
reproduce the datasheet's own printed VAC figure. It does, on every panel:

| panel | plateau read | datasheet header |
|---|---|---|
| 600 Vdc | 301 Vrms | 300 Vac |
| 850 Vdc | 361 | 360 |
| 1000 Vdc | 400 | 400 |
| 1200 Vdc | 431 | 430 |
| **1600 Vdc** | **461** | **460** |
| 2000 Vdc | 501 | 500 |

Six panels agreeing to ≤0.3 % validates both axis calibrations simultaneously.

Above the knee each curve falls as `V ∝ 1/f`, i.e. **constant current** —
because `I = V · 2πfC`, so `V·f` is proportional to permissible current and `C`
cancels out of any ratio. Taking `I(47 kHz)/I(98.5 kHz)` on every curve whose
current-limited branch starts below 47 kHz:

| panel | knee | I(47 k)/I(100 k) |
|---|---|---|
| 600 Vdc | 39.7 kHz | 0.837 |
| 600 Vdc | 19.9 kHz | 0.959 |
| 600 Vdc | 5.9 kHz | 1.052 |
| 1000 Vdc | 19.8 kHz | 0.919 |
| 1000 Vdc | 7.9 kHz | 1.038 |
| 1200 Vdc | 19.8 kHz | 0.890 |
| 1200 Vdc | 9.9 kHz | 0.996 |
| **1600 Vdc** | **39.7 kHz** | **1.000** |
| **1600 Vdc** | **19.8 kHz** | **1.000** |
| 2000 Vdc | 39.6 kHz | 0.838 |

**n = 10, mean 0.953, range 0.837–1.052.** Both 1600 Vdc curves — the panel
that governs this part — give exactly 1.000. The two 0.837/0.838 outliers are
curves whose knee sits at ~39.7 kHz, so 47 kHz falls on the rendered polyline's
cut corner and is understated; they are kept as the conservative bound rather
than discarded.

**Method B — CDE's generic polypropylene DF-vs-frequency curve
[chart-vector].** `filmAPPguide.pdf` p.3, captioned *"DF change with
temperature and frequency are given for polypropylene in the curves below"*
**[sourced]**. Same vector extraction; axis calibration from the log gridlines
(x: 1 kHz at 83.1 pt, 59.7 pt/decade; y: `tanδ×10⁻⁴` = 1 at 731.0 pt,
49.15 pt/decade), validated by reproducing the minor-decade tick positions for
2/3/5 to ≤0.15 pt.

- DF(10 kHz) = **1.80 × 10⁻⁴**
- DF(47 kHz) = **2.95 × 10⁻⁴**
- DF(100 kHz) = **4.48 × 10⁻⁴**

Since `ESR = DF/(2πfC)`, `ESR(47k)/ESR(100k) = (2.95/4.48) × (100/47) = 1.40`,
hence `I(47k)/I(100k) = 1/√1.40 = **0.845**` **[derived]**.

**The two methods agree: 0.837 and 0.845.** They share no inputs — one is the
942C/943C product curves, the other a generic PP dielectric curve from a
different document.

### 2.4 The number, and the floor beneath it

> **Permissible RMS current, `942C16P1K-F` at 47 kHz, 70 °C ambient:
> 9.5 A** (conservative; 11.4 A if the 1600 Vdc panel's own 1.000 is taken at
> face value).

Recorded for completeness and explicitly **not** used: if one assumes tanδ is
flat with frequency — so `ESR ∝ 1/f` and the transfer factor is `√(47/100) =
0.686` — the figure falls to **7.8 A**. That assumption is contradicted by both
CDE curves above (DF *rises* 2.5× from 10 to 100 kHz, which is the signature of
the foil-electrode ohmic term this "hybrid section design of polypropylene
film, **metal foils** and metallized polypropylene" is built around
**[sourced]**, p.1). It is stated as a floor because even the floor clears the
requirement — see §3.

---

## 3. Does 3 × `942C16P1K-F` meet the requirement?

Required tank current, from this repo's own harness (`run_zvs_sweep.py`,
`C_TANK_F = 300e-9`, L = 150 µH, cast-iron preset), re-derived independently as
a check: `I = 234.2 V × 2π × 47 kHz × 300 nF = 20.748 A` — matching the
recorded 20.74 A **[derived]**. A second, harsher operating point is carried
through: the 88 µH coil candidate of
`docs/evidence/2026-07-28-coil-selection-research.md` §4.2 gives **22.5 A** at
f_sw = 46.6 kHz. The coil is still an open decision, so both are reported.

| required | per cap (÷3) | permissible | margin | P per cap | ΔT above ambient |
|---|---|---|---|---|---|
| **20.75 A** (repo committed) | **6.92 A** | 11.4 A (1600 Vdc panel) | 1.65× | 0.19 W | 5.5 K |
| | | **9.5 A (adopted)** | **1.38×** | 0.27 W | **7.9 K** |
| | | 7.8 A (contradicted floor) | 1.13× | 0.41 W | 11.7 K |
| **22.50 A** (88 µH coil) | **7.50 A** | 11.4 A | 1.52× | 0.23 W | 6.5 K |
| | | **9.5 A (adopted)** | **1.27×** | 0.32 W | **9.3 K** |
| | | 7.8 A (contradicted floor) | 1.04× | 0.48 W | 13.8 K |

**The entire bracket clears the requirement** — which is the exact mirror image
of the WIMA finding, where the entire published bracket sat *below* it
(`docs/evidence/2026-07-28-reference-appliance-and-cap-rating.md`).

For comparison, the part being replaced: 2 × `FKP1T031507G00JSSD` carries
**10.37 A each** against a **5.2 A** best estimate — **0.50×**.

### Every other rated axis, checked, none of them close **[derived]**

| axis | applied | rated | headroom |
|---|---|---|---|
| DC voltage | 331 V peak | 1600 Vdc | 4.8× |
| AC voltage | 234 Vrms | 460 Vac (60 Hz) †| — |
| dV/dt | 97.8 V/µs | 3425 V/µs | 35× |
| peak current | 9.8 A | 342 A | 35× |

† The 460 Vac figure is a **60 Hz** rating and does not transfer to 47 kHz;
the binding HF voltage limit is the plateau of the `RMS Voltage vs Frequency`
curve, which for the 1600 Vdc panel is 461 Vrms and holds until the
current-limited knee. At 47 kHz with 0.10 µF the current limit binds first,
which is exactly the axis §2 verified. Named explicitly so the next reader does
not have to re-derive which axis was checked — the mistake that put the WIMA
part on this board was reading the headline VAC number.

### The thermal caveat, stated rather than buried

The 9.5 A figure is a **still-air natural-convection** rating (§2.2 derives
h ≈ 10.9 W/m²K, which *is* still air) at **70 °C ambient**. A capacitor beside
an IGBT half-bridge in a closed enclosure is not automatically in that
condition. Two things make this materially better than the WIMA case rather
than the same problem restated:

1. CDE's reference **includes a 70 °C ambient budget**. WIMA's curve is a 15 K
   *internal rise* with **no ambient allowance at all**, plus an explicit
   footnote excluding "radiant heat within the chassis".
2. The computed rise is **7.9 K** at the committed operating point, against
   the 15 K the rating is drawn at. The bank runs at roughly half its allowed
   dissipation, so the hot spot reaches 85 °C only at a ~77 °C local ambient.

Recommended acceptance check at bring-up, following CDE's and WIMA's common
advice: measure can surface temperature at sustained full power and confirm
`T_case + 5 K ≤ 85 °C`.

---

## 4. Does 3 × C land on the committed 300 nF?

**Yes, exactly. 3 × 0.10 µF = 0.300 µF.** `C_TANK_F = 300e-9` in
`run_zvs_sweep.py` and `run_tank_coil_sweep.py` is untouched, and no
resonant-frequency consequence follows from the swap itself.

### But the tolerance regresses, and this is the one finding that costs something

The catalogue 942C tolerance is **K = ±10 %**. The WIMA part it replaces was
**J = ±5 %**.

| | bank worst case | f_res spread |
|---|---|---|
| WIMA, ±5 % | 285–315 nF | +2.60 % / −2.41 % |
| **CDE, ±10 %** | **270–330 nF** | **+5.41 % / −4.65 %** |

CDE's specification page states *"Capacitance Tolerance ±10 % (K) Standard;
±5 % (J) Optional"* **[sourced]** — but **no `J` part number appears in any CDE
catalogue table**, in either document. Obtaining ±5 % is therefore a
procurement conversation with CDE, **not** an MPN to be produced by swapping
the `K` for a `J`. That would be precisely the fabrication this repo removed on
2026-07-27. Flagged here, unresolved, for whoever owns the PLL window and the
ZVS ratio: a ±5.4 % resonant-frequency spread is wider than the design has
previously assumed.

---

## 5. Physical consequence — reported, not acted on

`pcb/temper.kicad_pcb` is **deliberately untouched**. A separate placement pass
owns re-placing this bank.

| | before (2 × WIMA FKP 1) | after (3 × CDE 942C) |
|---|---|---|
| parts | 2 | 3 |
| package | rectangular box, PCM 37.5 | axial can, horizontal |
| body | 41.5 × 20.0 mm, **39.5 mm tall** | ⌀22.5 × 34.0 mm, **22.5 mm tall** |
| land pitch | 37.50 mm | **40.00 mm** |
| courtyard each | 830 mm² | 968 mm² |
| **total land area** | **1660 mm²** | **2904 mm² (+75 %)** |
| **stack height** | **39.5 mm** | **22.5 mm (−43 %)** |

The bank gets **wider and shorter**. `docs/evidence/2026-07-28-reference-appliance-and-cap-rating.md`
§Q3 established that enclosure height was not the binding constraint even at
39.5 mm, so losing 17 mm of height is a free win; the +75 % board area is the
real cost and is the placement pass's problem.

The board was never re-laid-out for the WIMA parts either — `modules.ato`
carried a standing "BOARD REWORK REQUIRED, NOT DONE HERE" note and
`pcb/temper.kicad_pcb` still holds the *old* 27.5 mm-pitch land for C25/C26
(`docs/evidence/2026-07-28-tank-cap-placement.md`). So this change adds one
component to a rework that was already owed; it does not create a new one.

### Land pattern

New footprint `temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`
(`pcb/libs/temper.pretty/`), hand-built from CDE's own dimensions:

- Body **34.0 mm × ⌀22.5 mm** — CDE's `L`/`D` columns, which the mechanical
  drawing labels `L MAX.` / `D MAX.`, so the outline is a worst-case envelope.
- Lead **⌀1.0 mm** (`d` column); hole **1.3 mm** = lead + 0.3 mm IPC-2222
  Level-B clearance; pad **2.6 mm** → 0.65 mm annular ring, wider than KiCad's
  stock `C_Axial` default because this land carries ~7 A rms continuously.
- Pitch **40.00 mm** = 34.0 mm body + 3.0 mm lead-forming allowance per side,
  matching KiCad's own axial family convention (2.5–3.25 mm/side across
  `L30.0/P35.00`, `L22.0/P27.50`, `L34.5/P41.00`). CDE specifies **41 mm MIN**
  free lead each side, so 3.0 mm of formed lead has enormous margin.

No stock KiCad `Capacitor_THT` footprint matches ⌀22.5 × 34.0 mm; the nearest,
`CP_Axial_L34.5mm_D20.0mm_P41.00mm_Horizontal`, is 2.5 mm too narrow in
diameter *and* polarised.

---

## 6. Verification run

| check | before | after |
|---|---|---|
| `make netlist` | succeeds | succeeds |
| compiled nets | 162 | **162 (Δ 0)** |
| components | 168 | **169 (+1)** |
| `check_domain_partition.py` | PASSED, 0 crossings | **PASSED, 0 crossings (verdict unchanged)** |
| `mpn_fabrication_gate.py` | PASSED, 118 parts, **0 UNCHECKED** | **PASSED, 119 parts, 0 UNCHECKED** |
| `pytest elec/validation/` | 30 passed | **30 passed** |
| `pytest scripts/tests/test_mpn_fabrication_gate.py` | **49 passed, 1 FAILED** | **54 passed** |

**Net count is unchanged, and that is the correct answer, not a missed
update.** `c_tank3` is a third element of an existing parallel pair: `p1` joins
`SW_NODE` (which already carried `c_tank1.p1`, `c_tank2.p1`) and `p2` joins
`tank.c_tank1-p2` (which already carried both `p2` pins and
`inductor_conn.p1`). Adding a parallel element to two existing nets adds nodes,
not nets. Verified in `elec/build/default.net`: net 44 `SW_NODE` now lists
C25/C26/**C27** pin 1, net 59 `tank.c_tank1-p2` lists C25/C26/**C27** pin 2.

### The MPN gate: family taught, not allowlisted

Adding the CDE part initially moved three parts into the gate's **UNCHECKED**
column (prefix `942C` unrecognised). UNCHECKED does not fail the gate — but
`test_real_tree_has_no_unchecked_mpns_left` demands zero, and more importantly
the correct remedy for an unrecognised *real* family is to teach the decoder,
not to allowlist the part. **No allowlist entry was added** (still 10, all
pre-existing).

`_dec_cde_942c()` was transcribed from CDE's own Part Numbering System diagram
(§1) *before* being pointed at the repo's string, per the decoder registry's
standing rule. It is exercised by four new tests covering all three
decimal-point letters, the `W`-only embedded-`P` convention
(`942C8W1P5K-F` = 1.50 µF), the no-`-F` spelling CDE's older sheet uses, five
malformed-string rejections, and a declared-value mismatch. Seven of the eight
true-positive cases are parts that appear **nowhere** in `elec/src`, which is
what makes them evidence the rule came from the manufacturer rather than from
the string under test.

### A pre-existing red test, found and fixed

`test_gate_flags_the_resonant_tank_capacitor_on_real_tree_today` asserted the
gate exits **3** on the real tree. It has been failing since **`4696427a`**
(2026-07-28), which fixed the WIMA MPN in source and made the gate exit 0
without updating the assertion. That is **not** a consequence of this change —
it reproduces on `0baca74a` untouched — but it is exactly the situation the
test's own docstring described in advance:

> "if this test starts failing because the gate now exits 0, that means someone
> changed the design or the MPN — check that the fix was verified against a
> distributor, then move this assertion back to a clean pass with that evidence
> cited."

The distributor check is §1. The assertion is now `test_gate_is_clean_on_real_tree_today`,
pinning exit 0, and additionally pinning that **neither** WIMA string
(`FKP1U021507E00JSSD`, `FKP1T031507G00JSSD`) reappears — so a revert of this
current-rating fix trips a test rather than passing silently.

---

## 7. What this changes

- The tank capacitor bank goes from **0.50× its permissible AC current to
  1.38×**, on a figure derived from a manufacturer **table** plus a
  frequency transfer read off that manufacturer's **own curves**, rather than
  from an interpolation between curves for other parts.
- The committed **300 nF is unchanged**, exactly, and both simulation harnesses
  keep `C_TANK_F = 300e-9` untouched.
- The MPN gate can now read a fifteenth manufacturer family, and the real-tree
  integration assertion is green for the first time since 2026-07-28.

## 8. What this does not change, and what it leaves open

- **`f_switching`, the PLL window, and every gate threshold** are untouched.
- **The coil** (`inductor_conn`) is untouched — still `CUSTOM_LITZ_COIL`, still
  an open decision. Both operating points it might land on are carried through
  §3 and both clear.
- **`pcb/temper.kicad_pcb`** is untouched. Three parts now need placing where
  two were already mis-placed.
- **OPEN — the ±10 % tolerance.** §4. It widens the resonant-frequency spread
  to +5.4 %/−4.7 % and belongs to the PLL/ZVS-window owner. It is a real
  regression and is not resolved here.
- **OPEN — a stale comment in `elec/src/main.ato:138`** still reads
  "`the fixed 300nF C_TANK (c_tank1+c_tank2…)`". The value is right, the part
  list is now wrong by one. `main.ato` was out of scope for this change (a
  concurrent agent holds it), so it is reported rather than edited.
