# Evidence: gate-loop inductance estimator, remaining unwired kernels, duplicate-predicates registry

Status: DONE.

Branching from PR #1304 (`fix/trunk-health-green-the-trunk-2026-08-17`), picking up the
agent-actionable remainder per `docs/HANDOFF-2026-08-17.md`.

Board sha256 verified unchanged, start and end: `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`.
`pcb/temper.kicad_pcb` was not modified.

## Priority 1 — `estimate_gate_inductance_py` verdict: dead-by-design, deleted

**Not a live bug.** Neither the generic formula nor the gate-specific formula is applied to
the gate-drive loop in production today, because the entire call chain that would apply
either one is dead code, and has been for over a month:

1. `estimate_gate_inductance` (Rust, `packages/temper-thermal/src/inductance.rs`) had **zero
   production callers since the day it was authored** — `60a0ff099` (2025-12-26, pre-Rust
   Python original). At that exact commit, `measure_emi` was updated to call the generic
   `estimate_loop_inductance` for ALL loops (including the `i == 0` "gate drive" case) while
   `estimate_gate_inductance` was added alongside it and never wired in. This is not a
   regression — it was never wired, from inception, through the Wave 4 Rust port.
2. Its only ever-intended caller, `temper_placer.metrics.physics.measure_emi`, was itself
   deleted as dead code by `1060584b7` ("retire the old iterative pipeline + MazeRouter
   full-routing", 2026-07-10) — a deliberate, verified refactor unrelated to inductance. That
   commit removed `pipeline/orchestrator.py`'s `PipelineOrchestrator`, whose
   `_measure_physics` method (confirmed by reading `pipeline/orchestrator.py` at
   `1060584b7^`) was the sole call site of `measure_emi`/`measure_geometric`/
   `measure_thermal`/`measure_routability`/`PhysicsReport`. Since 2026-07-10, `metrics/
   physics.py` is not even re-exported from `temper_placer.metrics.__init__` — the whole
   module is orphaned, exercised only by its own test suite.
3. The board's actual, designed physics-check architecture for the gate-drive loop is
   `placer/cp_sat/gates.py::PhysicsGate.check()`'s sub-check 2 ("Gate-drive tightness"),
   which measures **routed trace geometry** — `gate_drive_loop_area`/`gate_drive_spacing`
   from `temper_placer.physics.gate_drive` — not a component-position inductance estimate.
   That module **does not exist anywhere in this repository** (confirmed: no `gate_drive.py`
   file, no `def gate_drive_loop_area`/`gate_drive_spacing` in Python or Rust). The
   `try/except ImportError` around that sub-check always fires, and `PhysicsGate.check()`
   always returns `UNMEASURED` for the gate-drive-loop check today, independent of this
   estimator. (Sub-check 1, commutation-loop area, is separately confirmed unreachable on
   the real board by `docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md`.) The
   design plan that created `PhysicsGate` (`docs/plans/2026-07-08-005-...`) intended
   `compute_gate_drive_loop_area`/`min_trace_to_return_spacing` to be added to
   `physics/loop_area.py`; that never happened either — `gates.py`'s import targets a
   different, never-created module name. This is a separate, larger, pre-existing gap
   (an entire unimplemented gate sub-check) — flagged for the owner, not attempted here.
4. **Stale-ground-truth corroboration**: `packages/temper-thermal/VERIFICATION.md` (§4, R24
   note) and `scripts/duplicate_predicate_registry.py`'s sibling registry
   (`validation/gate_input_registry.py`'s `R37-PHANTOM-REQUIRED-METRICS` finding, written
   2026-08-05, a month AFTER the pipeline retirement) both asserted `measure_emi` was "the
   live surface" for gate-loop EMI. Both were wrong by the time they were written; both are
   corrected as part of this pass (VERIFICATION.md directly; `gate_input_registry.py`'s
   stale attribution is flagged in this doc for a follow-up, not touched — it is a
   descriptive `TrackedFinding.attribution` string, not itself a scanned/enforced check, so
   leaving it stale is lower-priority than the enforced gates this pass fixed).

**Magnitude/direction, for the record (the estimator was never live, but the task asked):**
`estimate_gate_inductance(a, b) = (a + b + 5.0) * 0.8`. The generic formula, called on a
2-vertex "loop" (the shape `measure_emi` would actually receive for a driver→gate pair,
since `len(v) < 3` forces `area = 0.0`), reduces to `(2 * dist(driver, gate) * 0.2) * 1.2`.
For representative gate-driver-to-gate-resistor spacing (`configs/gate_driver_constraints.
yaml`: `U_GATE` (15,15) to `R_GATE_H` (20,20), 7.07 mm), the generic formula gives ≈3.4 nH
vs. the dedicated formula's ≈15.3 nH for the same 7.07 mm figure used symmetrically — the
generic formula is **permissive** (understates gate-loop inductance) in the 2-vertex case
that `measure_emi`'s actual calling convention would produce. Had this path been live, it
would have been the dangerous direction for EMI/overshoot margin. It was not live, so this
did not affect the board.

**Resolution: deleted**, not ledgered. Wiring `estimate_gate_inductance_py` into still-dead
`measure_emi` would have satisfied the unwired-kernel gate's coarse AST-reference check
(it counts any non-test reference, dead or not) without restoring any real behavior — that
would be gate-satisfaction theater, not a fix. Genuinely dead code with a fully-traced,
non-speculative provenance is legitimate to delete per this task's own rules.

Deleted: `estimate_gate_inductance`/`estimate_gate_inductance_py` (Rust fn + pyo3 binding +
`lib.rs` registration), its 3 Rust unit tests, its `ind_gate_commutative` property (60
generated-seed tests) in `property_campaigns.rs`, and the matching Python test code (`test_
inductance.py::test_estimate_gate_inductance`, `test_inductance_rust_differential.py`'s
gate oracle/pins, `test_inductance_rust_pbt.py`'s P3/M5 properties and their mutation
tests). `estimate_loop_inductance` (the generic formula) is untouched — it is out of this
priority's scope and the unwired-kernel gate does not flag it (the gate's coarse AST scan
sees `metrics/physics.py`'s dead `measure_emi` still textually reference it, which is enough
for the gate's definition of "wired" even though the call is unreachable — the gate cannot
see through dead code, which is exactly its documented limitation).

**Verification**: `cargo test -p temper-thermal --lib` — 2693 passed, 0 failed, after
deleting exactly 63 tests (60 `ind_gate_commutative` generated-seed tests + 3
`inductance.rs` gate unit tests) and nothing else. `cargo clippy -p temper-thermal
--all-targets` clean.
`cargo test -p temper-thermal --doc` clean. `scripts/gen_wasm_test_registry.py --check
--crate temper-thermal` clean after regeneration (2701→2638 entries, exact match). Python
test files verified syntactically (`py_compile`) and functionally (57/57 pass against the
shared `.venv`'s existing `temper_thermal` build — read-only, no `.so` rebuilt into the
shared venv per this task's hard rule).

## Priority 2 — the 8 remaining unwired-kernel-gate symbols, classified

Ran `scripts/check_unwired_kernels.py` directly (not by name) to get the authoritative list.
All 8 confirmed present before this pass; `estimate_gate_inductance_py` is the 9th named in
the handoff, already covered above (deleted, no longer registered at all).

| Symbol | Verdict | Action |
|---|---|---|
| `estimate_gate_inductance_py` | Dead-by-design (Priority 1) | **Deleted** |
| `slop_lint_hairpin_turns_py` | **Not a real gap** | Ledgered `[NOT-A-GAP]` |
| `slop_lint_isolated_vias_py` | **Not a real gap** | Ledgered `[NOT-A-GAP]` |
| `slop_lint_single_net_detours_py` | **Not a real gap** | Ledgered `[NOT-A-GAP]` |
| `slop_lint_zigzag_patterns_py` | **Not a real gap** | Ledgered `[NOT-A-GAP]` |
| `test_only_stackup` | **Not a real gap** (test fixture, by design) | Ledgered `[NOT-A-GAP]` |
| `parse_stackup` | **Live-path gap, owner-blocked** | Ledgered `[WIRE, owner-blocked]` |
| `parse_stackup_from_path` | **Live-path gap, owner-blocked** | Ledgered `[WIRE, owner-blocked]` |

### The 4 `slop_lint_*_py` — not a real gap

`slop_lint_all_py` **is** wired in production (`placer/cp_sat/gates.py:1101`,
`RepoHygieneGate`). Read its Rust body directly: `cluster_f::slop_linter::lint_all`
(`packages/temper-quality-oracle/src/cluster_f/slop_linter.rs:321`) is a fixed
concatenation — `lint_hairpin_turns(view) + lint_zigzag_patterns(view) +
lint_isolated_vias(view) + lint_single_net_detours(view, 1.5)` — the exact same Rust
functions the 4 individually-unwired `_py` bindings expose, just reached through the
aggregate's name rather than their own. Production exercises all 4 checks every time it
calls `slop_lint_all_py`; the individual bindings exist only so the differential oracle can
pin each linter in isolation (confirmed: they're used only in test files). Matches PR
#1304's speculation exactly — confirmed, not assumed, by reading `lint_all`'s body.

### `test_only_stackup` — not a real gap, deliberately test-only

Self-documented at `layer_identity.rs:730-733` as "the named, greppable Python-side escape
hatch for synthetic test fixtures" (mirrors `Stackup::test_only`). A production caller
would defeat its purpose: outside tests, a `Stackup` must only ever come from
`parse_stackup`/`parse_stackup_from_path` (a real board's own declaration) — the whole
point of `layer_identity.rs` (PR #1210, see below) is that a `Layer`/`Stackup` cannot be
hand-constructed from outside the module.

### `parse_stackup` / `parse_stackup_from_path` — genuine live-path gap, owner-blocked

**This is a real instance of mechanism 2**, not premature surface as PR #1304 speculated.
`layer_identity.rs` (PR #1210, 2026-08-15, two days before this pass) exists specifically to
replace `board_layer_roles.py`'s hand-rolled regex parser
(`parse_declared_layer_roles`/`parse_declared_layer_roles_from_path`) — its own evidence doc
(`docs/evidence/2026-08-14-layer-identity-type.md`, §3.2) gives the exact intended
migration: replace those two functions plus `signal_layer_names`/`routable_signal_layers`/
`is_signal_layer` with thin wrappers over `temper_geometry.parse_stackup`/
`parse_stackup_from_path` + `Stackup.signal_layer_names`/`routable_signal_layer_names`. Half
of that migration already landed (PR #1304: `ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` now
reads `temper_geometry.engine_supported_signal_layer_names()`); the parser half — the part
that would wire `parse_stackup`/`parse_stackup_from_path` in — was explicitly deferred, per
that evidence doc, "because doing so makes `board_layer_roles.py`'s import-time behavior
depend on a rebuilt `temper_geometry` native extension" during a busy multi-agent session,
not because it was judged unsafe on the merits.

**Not wired in this pass because it is NOT safe to do mechanically**, and this is a new
finding the 2026-08-14 evidence doc did not surface: `Stackup::parse`
(`layer_identity.rs:447`) has a **strictly stronger contract** than the Python parser it
would replace. `Stackup::parse` hard-requires a `(setup (stackup ...))` copper-thickness
entry for **every** declared `.Cu` layer (`StackupParseError::MissingCopperThickness`
otherwise), while `board_layer_roles.parse_declared_layer_roles` only ever reads the
`(layers ...)` block and has no dependency on the stackup/thickness block at all. Confirmed
directly: `tests/core/test_board_layer_roles.py`'s synthetic fixtures
(`_FOUR_LAYER_FRAGMENT`, `_SIX_LAYER_FRAGMENT`) declare a `(layers ...)` block only, no
`(setup (stackup ...))` block, and 8 of that file's tests (`TestParseDeclaredLayerRoles`,
`TestSignalLayerNames`, `TestRoutableSignalLayers`) call `parse_declared_layer_roles`/
`signal_layer_names`/`routable_signal_layers` directly against them — every one of those
tests would newly raise `NoStackupBlock`/`MissingCopperThickness` if the Rust parser were
swapped in verbatim. This is a real behavior change the migration path did not account for,
not a mechanical rename.

**Owner decision needed** (recorded precisely in `.unwired-kernel-inventory`): either (a)
relax `Stackup::parse` to make the stackup-thickness block optional for callers that only
need role/name (a Rust API change to a type built two days ago, low blast radius but a
real semantics decision about what "role-only" parsing should require), or (b) update
`board_layer_roles.py`'s test fixtures to include a stackup block and confirm no other
`(layers ...)`-only caller exists before wiring. Not attempted here: this is a designed
consolidation with a real behavioral subtlety, not a mechanical call-site swap, and
`layer_identity.rs` is very recently active (PR #1210 landed 2 days before this pass).

## Priority 3 — `check_duplicate_predicates.py`: registry was stale, not wrong

**Ran the gate directly**: `python3 scripts/check_duplicate_predicates.py` exited 3 (1
violation) before this pass — `clearance_check.py:857: def _is_hv_keyword_match(...) does
not call 'kw_boundary_match_py' anywhere in its body`.

**What the registry claimed**: the `hv_keyword_boundary_match` `ConsolidatedFamily`
asserted `clearance_check.py`'s `_is_hv_keyword_match` must delegate to
`temper_geometry.kw_boundary_match_py` (`via_clearance.rs`), consolidated 2026-08-13.

**What reality is**: it does not delegate — it has its own regex,
`(?:^|[_-])kw(?:$|[\d_-])`, treating **both** `_` and `-` as boundary characters.
`kw_boundary_match_py` (via `word_bounded`, `via_clearance.rs:168`) treats **only** `_` as a
boundary — confirmed by reading both implementations directly, not inferred from
docstrings.

**Which is right — both, for their own callers, and this was already decided and
documented on 2026-08-13, not a fresh call**:

- `_is_hv_keyword_match` **must** use the wider `_`/`-` boundary. Its own bug-history
  docstring (`clearance_check.py:7`, "Family C" of the hyphen-boundary defect) documents
  that 85 of 162 real net names on the production board mix `-` and `_` as word separators
  (atopile's compiled net names), and every one was invisible to the `_`-only boundary
  whenever the matching keyword sat on the hyphen side — a real **under-classification**
  defect, the dangerous direction for HV/LV creepage-rule selection on a mains board. Fixed
  by widening, with the resulting 14-net SELV over-match (the `"LINE"` keyword against
  `-line`-suffix nets) caught and mitigated by `_SELV_LINE_NET_OVERRIDES`, checked first.
- `kw_boundary_match_py` **must** stay `_`-only. `clearance_engine.py`'s own "Bug history
  (2026-08-13), URGENT — audited, deliberately NOT widened" docstring (`clearance_engine.
  py:50`) records that this kernel's only callers (`_kw_boundary_match`,
  `_net_class_to_voltage_class`) receive already-classified short net-CLASS labels (`"HV"`,
  `"Signal"`, ...) produced by `clearance_check._classify_net_class`, never raw hyphenated
  net NAMES directly — board-wide simulation of all 162 real net names confirmed zero live
  exposure through this narrower path. Widening it would also break
  `test_via_clearance_tier2_rust_differential.py`'s byte-verbatim oracle pin
  (`_ORACLE_PIN_SHA = "f1ffc013"`) with no documented safe update path.

Both sides' rationale is independently written, dated, and evidenced **on the same day**
(2026-08-13) the registry's `ConsolidatedFamily` entry was created — the registry was never
reconciled after the Family C fix re-diverged the one file it was watching. This is not an
unresolved editorial question about HV classification; it is a stale bookkeeping entry
describing a decision that was already made, correctly, on both sides, in writing.

**Resolved (registry only — no clearance/creepage/HV-classification logic touched)**:
removed the `hv_keyword_boundary_match` `ConsolidatedFamily` (its only scan target,
`clearance_check.py`, is a deliberate, permanent, different-contract implementation, not an
accidentally-regressed duplicate — "must call `kw_boundary_match_py`" was never the right
check for it). Added an `OpenFinding` (`diverged=True`) in its place recording the
divergence, both rationales, and the precise decision an owner would need to make if a
single shared implementation is ever wanted: widening `kw_boundary_match_py` needs an
oracle-pin update this pass did not have a safe path for; narrowing `_is_hv_keyword_match`
back down would reintroduce the confirmed Family C under-classification on real board net
names. Neither side should move without that being an explicit, human safety call — not a
side effect of a registry-consolidation gate.

**Explicitly not touched, and out of scope**: `packages/temper-drc-rs/src/router_clearance.
rs` has its own, third, independent word-boundary keyword matcher (`compile_keyword`,
mirroring `_is_hv_keyword_match`'s pre-Family-C `_`-only form) — visibly under active work
by another session (the most recent commit on `main`, `1a7d1dde0` "fix(drc): word-boundary
net classification in router_clearance (resolves #1175)", is not yet in this branch's
ancestry and touches exactly this file). Registering it as a new duplicate-predicate family
would be a fresh audit exercise the gate's own docstring says is out of a mechanical gate's
scope, and the file is someone else's in-flight work.

**Verification**: `python3 scripts/check_duplicate_predicates.py` now exits 0 ("PASS -- 2
consolidated predicate families checked, 0 non-delegating copies found"). Full test suite
`scripts/tests/test_check_duplicate_predicates.py` — 17/17 pass (via the shared `.venv`'s
Python, read-only, no `.so` rebuild — this test file is pure Python, no pyo3 dependency).

## What was left honestly red / not attempted

- The `PhysicsGate` gate-drive-tightness sub-check being permanently `UNMEASURED` (missing
  `physics/gate_drive.py` module) — a real, pre-existing gap, larger than "wire one
  estimator." Flagged for the owner; not attempted (out of this task's stated scope, and a
  genuine feature-completion, not a wiring fix).
- `gate_input_registry.py`'s `R37-PHANTOM-REQUIRED-METRICS` `TrackedFinding.attribution`
  string still says `measure_emi` is "the live surface" — now known stale (see Priority 1).
  Not corrected: it is a descriptive string in a `status="closed"` historical record, not
  itself a scanned/enforced check, so lower priority than the two live gates this pass
  fixed. Flagged for a follow-up.
- `packages/temper-drc-rs/src/router_clearance.rs`'s independent keyword matcher (see
  Priority 3) — third home for a related-but-not-identical predicate, actively owned by
  another in-flight session.
- `parse_stackup`/`parse_stackup_from_path` remain unwired, owner-blocked (see Priority 2)
  — the `Stackup::parse` stackup-thickness-block-required-vs-optional question is a real
  decision, not something to make unilaterally.
- Everything explicitly out of scope per the task brief: `pair_clearance.py`,
  `_astar_nlayer.py`, `test_astar_nlayer.py`, `test_clearance_check.py`,
  `zone_generator.rs`, `_zone_pour_stitch.py`, wasm-tier workflows, `pad_connectivity_
  audit.py`, routing metrics, and the LOC-cap gate — untouched.
