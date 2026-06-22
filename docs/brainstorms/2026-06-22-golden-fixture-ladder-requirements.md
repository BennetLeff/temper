---
date: 2026-06-22
topic: golden-fixture-ladder
focus: Per-seam DSN/SES parity testing via committed golden fixtures that gate every PR through CI diff comparison
origin: docs/ideation/2026-06-22-pipeline-strangler-decomposition-ideation.md
status: active
actors: pipeline developer, CI system
---

# Golden Fixture Ladder — Per-Seam Parity Testing as Strangler Safety Net

## Summary

Commit golden DSN/SES fixtures at every pipeline stage boundary for canonical test boards. CI diffs old-vs-new stage output on every PR with geometric tolerance thresholds. Automates Fowler's strangler parity-test pattern — replace a stage → run → compare → gate — making each extraction self-certifying: if the new stage's output matches the golden, the stage is safe to deploy. The ladder grows incrementally as new test boards are added.

## Problem Frame

Temper has three overlapping PCB design automation pipeline systems (PipelineOrchestrator 8-phase monolith, RouterV6Pipeline 5-stage, DeterministicPipeline 26 stages) currently being decomposed via strangler fig adapters under the active Pipeline Gap plan. The closure test (`parse → place → route → DRC`) is the only integration gate, but it operates only at pipeline endpoints — an extracted stage can silently diverge from the monolith's behavior at intermediate seams and the divergence is only discovered at the final DRC step, requiring backward tracing through 8+ phases.

The strangler fig pattern explicitly requires parity testing at each seam: wrap the monolith at stage boundaries, run both old and new implementations on the same inputs, and compare outputs before deployment. Without per-seam golden fixtures, every stage extraction is a gamble. The existing `temper-testing/golden.py` module provides snapshot testing infrastructure but operates on generic JSON — it lacks geometric tolerance thresholds for DSN coordinate comparison, stage-boundary registration, and CI-integrated diff-on-PR gating.

## Actors

- **A1. Pipeline developer** — extracts or rewrites a pipeline stage; generates golden fixtures from the monolith's output at that stage boundary; runs the diff gate locally to verify parity before pushing
- **A2. CI system** — on every PR, runs each canonical board through both the monolith (to compare) and the modified pipeline; diffs stage outputs against committed golden fixtures; fails the PR on divergence beyond tolerance thresholds

## Key Flows

- **F1. Initial golden generation.** A1 runs `temper golden generate --stage <stage_name> --board <board_id>` which executes the current monolith pipeline up to the designated stage boundary on the canonical board, serializes the stage output as DSN (or SES, for routing stages), and writes it to `power_pcb_dataset/goldens/<board_id>/<stage_name>.dsn`. A manifest entry is added. The file is committed to the repo.

- **F2. Per-PR diff gate.** On every PR, CI runs `temper golden check --board <board_id>` which executes the pipeline up to each registered stage boundary, serializes intermediate outputs to temp files, diffs against the committed golden fixtures, and reports any divergences. The check must pass (all goldens match within tolerance) for the PR to merge.

- **F3. Intentional golden regeneration.** When the monolith intentionally changes (e.g., parameter tuning, algorithm replacement), A1 runs `temper golden regenerate --stage <stage_name> --board <board_id>` to overwrite the committed golden with the new monolith output. The regeneration is committed in the same PR as the monolith change so the diff gate sees zero divergence.

- **F4. Ladder growth.** When a new canonical test board is added to the manifest, A1 runs `temper golden generate --board <new_board_id> --all-stages` to populate goldens for all registered stage boundaries. The new board and its goldens are committed together.

- **F5. Local parity verification.** Before pushing, A1 runs `temper golden check --stage <stage_name>` to verify the extracted stage produces output matching the monolith's golden. This is the inner loop of strangler replacement — iterate locally until parity, then open the PR with confidence.

## Requirements

### Stage Boundary Registration

- **R1. Stage boundary registry.** A manifest file `power_pcb_dataset/stage_boundaries.yaml` declares stage boundaries by name with the pipeline class, stage index or name, output format (DSN or SES), and the serialization function. The DeterministicPipeline's 26 stages are registered first (highest ROI due to immutable BoardState); the PipelineOrchestrator's 8 phases and RouterV6Pipeline's 5 stages follow.

- **R2. Output format per boundary.** Each stage boundary declares whether its golden is serialized as DSN (for structural/placement stages) or SES (for routing stages). The format matches the DSN/SES universal seam established in ideation #1. DSN captures board geometry, component placements, and net definitions. SES captures routed traces, vias, and completion metadata.

- **R3. Serialization function interface.** Each registered boundary provides a serialization callable `(BoardState | StageOutput) → str` that produces deterministic, diffable DSN/SES text (or JSON for analysis-data boundaries). Functions live in `temper_placer.io.golden_serializers` and are registered by name in the stage boundary manifest. Deterministic output is enforced — no timestamps, no memory addresses, no non-deterministic iteration counts. v1 supports three serialization targets: `BoardState` (DeterministicPipeline stages), `StageOutput` dataclasses (RouterV6 Stage2–4), and `PipelineState` (PipelineOrchestrator phases, via adapter that snapshots mutable state to a serializable dict).

### Golden Fixture Generation

- **R4. Generation CLI.** `temper golden generate` accepts `--stage <name>` and `--board <id>` (or `--all-boards`). It runs the monolith pipeline to the designated stage boundary on the target board, serializes the output via the registered serialization function, and writes to `power_pcb_dataset/goldens/<board_id>/<stage_name>.<ext>` where `<ext>` is `dsn` or `ses`.

- **R5. Golden fixture directory structure.** Goldens live under `power_pcb_dataset/goldens/<board_id>/` with one file per stage boundary. A `goldens/`-level `manifest.yaml` records each fixture's board, stage, pipeline, git commit hash at generation time, and format version. This manifest is the single source of truth for which fixtures exist.

- **R6. Generation is reproducible (same code, same machine).** Given the same monolith code, same board, and same seed, repeated `temper golden generate` invocations produce byte-identical golden files on the same machine. The serialization layer ensures floating-point formatting is pinned (`{:.6f}`), hashmap iteration order is deterministic, and no non-semantic data (timestamps, memory addresses, JAX PRNG state) leaks into output. Cross-machine floating-point variance up to `1e-6 mm` is handled by R8's tolerance threshold — this is a separate concern handled at diff time, not generation time.

### CI Diff Gate

- **R7. CI check command.** `temper golden check` (the same subcommand usable locally) runs all stage boundaries for all boards in the manifest. For each (board, stage) pair, it executes the current pipeline to that stage, serializes output, diffs against the committed golden, and reports pass/fail. Exit code 0 if all goldens match within tolerance; non-zero otherwise.

- **R8. Geometric tolerance thresholds.** Floating-point coordinate comparisons use a configurable tolerance (default: `1e-3 mm` for DSN positions, `1e-6 mm` for SES trace coordinates). Tolerance is per-stage-boundary and declared in `stage_boundaries.yaml`. Differences within tolerance are not reported. The tolerance accounts for the fact that small floating-point shifts in coordinate arithmetic are not semantic regressions.

- **R9. PR-blocking gate.** The CI workflow at `.github/workflows/golden-check.yml` runs `temper golden check` and fails the PR check if any fixture diverges. The check output includes a human-readable diff per failing (board, stage) pair. The gate is **required** — branch protection rules enforce it.

- **R10. Golden check is not in the hot path for local development.** Running the full ladder (all boards, all stages) may take minutes. `temper golden check --stage <name> --board <id>` allows developers to check only the stage they are modifying.

### Diff Reporting

- **R11. Structured failure report.** When goldens diverge, the output identifies: (a) which board, (b) which stage, (c) which net(s) diverged, (d) the nature of the divergence (missing net, added net, coordinate shift, trace count difference), and (e) the magnitude (max coordinate delta, net count delta). The report is emitted as both human-readable text and machine-parseable JSON for CI annotation.

- **R12. Diff tolerance triage.** The report categorizes divergences into BINARY (exact mismatch), WITHIN_TOLERANCE (difference ≤ threshold, informational only), and BEYOND_TOLERANCE (difference > threshold, gate-failing). Only BEYOND_TOLERANCE causes gate failure. WITHIN_TOLERANCE entries are informational and visible in CI logs.

### Golden Fixture Versioning

- **R13. Intentional regeneration requires the commit.** When golden fixtures are regenerated, the regeneration commit is part of the same PR that changes the monolith. The golden manifest records the git commit hash at generation time for audit. A CI check verifies that every committed golden was generated from a commit that is an ancestor of the PR HEAD — preventing goldens from being regenerated on an unrelated branch and merged separately.

- **R14. Format versioning.** The golden manifest includes a `format_version` field (starting at 1). If the DSN/SES serialization format changes, the version is incremented. CI rejects goldens whose format version does not match the current tooling version, forcing a regeneration. This prevents silent format drift where old goldens compare against new output in a different format.

### Fixture Selection Strategy

- **R15. Canonical board manifest.** `power_pcb_dataset/golden_manifest.yaml` (existing file, extended) declares the canonical test boards included in the golden ladder. Each entry records the board ID, `.kicad_pcb` path, description, and which stage boundaries are applicable (not all stages apply to all boards — e.g., boards without fine-pitch components skip the FinePitchEscape stage).

- **R16. Minimum canonical set.** The initial golden ladder includes at minimum the `temper_placed` board (already in the manifest) plus two additional boards that stress different pipeline paths: one minimal board (few components, few nets — fast CI) and one complex board (many components, dense routing — exercises the full pipeline). Boards that stress variant geometries (mixed SMD/through-hole, high pin count, multiple layers) are candidates for future ladder rungs.

- **R17. Board variant handling.** Boards that share a common base design but differ in variants (e.g., populated vs unpopulated) share a board ID with a `variant` field. Golden fixtures are per-(board, variant) pair. The CI check runs all declared variants.

### Incremental Ladder Growth

- **R18. New board addition is non-breaking.** Adding a board to `golden_manifest.yaml` and generating its goldens does not affect existing fixtures. The CI check runs the new board alongside existing ones. A board can be added in its own PR without modifying any pipeline code.

- **R19. Stage boundary addition is non-breaking.** Adding a new stage boundary to `stage_boundaries.yaml` does not invalidate existing goldens. New boundaries generate goldens for all existing boards. The CI check expands to include the new boundary.

- **R20. Ladder growth is tracked in the golden manifest.** The manifest records the commit hash at which each (board, stage) fixture was first added. The commit timeline serves as an audit trail of ladder growth.

## Acceptance Examples

- **AE1. First golden generation.** Given a fresh checkout with no goldens, running `temper golden generate --stage apply_placements --board temper_placed` executes DeterministicPipeline up to `ApplyPlacementsStage`, serializes the `BoardState` as DSN, and writes `power_pcb_dataset/goldens/temper_placed/apply_placements.dsn`. The golden manifest gains an entry with the current commit hash.

- **AE2. Parity passes on identical code.** Given goldens generated from the current monolith, running `temper golden check` exits 0 with output: `OK: 3 boards × 5 stages = 15 fixtures matched`.

- **AE3. Parity fails on stage divergence.** Given an extracted `ApplyPlacementsStage` that shifts component `Q1` by 2.0 mm (beyond the 0.001 mm tolerance), running `temper golden check --stage apply_placements --board temper_placed` exits non-zero with output: `FAIL: temper_placed/apply_placements — net "HV_IN", component "Q1" X coordinate 12.500 != 10.500 (delta=+2.000mm, BEYOND_TOLERANCE)`.

- **AE4. Tolerance bypasses noise.** Given the same stage produces a coordinate `10.500001` where the golden has `10.500000` (delta = 0.000001 mm, within 0.001 mm tolerance), the check reports a WITHIN_TOLERANCE notice and exits 0.

- **AE5. Intentional regeneration flow.** A1 changes the placement algorithm and runs `temper golden regenerate --stage apply_placements --board temper_placed`. The golden is overwritten. `temper golden check` now passes. The regeneration and algorithm change are in the same PR. CI accepts the PR.

- **AE6. New board addition.** A1 adds `minimal_board` to `golden_manifest.yaml`, runs `temper golden generate --board minimal_board --all-stages`, and commits. A separate PR modifies a stage; CI golden check verifies parity on all boards including the new one.

- **AE7. Format version bump.** The serialization format changes from `format_version: 1` to `format_version: 2`. All existing goldens now fail CI with `MISMATCH: format version 1 != 2 — regenerate goldens`. A1 regenerates all goldens and commits in the same PR.

## Success Criteria

- **SC1.** Every pipeline stage extraction under the strangler fig plan is gated by a golden fixture parity check that runs in CI — no extraction merges without passing.
- **SC2.** Golden fixtures cover a minimum of 3 canonical boards × 5 stage boundaries (15 fixtures) initially, growing to full stage-boundary coverage as the pipeline decomposition progresses.
- **SC3.** The golden check completes in under 5 minutes for the initial fixture set on CI hardware (minimal board fast path: <30 seconds).
- **SC4.** Intentional monolith changes can regenerate goldens within the same PR without breaking the developer workflow — regeneration takes <2 minutes for all fixtures.
- **SC5.** The diff report enables a developer unfamiliar with the changed code to identify which stage, which net, and by how much an output diverged — within 30 seconds of reading the CI failure log.

## Scope Boundaries

### In scope
- Stage-boundary golden fixture generation, storage, and CI-integrated diff gating
- Geometric tolerance thresholds for DSN coordinate comparison
- Structured failure reporting (board, stage, net, delta, triage category)
- Golden fixture versioning and format version enforcement
- Incremental manifest growth (new boards, new stage boundaries)
- Per-stage-boundary serialization functions for DeterministicPipeline stages (primary consumer)
- PipelineOrchestrator and RouterV6Pipeline stage boundaries (follow-on registrations)

### Deferred for later
- **Property-based testing integration.** Golden fixtures verify point-output parity; PBT verifies invariant properties (connectivity, clearance) across generated inputs. This is covered by ideation #6 (Per-Stage DRC Fence).
- **Full-board DSN round-trip verification.** Verifying that a DSN file can be re-imported and produce identical behavior to the original KiCad PCB is valuable but orthogonal — this is about stage-output parity, not format round-trip fidelity.
- **Million-design regression corpus.** Ideation #14 explicitly rejects this as too expensive as a first move — golden fixtures are the focused starting point.
- **Differential oracle across board variants.** Covered by the golden fixture check running on all declared variants (R17) — comparing variant A's stage output to variant B's is a separate, higher-order oracle not needed for strangler safety.

### Outside this product's identity
- The DSN/SES serialization layer (ideation #1) is a dependency, not part of this work. This work consumes the serialization interface.
- The strangler fig adapters themselves (Pipeline Gap plan, RouterV6 decomposition) are separate workstreams — golden fixtures are the safety net for those workstreams.
- Changes to the closure test's pass/fail criteria or the DRC ceiling mechanism — the golden ladder gates per-stage parity; the closure test gates end-to-end integration.

## Key Decisions

- **K1. DSN/SES as the golden format.** JSON snapshots (as in the existing `temper-testing/golden.py`) are generic but not EDA-aware — they don't understand that geometric coordinates can differ by floating-point epsilon while being semantically identical. DSN/SES with geometric tolerance diffing is purpose-built for PCB pipeline parity testing. JSON snapshots remain available for non-geometric data (e.g., netlist hashes, stage metadata).

- **K2. Per-coordinate tolerance, not semantic equivalence.** The diff operates on coordinate-level comparison with configurable tolerances, not on semantic equivalence (e.g., "these two traces are topologically identical even though their coordinate sequences differ"). Semantic equivalence is a harder problem (graph isomorphism on routed nets) and is unnecessary for the strangler safety net — if a replacement stage produces byte-identical or near-identical coordinates, it is safe. If it produces topologically equivalent but geometrically different routes, that is a meaningful change worth human review.

- **K3. DeterministicPipeline stages first.** The DeterministicPipeline's `Stage.run(state: BoardState) → BoardState` interface with immutable state is the cleanest boundary for golden fixture generation. The 26 stages cover placement, routing, validation, and refinement. The PipelineOrchestrator's monolithic methods (60–100 lines each, no clean intermediate state) are registered after refactoring them to expose stage boundaries. The RouterV6Pipeline's `StageOutput` dataclasses (Stage2–4) are registered in parallel.

- **K4. Golden files are committed to the repo.** Goldens are small (<100 KB per DSN file for typical boards, <1 MB for SES), so committing them avoids external artifact storage complexity. They live alongside the board manifest in `power_pcb_dataset/goldens/`. The repo grows by a few MB even with dozens of boards — acceptable. Git LFS is not introduced for this.

- **K5. CI uses the monolith for parity, not a previous golden.** The golden check runs the _current_ pipeline code (including any in-progress changes) and compares to the _committed_ golden. This means the golden is the snapshot of truth, and the PR's code is the candidate. When the monolith intentionally changes, the golden is regenerated and committed alongside the change so the diff is zero. This is the standard strangler parity-test pattern — the golden is the monolith's certified output.

## Dependencies / Assumptions

### Dependencies
- **Ideation #1 (DSN/SES universal seam).** The golden fixtures depend on the DSN/SES serialization layer. Without standardized intermediate formats, the diff gate has no stable representation to compare. The serialization interface (`BoardState → str` producing DSN/SES text) must exist before golden fixtures can be generated.
- **`temper-testing/golden.py` (existing).** The existing snapshot testing module provides the comparison infrastructure (JSON diff, tolerance, `TEMPER_UPDATE_GOLDEN` env var). The golden ladder extends this for DSN-specific geometric diffing rather than replacing it.
- **`power_pcb_dataset/golden_manifest.yaml` (existing).** Extended with stage boundary references. The existing board registry is the foundation for fixture generation.
- **DeterministicPipeline stages (existing).** The 26 `Stage.run(state) → state` implementations in `packages/temper-placer/src/temper_placer/deterministic/stages/` are the primary fixture sources.
- **Pipeline Gap plan (active).** The `benders_placement` and `route_pcb` adapters wrapping the monolith are consumer #1 of golden fixtures — the first stage extractions gated by golden parity.

### Assumptions
1. DSN/SES serialization is deterministic — given the same board state, the output is byte-identical across runs. Floating-point formatting is pinned to a fixed precision.
2. The DeterministicPipeline's `BoardState` (frozen dataclass) is fully serializable to DSN/SES without information loss. KiCad-specific features (zone fills, custom pad shapes, 3D models) that DSN cannot represent are not needed for parity testing — netlist, component positions, and route geometry are sufficient.
3. Three canonical boards (simple, placed, complex) exercise enough pipeline variance to catch the majority of extraction regressions. More boards are added as regressions specific to unrepresented board features are discovered.
4. A single `temper golden` CLI subcommand (registered under the existing `temper_placer.cli` entry points) is sufficient — golden generation and checking are development/CI workflows, not end-user features.
5. CI hardware has sufficient resources to run the full monolith pipeline on 3 boards (the pipeline is CPU-only after JAX config; wall clock is minutes, not hours).

## Outstanding Questions

- **OQ1 [Affects R8][Technical].** What is the right default geometric tolerance for DSN coordinate comparison? `1e-3 mm` (1 micron) is the current strawman — tight enough to catch real coordinate drift but loose enough to absorb floating-point noise from repeated affine transforms. Should this be validated against actual floating-point noise measured from repeated monolith runs on the same board?

- **OQ2 [Affects R1][Design].** Which stage boundaries are registered first? The ideation suggests DeterministicPipeline stages first, but within the 26 stages, some are more strategic than others. Candidate first-registrations: `ApplyPlacementsStage` (placement boundary — gates the place→route seam), `ClearanceGridStage` (pre-routing geometry), `SequentialRoutingStage` (post-routing). Exact prioritization is a planning deliverable.

- **OQ3 [Affects R5][Design].** Should the golden manifest be a single file (`goldens/manifest.yaml`) or distributed per-stage (one `manifest.yaml` per board directory)? Single file is simpler for CI to parse atomically; distributed is more resilient to merge conflicts when multiple st ages are being regenerated in different PRs.

- **OQ4 [Affects R16][Policy].** What are the specific canonical boards beyond `temper_placed`? Candidates include a minimal board (test fixture, <10 components) and a complex board (dense routing, multi-layer). The existing test fixtures (`medium_board.kicad_pcb`, `minimal_board.kicad_pcb`) referenced in `tests/integration/test_pipeline_gap.py` are the leading candidates — are these real boards or synthetic test fixtures, and do they exercise meaningful pipeline diversity?

- **OQ5 [Affects R7][Technical][Resolved]** When a PR intentionally changes monolith output, golden fixtures must be regenerated and committed in the same PR. The regeneration commit carries an `--intentional` flag that embeds a token in the golden manifest (`regenerated: true, pr: <number>`). CI golden check reads the manifest: if the fixture has `regenerated: true` and the regeneration commit is in the same PR, the check passes despite fixture divergence. This avoids the two-commit problem while preventing abuse — the flag only works for fixtures whose regeneration commit is an ancestor of the PR HEAD and whose manifest format version matches.

- **OQ6 [Affects R3][Technical].** The `BoardState` frozen dataclass in DeterministicPipeline carries trace geometry as numpy arrays (`positions: ndarray`, `routes: list[ndarray]`). DSN serialization of numpy arrays requires stable formatting — should the serializer use `numpy.savetxt` with a fixed format string, or a custom writer that guarantees no scientific-notation floating under the tolerance threshold?

- **OQ7 [Affects R15][Policy].** When a new canonical board is added to the manifest, who decides it is "canonical"? The ladder grows organically as regressions are discovered on boards not in the golden set — is there a formal process (ticket + review) or informal (developer adds a board that caught a real regression)?
