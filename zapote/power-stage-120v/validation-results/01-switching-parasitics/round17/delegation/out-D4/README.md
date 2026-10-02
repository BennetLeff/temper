# D4 — adversarial review of round 17

**Round 17 is useful provisional evidence, but its present grid cannot certify the switching criteria: result reuse and ZVS verdict handling are defective, and the FEM-to-circuit reduction and extrapolation retain unquantified model errors.**

Reviewed source: `67aec36f8c876a7026c07ce3752105ab34d3ce46`.
Reviewer: OpenAI GPT-6 Astra, Codex. Review date: 2026-10-01.
This is a review of software and model assumptions, not a board redesign or
physical qualification. Board/part identities are inherited inputs, not changed
artifacts. No FEM, ngspice, Rust, workspace, or extension build was run. No
licensed model was downloaded because no SPICE run was needed. No contradiction
between a board, frozen netlist and datasheet was established; the findings below
concern the numerical workflow and its model claims.

## Method and reproduction

Read both closure files, the round-17 and D2 READMEs, package-inductance note,
D1-FEM amendments, mesher, campaign, matrix extraction, extrapolation, deck,
runner and grid. Executed the original Python functions with controlled fixtures
and ran the original matrix-extraction CLI against synthetic VTUs. Checked the
existing matrices and their conversion to SPICE parameters.

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/miniforge3/bin/python \
  zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D4/reproduce.py \
  > /tmp/round17-d4-evidence.json
```

A Python environment with NumPy and meshio can replace that interpreter. The
script creates and removes its temporary fixtures inside this output folder and
prints JSON. It does not run the simulator or change reviewed source files.
[reproduce.py](reproduce.py) and [evidence.json](evidence.json) are the committed
checks and output. Evidence records interpreter/library versions, reviewed
revision and source hashes. Every numerical example below is either calculated
there or explicitly identified as an existing source requirement. Synthetic
counterexamples demonstrate missing guarantees; they do not estimate the error
on this board.

All source locations below are relative to `round17/` unless prefixed with
`validation-plan/`; line numbers refer to the reviewed revision.

## Findings, ranked by severity

### P1 — Reusing a grid output directory can attribute old simulations to a new matrix

**Location:** `d2/grid.py:62–65, 121–124`; related FEM resume assumption at
`scripts/campaign.py:164–169, 193–195`.

`one()` returns a case file solely because its filename exists. The filename
contains operating corners but no matrix, deck, model, simulator, or criteria
identity. Meanwhile `main()` overwrites `matrix_used.txt` before dispatch. A
caller rerunning a grid in the same directory with the extrapolated or corrected
matrix can receive the old results beside a new matrix label. Changes to the
classification code also leave cached verdicts untouched. The campaign similarly
reuses meshes and converged solves by names that do not bind source hashes.

**Reproduction:** `grid_checks()` calls the actual `one()` twice for the same
case and directory, first with an identity matrix and then with its diagonal
multiplied by 100. The second call returns the first row without invoking the
stub simulator. The stub replaces only the expensive simulation; cache lookup,
classification and persistence are production code. `different_matrix_cache_hit`
is true in the evidence. This is a demonstrated failure mode, not an allegation
that the currently committed grids reused a directory incorrectly.

**Decision/check:** use a new output directory per immutable input set until
cache identity includes the matrix, deck/model and classification versions.
Validate saved input identity before reuse and retain per-case provenance.
For the FEM campaign, fresh campaign directories after geometry changes remain
necessary; no existing campaign was inspected or disturbed by this review.

### P1 — A failed nominal ZVS criterion can still contribute to the overall pass count

**Location:** `d2/grid.py:87–88, 101–107`;
`validation-plan/01-switching-parasitics.md:193`.

The plan requires ZVS for S1 at nominal dead time. The grid computes `zvs` and
reports a separate nominal-S1 yes/no tally, but `row['pass']` only combines
abort, VDS, off-gate and transient-gate checks. Its pass/fail counts therefore
mean stress-only acceptance, despite the module's claim that it judges the task
criteria. The separate ZVS tally is useful and makes this visible to a careful
reader; it does not make an overall pass satisfy the plan.

**Reproduction:** the production classifier accepts a synthetic S1, 170 V,
348 ns row with incoming VDS 100 V, VDS peaks 200 V, off-gate peak 2 V and maximum
absolute gate voltage 15 V. It produces `zvs: false` and `pass: true`.
These are fixture values, not an observed switching case. Evidence key:
`grid.synthetic_non_zvs_row`.

**Decision/check:** require nominal-S1 ZVS in the overall acceptance result, or
name the existing result stress-only and expose a separate complete task
verdict. There is no demonstrated change to the already reported passing
nominal-S1 cases; the bug affects a future failing case or missing ZVS measure.

### P1 — The four-port matrix does not establish equivalence for the additional bulk and load current modes

**Location:** `d2/leg_matrix.cir:6–17, 39–63, 67–84`;
`closures-legA.json:2–12`; `d2/run_d2.py:57–69`.

For the closed extracted network, a coupled loop-inductance matrix can represent
shared source copper without a separately named LCS. That does **not** justify
moving all board power inductance to the local-capacitor branches after adding
independent connections. The FEM's power excitations are at C38/C39. The deck
also supplies the switch node from a bulk path and an imposed load connection,
but has no FEM port for either physical attachment. Every FEM-derived power
inductor is in a local capacitor branch; the switch power path itself has none.

**Concrete failure scenario:** incremental bulk current changes through a
physical shared source segment while the local-capacitor currents remain
stationary. The real source voltage includes `Lshared * di_bulk/dt`; the mapped
model's FEM board contribution to the gate loop is then zero because both
capacitor-current derivatives are zero. The analytic fixture uses a passive
5 nH shared segment and a 2 A/ns slew: 10 V versus zero. Those are synthetic
values. Existing FEM mutuals can correctly reproduce the capacitor-fed modes
and still say nothing about this omitted mode.

This does not prove the actual D2 waveform has a large missing contribution:
the bulk inductance can make its current slew small over a switching edge, and
the prescribed load can be effectively constant there. It establishes an
unverified approximation. The near-zero-board-L wiring check necessarily
removes the coupling under review and cannot establish inductive equivalence.

**Decision/check:** derive the branch-to-loop current transformation including
bulk, switch/load attachment and snubber terminals; show that omitted current
slews and their transfer terms are negligible over every relevant event, or
extract the missing port modes. Retain physical source-reference nodes in that
check. Do not add the old heuristic LCS on top of FEM mutuals: that would count
the shared path twice for modes already represented. Do not use a small `k`
alone to exclude common-source effects: `M`, current slew and cancellation
between field contributions determine the induced voltage.

### P2 — The zero-height result is a reference-geometry extrapolation, not removal of every closure conductor

**Location:** `scripts/mesh25d_hybrid.py:67, 368–395`;
`closures-legA.json:6–12`; `scripts/extrapolate.py:41–59`;
`PACKAGE-INDUCTANCE.md:3–6`; `validation-plan/D1-FEM.md:74–82`.

Changing bridge height to `2h` removes the earlier fixed-height offset, but the
bars keep finite lateral length and thickness. A flat connection still carries
current, field energy and mutual coupling; zero height does not mean zero
inductance. Moreover, the current mesher refuses `h <= 0.35 mm`, and the planar
GS bars cross the drain positions. The intended insulating separation cannot
be preserved by literally flattening this fixed-thickness geometry. Thus the
computed intercept is a continuation from separated arches, not a meshed,
verified physical board-only circuit at zero height.

**Reproduction:** `geometry_checks()` reads the actual closure coordinates.
Q2's GS span contains its drain x-coordinate, and so does Q3's. The script
records the spans and the exclusive mesher height limit derived from its
constants. No mesh was generated.

**Package implication:** adding vendor lead terms is appropriate only with an
explicit reference-plane convention. The intercept retains a reference path
across the component pads; adding absolute package inductance without matching
that path can overcount its reference contribution, while omitted package-to-
board mutuals can alter either sign of the error. This review does not assign
a numerical correction or claim that all lead inductance is duplicated. The
deck's decision not to add a second copy of lead inductance already inside the
vendor model remains correct.

**Decision/check:** define the limiting insulated reference paths and terminal
planes, qualify the same extraction/insertion procedure on a simple known
component connection, and compare a feasible lower-height or alternate-closure
family. Treat the intercept as an estimate until that convention is validated.

### P2 — Agreement of extrapolants and an additive crop correction do not bound the missing terms

**Location:** `scripts/extrapolate.py:44–59, 110–122`;
`validation-plan/D1-FEM.md:77–93`.

With only the committed first two heights, the code emits identical low/high
values because there is one estimate. With three heights, an unobserved
higher-order term can make every estimate agree and still move the intercept.
SPD constrains passivity, not accuracy. The report's spread is a method
comparison, not an uncertainty bound; the current two-height width of zero
must not be read as zero error.

**Reproduction:** use the SPD scalar matrix family
`L(h) = [30 + 2h + (h−1)(h−2)(h−3)] I` in nH with h in mm. The actual
extrapolator returns 30 nH and effectively zero spread from the supplied
heights; its true zero-height value is 24 nH. `extrapolation_checks()` also
confirms the existing two-height files produce zero range width.

The proposed crop correction is
`Lfine(h=0,M=10) + Lcoarse(h=1,M=20) − Lcoarse(h=1,M=10)`.
It assumes the crop effect transfers across both mesh size and arch height.
A P1 margin sweep at one mesh/height does not test these interactions or the
other matrix entries. The script's smooth positive scalar counterexample
`L(e,M,h)=30+2h+e+(M−10)(−0.5+0.2e+0.1h)` gives a coarse h1 correction of
−2 nH but a fine h0 correction of −4.3 nH. The resulting 2.3 nH error is
synthetic, not a board estimate. Adding a matrix difference also need not
preserve SPD; check the final corrected matrix itself.

**Decision/check:** report the method spread separately from unbounded model
error. Test crop differences at another affordable mesh and height, including
gate diagonals and all mutuals, before transferring the correction. A finer
large-margin solve is not the only test: paired coarser levels can expose the
interaction. A near-zero mutual needs an absolute tolerance as well as a
relative one. No crop correction was implemented or executed in this review.

### P2 — Energy and within-tet gates cannot detect an incorrect port orientation or run identity

**Location:** `scripts/inductance_matrix.py:60–66, 74–99, 103–107`;
`scripts/campaign.py:189–211`; `scripts/extrapolate.py:34–37`;
`d2/run_d2.py:36–48`.

The reciprocity expression is correct for fields from the same linear system,
with the intended normalized excitations. Both gates are invariant when an
entire port field changes sign. Reversing a field together with its declared
port orientation is legitimate coordinate freedom; the failure here is a
reversal that leaves the declared closure a/b convention unchanged. A stale/reversed `--k`, swapped run identity,
or coordinate-axis mismatch in one run can therefore change off-diagonal signs
while preserving every diagonal and the within-tet spread. Symmetrizing the
upper triangle is not an independent reciprocity check.

**Reproduction:** `reciprocity_checks()` invokes the production matrix CLI on
constant-per-tet synthetic fields with matching energy files. Reversing one
port field reverses its mutual while both CLI invocations succeed. The mesh
argument is deliberately nonexistent and is still accepted: it is not checked
or hashed. The output prints only user-supplied port labels. Downstream readers
also discard these labels and assume ordering. This demonstrates missing
identity checks, not a sign error in the existing board matrix.

**Decision/check:** bind runs to mesh/partition hashes, signed port directions,
source amplitudes and solver inputs before composing the matrix; validate port
order in downstream readers. Independently check a power-to-gate and gate-to-
gate pair energy with signed combined excitation. The existing M12 pair check
is useful evidence for that pair, not a qualification of every port identity.

### P2 — Off-gate cause classification is a timing observation, not a causal diagnosis

**Location:** `d2/grid.py:82–85`; `d2/leg_matrix.cir:95–109`.

A failed peak with missing `vgs_*_at_partner` is labeled rebound because
`None or 0` becomes zero. A gate that is already elevated at the partner
command can also be experiencing a prior rebound; conversely, above the
acceptance threshold at that command is not proof of channel overlap when
the incoming transistor later reaches conduction. These measures help locate
the violation but do not isolate its mechanism.

**Reproduction:** `grid_checks()` supplies a valid off-gate peak of 4 V and
omits the partner-command sample. The actual classifier returns `rebound`.
No waveform exists in this fixture, so that diagnosis cannot be supported.

**Decision/check:** represent missing timing evidence as unknown; describe
existing labels as above-threshold-at-command versus later peak. To establish
shoot-through or a recovery/Miller cause, inspect both channel currents and
gates, the incoming device's actual turn-on time and the peak's time. Short
dead time may be the correct diagnosis for a particular waveform; the single
sample does not prove it.

## What was checked and found sound

- **Current directions and all K signs:** the mesher drives each sheet from
  closure `a` toward `b`, including the coordinate-system y inversion
  (`mesh25d_hybrid.py:391`). For P1/P2, the deck's positive capacitor-branch
  current goes from bus toward return. For P3/P4, positive sheet current runs
  from driver output toward driver source; the external return goes from the
  FET gate toward the driver. Thus the gate inductors' first nodes at the FET
  gates correctly represent positive gate-discharge current. The four loop
  currents are consistent; reversing only the gate inductors would be wrong.
- **Conversion algebra:** `run_d2.matrix_params()` reproduces the original
  provisional matrix from diagonal L and K to about `1.2e-8 nH` maximum error.
  K12, K13, K14, K23 and K24 are positive; K34 is negative. The reconstructed
  matrix is SPD; its smallest eigenvalue is about `10.3566 nH`. All values and
  complete K coefficients are in `extrapolation_and_mapping` in the evidence.
  No numerical sign error was found in the conversion.
- **Common-source physics within the extracted modes:** a loop Gram matrix
  includes overlap of the power and gate magnetic fields, including shared
  source copper. A separate board LCS is not required merely because the
  netlist lacks that name. The driver return closure points are U1.14/sw_a
  and U1.9/leg_ret (`closures-legA.json:4–5`). The deck references high and low
  drivers to their external source nodes (`leg_matrix.cir:67–76`). The
  limitation is the additional current modes and collapsed physical terminal
  locations described above, not an automatically missing shared-source term.
- **Reciprocity mathematics:** for the same real, linear, uniform-permeability
  magnetostatic operator, the field cross-energy expression is the appropriate
  bilinear form. Its diagonal equals twice stored energy at unit current.
  The constant-per-tet and independent energy checks address field averaging;
  the nonuniform fixture and board pair comparison documented in the original
  README are materially stronger than a uniform-field fixture alone. Those
  historical FEM results were read, not independently rerun here.
- **Extrapolation arithmetic:** the linear and quadratic intercept formulas
  are implemented correctly. Using `2h` fixes the specifically identified
  residual elevation of the prior `h+1` convention. The SPD gate is a useful
  necessary passivity check, even though it cannot bound approximation error.
- **Grid stress checks:** direction selects the proper off and incoming
  devices; missing stress measurements fail their relevant check; aborted
  runs cannot become overall passes. The distinct fault VDS threshold is
  implemented. The generated case count is 306, reproduced by the original
  `cases()` function. These checks do not resolve the ZVS and cause-label
  findings above.

## Limits and acceptance decision

No claim is made that the existing S4 peaks are real hardware failures, or that
fixing the model will remove them. This review supplies no fresh device-model,
package or driver qualification; those belong to D1–D3 and physical checks.
Raw board VTUs, signed pair reruns, a finer large-crop result and new waveforms
were not generated. The provisional matrix is internally passive and its
SPICE parameter conversion is consistent, but the board-only interpretation,
full-circuit equivalence and uncertainty budget remain open. Resolve the
reproducible software verdict/provenance defects and qualify those model
assumptions before using the grid's aggregate pass count as task acceptance.

Publishing checks: [validation.txt](validation.txt) records a passing import-boundary
gate and report-only derived-artifact check. The private environment contains only
import-check tooling; no repository build was needed. Firmware tests were not
run because this review changes no firmware or production implementation.
