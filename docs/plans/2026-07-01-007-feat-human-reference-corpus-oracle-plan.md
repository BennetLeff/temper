---
title: "feat: Human-Reference Corpus Oracle"
type: feat
status: active
date: 2026-07-01
origin: docs/brainstorms/2026-07-01-human-reference-corpus-oracle-requirements.md
deepened: 2026-07-01
---

# feat: Human-Reference Corpus Oracle

## Summary

A non-blocking PR comment comparing the placer's output on real open-source boards against human-designed reference placement, built correctness-first with per-piece validation at every link in the chain. Shipped in four sequential phases: fix the broken corpus gate, spike the extractor on piantor_right, wire the CI comparison comment, then expand to the full corpus five with routing metrics.

---

## Problem Frame

The project's verification apparatus measures placement quality against itself — goldens check parity, corpus regressions check drift. The 17 real, human-placed-and-routed open-source boards on disk are used only as parse smoke tests. The human reference — competent-human placements and routings sitting in the same KiCad file — is unused.

Compounding this, the existing corpus regression gate is silently broken: four of five baseline metrics are wrong. `extract_corpus_baselines.py` calls a nonexistent function in a swallowed `try/except`, hardcodes `overlap_loss_final` and `boundary_loss_final` to `0.0`, and aliases `wirelength_final` to `final_loss`. The gate's tolerance floor (`margin_abs: 100.0`) absorbs the zero-valued baselines without complaint. Two divergent, untested copies of `baseline_extractor.py` exist, neither exercising the full validation chain. The code has been dead since first commit.

The remedy is a correctness-first rewrite: fix the existing gate, build a single canonical extractor with per-piece validation tests, and surface per-metric ratios as an advisory PR comment — not a new gate. (See origin: docs/brainstorms/2026-07-01-human-reference-corpus-oracle-requirements.md)

---

## Requirements

- R1. One canonical baseline extractor under `src/temper_placer/`; remove the two divergent copies.
- R2. Canonical extractor's public surface is a single function; no dead-import blocks.
- R3. Trace extraction validated against a real board — every trace's net resolves to a named net.
- R4. Via extraction validated against a real board — every via's net resolves to a real net name.
- R5. HPWL computed via `compute_total_hpwl(positions, rotations, context)`; strictly positive assertion on boards with ≥1 multi-component net.
- R6. Overlap loss and boundary loss measured, not hardcoded; positive on fixtures with overlaps/boundary violations.
- R7. Routed length and via count derived from extracted traces; positive on routed boards, zero on unrouted fixtures (expansion phase).
- R8. Human-reference metrics written to `power_pcb_dataset/corpus/{board}/human_reference.yaml` — separate from `baseline.json`.
- R9. `human_reference.yaml` metric values, once committed, are never overwritten. In expansion phases (R14, R15), new metric keys may be added but existing keys are not modified. Bless workflow must not touch it.
- R10. Per-metric ratios (opt / human) surfaced for HPWL, overlap, boundary, RDL, via count, DRC delta; no composite score.
- R11. Comparison posted as sticky PR comment using existing `marocchino/sticky-pull-request-comment@v2`; advisory only.
- R12. Spike covers exactly one board: piantor_right; committed `human_reference.yaml` and passing validation tests.
- R13. After spike, expand to corpus 5; boards whose validation fails are excluded from comment with a note.
- R14. Router-vs-human comparison (RDL, via count, DRC delta) is the expansion phase, not deferred.
- R15. DRC delta computed from validated DRC run; board with nonzero human DRC errors excluded from DRC-delta row (expansion phase).
- R16. Fix `extract_corpus_baselines.py` before spike: correct HPWL call, measure overlap/boundary from breakdown, fix wirelength aliasing, remove silent `try/except`, regenerate baselines.

**Origin actors:** A1 (Maintainer), A2 (Reviewer), A3 (CI runner), A4 (Future planner/implementer)
**Origin flows:** F1 (Baseline extraction — validation-gated), F2 (PR comparison — report-only)
**Origin acceptance examples:** AE1 (piantor_right produces valid HPWL, named nets, no swallowed import), AE2 (overlapping fixture yields positive overlap loss), AE3 (off-board fixture yields positive boundary loss), AE4 (PR gets sticky comment with per-metric ratios, no composite), AE5 (spike shows only piantor_right), AE6 (board validation failure noted in comment, not silent), AE7 (bless touches baseline.json not human_reference.yaml)

---

## Scope Boundaries

- No auto-promotion of the comparison to a CI gate. The comment is advisory; promotion depends on accumulated real-signal runs (future brainstorm).
- No FreeRouting integration as an independent autorouter oracle.
- No topological / graph-isomorphism semantic golden equivalence.
- No mutation testing (mutmut / cosmic-ray) — deferred until this oracle accumulates enough runs.
- No new Kicad board downloads in the spike phase; piantor_right is already on disk.
- No real Z3 / SMT differential oracle.
- No modification to the extra 12 external boards in `tests/fixtures/external/` — corpus 5 only.
- The existing scorecard sticky comment (pr-pipeline-scorecard workflow) is not modified; the human-reference comment uses a distinct header.
- Known-broken window, owned: until U1 lands, the existing corpus gate blesses four wrong metrics on every PR.

---

## Context & Research

### Relevant Code and Patterns

- **`scripts/extract_corpus_baselines.py`** (lines 117-132): the five-bug block — wrong HPWL function name, wrong signature, swallowed `try/except`, hardcoded `0.0` on overlap/boundary, `wirelength_final` aliased to `final_loss`.
- **`packages/temper-placer/src/temper_placer/regression/corpus_runner.py`** (lines 447-472): correctly computes loss breakdown from composite — the pattern to follow for metric extraction. The HPWL computation at lines 467-472 uses the correct function name (`compute_total_hpwl`) with the correct signature, but wraps it in a swallowed `try/except` — the same silent-failure pattern. If `compute_total_hpwl` is renamed or fails, the exception is silently caught and `hpwl_val` stays `0.0`.
- **`packages/temper-placer/src/temper_placer/validation/baseline_extractor.py`**: source-tree extractor — uses `compute_metrics` → `PlacementMetrics`, outputs flat `BaselineMetrics`. Has dead `_check_dependencies` block importing unused losses.
- **`packages/temper-placer/tests/fixtures/external/baseline_extractor.py`**: test-fixture extractor — different schema (nested `human_placement.metrics`), uses `compute_quality_report`, outputs `_benchmark.yaml`. Also dead code.
- **`packages/temper-placer/src/temper_placer/losses/wirelength.py`**: `compute_total_hpwl(positions, rotations, context, alpha=10.0)` — the correct HPWL entrypoint. The nonexistent `compute_hpwl(state, netlist)` is a fabrication.
- **`packages/temper-placer/src/temper_placer/io/kicad_parser.py`**: `_extract_traces_from_pcb` (line 485), `_extract_vias_from_pcb` (line 539) — both resolve nets via `net_map`. Via fallback path uses `str(track.net)` which can produce `<Net object at 0x…>` placeholders.
- **`packages/temper-placer/src/temper_placer/core/pin_geometry.py`**: `pin_world_position(pin, comp)` — SSOT for pin-world-coordinate transforms; must be used for any position comparisons.
- **`packages/temper-placer/src/temper_placer/validation/metrics.py`**: `compute_metrics(state, netlist, board)` → `PlacementMetrics` (overlap_count, boundary_violations, hv_lv_violations, total_wirelength).
- **`.github/workflows/pr-pipeline-scorecard.yml`**: existing sticky comment pattern — `marocchino/sticky-pull-request-comment@v2` with `header: pipeline-scorecard`. Three-job pattern (baseline, current, scorecard).
- **`scripts/bless_baselines.py`** (184 lines): bless workflow — calls `extract_corpus_baselines.py`, shows diffs, requires `Ceiling-Approval:` in commit.
- **`power_pcb_dataset/corpus/manifest.yaml`**: 5 corpus boards — temper, minimal, rp2040_designguide, bitaxe_ultra, piantor_right.
- **`packages/temper-placer/tests/validation/test_placement_comparison.py`** (735 lines): dead test code — reads `human_placement` field from committed baselines that don't populate it; also to be removed per R1.

### Institutional Learnings

- **Corpus rotation-logits boundary regression** (`docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md`): Prior silent-failure — corpus runner passed raw logits instead of softmax to loss functions, producing 250M vs ~0 garbage. Training-time and post-hoc metric evaluation use different data paths; always assert they agree within tolerance.
- **BFS oracle cost-model mismatch** (`docs/solutions/best-practices/bfs-oracle-cost-model-mismatch-astar-validation-2026-06-28.md`): A mismatched oracle produces false confidence. The human-reference oracle must use the same `LossContext`, coordinate conventions, and loss functions as the optimizer.
- **CI-gate quality enforcement** (`docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md`): Five-element pattern for building gates that structurally prevent the `try/except: pass` failure class — mechanical gate, baseline allowlist, hard block, stale-entry enforcement, ticketed exit.
- **Pipeline observability** (`docs/solutions/architecture-patterns/pipeline-observability-observer-cross-validation-pattern-2026-06-29.md`): Three guardrails before every write: schema validation, dual-source cross-validation, canary injection. Integrity checks must halt the write path, not just warn.
- **Pad-position SSOT** (`docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md`): Inline `comp_pos + pin.position` was silently wrong for rotated/bottom-side components. Must use `pin_world_position` from `core/pin_geometry.py`.
- **Golden fixture ladder** (`docs/solutions/best-practices/golden-fixture-ladder-parity-testing-2026-06-22.md`): Closest existing infrastructure to the oracle concept — deterministic serializers, geometric diff engine with tolerance thresholds, CI gate with ancestry check. Follow this architecture.

### External References

- No external research performed — the codebase has extensive existing patterns for metrics computation, CI integration, and validation.

---

## Key Technical Decisions

- **New CI workflow, not extension of existing scorecard.** The human-reference comparison has different triggers (placer/router source + corpus data), different comment content (per-metric ratios vs. time/DRC drift), and a distinct advisory posture. Extending the existing scorecard workflow would couple two different concerns under one header. A new `human-reference-check.yml` with its own `header: corpus-oracle` keeps concerns separate and makes the non-blocking intent explicit.

- **Flat `human_reference.yaml` schema.** Each metric is a top-level key with `value`, `extracted_at`, and `pcb_git_hash`. No nested `human_placement.metrics` dict (as in the test-fixture extractor), no tolerance margins (which belong to the gate, not the reference), and no composite scores. The flat shape is easier to read in PR diffs and avoids the silent-nesting bugs that made the current `baseline.json` structure amenable to mislabeling.

- **Per-board runtime validation inside the comparison step.** When a board's per-piece validation fails (e.g., trace net-name resolution produces a placeholder), the comparison script excludes that board from the comment and notes `validation failed — excluded from comparison`. Failing the CI job for a single-board validation failure would couple the advisory oracle to build status — the same anti-pattern of premature gating the brainstorm explicitly rejects. The excluded board's failure is visible in the comment, not buried in CI logs.

- **Minimal programmatic fixtures for overlap/boundary edge cases.** Two small fixtures (two components placed to overlap; one component placed off-board) constructed in the test file rather than reusing `tests/fixtures/generators/`. The generators produce full boards for optimizer tests; a two-component fixture is simpler, faster, and directly exercises the metrics under test without importing optimizer state infrastructure.

- **Rewrite the extractor rather than patch the divergent copies.** The two existing `baseline_extractor.py` files differ in schema, metric computation path, and output format; neither is tested on real boards. Consolidation into a new canonical module is cleaner than picking one and retrofitting the other's semantics. The rewrite inherits the constraint that no piece of the chain swallows an exception into a recorded metric.

- **Separate `human_reference.yaml` from `baseline.json`.** Different update semantics: baselines are re-blessed on every placer improvement; the human reference is an append-only artifact derived from the downloaded board — existing metric values are never overwritten, though new metric keys may be added in expansion phases. Cohabiting them in one file risks a future bless-script change silently overwriting the human number — the same class of silent-failure bug we are removing.

- **Phased delivery: prerequisite fix → spike → CI wiring → expansion.** R16 must land first so the spike builds on a correct gate. The spike on piantor_right proves the extractor chain end-to-end. CI wiring lands after the extractor is validated to avoid wiring a broken pipeline. Expansion to corpus 5 + routing metrics comes last, blocked on the spike's validation tests passing on `main`.

---

## Open Questions

### Resolved During Planning

- **[Does `_extract_traces_from_pcb` lose net names on corpus 5?]** The `net_map` lookup in `_extract_traces_from_pcb` resolves net IDs to names via the `ki_board.netItems` mapping. The fallback `str(track.net)` path can produce `<Net object at 0x…>` placeholders when both `.name` and `.number` are unset. **Resolution:** The canonical extractor's trace-extraction step asserts every trace resolves to a named net; failure raises. The fallback path in the parser is not modified (it's shared with router-v6), but the extractor validates its output before use.

- **[Is `compute_total_hpwl(positions, rotations, context)` the only HPWL entrypoint?]** Yes. There is no `compute_hpwl(state, netlist)` in the codebase; that function name is a fabrication in `extract_corpus_baselines.py`. The `corpus_runner.py` at lines 467-472 uses the correct function name and signature but wraps the call in a swallowed `try/except` — same silent-failure pattern, different mechanism.

- **[What fields does `human_reference.yaml` contain?]** See Key Technical Decision on flat schema. Placement metrics (spike): `hpwl`, `overlap_loss`, `boundary_loss`. Routing metrics (expansion): `rdl`, `via_count`. DRC (expansion): `drc_violations`. Each metric is a map: `{value: float, extracted_at: iso8601, pcb_git_hash: str}`. Top-level metadata: `board_id`, `extraction_source` (pcb path), `extractor_version`.

- **[What does the PR comment body look like?]** Per the High-Level Technical Design section: one block per board with a header line (`#### {board_id}`), a table with columns Metric / Opt / Human / Ratio, rows for each metric, and a trailing one-line note when metrics were excluded or the board was skipped.

### Deferred to Implementation

- **[How is the overlapping fixture for AE2 produced?]** Two components with bounding boxes that overlap, constructed in the test file using `PlacementState.from_positions`. Exact overlap amount depends on component geometry; tuned during test-writing to produce a clear positive signal (>0 overlap loss at default loss-function parameters).

- **[What are the exact YAML field names in `human_reference.yaml`?]** Settled during implementation; the plan specifies the semantic content and flat shape; exact key names (`hpwl`, `overlap_loss`, `boundary_loss`, `rdl`, `via_count`, `drc_violations`) are directional and may be adjusted for consistency with existing metric naming conventions in the codebase.

- **[Exact tolerance thresholds for metric comparisons?]** The comparison is advisory and ratio-based (opt / human), so no gate thresholds are set. The comment may include a qualitative indicator (e.g., ratio < 1.0 = better than human, > 1.0 = worse) but no pass/fail determination. Exact formatting deferred to implementation.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Extractor: `extract_human_reference(pcb_path) → HumanReference`

```
1. Parse board: parse_result = parse_kicad_pcb(pcb_path)
2. Validate parser output:
   - assert len(parse_result.traces) > 0 (for routed boards)
   - assert every trace.net is a named net (not "<Net object at ...>")
   - assert len(parse_result.vias) > 0 (for routed boards)
   - assert every via._net is a named net
3. Build PlacementState from parse_result.netlist.components:
   - Absolute positions: component.initial_position + board.origin
   - Rotation logits: one-hot at component.initial_rotation % 4
4. Build LossContext from netlist and board geometry
5. Compute HPWL: compute_total_hpwl(positions, rotations, context)
   - Assert isfinite and > 0 for multi-component nets
6. Compute overlap: OverlapLoss()(positions, rotations, context)
   - Assert isfinite
7. Compute boundary: BoundaryLoss()(positions, rotations, context)
   - Assert isfinite
8. (Expansion) Compute routing metrics from traces and vias
9. Write human_reference.yaml
```

### PR comment template

```
## Human-Reference Comparison
*Placer output compared to human-designed placement*

#### piantor_right
| Metric | Opt | Human | Ratio |
|--------|-----|-------|-------|
| HPWL | 12450.3 | 11820.0 | 1.05 |
| Overlap Loss | 0.0 | 0.0 | 1.00 |
| Boundary Loss | 0.0 | 0.12 | 0.00 |
| RDL | — | — | — |
...
> Board `bitaxe_ultra`: validation failed — excluded from comparison (trace net-name resolution produced placeholder)
```

### CI workflow shape

```
Trigger: PRs touching packages/temper-placer/src/** OR power_pcb_dataset/corpus/**
Jobs:
  1. current (checkout PR head → run placer on each board → produce metrics artifact)
  2. comparison (needs [current] → run comparison script against human_reference.yaml → post sticky comment)
```

---

## Implementation Units

### Phase 1: Prerequisite Fix

### U1. Fix `extract_corpus_baselines.py` and regenerate corpus baselines

**Goal:** Close the known-broken window: correct the four-wrong-metrics regime in the existing corpus regression gate before the spike builds on it.

**Requirements:** R16

**Dependencies:** None

**Files:**
- Modify: `scripts/extract_corpus_baselines.py`
- Modify: `packages/temper-placer/src/temper_placer/regression/corpus_runner.py`
- Modify: `power_pcb_dataset/corpus/temper/baseline.json`
- Modify: `power_pcb_dataset/corpus/minimal/baseline.json`
- Modify: `power_pcb_dataset/corpus/rp2040_designguide/baseline.json`
- Modify: `power_pcb_dataset/corpus/bitaxe_ultra/baseline.json`
- Modify: `power_pcb_dataset/corpus/piantor_right/baseline.json`
- Test: `packages/temper-placer/tests/regression/test_corpus_baseline_extraction.py` (new)

**Approach:**
- Replace `compute_hpwl(state, netlist)` with `compute_total_hpwl(positions, rotations, context)` using the correct signature.
- Remove the bare `try: ... except Exception: pass` block; let import or computation failures raise.
- Compute `overlap_loss_final` and `boundary_loss_final` from the composite loss breakdown (following `corpus_runner.py:447-472`).
- Set `wirelength_final` to the wirelength breakdown value, not `final_loss`.
- Also fix the swallowed `try/except` in `corpus_runner.py` lines 467-472: remove the bare `try: ... except Exception: pass` so import or computation failures raise instead of silently setting `hpwl_val = 0.0`. The function name and signature there are already correct — only the error-handling is broken.
- Regenerate all five `baseline.json` files by running the corrected script.
- Re-derive `margin_rel`/`margin_abs` for each metric against the newly correct measured values (not inherited from the broken-baseline `100.0` floor).
- Commit regenerated baselines with `Ceiling-Approval:` in the commit message body.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/regression/corpus_runner.py:447-472` — the correct loss breakdown computation
- `packages/temper-placer/src/temper_placer/losses/wirelength.py` — `compute_total_hpwl` signature

**Test scenarios:**
- Happy path: Run the fixed extractor on piantor_right; assert `hpwl_final.mean > 0`, `overlap_loss_final` and `boundary_loss_final` are finite (not hardcoded 0.0), and `wirelength_final.mean != final_loss.mean`.
- Happy path: Run the fixed extractor on all 5 corpus boards; assert all five metrics are finite and the `hpwl_final` mean is non-zero on boards with ≥2 components.
- Error path: Import `compute_hpwl` (the wrong name) instead of `compute_total_hpwl`; assert the script raises rather than silently writing 0.0.

**Verification:**
- `git diff` on each `baseline.json` shows `hpwl_final.mean > 0`, `overlap_loss_final` and `boundary_loss_final` reflect computed values, and `wirelength_final` differs from `final_loss`.
- Existing corpus regression gate (`placer-regression.yml`) passes against the regenerated baselines.

---

### Phase 2: Spike — Canonical Extractor on Piantor Right

### U2. Remove dead code

**Goal:** Delete the two divergent `baseline_extractor.py` copies, the dead `_check_dependencies` import block, and the dead `test_placement_comparison.py` — clearing the ground before introducing the canonical extractor.

**Requirements:** R1, R2, R9 (bless audit)

**Dependencies:** U1 (to avoid merge conflicts with the script fix)

**Files:**
- Delete: `packages/temper-placer/src/temper_placer/validation/baseline_extractor.py`
- Delete: `packages/temper-placer/tests/fixtures/external/baseline_extractor.py`
- Delete: `packages/temper-placer/tests/validation/test_placement_comparison.py`
- Delete: `packages/temper-placer/tests/comparison/test_placement_comparison.py` (also dead — uses synthetic netlists, not corpus boards)

**Approach:**
- Verify no imports reference the deleted modules (grep codebase for import paths to `validation.baseline_extractor` and `fixtures.external.baseline_extractor`).
- Before deleting `test_placement_comparison.py`: audit and update the two modules that import from it — `tests/debug_libresolar.py` and `tests/test_piantor_left_overlap.py` — to either remove the import or migrate to the new canonical extractor. Both are external/slow tests; if dead, delete them; if needed, extract the shared `BaselineMetrics` class and utility functions into a surviving module.
- Remove any stale references in `__init__.py` files or test configuration.
- The `_check_dependencies` block in `validation/baseline_extractor.py` is removed as part of the file deletion; the imported loss functions (`BoundaryLoss`, `OverlapLoss`, `KiCadDRCValidator`) were never exercised by it.
- Verify `scripts/bless_baselines.py` does not reference `human_reference.yaml` (it reads `entry["baseline"]` from the manifest, so it naturally excludes non-baseline files). Add an explicit guard comment if needed. Covers AE7.

**Test expectation:** none — pure deletion of dead code. CI green after removal confirms no import breakage.

**Verification:**
- `rg baseline_extractor` returns zero results in `packages/temper-placer/`.
- `rg test_placement_comparison` returns zero results.
- Full test suite (`pytest -m "not external and not gpu and not slow"`) passes.
- Covers AE7: `scripts/bless_baselines.py` confirmed to reference only `baseline.json` (via manifest `entry["baseline"]`), not `human_reference.yaml`.

---

### U3. Create canonical `human_reference_extractor.py`

**Goal:** Single source of truth for extracting human-reference metrics from a `.kicad_pcb` file, with validation-gated pipeline and flat YAML output.

**Requirements:** R1, R2, R5, R6, R8

**Dependencies:** U2

**Files:**
- Create: `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py`
- Create: `packages/temper-placer/tests/validation/test_human_reference_extractor.py`
- Test: `packages/temper-placer/tests/validation/test_human_reference_extractor.py`

**Approach:**
- Public surface: `extract_human_reference(pcb_path: str, validate: bool = True) -> HumanReference` where `HumanReference` is a Pydantic model with `board_id: str`, `metrics: dict[str, MetricValue]`, `extraction_source: str`, `extractor_version: str`.
- Internally sequences: parse → validate parser output → build PlacementState → build LossContext → compute metrics → write YAML.
- Each computation step is a separate private function (`_parse_and_validate`, `_build_state`, `_compute_placement_metrics`, `_compute_routing_metrics`) — testable in isolation.
- Spike covers placement metrics only: HPWL, overlap loss, boundary loss. Routing metric functions are stubbed (return `{}` — empty dict) for now.
- `save()` writes flat `human_reference.yaml` — each metric as `{value: float, extracted_at: iso8601, pcb_git_hash: str}`.
- Follows the composite loss breakdown pattern from `corpus_runner.py:447-472` with softmax on rotation logits.
- Uses `pin_world_position` SSOT for any position transforms.
- No `try/except: pass` anywhere. Every validation failure raises with a descriptive message.

**Technical design:**

```
HumanReference:
    board_id: str
    extraction_source: str       # "piantor_right/keyboard_pcb.kicad_pcb"
    extractor_version: str       # git describe
    metrics: dict[str, MetricValue]

MetricValue:
    value: float
    extracted_at: datetime
    pcb_git_hash: str

extract_human_reference(pcb_path, validate=True) -> HumanReference:
    parse_result = _parse_and_validate(pcb_path, validate)
    state, context = _build_state_and_context(parse_result)
    metrics = _compute_placement_metrics(state, context)
    routing_metrics = _compute_routing_metrics(parse_result)  # stub — returns {}
    return HumanReference(...)
```

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/regression/corpus_runner.py:447-472` — composite loss breakdown + HPWL computation
- `packages/temper-placer/src/temper_placer/validation/metrics.py` — `compute_metrics` → `PlacementMetrics`
- `packages/temper-placer/src/temper_placer/core/pin_geometry.py` — `pin_world_position` SSOT
- `packages/temper-placer/src/temper_placer/core/state.py` — `PlacementState` construction with rotation_logits

**Test scenarios:**
- Happy path: `extract_human_reference` on piantor_right `keyboard_pcb.kicad_pcb` returns a `HumanReference` with `board_id="piantor_right"`, HPWL > 0, overlap_loss and boundary_loss finite.
- Happy path: `save()` writes a `.yaml` file whose content round-trips through `HumanReference(**yaml.safe_load(...))`.
- Happy path: On a multi-component board with known routing, `_parse_and_validate` returns `parse_result.traces` with count > 0 and every trace.net is a string (not `<Net object at ...>`).
- Edge case: On a 4-component minimal board, HPWL is still finite and positive (at least one net spans ≥2 components).
- Error path: Passing a nonexistent file path raises `FileNotFoundError`.
- Error path: Passing a board where HPWL computation returns NaN raises `ValueError`.
- Integration: `extract_human_reference(pcb_path, validate=False)` skips assertions and still produces output (for debugging/iteration).

**Verification:**
- `pytest packages/temper-placer/tests/validation/test_human_reference_extractor.py` passes.
- Human-read the generated `human_reference.yaml` for piantor_right — confirm HPWL value is in a reasonable range for a ~36-component keyboard.

---

### U4. Per-piece validation tests and piantor_right human_reference.yaml

**Goal:** Write per-piece validation tests covering every link in the extraction chain against real data, plus programmatic fixtures for edge cases. Generate and commit the first `human_reference.yaml`.

**Requirements:** R3, R4, R5, R6, R12

**Dependencies:** U3

**Files:**
- Create: `packages/temper-placer/tests/validation/test_human_reference_validation.py` (extended from U3 test file or new)
- Create: `power_pcb_dataset/corpus/piantor_right/human_reference.yaml`
- Test: `packages/temper-placer/tests/validation/test_human_reference_validation.py`

**Approach:**
- Trace extraction test (R3): Parse piantor_right PCB, assert `len(traces) > 0`, assert every `trace.net` is a named net (not matching the `<Net object at 0x…>` pattern), assert every `trace.net` appears in the parsed netlist's net names.
- Via extraction test (R4): Same board, assert `len(vias) > 0`, assert every `via._net` resolves to a real net name.
- HPWL test (R5): Run `compute_total_hpwl` on piantor_right's parsed PlacementState; assert finite and > 0.
- Overlap test (R6): Build a minimal two-component fixture where bounding boxes overlap (positions set to nearly identical coordinates); assert `OverlapLoss()(positions, rotations, context).value > 0`.
- Boundary test (R6): Build a minimal fixture with one component placed at negative coordinates (off-board); assert `BoundaryLoss()(positions, rotations, context).value > 0`.
- Trace fallback audit: For every trace on piantor_right, verify the net-name resolution path (net_map vs. fallback); log any fallback hits and assert count == 0.
- Generate `human_reference.yaml` for piantor_right by running the canonical extractor.
- Write a test that loads the committed `human_reference.yaml` and asserts all placement metrics are present, finite, and `hpwl > 0`. Covers AE1, AE5.

**Execution note:** Write validation tests before generating the committed YAML — the extractor must pass its own tests before its output is committed.

**Patterns to follow:**
- Use `parse_kicad_pcb` for all real-board tests — no mock parsers.
- Programmatic fixtures use `PlacementState.from_positions` with literal coordinate lists.
- Mark real-board tests with `@pytest.mark.l4_regression` (corpus-level test marker).

**Test scenarios:**
- Covers AE1. Trace extraction on piantor_right: parse PCB, extract traces, assert count > 0 and every trace.net is a named net from the netlist.
- Covers AE1. HPWL on piantor_right: build PlacementState, compute HPWL, assert finite and > 0.
- Covers AE2. Overlap fixture: two components at overlapping positions, overlap loss > 0.
- Covers AE3. Boundary fixture: one component off-board, boundary loss > 0.
- Covers AE5. Committed `human_reference.yaml` for piantor_right: load file, assert `hpwl.value > 0`, `overlap_loss.value` and `boundary_loss.value` are finite, `board_id == "piantor_right"`.
- Edge case: Via extraction on an UNROUTED board (the `_unrouted.kicad_pcb` from `strip_routing`) returns zero vias and handles gracefully.
- Edge case: Net-name resolution for all traces on piantor_right never falls through to the `str(track.net)` placeholder path.

**Verification:**
- All validation tests pass on piantor_right.
- `power_pcb_dataset/corpus/piantor_right/human_reference.yaml` is committed with correct, non-zero, non-defaulted metrics.
- `pytest packages/temper-placer/tests/validation/ -m "not external" -v` shows each per-piece test passing.

---

### Phase 3: CI Integration

### U5. Create `human-reference-check.yml` CI workflow and comparison script

**Goal:** Wire the comparison pipeline: CI runs the placer on each in-scope board, compares optimizer output to human_reference.yaml, and posts a sticky PR comment with per-metric ratios.

**Requirements:** R10, R11, R12 (spike: piantor_right only)

**Dependencies:** U4 (piantor_right human_reference.yaml committed)

**Files:**
- Create: `.github/workflows/human-reference-check.yml`
- Create: `scripts/human_reference_compare.py`
- Modify: `scripts/manifest.yaml` (add entry for new script)

**Approach:**
- **CI workflow** (`human-reference-check.yml`):
  - Triggers on PRs touching `packages/temper-placer/src/**`, `power_pcb_dataset/corpus/**`, or `human_reference.yaml` files.
  - Two-job pattern: `current` (checkout PR head → run placer → produce metrics artifact), `comparison` (download current artifact → run `human_reference_compare.py` → `marocchino/sticky-pull-request-comment@v2` with `header: corpus-oracle`). No merge-base baseline job is needed — the comparison is against the static `human_reference.yaml`, not against the merge-base. A third job can be added later if delta-from-baseline context is desired.
  - `continue-on-error: true` on the comparison job (advisory only, per R11).
  - Spike phase: only piantor_right is in the comparison matrix. A CI variable or script config flag gates the board list.
  - Path filter ensures the workflow only runs when relevant files change.

- **Comparison script** (`scripts/human_reference_compare.py`):
  - Reads current placer metrics (from artifact JSONL or direct invocation) and the committed `human_reference.yaml` for each board.
  - For each board: runs per-piece validation. Boards that pass → computes per-metric ratio (opt / human). Boards that fail → marks as "excluded".
  - Produces a Markdown comment body: one `#### {board_id}` block per board with a table of Metric / Opt / Human / Ratio rows.
  - For excluded boards: a single line below the header: `> validation failed — excluded from comparison`.
  - No composite score. No pass/fail indicators. Ratios are displayed as raw floats to 2 decimal places.
  - In spike phase, only piantor_right appears. Other corpus boards are in the board list but gated by a `boards` config.

**Technical design:**

```
# human_reference_compare.py signature
def compare_board(board_id: str, opt_metrics: dict, human_ref_path: str) -> ComparisonBlock:
    """Returns a ComparisonBlock with ratios or exclusion note."""
    ...

def render_comment(blocks: list[ComparisonBlock]) -> str:
    """Renders the full Markdown comment body."""
    ...
```

**Patterns to follow:**
- `.github/workflows/pr-pipeline-scorecard.yml` — three-job artifact upload/download pattern
- `scripts/pr_scorecard.py` — Markdown table rendering and sticky comment posting
- `marocchino/sticky-pull-request-comment@v2` with a unique header to avoid collision with the existing scorecard comment

**Test scenarios:**
- Happy path: Run comparison script with piantor_right metrics; output Markdown contains a `#### piantor_right` block with a table; all metrics have defined values in the "Human" column.
- Happy path: Run comparison script with piantor_right metrics where opt HPWL > human HPWL; ratio > 1.0 displayed.
- Edge case: Run comparison script on a board where `human_reference.yaml` is missing; board marked as "reference not found — excluded".
- Covers AE4. Integration: PR touching `packages/temper-placer/src/` triggers the workflow; sticky comment appears with piantor_right block and no composite score.
- Covers AE5. Spike: board list contains only piantor_right; comment shows exactly one board block.
- Error path: placer run fails for a board; that board is noted as "placer run failed — excluded" in the comment.

**Verification:**
- Open a draft PR touching a file under `packages/temper-placer/src/`; confirm `human-reference-check.yml` triggers and posts a sticky comment.
- Comment body matches the template: one block, `piantor_right`, per-metric ratios, no composite score.
- The existing `pr-pipeline-scorecard.yml` sticky comment continues to work independently (confirm distinct headers).

---

### Phase 4: Corpus Expansion and Routing Metrics

### U6. Expand to corpus 5 with per-board validation and exclusion

**Goal:** Generate `human_reference.yaml` for the remaining 4 corpus boards, write per-board validation tests, and implement per-board exclusion in the comparison script.

**Requirements:** R13

**Dependencies:** U5 (CI + comparison wired)

**Files:**
- Create: `power_pcb_dataset/corpus/temper/human_reference.yaml`
- Create: `power_pcb_dataset/corpus/minimal/human_reference.yaml`
- Create: `power_pcb_dataset/corpus/rp2040_designguide/human_reference.yaml`
- Create: `power_pcb_dataset/corpus/bitaxe_ultra/human_reference.yaml`
- Modify: `.github/workflows/human-reference-check.yml` (expand board matrix)
- Modify: `scripts/human_reference_compare.py` (expand board list, add per-board validation logic)
- Test: `packages/temper-placer/tests/validation/test_human_reference_validation.py` (extend with per-board tests)

**Approach:**
- Before generating any `human_reference.yaml`, screen each board's human placement for competence: run DRC (`KiCadDRCValidator.run_drc`), check via count is in an expected range for the board's class, and eyeball for obvious corner-packing. Boards that fail screening are excluded from the oracle — the same exclusion pattern R13 uses for validation failures. Log the screening result in the extraction commit message.
- Run the canonical extractor on each of the 4 remaining corpus boards.
- For each board, write a validation test asserting: trace count > 0 (for routed boards), HPWL > 0, overlap_loss and boundary_loss finite, net names resolve correctly.
- Minimal board (4 components) may have trace count = 0 if unrouted; handle gracefully (HPWL should still be > 0 since it has multi-component nets).
- Implement per-board exclusion in the comparison script: before computing ratios, run per-piece validation. If any validation assertion fails, mark board as excluded with the specific failure reason in the comment.
- Expand CI matrix to all 5 corpus boards.
- Covers AE6: verify that a deliberately corrupted `human_reference.yaml` (e.g., missing a metric) produces an exclusion note, not a misleading ratio.

**Execution note:** Generate `human_reference.yaml` for each board one at a time, running the per-board validation test before committing. A board whose validation fails during generation is investigated, not committed.

**Patterns to follow:**
- Same extractor and test patterns as U4, applied per-board.
- `power_pcb_dataset/corpus/manifest.yaml` — may add an `oracle: true` field to mark boards included in the human-reference comparison.

**Test scenarios:**
- Happy path: All 5 corpus boards have committed `human_reference.yaml`; each passes its per-board validation test.
- Covers AE6. Board exclusion: Run comparison on a board whose trace extraction produces net-name placeholders; comment output shows "validation failed — excluded from comparison" for that board, not a table of ratios.
- Complete: Comparison run across all 5 boards produces 5 blocks, of which ≥4 are valid (more if all pass).
- Edge case: A board's `human_reference.yaml` is committed but missing a required metric field; comparison script excludes with note "missing metric `hpwl` — excluded".

**Verification:**
- All 5 `human_reference.yaml` files committed; each passes its per-board validation test.
- Comparison CI run produces a comment with 5 board blocks; non-zero per-metric ratios on all eligible boards.
- No board silently emits a `0.0` ratio sourced from an unvalidated pipeline piece.

---

### U7. Add routing metrics (RDL and via count)

**Goal:** Extend the canonical extractor with routing metric computation from parsed traces and vias, and add RDL/via-count rows to the PR comment.

**Requirements:** R7, R14

**Dependencies:** U6 (corpus 5 committed, validation framework in place)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py` (implement `_compute_routing_metrics`)
- Modify: `packages/temper-placer/tests/validation/test_human_reference_validation.py` (add routing validation tests)
- Modify: `scripts/human_reference_compare.py` (add RDL and via-count rows)
- Modify: `power_pcb_dataset/corpus/*/human_reference.yaml` (regenerate with routing fields)

**Approach:**
- In `_compute_routing_metrics(parse_result)`: sum segment lengths for RDL (Euclidean distance between `trace.start` and `trace.end` for each segment), count vias.
- RDL sum is approximate (straight-line per segment, not accounting for layer transitions); the brainrot's requirement is "measured, not hardcoded," not "micron-accurate trace routing model."
- Both metrics are asserted finite and strictly positive on routed boards (all corpus 5 except possibly minimal).
- Test on an unrouted board fixture (produced by `strip_routing`): assert RDL = 0, via_count = 0.
- Extract RDL and via count from the placer's own router output (router-v6's `RouteResult`) for the comparison — the opt side must be generated by the router, not the authoring tool.
- For the spike-to-expansion transition: RDL and via-count rows in the comment show `—` (placeholder) when the optimizer side doesn't produce routing yet. Once the router produces routing output, rows populate with ratios.
- Regenerate all 5 `human_reference.yaml` files to include the routing metric fields.

**Execution note:** Write routing validation tests against real piantor_right board first (most routing-heavy), then extend to all 5.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/io/kicad_parser.py:485-530` — `_extract_traces_from_pcb` and `TraceData` structure
- `packages/temper-placer/src/temper_placer/io/kicad_parser.py:539-579` — `_extract_vias_from_pcb` and `ViaData` structure

**Test scenarios:**
- Happy path: `_compute_routing_metrics` on piantor_right returns `rdl > 0` and `via_count > 0`.
- Covers R7. Routed board: assertion that RDL and via count are finite and strictly positive on piantor_right, temper, rp2040_designguide, bitaxe_ultra.
- Covers R7. Unrouted board: `strip_routing` fixture produces 0 routed length and 0 vias; assertions pass.
- Edge case: A board with traces but no vias (surface-mount only) returns `via_count == 0` gracefully (not an error).
- Integration: Regenerated `human_reference.yaml` for piantor_right includes `rdl` and `via_count` fields with non-zero values.

**Verification:**
- All 5 `human_reference.yaml` files include `rdl` and `via_count` with finite, non-zero values on routed boards.
- `pytest packages/temper-placer/tests/validation/test_human_reference_validation.py -k routing` passes.
- Comment includes RDL and via-count rows for boards where both human and opt routing metrics are available.

---

### U8. Add DRC delta comparison (expansion)

**Goal:** Compute DRC violations on the human-reference board and the optimizer's output, and surface the delta as a row in the PR comment.

**Requirements:** R15

**Dependencies:** U7 (routing metrics wired, router produces placement+routing for DRC comparison)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py` (add `_compute_drc`)
- Modify: `packages/temper-placer/tests/validation/test_human_reference_validation.py` (add DRC validation tests)
- Modify: `scripts/human_reference_compare.py` (add DRC delta row)
- Modify: `power_pcb_dataset/corpus/*/human_reference.yaml` (regenerate with DRC field)

**Approach:**
- `_compute_drc(pcb_path)` invokes the existing `KiCadDRCValidator.run_drc(pcb_path)` and records the violation count.
- Test assertions: DRC runs and returns finite count; on the clean human reference, count is zero; on a deliberately-broken fixture (e.g., traces crossing clearance boundaries), count > 0.
- A board whose human reference has nonzero DRC errors (e.g., due to original .kicad_pcb compatibility or version mismatch) is excluded from the DRC-delta row with a note — not silently included with a misleading ratio.
- DRC delta row does not appear in the comment for a board until R15's test assertions pass on that board (per-board gate).
- DRC delta = opt_drc_violations - human_drc_violations (absolute delta, not a ratio, since zero denominator is meaningful — zero human violations, nonzero opt violations, ratio is infinite/undefined).
- Regenerate all 5 `human_reference.yaml` files to include the DRC field.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/validation/drc.py` — `KiCadDRCValidator`
- `tests/fixtures/external/baseline_extractor.py` — example of `run_drc` invocation

**Test scenarios:**
- Happy path: `_compute_drc` on piantor_right returns 0 violations.
- Happy path: `_compute_drc` on a deliberately-broken fixture returns > 0 violations.
- Error path: `_compute_drc` on a board whose human reference has nonzero DRC violations; the DRC-delta row is excluded with a note `DRC excluded: human reference has N violations`.
- Integration: Comment for piantor_right includes a DRC delta row showing delta = (opt_violations - 0).

**Verification:**
- All 5 `human_reference.yaml` files include `drc_violations` field.
- DRC row in comment is populated when both human and opt DRC are valid.
- Board with nonzero human DRC is excluded from the DRC row with a note, not silently included.

---

## System-Wide Impact

- **Interaction graph:** The new `human-reference-check.yml` workflow runs alongside existing `pr-pipeline-scorecard.yml` and `placer-regression.yml` — distinct triggers and sticky comment headers ensure no collision.
- **Error propagation:** All extraction failures raise by default (no `try/except: pass`). Comparison script catches board-level failures and surfaces them in the comment without failing the CI job (advisory oracle).
- **State lifecycle risks:** `human_reference.yaml` is immutable once committed; the bless script (`scripts/bless_baselines.py`) must be audited (and possibly guarded) to ensure it never touches `human_reference.yaml` files.
- **API surface parity:** The canonical extractor's public function `extract_human_reference(pcb_path)` is the single entrypoint for human-reference extraction — no divergent copies or alternate paths.
- **Integration coverage:** CI workflow with artifact upload/download proves the end-to-end pipeline (parse → extract → placer → compare → comment) works. Per-board validation in the comparison script proves the pipeline works on every board, not just the spike board.
- **Unchanged invariants:**
  - The existing `pr-pipeline-scorecard.yml` sticky comment is not modified — separate header ensures independent operation.
  - The existing `placer-regression.yml` corpus gate continues to operate on `baseline.json` — U1 fixes its broken baselines but does not change the gate's behavior.
  - The `scripts/bless_baselines.py` workflow continues to operate on `baseline.json` only — `human_reference.yaml` is explicitly excluded.
  - The `kiutils`-based parser (`kicad_parser.py`) is not modified — the extractor validates its output rather than changing its behavior.
  - The `corpus_runner.py` regression runner is not modified beyond the line-469 `compute_hpwl` bug fix in U1.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Piantor right fails to parse under current `parse_kicad_pcb` — the spike has no board to test on. | Already verified as a corpus board with a committed `baseline.json` — the parser already works on it. The risk is in trace/via extraction specifically; if extraction fails, investigate and fix the parser before proceeding. |
| `_extract_traces_from_pcb` fallback path fires on real corpus boards — net-name resolution is unreliable. | U4 includes a trace-fallback audit test that counts and asserts zero fallback hits. If it fires, the net-map lookup needs extension before proceeding. |
| `compute_total_hpwl` returns 0 on a multi-net board — the HPWL implementation has a bug that conflates single-pin and multi-pin nets. | Validate on piantor_right first (U4); if HPWL is zero, investigate and fix in a separate prerequisite issue before continuing. |
| A corpus board's human placement is rough or didactic — treating it as an "accuracy oracle" produces misleading ratios. | Screen each board's placement (eyeball or heuristic: DRC-clean, via count in expected range, no corner-packing). Exclude boards that don't pass screening. Ratio=1.0 means "matches this human," not "optimal." |
| CI runner lacks KiCad for DRC validation (U8 expansion). | DRC tests are marked and gated — the DRC-delta row doesn't appear until R15's assertions pass. If KiCad is unavailable in CI, skip DRC with a noted exclusion. |
| JAX nondeterminism on CI runners causes spurious metric drift in the PR comment. | This is a known issue (the existing `placer-regression.yml` uses `continue-on-error: true` for this reason). The comment is advisory — per-metric ratios will have noise; the comparison script does not fail on ratio variance. |

---

## Phased Delivery

### Phase 1 (U1): Prerequisite Fix
Fix `extract_corpus_baselines.py` and regenerate corpus baselines. Lands first because the spike builds on a correct gate, not a broken one.

### Phase 2 (U2, U3, U4): Spike — Canonical Extractor on Piantor Right
Remove dead code, create the canonical extractor, write per-piece validation tests, and commit the first `human_reference.yaml`. The extractor must pass its own tests before its output is committed.

### Phase 3 (U5): CI Integration
Wire the comparison workflow and PR comment. Spike phase: piantor_right only in the comment.

### Phase 4 (U6, U7, U8): Corpus Expansion and Routing Metrics
Expand to all 5 corpus boards, add routing metrics (RDL, via count), add DRC delta. Each board gates on its own per-piece validation passing.

---

## Documentation / Operational Notes

- **`BASELINE_POLICY.md`** (`power_pcb_dataset/corpus/`): Update to include `human_reference.yaml` immutability rule — bless workflow must not touch it; only path to update is a separate regenerate-and-review commit.
- **PR comment header `corpus-oracle`**: Documented here so future CI changes don't accidentally reuse the same header and overwrite the human-reference comment.
- **On-call / support**: The comment is advisory; no alerts fire on ratio changes. A future brainstorm may define alert thresholds once real-signal runs accumulate.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-01-human-reference-corpus-oracle-requirements.md](../../brainstorms/2026-07-01-human-reference-corpus-oracle-requirements.md)
- Broken baseline extractor: `scripts/extract_corpus_baselines.py`
- Correct loss breakdown pattern: `packages/temper-placer/src/temper_placer/regression/corpus_runner.py:447-472`
- Existing sticky comment pattern: `.github/workflows/pr-pipeline-scorecard.yml`
- `marocchino/sticky-pull-request-comment@v2`: used in pr-pipeline-scorecard.yml
- Institutional learning — silent failure class: `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md`
- Institutional learning — oracle mismatch risk: `docs/solutions/best-practices/bfs-oracle-cost-model-mismatch-astar-validation-2026-06-28.md`
- Institutional learning — pipeline observability: `docs/solutions/architecture-patterns/pipeline-observability-observer-cross-validation-pattern-2026-06-29.md`
- Institutional learning — CI gate quality enforcement: `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md`
- Institutional learning — golden fixture ladder: `docs/solutions/best-practices/golden-fixture-ladder-parity-testing-2026-06-22.md`
- Institutional learning — pad-position SSOT: `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md`
