---
title: "_drc_api.run_drc()'s DrcError/DrcWarning always report empty components and (0.0, 0.0) location, for every violation type -- not just courtyard ones"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
severity: medium
symptoms:
  - "DrcError.components and DrcWarning.components are always [] regardless of violation type or real kicad-cli data"
  - "DrcError.location and DrcWarning.location are always (0.0, 0.0) regardless of violation type or real kicad-cli data"
  - "The existing test suite for this wrapper (test_drc_runner.py) passed despite this, because its mock fixtures invented a JSON schema (top-level violation 'pos', item-level 'reference' key) that matches neither real kicad-cli output nor was ever checked against it"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - drc
  - kicad-cli
  - self-grading
  - test-fixture-drift
  - json-parsing
---

# `_drc_api`'s `DrcError`/`DrcWarning` always report empty `components` and `(0.0, 0.0)` `location`

## Problem

`_drc_api.py`'s `_parse_drc_json` is the parser behind `run_drc()`, the
programmatic wrapper around `kicad-cli pcb drc --format json` used
throughout the codebase (`regression/runner.py`, `regression/closure_test.py`,
`regression/drc_ratchet.py`, `validation/scheduler.py`,
`validation/human_reference_extractor.py`, and ad hoc investigation
scripts). Discovered mid-investigation into
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md):
pulling real component refs out of a `courtyards_overlap` `DrcError` via
`.components` returned `[]`, and `.location` returned `(0.0, 0.0)`, forcing
a workaround of calling `kicad-cli` directly and parsing its raw JSON by
hand instead of using the wrapper. Investigating further showed this is
**not specific to courtyard violations** -- it happens for every single
violation kicad-cli reports, on every rule type.

## Root Cause

```python
pos = violation.get("pos", {})
location = (pos.get("x", 0.0), pos.get("y", 0.0))

components = []
for item in violation.get("items", []):
    ref = item.get("reference")
    if ref:
        components.append(ref)
```

Two wrong assumptions about kicad-cli's real JSON schema, verified
directly against actual `kicad-cli pcb drc --format json --severity-all`
output on the production board (806 real violations surveyed):

1. **No violation ever has a top-level `"pos"` key.** Only individual
   `items` within a violation carry `"pos"`. `violation.get("pos", {})`
   always returns `{}`, so `location` was always `(0.0, 0.0)`.
2. **No item ever has a `"reference"` key.** The component ref is
   embedded in each item's free-text `"description"` string, in one of
   several shapes depending on the item type:
   - `"Footprint D3"` → `D3`
   - `"Reference field of C1"` → `C1`
   - `"Segment of C16 on F.Silkscreen"` → `C16`
   - `"PTH pad 1 [+15V] of R1"` → `R1`
   - `"Pad 13 [power_in.ntc-no] of K1 on F.Cu"` → `K1`

   Some items are legitimately not owned by a single component --
   `"Via [bias] on F.Cu - B.Cu"` (net-owned) and `"Polygon on Edge.Cuts"`
   (board-level) have no ref to extract, and correctly should not.

   `item.get("reference")` matched none of these real shapes, so
   `components` was always `[]`.

**Why this went unnoticed**: `test_drc_runner.py`'s `mock_error_drc_output`
fixture invented its own JSON shape -- top-level `"pos"` on the violation,
`{"reference": "U1", ...}` items -- that happened to satisfy the (also
wrong) parser above. The test and the implementation were mutually
self-consistent, so `test_drc_detects_overlap` and
`test_drc_detects_clearance` both passed, while neither was ever checked
against a real `kicad-cli` JSON sample. This is the same failure pattern
as the courtyard-check and DRC-oracle findings from the same
investigation: a check "passing" by agreeing with itself, not with
reality.

## What Was Ruled Out

- **Not courtyard-specific.** Surveyed all 806 violations across every
  rule type present in a real run (`courtyards_overlap`,
  `pth_inside_courtyard`, `clearance`, `shorting_items`, `silk_overlap`,
  `lib_footprint_issues`, `via_dangling`, `hole_to_hole`,
  `copper_edge_clearance`, etc.) -- the bug is universal to the parser,
  not tied to any specific rule.
- **Not a currently load-bearing bug in the live pipeline.** Grepped
  every consumer of `DrcResult`/`DrcError`/`DrcWarning`
  (`regression/runner.py`, `regression/drc_ratchet.py`,
  `regression/closure_test.py`, `validation/scheduler.py`,
  `validation/human_reference_extractor.py`) -- none currently read
  `.components` or `.location`; they only consume `error_count`/
  `warning_count`. This bug silently degraded a wrapper's data integrity
  without breaking any pipeline gate, which is exactly why it went
  unnoticed for as long as it did.

## Resolution

Rewrote `_parse_drc_json` to extract refs from item `description` text
via `_extract_ref_from_item_description` (two regexes: `^Footprint (\S+)$`
for footprint-level items, `\bof (\S+?)(?:\s+on\s+\S.*)?$` for the
"X of REF[ on LAYER]" shape covering pads/reference-fields/silkscreen
items), returning `None` for items with no owning component (vias,
board-edge features) rather than a wrong guess. `components` now collects
every item's ref, deduplicated, preserving order.

For `location`, since no top-level `"pos"` exists, the fix uses the
position of the **first item with an extractable ref**, not simply the
first item -- some rules (`copper_edge_clearance`) list a board-level
feature with a degenerate `(0, 0)` position first and the real offending
pad second; grabbing item[0] unconditionally would have kept exactly the
same bug for those rules even after fixing ref extraction. Falls back to
the first item's position only when no item has an extractable ref (e.g.
a genuine via-to-via clearance violation).

**Verification performed:**
- Ran the fixed parser against the full real 806-violation JSON dump: 0
  violations now have `(0.0, 0.0)` location (down from 806/806); 173/806
  have empty `components`, and every one of those is legitimately
  net/board-owned (`via_dangling`, via-to-via `clearance`, one
  via-to-via `hole_to_hole`) -- confirmed by inspecting each remaining
  empty-components rule's raw item descriptions directly.
- `courtyards_overlap` for the known D3/C4 pair: `components=['D3','C4']`,
  `location=(134.8, 74.25)` (previously `[]`, `(0.0, 0.0)`).
- New regression test file `test_drc_api_parsing.py` (10 tests, including
  the degenerate-first-item `copper_edge_clearance` case and the
  legitimately-empty via-clearance case) -- confirmed as a genuine
  regression guard against the exact pre-fix behavior via direct
  `_parse_drc_json` comparison (old code returns `[]`/`(0.0, 0.0)` on the
  same fixture the new code correctly resolves).
- Fixed `test_drc_runner.py`'s `mock_error_drc_output` fixture, which had
  been asserting against its own invented (wrong) schema --
  `test_drc_detects_overlap` and `test_drc_detects_clearance` failed
  against the corrected fixture until the parser fix was applied, then
  passed; both now exercise the real kicad-cli JSON shape.
- No regressions: every test file touching this module (`test_drc.py`,
  `test_drc_runner.py`, `test_scheduler.py`, `test_drc_api_parsing.py`,
  91 tests) passes. `test_gate.py` and `test_regression_drc.py` (also
  importing DRC types) fail identically with and without this fix --
  confirmed pre-existing and unrelated (an `AcceptanceGate.inner_gate()`
  API mismatch and a config↔netlist drift error, neither touching DRC
  JSON parsing).

## Why This Matters

A wrapper whose whole purpose is turning raw DRC output into structured,
addressable data was silently stripping the two fields (`components`,
`location`) that make a violation *actionable* -- "27 courtyards_overlap
errors" is much less useful than "27 courtyards_overlap errors, here are
the component pairs and where they are." Anyone building tooling on top
of `run_drc()` (auto-fix suggestions, violation-to-component mapping,
visualizations) would have silently gotten nothing usable from these
fields without ever seeing an exception -- the same "quiet failure"
pattern as this investigation's other findings, just in the verification
tooling itself rather than the pipeline it verifies.

## Prevention

- **A mock fixture for an external tool's output must be built from a
  real captured sample of that tool, not invented from memory or from
  reading the code under test.** This fixture and the implementation
  shared the same wrong assumption about kicad-cli's JSON schema,
  making the test worthless as a correctness check -- it could only ever
  catch a regression relative to the wrong baseline, never the original
  bug.
- **When two things (a mock and the code it mocks) were plausibly
  authored by looking at each other rather than at the real system,
  they can both be wrong in the same way and still "pass."** Treat
  fixtures for third-party tool output as data that needs independent
  verification against the real tool, not just internal consistency
  with the parser.
- Checked the codebase for a second parser with the same schema
  assumption (`validation/drc.py`'s `KiCadDRCValidator._parse_violations`,
  which also expects item `"reference"` keys and a top-level violation
  `"pos"`) -- confirmed it is dead code (the `DRCLoss` class its
  docstring example references was deleted along with the JAX
  gradient-descent optimizer; `KiCadDRCValidator` has no live callers).
  Not fixed in this pass since it has no runtime impact, but flagged
  here in case it is ever revived.

## Follow-Up (2026-07-18): Added `nets` -- `components` Alone Wasn't Enough

Fixing `.components` didn't cover every consumer's need: `IECCreepageGate`
(a real, live gate) needs **net names** for bare copper track/via
clearance violations, which have no owning component at all (so
`.components` is correctly empty for them) -- their identifying info is
a net name embedded in brackets (`"Via [GND] on F.Cu - B.Cu"`), a
different concept `.components` was never designed to carry. Added a
parallel `nets: list[str]` field (via `_extract_net_from_item_description`)
and fixed `IECCreepageGate.check()` to read it instead of `.components`.
See
[`gate-to-delta-tests-assumed-dict-shaped-constraintdelta-and-wrong-mapped-types.md`](../test-failures/gate-to-delta-tests-assumed-dict-shaped-constraintdelta-and-wrong-mapped-types.md)
for the full investigation -- this was a real, live bug (the gate always
silently reported `CLEAN`), not just another stale test.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the investigation this bug was found during; this wrapper's broken
  `.components`/`.location` is why that investigation had to fall back to
  parsing raw `kicad-cli` JSON by hand.
- [`docs/solutions/test-failures/gate-to-delta-tests-assumed-dict-shaped-constraintdelta-and-wrong-mapped-types.md`](../test-failures/gate-to-delta-tests-assumed-dict-shaped-constraintdelta-and-wrong-mapped-types.md)
  — the follow-up that added `.nets` and fixed a real live bug in
  `IECCreepageGate`.
- `packages/temper-placer/tests/validation/test_drc_api_parsing.py` —
  new regression test file for this fix.
- `packages/temper-placer/tests/validation/test_drc_runner.py` —
  `mock_error_drc_output` fixture corrected to match real kicad-cli
  schema as part of this fix.
