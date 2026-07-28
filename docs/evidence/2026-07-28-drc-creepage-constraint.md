<!-- provenance: commit=982c5a7d dirty=false (base) -->

# Closing the creepage enforcement hole: kicad-cli 10.0.4 DOES support a real `creepage` DRC constraint

Base commit: `982c5a7d` (`merge: RULE 1/1a discriminate dynamically -- plus a
third dead property and a stale .kicad_pro`, branch
`docs/methodology-loop-discipline`). Work done in worktree
`agent-ad212b5b1b0cd0439`, branch `fix/drc-creepage-constraint` created from
that commit.

Reads first, per task instructions: `scripts/generate_kicad_dru.py` (esp.
the "no creepage constraint type" comment, formerly lines 24-82),
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md`,
`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md`,
`docs/evidence/2026-07-28-coating-supplemental-scope.md`,
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `scripts/check_isolation_keepout.py`.

## FALSIFIER, stated up front

> "kicad-cli 10.0.4 supports a creepage constraint and it can be emitted and
> shown to bind. If it does not support one, the deliverable is that finding
> plus an explicit, discoverable statement of where creepage IS enforced --
> not a silently absent check."

**The first branch fires, cleanly, on both required legs:**

1. **kicad-cli 10.0.4 DOES support a real `creepage` constraint** --
   confirmed two independent ways (§1).
2. **It can be emitted and shown to bind** -- confirmed on an isolated
   fixture AND on the real board (§2, §4).

The hole named in the task (creepage established today at 8.0mm PD2 /
12.6mm PD3, enforced only by `check_isolation_keepout.py`'s straight-line
corridor approximation, never by fab-authoritative KiCad DRC) is closed:
`scripts/generate_kicad_dru.py` now emits real `creepage` constraints on
the same net-class pairs its existing clearance rules already cover.

---

## 1. Does kicad-cli 10.0.4 support a creepage constraint? -- source evidence

Fetched `pcbnew/` sources from `kicad-source-mirror` at the exact `10.0.4`
tag (`gh api repos/KiCad/kicad-source-mirror/contents/<path>?ref=10.0.4`),
matching this repo's own documented methodology from the sibling evidence
docs (`drc_rule1-netclass-redo.md` §1 already used this technique for
`pad.cpp`).

| File (at tag `10.0.4`) | Finding |
|---|---|
| `pcbnew/drc/drc_rule.h` | `DRC_CONSTRAINT_T` enum has a `CREEPAGE_CONSTRAINT` member, listed right after `CLEARANCE_CONSTRAINT` |
| `pcbnew/drc/drc_rule_parser.cpp` | `case T_creepage: c.m_Type = CREEPAGE_CONSTRAINT; break;` -- the `.dru` keyword `creepage` maps directly to the constraint type |
| `pcbnew/drc/drc_test_provider_creepage.cpp` | A **dedicated, registered test provider** (`DRC_REGISTER_TEST_PROVIDER<DRC_TEST_PROVIDER_CREEPAGE>`, the same static-registration idiom every other real DRC check uses) implementing `DRCE_CREEPAGE`. Its own top-of-file comment: "Physical creepage tests." It builds a `CREEPAGE_GRAPH` over board-edge/insulator boundaries and solves shortest surface paths between nets -- this is a **genuine surface-path solver**, not a clearance alias. |

GitHub code search (`search/code?q=CREEPAGE_CONSTRAINT+repo:KiCad/kicad-source-mirror`)
independently turned up the same three files plus `drc_engine.cpp` (which
reports progress as `"Checking %s creepage"`) and `api/api_pcb_enums.cpp`
(the constraint is exposed through KiCad's own API enum, i.e. it is a
first-class, documented constraint type, not an internal-only leftover).

**One caveat noted, not load-bearing:** the parser's own error-message
string (`"Missing constraint type. Expected %s."`) lists `clearance,
hole_clearance, edge_clearance, ...` but does not name `creepage` in that
prose list, even though the `switch` statement two lines below handles
`T_creepage` correctly. This looks like a stale help string, not evidence
against support -- confirmed by testing (§2) that the constraint parses
and binds regardless of what the (irrelevant, only reached on a genuinely
missing/unmatched token) error message would have said.

## 2. Empirical probe -- isolated fixture

Built a minimal fixture (one footprint `Q1`, two SMD pads on nets
`HV_SIDE`/`LV_SIDE`, `HV_SIDE` mapped to netclass `HighVoltage`) using the
exact pattern `scripts/tests/test_generate_kicad_dru.py`'s existing
`_build_cross_domain_fixture` already established as reliable. Ran
`kicad-cli pcb drc --format json --severity-all` with a lone
`(constraint creepage (min 999mm))` rule at a fixed 5.0mm pad gap.

**Result: PASSES the falsifier outright.**

```
returncode: 0
violation types: {'creepage': 1, 'lib_footprint_issues': 1}
Creepage violation (rule 'Creepage probe' creepage 999.0000 mm; actual 5.0000 mm)
```

- Default severity for an unconfigured `creepage`-type violation is
  `"error"` (confirmed in the raw JSON report) -- no special
  `rule_severities` entry was needed in the `.kicad_pro`, exactly like
  `clearance`.
- A same-fixture, same-gap `clearance`-only control rule at 999mm produced
  the expected `type: "clearance"` violation, confirming the harness itself
  is sound and the creepage result is not an artifact of the fixture.

### 2a. Bonus finding: this is a real surface-path solver, not a clearance alias

Built a second pair of fixtures at the identical 5.0mm straight-line pad
gap: one with no obstruction, one with an `Edge.Cuts` slot cut directly
between the two pads, forcing any surface path to detour around the slot's
ends.

| Fixture | Reported "actual" creepage |
|---|---:|
| No slot | 5.0000 mm |
| Slot between pads | **41.0526 mm** |

The reported distance changed by >8x for the identical straight-line pad
gap, purely because of an added board-edge obstacle. This is definitive
proof `DRC_TEST_PROVIDER_CREEPAGE` is solving a real path-around-obstacles
problem (consistent with its `CREEPAGE_GRAPH`/`CollectBoardEdges`
implementation read in §1), not reporting straight-line distance under a
different name. This is a materially more capable check than
`scripts/check_isolation_keepout.py`'s straight-line corridor
approximation (which that script's own docstring already documents as
sufficient-but-not-necessary, unable to credit a groove/slot) -- kicad-cli's
native engine can, in principle, credit exactly the groove remedy that
script's docstring says it cannot model.

### 2b. One rule block can carry both a clearance and a creepage constraint

Probed whether `(rule ... (constraint clearance ...) (constraint creepage
...))` -- two constraint clauses in one rule -- is valid, since this is the
minimal-diff way to add creepage to RULE 2/RULE 4's existing clearance
rules. Confirmed against `drc_rule_parser.cpp`: `DRC_RULE::m_Constraints`
is a `std::vector<DRC_CONSTRAINT>` and `parseConstraint()` calls
`aRule->AddConstraint(c)` (additive), so multiple `(constraint ...)` clauses
in one rule are supported by the grammar. Empirically confirmed on the
same 5.0mm-gap fixture: a single rule with both
`(constraint clearance (min 999mm))` and `(constraint creepage (min
999mm))` produced **both** violation types independently:

```
creepage -> Creepage violation (rule 'Combined probe' creepage 999.0000 mm; actual 5.0000 mm)
clearance -> Clearance violation (rule 'Combined probe' clearance 500.0000 mm; actual 5.0000 mm)
```

Note the `clearance` constraint's value was silently clamped to 500.0000mm
even though 999mm was requested -- reproducing the exact clamp
`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` §2a already
documented for `clearance`. **The `creepage` constraint showed no such
clamp** at 999mm in any probe run this session -- worth noting as a
difference between the two constraint types, not verified beyond 999mm.

## 3. What was changed

`scripts/generate_kicad_dru.py`:

- Added `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM`, a single new
  constant with an extensive comment recording: (a) the PD2/PD3 question is
  a **separate, still-unresolved** decision from which constant to emit;
  (b) it is pinned to the PD3 (12.6mm) figure, reusing -- not
  re-deciding -- the identical call `scripts/check_isolation_keepout.py`
  already made and cited for the same barrier; (c) changing the pinned
  figure later is a one-line edit (plus updating that script's
  `MIN_BARRIER_WIDTH_MM` to match, so the two enforcement points never
  silently diverge).
- RULE 2 ("AC Mains to LV") and RULE 4 ("HV to LV") -- the generator's
  existing net-class-pair clearance rules for the mains/HV-to-everything-
  else boundary -- each gained a second
  `(constraint creepage (min {HV_CREEPAGE_ENFORCED_MM}mm))` clause, using
  the same condition already measured to bind
  (`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` §4c: `NetClass`
  comparisons are confirmed to resolve correctly against the real board).
  No other rule was touched; `HighVoltageIsolated` (the gate-drive isolated
  supply's net class) still has no clearance or creepage rule in the
  generator at all -- a real, separate, narrower gap, out of this task's
  scope, and now explicitly flagged in
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §9.1 rather than left silently
  implied.
- The file's own header comment and RULE 2/RULE 4's comments were rewritten
  to state plainly that creepage is now enforced, where the PD2/PD3
  ambiguity is recorded, and that `check_isolation_keepout.py` remains the
  other (board-construction-level) enforcement point.

`scripts/tests/test_generate_kicad_dru.py`:

- Updated the pre-existing
  `test_creepage_figures_recorded_but_flagged_unresolved` test (renamed
  `..._and_pd2_pd3_question_still_unresolved`) -- its old assertion that
  creepage is "not emitted as an enforced KiCad rule" is no longer true and
  was corrected rather than left stale.
- Added `TestCreepageConstraintEmitted` (5 static tests): the enforced
  constant is one of the two declared PD2/PD3 candidates, is currently
  pinned to PD3, RULE 2/RULE 4 both emit the creepage clause with the right
  value, and the header documents the change.
- Added `TestCreepageDrcFalsifier` (2 real kicad-cli tests, skipped if
  kicad-cli isn't on PATH): the exact "HV to LV" rule block
  `generate_dru()` emits today, run wholesale against a fixture, flags a
  5.0mm cross-domain gap (well below 12.6mm) with a real `creepage`
  violation citing the `12.6000` threshold; a control fixture at
  `HV_CREEPAGE_ENFORCED_MM + 5.0mm` (17.6mm) produces **no** creepage
  violation, proving the rule discriminates on distance rather than always
  firing.

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`: see the companion commit and
§4 below -- reconciled the document's own third inconsistent
clearance/creepage figure set, and corrected §9.1's illustrative KiCad rule
snippet to reflect the real generator's new behavior.

## 4. `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` reconciliation

The task named one concrete inconsistency: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
§4.2 asserted "AC Mains to SELV | Reinforced | 5.0mm clearance | 8.0mm
creepage" -- a third figure set, disagreeing with both the document's own
already-corrected §6.4 (coating section, v1.1) and the primary-text
determination in `docs/evidence/2026-07-28-creepage-determination-
brainstorm.md`.

Traced the root cause: **every wrong number in §4/§5's old tables is an
IEC 60335-1 Table 17 (creepage) value copied into a clearance context, or a
"Table 16" mis-citation for creepage** -- the identical failure-mode
`creepage-determination-brainstorm.md` §1 already found across the rest of
the repo. §3.2's Overvoltage Category (III, should be II per IEC 60335-1
cl. 29.1's own text) and Pollution Degree (2, uncited; should be 3 per IEC
60335-2-6 cl. 29.2 Addition, matching the already-corrected
`docs/ENVIRONMENTAL_SPEC.md` and `check_isolation_keepout.py`) were also
wrong and uncited.

**Corrected in place, old values recorded rather than deleted** (see the
git diff/commit for the full before/after; every "old (wrong) value" is
preserved in an adjacent table column or inline note, not removed):

- §3.2: Pollution Degree 2->3 (cited), Overvoltage Category III->II
  (cited), Material Group clarified (IIIa/IIIb unified, laminate
  unspecified).
- §4.1/4.2: real clearance requirement is **1.5mm nominal / 2.0mm with the
  clause-29.1 soldered-construction adder** (not the old table's 1.5-10mm
  spread, and specifically not the flagged "5.0mm/8.0mm" pair).
- §5.1/5.2: real creepage requirement is **8.0mm at PD2 / 12.6mm at PD3**,
  with the PD2-vs-PD3 question explicitly flagged UNRESOLVED --
  matching `generate_kicad_dru.py`'s constants and
  `check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM`, all three now
  agreeing rather than silently diverging.
- §6-§8: flagged (not individually re-derived this pass) with an explicit
  pointer to the real enforcement points; the one specific mislabelled cell
  called out in §7.1 ("8mm clearance, 12mm creepage" in one cell) was
  corrected since leaving it standing beside the corrected §4 figure would
  recreate the same three-inconsistent-sets problem.
- §9.1: the illustrative KiCad rule snippet (which already, correctly,
  showed `creepage` constraint syntax -- interesting foreshadowing, since
  this task independently confirmed that syntax is real) had wrong values
  and a `B.NetClass == 'Default'` condition that does not mean "SELV" on
  this board's actual net-class list. Corrected to match what the real
  generator emits today.

**Hard rule check: no clearance/creepage figure was weakened anywhere in
this reconciliation.** Every changed number moved toward the primary-text
determination (2.0mm clearance is *smaller* than the old 5-8mm figures it
replaced, but that old figure was never a real clearance value to begin
with -- it was a mislabelled creepage figure, and the actual creepage
requirement, 8.0/12.6mm, is unchanged from the determination and is *larger*
than the old table's 10.0/12.0mm in the PD3 case).

## 5. Real-board measurement -- counts with denominators

All measurement against a **scratch copy** of `pcb/temper.kicad_pcb` /
`pcb/temper.kicad_pro` (never the repo's live files, which a sibling agent
owns for this task). Copied once to
`/private/tmp/.../scratchpad/real_board_test/`, `kicad-cli pcb drc --format
json --severity-all` run directly against the copy.

### 5a. Raw kicad-cli, before vs. after this diff

| Generator | Total violations | `creepage` | `track_width` | `copper_edge_clearance` |
|---|---:|---:|---:|---:|
| Base commit (`982c5a7d`, no creepage rule) | 1560 | 0 | 39 | 40 |
| This diff (creepage rule added) | 1677 | **117** | 39 | 40 |

**Delta is entirely attributable to the new creepage constraint**: total
violations rose by exactly 117 (1677-1560), matching the new `creepage`
category count exactly; `track_width` and `copper_edge_clearance` are
byte-identical before and after (confirmed by running the ORIGINAL,
unmodified `generate_kicad_dru.py` module -- via `git show 982c5a7d:...` --
against the identical board copy, not by inference).

Of the 117 real-board `creepage` violations: **101** from "HV to LV", **16**
from "AC Mains to LV" (both rule names extracted directly from each
violation's own description string, denominator = 117, no truncation
observed at this count -- see §5c). A sample of the "HV to LV" violations'
`actual` values (0.4900mm, 6.8657mm, 8.0000mm, 9.6476mm, 0.0750mm, ...)
includes figures matching prior isolator-gap measurements in
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §6 (e.g.
K1's 8.000mm edge-to-edge gap) almost exactly -- corroborating that the
KiCad engine's own surface-path measurement is consistent with this repo's
independent rectangle-model measurements, not an unrelated number.

### 5b. Via the project's own DRC-ratchet harness (`scripts/ci_check_drc.py`)

This harness measures differently from raw `kicad-cli` (zone-fill,
`--all-track-errors`; already documented as a source of count differences
in `power_pcb_dataset/drc_ceiling.json`'s own march notes). Ran it twice
against the identical board, swapping only `scripts/generate_kicad_dru.py`
between the base-commit module and this diff's module (file swapped and
`pcb/temper.kicad_dru` regenerated between runs, then both restored),
never touching `power_pcb_dataset/drc_ceiling.json` itself:

| Generator | Aggregate errors | vs. ceiling (1017) | `creepage` | `track_width` | `copper_edge_clearance` |
|---|---:|---:|---:|---:|---:|
| Base commit | 1078 | **+61 over, already failing** | 0 | 39 (NEW, ceiling 0) | 49 (regressed, ceiling 15) |
| This diff | 1193 | **+176 over** | **115 (NEW, ceiling 0)** | 39 (unchanged) | 49 (unchanged) |

**Net attributable to this diff: +115 aggregate errors, entirely the new
`creepage` category** (1193-1078=115, matching the reported delta exactly).
`track_width` and `copper_edge_clearance` breaches **pre-exist this diff**
-- the ceiling gate was **already failing before this task started**, by
+61, for reasons unrelated to creepage. Per the task's hard rule, this is
reported, not fixed, and `power_pcb_dataset/drc_ceiling.json` was not
touched (no `Ceiling-Approval:` trailer exists or was added).

The small discrepancy between the raw-kicad-cli creepage count (117, §5a)
and the ratchet-harness count (115, §5b) is consistent with the harness's
own documented zone-fill/measurement differences from raw `kicad-cli`
(same class of discrepancy `power_pcb_dataset/drc_ceiling.json`'s own
"2026-07-28-routed-rebaseline" note already describes for `clearance`) --
not independently root-caused further here, since both counts already
establish the qualitative point (a large, real, entirely-new violation
category) beyond doubt.

### 5c. Truncation caveat (per task instructions)

`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` §2a established
kicad-cli 10.0.4 truncates its JSON DRC report at roughly 500 total
`clearance`-type violations, shared across all sources. This board's total
violation count (1677, §5a) exceeds 500, so **every count in this document
above the truncation floor is a lower bound, not an exact total** -- in
particular the 117/115 creepage counts themselves are comfortably below
500 and were not observed to be truncated in any run this session, but the
*other* categories reported alongside them (e.g. `clearance` at 361, close
to a plausible truncation regime) should be read the same cautious way the
prior evidence docs already established. This caveat does not affect the
qualitative finding (creepage went from a real zero to a real, large,
positive count).

## 6. Verification

- `make netlist` -- **PASSED** (rebuilt `elec/build/default.net`, full
  assertions-report green).
- `uv run --no-sync ruff check scripts/generate_kicad_dru.py
  scripts/tests/test_generate_kicad_dru.py` -- **all checks passed**.
- `uv run --no-sync python -m pytest scripts/tests/test_generate_kicad_dru.py -v`
  -- **21/21 passed** (14 pre-existing + 7 new: 5 in
  `TestCreepageConstraintEmitted`, 2 in `TestCreepageDrcFalsifier`).
- `uv run --no-sync python -m pytest elec/validation -q` -- **30/30 passed**.
- Nine required gates, confirmed this session, all matching expected/prior
  state:

| Gate | Result |
|---|---|
| `check_domain_partition` | PASSED (exit 0) -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects (60 declared nets, 2 domains, 10 isolators, over 168 compiled nets/components) |
| `capacity_budget_gate` | PASSED (exit 0) -- 0 defects |
| `mpn_fabrication_gate` | PASSED (exit 0) -- 0 new violations |
| `check_derived_doc_drift` | PASSED (exit 0) -- 3 docs, 47 tables, 136 fields checked (does not check `HIGH_VOLTAGE_CLEARANCE_SPEC.md`, unaffected by that edit) |
| `check_rust_drc_presence` | PASSED (exit 0) -- `temper_drc_rs` symbols present and fresh |
| `check_undeclared_imports` | PASSED (exit 0) -- 1262 stdlib, 1252 local, 1 allowlisted, 712 resolved |
| `check_stale_extensions` | exit 3, 10 crates flagged "stale" -- confirmed the same documented checkout-mtime false positive prior sessions hit (`git checkout -b` resets tracked-file mtimes newer than the shared checkout's already-built `.venv` artifacts); none of the 10 crates' `.rs` files are touched by this diff |
| `check_net_classification` | PASSED (exit 0) |
| `check_pll_range_consistency` | PASSED (exit 0) -- 4/4 checks agree |

- Pre-existing failures, confirmed (not fixed, per task instructions):

| Gate | Result |
|---|---|
| `check_isolation_keepout` | exit 3 -- barrier keepout zone `MAINS_SELV_ISOLATION_BARRIER` still not placed on the board (unrelated to this diff; this gate's own `MIN_BARRIER_WIDTH_MM` is already 12.6mm, unchanged here) |
| `check_measurement_provenance` | exit 5 -- `power_pcb_dataset/drc_ceiling.json`'s `source: "measured-live-5-samples"` is not one of the two allowed enum values; pre-existing, not touched |
| `check_copper_net_consistency` | exit 3, 146 violations -- pre-existing, matches the count in `docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` §7 exactly; pending the sibling agent's board resync, not fixed here |

- `power_pcb_dataset/drc_ceiling.json` -- **not touched** (no
  `Ceiling-Approval:` trailer added or needed for this task). Confirmed the
  DRC-ratchet gate now fails harder (+176 over ceiling vs. +61 before this
  diff, §5b) -- reported above, not silenced.
- `pcb/temper.kicad_pcb`, `elec/src/` -- **not touched** (sibling agent's
  files). All real-board measurement used scratch copies.

## 7. Compliance with the task's hard rules

- **Never emitted a weaker figure than determined.** The emitted creepage
  constant (`HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM = 12.6mm`) is the
  *larger* of the two live candidates, chosen explicitly because it cannot
  be an under-enforcement if PD3 is later confirmed.
- **Did not resolve the PD2/PD3 question unilaterally.** Both
  `HV_CREEPAGE_PD2_MM` and `HV_CREEPAGE_PD3_MM` remain declared side by
  side, with the ambiguity recorded in the same comment as the new
  `HV_CREEPAGE_ENFORCED_MM` constant; the pin is a documented, reversible
  engineering default (matching the identical, already-made call in
  `check_isolation_keepout.py`), not a resolution of the underlying safety
  question.
- **`power_pcb_dataset/drc_ceiling.json`** -- not touched; ceiling breaches
  reported in §5b/§6, not fixed.
- **No `git stash`** used anywhere this session.
- **No `run_in_background`**, no `Monitor`, no waiting on background jobs
  -- every `kicad-cli`/`pytest`/gate invocation ran in the foreground.
- **Committed after each meaningful step**: `scripts/generate_kicad_dru.py`
  + `scripts/tests/test_generate_kicad_dru.py` in one commit
  (`e9c0805b`), `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` in a second
  (`e80c19dd`), this evidence doc in a third.
- **Disk**: no new worktree created (reused the agent's already-assigned
  worktree, rebased its branch onto `982c5a7d`); no large downloads (KiCad
  source files fetched via `gh api` are small, single-file text/C++
  sources, held only in the session scratchpad, never committed).
- `uv run --no-sync` used throughout; `UV_PROJECT_ENVIRONMENT` pointed at
  the main checkout's already-synced `.venv` rather than syncing a fresh
  one in this worktree.
- Files touched: `scripts/generate_kicad_dru.py`,
  `scripts/tests/test_generate_kicad_dru.py`,
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, this evidence doc. Did not
  touch `pcb/temper.kicad_pcb`, `elec/src/`, or
  `power_pcb_dataset/drc_ceiling.json`.
- Not pushed.

## UNVERIFIED

- **Whether the CI container's kicad-cli 10.0.5 (rather than this
  session's 10.0.4) behaves identically for `creepage`.** Not independently
  re-verified in this session (no Docker pull, consistent with disk
  constraints); relies on the same class of source-tag-diff precedent
  prior sessions used for other constructs (`pcbexpr_evaluator.cpp`/
  `pad.cpp` at 10.0.4 vs. 10.0.5), not re-diffed here for
  `drc_test_provider_creepage.cpp` specifically.
- **The exact root cause of the 117 (raw kicad-cli) vs. 115 (ratchet
  harness) creepage-count discrepancy** (§5b) -- attributed to the
  harness's already-documented zone-fill/measurement methodology
  difference from raw `kicad-cli`, not traced pair-by-pair.
  Does not affect the qualitative finding.
- **Whether kicad-cli's creepage solver's surface-path graph is a complete,
  exact minimum-path solver in all geometries**, versus an approximation
  with its own edge cases -- only spot-checked on two small fixtures (a
  clean straight-line case and a single-slot-obstacle case) in this
  session, not stress-tested against the pathological cases KiCad's own
  issue tracker might document. Treated here as "real and load-bearing,"
  not as "provably exact everywhere."
- **`scripts/check_isolation_keepout.py`'s own straight-line-corridor
  design decision was not revisited** -- this task's brief was to close the
  KiCad-DRC-side gap, not to decide whether that script should be rewritten
  now that a real surface-path engine is confirmed to exist. Flagged as a
  natural, larger follow-up (the two enforcement points could in principle
  converge on one real surface-path model instead of a corridor
  approximation plus a separate DRC rule), explicitly out of this task's
  scope.
- **The `HighVoltageIsolated` net class's total absence of any
  clearance/creepage rule** in `scripts/generate_kicad_dru.py` -- confirmed
  present (grep, zero matches) and flagged in both this doc and
  `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §9.1, but not fixed; a real, separate,
  narrower gap than the one this task was scoped to close.
- Per §5c, every count in this document above the ~500-violation
  truncation floor documented in
  `docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` §2a should be read
  as "at least N," not an exact total. The creepage-specific counts (117,
  115) are both comfortably below that floor and were not observed to be
  truncated.
