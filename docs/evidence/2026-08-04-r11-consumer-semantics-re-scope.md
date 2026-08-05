# R11 consumer-semantics catalog — audit working record (2026-08-04)

<!-- provenance: commit=3400e7ecce664bc97087cfc4556b0d10bf73aa88, branch=feat/wave4-phase3-board-netlist-contracts, dirty=false -->
<!-- base: PR #701 (board/netlist parse-target contracts), tip 3400e7ecc -->

**Date:** 2026-08-04
**Scope:** the R11/U4 full-enumeration requirement for the board/netlist
contract migration (PR #701) and its re-scope to the enumerated pin-list
recorded in `packages/temper-design-bundle/VERIFICATION.md`.

---

## The counting rule

"69 board + 77 netlist src importers" counts **distinct source modules under
`packages/temper-placer/src/`** that import a symbol from
`temper_placer.core.board` / `temper_placer.core.netlist` (or reach the
migrated pyclasses through those delegation shims), measured by
`grep -rl "core.board\|core.netlist" packages/temper-placer/src/...` at the
pre-migration base commit. The count is *module-level*, not per-symbol: a
module that imports both classes and a module that imports one both count 1.
Tests are excluded from this count (they are exercised in bulk by the broad
suite, not by the consumer-semantics catalog).

The full per-symbol enumeration was **not** produced as a committed artifact
at this pull. Instead, every consumer behavior the differentials actually pin
is enumerated by name in the R11 re-scope record in VERIFICATION.md, and the
drift mechanism (plan R13) operates through the per-pull scorecard convention
described there.

## Why the re-scope is sound here

- The stacked PRs built against these contracts (#716 config/reference
  loaders, #718/#723 candidates) exercised the consumer surface broadly, and
  the broad-suite baseline comparison at this pull found both escaped
  regressions (`dataclasses.replace` via `apply_placements.py`, `board.traces`
  injection via `trace_analyzer.py`/`board_renderer.py`) — the two failure
  classes a full enumeration exists to catch, caught by the comparison.
- The re-scope is a **plan-level** change needing the product authority's
  concurrence; this record + the VERIFICATION.md section are the record of it.
  A fresh full enumeration remains available as a follow-up if the product
  authority rejects the re-scope.

## Cross-links

- Re-scope record: `packages/temper-design-bundle/VERIFICATION.md` →
  "R11 consumer-semantics catalog — re-scope record (2026-08-04)".
- Plan requirement: `docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`
  D2 ("candidate 1 budgets a consumer-semantics audit for iteration, dunders,
  and numpy dtype behavior").
