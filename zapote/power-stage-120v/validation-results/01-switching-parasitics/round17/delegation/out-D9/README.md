**D-9: the committed grid-v2 conclusions reproduce, but result reuse, port/mesh identity, override classification and pair-check acceptance still have demonstrated holes; keep the switching answer provisional.**

Reviewed `f5a1c8083^..f9b13b483d6d4ed52439d4da419c7670bab6966c`, including the first D-4 fix commit itself. Reviewer: OpenAI GPT-6 Astra / Codex, 2026-10-02. No existing simulation verdict is shown wrong by this review. The findings concern reproducible failure modes in the follow-up tooling; they are not measurements of board error. No contradiction among the board, frozen netlist and a datasheet was established.

## Method and rerun

Read the delegation ground rules and D-9 brief, task STATUS/FINDINGS, D-4 report, the scoped follow-up source and committed results. Checked production functions with controlled fixtures, invoked the actual matrix and correction CLIs, and recomputed grid summaries and case-matched differences from committed rows. The campaign reproduction stubs expensive commands; its manifest, resume logic and status writes are original. Pair reproduction executes the comparison code extracted verbatim from the shell script. No FEM, ngspice, Rust or native-bridge build was run; no vendor library was fetched or copied.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/bennet/miniforge3/bin/python \
  zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D9/reproduce.py \
  > /tmp/round17-d9-evidence.json
```

Use Python with NumPy and meshio; versions, source hashes and results are in [evidence.json](evidence.json). [reproduce.py](reproduce.py) writes and removes its fixtures only inside `out-D9`. Source locations below are relative to `round17/` at the reviewed revision. This was one review writer, not an independent multi-reviewer or cross-model pass. The code-review and Python skills informed the checks; the delegation's output and solo-writer constraints take precedence over their general workflows.

## Ranked findings

No P1 finding is established against the committed decision cases. P2 findings below need fixes before relying on automatic reuse or general input acceptance. Each is demonstrated; incidence in existing campaigns is not established.

### P2 — Grid identity omits runtime inputs that alter the simulation

**Location:** `d2/grid.py:63–68, 94–98`; `validation-plan/sim-kit/common/run_ngspice.py:43–60`.

The identity hashes the top-level deck, matrix, vendor library, grid and `run_d2.py`. It does not hash the included `common/options.inc`, the actual `common/run_ngspice.py` implementation, or identify the executable/version/configuration selected as `ngspice` on PATH. A numerical-options edit or runner update followed by a resume returns the old row, because those changes do not enter the compared dictionary. `grid_checks()` records the production identity's file reads and proves both source dependencies are absent. The runner reads the options at simulation time, so this is a real missing dependency, not an unused file. Existing criteria constants are inside the hashed grid source and therefore **are** covered.

**Decision/check:** recursively bind deck includes, the runner implementation and simulator build/runtime settings, or use fresh output directories on any such change. Add a regression that changes only options or runner bytes and requires a rerun. Current committed grid-v2 rows are not proved stale; their counters reproduce.

### P2 — Campaign resume can relabel a loose solve as meeting a tighter tolerance

**Location:** `scripts/campaign.py:158–170, 202–211`.

The manifest binds source files and board export but omits `--tol`, solver installation, rank count, dependency versions and the campaign's own command-generation code. Existing `.out` is reused on its saved `converged` boolean. In `campaign_checks()`, a synthetic saved result with residual `1e-5` is first resumed at requested tolerance `1e-4`, then at `1e-8` with a different solver path. Both runs bypass the solver, and the latter status advertises the new tolerance while listing the old result as converged. Old pre-manifest directories are also accepted by writing a new manifest without establishing which inputs made their existing outputs.

**Decision/check:** bind full effective solver/mesher configuration and tool identity per run; compare saved residual and solver receipt with the requested contract. Reject or explicitly migrate directories without provenance. Re-run mesh gates after their implementations change: `pec_columns.py` and `port_loops.py` are also outside the manifest, while gate files are reused. This reproduction establishes the resume bug, not that the real remote campaign used a different tolerance.

### P2 — The accepted `--set` interface can select the wrong gate and skip nominal ZVS

**Location:** `d2/grid.py:100–117, 127–129, 172–174`.

Overrides are applied to SPICE parameters after the operating tuple, but labels, off-device selection, ZVS threshold and the nominal-ZVS requirement still use that original tuple. The reproduction passes a tuple labelled DIR=0, DT=450 ns with overrides `DIR=1, DT=348n`. The actual simulated parameters select the high-side off gate and nominal timing; the returned row tests the low-side gate and skips required nominal ZVS. Synthetic measurements with low-side off-gate 2 V, high-side off-gate 4 V and incoming VDS 100 V produce `task_pass: true, zvs: false`. These values are fixture inputs, not board simulations.

**Decision/check:** reject overrides of scenario keys (`DIR`, `DT`, `VBUS`, `IL`, `LESL`) or derive all labels and acceptance logic from the merged effective parameters. The committed bulk A/B/C runs override coupling coefficients, not these scenario keys; this defect does not invalidate their results.

### P2 — Port metadata is checked locally but not bound through the whole transformation

**Location:** `scripts/inductance_matrix.py:94–116, 148–151`; `scripts/extrapolate.py:40–47`; `d2/run_d2.py:42–49`; `scripts/margin_correct.py:44–54`.

Two demonstrated gaps remain:

- The extractor now checks SIF port ID and signed excitation against the supplied mesher log, and compares VTU tetrahedra across runs. It never establishes that those VTUs came from the supplied mesh. `extraction_checks()` supplies an existing file containing `not a mesh at all`, a matching synthetic log/SIF, and valid constant-field VTUs with matching energies. The real CLI exits successfully and publishes that unrelated file's SHA as `mesh_sha256`. A copied stale log/SIF/VTU set beside a new mesh is the practical version of this counterexample.
- The downstream readers check names/order, not signed orientation. `matrix_checks()` gives a consistent coordinate reversal of P3: both its signed metadata and matrix row/column are reversed, preserving SPD. Both readers accept it without remapping to the fixed deck convention. M13 changes from `+3.747410` to `−3.747410 nH`. The correction reader likewise compares names only. The historical coarse files contain only physical IDs, so newly added names cannot retroactively supply their orientation provenance.

**Decision/check:** bind generated partition/VTU output to the input mesh and SIF at solve time, then verify those receipts during composition. Carry canonical terminal a/b identities and orientation through extrapolation/correction, requiring an explicit sign transformation if a basis changes. Existing board port directions agree with the deck; no reversal in current results was found.

### P2 — Pair checks report agreement without requiring a successful converged solve

**Location:** `scripts/pair_check.sh:11, 29–45`; `results/pair-check-h1-e1p0.txt`.

The shell prints the solver return code then continues. The comparison reads `inductance_nH` alone, ignoring `converged`, residual, exit status and solve/input identity; it also has no discrepancy failure threshold. `pair_checks()` executes the exact comparison block on a failed, explicitly nonconverged synthetic result with diagonal terms 30/20 nH and pair energy-equivalent inductance 58 nH. It emits `M_energy_nH: 4`, `same_sign: true`, and zero difference. Thus the success-shaped comparison is not itself evidence that the pair solve passed the numerical gate.

The committed comparisons are algebraically consistent: M13 differs by about `1.2e-5 nH`, M34 by `4e-6 nH`, with the expected signs. Their committed short records lack convergence and input receipts, so this review cannot independently verify those prerequisites. This is missing evidence, not evidence that those historical solves failed.

**Decision/check:** fail closed on solver failure/nonconvergence, verify mesh and signed excitation identities against the single-port reference, and retain raw result/receipt hashes. Apply an absolute mutual-error tolerance as well as relative error; normalizing only to the much larger total pair inductance can conceal an incorrect near-zero mutual. Pair energy is independent of the B-field integration implementation, but shares the mesh, physics and source convention; it does not independently validate those assumptions.

### P2 — Crop correction accepts a nonsymmetric matrix as positive definite

**Location:** `scripts/margin_correct.py:55–65`.

The script computes eigenvalues of `(out + out.T)/2` but never checks `out == out.T`. It then writes the unmodified matrix. `matrix_checks()` passes a synthetic matrix with 30 nH diagonal, `L12=8 nH` and `L21=0`; the CLI succeeds and advertises minimum eigenvalue 26 nH. `matrix_params()` later uses only the upper triangle, silently turning it into a different symmetric network.

**Decision/check:** validate dimensions, finite entries and symmetry before the eigenvalue test and publish output only after all gates pass. Add negative cases for asymmetry and indefinite matrices. The committed correction matrices are symmetric; this is a general acceptance hole, not a measured current-grid error.

### P3 — Narrow the claim that all existing loops moved less than 0.1 percent

**Location:** `d2/README.md`, “Bulk current mode”, sentence “the four existing loops moved < 0.1 %.”

The four diagonal self-inductances meet that statement, changing by approximately 0.012–0.035%. Across the existing matrix entries, M34 changes by 0.813%, or only `−0.002407 nH`. `audit_results()` computes these numbers from the committed four- and five-port matrices.

**Decision/check:** say “the four self-inductances moved < 0.1%” and report the small absolute mutual change if discussing the full matrix. This wording issue has no demonstrated switching-verdict consequence.

## What was checked and found sound

- **Original D-4 grid fixes:** an actual nominal S1 non-ZVS fixture now fails the task verdict; a matrix change triggers another simulation; identical inputs reuse the row. Missing partner-command information remains `unknown` in the reviewed code. The new labels describe timing rather than claim a diagnosed mechanism; remaining old causal comments should not be treated as evidence of shoot-through.
- **Grid v2 arithmetic:** all 510 committed rows reproduce the saved summary exactly: 292 task passes, 218 failures, no aborted cases, and nominal S1 ZVS in all 18 cases. The per-scenario/dead-time table reproduces. Every task failure includes the off-gate failure, with 39 VDS failures, all S4. This is an audit of stored measurements, not fresh ngspice validation.
- **Controlled comparisons:** committed case matching confirms no crop-correction verdict flips over 240 common cases, no curved-extrapolation flips over 32, and one bulk A-to-C flip over 32. The B-to-C comparison isolates C6 coupling on the same five-port topology, whereas A-to-B includes the bulk split and topology change. Complete peak deltas and counts are in `actual_results.case_comparisons` in the evidence.
- **Five-port wiring and generation:** `make_deck5.build()` matches the committed deck byte-for-byte. P5 is at C6.1 bus_p toward C6.3 hv_ret; its deck inductor has bus as its first node, consistent with the capacitor-loop orientation. The A5 crop reaches both closure endpoints. The saved matrix is symmetric and SPD (minimum eigenvalue about 11.6663 nH). The existing gate inductor orientations are correct; reversing them would introduce a bug.
- **Physical scope of the bulk test:** adding C6 is an appropriate test of that missing current mode. It does not extract C5, whose heuristic branch still lacks gate mutuals; the ideal source also imposes the load-current behavior. Shared `LESL` makes C6 inherit the local-cap ESL assumption despite being a different part. Neither C5 omission nor ESL reuse has a measured error bound here. Treat “closes” as closing the tested C6 sensitivity question at this basis, not establishing full physical equivalence. A decision within the reported C6-induced shift still needs the stronger model.
- **Slew calculation:** `np.gradient(i, t)` uses the actual nonuniform timestamps, not a blind fixed-step difference. The configured maximum timestep is 0.2 ns, and the window includes both switching commands plus the stated tail. Peak differentiation can nevertheless amplify raw-file quantization and depends on timestep and window. There are no committed bulk raw waveforms to independently recompute the derivatives; repeat with a refined maximum step, report waveform precision, peak time and integral/window sensitivity. The estimated induced EMF is a loop forcing voltage, not a predicted gate voltage, so comparing its amplitude directly with a filtered off-gate peak is not like-for-like. Its assumption and conditional Cauchy–Schwarz statement are explicit, and the direct A/B/C test supersedes it. No numerical derivative-error magnitude is claimed.
- **Margin/extrapolation transfer:** the additive formula is implemented as stated and explicitly marks transfer as assumed. A crop-by-height or crop-by-mesh interaction changes the correction; SPD cannot exclude it. A second matched crop pair at another affordable height/mesh, comparing every entry with both absolute and relative tolerances, is the decisive test. Curved extrapolation already moves results consistently toward higher off-gate peaks in the saved comparison; an absence of verdict flips is not an error bound. These are acknowledged open model limits, not newly discovered defects.

## Limits and owner decisions

Retain the committed simulation conclusions as provisional model evidence. Assign tooling ownership to the P2 fixes before future resumed or generalized campaigns; no board redesign follows from these counterexamples. Preserve or regenerate successful pair-solve receipts before calling their convergence independently audited. The owner must decide whether C5, bulk ESL and correction-transfer uncertainty matter for the eventual decision margins after D-5/D-6/D-7; this review cannot close them.

No historical FEM solves or new transient waveforms were generated. The vendor model's device physics, hot-junction criterion, timing chain and bench qualification belong to the other briefs. No files outside `out-D9` are intentionally changed. Publishing checks are recorded in [validation.txt](validation.txt) and [regen-check.txt](regen-check.txt); report-only regeneration respects the explicit prohibition on editing other artifacts.
