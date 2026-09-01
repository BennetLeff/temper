<!-- provenance: commit=d4510f23ec67ec762ecb3505ef03b65ea7722942 dirty=true -->

# Should `power_pcb_dataset/corpus/temper/temper.kicad_pcb` be regenerated from the real board? (2026-08-11)

## Verdict, first

**MIXED — and for the one consumer the owner's premise was about, the
answer is NO, do not regenerate.** `power_pcb_dataset/corpus/temper/temper.kicad_pcb`
(33 components, 100x150mm, frozen since 2026-07-11 `454f71d9`) has two
classes of consumer:

- **Parse/DRC-only consumers** (metamorphic oracles, round-trip integrity,
  DSN differential export) are generic across board size and would work
  identically on a regenerated fixture. Reading B ("independent fast test
  case") vs A ("stale snapshot") is moot for these — they don't care.
- **CP-SAT-solving consumers** (`test_golden_board_drc_regression`,
  `test_golden_board_routing_drc_regression`, and the
  `build_full_board_corpus()` evidence harness) are reading **B**, and
  swapping them to the real board is actively harmful: **measured
  directly, today**, CP-SAT solves the 33-component fixture `optimal` in
  3.5s and returns `unknown` (never completes) on the real 169-component
  board after ~20s of its 30s budget. Regenerating would not fix these
  tests — it would silently convert them from "runs a real regression
  check" to "always `pytest.skip`s", which is worse than the status quo,
  not better.

**The owner's stated goal — catch PCL config drift against the real board
— cannot be achieved by regenerating this fixture alone**, for a second,
independent reason found by a parallel investigation today
(`docs/evidence/2026-08-11-pcl-config-intent.md`): the PCL config's zone
geometry is itself stale in a way that a mechanical resize would launder a
possible safety defect (HV bus capacitors physically inside geometry
labelled `MCU_ZONE`) into a passing check — fixing it needs owner/EE
sign-off, not a fixture swap, and is explicitly out of scope here (tied to
the in-flight sealed-compartment/PD2 work).

**What actually landed**: naming fixed everywhere the fixture was called
"the real board" (task item 4), a divergence gate that encodes the A-vs-B
decision as data instead of prose (task item 5), and the manifest now
explicitly declares this fixture's role so no future reader has to
re-derive it from scratch the way this doc, and the two documents it
builds on, had to.

## 1. Every consumer, enumerated

| Consumer | Operation | Risk | Classification |
|---|---|---|---|
| `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression` | **Solves** CP-SAT placement, 30s timeout, then writes+DRCs | HIGH — measured infeasible at real scale (§2) | B |
| `...::test_golden_board_routing_drc_regression` | **Solves** CP-SAT + routes | HIGH (same solve) — currently `pytest.skip`'d for an unrelated KNOWN GAP regardless | B |
| `...::test_golden_board_rotation_drop_mutant_fails_oracle` | Parses only (uses first 5 zero-angle components) | none | B-compatible, no change needed |
| `docs/evidence/scripts/2026-08-07-cpsat-equivalence-harness.py::build_full_board_corpus()` | **Solves** CP-SAT with the real PCL config, 30s timeout | HIGH (same solve) — research/evidence harness, not CI-gating | B, was mislabeled "the real golden-board corpus" — fixed this PR |
| `packages/temper-placer/tests/test_metamorphic_oracles.py` (T1-T4) | Parses only — idempotency, bounds, non-overlap, ref uniqueness | none — invariants are size-agnostic | B-compatible, no change needed |
| `packages/temper-placer/tests/test_round_trip_integrity.py` | Parses, writes, re-parses — netlist preservation | none — generic across the 4-board parametrization | B-compatible, no change needed |
| `packages/temper-placer/tests/router_v6/_quality_metrics_cases.py` (`CORPUS_BOARDS["temper"]`) → `test_quality_metrics_oracle_pin.py` | Parses only, compares against **exact pinned metrics** (`n_components=33, n_vias=0, n_traces=0, lint_total=0, ...`) | none (no solve) but **regeneration would move every pinned number** | B — these are exact-value pins tuned to this fixture's specific unrouted geometry; regenerating invalidates all of them |
| `packages/temper-placer/tests/io/test_dsn_rust_differential.py::test_corpus_boards_export_bit_identically` | Parses, differential Rust-vs-Python DSN export, bit-identical | none — generic across the 5-board corpus glob | B-compatible, no change needed |
| `test_golden_board_drc_regression`'s siblings, `test_production_board_drc_regression` / `test_production_board_routing_drc_regression` | DRC-only / route-only on **`pcb/temper.kicad_pcb` directly** (already the real board) | n/a — not a corpus-fixture consumer | Already correct; explicitly documented in their own docstring as NOT running CP-SAT ("infeasible at 168 components / 30s timeout") |
| `.github/workflows/placer-regression.yml` (`power_pcb_dataset/corpus/manifest.yaml`'s `epochs`/`seed` fields) | N/A today | none | The JAX/benders_loop backend that consumed `epochs` was retired 2026-07-27; the per-board matrix was collapsed the same day (see the workflow's own comment). The surviving step is a `git diff` baseline-approval check that does not read `matrix.board`. Vestigial fields, not a live consumer. |
| `scripts/bless_baselines.py` / `scripts/extract_corpus_baselines.py` | N/A today | none | `extract_corpus_baselines.py` is an explicit `DEPRECATED` stub (JAX optimizer retired 2026-07); calling it exits 1 with a pointer to the CP-SAT CLI. Dead code path, not a live consumer. |
| `.github/workflows/human-reference-check.yml` | N/A today | none | Opt-in (`ci-advisory` label only), `continue-on-error: true` on its one substantive step, and that step `ModuleNotFoundError`s on `jax` before reaching any board (jax is not a declared dependency). Also has a pre-existing, unrelated bug: its board-path table has no `temper` case, so it would resolve to a nonexistent `.../temper/keyboard_pcb.kicad_pcb` even if jax were installed. Broken independent of this task; not touched here (out of scope). |
| `scripts/ci_closure_test.py` | Solves via `--pcb` CLI arg | n/a | Every invocation in every workflow (`metrics-record.yml`, `pr-pipeline-scorecard.yml`, `python-tests.yml`) passes `--pcb pcb/temper.kicad_pcb` explicitly. Not a corpus-fixture consumer at all. |
| `power_pcb_dataset/golden_manifest.yaml` | N/A | none | A separate, smaller manifest (`temper_production` id) pointing at `pcb/temper.kicad_pcb` directly, `component_count: 149` (itself stale — real count is 169). Not a corpus-fixture consumer; its own staleness is a separate, smaller finding not acted on here (one integer, no code depends on it being current as verified by grep). |

## 2. The solve-time measurement

Measured directly today, same call shape as `test_golden_board_drc_regression`
(`solve_placement(..., timeout_ms=30_000, seed=42, zones=<PCL zones>)`,
same `_UNRESOLVED_REF_POLICY="warn"` downgrade, same
`temper_induction_cooker.yaml` PCL config, 21 constraints + 3 zones
loaded successfully):

| Board | Components | Status | Wall time | Budget |
|---|---:|---|---:|---:|
| `power_pcb_dataset/corpus/temper/temper.kicad_pcb` (corpus fixture) | 33 | `optimal` | 3.498s | 30s |
| `pcb/temper.kicad_pcb` (real board) | 169 | `unknown` (never completes) | 19.784s (this run; ranged 22.9-25.4s in the independent `docs/evidence/2026-08-11-pumpkin-real-budget-spike.md` §4.1 run, N=3 seeds, all hit the 30s wall) | 30s |

This directly reproduces, independently, the same finding
`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md` reports (§4.0-4.1)
and the one `test_production_board_drc_regression`'s own docstring already
stated in prose ("infeasible at 168 components / 30s timeout") before
either spike ran. Three independent sources now agree: **OR-Tools CP-SAT
does not decide feasibility on the real 169-component board within the
30s budget every CI-gating test in this repo actually uses.**

A secondary observation from this run: the PCL config's component
references (`Q1`, `Q2`, `U_MCU`, `C_BUS1`, `C_BUS2`, `U_GATE`, ...) resolve
cleanly against the 33-component corpus fixture (it still carries the
original, pre-resync symbolic reference designators) and do **not**
resolve against the real board (renumbered `U1`..`U27`/`C1`..`C40` in the
2026-07-15 BOM resync) — visible directly in this run's own
"Constraint(s) reference names absent from the netlist" warnings, firing
only for the real-board call. This is the same drift
`docs/evidence/2026-08-11-pcl-config-intent.md` §1.4 already documented by
static analysis; this run reproduces it dynamically.

**What it would take to make the real board solvable in this test's
budget** (reported, not implemented — out of scope): per
`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md`, Pumpkin proves
feasibility on the real board in 0.9-2.0s where OR-Tools does not complete
in 30s — but that spike also found the *full, as-configured* PCL-constrained
model is `infeasible` for both engines (§4.1), because of the config/board
reference drift above, independent of which solver is used. So even a
solver swap does not unlock "regenerate the fixture and have this test
mean something at real scale" today; the PCL config would need the
same owner/EE-reviewed fix `2026-08-11-pcl-config-intent.md` scoped and
explicitly declined to make unilaterally.

## 3. What moved

**Nothing in `power_pcb_dataset/corpus/temper/temper.kicad_pcb` itself.**
No baseline, ceiling, or pinned-metric value in this repo changed, because
the fixture was not regenerated. Specifically NOT moved, and verified
unaffected by this PR:

- `power_pcb_dataset/corpus/temper/baseline.json`, `constraints.yaml`,
  `human_reference.yaml` — untouched.
- `packages/temper-placer/tests/router_v6/_quality_metrics_cases.py`'s
  pinned `CORPUS_BOARDS["temper"]` metrics (`n_components=33`, `n_vias=0`,
  `lint_total=0`, ...) — untouched; a regeneration would have forced every
  one of these to be re-derived and re-verified against the router's
  actual output, which is exactly the "report every such movement" case
  this task's cautions section warned about. It did not happen because
  the fixture did not change.
- `packages/temper-placer/tests/test_metamorphic_oracles.py`,
  `test_round_trip_integrity.py`, `test_dsn_rust_differential.py` — all
  three pass unchanged (verified: `pytest tests/test_metamorphic_oracles.py
  tests/test_round_trip_integrity.py -q` → 9 passed).
- `test_golden_board_drc_regression` / `test_golden_board_routing_drc_regression`
  — solve behavior unchanged (still `optimal` in ~3.5s on the same
  fixture); no new skip, no new failure introduced.

**What DID change** (naming/documentation/tooling only, per task items 4-5):

- `docs/evidence/scripts/2026-08-07-cpsat-equivalence-harness.py`:
  `build_full_board_corpus()`'s docstring no longer calls the fixture "the
  real golden-board corpus"; the returned model's `name` field changed
  from `"full-board"` to `"corpus-fixture-33c"` so the label itself
  carries the component count; every result line already printed
  `len(model.verification_model.sizes_mm)` (unchanged) and now the model
  name reinforces rather than contradicts it.
- `docs/evidence/scripts/2026-08-07-pumpkin-equivalence-run.py`: the dependent
  `model.name == "full-board"` timeout-selection check updated to match,
  so a future re-run of this companion script does not silently regress
  to the wrong timeout.
- `power_pcb_dataset/corpus/manifest.yaml`: the `temper` board entry gained
  `role: independent-fixture` and `real_board_path: pcb/temper.kicad_pcb`,
  making today's A-vs-B decision a durable, machine-checked fact instead
  of tribal knowledge someone has to re-derive from git history again.
- New: `scripts/check_corpus_fixture_realboard_divergence.py` +
  `scripts/tests/test_check_corpus_fixture_realboard_divergence.py` (9
  tests, all passing) — the staleness gate (task item 5), wired
  **BLOCKING** (not advisory) into `python-tests.yml` as "Gate 5", because
  it already passes clean on `origin/main` today (the manifest correctly
  declares `role: independent-fixture`, so the fixture's divergence from
  the real board is reported as information, not a failure). Modeled
  directly on `scripts/check_pcl_config_board_correspondence.py` (Gate 1):
  same exit-code convention (0/violation=3/gate-error=5), same
  dependency-free KiCad s-expression reader (reused via import rather than
  duplicated), same `_lib.repo`/`_lib.github_summary` helpers.

## 4. Why this gate is shaped the way it is (not "fixture must match real board")

An earlier draft of this gate asserted every corpus fixture's component
count must equal its real-board counterpart's — i.e. hard-coding the A
answer. That is wrong for the same reason regenerating the fixture
outright is wrong: it would make `role: independent-fixture` boards
(this one, today) either impossible to declare or permanently failing.
The gate instead makes the manifest the single place a human commits to
A or B **per board**, and enforces internal consistency of that
commitment rather than a single global policy:

- `role: real-board-snapshot` + component-count mismatch → **BLOCKING
  violation** (exit 3). This is the check that would have caught the
  2026-07-15 33→169 jump the same week it happened, if this fixture had
  ever been declared this role.
- `role: independent-fixture` → divergence reported, never fails. This is
  `temper` today: CP-SAT needs it to stay small (§2), so divergence from
  the real board's component count is not a defect, it's the design.
  `MISMATCH` in the printed report is not a synonym for `FAILED` for this
  role — the test suite makes this explicit
  (`TestIndependentRole::test_independent_component_count_mismatch_is_informational_not_a_violation`).
- No `role` declared at all, while `real_board_path` is present →
  **GATE ERROR** (exit 5), fail closed. This is deliberately the loudest
  failure mode: an undeclared role is exactly the shape of the original
  incident (a fixture nobody had ever committed, in writing, to "does or
  doesn't track the real board").

## 5. Boundaries respected

`pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`,
`power_pcb_dataset/drc_ceiling.json`, and `power_pcb_dataset/baselines/**`
were not read for modification and are unchanged (verified: `git status`
shows no changes under any of these paths). No PCL config edits landed —
`packages/temper-placer/configs/constraints/temper_induction_cooker.yaml`
is untouched, consistent with `docs/evidence/2026-08-11-pcl-config-intent.md`'s
own conclusion that none of its 21 constraints have a safe mechanical fix.
