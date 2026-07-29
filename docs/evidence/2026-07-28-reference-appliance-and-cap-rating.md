# Reference appliance and tank-capacitor AC current rating — 2026-07-28

<!-- provenance: commit=77f88827af479f94446aa1308692bf808050c798 dirty=false -->

Three bounded research questions feeding a component-selection decision on the
resonant tank capacitor (`c_tank1`/`c_tank2`, `elec/src/modules.ato:480-484`,
MPN `FKP1T031507G00JSSD`). No code, `.ato`, board file or gate was modified.

| # | Question | Verdict |
|---|----------|---------|
| Q1 | WIMA permissible AC current, from a table not a chart | **Established** — with a correction: WIMA publishes no table *and no curve for this part*. Bracketed 4.0–6.2 A; best estimate 5.2 A. The prior ~6 A was the optimistic end. |
| Q2 | Does the Breville Control Freak duty-cycle or modulate continuously? | **Could not establish.** General practice reported separately and labelled as such. |
| Q3 | Control Freak dimensions and internal volume | **Partially established.** External dimensions sourced; internal volume could not be established from any teardown — estimate given with reasoning. |

Every figure below is tagged **[sourced]** (read from a manufacturer or
manufacturer-hosted document), **[chart-vector]** (recovered from the
underlying vector coordinates of a published chart — see method), **[derived]**
(arithmetic on the above), or **[inferred]** (reasoning, not measurement).

---

## Q1 — WIMA FKP 1 permissible AC current

### Verdict

**Established, and it moves the number in the unfavourable direction.**

The task asked whether the ~6 A figure could be confirmed from a table. It
cannot, for a reason more interesting than "WIMA only publishes curves":

> **WIMA publishes permissible AC current only as curves, and for
> 0.15 µF / 1600 VDC / PCM 37.5 it publishes no curve at all.**

The 1600 VDC panel plots exactly five parts — 0.33 µF/37.5, 0.047 µF/37.5,
0.022 µF/27.5, 4700 pF/22.5, 100 pF/15 **[chart-vector]**. The part actually
fitted, 0.15 µF/PCM 37.5, is not among them. Any figure for it is an
interpolation between neighbours, and the previously reported ~6 A is
numerically the *0.33 µF* curve — a part with 2.2× the capacitance and 1.8× the
case cross-section.

### Source

WIMA FKP 1 datasheet, revision **03.26**, `e_WIMA_FKP_1.pdf`
(https://www.wima.de/wp-content/uploads/media/e_WIMA_FKP_1.pdf), printed
page 70 (PDF page 8). Chart caption, verbatim **[sourced]**:

> "Permissible AC current in relation to frequency till 15° C internal
> temperature rise (general guide). The information behind the cross bar denote
> the PCM of the measured value."

The ordering table on printed page 63 confirms the part **[sourced]**:

> `0.15 „   …   20   39.5  41.5  37.5   FKP1T031507G_ _ _ _ _ _`

under the column header `1600 VDC/650 VAC*`, with the footnote

> `* AC voltages: f ≤ 1000 Hz; 1.4 x Urms + UDC ≤ Ur`

confirming the headline 650 VAC is a ≤1 kHz figure and does not apply at 47 kHz.

### Method — why this is not "read off a chart"

The curves are vector paths, not raster images. The page content stream was
decompressed (`qpdf --qdf`) and parsed with a graphics-state-tracking
interpreter that transforms every path vertex through the CTM into page
coordinates. Each curve is a 3-vertex polyline. Axis calibration came from the
panel's own major gridlines, not from eyeballing:

- x: 10³ Hz at 328.43 pt, **58.170 pt/decade**
- y: 10⁻² A at 517.37 pt, **26.985 pt/decade**

**Calibration validated independently.** The low-frequency rising segment of
each curve is the rated-AC-voltage limit, so back-computing `V = I/(2πfC)` at
~1 kHz must reproduce a rated voltage. It does **[derived]**:

| curve | I at ~1 kHz | back-computed V |
|---|---|---|
| 0.33 µF/37.5 | 1.384 A | **657 V** (datasheet header: 650 VAC — 1.1 % error) |
| 0.047 µF/37.5 | 0.1473 A | 502 V |
| 0.022 µF/27.5 | 0.0703 A | 508 V |
| 4700 pF/22.5 | 0.0151 A | 502 V |

Three independent curves agreeing to 502–508 V, and the fourth reproducing the
datasheet's own printed 650 VAC to 1.1 %, validates both axis calibrations
simultaneously. A calibration error would not produce that agreement. Extracted
plateau values also land on round numbers (2.00, 2.99, 4.00, 6.02 A),
consistent with sub-1 % extraction error.

### The 1600 VDC family, extracted **[chart-vector]**

| Part (label on chart) | knee | plateau | **I @ 47 kHz** | case W×H×L / PCM **[sourced]** |
|---|---|---|---|---|
| 0.33 µF / 37.5 | 4.67 kHz | 6.33 → 6.02 A | **6.19 A** | 31 × 46 × 41.5 / 37.5 |
| *0.15 µF / 37.5* | — | — | *not published* | *20 × 39.5 × 41.5 / 37.5* |
| 0.047 µF / 37.5 | 26.8 kHz | 4.00 A | **4.00 A** | 13 × 24 × 41.5 / 37.5 |
| 0.022 µF / 27.5 | 42.9 kHz | 2.99 A | 2.99 A | 11 × 21 × 31.5 / 27.5 |
| 4700 pF / 22.5 | 136 kHz | 2.00 A | 0.695 A | 7 × 16.5 × 26.5 / 22.5 |
| 100 pF / 15 | 628 kHz | 0.199 A | 0.015 A | 5 × 11 × 18 / 15 |

### The number

**Hard bracket, both endpoints published, same rated voltage, same PCM:**

> **4.0 A ≤ I_permissible(0.15 µF, 1600 VDC, PCM 37.5, 47 kHz) ≤ 6.2 A**

**Best estimate: 5.2 A** **[derived]**, by interpolating between the two
bracketing published curves. Two independent interpolation bases agree:

- on log-capacitance (0.047 → 0.15 → 0.33 µF): **5.19 A**
- on log case cross-section (312 → 790 → 1426 mm²): **5.23 A**

The case-area fit is `I = 4.00 A × (A/312 mm²)^0.2878`, anchored on the two
measured endpoints. Its exponent is fitted from two points only; across other
voltage panels the equivalent exponent ranges 0.22–0.91, so this relation is
**not** safe to extrapolate. It is used here strictly as *interpolation* —
0.15 µF lies inside the 0.047–0.33 µF interval that anchors it.

### Verdict against the requirement

Required, from this repo's own simulation (`run_zvs_sweep.py`, `C_TANK_F = 300e-9`),
re-derived here independently as a check: `I = 234.2 V × 2π × 47 kHz × 300 nF =
20.748 A` total, matching the recorded 20.74 A; **10.37 A per capacitor**.

| | permissible | over by |
|---|---|---|
| best case (bracket top, 0.33 µF curve) | 6.19 A | **1.67×** |
| **best estimate** | **5.22 A** | **1.99×** |
| worst case (bracket bottom, 0.047 µF curve) | 4.00 A | **2.59×** |

The prior finding's stated weakness — "±1 A does not change the verdict, ±5 A
would" — **does not materialise**. The entire published bracket sits below the
requirement. The verdict is unchanged and strengthened: the previously reported
~6 A was the optimistic extreme, and the honest centre is ~5.2 A, i.e. a
factor of two over, not 1.7×.

### Conditions the figure is specified under

This matters more than the number, and the answer is unfavourable.

1. **ΔT = 15 K *internal* rise, "general guide"** **[sourced]** — the caption
   above. It is a temperature *rise*, not an absolute rating, so it carries no
   ambient allowance of its own.

2. **Ambient is additive and the assembly conditions are stated.** WIMA's
   knowledge base ("Special technical subjects",
   https://www.wima.de/en/service/knowledge-base/special-technical-subjects/)
   does publish a genuine **table** — Table 1, specific dissipation in watts
   per K **above the ambient temperature** **[sourced]**:

   | PCM (mm) | 2.5 | 5 | 7.5 | 10 | 15 | 22.5 | 27.5 | **37.5** |
   |---|---|---|---|---|---|---|---|---|
   | W/K above ambient | 0.0025 | 0.004 | 0.006 | 0.0075 | 0.012 | 0.015 | 0.025 | **0.03** |

   with the footnote, verbatim:

   > "Table 1: The data is for ordinary assembly and ventilation conditions
   > avoiding radiant heat within the chassis of the equipment."

   A capacitor sitting beside an IGBT half-bridge inside a closed enclosure is
   explicitly *outside* the conditions this table is quoted for.

3. **The ambient arithmetic is the designer's** **[sourced]**:

   > "The temperature rise plus the max. ambient temperature = max. permissible
   > operating temperature (taking into account the voltage derating…)"

   FKP 1 operating range is −55 °C to +105 °C, and — critically — the voltage
   derating factor of **1.35 %/K applies from +75 °C for AC voltages** (vs
   +85 °C for DC). An enclosure ambient of 60 °C plus a 15 K rise reaches 75 °C
   and begins derating before any margin exists.

4. **Measure, do not trust the curve** **[sourced]**:

   > "In applications where reliability is critical, it is recommended to
   > measure the surface temperature of the capacitor and to take into account
   > that the temperature within that capacitor will be approximately 5 K above
   > the case temperature."

### A first-principles cross-check that does *not* validate

For completeness and against the temptation to present it as confirmation:
combining Table 1 (0.03 W/K at PCM 37.5), ΔT = 15 K, and the datasheet's tanδ
table gives `P_max = 0.45 W`, `ESR = tanδ/(2πfC) ≈ 0.0196 Ω` at 47 kHz, hence
`I ≈ 4.8 A` **[derived]**. That lands inside the bracket. But applying the same
method to the *published* 0.047 µF curve yields 2.7 A against a published
4.0 A — the model under-predicts by 1.5×. It is therefore **not** an
independent confirmation of 5.2 A and is recorded only as a conservative
sanity check that does not contradict the bracket.

### Adjacent data point, deliberately not used

The **1250 VDC** panel *does* publish a 0.15 µF/PCM 37.5 curve: plateau 6.01 A
from 17.5 kHz, so 6.0 A at 47 kHz **[chart-vector]**. It is not transferable —
that part has a different case (17 × 29 × 41.5), thinner film and a different
turns count. It is noted because it sits at the top of the bracket and a reader
who found it independently might mistake it for a confirmation of the ~6 A
figure. It is not one; it is a different part.

### Design implication **[derived]**

Using the interpolation above, permissible current per device against the
current each device must carry when N devices share 300 nF and 20.748 A:

| N | C each | catalogue part | I required | I permissible | margin |
|---|---|---|---|---|---|
| 2 | 150 nF | FKP1T031507G | 10.37 A | 5.22 A | **0.50×** (today) |
| 4 | 75 nF | (no catalogue value) | 5.19 A | ~4.4 A | 0.85× |
| 6 | 47 nF (282 nF total) | FKP1T024707C | 3.46 A | 4.00 A | **1.16×** |
| 7 | 47 nF (329 nF total) | FKP1T024707C | 2.96 A | 4.00 A | 1.35× |

Paralleling *does* converge — permissible current falls only as ≈`C^0.29` while
required current falls as `1/N` — but it needs **six or seven** devices, not
three, and 6 × 47 nF is 282 nF (6 % under the committed 300 nF, a ~3 % shift in
resonant frequency). This is flagged, not recommended: `C_TANK_F = 300e-9` is
treated as fixed by both simulation harnesses. All margins above are at ΔT = 15 K
with **no ambient derating applied**.

---

## Q2 — Breville Control Freak duty-cycle behaviour

### Verdict

**Could not establish.** I found no manufacturer statement, patent, teardown,
service manual, or instrumented measurement that describes how the Control
Freak's resonant converter regulates output power at reduced settings.

### What was tried

- **Patents.** Google Patents assignee queries: `Breville` + induction
  (160 results), `Breville USA, Inc.` (22 results). The only induction-cooktop
  patent found is **AU2021203832B2, "Cooktop", Breville Pty Limited, granted
  2023-07-13**. Fetched and read: it covers temperature control, fan
  management and cookware detection, and describes power only as discrete
  levels — verbatim, *"The right Y-axis 406 shows power levels from 1 to 10. In
  this graph each power level represents approximately 90 Watt"* and *"The
  maximum power supplied to the heating system is capped at a fraction of the
  maximum appliance power limit, e.g. 1/5, 1/4, 1/3 or 1/2 the maximum power."*
  It contains **no** description of the inverter modulation scheme — no
  duty-cycle switching, frequency modulation, phase shift, PWM, pulse skipping
  or bus-voltage control. Its ~900 W scale (10 × ~90 W) also does not match the
  Control Freak's 1800 W (US) / 2400 W (AU/EU) rating, so I could not tie it to
  this appliance at all.
- **Teardowns.** No public teardown of CMC850 or BMC800 with board-level
  photographs. iFixit's only Breville induction teardown is a different model
  (LIC400BLKANZ, teardown 132482); fetched, it identifies the stack-up
  qualitatively but gives no measurements and no inverter analysis.
- **FCC.** No FCC ID appears in any CMC850 documentation; fccid.io returned
  HTTP 403. A 1800 W induction cooktop with no intentional radiator falls under
  FCC Part 18 (ISM), which for consumer equipment does not require a published
  grant or test report — so the *absence* of a filing is expected and carries no
  information either way.
- **Manufacturer documentation.** The CMC850 technical specification sheet and
  the safety instruction book state *"Power Range 100–2400 Watts"* and *"Heat
  intensity control"* **[sourced]** and say nothing about the mechanism.

### A claim I found and deliberately did not carry forward

Several retailer pages, review sites and search-engine summaries assert that
the Control Freak uses continuously variable power *"rather than cycling on and
off"*. Every instance I could trace back was an **inference from the
temperature-precision marketing claim**, not an observation and not a
manufacturer statement. When Sizzle & Sear's detailed review — the most
technical of them — was fetched directly, it contains **no statement about power
delivery mechanism at any setting**. This is precisely the trap the task
flagged, and the claim is not evidence.

One weak anecdote exists in the other direction: a ChefSteps community report
that when holding a boil the unit *"cycles between boiling and dropping down to
around 98–99 °C"*, with the burner *"pausing"*. **[inferred, third-hand]** —
reached only via a search summary, thread not fetched. Even taken at face value
this describes the **outer thermostatic loop** bang-banging over seconds, which
says nothing about the inner converter's modulation. Not treated as evidence
either way.

### General practice — clearly labelled as *not* this appliance

From **Infineon Application Note AN2014-01, "Reverse-conducting IGBTs for
induction cooking and resonant applications", V3.01, 2021-08-24** **[sourced]**:

- Typical switching frequency: *"frequency between 20 kHz and 75 kHz is
  sufficient to guarantee heating power up to 4 kW for most"* applications.
- **Quasi-resonant single-switch** (the dominant single-hob topology) — at low
  power it loses soft switching, and the standard remedy is on/off cycling:

  > "As this condition is predominant at low output power, one possible solution
  > to avoid a hard-switching condition is to adopt a so-called burst mode… the
  > minimum output power of the system is set in such a way that no hard
  > switching operations occurr, and a lower output power can be achieved by an
  > **on-off modulation of the inverter**"

  Its Table 1 maps 1000/800/600/400 W to inverter on-duty 100/80/60/40 %, and:

  > "Usually, a **burst frequency of 0.2-0.3 Hz** is used."

- **Half-bridge series resonant** — primary control is switching frequency;
  asymmetric PWM is available for very low power but *"is usually used only in
  extreme cases"* because *"one of the two power switches no longer operates in
  soft switching."*

So general practice for single-hob designs at low power **is** on/off burst
modulation at roughly 0.2–0.3 Hz. Whether the Control Freak does this is
unestablished.

### Why Q2 turns out not to matter much **[derived]**

Two reasons, both worth recording so this question is not reopened at cost:

1. **The finding is at full power.** The 10.37 A figure is computed at the
   committed 1.8 kW operating point, which any control scheme must sustain
   *continuously* by definition. Duty-cycling changes the duty at *reduced*
   settings only. It cannot relieve the rated-power case at all.

2. **At equal average output power the two schemes are thermally equivalent for
   this capacitor.** Tank loss scales as `I²·ESR` and delivered power scales as
   `I²`, so burst mode at duty D dissipates `I_full²·ESR·D` while continuous
   modulation dissipates `I_red²·ESR` — and `I_red² = I_full²·D` at the same
   average power. The two are equal to first order. With a burst period of
   3–5 s against a film capacitor thermal time constant of minutes, the
   capacitor integrates to that average either way.

   Assumptions: burst period ≪ capacitor thermal time constant; ESR
   approximately constant over the modulation range. Both hold here.

---

## Q3 — Control Freak dimensions and internal volume

### External dimensions — **established [sourced]**

From the PolyScience/Breville *"the °Control Freak™ CMC850 Technical
Specifications"* sheet (identical document hosted at
`webstaurantstore.com/documents/specsheets/specsheet_for_polyscience_cmc850bssusa_induction_cooking_system.pdf`
and `savagebros.com/wp-content/uploads/2024/10/Breville-ControlFreak-CMC850_USA.pdf`),
verbatim:

> `Unit Dimensions (H x W x D)   110 x 350 x 470mm / 4.3 x 13.7 x 18.5in`
> `Shipping Weight               11.2 kg / 24.7 lb`
> `Power Range                   100–2400 Watts`
> `PRECISION INDUCTION HOB       Heat intensity control / Dual fan cooling system`

Corroborated independently by Culinary Depot ("13.7"W x 18.5"D") and
WebstaurantStore. Note the extracted sheet is the **220–240 V / 2400 W**
variant; the US model is 120 V / 1800 W in the same case.

**External envelope: 110 mm tall, 350 × 470 mm footprint.** Gross external
volume 18.1 L.

### Internal volume — **could not establish [sourced]**; estimate follows

No dimensioned teardown of the CMC850 or BMC800 exists publicly that I could
find. The only Breville induction teardown on iFixit is a different model and
carries no measurements. Everything below is **[inferred]** and should not be
quoted as measured.

Height budget from the 110 mm sourced external height, using conventional
single-hob stack-up:

| layer | est. | basis |
|---|---|---|
| ceramic glass top | 4 mm | standard hob glass |
| mica / air gap | 2–3 mm | coil-to-glass insulation |
| coil + ferrite bars | 12–18 mm | litz pancake coil with radial ferrites |
| clearance over PCB | 3–5 mm | assembly tolerance |
| PCB | 1.6 mm | standard |
| base moulding + feet | 8–12 mm | injection-moulded ABS base |

Under the coil this leaves roughly **20–30 mm** of board-side headroom — less
than the 39.5 mm the present capacitor needs. But the coil occupies only a
~200 mm circle within a 350 × 470 mm footprint, so a large majority of the
board area lies **outside** the coil, where the available height is the full
internal height less glass and base: roughly **85–95 mm**.

**Answer to the question actually asked:** in an enclosure of Control Freak
proportions, a 39.5 mm-tall capacitor is not height-constrained provided it
stands outside the coil footprint. Nor would the next case sizes be — the
0.22 µF (45.5 mm) and 0.33 µF (46 mm) FKP 1 parts still fit that budget, and so
would a row of six or seven 0.047 µF parts (24 mm tall, 13 mm wide on 37.5 mm
pitch, ~225 mm of board edge). **Enclosure height is not the binding
constraint on this decision.** That reinforces Q1's conclusion: the constraint
is the part family's current rating, not the space to put a bigger part in.

---

## What this changes

- **Q1's number is now defensible and slightly worse.** 5.2 A best estimate,
  4.0–6.2 A bracket, against 10.37 A required — a factor of ~2, not 1.7×. The
  caveat in `docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`
  ("confirm the figure from a table or from the manufacturer directly") is
  discharged: there is no table, there is not even a curve for this part, and
  the honest interpolation is worse than the figure it replaces.
- **Q2 is open and is worth less than it appeared.** The capacitor's thermal
  duty is essentially the same under either control scheme at equal average
  power, and the binding case is full power regardless.
- **Q3 rules out one hypothesis.** "A bigger capacitor would not fit" is not
  why this part was chosen and is not a reason to keep it.

## What this does not change

The 300 nF total tank value and the 47 kHz switching plan are untouched. This
document concerns the part family and case size only.
