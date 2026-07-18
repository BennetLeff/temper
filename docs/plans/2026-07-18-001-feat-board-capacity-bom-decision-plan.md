---
title: "feat: Board Capacity vs. BOM — Decision-Support Artifacts and Re-Verification Infrastructure"
type: feat
status: active
date: 2026-07-18
origin: docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md
---

# Board Capacity vs. BOM — Decision-Support Artifacts and Re-Verification Infrastructure

## Summary

`pcb/temper.kicad_pcb` (149 components, 100mm x 150mm) cannot reach
zero courtyard-overlap DRC at its current size/BOM — total component
courtyard area (13,670.8 mm^2) is 108.5% of usable board area (12,600
mm^2) before any packing-inefficiency allowance, confirmed as a genuine
geometric infeasibility, not a placement-algorithm defect. Closing this
gap requires a human decision among board resize (A), BOM substitution
(B), reviewed-overlap acceptance (C), or a blend (D) — a decision this
plan does not make, because none of the options are executable without
authority this plan does not have (mechanical/enclosure sign-off for A,
circuit-design re-derivation for B, PCB-layout review for C).

This plan instead builds what an agent *can* concretely do now,
independent of which option is eventually chosen: (1) a reviewable
report of the exact courtyard/PTH violation pairs a human reviewer
needs to make the option C judgment call (or to size options A/B); (2)
a decision memo re-deriving this brainstorm's area math into concrete
per-option candidate numbers; (3) a board-dimension parsing fix that
the re-verification tooling needs to be trustworthy for any resized
board; and (4) a reusable area-sufficiency re-verification tool/test
(the brainstorm's R2) so that whichever option is chosen later, "did it
actually close the gap" is a fast, objective, repeatable check rather
than a fresh ad hoc calculation. Execution of any specific option (A,
B, or C) is scoped as explicitly deferred, decision-gated work — not
sequenced for an agent to start on its own.

---

## Requirements

Traces to the origin (`docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md`).

- **R1 — Decision-support violation report.** Produce a reviewable
  table (ref pair, violation type, location, courtyard margin involved)
  of the real 27-29 `courtyards_overlap` and 16-18
  `pth_inside_courtyard` violations from actual `kicad-cli pcb drc`
  output, so a human with PCB-layout authority can evaluate option C
  (or use the same data to inform A/B sizing). Traces origin **R1**
  (traceable/falsifiable decision) and origin **Open Question 3**
  ("no one has yet reviewed the specific flagged pairs individually").
- **R2 — Area-sufficiency decision memo.** Re-derive this brainstorm's
  own area math into concrete, option-specific numbers: candidate new
  board dimensions and the usable-area math for option A; area freed
  per candidate substitution (by component role, not part number) for
  option B; and the blended-scenario shape for option D. A memo, not
  executed code/hardware changes. Traces origin **R1**, the numeric
  parts of origin **R3-A/R3-B** (excluding the mechanical/circuit
  sign-off those sub-requirements also demand — see Scope Boundaries),
  and origin **Open Questions 1, 2, 4**.
- **R3 — Correct board-dimension parsing.** Fix
  `extract_kicad_metadata`'s hardcoded `board_width = 100.0` /
  `board_height = 150.0` fallback to parse the real `Edge.Cuts`
  polygon, so that area-sufficiency tooling (R4) produces a correct
  answer for *any* board size — including a resized board if option A
  is chosen — not just the current board where the hardcode happens to
  coincidentally match. Traces the "Related Finding" in
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`
  and is a prerequisite for R4 to be trustworthy under option A.
- **R4 — Reusable area-sufficiency re-verification mechanism.** Package
  the courtyard-area-vs-usable-area calculation this brainstorm is
  based on as a script + test, parameterized by board path, so it can
  be re-run against any future board/BOM state to confirm a shortfall
  is actually closed. Traces origin **R2** directly.
  ("Re-verify area sufficiency before declaring done.")
- **R5 — Option-specific execution is deferred and decision-gated.**
  Actually resizing the board (A), substituting BOM components (B), or
  populating a reviewed-overlap allowlist (C) are each blocked on a
  human decision and human authority this plan does not have. Traces
  origin **R3** (all three sub-parts, each of which the origin document
  itself assigns to mechanical, circuit-design, or PCB-layout-review
  authority, not to a placement/software agent) and origin's own
  framing: "No option is pre-selected."
- **R6 — Finish-the-Board plan reconciliation.** Whichever option is
  eventually chosen (or if none is chosen and overlaps are formally
  left open), `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`'s
  scope boundary ("No constraint relaxation to buy completion," "No
  footprint rebuild / real-board migration") must be either satisfied
  as originally written or explicitly amended before that plan claims
  literal-zero courtyard DRC. Traces origin **Success Criterion 3**.

**Origin actors:** none named explicitly in the origin brainstorm; this
plan's implementation units are written for A2-equivalent (an
agent/automation actor) for R1-R4, and explicitly require a human role
(mechanical engineer, circuit designer, PCB-layout reviewer, or project
lead) for R5/R6, named per unit below.

---

## Scope Boundaries

**In scope:**
- Producing the violation-pair decision-support report (R1).
- Producing the area-sufficiency decision memo with concrete
  per-option numbers (R2).
- Fixing the hardcoded board-dimension parsing bug (R3).
- Building the reusable area-sufficiency re-verification script/test
  (R4).
- Documenting the option-specific execution units as explicitly
  deferred and decision-gated (R5), so the work is scoped and ready to
  pick up the moment a decision lands, without being executed now.
- Noting the `Finish the Board` plan reconciliation as a required
  follow-up once a decision lands (R6).

**Explicitly not decided or executed by this plan:**
- **Which option (A/B/C/D) is chosen.** This plan does not recommend
  or select an option. Per the origin document: "No option is
  pre-selected — this section lays out the fork in the road for a
  human decision, not a recommendation."
- **Actually enlarging the board (option A execution).** Requires
  mechanical/enclosure authority this plan does not have — new board
  dimensions must be confirmed against enclosure fit, glass-top sizing
  (MCH-03: Glass Load 20kg gate, `docs/STRATEGY.md`), and possibly
  cost-per-unit impact, none of which a placement/software agent can
  determine.
- **Actually substituting BOM components (option B execution).**
  Requires circuit-design authority this plan does not have — each
  substituted component (L1, PS1, C2-C5, K1, U22) must be re-verified
  against its original electrical requirement (inductance/ESR for L1,
  capacitance/ripple current for C2-C5, contact rating for K1,
  thermal/power dissipation for PS1) by someone with circuit-design
  authority. Undersizing any of these risks the EFF-01/EFF-02,
  PWR-01/PWR-02 performance gates in `docs/STRATEGY.md`, not just DRC.
- **Actually accepting specific overlap pairs as reviewed-safe (option
  C execution).** Requires a human PCB-layout reviewer to inspect each
  flagged pair individually; this plan does not pre-judge which pairs
  (if any) are genuinely non-physical.

**Outside scope (separate initiatives):**
- The routing-completion work
  (`docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` and its
  successor scoped in
  `docs/brainstorms/2026-07-18-board-routing-completion-requirements.md`)
  depends on this decision landing eventually, but is not part of this
  plan and is not blocked by it in the near term. Per the origin
  brainstorm's own framing (carried forward unchanged): "the two
  threads can proceed in parallel until a resize decision (if any)
  actually lands" — routing work on the *current* board geometry may
  need to be redone if option A is eventually chosen, but that is an
  acknowledged future rework risk, not a reason to block routing work
  now.
- The single-layer-routing DRC-quality gap
  (`docs/brainstorms/2026-07-08-single-layer-route-requirements.md`) —
  an independent, non-courtyard DRC problem.
- Any further change to the placement/routing software's courtyard
  detection or resolution logic — both software bugs in that path
  (STRtree indexing, courtyard geometry extraction) are already fixed
  and confirmed not to be the cause of the remaining gap; see Context
  below.

---

## Context & Research

### Relevant Code and Patterns

- **Board-dimension hardcode (R3 target):**
  `extract_kicad_metadata` in
  `packages/temper-placer/src/temper_placer/io/kicad_metadata.py:102-104`
  — `board_width = 100.0` / `board_height = 150.0` with a `# TODO:
  Parse from edge cuts - for now use defaults` comment. The real
  `Edge.Cuts` polygon (a `GrPoly` in the `.kicad_pcb` s-expression) must
  be parsed instead. `BoardMetadata`'s `__post_init__`
  (`kicad_metadata.py:59-61`) already validates `board_width > 0` /
  `board_height > 0` — the fix should preserve this invariant and raise
  rather than silently default if `Edge.Cuts` cannot be parsed, per the
  codebase's fail-closed convention (see Institutional Learnings).
- **DRC violation extraction (R1 target):** `run_drc()` in
  `packages/temper-placer/src/temper_placer/validation/_drc_api.py:245`
  returns a `DrcResult` with `.errors: list[DrcError]`, each carrying
  `.rule` (e.g. `"courtyards_overlap"`, `"pth_inside_courtyard"`),
  `.location: tuple[float, float]`, `.message`, `.components:
  list[str]`, and `.nets: list[str]`. `.components` and `.location`
  were themselves a bug (always empty/`(0.0, 0.0)`) fixed in
  `docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md`
  — confirmed fixed and correct for `courtyards_overlap` specifically
  (`components=['D3','C4']`, real location) in that doc's verification.
  R1's report generator should call `run_drc(pcb_path)` and filter
  `errors` by `.rule in {"courtyards_overlap", "pth_inside_courtyard"}`,
  reading `.components` for the ref pair and `.location` for
  positioning — this is the documented, already-correct path; no raw
  JSON workaround is needed (that workaround predates the wrapper fix).
- **Courtyard geometry, for margin context in the R1 report:**
  `metadata.courtyards` (per-component `Courtyard` objects with
  `.points`) is populated by the (now-fixed) extraction logic in
  `io/kicad_metadata.py`'s `_extract_courtyards`. The R1 report can
  compute each flagged pair's actual overlap area/margin by loading
  both components' courtyard polygons and intersecting them with
  `shapely`, giving a reviewer a concrete number instead of only a
  ref pair.
- **Area-sufficiency calculation to package as reusable tooling (R4):**
  the exact method is described narratively in
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`
  ("Investigation" section): sum all components' courtyard polygon
  areas via `shapely`, compare against `(board_width - 2*margin) *
  (board_height - 2*margin)` (5mm margin, matching
  `CourtyardCheckStage`'s own edge margin), and report the ratio. No
  existing script does this end-to-end as reusable tooling — this
  session's number was produced ad hoc. `CourtyardCheckStage`
  (`packages/temper-placer/src/temper_placer/deterministic/stages/courtyard_check.py`)
  is the stage whose resolution loop this calculation explains the
  failure of — see its comment at line 161 referencing the 27/16 error
  counts.
- **Analysis-script convention:** ad hoc board-analysis scripts live in
  `packages/temper-placer/scripts/analysis/` (e.g. `filter_drc.py`,
  `analyze_final_drc.py`, `analyze_conflicts.py`). R1's and R4's new
  scripts should follow this location. A (currently empty)
  `packages/temper-placer/tests/analysis/` directory already exists as
  the expected test-location counterpart — R4's test belongs there.

### Institutional Learnings

- **The two software bugs behind the original zero-collision false
  report are already fixed and ruled out as the cause of the remaining
  gap** —
  `docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`:
  a Shapely `STRtree.query()` index-vs-object-identity bug, and a
  courtyard-geometry-extraction bug silently falling back to a wrong
  pad-bounding-box approximation for 142/149 footprints. Both fixed and
  regression-tested. **Do not re-investigate the placement/detection
  software as a candidate fix for the remaining 27-29/16-18 violations**
  — that door is closed; see the next learning.
- **Stable oscillation across a 10x iteration-budget increase is
  infeasibility, not slow convergence** —
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`:
  `CourtyardCheckStage`'s resolution loop oscillates between ~26-48
  unresolved pairs regardless of iteration budget (500 vs. 5000
  iterations moved the final count from 43 to 31, no downward trend).
  This is the direct evidence that the remaining gap is a board-level
  design constraint, not a software defect — the premise this entire
  plan is built on.
- **A wrapper's `.components`/`.location` fields were silently broken
  for every DRC violation type until fixed on 2026-07-17-18** —
  `docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md`.
  R1's report generator must use the now-fixed `run_drc()` wrapper, not
  reintroduce the raw-JSON hand-parsing workaround that doc describes
  as a stopgap that predates the fix.
- **A mock/fixture for external tool output must be built from a real
  captured sample, not invented from memory** (same doc, Prevention
  section) — if R4's test needs a fixture DRC/courtyard result, capture
  it from a real `kicad-cli` or `shapely` run against a small synthetic
  board, not hand-authored JSON that might silently encode the same
  wrong assumption as a bug it's meant to catch.
- **Fail-closed discipline applies to R3's fix.** Per the "Finish the
  Board" plan's R7 anti-false-zero guard pattern
  (`docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`) and the
  weak-encoding/silent-guard learnings it cites
  (`docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md`,
  `docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md`):
  R3's `Edge.Cuts` parser should raise a clear error if it cannot find
  or parse the polygon, not silently fall back to a hardcoded guess —
  the exact failure mode it is replacing.

---

## Key Technical Decisions

- **This plan produces artifacts and infrastructure, not a decision.**
  Every Implementation Unit below either (a) is executable now by an
  agent without hardware/circuit/mechanical authority, or (b) is
  explicitly marked deferred and gated on a named human decision. No
  unit commits to executing option A, B, C, or D.
- **R1's violation report reuses the already-fixed `run_drc()` wrapper**
  rather than the raw-JSON hand-parsing workaround documented as a
  stopgap in the DRC-wrapper bug doc — that workaround predates the fix
  and should not be reintroduced now that `.components`/`.location`
  are correct.
- **R3 (board-dimension parsing fix) is treated as in-scope
  infrastructure, not "option-specific execution,"** because it is
  needed for R4's re-verification tool to give a correct answer under
  *any* future board size — including whichever candidate dimensions
  option A might eventually use — not because it changes the current
  board. The current board's hardcoded values happen to already be
  correct (100x150mm), so this fix has zero effect on today's
  measurement; it only matters once a board dimension ever changes.
- **R4's re-verification tool is deliberately generic** (takes a board
  path and optional margin/packing-efficiency-assumption parameters),
  not hardcoded to `pcb/temper.kicad_pcb` at its current size, so the
  same tool checks option A's resized board, option B's
  reduced-footprint BOM, or a re-run against the unchanged board (to
  confirm option C's allowlist doesn't quietly grow) without
  modification.
- **The option C allowlist mechanism itself (origin R3-C's "encoded
  somewhere `CourtyardCheckStage`/the DRC gate can read") is treated as
  option-specific execution, not built now.** Although a schema-only,
  unpopulated allowlist could be framed as generic infrastructure, its
  only purpose is serving option C — building it now would silently
  bias toward C being the chosen path, which the origin document
  explicitly says not to do ("No option is pre-selected"). It is
  scoped under the deferred/conditional Option C unit instead.

---

## Open Questions

### Deferred to Implementation

- **R1's overlap-margin computation method.** The report should show
  "how much" each flagged pair overlaps (e.g. shapely intersection
  area, or penetration depth) to help a reviewer judge whether a
  courtyard margin is "deliberately conservative" (origin's phrase) vs.
  a real clearance conflict. The exact metric (intersection area vs.
  minimum separation distance vs. both) is an implementation judgment
  call — either is defensible; implementer should pick whichever is
  cheaper to compute correctly and document the choice in the report's
  own header.
- **R2 memo's packing-efficiency assumption range.** The origin
  brainstorm uses 50-80% "generously" as a placeholder packing
  efficiency to derive the 1.4x-2.2x board-growth range. The memo
  should either defend this range with a citation/rationale (e.g. from
  PCB layout literature for mixed rectangle/circle component packing)
  or explicitly flag it as a rough placeholder that a mechanical/PCB
  layout expert should refine before option A's exact dimensions are
  committed to hardware. Do not present the placeholder range as more
  precise than it is.
- **R4 tool's pass/fail threshold.** Should the re-verification
  tool/test assert `total_courtyard_area <= usable_area` (raw,
  optimistic) or apply a packing-efficiency safety factor (e.g. assert
  `<= 0.7 * usable_area`)? The raw check is what this brainstorm's own
  108.5% number uses; a safety-factored check is more conservative and
  arguably more honest given "100% packing efficiency is physically
  unachievable" is itself one of this investigation's findings.
  Recommend implementing both as separate reported numbers (raw ratio
  and safety-factored ratio) rather than picking one silently — leave
  the interpretation to whoever reviews a re-verification run.
- **Whether R6 (Finish-the-Board reconciliation) needs its own doc
  edit now.** This plan flags the requirement but does not diff/edit
  `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`'s scope
  boundary itself, since the correct edit depends on which option is
  chosen (satisfy as-written vs. amend). Implementer/reviewer should
  confirm this stays deferred rather than being resolved speculatively.

---

## Implementation Units

### U1. Courtyard/PTH violation-pair decision-support report

**Goal:** Produce a reviewable table of every real `courtyards_overlap`
and `pth_inside_courtyard` violation from `kicad-cli pcb drc` on
`pcb/temper.kicad_pcb`, giving a human PCB-layout reviewer (or whoever
is sizing options A/B) concrete data instead of just violation counts.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Create: `packages/temper-placer/scripts/analysis/courtyard_violation_report.py`
- Create: `packages/temper-placer/tests/analysis/test_courtyard_violation_report.py`
- Output (generated, not committed as source): a report artifact (e.g.
  `courtyard_violation_report.md` or `.json`) written to a path the
  script accepts as an argument — do not hardcode an output path
  inside the repo tree meant for source.

**Approach:**
- Call `run_drc(Path("pcb/temper.kicad_pcb"))` from
  `temper_placer.validation._drc_api`.
- Filter `result.errors` (and `result.warnings`, if kicad-cli reports
  either as a warning) to `rule in {"courtyards_overlap",
  "pth_inside_courtyard"}`.
- For each violation, extract `.components` (the ref pair, or single
  ref for PTH-inside-courtyard, which may only name the offending
  footprint), `.location`, and `.message`.
- For `courtyards_overlap` pairs specifically, load both components'
  courtyard polygons via `extract_kicad_metadata(...).courtyards[ref]`
  and compute the `shapely` intersection area as a concrete overlap
  magnitude (see Open Questions for the exact metric decision).
- Render as a table (ref pair | violation type | location | overlap
  area or PTH detail | raw kicad-cli message) sorted by overlap
  magnitude descending, so the reviewer sees the worst offenders first.
- CLI entry point accepting `--pcb <path>` and `--output <path>`,
  following the lazy-import/CLI conventions used elsewhere in
  `packages/temper-placer/scripts/analysis/`.

**Patterns to follow:**
- `run_drc()` signature and `DrcError`/`DrcWarning` fields:
  `packages/temper-placer/src/temper_placer/validation/_drc_api.py:33-76,245`
- Existing analysis-script structure (simpler style, acceptable to
  follow loosely): `packages/temper-placer/scripts/analysis/filter_drc.py`
- Courtyard polygon access: `metadata.courtyards` from
  `extract_kicad_metadata()`,
  `packages/temper-placer/src/temper_placer/io/kicad_metadata.py`

**Test scenarios:**
- Happy path: run against a small synthetic fixture PCB with a known,
  hand-verified courtyard overlap → report contains that pair with a
  nonzero overlap area.
- Real-board smoke test (marked slow/integration, skip if `kicad-cli`
  unavailable): run against `pcb/temper.kicad_pcb` → report row count
  is in the 27-29 (`courtyards_overlap`) + 16-18
  (`pth_inside_courtyard`) range documented in the origin brainstorm;
  assert this as a range check, not an exact count, since the origin
  doc itself reports the count as varying run-to-run within that band.
- Edge case: a `pth_inside_courtyard` violation with only one
  extractable component ref (no pair) → reported without erroring.

**Verification:**
- `uv run python packages/temper-placer/scripts/analysis/courtyard_violation_report.py --pcb pcb/temper.kicad_pcb --output /tmp/report.md` produces a non-empty report with one row per real violation.
- `uv run pytest packages/temper-placer/tests/analysis/test_courtyard_violation_report.py -v` passes.

---

### U2. Area-sufficiency decision memo (per-option numbers)

**Goal:** Re-derive this brainstorm's area math into concrete,
citable, per-option candidate numbers a human decision-maker can act
on directly — not a fresh piece of code, a written memo.

**Requirements:** R2

**Dependencies:** U4 (should use the packaged re-verification
calculation from R4 rather than recompute ad hoc, once U4 exists —
sequence U2 after U4 if convenient, or compute manually and cross-check
against U4's tool once it lands)

**Files:**
- Create: `docs/solutions/architecture-patterns/board-capacity-bom-decision-memo-2026-07-18.md`
  (or append as a dated addendum to the existing
  `production-board-courtyard-area-exceeds-usable-board-area.md` if
  that reads more naturally at implementation time — implementer's
  call, document the choice)

**Approach:**
- **Option A numbers:** for each candidate scale factor in the
  1.4x-2.2x usable-area range (e.g. 1.4x, 1.7x, 2.0x, 2.2x), compute a
  concrete `(width, height)` pair that both hits the target usable area
  and stays a plausible board aspect ratio (the current board is
  100x150mm, a 2:3 ratio — candidates should likely preserve this ratio
  unless there's a documented mechanical reason not to). Show the
  resulting usable area (after the same 5mm margin) and its ratio to
  the 13,670.8 mm^2 courtyard-area requirement.
- **Option B numbers:** for each of the 8 largest components (L1,
  PS1, C2-C5, K1, U22 — 7,860.1 mm^2 combined, 57.5% of total), compute
  what fraction of the total shortfall (13,670.8 - 12,600 = 1,070.8
  mm^2 minimum, or more under realistic packing efficiency) would be
  closed by a 25%/50%/75% area reduction of that component alone, and
  cumulatively across the top-N components. This is deliberately a
  *leverage* calculation (which components matter most), not a
  proposed replacement part number — replacement parts are explicitly
  outside this plan's scope (see Scope Boundaries).
- **Option D shape:** using the A and B numbers above, sketch 2-3
  concrete blended scenarios (e.g. "1.2x board growth (120x180mm) +
  50% reduction on the top-3 components would close X% of the gap") so
  a decision-maker has a real blended data point, not just "not yet
  analyzed" (the origin document's current state for option D).
- Explicitly flag every number's dependency on the 50-80% packing
  efficiency placeholder (see Open Questions) so the memo doesn't
  overstate its own precision.
- Cross-reference `docs/STRATEGY.md`'s MCH-03 (Glass Load 20kg),
  EFF-01/EFF-02, PWR-01/PWR-02 gates by name next to the options they
  constrain (A → MCH-03 and enclosure risk; B → EFF/PWR risk for
  undersized bulk caps/inductor), without asserting whether those gates
  would actually be violated — that determination needs the
  mechanical/circuit authority this plan doesn't have.

**Patterns to follow:**
- Structure and tone of the existing area-shortfall doc:
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`
  (frontmatter, Investigation/Conclusion/Why This Matters sections).

**Test scenarios:** N/A — this is a documentation deliverable, not
code. "Test" is human review: does every number trace back to a
formula and an input the reviewer can independently re-check.

**Verification:**
- Every number in the memo cites its formula and inputs (board
  dimensions, courtyard areas, assumed packing efficiency) so a
  reviewer can recompute it independently.
- The memo does not recommend an option — consistent with R5/the
  origin document's "no option is pre-selected."

---

### U3. Fix hardcoded board-dimension parsing in `extract_kicad_metadata`

**Goal:** Replace the hardcoded `board_width = 100.0` / `board_height =
150.0` fallback in `extract_kicad_metadata` with real parsing of the
`Edge.Cuts` `GrPoly` polygon, so board-size-dependent tooling (notably
R4) gives a correct answer for any board, not just the current one.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/io/kicad_metadata.py`
  (the `extract_kicad_metadata` function, around lines 96-118)
- Test: `packages/temper-placer/tests/io/test_kicad_metadata_board_dimensions.py`

**Approach:**
- Locate the `Edge.Cuts` layer's graphic items in the parsed `.kicad_pcb`
  (kiutils board object) — likely `GrPoly`, `GrLine`, or `GrRect` items
  on layer `"Edge.Cuts"`, following the same "recognize the real shape
  types" lesson the courtyard-extraction bug fix already had to learn
  (`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`'s
  "Second Root Cause" — do not repeat the "only handles one shape type"
  mistake for board-edge parsing).
- Compute the bounding box of the `Edge.Cuts` geometry; `board_width` =
  max_x - min_x, `board_height` = max_y - min_y.
- If no `Edge.Cuts` geometry is found or it degenerates to zero area,
  raise a clear exception (do not silently fall back to 100x150) —
  fail-closed, per the Institutional Learnings above.
- Verify against `pcb/temper.kicad_pcb`: parsed dimensions must equal
  the currently-hardcoded 100.0 x 150.0 (this board's real `Edge.Cuts`
  corners are confirmed `(0,0)` to `(100,150)` per the origin
  brainstorm's own verification) — this is the regression check that
  proves the fix doesn't change today's behavior, only future
  correctness.

**Patterns to follow:**
- The courtyard-extraction fix's multi-shape-type handling (`FpRect`,
  `FpLine`, `FpCircle`, unioned via `shapely.ops.unary_union`) in
  `io/kicad_metadata.py`'s `_extract_courtyards` — Edge.Cuts parsing
  should follow the same "handle every real shape KiCad might use,
  fail loudly if none match" discipline, though `GrPoly`/`GrLine`/`GrRect`
  (board-edge shapes) are a different kiutils type family than the
  `Fp*` footprint-graphic types `_extract_courtyards` handles.

**Test scenarios:**
- Regression: `extract_kicad_metadata(Path("pcb/temper.kicad_pcb"))`
  returns `board_width == 100.0` and `board_height == 150.0` (matches
  today's hardcoded value, on the real board).
- New coverage: a synthetic fixture PCB with a deliberately
  non-100x150 `Edge.Cuts` rectangle (e.g. 120x170mm) → parsed
  dimensions match the fixture, not the old hardcode.
- Error path: a fixture PCB with no `Edge.Cuts` layer at all → raises a
  clear exception, not a silent 100x150 default.

**Verification:**
- `uv run pytest packages/temper-placer/tests/io/test_kicad_metadata_board_dimensions.py -v` passes.
- `BoardMetadata.__post_init__`'s existing positive-dimension
  validation (`kicad_metadata.py:59-61`) still holds for all cases.

---

### U4. Reusable area-sufficiency re-verification tool + test

**Goal:** Package the courtyard-area-vs-usable-area calculation this
brainstorm is based on as a standalone, board-path-parameterized
script and pytest, so "did the shortfall actually close" is a fast,
objective, re-runnable check against whichever board/BOM state exists
after a decision lands — this is the brainstorm's own R2 requirement,
built as option-agnostic infrastructure now rather than deferred.

**Requirements:** R4 (packages origin R2)

**Dependencies:** U3 (needs correct board-dimension parsing to be
trustworthy for a resized board under option A)

**Files:**
- Create: `packages/temper-placer/scripts/analysis/area_sufficiency_check.py`
- Create: `packages/temper-placer/tests/analysis/test_area_sufficiency_check.py`

**Approach:**
- Accept `--pcb <path>` and optional `--margin-mm` (default 5.0,
  matching `CourtyardCheckStage`'s own edge margin) and
  `--packing-efficiency` (default: report both the raw 100%-efficiency
  ratio and one or more safety-factored ratios — see Open Questions;
  do not silently pick one).
- Load board dimensions via the now-fixed `extract_kicad_metadata`
  (U3) and all components' courtyard polygons via
  `metadata.courtyards`.
- Sum courtyard polygon areas with `shapely` (reuse the same union/area
  logic pattern as the courtyard-extraction fix, not a re-derivation
  that could silently diverge from it).
- Compute `usable_area = (board_width - 2*margin) * (board_height -
  2*margin)`.
- Report: total courtyard area, usable area, raw ratio (%), and
  ratio at each supplied packing-efficiency assumption. Exit 0 if raw
  ratio <= 100% (or the configured threshold), exit nonzero otherwise
  — usable as a CI-style gate, not just a human-read report.
- This tool is the mechanism U2's memo numbers should ultimately be
  cross-checked against, and the mechanism whoever executes option
  A/B/C later runs to confirm their change actually closed the gap
  (R6's re-verification step).

**Patterns to follow:**
- The narrative calculation method in
  `docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md`
  ("Investigation" section) — this unit is that calculation, packaged.
- `CourtyardCheckStage`'s own 5mm edge-margin constant
  (`packages/temper-placer/src/temper_placer/deterministic/stages/courtyard_check.py`)
  — the default margin must match, not drift independently.

**Test scenarios:**
- Regression: run against `pcb/temper.kicad_pcb` as-is → raw ratio
  reports ~108.5% (matching the origin brainstorm's number to within a
  small tolerance, since the brainstorm's own number came from a
  single manual run), exit code nonzero (shortfall not closed).
- Synthetic pass case: a fixture board sized generously larger than its
  components' total courtyard area → raw ratio < 100%, exit code 0.
- Synthetic fail case: a fixture board deliberately undersized → raw
  ratio > 100%, exit code nonzero, and the reported numbers match a
  hand-computed expected value exactly (this is the test that proves
  the tool's arithmetic itself is trustworthy, independent of any real
  board).
- Margin/packing-efficiency parameters: passing a nonstandard
  `--margin-mm` or `--packing-efficiency` changes the reported ratio in
  the expected direction (larger margin → smaller usable area → higher
  ratio; lower packing efficiency → higher effective-requirement
  ratio).

**Verification:**
- `uv run python packages/temper-placer/scripts/analysis/area_sufficiency_check.py --pcb pcb/temper.kicad_pcb` reports ~108.5% and exits nonzero, matching this brainstorm's documented finding exactly (this is the tool's own self-check against known-correct ground truth).
- `uv run pytest packages/temper-placer/tests/analysis/test_area_sufficiency_check.py -v` passes.

---

### U5. [Deferred — decision-gated] Execute option A: enlarge the board

**Goal:** If and when a human with mechanical/enclosure authority
chooses option A, resize `Edge.Cuts` in `pcb/temper.kicad_pcb` to the
chosen candidate dimensions (from U2's memo) and re-run placement.

**Requirements:** R5 (origin R3-A)

**Dependencies:** U2 (candidate numbers), U4 (post-change
re-verification)

**Blocked until:** a mechanical/enclosure engineer (or whoever holds
that authority on this project) confirms the chosen new board
dimensions fit the enclosure and glass-top design (MCH-03: Glass Load
20kg gate, `docs/STRATEGY.md`) and signs off on the specific
`(width, height)` pair to use. **This plan does not select that
number and does not start this unit.**

**Files (once unblocked):**
- Modify: `pcb/temper.kicad_pcb` (`Edge.Cuts` polygon)
- Re-run: the deterministic placement pipeline against the resized
  board.

**Approach (once unblocked):**
- Update `Edge.Cuts` to the signed-off dimensions.
- Re-run placement end-to-end; confirm `CourtyardCheckStage`'s
  resolution loop now converges (or re-diagnose if it still doesn't,
  per the same infeasibility-check method this plan's U4 packages).
- Run U4's `area_sufficiency_check.py` against the resized board;
  confirm exit code 0 (raw ratio <= 100%) before declaring the
  shortfall closed.
- Feed into R6 (Finish-the-Board plan reconciliation) — this is a
  board/BOM change, so that plan's scope boundary needs an explicit
  amendment, not silent satisfaction.

**Test scenarios (once unblocked):** placement pipeline succeeds on
the resized board; `CourtyardCheckStage` converges to 0 unresolved
pairs (or a documented, reduced residual); U4's tool reports the
shortfall closed.

**Verification (once unblocked):** U4's re-verification tool exits 0
against the resized board; kicad-cli DRC shows 0
`courtyards_overlap`/`pth_inside_courtyard` (or a documented residual
if convergence is still imperfect at the new size).

---

### U6. [Deferred — decision-gated] Execute option B: shrink/relocate BOM

**Goal:** If and when a human with circuit-design authority chooses
option B, substitute specific components (from U2's leverage ranking:
L1, PS1, C2-C5, K1, U22) with smaller-package alternatives that still
meet their original electrical requirements.

**Requirements:** R5 (origin R3-B)

**Dependencies:** U2 (leverage ranking), U4 (post-change
re-verification)

**Blocked until:** for each proposed substitution, someone with
circuit-design authority re-verifies the replacement part against the
original electrical requirement (inductance/ESR for L1,
capacitance/ripple current for C2-C5, contact rating for K1,
thermal/power dissipation for PS1) — not inferred from courtyard area
alone. **This plan identifies which components are highest-leverage
(U2) but does not select replacement part numbers and does not start
this unit.**

**Files (once unblocked):**
- Modify: BOM/schematic source for the substituted component(s) and
  their footprint assignment in `pcb/temper.kicad_pcb`.

**Approach (once unblocked):**
- Apply the circuit-design-approved substitution(s).
- Re-run placement; run U4's `area_sufficiency_check.py` against the
  updated BOM to confirm the shortfall is closed or measurably reduced
  by the expected amount from U2's leverage calculation.
- Feed into R6 — this is also a board/BOM change requiring explicit
  Finish-the-Board plan reconciliation.

**Test scenarios (once unblocked):** each substituted component's
footprint area matches the expected reduction; U4's tool shows the
predicted ratio improvement; no EFF-01/EFF-02/PWR-01/PWR-02 regression
(verified by whoever holds that test authority, outside this plan's
scope).

**Verification (once unblocked):** U4's re-verification tool shows a
measurable ratio improvement matching U2's predicted leverage for the
chosen substitution(s).

---

### U7. [Deferred — decision-gated] Execute option C: reviewed-overlap allowlist

**Goal:** If and when a human PCB-layout reviewer individually reviews
the violation pairs from U1's report and judges some genuinely
non-physical, build the allowlist mechanism origin R3-C requires (an
explicit list `CourtyardCheckStage`/the DRC gate can read) and populate
it with the reviewed pairs.

**Requirements:** R5 (origin R3-C)

**Dependencies:** U1 (the violation report a reviewer works from)

**Blocked until:** a human with PCB-layout authority reviews each
flagged pair from U1's report individually and writes a one-line
justification per accepted pair (e.g. "courtyard margin conservative
for tall connector J1, no physical clearance conflict with adjacent
low-profile part," per the origin document's own example). **This plan
does not pre-judge which pairs, if any, are acceptable and does not
start this unit** — building the allowlist mechanism before any pairs
are reviewed would implicitly bias toward option C being chosen, which
the origin document explicitly avoids doing.

**Files (once unblocked):**
- Create: an explicit allowlist file/config (format TBD by
  implementer at that time — e.g. YAML keyed by sorted ref pair, each
  entry carrying the reviewer's justification string) readable by
  `CourtyardCheckStage` and/or the DRC gate.
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/courtyard_check.py`
  and/or the DRC gate to consult the allowlist and treat listed pairs
  as non-violations, while still flagging any *new*, unlisted pair
  (drift detection — the origin document's explicit requirement: "so
  future drift is caught").

**Approach (once unblocked):**
- Encode reviewed pairs with their justification, not a blanket
  threshold fudge (origin R3-C's explicit constraint: "an explicit
  allowlist, not a threshold fudge").
- Wire the allowlist into both `CourtyardCheckStage`'s resolution loop
  (stop trying to nudge apart pairs that are allowlisted) and the DRC
  gate (treat allowlisted `courtyards_overlap`/`pth_inside_courtyard`
  kicad-cli findings as expected, not a gate failure) — this needs both
  sides updated in the same change; allowlisting only one would leave
  the other producing a false read.
- Feed into R6 — if fully covered by the allowlist (no board/BOM
  change), the Finish-the-Board plan's scope boundary may be satisfied
  as originally written; document this explicitly either way.

**Test scenarios (once unblocked):** an allowlisted pair no longer
triggers `CourtyardCheckStage` nudging or a DRC gate failure; a
non-allowlisted new overlap (simulated by adding one) still triggers
both — proving the allowlist doesn't accidentally widen into a
threshold fudge.

**Verification (once unblocked):** DRC gate reports CLEAN with the
allowlist applied and UNMEASURED/VIOLATIONS if the allowlist file is
missing or a new unlisted overlap appears (fail-closed, matching the
two-tier acceptance gate pattern in
`docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`).

---

## System-Wide Impact

- **Interaction graph:** U1 and U3 are independent and can run in
  parallel. U2 depends conceptually on U4's method (can be drafted in
  parallel and cross-checked once U4 lands). U4 depends on U3. U5/U6/U7
  are mutually exclusive-or-combinable option executions, each blocked
  independently on a different human decision/authority, and each
  depends on U2 (numbers) and U4 (re-verification) once unblocked.
- **No changes to placement/routing/courtyard-detection software
  logic.** U3 touches board-dimension *parsing* only (a metadata
  extraction path), not courtyard detection, collision resolution, or
  DRC logic — those are already fixed and out of scope per the
  Institutional Learnings above.
- **Relationship to `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md`:**
  that plan's scope boundary is not touched by this plan directly (R6
  documents the requirement to reconcile it later, once an option is
  chosen); this plan does not edit that file.
- **Relationship to `docs/brainstorms/2026-07-18-board-routing-completion-requirements.md`:**
  parallel, non-blocking. Routing-completion work may proceed against
  the current board geometry concurrently with this plan's U1-U4; only
  if option A is eventually chosen would routing work done on the
  current geometry need to be redone — an acknowledged future risk, not
  a present blocker, matching that sibling brainstorm's own scope
  boundary language.
- **CI/tooling surface:** U1's and U4's scripts are new, standalone
  analysis tools under `packages/temper-placer/scripts/analysis/` —
  neither is wired into any existing CI gate by this plan (that would
  be a decision to reconsider once an option is chosen and R6 is
  resolved).

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| U1's report is treated as a decision by someone skimming it, rather than input to one | Report explicitly states it does not judge which pairs are safe — that judgment is U7's, requiring a named human reviewer |
| U2's memo numbers get treated as committed engineering targets rather than a re-derivation of the brainstorm's placeholder math | Memo explicitly flags the 50-80% packing-efficiency assumption as a placeholder pending mechanical/PCB-layout refinement (see Open Questions) |
| U3's fix accidentally changes behavior for the current board (it shouldn't, since 100x150mm is correct either way) | Regression test asserts parsed dimensions match today's hardcoded values exactly before this fix ships |
| U4's tool's packing-efficiency default is later misread as a validated engineering constant rather than the brainstorm's own "50-80%, generously" placeholder | Tool reports both raw and safety-factored ratios explicitly labeled, no single hidden default silently gates a decision |
| U5/U6/U7 accidentally get started before their blocking decision actually lands, because "the plan already scoped it" reads as permission | Each unit's Approach opens with an explicit "Blocked until [role] does [action]" sentence; this plan's Summary states no option is selected |
| A future implementer resumes this plan and treats U5/U6/U7's presence as evidence a decision was already made | R6 and this plan's Summary both explicitly restate "no option pre-selected" as of this plan's authoring date |

---

## Success Metrics

This plan's own success (distinct from the underlying board-capacity
decision, which remains a human call):

1. U1's violation report exists and is usable by a human reviewer
   without further data-gathering (ref pairs, locations, overlap
   magnitudes, all present).
2. U2's memo gives concrete, formula-traceable numbers for options A,
   B, and a sketched D — no "we'll make it fit" language, per origin
   R1.
3. U3's fix is regression-tested and does not change the current
   board's measured dimensions.
4. U4's tool independently reproduces the origin brainstorm's 108.5%
   finding on the current board, and is generically re-runnable against
   any future board/BOM state per origin R2.
5. U5/U6/U7 remain explicitly unexecuted until their named blocking
   decision/authority is satisfied — verified by their Approach
   sections' "Blocked until" language, not by any code being merged.

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md](../brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md)
- **Root area-shortfall analysis:** [docs/solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md](../solutions/architecture-patterns/production-board-courtyard-area-exceeds-usable-board-area.md)
- **Software-bugs-ruled-out doc:** [docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md](../solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
- **DRC wrapper `.components`/`.nets` fix:** [docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md](../solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md)
- **Stalled routing plan whose scope boundary this decision affects:** [docs/plans/2026-07-10-001-feat-finish-the-board-plan.md](2026-07-10-001-feat-finish-the-board-plan.md)
- **Parallel, non-blocking sibling brainstorm:** [docs/brainstorms/2026-07-18-board-routing-completion-requirements.md](../brainstorms/2026-07-18-board-routing-completion-requirements.md)
- **Two-tier acceptance gate pattern (for U7's allowlist gate behavior):** [docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md](../solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md)
- **Fail-closed / anti-false-zero precedent (for U3's parsing fix):** [docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md](../solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md), [docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md](../solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md)
- **Strategy gates referenced (MCH-03, EFF-01/02, PWR-01/02):** [docs/STRATEGY.md](../STRATEGY.md)
- Related code: `packages/temper-placer/src/temper_placer/io/kicad_metadata.py`, `packages/temper-placer/src/temper_placer/validation/_drc_api.py`, `packages/temper-placer/src/temper_placer/deterministic/stages/courtyard_check.py`
