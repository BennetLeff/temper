# RTD-chain / rail-monitor Panasonic ERA-series resistor resolution — 2026-07-27

**Scope:** three `mpn_fabrication_gate.py` findings, all in
`RTDSensing` (`elec/src/modules.ato`): `r_low_top` (61.3 kΩ,
`ERA-3AEB6132V`), `r_high_top` (5.93 kΩ, `ERA-3AEB5931V`), and `r_avdd_top`
(616 kΩ, `ERA-3AEB6163V`). All three sit in a sensing/reference divider (the
independent RTD hardware-fault window and the `RTD_AVDD` rail monitor), so
each required re-deriving the affected threshold, not just swapping a part
number. No `pcb/` files were touched.

**Base:** the initial worktree checkout was 213 commits behind and 3 ahead
of `docs/methodology-loop-discipline` (diverged at `ee9ba6ba`); rebasing
produced conflicts in 9 files including `elec/src/modules.ato` and
`pcb/temper.kicad_pcb`. Per the coordinator's diagnosis, the 3 "ahead"
commits were not unique work (`866de677` is the squash-merge of PR #344,
already reachable from `origin/main`; the other two are auto-generated
chore commits), so the fix was `git checkout -B <branch>
docs/methodology-loop-discipline` (repoint, not rebase) rather than a merge.
`scripts/assert-base.sh docs/methodology-loop-discipline` confirmed exit 0
(HEAD `9f793467...`) before any implementation. `scripts/mpn_fabrication_gate.py`
was run first and confirmed 5 findings (this task's 3, plus
`OCPComparator.r_ref_top` and `LogicUVLOComparator.r_div_bot`, which a
concurrent agent was assigned). Both agents' commits landed in the same
working tree; that agent's two fixes (`f66bb00c`, `ed89a3a2`) were already
present by the time this task's own edits were made — see "Attribution"
below.

---

## Falsifier (stated before implementing)

> If a real, distributor-confirmed E96/E192 Panasonic ERA part cannot be
> found within roughly ±2% of any of the three declared values, or if the
> nearest real part pushes a threshold outside its required window (RTD
> short/valid/open separation, or the TPS3700 rail-monitor's 2.70–2.97 V
> corner), then this is not a simple value swap and needs escalation
> (topology change or spec review) instead.

**Did not fire for any of the three.** Real E-series parts exist within
0.03–0.5% of each declared value, and every affected threshold/margin was
recomputed (worst-case tolerance, and separately with 25 ppm/°C tempco at
ΔT=45/60°C) and stays inside its required window — see per-part sections
below. One secondary finding did surface during the search, reported as its
own falsifier disposition: **the audit's proposed 61.9 kΩ neighbour for
case 1 had to be independently checked against its nearer numerical
neighbour, 61.2 kΩ** — see Defect 1.

---

## Defect 1 — `r_low_top` (RTD window, low threshold), 61.3 kΩ

### Status: CONFIRMED fabricated (already established by the audit; independently reverified here)

- **61.3 kΩ is not an E96 or E192 member.** `scripts/mpn_fabrication_gate.py`
  computes the E192 neighbours as 60.4, **61.2**, **61.9** kΩ (no 61.3).
- **`ERA-3AEB6132V` does not exist at DigiKey**, fetched directly this
  session: `https://www.digikey.com/en/products/result?keywords=ERA-3AEB6132V`
  → "Sorry, 'ERA-3AEB6132V' did not return any results."
- **The audit's proposed replacement, `ERA-3AEB6192V` (61.9 kΩ), was
  independently verified, not adopted on report**:
  `https://www.digikey.com/en/products/result?keywords=ERA-3AEB6192V` →
  exact match, **61.9 kΩ, ±0.1%, ±25 ppm/°C, Panasonic Industry, In-Stock:
  49,677**, 0603 (1608 Metric), AEC-Q200.
- **The nearer numerical neighbour, 61.2 kΩ, was checked and rejected**:
  `ERA-3AEB6122V` (the value's natural ERA-3A encoding) returns **zero
  results** at DigiKey (`https://www.digikey.com/en/products/result?keywords=ERA-3AEB6122V`
  → "did not return any results"). This is a real finding, not an
  assumption: 61.2 kΩ is 0.1 kΩ closer to 61.3 kΩ than 61.9 kΩ is (0.6 kΩ),
  so a naive "nearest E-series value" choice would have picked 61.2 kΩ —
  but Panasonic does not appear to manufacture/stock that specific ERA-3A
  part. **Real-part availability, not numeric proximity, is the binding
  constraint**, which is exactly why this had to be checked with a live
  fetch rather than computed.

### Chosen replacement: 61.9 kΩ, `ERA-3AEB6192V` (0603, unchanged footprint)

### Threshold impact

Low-window threshold `V_low = VBIAS · r_low_bottom / (r_low_top + r_low_bottom)`,
`VBIAS = 1.25 V` (REF2025):

- Old (fabricated) nominal: 1.25 × 10/71.3 = **175.32 mV**
- New nominal: 1.25 × 10/71.9 = **173.85 mV** (−1.47 mV shift)

Worst-case margin (independent ±0.1% on all four divider resistors, REF2025
±0.13% incl. its own tempco, MAX31865 VBIAS 1.95–2.06 V, RREF ±0.1%,
TLV3201 ±4 mV offset — exhaustive corner grid, not just the module's
hypothesis-sampled property test):

| Boundary (must stay positive) | Old (616→~fabricated 61.3k) | New (61.9k), initial tol. | New, +tempco ΔT=60°C |
|---|---:|---:|---:|
| short (10Ω) vs. low threshold | 123.9 mV | 122.5 mV | 122.0 mV |
| valid-min (100Ω) vs. low threshold | 187.8 mV | 189.2 mV | 188.8 mV |

Both margins stay large and are essentially unaffected by the substitution
(<2 mV shift either way). This boundary is not the tight one in the circuit
(see Defect 2).

---

## Defect 2 — `r_high_top` (RTD window, high threshold), 5.93 kΩ

### Status: CONFIRMED fabricated (new finding this session)

- **5.93 kΩ is not an E96 or E192 member.** Gate-computed E192 neighbours:
  5.9, 5.97, 5.83 kΩ (no 5.93).
- **`ERA-3AEB5931V` does not exist at DigiKey**, fetched directly:
  `https://www.digikey.com/en/products/result?keywords=ERA-3AEB5931V` →
  "did not return any results."
- **Candidates checked, in order of numeric proximity:**
  - `ERA-3AEB5901V` (5.90 kΩ, Δ=0.03 kΩ): **exists** —
    `https://www.digikey.com/en/products/result?keywords=ERA-3AEB5901V` →
    exact match, **5.9 kΩ, ±0.1%, ±25 ppm/°C, Panasonic Industry**, 0603,
    AEC-Q200. **Stock: 0 units, standard lead time 33 weeks** (real part,
    currently backordered — flagged below, not a blocker for this fix).
  - `ERA-3AEB5971V` (5.97 kΩ, Δ=0.04 kΩ): **no DigiKey hit.**
  - `ERA-3AEB5831V` (5.83 kΩ, Δ=0.10 kΩ): **no DigiKey hit.**
  - Mouser was attempted as a second source for `ERA-3AEB5901V` and for the
    two rejected candidates; every Mouser fetch this session timed out
    (60 s) — recorded as UNVERIFIED/unreachable, not as absence.

### Chosen replacement: 5.9 kΩ, `ERA-3AEB5901V` (0603, unchanged footprint)

### Threshold impact

High-window threshold `V_high = VBIAS · r_high_bottom / (r_high_top + r_high_bottom)`:

- Old (fabricated) nominal: 1.25 × 10/15.93 = **784.68 mV**
- New nominal: 1.25 × 10/15.90 = **786.16 mV** (+1.48 mV shift)

Worst-case margin (same exhaustive corner grid as Defect 1):

| Boundary (must stay positive) | Old (fabricated 5.93k) | New (5.9k), initial tol. | New, +tempco ΔT=60°C |
|---|---:|---:|---:|
| valid-max (194.1Ω) vs. high threshold | 137.96 mV | 139.44 mV | 138.57 mV |
| **open (300Ω) vs. high threshold** | **10.61 mV** | **9.13 mV** | **8.25 mV** |

**This is the tightest margin anywhere in the RTD window circuit, both
before and after this fix.** It was already thin (10.6 mV) with the
fabricated value; the real replacement narrows it further by about 1.5–2.4 mV
(to 8.25 mV at ΔT=60°C combined tolerance+tempco) because 5.90 kΩ sits on
the side of 5.93 kΩ that raises the high threshold slightly, moving it
closer to the open-circuit sensed voltage. **The margin stays positive at
every corner checked** (exhaustive grid over ±0.1% resistor tolerance +
tempco, ±0.13% REF2025 tolerance, MAX31865 VBIAS 1.95–2.06 V, RREF ±0.1%,
±4 mV TLV3201 offset — this is stronger evidence than the module's own
`test_captured_ref2025_divider_network_separates_every_rtd_corner`
Hypothesis test, which samples the open range `[300, 1000)` continuously
and is unlikely to hit exactly R=300Ω, the true worst corner since sensed
voltage is monotonic increasing in R). This is reported as a real, if small,
degradation — not hidden — per the task's instruction to say so with
arithmetic when a substitution narrows a margin.

---

## Defect 3 — `r_avdd_top` (TPS3700 rail monitor divider), 616 kΩ

### Status: CONFIRMED fabricated (new finding this session)

- **616 kΩ is not an E96 or E192 member.** Gate-computed E192 neighbours:
  619, 612, 626 kΩ (no 616).
- **`ERA-3AEB6163V` does not exist at DigiKey**, fetched directly:
  `https://www.digikey.com/en/products/result?keywords=ERA-3AEB6163V` →
  "did not return any results."
- **None of the three E192 neighbours exist as ERA-3A (0603) parts either**,
  each checked individually: `ERA-3AEB6193V` (619k), `ERA-3AEB6123V` (612k),
  `ERA-3AEB6263V` (626k) — all "did not return any results" at DigiKey. Two
  further E96/E192 neighbours one step out, `ERA-3AEB6043V` (604k) and
  `ERA-3AEB6343V` (634k), were also checked and also do not exist.
- **This is a package/series-range problem, not just a value problem.**
  Checking further up the ERA-3A (0603) value range: `ERA-3AEB334V` (330 kΩ)
  exists (out of stock, 33-week lead time); `ERA-3AEB394V` (390 kΩ) does
  **not** exist, and DigiKey's own search page volunteers
  `ERA-6AEB394V` as an alternative. That part **does** exist — **390 kΩ,
  ±0.1%, ±25 ppm/°C, 0805 (2012 Metric), In-Stock: 14,344** — confirming
  that Panasonic's ERA-3A (0603) thin-film series tops out somewhere below
  ~390 kΩ, and the 600 kΩ decade is only available in the larger ERA-6A
  (0805) package. Checked directly: **`ERA-6AEB6193V` exists** —
  `https://www.digikey.com/en/products/result?keywords=ERA-6AEB6193V` →
  exact match, **619 kΩ, ±0.1%, ±25 ppm/°C, Panasonic Industry, 0805,
  In-Stock: 6,638**, AEC-Q200. (`ERA-6AEB6123V` (612k) and `ERA-6AEB6263V`
  (626k) were also checked in the 0805 family and do **not** exist, so 619 kΩ
  is not just the nearest value — it is the only one of the three E192
  neighbours available in either package.)

### Chosen replacement: 619 kΩ, `ERA-6AEB6193V`, **package changed 0603 → 0805**

`elec/src/modules.ato`'s `Resistor` component defaults to the
`Resistor_SMD:R_0603_1608Metric` footprint; `r_avdd_top` previously relied on
that default (matching the fabricated part's implied 0603 package). This fix
adds an explicit `r_avdd_top.footprint = "Resistor_SMD:R_0805_2012Metric"`
override in `elec/src/modules.ato`, matching how the design already
overrides `r_ref`'s footprint to 0805 for its own ERA-6A part
(`ERA-6AEB431V`). This is a change to the atopile source only; `pcb/` was
not touched, and `make netlist` (which does not write to `pcb/`, confirmed
by diffing `git status pcb/` before/after) still builds clean — the
placement-side footprint resync is a separate, later build step outside
this task's scope.

### Threshold impact (TPS3700 UV monitor)

`V_trip = VIT_A · (r_avdd_top + r_avdd_bottom) / r_avdd_bottom`, TPS3700
`VIT_A` range 387–400 mV (carried over from the project's existing UVL-02
citation to the same TI part; not independently re-fetched this session,
see UNVERIFIED). Required window: `2.70 V < trip_min` (TLV3201 minimum
supply) and `trip_max < 2.97 V` (3.3V −10% normal-rail floor).

| Case | Old (fabricated 616k/100k) | New (619k/100k) |
|---|---:|---:|
| Initial tolerance only (±0.1% each) | 2.7662–2.8689 V | 2.7777–2.8810 V |
| + tempco, ΔT=45°C (25 ppm/°C, uncorrelated) | 2.7608–2.8745 V | 2.7724–2.8865 V |
| + tempco, ΔT=60°C | 2.7590–2.8764 V | 2.7706–2.8884 V |
| Margin above 2.70 V floor (ΔT=60°C case) | 59.0 mV | **70.6 mV** |
| Margin below 2.97 V ceiling (ΔT=60°C case) | 93.6 mV | **81.6 mV** |

Both margins stay comfortably positive; the window is, if anything,
slightly better centred with the real part (more balanced margins: 70.6/81.6
mV vs. the fabricated value's 59.0/93.6 mV). The nominal trip point (using
the ngspice-modelled TPS3700 behavioural part, `VIT_A=394.5 mV` from the
model header) moved from **2.825 V to 2.837 V** (measured via
`simulation/harness/run_uvl02_sim.py`, deterministic across 5 runs) — a
+12.3 mV shift, still well clear of the 2.9 V UVL-02 spec ceiling this
harness compares against (as a labelled CANDIDATE, not a confirmed UVL-02
circuit — see the harness's own scope caveat).

---

## Tempco treatment (all three parts)

Panasonic ERA-3A/ERA-6A is a 25 ppm/°C thin-film series (datasheet-verified
via the DigiKey pages fetched above, and already cited in
`docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`). Per that
document's board-ambient convention (ΔT=45–60°C above the 25°C calibration
point, inferred from analogous board-zone figures elsewhere in this repo —
no direct measurement exists for this specific board region), tempco
contributes an added **0.1125–0.15% per resistor** on top of the ±0.1%
initial tolerance, treated **uncorrelated/worst-case** (each resistor
independently at its own tempco extreme), consistent with that document's
own methodology and its conclusion that correlated/RSS treatment is not
defensible for a protection circuit without supplier tracking data. All
margin tables above report both the initial-tolerance-only and the
ΔT=60°C-combined cases; no threshold flips sign or crosses its required
window at either.

---

## Attribution

`OCPComparator.r_ref_top` (3.2 kΩ → 3.24 kΩ) and
`LogicUVLOComparator.r_div_bot` (100 kΩ value / 10 kΩ-encoding MPN
mismatch → corrected) were fixed by a concurrent agent (commits `f66bb00c`,
`ed89a3a2`); see `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`.
Those two were **not** touched by this task's edits (diff scope confirmed:
this task's uncommitted diff to `elec/src/modules.ato` touches only
`r_low_top`, `r_high_top`, and `r_avdd_top`).

## Verification

- `scripts/assert-base.sh docs/methodology-loop-discipline`: exit 0.
- `scripts/mpn_fabrication_gate.py`: started at **5** findings (this task's
  3 + the concurrent agent's 2); ends at **0** ("MPN fabrication gate PASSED
  — 0 new violations") once both agents' fixes are applied. This task's own
  contribution is 3 fewer.
- `make netlist`: build succeeded, **76 PASSED** assertions, 0 failed
  (matches the task's stated baseline count). `git status pcb/` empty both
  before and after the build — `pcb/` was not touched.
- `scripts/check_domain_partition.py`: exit 0, "PASSED — 0 domain crossings,
  0 isolator-barrier breaches, 0 protective-impedance chain defects."
- `scripts/capacity_budget_gate.py`: exit 0, "Design capacity budget gate
  PASSED — 0 defects."
- `packages/temper-placer/tests/validation/` (RTD-scoped): 28 passed
  (`test_rtd_fault_latch_pbt.py`, `test_rtd_safety_pbt.py`,
  `test_rtd_window_comparator_pbt.py`), after updating
  `RTD_LOW_WINDOW_TOP_OHM`/`RTD_HIGH_WINDOW_TOP_OHM` in `rtd_safety.py` and
  the `_RTD_AVDD_MONITOR` trip corners (2.766–2.870 V → 2.777–2.882 V) in
  `test_rtd_window_comparator_pbt.py` to match the corrected resistor values.
- `elec/validation/` (RTD-scoped SPICE decks): 11 passed, including
  `test_rtd_window_selected_values_spice.py` and
  `test_rtd_window_ported_models_spice.py` after updating the literal
  resistor values in `rtd_window_selected_values.cir` and
  `rtd_window_ported_models.cir`, and `test_rtd_fault_latch_transient_spice.py`
  (unaffected, uses behavioural fault injection not tied to these values).
- `scripts/tests/test_mpn_fabrication_gate.py`: 16 passed (uses synthetic
  fixtures, not live `modules.ato`, so unaffected by this change; confirms
  the gate logic itself still works).
- `simulation/harness/run_uvl02_sim.py` (the TPS3700 rail-monitor CANDIDATE
  sim covering `r_avdd_top`): re-run after updating `R_AVDD_TOP_OHM` from
  616,000 to 619,000 and replacing a hardcoded `2.8250` hand-derived-trip
  literal with a value computed from the same constants (the literal had
  silently gone stale after a resistor-value edit once already — replaced
  so this class of drift can't recur). New result: measured trip
  2.8373 V, hand-derived 2.8365 V (agreement within 0.8 mV, deterministic
  across 5 runs), vs. the old 2.825 V nominal — a +12.3 mV shift, still
  clear of the 2.9 V spec line this harness compares against.

## UNVERIFIED

- **`ERA-3AEB5901V` (5.9 kΩ replacement for r_high_top) is out of stock at
  DigiKey** with a 33-week standard lead time. It is a real, catalogued
  part (not fabricated), but this is a sourcing risk worth flagging to
  whoever owns procurement — not something this task's scope (fixing the
  fabricated-MPN gate finding) resolves.
- **Mouser was not successfully queried this session** as a second
  distributor source for any of the three replacement parts —
  every Mouser fetch (`mouser.com/c/?q=...`) timed out at 60 s, tried
  multiple times across all three candidates. All verification in this
  document rests on DigiKey alone. Recorded as an attempted-but-unreachable
  source, not treated as corroborating or contradicting evidence.
- **TPS3700 `VIT_A` 387–400 mV range** used for the rail-monitor threshold
  arithmetic is carried over from the project's existing UVL-02 citation
  (itself sourced from TI datasheet SBVS187G per
  `docs/hardware/UVL02_DESIGN.md`) rather than independently re-fetched by
  this task.
- **Board-ambient ΔT (45–60°C) assumption** for the tempco budget is
  inherited from `docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`'s
  own inference from analogous board-zone figures elsewhere in this repo —
  not a direct measurement for this specific board region.
- **The 5.9 kΩ/8.25 mV open-boundary margin (Defect 2)** is the tightest
  margin found anywhere in this circuit and was checked only against the
  modelled corners in `rtd_safety.py` (VBIAS range, RREF tolerance, divider
  tolerance + tempco, TLV3201 offset spec). It has not been bench-measured;
  per `docs/hardware/RTD_SAFETY_DUAL_PATH.md`, no bench measurement exists
  for this comparator circuit at all yet (`CALIBRATED: false` throughout).
- (Resolved, not left open) `RTDSensing`'s inline comment citing "~2.82 V
  nominal UV threshold" was updated to ~2.84 V in the same edit, since it
  directly describes `r_avdd_top` and sits inside the RTD region this task
  was scoped to.
