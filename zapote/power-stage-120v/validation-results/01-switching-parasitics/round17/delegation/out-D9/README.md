# D9 — review of the D4 follow-up work

**Grid v2's published counts are supported, and the ZVS fix works; result reuse and matrix identity remain incomplete, while the bulk-mode and margin work still need controlled validation before supporting hardware acceptance.**

Reviewed `f5a1c8083` inclusive through frozen head
`1f09223516cc37d00f73b5e5e6d33a0197d7a30d`. Review date: 2026-10-02.
Reviewer: OpenAI GPT-6 Astra / Codex. This report changes no original source,
board, simulation, or licensed model. It does not claim that any committed
simulation used stale data. Findings below distinguish demonstrated software
failure modes from unverified physical/model concerns.

## Replay and evidence

From the repository root, with Python, NumPy and meshio available:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/miniforge3/bin/python \
  zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D9/reproduce.py \
  > /tmp/round17-d9-evidence.json
```

[reproduce.py](reproduce.py) calls the reviewed grid, campaign, matrix readers,
extraction CLI, margin CLI, deck generator and pair comparator. It stubs expensive
solver calls in cache tests and constructs temporary fixtures under this folder.
It does not run FEM or SPICE. [evidence.json](evidence.json) records source hashes,
runtime versions, synthetic counterexamples and arithmetic replay of committed
results. Synthetic values are examples of missing guarantees, not measured board
errors. All source paths below are relative to `round17/` unless stated otherwise;
line numbers refer to the frozen review head.

## Ranked findings

### P1 — Grid reuse still ignores solver options and the common runner

**Demonstrated software gap.** `d2/grid.py:56–62,86–91`, introduced in
`f5a1c8083`; `validation-plan/sim-kit/common/run_ngspice.py:41–49`.

The new identity covers matrix values, the deck, `run_d2.py`, `grid.py` and the
vendor library. It omits the included `common/options.inc`, the common runner
that rewrites the deck and parses output, and the resolved ngspice executable /
version. A tighter tolerance or changed integration options can therefore reuse
old measured peaks and verdicts. An upgraded parser can similarly leave old
classification inputs in place. The criteria constants are in hashed `grid.py`;
those are covered, unlike these transitive inputs.

**Failure scenario/replay:** `grid_checks()` calls the actual `one()`, changes a
fixture options file from `reltol=1e-3` to `1e-6`, then calls it again. The options
hash changes but the identity and returned row do not; the simulator stub is
called only for the first request. This demonstrates the cache omission, not a
numerical difference caused by those particular tolerances.

**Decision/check:** keep each grid run immutable until identity includes all
resolved includes, the common runner, simulator identity and relevant startup
configuration. Add options/runner-change regression cases. The response table's
unqualified "fixed" for cache reuse is premature. No stale row was established
in the committed v2 dataset.

### P1 — Campaign reuse accepts a different requested convergence contract

**Demonstrated software gap.** `scripts/campaign.py:158–172,177–179,209–221`,
`f5a1c8083`.

The manifest hashes selected files but omits `--tol`, `--np`, `--maxit`, the
Elmer installation, and the campaign code containing mesher/solver arguments.
A completed solve is reused solely on its saved `converged` boolean. In a reused
directory, status then reports the newly requested tolerance/rank count even
though the accepted solve was not rerun under them. A partly complete directory
can mix older and newly partitioned solves, failing much later at extraction.

**Failure scenario/replay:** `campaign_checks()` supplies a cached result marked
converged at `1e-8`. It runs the production campaign twice, requesting first
`1e-8`/10 ranks and then `1e-12`/12 ranks with a different Elmer prefix. Both
finish without a solver call, their manifests are equal, and the second status
claims the tighter tolerance while accepting the cached solve. Mesh/gate output
and field checks are controlled stubs here; the manifest, reuse branch and
status code are the actual implementation.

Other unbound dependencies include Gmsh/Shapely/NumPy versions used by the
mesher, Elmer/MPI/Hypre runtime and cached gate implementations
`pec_columns.py`/`port_loops.py`. Changes to those files need not invalidate their
saved gate results. Conversely, margin and air values are encoded in the case
tag: they are not the demonstrated collision.

**Decision/check:** bind each mesh/solve/gate to its resolved arguments, tool and
source identities; compare the saved solve tolerance and residual to the new
request. A missing manifest must not silently adopt existing outputs as fresh
evidence. Use a new campaign directory for a changed solver contract in the
meantime. This is not evidence that the running campaign has mixed inputs.

### P2 — Port metadata checks do not bind the fields to the declared inputs

**Demonstrated missing guarantee.** `scripts/inductance_matrix.py:94–106,115–124,
137–145`, `scripts/extrapolate.py:41–53`, `d2/run_d2.py:36–52`, `f5a1c8083`.

Checking the current SIF's signed K against the current mesher log catches the
original reversed-SIF case. It does not prove those files generated the VTUs and
energy log. Extraction hashes the supplied MSH without reading its geometry;
it compares VTU centroids between runs, not VTU geometry against that MSH.
A copied or stale result folder beside a newly generated SIF can therefore pass.
The downstream readers also accept an entirely unlabeled matrix: absent names
and absent IDs skip both checks. Ascending IDs alone do not identify a leg,
terminal convention, or expected physical-ID set.

**Failure scenario/replay:** `extraction_checks()` uses a valid declared mesh
whose tetrahedron differs from the VTUs. Extraction succeeds and emits that
unrelated mesh hash. Reversing a synthetic port's entire VTU field while retaining
its current SIF and energy again succeeds and reverses the mutual sign.
`matrix_checks()` passes a matrix with no identity metadata through both readers.
These demonstrate incomplete input/result association; no actual board field
corruption was found.

**Decision/check:** capture immutable pre-solve mesh/SIF/tool hashes and output
hashes in a completed-run receipt; verify them before extraction. Verify actual
tet geometry/connectivity, not just approximate centroids. Require explicit
ordered terminal identities downstream, with legacy inputs admitted through an
explicit audited migration path. This remaining association problem is distinct
from the now-working SIF-vs-log comparison.

### P2 — The margin CLI can write an asymmetric matrix as a passing result

**Demonstrated software gap; existing inputs pass.**
`scripts/margin_correct.py:52–62`, `934dba659`.

The script promises a symmetric positive-definite output but tests eigenvalues
of `(L + L.T)/2`, never symmetry of `L` itself. It writes the unsymmetrized matrix.
A malformed target or mismatched upper/lower mutual can therefore pass; later
SPICE conversion uses only the upper triangle and models a different matrix.
The output file is also written before the positivity check, leaving an output
artifact after a failing invocation unless callers check its exit status.

**Replay:** equal diagonal margin inputs and a target with an unmatched upper
mutual yield an accepted matrix with `2 nH` maximum asymmetry and a `19 nH`
minimum eigenvalue of its symmetric part. This is a synthetic fixture. Replaying
the committed inputs produces a symmetric corrected matrix, minimum eigenvalue
`10.1845569008 nH`; no current correction arithmetic error was found.

**Decision/check:** validate finite values, shapes, symmetry and complete
identities before subtraction; validate the rounded output and publish it only
after all checks pass. Preserve source content hashes, not paths alone. Separate
this software defect from the physical transfer assumption discussed below.

### P2 — Pair comparison does not reject unconverged or contradictory evidence

**Demonstrated checker gap, not a failed physical comparison.**
`scripts/pair_check.sh:10,27–46`, `f5a1c8083`.

The script prints the solver return code and continues. Its embedded comparator
extracts `inductance_nH` without checking `converged`, reports differences and
`same_sign`, but applies no acceptance tolerance or failure exit. The final
`echo PAIR_DONE` can leave the shell successful after a failed solve/comparator.
A consumer treating completion or shell success as validation would be misled;
a human inspecting every row can see the reported disagreement.

**Replay:** `pair_checks()` executes the unchanged embedded comparator on a
synthetic unconverged pair energy: it returns normally with inferred mutual
`+1 nH`, matrix mutual `−1 nH`, and `same_sign: false`. No shell solver or delete
command is executed by this fixture.

**Decision/check:** reject failed/unconverged solves, bind pair and single-port
results to the same inputs, specify absolute and relative mutual-error tolerances,
and return nonzero on disagreement. Prefer subtraction of independently saved
single-port solver energies for the "energies alone" claim: currently the
subtracted diagonals come from the field matrix. Their existing diagonal-energy
gate provides a useful cross-check, but the pair script does not reverify it.

## Model concerns and discriminating checks

These are **unverified concerns about applicability**, not demonstrations of wrong
current output. The follow-up text already identifies several as open; D9 does
not relabel those acknowledged assumptions as newly discovered defects.

### Bulk slew and the estimate (`d63adce48`, `befcad3f9`)

`d2/bulk_mode.py:85–102` correctly uses `np.gradient(i, t)` with the actual
nonuniform time vector, sums signed represented mutual voltages before taking
the maximum, and converts nH × A/s to volts. `TRMAX=0.2n` is a maximum step,
not proof of derivative convergence. The window includes both outgoing and
incoming switching events. Its maximum over that whole window cannot be read as
a missing voltage specifically during the off-gate failure peak. Very small
adaptive steps or raw-output precision can amplify derivative noise; D9 did not
rerun the raw waveforms or demonstrate such noise in these results.

The committed summaries give bulk peak slews `3.8464–8.9213 A/ns` and estimated
missing EMF `13.9729–48.3187 V` (replayed in `committed`). These support investigating
the omitted bulk mode. They do not establish its actual mutual magnitude, sign,
phase, die VGS change, or failure direction. Applying local-capacitor mutuals to
a different physical loop is a reasonable sensitivity scale, not a bound.
The conditional Cauchy–Schwarz expression is valid only with a compatible whole-
loop inductance; the script explicitly identifies its heuristic LBULK limitation.

**Check:** refine the time step and output precision on decisive cases, locate
peak times relative to gate events, repeat derivatives over short physical
windows, and compare with inductor-voltage/current identities. Report the signed
represented and omitted-mode contributions at the same times. Compare capacitor
ESL variants before interpreting the heuristic bulk branch as a real slew bound.

### Five-port response: useful added mode, incomplete bulk-capacitor model

`closures-legA5.json:13`, `scripts/mesh25d_hybrid.py:65–68`,
`d2/make_deck5.py:14–35`, `d63adce48`.

The added P5 coordinates match actual inner C6 pads 1 and 3 and their
`bus_p → hv_ret` polarity. The deck's `L_P5 bus c6a` orientation is consistent
with the existing local-capacitor port convention. All added K terms are present;
the committed five-port deck exactly equals the generator output. Splitting the
bulk capacitance between C5 and C6 preserves their total nominal capacitance.

However, C6 also has outer pads 2 and 4 at board x=`194.65 mm`; the A5 default
crop ends at x=`184.35 mm`. `bulk_geometry` independently reads the saved board
pad placements, checks the inner closure coordinates, and records that omission.
A single inner-pad injection is an explicit reduced terminal model, not an
extraction of both physical pin pairs' current sharing. This is a model-scope
limitation, not a contradiction between the board and frozen netlist.

C5 remains a heuristic, uncoupled supply path, so a quiet C6 result cannot close
the entire bulk-mode question. C6 also reuses the local capacitors' `LESL` knob:
a correlated ESL sweep cannot establish combinations where local and bulk ESL
move independently. The real parts/models and connection reference planes belong
to D7; no numerical ESL guarantee is asserted here.

The A5 crop differs from A4 as well as adding P5. Comparing their waveforms alone
confounds changed copper domain, added mode, capacitance distribution and ESL.
**Check:** compare variants on a common expanded crop, retain the same circuit
parameters, then isolate P5 couplings and the C5 approximation. Add the outer C6
terminal pair / an explicitly justified terminal reduction, vary sharing, and
sweep bulk ESL independently. Inspect C5 slew/coupling before declaring the
omitted-mode issue closed. No A5 matrix result is committed within this frozen
review scope; ongoing solves and later results were not examined.

### Additive margin transfer (`934dba659`)

The production replay gives the following corrected lin12 matrix in nH:

```text
 26.5944  16.0941   3.5419   5.0829
 16.0941  25.9745   3.2953   5.2918
  3.5419   3.2953  25.9394  -0.2134
  5.0829   5.2918  -0.2134  36.2982
```

This is a calculation from committed coarse-margin and fine-target inputs, not
a fresh solve. The correction is now per entry and explicitly described as an
assumed transfer. It remains conditional on margin differences being insensitive
to both mesh size and closure height. Changing the crop changes return-current
paths and meshing; finite-height closure fields also interact with the crop.
SPD tests passivity and cannot test those interactions.

**Check:** measure the complete m20−m10 difference at another mesh size at fixed
height, and another feasible closure height at fixed mesh size. Compare diagonals
and mutuals using absolute tolerances near zero as well as relative differences.
Propagate plausible residual difference matrices into the switching cases nearest
the criteria. Merely checking another unrelated `(mesh,height)` combination is
weaker than varying each factor separately. No additional transfer test was
executed or claimed by D9. The earlier method-spread wording is now correct;
D4's hidden-extrapolation-term example remains a limitation, not a resolved
accuracy guarantee.

## Grid v2 conclusions checked and found sound

`d2/README.md`, Grid v2 (`642ff3571`), agrees with the committed JSONL, summary
and individual case files:

| Case | 250 ns | 307 ns | 348 ns | 391 ns | 450 ns |
|---|---:|---:|---:|---:|---:|
| S1 | 0/18 | 0/18 | 18/18 | 18/18 | 18/18 |
| S2 | 0/12 | 0/12 | 10/12 | 12/12 | 12/12 |
| S3 | 0/54 | 42/54 | 54/54 | 54/54 | 54/54 |
| S4 | 0/18 | 0/18 | 0/18 | 0/18 | 0/18 |

There are `510` unique cases, `292` task passes, `218` failures and no reported
aborts. Every task failure includes off-gate failure; all `39` VDS failures are
S4. All `18` nominal S1 cases satisfy the saved ZVS criterion. The synthetic
non-ZVS nominal S1 case now fails `task_pass` while passing `stress_pass`.
Changed matrices rerun; missing partner samples receive `unknown`, not a
fabricated rebound diagnosis. Direction selection and nominal-only ZVS enforcement
match the stated task. Numerical criteria remain hashed in the grid source.

The S1 off-gate ranges round to the stated `3.45–4.01 V` at `307 ns` and
`2.03–2.54 V` at `348 ns`. The S2 and S3 failure rows and S4 extrema agree too.
All recorded matrix/deck/grid/run_d2 identities match the frozen sources. The
vendor hash is consistent across rows; D9 did not independently fetch the licensed
library or rerun ngspice, so this is an evidence audit, not independent simulation
qualification.

The statement that dead-time margin lies between the sampled failing and passing
points is a **model bracket**, not a continuous monotonicity proof or a guaranteed
hardware dead time. The README properly calls D1's interval an estimate. D5 must
establish which gate-timing conditions the controller/driver can actually create;
D6 and D7 must address driver remedies, hot-threshold applicability and ESL.
Neither the grid nor this review proves the real board reaches the failing points.

## Signed-pair independence and final decision

The pair-energy identity is mathematically appropriate for a linear common
operator with normalized signed excitations. A separately solved pair offers a
useful check of field cross-products and output processing. It is not independent
of geometry, meshing, port orientation or solver physics shared with the original
solves; consistent errors can survive both. For small mutuals, cancellation of
large diagonal energies also requires an absolute error budget. At the frozen
head the README calls the new signed checks queued; D9 evaluated the checker,
not an uncommitted or later pair-solve result.

The follow-up work improves the evidence: v2 arithmetic, nominal ZVS handling,
labels, signed-SIF checks, five-port deck generation and per-entry correction
were verified. It does not yet justify hardware acceptance. Close the demonstrated
reuse/identity/checker gaps and perform the controlled bulk and margin checks;
retain D5–D8's separate timing, model and bench qualifications.

[validation.txt](validation.txt) records the publishing gates. No Rust/workspace,
firmware, native-extension, FEM or ngspice build/run was needed for this review.
