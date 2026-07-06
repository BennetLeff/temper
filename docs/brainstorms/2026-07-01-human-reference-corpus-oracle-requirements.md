---
date: 2026-07-01
topic: human-reference-corpus-oracle
---

# Human-Reference Corpus Oracle

## Summary

A non-blocking PR comment comparing the placer's and router's output on real open-source boards against the human-designed reference placement and routing that already lives in those same `.kicad_pcb` files. Built correctness-first, with per-piece validation at every level of granularity before any number is trusted enough to surface.

---

## Problem Frame

The project has a mature verification apparatus (golden fixture ladder, per-stage DRC fence, corpus regression gate over 5 boards, 6,480 tests, 252 Hypothesis properties, BMC exhaustive proofs). Almost all of it measures the pipeline against *itself* on toy data: goldens compare pipeline output to pipeline output (parity, not correctness); corpus baselines compare metrics to the placer's own previously-recorded metrics (drift, not quality); invariants prove "this placement isn't illegal," never "this placement is good."

The 17 real, human-placed-and-routed open-source boards already on disk are used only as parse smoke tests (`@pytest.mark.external`, skipped when not downloaded, gated on the 4-component `minimal_board.kicad_pcb` for "zero DRC" claims). The external oracle — competent-human placements and routings sitting in the same KiCad file — is unused.

The corpus regression apparatus meant to gate placement regressions is itself silently broken. Inspecting the committed `power_pcb_dataset/corpus/*/baseline.json` files together with their writer, `scripts/extract_corpus_baselines.py`, shows four of five baseline metrics are wrong via three distinct failure modes:

- `hpwl_final: {"mean": 0.0}` — written by a `try: from temper_placer.losses.wirelength import compute_hpwl; ... except Exception: pass` block. No `compute_hpwl` exists in `wirelength.py`; only `compute_total_hpwl(positions, rotations, context)`. The `ImportError` is silently swallowed and `0.0` propagates.
- `overlap_loss_final: {"mean": 0.0}` — hardcoded as `0.0` in the writer template, not measured.
- `boundary_loss_final: {"mean": 0.0}` — same. Hardcoded, not measured.
- `wirelength_final` — aliased to `final_loss` (the composite), not the wirelength breakdown.

Each modified `baseline.json` is committed, every PR's regression run reads these as ground truth, and the gate passes — because the gate's tolerance floor (`margin_abs: 100.0`) absorbs `0.0 ± 100` without complaint. A bug this coarse shipping through a verification apparatus the size of this one is the strongest possible signal that the apparatus measures precision, not accuracy: it can prove drift and legality, not correctness.

The half-built human-reference scaffolding compounds this. Two divergent copies of `baseline_extractor.py` exist (`tests/fixtures/external/` and `src/temper_placer/validation/`), neither tested beyond `test_placement_comparison.py` — which itself reads a `human_placement` field the committed baselines don't populate. `_check_dependencies()` imports `BoundaryLoss`, `OverlapLoss`, `KiCadDRCValidator` and uses none of them. The code has been dead since first commit (`6db810fb`).

The remedy is not "more machinery." It is: rewrite the baseline extractor correctly, validate each piece of the chain against a real board, build a non-blocking human-reference comparison over the result, and only then consider whether anything should gate.

---

## Actors

- A1. **Maintainer**: opens a PR touching the placer or router. Wants to know whether their change made placement or routing better or worse against a real human reference, not just whether self-parity goldens still pass.
- A2. **Reviewer**: reads the PR comment. Needs per-metric ratios they can reason about (one regression in a sea of improvements is signal; a green composite score is not).
- A3. **CI runner**: produces the comment. Must produce traceable, reproducible per-board blocks; must not silently emit `0.0` or hide failure behind a tolerance floor.
- A4. **Future planner/implementer**: consumes this requirements doc. Needs the validation discipline explicit enough that they can't accidentally rebuild the silent-failure pattern under a new name.

---

## Key Flows

- F1. **Baseline extraction (validation-gated)**
  - **Trigger:** maintainer or CI invokes the extractor on a real board's `.kicad_pcb`.
  - **Actors:** A3
  - **Steps:**
    1. Parse the placed-and-routed PCB.
    2. Validate every piece of the parse: footprint count, net-name resolution, trace segment count, via count, net continuity (every trace's net resolves to a named net, not `<Net object at 0x…>`).
    3. Build a `PlacementState` from the parsed positions and rotations.
    4. Compute_HPWL over that state. Assert the result is finite and non-zero for any board with ≥ 1 net spanning > 1 component.
    5. Compute overlap loss and boundary loss over that state. Assert each is finite. Record the measured value, not a hardcoded default.
    6. (Expansion phase.) Compute traced routed length and via count from extracted traces. Assert non-zero on boards known to contain routing. Skipped during the spike — the spike's `human_reference.yaml` is placement-only (HPWL, overlap, boundary) and is extended with routing metrics during expansion.
    7. Write `human_reference.yaml` to the corpus board directory.
  - **Outcome:** `human_reference.yaml` is provably derived from the parsed board, every metric traceable to a measured value.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8

- F2. **PR comparison (report-only)**
  - **Trigger:** a pull request touches `packages/temper-placer/src/**` or `power_pcb_dataset/corpus/**`.
  - **Actors:** A1, A2, A3
  - **Steps:**
    1. CI runs the placer (and, in the expansion phase, the router) on each in-scope board.
    2. CI compares the placer's output to `human_reference.yaml` for that board: per-metric ratios (HPWL, overlap, boundary, RDL, via count, DRC delta).
    3. CI posts a sticky PR comment with one block per board showing the ratios, plus a one-line "compared to human-designed {placement,placement+routing}" header.
    4. CI does not fail the build on regression.
  - **Outcome:** maintainer and reviewer see real-signal per-metric deltas on every relevant PR; no false-fails, no blessing of bad baselines.
  - **Covered by:** R10, R11

---

## Requirements

**Canonical extractor (one source of truth)**

- R1. The baseline extractor exists in exactly one location under `src/temper_placer/`. The divergent copies in `tests/fixtures/external/baseline_extractor.py` and `src/temper_placer/validation/baseline_extractor.py` are removed or consolidated into the single canonical module.
- R2. The canonical extractor's public surface is a single function that takes a parsed board and returns a human-reference metrics block. No `_check_dependencies` style dead-import block; imports are at module top level and exercised by tests.

**Per-piece validation: parser**

- R3. `_extract_traces_from_pcb` is exercised against a real board's `.kicad_pcb` by a test that asserts the returned trace count is non-zero and that every returned trace's `net` field resolves to a named net (not a `str(net)` fallback to `<Net object at 0x…>`). The fallback path is either removed or made loud — a trace whose net cannot be resolved raises, not silently receives a placeholder name.
- R4. `_extract_vias_from_pcb` is exercised against the same board with the analogous assertions (via count non-zero on a routed board; every via's `_net` resolves to a real net name).

**Per-piece validation: placement metrics**

- R5. HPWL computation invoked from the extractor uses the correct function signature (`compute_total_hpwl(positions, rotations, context)`, not the nonexistent `compute_hpwl(state, netlist)`). The test asserts the value is finite and strictly positive on any board with at least one net spanning more than one component. A board that returns `0.0` for HPWL fails the test, not the run.
- R6. The extractor computes `overlap_loss` and `boundary_loss` from the parsed placement state — never hardcoded `0.0`. Tests assert that on a well-placed board these are finite (and may legitimately be small), and on a deliberately-overlapping fixture the overlap loss is strictly positive.

**Per-piece validation: routing metrics (expansion phase)**

- R7. Routed length and via count are derived from the extracted traces (sum of segment lengths for RDL; count of vias for via count). Tests assert both are finite and strictly positive on a routed board, and zero on a deliberately unrouted fixture (the `_unrouted.kicad_pcb` form already produced by `strip_routing`).

**Human-reference artifact**

- R8. Each in-scope board's human-reference metrics are written to `power_pcb_dataset/corpus/{board}/human_reference.yaml` — separate from `baseline.json`. The file records, per metric, the measured value and the extraction timestamp and source PCB git hash. No tolerance margins (`margin_rel`/`margin_abs`) are stored; this artifact is an immutable human-reference diff (the downloaded human's placement and routing), not a correctness oracle and not a regression gate baseline. The spike's `human_reference.yaml` records placement metrics only (HPWL, overlap, boundary); routing-metric fields (RDL, via count, DRC) are added during the expansion phase (R7, R15).
- R9. A `human_reference.yaml` is treated as immutable once committed: the bless workflow (`scripts/bless_baselines.py` and successors) must not touch it. The only path to update it is a separate, explicit regenerate-and-review commit.

**Comparison report**

- R10. The comparison surfaces per-metric ratios (opt vs. human) for: HPWL, overlap loss, boundary loss, RDL, via count, DRC delta. No composite score is computed or surfaced.
- R11. The comparison is posted as a sticky PR comment using the existing `marocchino/sticky-pull-request-comment@v2` action already wired in `pr-pipeline-scorecard.yml`. One block per board. The comment is advisory: PRs are not failed by the comparison.

**Spike, then expand**

- R12. The first wiring covers exactly one board: `piantor_right`. The spike produces a committed `human_reference.yaml` for `piantor_right`, a working end-to-end comparison report on one PR, and passing validation tests for every piece touched.
- R13. After the spike, the harness is expanded to the corpus 5 (`temper`, `minimal`, `rp2040_designguide`, `bitaxe_ultra`, `piantor_right`). Each new board gates on that board's per-piece validation tests passing; a board whose validation fails is excluded from the comment and the failure is noted in the comment, not swallowed.
- R14. The router-vs-human comparison (RDL, via count, DRC delta) is scoped as the expansion phase after the spike, not deferred indefinitely. The spike covers placement metrics (HPWL, overlap, boundary); the expansion adds the routing metrics via R7.

**Per-piece validation: DRC (expansion phase)**

- R15. DRC delta is computed from a validated DRC run over the extracted placement and routing. Tests assert the DRC validator runs, returns finite violation counts (strictly positive on a deliberately-broken fixture), and returns zero on the clean human reference board. A board whose human reference has nonzero DRC errors is excluded from the DRC-delta row of the comment and noted, not silently included with a misleading ratio. DRC delta does not surface in the comment until this requirement passes.

**Prerequisite: fix the existing corpus gate**

- R16. Before the spike (R12) starts, the existing corpus regression gate is corrected in a separate, small PR: `scripts/extract_corpus_baselines.py` is fixed to call `compute_total_hpwl(positions, rotations, context)` with the correct signature (not the nonexistent `compute_hpwl(state, netlist)`), `overlap_loss_final` and `boundary_loss_final` are measured from the run (not hardcoded `0.0`), `wirelength_final` records the wirelength breakdown (not the `final_loss` composite), and the bare `try: ... except Exception: pass` block is removed so import or computation failures raise instead of silently writing zero. The committed `power_pcb_dataset/corpus/*/baseline.json` files are regenerated from the corrected writer, and each metric's `margin_rel`/`margin_abs` is re-derived against the measured value (not inherited from the broken-baseline regime's `100.0` floor). This lands before R12 so the spike builds on a correct gate, not alongside a broken one.

---

## Acceptance Examples

- AE1. **Covers R3, R5.** Given `power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb` (a real, placed-and-routed board), when `extract_human_reference` runs, then every extracted trace has a `net` field equal to a named net from the netlist (no `<Net object at …>` placeholders), HPWL is finite and strictly positive, and the run completes without raising a swallowed `ImportError`.
- AE2. **Covers R5, R6.** Given a fixture with two components deliberately placed to overlap, when the extractor computes overlap loss on that fixture, then the overlap loss is strictly positive and recorded in `human_reference.yaml` as such (never as a hardcoded `0.0`).
- AE3. **Covers R6.** Given a fixture with a component placed partially off-board, when the extractor computes boundary loss, then the boundary loss is strictly positive and recorded as such.
- AE4. **Covers R10, R11.** Given a PR that touches `packages/temper-placer/src/`, when the comparison workflow runs across the corpus 5, then a sticky PR comment appears with one block per board showing per-metric ratios (opt / human) and no composite score. The build does not fail regardless of the ratios.
- AE5. **Covers R12.** Given the spike phase, when the harness is first wired, then only `piantor_right` appears in the comment. Corpus expansion to the other 4 boards is blocked until the spike's validation tests pass on `main`.
- AE6. **Covers R13.** Given a board whose validation tests fail (e.g. trace extraction returns a `<Net object at …>` placeholder on a new board), when the comparison runs, then the comment notes that board as "validation failed — excluded from comparison" rather than emitting a misleading ratio computed from corrupted data.
- AE7. **Covers R8, R9.** Given a maintainer runs `scripts/bless_baselines.py` to refresh a placer improvement, when the bless completes, then `baseline.json` is rewritten and `human_reference.yaml` is untouched.

---

## Success Criteria

- A maintainer opening a placer or router change can read the PR comment and see per-metric deltas against a real human reference on at least one real board, with no metric in the comment sourced from an unvalidated pipeline piece.
- A reviewer can distinguish "this change improved HPWL by 8% but worsened overlap by 50%" from "the composite score moved" — and trust that no per-metric value is silently `0.0`.
- A future planner or implementer can run the per-piece validation tests and get green on `main` today, and red the moment any piece of the chain (parser, HPWL, overlap, boundary, RDL, via count) breaks on a real board.
- The four-wrong-metrics regime (`hpwl_final` silently `0.0`, `overlap_loss_final` hardcoded, `boundary_loss_final` hardcoded, `wirelength_final` mislabeled) is no longer possible: every metric in either `baseline.json` or `human_reference.yaml` is traceable to a measured value, asserts non-triviality on boards known to exercise the metric, and fails loud if a link in the chain silently breaks.
- A downstream agent reading this doc knows which validation tests to write, in which order, against which fixtures — without re-deriving the failure modes from the current bug.

---

## Scope Boundaries

- No auto-promotion of the comparison to a CI gate. The comment is advisory. Promotion to a gate is a separate decision that depends on accumulated real-signal runs and chosen thresholds, deferred to a later brainstorm.
- No FreeRouting integration. FreeRouting as an independent autorouter oracle is out of scope; the human reference is the only external oracle in this work.
- No topological / graph-isomorphism semantic golden equivalence. Coordinate parity and per-metric ratios remain the comparison basis.
- No mutation testing (mutmut / cosmic-ray). Useful for assertion-strength measurement but only meaningful against a real oracle; deferred until this oracle has accumulated enough runs to make mutation kills interpretable.
- No new Kicad board downloads in the spike phase. The spike uses `piantor_right`, which is already on disk and already a corpus board.
- No real Z3 / SMT differential oracle. The committed "Z3 SMT verification" claim in `e375e111` is unsupported; wiring real Z3 belongs to a separate brainstorm.
- Known-broken window, owned: until R16 lands, the existing corpus regression gate blesses four wrong metrics on every PR. R16 is the prerequisite that closes this window; the spike (R12) does not start until R16 is on `main`. The doc does not pretend the window doesn't exist.

---

## Key Decisions

- **Correctness first, elegance second.** The rewrite exists to make the chain auditable, not to make the code beautiful. A verbose extractor where every step is testable beats a terser one where silent failure hides. Elegance is pursued only within constraints that preserve validation.
- **Validation at every level of granularity.** Every piece of the chain — parser trace extraction, parser via extraction, net-name resolution, PlacementState construction, HPWL, overlap, boundary, RDL, via count — has at least one test asserting it works on a real board. A piece without a test is a piece the chain doesn't trust.
- **Report-only, no gate.** We don't yet know what "good" looks like on real boards. The current corpus baselines were wrong since first commit and the gate passed them. Any gate inherits its tolerance from accumulated real measurements — we don't have those yet. Premature gating either blesses another bad baseline or blocks unrelated PRs.
- **Separate `human_reference.yaml` from `baseline.json`.** Different update semantics: `baseline.json` is re-blessed on every placer improvement; `human_reference.yaml` is an immutable human-reference diff derived from the downloaded board. Cohabiting them risks a future bless-script change silently overwriting the human number — the same class of silent-failure bug we are removing.
- **Raw per-metric ratios, no composite score.** A composite score is what allowed four-wrong-metrics to ship under a fine-looking aggregate. Each metric surfaces as opt / human with no weighting. The reader decides.
- **Rewrite the extractor rather than patch it.** The real rewrite drivers are R1 (two divergent copies of `baseline_extractor.py` — one in `tests/fixtures/external/`, one in `src/temper_placer/validation/`) and R2 (the dead `_check_dependencies` block importing `BoundaryLoss`, `OverlapLoss`, `KiCadDRCValidator` and using none of them). The current code is actively emitting wrong numbers via three localized failure modes (wrong function name in a swallowed `try`/`except`, hardcoded `0.0`, mislabeled alias); consolidation and dead-code removal justify a rewrite, not the rhetorical claim that patching inherits the failure discipline. The rewrite's defining constraint is that no piece of the chain swallows an exception into a recorded metric.
- **Spike on one board, expand to corpus 5, with router-comparison as the expansion — not deferred.** One board proves the wiring. Corpus 5 uses the wiring. The router-comparison metrics (RDL, via count, DRC delta) are what separates "placement quality diagnostic" from "system quality oracle" — they belong in the expansion phase of this work, not a future one.

---

## Dependencies / Assumptions

- The `piantor_right` board (`power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb`, 1.9 MB) parses correctly under the current `parse_kicad_pcb`. Verify during planning; if parse fails the spike can't proceed on this board.
- The `marocchino/sticky-pull-request-comment@v2` action (already in `pr-pipeline-scorecard.yml`) is reusable for this workflow without bespoke new comment infrastructure.
- The `_extract_traces_from_pcb` net fallback path (`str(track.net)`) is expected to produce `<Net object at 0x…>` on at least some boards when `.name` and `.number` are both unset — unverified at the time of writing but consistent with kiutils's object model. Verify during planning.
- The existing `scripts/bless_baselines.py` touches only `baseline.json` and not `human_reference.yaml`; verify during planning, and if false, add an explicit guard before this work's first bless.
- `compute_total_hpwl` on a board with a single net spanning > 1 component returns strictly positive HPWL; verify during planning (a HPWL implementation that conflates single-pin and multi-pin nets would return 0 on legitimate boards).
- The corpus gate tolerance floors (`margin_abs: 100.0` on `hpwl_final`) are inherited from the broken-baseline regime; they must be re-derived against real measurements in the expansion phase, not inherited. A metric re-named but tolerance-inherited would let the same bug class ship under a new name.
- The corpus-5 human placements are screened for competence before their metrics are treated as an accuracy oracle: each board is either maintainer-eyeballed or heuristically gated (DRC-clean, via count in an expected range, no obvious corner-packing). A board whose human placement is rough or didactic is excluded from the human-reference oracle the same way R13 excludes a board whose per-piece validation fails. Ratio=1.0 in the comment means "matches this human," not "optimal."

---

## Outstanding Questions

### Resolve Before Planning

- *None.*

### Deferred to Planning

- [Affects R3, R7][Needs research] Does `_extract_traces_from_pcb` currently lose net names on any of the corpus 5 boards, or only on boards with unusual net encodings? The fix path differs (raise-on-unresolved vs. extend the net-map lookup) depending on whether the fallback path fires on real data.
- [Affects R8][Technical] What fields exactly does `human_reference.yaml` contain? The doc names the metrics; the YAML schema (field names, nesting) is a planning decision.
- [Affects R10, R11][Technical] What does the PR comment body look like concretely? The doc specifies one block per board, per-metric ratios, adhesive-via-sticky-comment; the template (Markdown shape, ordering, units) is a planning decision.
- [Affects R5][Needs research] Is `compute_total_hpwl(positions, rotations, context)` the only HPWL entrypoint in `wirelength.py`, or are there other call sites still referencing the nonexistent `compute_hpwl(state, netlist)`? Sweep during planning to avoid leaving latent dead calls.
- [Affects R6][Technical] How is the deliberately-overlapping fixture for AE2 produced? Reuse an existing fixture generator in `tests/fixtures/generators/`, or write a minimal ad hoc one?
- [Affects R13][Technical] What is the gating mechanism that excludes a board from the comment when its per-piece validation fails? Fail the validation tests in CI and let the comment workflow detect the failure; or do per-board runtime validation inside the comparison step?