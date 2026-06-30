---
type: feat
origin: docs/brainstorms/2026-06-30-4-layer-enforcement-requirements.md
status: active
date: 2026-06-30
---

# 4-Layer Board Enforcement

## Summary

Remove the 2-layer production path from the placer, add layer-count invariants at Board construction, pipeline stages, and KiCad output, add property tests and a CI gate verifying every pipeline output has exactly 4 canonical layers, and add professional stackup validation checks (copper symmetry, return-path adjacency for differential nets, controlled-impedance specification, copper balance).

---

## Problem Frame

The Temper board is specified as a 4-layer design with inner ground and power planes. The placer fully supports 4-layer boards and `default_4layer()` is used everywhere. However, `default_2layer()` exists as a production API, and `TWO_LAYER_MAP` in the KiCad exporter dynamically selects between 2-layer and 4-layer output based on template PCB content. Nothing in the codebase prevents a Board from being created with a 2-layer stackup, and if one is, the generated `.kicad_pcb` would silently contain only two copper layers — passing all checks but electrically broken.

This plan hardens the 4-layer requirement end-to-end: model, pipeline, output, tests, and CI.

---

## Implementation Units

### U1. Remove 2-layer production path

- **Goal:** Delete `default_2layer()` and `TWO_LAYER_MAP`, hardcode the 4-layer layer map in the KiCad exporter, and provide a scoped test-only helper.
- **Requirements:** R1, R2
- **Dependencies:** None
- **Files:**
  - `packages/temper-placer/src/temper_placer/core/board.py` — remove `default_2layer()` (line 272-280), replace with `_test_only_2layer()`
  - `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` — remove `TWO_LAYER_MAP` (line 38-41), hardcode `DEFAULT_LAYER_MAP` as the only map
  - `tests/manual/test_drc_1_isolation_standalone.py` — update standalone `default_2layer()` reference
- **Approach:**
  - `default_2layer()` has zero production callers (grep confirmed). Replace with `_test_only_2layer()` — same body with a docstring noting test-only use and a `DeprecationWarning`.
  - In `kicad_exporter.py`, remove the `TWO_LAYER_MAP` dictionary and the dynamic layer-map selection logic (~line 452-459). Always use `DEFAULT_LAYER_MAP` (the 4-layer map).
  - The manual test file defines its own `default_2layer()` — update the copy there to `_test_only_2layer()` for consistency.
- **Patterns to follow:** `_test_only_*` naming convention for test-scoped helpers.
- **Test scenarios:**
  - `_test_only_2layer()` produces a 2-layer `LayerStackup` with F.Cu and B.Cu only.
  - KiCad exporter always writes 4 copper layers regardless of template content.
  - No `default_2layer` name remains in the public API surface (import fails or produces deprecation warning).
- **Verification:** `uv run pytest tests/core/test_board.py -k "4layer"` — existing default_4layer tests pass unchanged. Grep for `default_2layer` and `TWO_LAYER_MAP` returns zero production matches.

---

### U2. Add layer-count invariant at LayerStackup and Board construction

- **Goal:** `LayerStackup` and `Board` reject non-4-layer stackups at construction time with a clear error message.
- **Requirements:** R1, R3
- **Dependencies:** U1
- **Files:**
  - `packages/temper-placer/src/temper_placer/core/board.py` — add `__post_init__` to `LayerStackup`; enhance `Board.__post_init__`
  - `packages/temper-placer/tests/core/test_board.py` — add invariant tests
- **Approach:**
  - Add a `CANONICAL_4LAYER_LAYER_NAMES` set derived from `STANDARD_LAYER_ORDER` + `LAYER_NAME_TO_IDX`: `frozenset({"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"})`.
  - `LayerStackup.__post_init__`: assert `len(self.layers) == 4` and every layer name is in the canonical set. Raise `ValueError` with the expected vs actual layer names on mismatch.
  - `Board.__post_init__`: after the existing `default_4layer()` fallback, validate `self.layer_stackup` against the canonical set. This catches manually-constructed `LayerStackup`s with wrong layers.
- **Patterns to follow:** The existing `Board.__post_init__` pattern (lines 437-441). `LayerStackup` already validates nothing — use same dataclass post-init approach.
- **Test scenarios:**
  - Construction with `default_4layer()` succeeds.
  - Construction with 4 layers having correct KiCad names (F.Cu, In1.Cu, In2.Cu, B.Cu) succeeds.
  - Construction with 2 layers raises `ValueError` mentioning the missing inner layers.
  - Construction with 4 layers but wrong names (e.g., "Top", "GND", "PWR", "Bottom") raises `ValueError`.
  - Construction with 6 layers raises `ValueError`.
  - `_test_only_2layer()` construction bypasses the invariant (its scope is test-only and must not be blocked).
- **Verification:** `uv run pytest tests/core/test_board.py -k "layer_count or stackup"` — invariant test passes, all existing tests still pass.

---

### U3. Add per-stage pipeline fence invariant for 4 layers

- **Goal:** Pipeline stages that consume a `BoardState` validate 4-layer stackup before processing, using the existing per-stage DRC fence pattern.
- **Requirements:** R5
- **Dependencies:** U2
- **Files:**
  - `packages/temper-placer/src/temper_placer/pipeline/stages/preflight_stage.py` — add `InvariantSpec` for layer count
  - `packages/temper-placer/src/temper_placer/pipeline/state.py` — verify `BoardState` already carries layer info
- **Approach:**
  - Per `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`, each `Stage` subclass can declare invariants via an `invariants` property. Add an `InvariantSpec(name="stackup_has_4_copper_layers", check=...)` that verifies `len(board_state.layers) == 4` and the names match the canonical set.
  - The preflight stage is the natural insertion point — it already runs feasibility checks before optimization. Add the invariant there.
  - If `BoardState` immutability is already enforced (frozen dataclass per strangler-fig learnings), per-stage re-validation is lightweight — the invariant is cheap. If immutability is confirmed, R5 can be satisfied with preflight-only validation rather than per-stage.
- **Patterns to follow:** `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — InvariantSpec declaration and auto-discovery.
- **Test scenarios:**
  - Pipeline run with canonical 4-layer board passes the preflight invariant.
  - Pipeline run with a non-canonical stackup (if somehow constructed) fails at preflight with an attributed error naming the invariant.
  - Existing pipeline integration tests pass unchanged (canonical board already used everywhere).
- **Verification:** `uv run pytest tests/ -k "preflight"` — pipeline tests pass with the new invariant active.

---

### U4. Add KiCad writer output validation

- **Goal:** The KiCad file writer validates that the output contains exactly 4 copper layers with canonical names before writing.
- **Requirements:** R4
- **Dependencies:** U2
- **Files:**
  - `packages/temper-placer/src/temper_placer/io/kicad_exporter.py` — add pre-write validation in `export_board_state()` and `export_routed_pcb()`
  - `packages/temper-placer/src/temper_placer/io/kicad_writer.py` — add validation in `write_placements_to_pcb()`
- **Approach:**
  - After U1 removes `TWO_LAYER_MAP` and hardcodes the 4-layer map, the exporter already always writes 4 layers. Add an explicit assertion as a safety net: `assert len(ki_board.layers) == 4 and all(l.name in CANONICAL_4LAYER_LAYER_NAMES for l in ki_board.layers)` before `ki_board.to_file()`.
  - In `kicad_writer.py`, validate layer count when constructing the KiCad board representation.
  - Raise `RuntimeError` with diagnostic info (actual layer count and names) on mismatch.
- **Patterns to follow:** Existing assertion patterns in the export pipeline; `CANONICAL_4LAYER_LAYER_NAMES` from U2.
- **Test scenarios:**
  - Calling `export_board_state()` with a valid 4-layer board writes a .kicad_pcb with `(0 "F.Cu" ...) (1 "In1.Cu" ...) (2 "In2.Cu" ...) (31 "B.Cu" ...)`.
  - Calling with a non-4-layer board state raises `RuntimeError` before any file is written.
- **Verification:** `uv run pytest tests/io/test_kicad_exporter.py` — existing export tests pass with the new validation active.

---

### U5. Add property tests for 4-layer output

- **Goal:** Hypothesis property tests verify that for any valid pipeline input, the generated `.kicad_pcb` contains exactly 4 copper layers with canonical names.
- **Requirements:** R6
- **Dependencies:** U2, U4
- **Files:**
  - `packages/temper-placer/tests/io/io_property_strategies.py` — add `four_layer_board_state()` composite strategy
  - `packages/temper-placer/tests/io/test_4layer_output_properties.py` — new theorem-class property test file
- **Approach:**
  - Follow the established pattern from `tests/io/test_io_invariants_pbt.py` (theorem/lemma structure) and `tests/router_v6/test_copper_balance_properties.py` (closest DFM analog).
  - Build a composite `@st.composite` strategy that generates a valid `BoardState` with canonical layers, feeds it through the export pipeline (or a minimal export path), writes to a temp `.kicad_pcb`, re-parses with `kiutils.KiBoard.from_file()`, and returns the parsed board.
  - Theorem: "Stackup Correctness" — the generated `.kicad_pcb` always has exactly 4 copper layers with names F.Cu, In1.Cu, In2.Cu, B.Cu.
  - Invariants: `len(ki_board.layers) == 4`, `set(l.name for l in ki_board.layers) == {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}`.
  - Use `@settings(max_examples=50, deadline=30000)` — lower than DFM's 200 because export I/O is heavier.
- **Patterns to follow:** `tests/io/test_io_invariants_pbt.py:1-30` (theorem/lemma), `tests/router_v6/test_copper_balance_properties.py:125-153` (R16 layer count invariant), `tests/router_v6/dfm_property_strategies.py` (composite strategies).
- **Test scenarios:**
  - **Covers AE5.** Fuzz pipeline inputs; every generated `.kicad_pcb` is parsed and verified to contain exactly 4 copper layers with canonical names.
  - Property holds across a range of input variations (different component counts, netlists, zone configurations).
- **Verification:** `uv run pytest tests/io/test_4layer_output_properties.py -v` — property holds for all fuzzed inputs.

---

### U6. Add CI gate for .kicad_pcb layer count

- **Goal:** A CI job regenerates the `.kicad_pcb` from spec and diffs against the committed copy. Any layer-count or layer-name deviation fails CI. Additionally, a CI check verifies the committed `.kicad_pcb` has exactly 4 layers as a backstop.
- **Requirements:** R7, R12
- **Dependencies:** U4
- **Files:**
  - `.github/workflows/python-tests.yml` — add CI job for `.kicad_pcb` diff
- **Approach:**
  - **Layer-count check (lives in U5's property test):** Add a CI job that runs U5's property tests — if they pass, the committed PCB has 4 layers.
  - **Regen-diff gate:** Add a CI job following the existing `firmware-tests.yml:33` pattern: regenerate `.kicad_pcb` from spec via `uv run temper-placer ...` (or the appropriate pipeline command), then `git diff --exit-code pcb/temper.kicad_pcb`. If the committed copy drifts from what the pipeline produces, CI fails.
  - **Warnings surface (R12):** Stackup validation warnings from U7 are emitted as CI annotations or a structured report artifact. Add a CI step that runs U7 validation and surfaces results in the PR UI.
- **Patterns to follow:** `firmware-tests.yml:33` (`python3 firmware/tools/gen_config.py && git diff --exit-code firmware/config.h`).
- **Test scenarios:**
  - **Covers AE6.** A commit that changes the `.kicad_pcb` layer count from 4 to 2 fails CI with a diff showing the layer change.
  - A commit that changes a layer name (e.g., "In1.Cu" → "In1.Cu_renamed") fails CI.
  - A commit with no PCB-related changes passes the diff gate.
- **Verification:** Trigger CI on this branch; confirm the gate passes against the current committed 4-layer `.kicad_pcb`.

---

### U7. Add professional stackup validation checks

- **Goal:** Add PCB stackup validation checks that warn on copper asymmetry, return-path adjacency issues for differential nets, missing controlled-impedance specification, and copper density imbalance. Warnings are surfaced via CI annotations.
- **Requirements:** R8, R9, R10, R11, R12
- **Dependencies:** U2 (canonical layer set available)
- **Files:**
  - `packages/temper-placer/src/temper_placer/manufacturing/stackup_validator.py` — new module with validation logic
  - `packages/temper-placer/tests/manufacturing/test_stackup_validator.py` — unit tests for each check
  - `packages/temper-placer/src/temper_placer/pipeline/stages/preflight_stage.py` — wire validator into preflight (or a standalone stage)
- **Approach:**
  - **Audit before build:** Run `git grep` for `copper_symmetry`, `return_path_adjacency`, `controlled_impedance` in `packages/*/src/` to check for pre-existing but unwired validation code, per `docs/solutions/workflow-issues/integration-hunting-audit-before-build-2026-06-28.md`.
  - **Copper symmetry check (R8):** Compute effective copper weight per layer as `layer.copper_weight * estimated_fill_percentage`. Compute imbalance as `(max_eff - min_eff) / total_eff`. Warn if >25% (exact threshold deferred to planning per origin). The current Temper stackup (~22.4%) passes. Note: fill percentage estimation method is deferred to planning.
  - **Return-path adjacency (R9):** For nets in the `Differential` class, check that the layer they route on has an adjacent reference plane. L1 adjacent to L2 (GND) passes. L4 adjacent to L3 (PWR) warns. Non-differential nets are not checked.
  - **Controlled-impedance specification (R10):** Check that the `Differential` net class has a documented target impedance. If absent, warn suggesting 90Ω for USB 2.0. Does not validate the value.
  - **Copper balance check (R11):** Verify copper density across all 4 layers. Warn if `max_fill - min_fill` exceeds a threshold (deferred to planning). Reuses the existing `router_v6/copper_balance.py:analyze_copper_balance()` function rather than building a parallel analysis.
  - **Warning emission:** Each check returns a `StackupValidationResult` with `severity: "warning"`, `message: str`, and `layer: str | None`. Results are surfaced via the pipeline's existing warning reporting channel.
- **Patterns to follow:**
  - Per-layer breakdown preservation: return validation results per-layer, not aggregated boolean. Per `docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md`, aggregation hides which layer violates.
  - `router_v6/copper_balance.py:analyze_copper_balance()` for existing copper density computation.
  - `core/design_rules.py:TEMPER_NET_CLASSES` for `required_layer` and net class definitions.
- **Test scenarios:**
  - **Covers AE7.** Stackup with effective imbalance >25% warns ("Effective copper imbalance detected: L1 at 2oz × 95% fill vs L4 at 0.5oz × 20% fill"). Current Temper stackup passes.
  - **Covers AE8.** Differential net class with traces on L4 warns ("L4 references L3 (PWR plane). Verify return-path quality for differential nets."). Non-differential nets on L4 produce no warning.
  - **Covers AE9.** Missing impedance specification for differential nets warns ("No target impedance specified for differential nets. Expected: 90Ω differential for USB 2.0.").
  - **Covers AE10.** Stackup with one layer at 3% fill and another at 78% fill warns about copper density imbalance. All layers 25-55% fill passes.
  - Each validation check returns per-layer results, not a single boolean.
- **Verification:** `uv run pytest tests/manufacturing/test_stackup_validator.py -v` — all checks produce correct warnings for the trigger conditions. Current Temper config passes without warnings (after impedance spec is added, if needed).

---

## Key Technical Decisions

- **Build on existing SSOT, not a new constant.** The canonical layer names are derived from `STANDARD_LAYER_ORDER` + `LAYER_NAME_TO_IDX` in `core/board.py`. No new `CANONICAL_4LAYER_NAMES` constant — use the existing `LayerIndex` IntEnum (established in `docs/solutions/architecture-patterns/layer-index-ssot-placer-2026-06-23.md`).
- **`_test_only_2layer()` bypasses the invariant.** Test code may legitimately need simplified stackups for focused assertions. The naming convention signals test-only scope. The invariant lives in `LayerStackup`/`Board.__post_init__`, which `_test_only_2layer()` constructs as a `LayerStackup` directly (not via `default_4layer()`).
- **Preflight-only pipeline validation if BoardState is immutable.** Per `docs/solutions/architecture-patterns/strangler-fig-pipeline-decomposition-2026-06-22.md`, `BoardState` is a frozen dataclass — if confirmed, layer count cannot change mid-pipeline. Per-stage re-validation is then redundant. U3 adds the invariant at preflight and verifies immutability during implementation.
- **Stackup validation returns per-layer results, not aggregated.** Per `docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md`, aggregated pass/fail hides which layer violates. Each validation check returns a list of `StackupValidationResult` per layer.
- **2-layer removal is immediate, not behind a feature flag.** `default_2layer()` has zero production callers. A deprecation period adds process overhead with no benefit. The test fixture is renamed synchronously.

---

## Risks & Dependencies

- **Test cardinality breakage.** Removing variable-layer-count assumptions may break existing invariant tests that assume layer count is parameterizable. Audit all tests that iterate over `Layers` or compare against `len(layers)` before landing U2. Per `docs/solutions/test-failures/refactor-breakage-test-imports-stale-references-2026-06-29.md`.
- **BoardState immutability not confirmed.** U3's approach depends on `BoardState` being frozen. If it is mutable in practice, per-stage validation around mutation points may be needed instead. U3 verifies this during implementation.
- **Fill percentage estimation method undefined.** R8's effective copper weight computation depends on `estimated_fill_percentage`, which is not yet defined (pre-routing vs post-routing, global vs per-region). U7 uses a conservative placeholder and defers the exact method to a follow-up.
- **No impedance specification exists today.** R10 warns on missing impedance spec for USB differential pairs. If the spec is added as a one-line comment (`90Ω differential`), the warning resolves. If the spec value is wrong, the check doesn't catch it — R10 only checks existence, not correctness.
- **KiCad version format changes.** The CI diff gate (U6) does a textual diff. KiCad format changes could produce false-positive CI failures. Deferred to planning whether a semantic layer-count diff is warranted.

---

## Scope Boundaries

### Deferred to Follow-Up Work

- Controlled-impedance routing calculations (computing trace width from dielectric height) — R10 only checks spec existence
- Stackup physical redesign (changing copper weights, dielectric thicknesses)
- 6-layer extension
- Via type extensions (blind, buried, microvia)
- The following open questions from the origin document:
  - Effective copper imbalance threshold (U7 uses 25% as illustrative placeholder)
  - Copper balance density threshold
  - Target impedance value for USB differential pairs
  - Return-path adjacency with plane stitching as mitigation
  - Fill percentage estimation method (pre/post-routing, granularity)
  - Semantic vs textual `git diff` for the CI gate
  - BoardState serialization/deserialization guard
  - Impedance spec value validation (vs existence-only check)
