<!-- provenance: commit=9e957dc0923784eedc8d99f6e4d916842941225b dirty=false (recorded by the follow-up chore commit; the referenced commit is the doc-content commit, reachable from this branch) -->

# Validator-aligned post-solve solve audit — closing the run-B lie (issue #523 gap 2, R24 item 3)

**Date:** 2026-08-02
**Branch:** `feat/validator-aligned-solve-audit` (worktree `.claude/worktrees/agent-gap2`).
**Issue:** #523 gap 2 — the placer's post-solve audit must re-run the
REQ-SAFE-01 validator itself, not a cheaper proxy, so a solve that passes the
solver's own audit cannot silently fail the actual safety gate.
**Constraint discipline:** AGENTS.md R24 (post-solve audit recomputes the
physical quantity from coordinates and hard-fails on mismatch), R22 (bug
triage, no test weakening), no gate changes, no `continue-on-error`,
`pcb/**` untouched.

## 1. What gap 2 does

`solve_placement` gains an optional `validator_input={"placement": ...,
"voltage_domains": ...}` parameter. When given AND the solve is
feasible/optimal, the REQ-SAFE-01 validator itself
(`verify_iec60335_compliance` — copper-to-copper on exact, rotation-aware pad
geometry, the function the CI gate runs) is re-run against a placement whose
positions/rotations come from the *solve* (`build_validator_placement`
mirrors `tests/requirements/safety/_real_board_fixture.py`'s loader shape;
only the position/rotation source changes). Violations are classified into
three buckets; a HARD failure on a feasible/optimal solve **raises**
(`RuntimeError`), same contract as `audit_fixed_copper`. The cheaper
center-distance audit (`audit_domain_clearance`, still the repair loop's
cheap encoder check) is untouched — this audit is additive.

Absent `validator_input`, the solve is byte-for-byte unchanged
(`validator_audit` stays `None`); a missing `placement`/`voltage_domains` key
raises `ValueError` rather than silently skipping the gate.

## 2. The run-B lie this kills

Measured and documented in
`docs/evidence/2026-08-01-k3-runb-not-validator-clean.md` (the PR #564
evidence doc): the issue-#523 run-B scoped solve (K3 → (63.52, 51.97),
C27 → (44.44, 236.56)) was **solver-audit-clean** — `audit_fixed_copper`
0 violations, `audit_domain_clearance` 0 violations — while the actual
REQ-SAFE-01 gate measured **12 violations across 9 pairs** on the same
placement (C27 0.32mm from U24; C3/K3, K3/R60, C24/K3). Root cause, in code:

- `domain_clearance.audit_domain_clearance` (line ~436) recomputes
  **center-to-center** Euclidean distance vs the margin; its own docstring
  admits it is "a cheaper, weaker check than what `clearance.py`'s validator
  actually measures (copper-to-copper on exact pad geometry)".
- The truth is `clearance.verify_iec60335_compliance` — exact pad copper via
  the `_copper.py` model, the same function the CI gate runs.
- `generate_domain_clearance_constraints` already mirrors the validator's
  pair set and margins (imported pairing, verified at domain_clearance.py:233
  + clearance.py:367 `_domain_boundary_pairs`), so the pair/margin side was
  aligned; **the audit side was not**. Gap 2 = make the post-solve audit run
  the validator itself.

A center-to-center distance is an **upper bound** on true copper-to-copper
separation (copper extends outward from the center): a placement can be
center-clean while its copper violates every bar — the exact direction this
project already burned once (the origin-to-origin → copper fix of
2026-07-28, `docs/evidence/2026-07-28-clearance-copper-to-copper.md`).
`audit_domain_clearance`'s center check is the same optimism, one level
removed.

## 3. Classification semantics (per validator violation)

| bucket | condition | consequence |
|---|---|---|
| (a) **HARD** | inter-component pair covered by a generated `domain_clearance_` `SeparatedConstraint` | encoding unsound for this solve; `solve_placement` **raises** on feasible/optimal |
| (b) **intra-footprint** | `pair_kind == "intra"` or `ref_a == ref_b` | placement-independent (a rigid part's own pads move together); reported, never raised — the K3 G5LE-1 class |
| (c) **coverage gap** | inter pair NOT in the constraint set (the generator's `component_refs` filter or the intra-footprint exemption excluded it) | solver↔validator pair-set alignment finding; reported, never raised |

`DomainClearanceValidatorAuditResult.clean` = no hard failures AND no
coverage gaps (intra-footprint records may remain — placement cannot fix
them). The classification needs only the constraint **pair set**, not its
margins: coverage is a per-pair property, and the validator violation
carries its own per-row `required_mm`.

**Geometry trust (added in adversarial review).** The validator models a
placement component without a `pads` key as a zero-extent point at its
origin — an *optimistic* upper bound on copper-to-copper separation (the
run-B lie direction: it can miss violations, never invent them). The audit
result therefore carries the validator's own `stats`
(`components_without_pads`, per-row `pairs_origin_modelled`) and a
`geometry_trusted` flag: **False** whenever any component lacked pads or any
pair was measured origin-to-origin, logged at `logger.error`. A
clean-but-untrusted audit proves nothing about real copper and must not
gate the board. The audit also raises `ValueError` (programmer error) when
the placement does not describe the solve — zero components, or
`resolved_positions_mm` refs disjoint from the placement's refs — instead
of vacuous-passing over the wrong geometry.

## 4. The falsifier proof (run-B lie, minimized)

Two components whose bbox centers are ≥ the margin apart (so the old
center audit reports 0 violations) but whose pad copper extends toward each
other below margin (so the validator fires). Concrete geometry, pinned by
`tests/placer/cp_sat/test_validator_audit.py::TestAuditFalsifier`:

- A at (0,0), B at (8.1,0): center distance 8.1 ≥ 8.0mm bar →
  `audit_domain_clearance` = **0 violations**.
- A's pad at offset (3,0), 2×1mm rect → copper x ∈ [2.0, 4.0]; B's pad at
  offset (−3,0) → copper x ∈ [4.1, 6.1]: exact copper-to-copper gap
  **0.1mm** ≪ every MAINS<->LV_CONTROL bar (3.0/4.0/6.0/8.0mm).
- `audit_domain_clearance_validator` classifies all 4 matrix-row violations
  as **HARD** (the pair IS covered by the constraint set), `clean is False`.
- The same geometry through `solve_placement` (deliberately broken bounds:
  copper outside the solver's 1×1mm box model — the exact failure mode the
  audit exists to catch): boxes separated 7.1mm ≥ the 4.0mm bar → solve
  feasible/optimal, and the wiring **raises RuntimeError** ("REQ-SAFE-01
  validator post-solve audit FAILED").

This is the minimized run-B: box separation (solver SAT) ≠ copper separation
(validator), and the audit now reports the difference instead of echoing the
solver's own "0 violations".

## 5. Position-frame contract (handoff §6 trap)

`solve_placement` only repositions FREE refs; fixed refs keep their board
positions. `build_validator_placement` overlays solved positions/rotations
only for refs in `resolved_positions_mm` and keeps the base placement
otherwise. The base placement (from `load_real_board_placement`) and the
solver positions are in **one consistent frame**: both are local
(origin-subtracted) coordinates of the parser's `Component.initial_position`
(board origin (20,20), 152×234mm). Verified two ways on the real board:

1. The validator's per-pair distances on the solved placement equal the
   committed board's exactly — the production test asserts
   `solved_metrics == base_metrics` (3 violations / 1 pair, all K3-intra,
   measured 3.559mm — the documented figure from the handoff §3).
2. Every fixed ref's solved position stays within one 0.01mm model-grid step
   of its board position (the documented `mm_to_units` round-half-even
   quantization), and C27 (excluded from the solve model, staged off-board)
   keeps its staged base position in the validator placement.

One latent defect found and fixed during adversarial review: the original
overlay gate kept the base `rotation_deg` whenever it was
non-multiple-of-90, *even for a ref the solve had rotated*. That was wrong
against the CLI contract: `cli/__init__.py`'s optimize command writes
`rotation=cp_result.rotations.get(ref, 0) * 90.0` to the PCB
**unconditionally** for every solved ref, so a ref the solve rotated *will*
be written as `idx*90` on the board — the audit must measure that post-solve
geometry, not the base. The overlay is now unconditional for any ref present
in BOTH `resolved_positions_mm` and `resolved_rotations` (the solve touched
it; the solver's rotation is authoritative), and the base rotation is kept
only when the ref is absent from `resolved_rotations` (the solve did not
rotate it — no rotation variable, e.g. a polarized part pinned by
construction). No-op on the production board (0 non-quadrant rotations,
measured), latent-correctness fix for the general contract.

## 6. Wiring contract (`_encoder_solve.py`)

- New optional param `validator_input: dict | None = None` on
  `solve_placement`; default `None` → existing behaviour unchanged
  (`validator_audit` `None`, logged at debug).
- When given and status ∈ {optimal, feasible}: filter the solve's
  `SeparatedConstraint` set to `domain_clearance_`-prefixed ids (the
  validator audit's concern is the domain-clearance pair set, not courtyard/
  netclass/keepaway), run `audit_domain_clearance_validator` with the solve's
  `positions`/`rotations`/`netlist`, and **raise RuntimeError** on
  `hard_failures` (a feasible solve with a constraint-covered copper
  violation is an encoding unsoundness, same contract as
  `audit_fixed_copper`). `intra_footprint`/`coverage_gaps` land on
  `CpSatPlacementResult.validator_audit`, never raised.
- Missing `placement` or `voltage_domains` key → `ValueError` (a silent skip
  would leave the solve unaudited against REQ-SAFE-01).
- On `infeasible`/`model_invalid`/`unknown` the audit does not run (there is
  no placement to audit) — `validator_audit` stays `None`, and the skip is
  logged at **WARNING** ("validator post-solve audit did NOT run ..."), never
  silent, so an unaudited solve is distinguishable from a clean one in the
  logs (adversarial-review finding 4).
- The hard-failure `RuntimeError` reports the **distinct violating-pair
  count** (frozenset-deduped) as the headline, with the raw record count in
  parentheses — one physical pair emits 4-8 records (clearance/creepage ×
  basic/reinforced), so "N hard violation(s)" with N=records would inflate a
  1-pair failure into a 4-8-pair failure (adversarial-review finding 5).
- Pair membership in the classification is a `frozenset`: a validator
  violation emitted as (B,A) against a constraint (A,B) absorbs into the
  same covered pair (HARD), never a coverage gap — the 451 reversed-duplicate
  emissions Agent 4 measured on the production board (e.g. (C11,C6)@1.0 +
  (C6,C11)@8.0) all collapse onto their covered pair (adversarial-review
  finding 6).

## 7. Measured results (this branch, 2026-08-02)

### Production solve (real board, FREE={K3})

The full #523 scoped solve (FREE={K3} + the 11,908-constraint
domain-clearance set at the 8.0mm PD2 bar) is **infeasible** on current main
— the documented "domain-bar wall": the box bar forces pinned refs' boxes
past their current separations (verified while writing this suite; same wall
as `docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md` and
`docs/evidence/2026-08-01-fixed-copper-constraint.md`). The production test
therefore uses the **pure-geometry recipe** the edge-hanging evidence doc
(`docs/evidence/2026-08-01-edge-hanging-refs-fix.md`) verified optimal on
current main: FREE={K3}, C27 excluded from the model (staged off-board),
everything else pinned at current positions/rotations, min-displacement
objective, hints = current positions, seed 0, NO domain/keepaway/fixed-copper
constraints.

Outcome (asserted by
`tests/placer/cp_sat/test_validator_audit.py::TestProductionBoardSolve`):

| metric | value |
|---|---|
| solve status | **optimal** |
| K3 solved position | its committed position (min-displacement optimum at 0) |
| `hard_failures` | **[]** |
| `coverage_gaps` | **[]** |
| `intra_footprint` | **3 violations / 1 pair, all K3** (G5LE-1: 3.559mm vs 4.0/6.0/8.0 bars — the documented single remaining REQ-SAFE-01 finding) |
| validator distances | identical to the committed board (3.559mm, exact) |

The K3-intra straddler lands in `intra_footprint`, NOT hard — placement
cannot fix a rigid part's own pad spacing, exactly the design's bucket (b).

### Test suite

`packages/temper-placer/tests/placer/cp_sat/test_validator_audit.py` — 24
tests, all passing, deterministic:

- **Falsifier** (4): center audit 0 vs validator 4 HARD; solve-level
  `RuntimeError` on a feasible solve with a covered-pair violation; the raise
  counts **1 distinct pair / 4 records** (record inflation fixed); a
  reversed-ordering violation (validator emits (B,A) against constraint
  (A,B)) absorbs into HARD via frozenset membership.
- **Clean placement** (2): both audits pass, `audit.clean is True`, feasible
  solve populates `validator_audit`.
- **Straddler** (2): own-pad boundary straddle → `intra_footprint` (4
  records), never hard, solve does not raise.
- **Coverage gap** (1): pair excluded by the `component_refs` filter → 4
  `coverage_gaps`, never hard.
- **Geometry trust / ref-set validation** (4): all pads present →
  `geometry_trusted True`; a pad-less component → `geometry_trusted False` +
  `logger.error` (with `pairs_origin_modelled > 0` asserted); empty placement
  → `ValueError`; solved refs disjoint from placement refs → `ValueError`.
- **Position frame** (5): overlay/keep-base semantics; non-quadrant base
  OVERLAID when the solve touched the ref (solved pos + rotation idx → 90.0);
  base kept exactly when the ref has a solved position but no rotation entry
  (45.0); base kept when untouched; pad fallback from netlist.
- **Wiring** (5): feasible solve populates audit; absent input → None;
  missing `placement`/`voltage_domains` → ValueError; infeasible solve with
  `validator_input` → WARNING logged (caplog), `validator_audit` None.
- **Production** (1): the table above.

Gates (all run in the worktree):

| gate | result |
|---|---|
| `ruff check` (touched files) | clean |
| `import_linter_gate.py` | PASSED — 0 new violations |
| `test_validator_audit.py` + `test_domain_clearance.py` + `test_fixed_copper.py` + `tests/requirements/safety/` | **171 passed, 2 failed** — the 2 failures (`test_temper_board_clearance_compliance`, `test_the_seven_known_intra_footprint_blockers_are_now_visible`) are pre-existing on origin/main, reproduced on a scratch origin/main worktree at `f20400709` with the same venv (board-state-dependent: K3-intra remaining, K2's intra resolved by the #579 move); byte-identical inputs (`pcb/`, `tests/requirements/safety/`, `requirements/`) between origin/main and this branch |
| full `tests/placer/cp_sat/` suite | **609 passed, 1 skipped, 1 xfailed, 1 failed** — the 1 failure is the documented pre-existing `test_checker_copper_distance_is_lower_bound_on_origin_distance` (failing identically on origin/main per `docs/evidence/2026-08-01-edge-hanging-refs-fix.md`). The previously-recorded second failure (`test_courtyard_clearance_strict_in_expansion`) **passes** in this session's re-measurement: that test asserts against the `temper-constraints` Rust extension, and this session ran `make extensions` first (the earlier doc's run measured against a stale installed `.so` — the exact "green tests are not evidence the extension was rebuilt" trap, AGENTS.md) |

## 8. After gap 2 lands (per the handoff)

**Status (amended after adversarial review):** the audit *machinery* ships
in this change — `validator_audit.py`, its test suite, and the
`validator_input` wiring inside `solve_placement` itself. It is **NOT yet
wired at any production caller**: `clearance_repair.py` (the repair loop's
`solve_placement` call, ~line 293) and `cli/__init__.py`'s optimize command
(~line 628) do not pass `validator_input`, so today the audit runs only via
explicit `validator_input` callers and the test suite. That production-caller
wiring is the explicitly-staged next step — this section's re-solve — and
lands with it as an issue #523 follow-up, not here (the scoped solve is
currently infeasible on the box-bar wall, so the audit would never fire
there anyway).

Re-run the scoped solve (FREE {K3, C27}, production repair recipe,
polygon-exact zones now on main) with `validator_input` from the real board
and gate-verify the candidate: REQ-SAFE-01 must not exceed 3/1,
`courtyards_overlap` ≤ 11, `shorting_items` ~200, the 4 consistency gates.
A validator-clean solve may exist where the box-bar solve says none does
(the exact-copper bar is looser than the box bar); if the scoped solve is
still infeasible against the validator audit, the remaining options are the
documented (a) milled isolation slot, (b) #517-style full re-layout, (c)
PD2/8.0mm validator-side reconciliation — a human decision per handoff §4.

## 9. Adversarial-review amendments (this change)

Findings from the review of the original gap-2 ship, all landed here:

| finding | fix |
|---|---|
| 2 — vacuous-clean under pad-geometry / ref-set drift | `stats` + `geometry_trusted` on the audit result; `logger.error` + `geometry_trusted=False` when any component lacks pads or any pair is measured origin-to-origin; `ValueError` on zero-component or ref-disjoint placements (see §3) |
| 3 — rotation overlay discriminator (latent) | a ref the solve touched (solved position + rotation index) gets `idx*90` overlaid unconditionally — the CLI writes it to the PCB; base rotation kept only when absent from `resolved_rotations` (see §5) |
| 4 — silent skip on non-optimal status | `logger.warning` when `validator_input` is given but the solve did not terminate (see §6) |
| 5 — raise message inflates pair counts | distinct-pair count (frozenset-deduped) as headline, record count in parentheses (see §6) |
| 6 — reversed-pair absorption unpinned | test: validator (B,A) vs constraint (A,B) → HARD (see §7) |
