# Resistor-set sensitivity ranking and temperature-coefficient budget for the four protection thresholds

<!-- provenance: commit=cb192812e6179af05b715299cfebb85064ce0cd8 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** Analysis only. No `elec/src/*.ato`, `pcb/`, or BOM files were modified.
**Subject:** OVP-01 (`OVPComparator`), THM-01 (`ThermalComparator`), THM-02
(`CoilThermalComparator`), UVL-02 (`LogicUVLOComparator`), all in
`elec/src/modules.ato`.

**Working-tree note:** this worktree's HEAD (`worktree-agent-ae3736ddd16914958`,
based on `fix/forced-segment-fail-closed`) is 199 commits behind
`docs/methodology-loop-discipline` and does not contain the 2026-07-27 OVP-01
retune. `git rebase docs/methodology-loop-discipline` was attempted per the
task's first-action instruction and produced conflicts squarely inside the
files this task is forbidden from touching (`elec/src/modules.ato`,
`pcb/temper.kicad_pcb`) plus add/add conflicts in the simulation harness. The
rebase was aborted rather than resolved (resolving it would mean editing the
forbidden files). All circuit content below (`modules.ato`, `main.ato`,
`components.ato`, `domain_manifest.yaml`, `docs/FUNCTIONAL_TEST_CRITERIA.md`,
`docs/STRATEGY.md`, `docs/hardware/*`) was read directly off
`docs/methodology-loop-discipline` via `git show <branch>:<path>`, i.e. the
real current state of those files, without merging them into this worktree.
Line numbers cited below are from that branch.

---

## Falsifier

Stated before computing: **"This analysis fails if tempco turns out negligible
against initial tolerance, in which case the cost question stands alone."**

**Did not fire.** At a working assumption of 45-60°C board-ambient rise above
the 25°C calibration point (justified below), Yageo RC-series 1% resistor
tempco (±100 ppm/°C, datasheet-verified) contributes **0.45-0.60% per
resistor** — smaller than the ±1% initial tolerance per part, but **not
negligible relative to it** (45-60% of the tolerance budget), and it stacks on
top of tolerance in the pessimistic (uncorrelated) case. For OVP-01, adding
tempco to the already-marginal tolerance-only worst case roughly **triples**
the window overshoot (from ~1.2 V/side to ~4-5 V/side at ΔT=60°C, see below).
For UVL-02, tempco erodes the margin from ~100 mV to ~70 mV but does not flip
the pass/fail verdict. The cost question does not stand alone; tempco is a
first-order term for OVP-01 specifically and changes which options remain
viable (see Part 3).

---

## Part 1 — OVP-01 sensitivity ranking

### Circuit model (verified against `modules.ato` and the closed form in
`docs/evidence/2026-07-27-ovp01-half-bus-retune.md`)

```
Rtop = r_div_top1 + r_div_top2 + r_div_top3   (3 x 430kΩ, nominal 1,290,000Ω)
N    = (Rtop + r_div_bot) / r_div_bot          (nominal 130)
Vref = VCC * r_ref_bot / (r_ref_top + r_ref_bot)   (VCC = 3.3V)
V_trip     = Vref * (N + Rtop/r_hyst)
hysteresis = VCC * Rtop / r_hyst                  (r_div_bot cancels exactly)
```

Nominal (recomputed independently, matching the evidence doc to the displayed
precision): **V_trip = 199.94 V, hysteresis = 6.877 V.**

### Per-resistor individual contribution (each resistor alone at ±1%, all others at nominal)

| Resistor | Nominal | ΔTrip at +1% | ΔTrip at −1% | ΔHyst at +1% |
|---|---|---|---|---|
| **r_div_bot** | 10 kΩ | **−1.933 V** | **+1.973 V** | 0.000 V (cancels exactly) |
| **r_ref_bot** | 10 kΩ | **+1.077 V** | −1.087 V | 0.000 V |
| **r_ref_top** | 11.8 kΩ | −1.076 V | **+1.088 V** | 0.000 V |
| r_div_top1 | 430 kΩ | +0.661 V | −0.661 V | +0.0229 V |
| r_div_top2 | 430 kΩ | +0.661 V | −0.661 V | +0.0229 V |
| r_div_top3 | 430 kΩ | +0.661 V | −0.661 V | +0.0229 V |
| r_hyst | 619 kΩ | −0.031 V | +0.032 V | **−0.068 V / +0.069 V** |

**Ranking for trip-point error:** `r_div_bot` dominates individually (≈1.95 V
per ±1%), with `r_ref_top`/`r_ref_bot` essentially tied for second (≈1.08 V
each). The three `r_div_top` parts are smaller individually (0.66 V each) but,
because they enter the formula only as a sum (`Rtop = R1+R2+R3`), their
**combined** worst-case contribution (≈1.98 V if all three move the same way)
matches `r_div_bot` almost exactly — this is a direct consequence of the
divider being a ratio of `Rtop` to `r_div_bot`; scaling either side by the
same fraction produces a proportional trip shift. `r_hyst` is essentially
irrelevant to the trip point (0.03 V) but is the single dominant term for
**hysteresis** error (0.068-0.069 V vs. ≤0.023 V for everything else); trip
and hysteresis are dominated by different resistors.

**A small subset does dominate**, confirming the premise of Part 3: of the
seven, `r_div_bot`, `r_ref_top`, and `r_ref_bot` account for essentially all
of the trip-point sensitivity that the fixed-reference resistors (as opposed
to the bus-side divider) can address; `r_hyst` matters for hysteresis alone.

### Structural insight (ratio, not absolute value) — tested, not assumed

Tested directly: scaling `Rtop` and `r_div_bot` by the *same* factor leaves
`N` unchanged (it is a pure ratio); scaling `r_ref_top` and `r_ref_bot` by the
same factor leaves `Vref` unchanged for the same reason. This is exactly why
`r_hyst` barely moves the trip point (630-part offset appears only through the
small `Rtop/r_hyst` additive term, not through a divider ratio) while it
dominates hysteresis (`hysteresis = VCC*Rtop/r_hyst` is a direct ratio in
`r_hyst`). This insight is load-bearing for the tempco analysis in Part 2/this
section (see below): **if every resistor in a given ratio pair drifts by the
same fraction in the same direction, the ratio — and hence the trip point —
is invariant to first order.**

### Correlation: worst-case vs. RSS, and whether relying on it is defensible

Three corner analyses, all recomputed independently (script:
`threshold_analysis.py`, this evidence run):

| Method | Trip range | Falls inside 195-205V? |
|---|---|---|
| **Independent worst-case**, all 7 resistors independently at their ±1% extreme (128 corners) | **193.89 - 206.16 V** | **No** — overshoots by ~1.1-1.2 V at each end |
| **Lumped-correlated top-3** (treat `r_div_top1-3` as one variable, matching the exact 32-corner sweep in `docs/evidence/2026-07-27-ovp01-half-bus-retune.md`) | **193.89 - 206.16 V** | **No — identical bound** |
| **RSS** (root-sum-square of each resistor's independent ±1% contribution, i.e. assuming statistically independent, normally-distributed errors) | 199.94 ± 2.72 V → **197.23 - 202.66 V** | **Yes, comfortably** |

**Two findings, and they point in different directions:**

1. **The correlation assumption among the three 430kΩ parts does not change the
   worst-case bound at all**, for this specific topology. Because `Rtop` enters
   the formula only as a sum `R1+R2+R3`, the extreme of that sum is identical
   whether the three parts are assumed to move together (correlated, e.g. same
   reel/lot systematic bias) or independently — the independent search's own
   worst corner already puts all three at the same sign. This is a genuine,
   verified result, not an assumption: the evidence doc's own "32 corner"
   sweep (5 effective variables, i.e. the three 430k lumped into one) produces
   the *exact same* bound as a full 128-corner independent sweep. Worth noting
   as a documentation correction: the evidence doc's comment says "every
   resistor... independently... all 32 corner combinations" — 7 independent
   binary variables is 128 corners, not 32; the 32-corner sweep it actually ran
   implicitly lumped the three 430k parts. The *arithmetic conclusion* is
   unaffected (both methods agree), but the description of the method was
   imprecise and should be corrected in that doc.
2. **Correlation matters enormously for RSS**, and this *is* where "is relying
   on correlation defensible" bites: the RSS figure (197.2-202.7V, comfortably
   inside the window) is only a reasonable estimate of the *population*
   behavior if the seven errors are independent, random draws — not a
   guarantee for any individual manufactured unit. There is no supplier
   tracking specification, matched-set binning, or incoming-inspection data in
   this project for these parts (all are catalog 1% RC-series resistors from
   presumably-independent reels); relying on RSS to declare compliance would
   be relying on an unverified statistical assumption to sign off a
   *protection* circuit, which is exactly the failure mode this project's own
   evidence trail (uncited IEC60335_REQUIREMENTS provenance, "documented
   verified" that later needed re-deriving, three previously-invented MPNs)
   warns against.

**The safety case should use the independent worst-case figure
(193.9-206.2V), not RSS.** By that standard, OVP-01 does not clear its window
at 1% tolerance — matching the pre-existing evidence doc's own conclusion, now
independently re-derived and confirmed rather than merely re-cited.

---

## Part 2 — Temperature-coefficient budget, all four thresholds

### Datasheet-verified tempco figures (not inferred)

| Part family | Tempco | Source |
|---|---|---|
| Yageo RC-series, 1% thick film (all values used: 10k, 11.8k, 430k, 619k, 698k, 100k, 3.74M, and the THM dividers' 9.09k/11.5k/34.8k/3.16k/3.32k/4.42k) | **±100 ppm/°C** | DigiKey product pages fetched directly for `RC0603FR-0710KL`, `RC1206FR-07430KL`, `RC0603FR-07619KL`, `RC0603FR-0711K8L` — all report ±100ppm/°C identically |
| Yageo RT-series, 0.1% thin film (candidate upgrade parts) | **±25 ppm/°C** | DigiKey pages for `RT1206BRD07430KL`, `RT0603BRD0711K8L`, `RT0603BRD07619KL`, `RT0603BRD0716K9L`, `RT0603BRD07562KL` — all ±25ppm/°C |
| Panasonic ERA-3A, 0.1% thin film (the project's existing 0.1% parts) | **±25 ppm/°C** | DigiKey page for `ERA-3AEB103V` and `ERA-3AEB6192V` |
| Vishay NTCALUG01A104GA (heatsink & coil NTC) | R25 **±2%**, B25/85 **±1.5%** (this is a manufacturing-spread term, not a linear tempco — the R-T curve *is* the sensing function) | DigiKey product page, fetched directly: "100k ±2%... B25/85 4190K ±1.5%... -40°C to 150°C" |
| TI TPS3700 (UVL-02) VIT_A | 387-400mV full datasheet range (already spans -40..85°C per the project's own prior citation to SBVS187G in the ato file/UVL02_DESIGN.md; I could not get clean text extraction from TI's or a mirror's PDF to independently re-verify the exact figure myself this session — see UNVERIFIED) | Carried over from `LogicUVLOComparator`'s own docstring |
| TI REF2025AIDDCR | Initial accuracy **±0.05%**, tempco **8 ppm/°C max** | DigiKey product page, fetched directly |

### Board-ambient assumption (stated explicitly, per instruction)

All four comparator circuits' fixed resistors (dividers, hysteresis resistors)
are **board-mounted**, not on the heatsink or coil. Only the NTC sensing
elements themselves sit at the hot junction (heatsink lug-mount for THM-01,
coil-mount for THM-02) — confirmed from `ThermalComparator`'s own comment
("lug-mount on heatsink... wired via flying leads anyway"). This project has
**no direct ambient-temperature measurement or spec for the specific board
region these safety comparators occupy.** The nearest analogous, already-cited
figures in this repo:

- `main.ato:77-79`: chassis-level `t_ambient_max = 50°C`, asserted in `[40,60]°C`.
- `docs/hardware/GATE_DRIVER_POWER_ARCHITECTURE_DECISION.md:368`: "control PCB
  away from induction coil, <85°C ambient."
- `docs/hardware/LMR51430_THERMAL_ANALYSIS.md`: uses 70°C as "worst-case
  ambient" and 85°C as "extreme ambient" for board-mounted parts near the
  MCU/control circuitry (same general board region as these comparators).

**Assumption used here:** ΔT = 45°C (conservative) to ΔT = 60°C (matching the
"extreme ambient" convention already used elsewhere in this design, and
matching the ~0.6%-per-resistor figure the task brief itself cites) above the
25°C calibration point at which the nominal trip values were derived. This is
**not measured for this specific board location** — it is inferred from the
nearest analogous board-zone figures already in the repo, and is flagged here
as an assumption rather than a verified fact.

### OVP-01 tempco budget

| Case | Trip range | vs. 195-205V window |
|---|---|---|
| Nominal | 199.94 V | centred |
| **Correlated** tempco only (uniform ±100ppm/°C, same direction, all 7 resistors, ΔT=60°C) | **199.94 V (unchanged)** | Confirms the ratio-invariance structural insight numerically: a uniform, same-sign, same-magnitude drift across a resistor pair that only ever appears as a ratio cancels exactly. |
| **Uncorrelated worst-case** tempco only (each resistor's actual TCR independently anywhere in ±100ppm/°C, ΔT=60°C) | 196.29 - 203.65 V | still inside window alone |
| Initial tolerance worst-case only (±1%, independent) | 193.89 - 206.16 V | **fails, ~1.1-1.2V over/under** |
| **Combined, ΔT=45°C** (tolerance + tempco stacked, uncorrelated/worst-case) | **191.23 - 209.02 V** | fails by ~3.8-4.0V |
| **Combined, ΔT=60°C** | **190.34 - 209.98 V** | fails by ~4.7-5.0V |

**Tempco roughly triples the size of the window violation** in the pessimistic
(no-correlation-guarantee) case, and this is the correct case to use for the
same reason given in Part 1: there is no supplier tracking spec for TCR across
these parts, so assuming correlated (self-cancelling) drift is not a
defensible basis for a protection circuit's safety case, even though it is the
mathematically-best-case outcome if it happened to hold.

### THM-01 (heatsink NTC, 85°C trip / 70°C recovery)

Circuit: NTC divider (`r_ntc_fixed` 10k) feeding `comp.INN`; reference divider
(`r_ref_top` 9.09k / `r_ref_bot` 11.5k) with `r_hyst` (34.8k) loading `comp.INP`
as a Schmitt trigger (Millman-solved per state, matching the ato file's own
closed form). Nominal (independently re-derived): **trip 84.96°C, release
69.79°C, hysteresis 15.17°C** — matches the module's own stated 85.0/69.8°C.

Per-parameter individual contribution to trip temperature:

| Parameter | Tolerance | ΔTrip |
|---|---|---|
| **NTC B-value** | ±1.5% | **±1.06 to +1.10°C — largest single term** |
| NTC R25 | ±2% | ±0.61-0.62°C |
| r_ref_top | ±1% | ±0.31°C |
| r_ntc_fixed | ±1% | ±0.31°C |
| r_ref_bot | ±1% | ±0.23°C |
| r_hyst | ±1% | ±0.08°C |

**Confirms the task's hypothesis: the NTC's own B-value tolerance dominates
every fixed-resistor term individually**, and is comparable to R25's
contribution. Worst-case combinations (all independent, 64 corners):

| Case | Trip | Release |
|---|---|---|
| NTC tolerance only (R25 ±2%, B ±1.5%) | 83.29 - 86.68°C | 68.47 - 71.14°C |
| Resistor tolerance only (±1% x4) | 84.04 - 85.88°C | 68.95 - 70.63°C |
| **All initial tolerance combined** | **82.40 - 87.62°C** | **67.65 - 72.01°C** |
| Combined + resistor tempco, ΔT=45°C (uncorrelated) | 82.00 - 88.05°C | 67.29 - 72.40°C |
| Combined + resistor tempco, ΔT=60°C | **81.87 - 88.19°C** | 67.16 - 72.53°C |

Trip and release ranges never overlap (worst-case trip floor 81.87°C is well
above worst-case release ceiling 72.53°C), so there is no risk of the
hysteresis band collapsing/chattering. `FUNCTIONAL_TEST_CRITERIA.md` §2.3
gives single point values (85°C/70°C), not a tolerance window like OVP-01 or
UVL-02 — there is no explicit pass/fail band to check against, which is
itself a documentation gap worth flagging. Reported here as: **worst-case trip
could be as high as 88.2°C and as low as 81.9°C**, a ±3.2°C spread around the
85°C target, dominated by the NTC's own manufacturing tolerance and not
meaningfully changed by adding resistor tempco (resistor tempco moves the
combined bound by only ~0.15-0.3°C beyond initial-tolerance-only, because the
NTC terms — not scaled by ΔT the same way — already dominate).

### THM-02 (coil NTC, 120°C trip / 100°C recovery)

Same topology, `r_ntc_fixed=3.32k`, `r_ref_top=3.16k`, `r_ref_bot=4.42k`,
`r_hyst=11.5k`. Nominal (independently re-derived): **trip 119.96°C, release
100.08°C**, matching the module's stated 120.0/100.1°C.

| Parameter | Tolerance | ΔTrip |
|---|---|---|
| **NTC B-value** | ±1.5% | **±1.84 to +1.92°C — largest single term, by a wide margin** |
| NTC R25 | ±2% | ±0.73-0.74°C |
| r_ntc_fixed | ±1% | ±0.37°C |
| r_ref_top | ±1% | ±0.37°C |
| r_ref_bot | ±1% | ±0.27°C |
| r_hyst | ±1% | ±0.10°C |

| Case | Trip | Release |
|---|---|---|
| NTC tolerance only | 117.40 - 122.63°C | 98.04 - 102.19°C |
| Resistor tolerance only | 118.86 - 121.08°C | 99.08 - 101.08°C |
| **All initial tolerance combined** | **116.33 - 123.77°C** | **97.07 - 103.22°C** |
| Combined + resistor tempco, ΔT=60°C | **115.69 - 124.47°C** | 96.49 - 103.84°C |

**This is the most safety-relevant single finding in this document.** The
module's own docstring already flags "SENSOR RATING CAVEAT: NTCALUG01A104GA is
specified to +125°C, and this gate trips at 120.3°C, so the sensor operates
within 5°C of its maximum" — but that caveat is written against the *nominal*
120.3°C figure. **The worst-case trip temperature computed here, including the
NTC's own datasheet-stated tolerance, reaches 124.47°C — within 0.5°C of the
125°C figure the module's docstring cites as the sensor's maximum**, before
any additional coil self-heating overshoot past the trip point during the
comparator's/relay's response time is even considered. Two things needed to
resolve this fully (out of scope to complete here, flagged as follow-up):

1. **The "+125°C" figure itself needs re-verification.** DigiKey's parametric
   page for `NTCALUG01A104GA`, fetched directly this session, states operating
   range **"-40°C ~ 150°C"** — 25°C higher than the ato docstring's "+125°C."
   I could not get readable text out of the Vishay PDF itself (repeated
   attempts returned encoded/unparseable content) to determine whether there
   is a *separate*, lower "accuracy guaranteed to" temperature distinct from
   the survival range, which would reconcile the two figures. **This is
   UNVERIFIED** — it is not clear from what I could access this session
   whether the true margin at worst-case trip is 0.5°C (if 125°C is the real
   accuracy limit) or 25.5°C (if 150°C is the applicable figure and the
   docstring's 125°C was itself an error or an overly-conservative
   assumption). This should be resolved before treating THM-02 as closed.
2. Whichever figure is correct, the **runaway-boundary margin check** cited in
   `FUNCTIONAL_TEST_CRITERIA.md`'s appendix (">=20°C margin below runaway
   boundary... 432 sweep points") was performed against a boundary-map
   simulation, not against this specific resistor-network's real worst-case
   trip-temperature spread computed here — it is not verified in this
   document whether that 20°C margin still holds once the NTC's own tolerance
   is folded in on top of whatever the boundary-map sweep already covered.

### UVL-02 (3.3V logic rail, <2.9V trip / >3.0V recover)

Circuit (Millman, confirmed against the ato file's own derivation):
`r_div_top=698k`, `r_div_bot=100k`, `r_hyst=3.74M`, `VIT_A` nominal 394.5mV
(TPS3700, range 387-400mV per the project's existing citation).

Nominal (independently re-derived, matches ato exactly): **trip 2.7150V,
recover 3.2217V.**

| Case | Trip (ceiling 2.9V) | Recover (floor 3.0V) |
|---|---|---|
| Initial tolerance only (resistors ±1% + VIT_A 387-400mV) | 2.6183 - **2.8004 V** | **3.1056** - 3.3246 V |
| **+ resistor tempco, ΔT=45°C, uncorrelated** | 2.5983 - 2.8221 V | 3.0812 - 3.3510 V |
| **+ resistor tempco, ΔT=60°C, uncorrelated** | 2.5917 - **2.8294 V** | **3.0731** - 3.3599 V |
| Correlated uniform tempco, ΔT=60°C | 2.7150 (unchanged) | 3.2217 (unchanged) — same ratio-invariance as OVP-01 |

**UVL-02 clears its window even under the pessimistic combined case**, though
with reduced margin: trip-side margin shrinks from ~100mV to ~70.6mV, recover-
side margin from ~106mV to ~73.1mV. Individual resistor ranking:
`r_div_bot`(100k, ±0.023-0.028V) > `r_div_top`(698k, ±0.02V) > `r_hyst`(3.74M,
±0.004V) — `r_hyst` is nearly irrelevant here, the opposite of its role in
OVP-01, because in this topology `r_hyst`'s conductance is a much smaller
fraction of the total node conductance. **UVL-02 does not need any of the
Part 3 remediation options — it already meets spec with tolerance and tempco
combined.**

---

## Part 3 — Costed options for OVP-01

All prices below are unit price at the stated DigiKey quantity break, fetched
directly this session (not estimated). "1k qty" is used as the comparison
tier throughout since that is the tier reported for the project's own
existing 0.1% parts.

### Pricing anchor — re-examined

The task names `r_low_top` (61.3kΩ ±0.1%, `ERA-3AEB6132V`,
`modules.ato:1620-1622`) as the pricing anchor for "0.1% parts already
bought." **This anchor does not check out.** 61.3kΩ is not a standard
resistor value in any IEC 60063 decade series: computing the E96 sequence
directly gives 60.4, **61.9**, 63.4 as the neighbors (no 61.3); computing E192
gives 60.43, **61.16 (≈61.2)**, **61.90**, 62.64 (no 61.3 or 61.4 either).
`ERA-3AEB6132V` does not appear in DigiKey's or Mouser's catalog search (both
queried directly; DigiKey returns "did not return any results"), while the
neighboring, numerically-consistent part `ERA-3AEB6192V` (61.9kΩ, same
"EB61x2V" naming pattern) **does** exist and is stocked. This looks like the
same failure mode this project has been bitten by before (invented/malformed
MPNs) — flagged here as a new instance, not a previously-known one (searched
this repo's history for prior mention of `ERA-3AEB6132V` or "61.3k"; none
found). **I used the verified real neighbor, `ERA-3AEB6192V` (61.9kΩ ±0.1%,
0603, ±25ppm/°C), as the practical anchor instead**: $0.10/1, $0.07/10,
$0.0577/100, **$0.0479/1000**. `r_low_bottom` (`ERA-3AEB103V`, 10kΩ ±0.1%) *is*
real and verified: identical pricing, $0.0479/1000.

### Baseline (existing 1% parts, DigiKey, cut-tape, per unit)

| Part | Value/pkg | 1 | 10 | 100 | 1000 |
|---|---|---|---|---|---|
| `RC1206FR-07430KL` (r_div_top x3) | 430k, 1206 | $0.10 | $0.047 | $0.0247 | $0.01477 |
| `RC0603FR-0710KL` (r_div_bot, r_ref_bot) | 10k, 0603 | $0.10 | $0.025 | $0.0122 | $0.00661 |
| `RC0603FR-0711K8L` (r_ref_top) | 11.8k, 0603 | $0.10 | $0.025 | $0.0122 | $0.00661 |
| `RC0603FR-07619KL` (r_hyst) | 619k, 0603 | $0.10 | $0.025 | $0.0122 | $0.00661 |

Total for the 7-part group at 1k qty: **$0.07075/board.**

### Option A — all seven to 0.1% thin film

| Part (replacement) | Value/pkg | 1000 qty |
|---|---|---|
| `RT1206BRD07430KL` x3 | 430k, 1206, ±0.1%, ±25ppm/°C | $0.1215 each |
| `RT0603BRD0710KL`-equiv (`ERA-3AEB103V` used as verified 10k 0.1% part) x2 | 10k, 0603 | $0.0479 each |
| `RT0603BRD0711K8L` | 11.8k, 0603, ±0.1% | $0.04654 |
| `RT0603BRD07619KL` | 619k, 0603, ±0.1% | $0.04319 |

Total: **$0.55003/board** at 1k qty → **incremental cost +$0.479/board.**

Worst-case (independent, all 7 at ±0.1%): trip 199.33-200.56V (tolerance
only), **198.42-201.48V with tempco (ΔT=60°C) included** — passes with wide
margin.

### Option B — sensitivity-driven partial upgrade (r_div_bot, r_ref_top, r_ref_bot only)

Upgrades exactly the three dominant individual contributors identified in
Part 1; leaves `r_div_top1-3` (protective-impedance chain, unchanged 1%
RC1206) and `r_hyst` (negligible trip-point contributor) at 1%.

Incremental cost: `r_div_bot` $0.00661→$0.0479 (+$0.04129), `r_ref_top`
$0.00661→$0.04654 (+$0.03993), `r_ref_bot` $0.00661→$0.0479 (+$0.04129).
**Total incremental: +$0.1225/board** at 1k qty.

Worst-case: tolerance only 197.52-202.38V (passes); **with tempco (ΔT=60°C):
195.71-204.22V** — passes, but with only ~0.7-0.8V margin at each edge (the
three untouched 430k parts and `r_hyst` still contribute their full ±1%+tempco
error).

### Option C — re-reference to REF2025 (recommended)

**Feasibility check:**

- **Same power domain — confirmed.** `main.ato:408-409` ties `rtd_pan.power`
  (the `RTDSensing` instance housing `REF2025`) to `vcc_3v3`/`gnd`;
  `main.ato:428-429` ties `safety.power_3v3` (housing `OVPComparator`) to the
  same `vcc_3v3`/`gnd` nets. Both REF2025 and OVP-01's comparator sit on the
  identical 3.3V logic rail.
- **Drive capacity — confirmed with large margin.** REF2025's `VBIAS` (1.25V)
  is already loaded by `RTDSensing`'s two RTD-window dividers, drawing
  roughly 17.5µA + 78.5µA ≈ 96µA total. Its `VREF` (2.5V) output is
  **completely unused** anywhere else in the design (checked every
  `reference.` reference in `modules.ato`; only `VBIAS` is wired). The part's
  rated output current is **20mA** (DigiKey, direct fetch) — either output has
  enormous headroom for OVP-01's ~150-190µA reference-leg draw.
- **Initial accuracy / tempco — confirmed, and dramatically better than the
  resistor divider it would replace:** REF2025AIDDCR is **±0.05% initial
  accuracy, 8ppm/°C max tempco** (DigiKey, direct fetch) vs. the current
  `r_ref_top`/`r_ref_bot` divider's effective ~1% ratio tolerance (contributing
  ±1.08V to trip point per Part 1) and 100ppm/°C tempco.

**Concept:** delete `r_ref_top` and `r_ref_bot` outright; tie `comp.INN`
directly to REF2025's `VREF` (2.5V, currently idle) instead of the
`power.vcc`-derived divider. This changes the trip-point equation's `Vref`
term from a divider ratio to a fixed 2.5V, which requires re-deriving `N` (via
`r_div_bot`, which is **not** part of the declared protective-impedance chain
— `domain_manifest.yaml`'s `ovp01_comparator_divider` entry lists only
`r_div_top1-3`, `min_length: 3` — so changing `r_div_bot`'s value does not
reopen the IEC 60335 protective-impedance/touch-current analysis) and
`r_hyst` (to hit both the trip and hysteresis targets simultaneously, exactly
as the original 2026-07-27 retune did for `r_ref_top`/`r_hyst`).

Worked illustrative values (nearest standard 0.1% E96 parts, both verified
real and stocked): `r_div_bot: 10k → 16.9k` (`RT0603BRD0716K9L`, ±0.1%,
±25ppm/°C, $0.04654/1k), `r_hyst: 619k → 562k` (`RT0603BRD07562KL`, ±0.1%,
±25ppm/°C, $0.04319/1k). `r_div_top1-3` **unchanged** (still 1% RC1206,
protective-impedance chain untouched).

Result (independently computed): nominal trip 199.07V, hysteresis 7.57V.
Worst-case tolerance-only: **196.81-201.33V.** **Worst-case tolerance + tempco
(ΔT=60°C, uncorrelated): 195.25-202.91V** — passes the 195-205V window with
margin at both ends, and hysteresis stays 7.43-7.72V (comfortably inside
5-10V) even in that combined worst case. This is the widest margin of any
option evaluated, including full Option A.

**Cost:** delete `r_ref_top` (−$0.00661) and `r_ref_bot` (−$0.00661); upgrade
`r_div_bot` (+$0.03993) and `r_hyst` (+$0.03658). **Net incremental: +$0.0633/
board at 1k qty** — roughly 1/2 of Option B's cost and 1/8 of Option A's,
while achieving the best margin of the three, using an IC that is **already
instantiated and already paid for** in this design (zero new component
introduced), and **removing two components** (assembly/placement cost
reduction, one fewer failure mode, not quantified in the resistor-line price
above).

**Residual open items (implementation-phase, not resolved here):** (1) a
routing trace from `RTDSensing`'s `REF2025.VREF` to `SafetyInterlock`'s
`OVPComparator.comp.INN` crosses between two different top-level module
instances — physical board proximity and noise-pickup on a precision analog
reference trace were not checked in this pass; (2) the exact E96 pair above is
illustrative, chosen to demonstrate feasibility and cost order-of-magnitude —
a proper E96/E192 sweep (as was done for the original `r_ref_top`/`r_hyst`
retune) should be run before finalizing; (3) removing the divider from
`power.vcc` eliminates that sensitivity but was not itself quantified here
(the current design's trip point does depend on `VCC`'s own tolerance/noise
through the `Vref = VCC*rrefbot/(...)` term — Option C removes this
dependency, which is a real but unquantified additional benefit beyond the
numbers above).

### Option D — widen the spec

Traced `195-205V / 5-10V` back to `FUNCTIONAL_TEST_CRITERIA.md` §2.2's **"DC
Bus OVP: 400V setting, 390-410V trip, 10-20V hysteresis."** Git-blamed to its
origin: introduced whole-cloth in commit `3f27dc58` ("chore: add comprehensive
.gitignore and commit all pending changes", 2025-12-17) — a bulk commit, not a
derivation. No formula, standard citation, or supporting calculation appears
anywhere in the document or its history. This **is the same pattern** as
`docs/STRATEGY.md`'s own conclusion about `IEC60335_REQUIREMENTS`: "the
provenance remains uncited."

However, the number is not *floating free* either — `main.ato:220-226` bounds
it between two real, cited engineering constraints already in the design:
`v_bus_max = 340V` (nominal operating ceiling, `main.ato:49`) and `v_cap_max =
500V` (two 250V-rated bus capacitors in series, `main.ato:224`), with
assertions `v_ovp_trip < v_cap_max` and `v_ovp_trip > v_bus_max`. So while the
*exact* 390-410V window and its width are uncited/arbitrary within that range,
the range itself (340-500V) is not baseless.

**Conclusion: widening is technically available and would not contradict any
cited external standard**, but **it is not recommended here**, because Option
C achieves full compliance (with the widest margin of any option) for
$0.06/board and zero new components — there is no need to relax a documented
acceptance criterion (however weakly derived) when a near-free hardware fix
already clears it. Keep Option D as a fallback only if a future hardware
constraint makes B/C/A infeasible.

### Recommendation

**Option C** (re-reference OVP-01's `comp.INN` to `REF2025.VREF`, retune
`r_div_bot` and `r_hyst`, delete `r_ref_top`/`r_ref_bot`). It is the cheapest
option that passes the combined-worst-case tolerance+tempco corner (195.25-
202.91V vs. the 195-205V window), cheaper than the sensitivity-driven partial
upgrade (Option B) which only barely passes the same combined test (195.71-
204.22V, ~0.3-0.5V less margin at $0.06/board more), uses an IC already paid
for in this BOM, and reduces total part count. Full Option A is not
recommended: it costs 7.6x Option C for a margin improvement (198.42-201.48V)
that Option C's structural fix already renders unnecessary.

---

## UNVERIFIED list

- **`NTCALUG01A104GA`'s true accuracy-guaranteed maximum temperature.**
  DigiKey's parametric page states "-40°C ~ 150°C"; the ato file's own
  docstring for `CoilThermalComparator` states "+125°C." I could not extract
  readable text from Vishay's own PDF (`vishay.com/docs/29092/ntcalug01a.pdf`)
  despite four attempts across this session — it returns encoded/unparsed
  content through WebFetch every time. This materially affects how much
  margin THM-02's worst-case 124.47°C trip actually has (0.5°C vs. 25.5°C) —
  **this is the single most important unresolved item in this document.**
- **TPS3700's VIT_A 387-400mV range** — carried over from the project's own
  prior citation (`docs/hardware/UVL02_DESIGN.md`, attributed to datasheet
  SBVS187G) rather than independently re-fetched and re-read by me this
  session; I attempted to fetch `ti.com/lit/ds/symlink/tps3700.pdf` directly
  and got a 200 response but could not get readable table text out of it.
  Treated as reliable because the project's own prior work already did this
  verification, but I did not personally re-confirm the exact mV figures
  against a page I could read.
- **Board-ambient ΔT (45-60°C) for the comparator resistor sets.** This is my
  assumption, built from analogous board-zone figures elsewhere in this repo
  (`main.ato`'s 50°C chassis ambient, the gate-driver doc's "<85°C ambient"
  for control-PCB-away-from-coil, the LMR51430 analysis's 70/85°C
  worst-case/extreme-ambient convention) — there is no direct measurement or
  spec for the specific board region these four comparators occupy.
- **The exact E96/E192 component values for Option C** (`16.9k`/`562k` shown)
  are illustrative, not a final selection — verified to exist and be stocked,
  but not run through the same exhaustive E96 sweep the original 2026-07-27
  retune used to find the true optimum.
- **REF2025 trace routing/noise feasibility** between the `RTDSensing` and
  `SafetyInterlock` module instances — not checked; flagged as an
  implementation-phase item for Option C.
- **Digikey pricing reflects list/cut-tape pricing at the time fetched this
  session** and is not a quote; distributor pricing changes over time and by
  account tier.

## Falsifier disposition (restated)

Did not fire. Tempco (0.45-0.6% per resistor at the assumed board ΔT) is
comparable to, not negligible against, the ±1% initial tolerance, and for
OVP-01 specifically it roughly triples the magnitude of an already-marginal
tolerance-only window violation under the (correct, for a safety case)
uncorrelated worst-case treatment. The cost question in Part 3 does not stand
alone — it is materially informed by which combination of tolerance and
tempco terms a given option needs to clear.
