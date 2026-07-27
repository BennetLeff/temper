---
date: 2026-07-26
topic: repo-orientation-and-structural-cleanup
---

# Repo Orientation and Structural Cleanup

## Summary

Make the repository's entry point incapable of lying: `README.md` keeps hand-written
identity and build instructions, while every claim about *current state* is generated
from source and enforced by the existing derived-doc drift gate. Alongside it, remove
committed junk from the repo root, dedupe `AGENTS.md`, generate the `docs/` indexes
from frontmatter, and merge the three package directories already verified as
vestigial.

---

## Problem Frame

Opening this repository cold does not answer "where do I start." Three things are
true at once.

**The front door is confidently wrong about the most important thing.**
`README.md:20-22` states that "All safety gates — over-current, over-voltage, thermal
shutdown, UVLO — are hardware-latched with firmware monitoring." `docs/STRATEGY.md`
records that OVP-01 is fail-open and can never trip, that OCP-02 and desaturation
protection have no implementing circuit at all, and that 0 of 22 gates have been
measured on hardware. The README also frames the placer pipeline as the project's
accomplishment; `STRATEGY.md` v3.0 opens by reversing exactly that premise. A reader
who trusts the README is misinformed about the safety case.

**This is a known failure class that has already cost real engineering work.** Twice
this week, reasoning from a lossy summary produced wrong results: a protection-gate
table that had silently dropped its hysteresis and recovery columns caused three
incorrect protection fixes on 2026-07-26, and `docs/hardware/PROTECTION_CHAIN_REVIEW.md`
still carries the same defect. The README is the same species — a stale summary of a
source that moved.

**Hand-maintained state in this repository decays in hours, not months.**
`docs/plans/README.md` was written in commit `cac98f5d` on 2026-07-25 and claims
`active` = 1, "Only `2026-06-28-004`". Frontmatter today shows **4** active plans; two
of them were added by `3b0e839d`, **the same day**. The index was falsified by the very
next commit. This is the decisive evidence against rewriting any of these documents by
hand.

(An earlier draft of this document said 5. That came from grepping `^status: active`
across whole files, which also matches
`docs/plans/2026-06-23-004-feat-seed-filtering-plan.md` — a document containing a
**committed, unresolved merge conflict** whose far side carries `status: active` at
line 246 while its frontmatter says `completed`. Frontmatter-only parsing gives 4.
See the conflict-marker finding under Dependencies / Assumptions.)

Around that, the map covers less than a third of the territory — the README's Project
Structure table documents **6 of 20** tracked top-level directories — and the root is a
junk drawer with some of the junk committed (`.DS_Store`, `.hypothesis/`,
`temp_routing_test/` are all tracked). `AGENTS.md`, the file every agent reads before
touching anything, is 430 lines and contains the same `--init` Workflow section twice,
at lines 293 and 346.

Notably, the pain is *not* inline hacks: there are only 23 `TODO`/`FIXME`/`HACK`
markers across 557 source files. The "thousand bandaids" feeling is structural —
vestigial packages, uncovered territory, and documents that assert things no longer
true.

---

## Actors

- A1. **Returning maintainer**: opens the repo after time away and needs current state
  and next action within a minute, without reading 1,310 lines of `STRATEGY.md`.
- A2. **Coding agent**: reads `AGENTS.md` and `README.md` at session start; acts on
  whatever they assert, including when it is false.
- A3. **CI**: regenerates derived content and blocks merges where committed content has
  drifted from source.

---

## Key Flows

- F1. Cold re-entry
  - **Trigger:** A1 opens the repository with no recent context.
  - **Actors:** A1
  - **Steps:** Read `README.md` top-to-bottom. Identity and build commands are prose.
    A generated state block reports the gate matrix, measured-vs-unmeasured counts,
    active plan list, package inventory, and top-level directory map. Judgment calls
    are one link away in `STRATEGY.md`, not restated.
  - **Outcome:** A1 knows what the project is, what state it is in, and what the
    current active work is, without opening a second long document.
  - **Covered by:** R1, R2, R3, R4, R12

- F2. Drift interception
  - **Trigger:** A2 or A1 changes a source of truth (a gate criterion, a plan's
    `status:`, a package directory) and commits without regenerating.
  - **Actors:** A2, A3
  - **Steps:** CI regenerates the derived blocks and compares against the committed
    copy. A mismatch fails the job, naming the drifted field and the source that
    contradicts it. A tool error also fails, and is never soft-launched.
  - **Outcome:** Committed state claims cannot silently diverge from source.
  - **Covered by:** R5, R6, R7

---

## Requirements

**Entry point**

- R1. `README.md` separates hand-written content (what Temper is, how to build and test
  it, how to contribute) from a generated state block delimited by explicit markers.
- R2. The README asserts **no hand-copied facts** about current state. Any state claim
  either lives inside the generated block or is replaced by a link to its source of
  truth.
- R3. The README's existing safety-gate claim at `README.md:20-22` is removed and
  replaced by generated content plus a link, since it is presently false.
- R4. The generated block reports, at minimum: the safety and performance gate matrix
  with measured/unmeasured status; counts of plans by `status:`; the list of `active`
  plans; the package inventory; and a complete map of tracked top-level directories.

**Generated state and drift enforcement**

- R5. Generated blocks are produced by a committed generator, run in CI, following the
  pattern already established by `scripts/gen_architecture_poster.py` and
  `.github/workflows/architecture-poster.yml`.
- R6. Drift between committed and regenerated content is enforced by
  `scripts/check_derived_doc_drift.py`, which already parses markdown pipe tables for
  this purpose. Generated tables are shaped so that gate can consume them.
- R7. The drift check for these blocks **fails closed from the first commit** — no
  `continue-on-error`, no `CUTOVER_DATE` soft launch, no allowlist. This is possible
  precisely because generated content starts clean, and it is required because the repo
  already carries 36 `continue-on-error: true` steps across 24 workflows.
- R8. Only mechanically-derivable facts enter generated blocks. Prose judgment (for
  example "OVP-01 is fail-open", or which work is on the critical path) remains in
  `docs/STRATEGY.md` and is linked, never summarized.

**Documentation indexes**

- R9. `docs/plans/README.md` and `docs/solutions/README.md` status tables are generated
  from existing document frontmatter rather than hand-maintained.
- R10. No file under `docs/brainstorms/`, `docs/plans/`, or `docs/solutions/` is moved,
  renamed, or deleted. These are the compound-engineering knowledge wiki, and
  `docs/plans/README.md` records that ~105 code and config references point into that
  directory, including provenance breadcrumbs in `packages/temper-drc-rs/` and
  `scripts/`.

**Repository hygiene**

- R11. Committed artifacts that should never have been tracked are removed from version
  control: `.DS_Store`, `.hypothesis/`, and `temp_routing_test/`.
- R12. Untracked root clutter is either gitignored or removed, and any root entry that
  survives is accounted for in the generated directory map. Known entries:
  `refined.mesh` (1 MB), `mfem_mesh/`, `drc_summary.txt`, `regression-report.json`,
  `fp-info-cache`, `worktrees/`, plus the agent-tool directories.
- R13. `tests/` and `test-boards/` are untracked yet read as load-bearing from their
  names. Each is resolved explicitly — tracked, gitignored, or removed — so neither
  remains ambiguous.

**Agent instructions**

- R14. `AGENTS.md` is deduplicated. The `--init` Workflow section appears twice (lines
  293 and 346); one copy is removed and the remaining copy is authoritative.
- R15. The `<!-- BEGIN:CLAUDE -->` / `<!-- BEGIN:GEMINI -->` marker fences are removed
  or documented. No script in the repository writes them — they are vestigial from an
  older merge of `CLAUDE.md` and `GEMINI.md`, and they falsely imply machine-managed
  content.

**Package consolidation**

- R16. Three package directories verified as vestigial in
  `docs/plans/2026-07-25-003-refactor-package-consolidation-plan.md` are merged into
  their parents: `temper-geometry-core` (437 LOC) into `temper-geometry`,
  `temper-dsn-core` (222 LOC) into `temper-dsn`, and `temper-ipc-core` (190 LOC) into
  `temper-ipc`.
- R17. `temper-rust-router-core` is **not** merged. That plan found it load-bearing —
  it has two genuine Rust consumers.
- R18. Test suites, import-linter contracts, and CI pass after the merges. Narrow edits
  to `.importlinter` contracts are permitted where a merge makes a contract obsolete;
  new allowlist entries are not.

---

## Acceptance Examples

- AE1. **Covers R5, R6, R7.** Given a clean tree, when a maintainer edits a gate
  threshold in `FUNCTIONAL_TEST_CRITERIA.md` and commits without regenerating, CI fails
  and names the drifted gate row and the source value that contradicts it.
- AE2. **Covers R7.** Given the drift generator itself raises an error, when CI runs,
  the job exits non-zero rather than reporting "no drift" — a gate that cannot run never
  passes.
- AE3. **Covers R9.** Given a plan's frontmatter changes from `active` to `completed`,
  when the index is regenerated, the status table reflects the new count with no manual
  edit. The `active` = 1 versus actual = 5 discrepancy is unreachable by construction.
- AE4. **Covers R2, R8.** Given `STRATEGY.md` revises which work is on the critical
  path, when nothing else changes, the README needs no edit — it links rather than
  restates.
- AE5. **Covers R16, R18.** Given the three `-core` merges have landed, when the full
  Python and Rust suites plus `scripts/import_linter_gate.py` run, all pass with no new
  allowlist entries.

---

## Success Criteria

- A1 opens the repository cold and can state what Temper is, what state it is in, and
  what the active work is, within one minute and without opening `STRATEGY.md`.
- No claim in `README.md` about current state can be falsified by the repository at any
  commit where CI is green.
- The `docs/plans/README.md` failure — an index contradicted by the next commit — cannot
  recur, because the index is derived.
- Tracked top-level directories are 100% accounted for in the generated map, up from
  6 of 20.
- `packages/` contains 15 directories, down from 18, with no functional change.
- A downstream implementer needs no product decisions from this document: every
  requirement is either observable in CI or a named file-level change.

---

## Scope Boundaries

- The dead-gate and allowlist layer is out of scope: 36 `continue-on-error: true`
  steps, the ~2,086 burn-down entries inventoried in
  `docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md`, and the 5 gates that
  plan found dead-wired. That plan already exists and is the right home.
- The **9** files under `packages/temper-placer/tests/requirements/` whose validators
  raise `NotImplementedError` — including IEC 60335-2-6 creepage and clearance — are not
  fixed here, despite having zero executed coverage today. (This was 11 when first
  measured; `validators/ground_plane.py` and `validators/emi_filter.py` were implemented
  concurrently by commits `eb3b38fb` and `7ab70a65` during this brainstorm.)
- The 15 source files over 800 LOC are not decomposed, and the test-versus-source LOC
  imbalance (131k vs 119k) is not addressed.
- `temper-placer` internals are untouched, though it is 88% of package source.
- No document under `docs/brainstorms/`, `docs/plans/`, or `docs/solutions/` is moved
  or deleted (see R10).
- No design, schematic, or firmware change. This work is documentation and repository
  structure only, consistent with `STRATEGY.md` placing design completion — not tooling
  — on the critical path.

---

## Key Decisions

- **Generated-and-gated over hand-written**: `docs/plans/README.md` was falsified by the
  next commit on the same day. Hand-maintained state in this repository has an
  observed half-life measured in hours, so a hand-written honest README would be wrong
  again within days.
- **Reuse the existing drift gate rather than build a new mechanism**:
  `scripts/check_derived_doc_drift.py` already parses markdown pipe tables and diffs
  derived documents against sources. Building a second mechanism would add carrying
  cost for no benefit.
- **Fail closed from day one**: the existing drift gate is soft-launched to 2026-08-02
  only because the current tree has live findings. Generated blocks start clean, so
  this gate has no reason to be soft — and adding a 37th soft-failing CI step would
  reproduce the exact disease being cleaned up.
- **Index the wiki rather than prune it**: the historical plans are the compounding
  asset of the compound-engineering workflow, and ~105 code references pin the files in
  place regardless. Tidiness is not worth breaking traceability.
- **Bounded scope over comprehensive**: 69 of 147 plans in this repository are stale or
  abandoned — a 47% non-completion rate. Completability is the binding constraint, so
  the bandaid factory is deferred to a plan that already exists rather than absorbed
  here.
- **The README gets shorter**: consequence of R2 and R8. Deferring judgment to
  `STRATEGY.md` means a blunter, less narrative front page than today's.

---

## Dependencies / Assumptions

- `scripts/check_derived_doc_drift.py` can be pointed at new derived documents without
  structural change. Verified that it parses pipe tables generically and supports
  source-to-derived comparison; not yet verified that its locator model fits every
  table shape R4 requires.
- Sources of truth for R4's generated content exist and are machine-readable:
  `FUNCTIONAL_TEST_CRITERIA.md` for gate definitions, `docs/evidence/*.json` for
  measured results, plan frontmatter for statuses, and the filesystem for inventory.
  Assumed sufficient; the mapping from evidence files to gate rows is not yet traced
  end to end.
- Plan 003's dependency analysis for the three `-core` merges is accurate. It reports
  verified Cargo and pyproject edges, and its two other conclusions —
  deleting `temper-validation` and `temper_placer/constraint_types/` — are confirmed
  landed, which raises confidence in the rest.
- `elec/build/` is gitignored and has never been tracked, so no generated state may be
  derived from netlist artifacts without first establishing their provenance.

**Findings surfaced while implementing this, each verified and none anticipated:**

- **Three documents carry committed, unresolved merge-conflict markers**:
  `docs/plans/2026-06-23-004-feat-seed-filtering-plan.md` (conflicted across its entire
  437-line length — `<<<<<<<` at line 2, `=======` at 243, `>>>>>>>` at 437),
  `docs/plans/2026-06-23-001-feat-hv-lv-guard-strip-plan.md`, and
  `docs/brainstorms/2026-06-28-live-terminal-dashboard-requirements.md`. Resolving them
  needs a human decision about which side is authoritative. Note that
  `check-merge-conflict` **is already configured** in `.pre-commit-config.yaml` — by
  default it only fires during an active merge state, so markers committed outside a
  merge are never seen. A CI grep for `^<<<<<<< ` plus `^>>>>>>> ` would close this.
- **`pyproject.toml` referenced a package that does not exist**: `temper-autoprof` had a
  `[tool.uv.sources]` mapping, a `testpaths` entry, and a `pythonpath` entry, while
  absent from `uv.lock` and from the dependency group. Removed. One dead reference
  remains at `scripts/gen_architecture_poster.py:588`, which also still names
  `temper-tools`, removed in `348fe457`.
- **Five `.DS_Store` files were tracked**, not one, despite `.gitignore:64` predating
  them — ignore rules never apply retroactively to tracked paths. Same root cause as
  `.hypothesis/` (`.gitignore:89`).
- **The manifest gate is currently red on this branch** (exit 3):
  `scripts/check_derived_doc_drift.py` and `scripts/worktree_report.py` have no
  `scripts/manifest.yaml` entry. `check_derived_doc_drift.py` is the gate R6 depends on.
- **`benchmarks/` has no `__init__.py`**, so `benchmarks.cp_sat_bench` is unimportable
  and `packages/temper-placer/tests/test_cp_sat_bench.py` fails collection. One of five
  pre-existing collection errors, all unrelated to this work and all left in place.
- **`max31865/` is a component library at repo root** while every other part library
  lives under `components/`, and it is not duplicated there. Moving it would touch KiCad
  library paths, so it is described in the generated map rather than relocated.

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R13][User decision] Are `tests/` and `test-boards/` live working
  directories, stale experiments, or intended to be tracked? Their names imply
  significance but neither is in version control.

### Deferred to Planning

- [Affects R4, R6][Technical] Which table shapes can
  `check_derived_doc_drift.py` enforce as-is, and does the gate matrix need
  restructuring to fit its locator model?
- [Affects R4][Needs research] Is the measured status of each of the 22 gates derivable
  from `docs/evidence/*.json` alone, or does some of it exist only as `STRATEGY.md`
  prose — in which case it falls under R8 and is linked rather than generated?
- [Affects R16, R18][Technical] Do the three merges require `.importlinter` contract
  changes, and can each be done in an independently revertable commit?
- [Affects R9][Technical] Should `docs/README.md` (213 lines) and
  `docs/requirements/README.md` also become generated, or does the value stop at plans
  and solutions?
