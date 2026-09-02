# The DRC parser read one of kicad-cli's ten top-level keys

<!-- provenance: commit=85b4e400572a77d18f0ee6c644a532ab0a55dd8e dirty=true (persistent main commit for PR #1390 carrying this evidence and the parser fix; original authoring worktree state was not retained) -->

**Date:** 2026-08-19
**Board:** `pcb/temper.kicad_pcb`, sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` (unmodified)
**Branch:** `fix/drc-parser-unconnected-items`, cut from `origin/main` `e63028ccd`

## Summary

`temper_placer.validation._drc_api._parse_drc_json` — the function behind
every kicad-cli DRC number this project has ever produced — read exactly one
of kicad-cli's ten top-level JSON keys. The dropped `unconnected_items` array
holds **339 entries** on the committed board, every one `severity: "error"`.

| | errors | warnings |
| --- | --- | --- |
| what the parser reported (and every ratchet recorded) | 379 | 397 |
| what kicad-cli actually reported | **718** | 397 |

339 of 718 real errors — **47%** — were invisible to
`power_pcb_dataset/drc_ceiling.json`, to `scripts/ci_check_drc.py`, and to
every DRC comparison in every evidence document in this repo. The project's
entire goal is a connected board; the gate that exists to catch regressions
had never once seen a connectivity failure.

Nothing failed loudly. The number was simply smaller than the truth, which is
indistinguishable from a good result.

## Conditions (every number below was measured under exactly these)

| condition | value |
| --- | --- |
| kicad-cli | 10.0.5 |
| flags | `pcb drc --all-track-errors --format json` |
| thread pin | `KICAD_CONFIG_HOME` with `MaximumThreads=1` (`_single_threaded_kicad_env`), confirmed active |
| project context | `pcb/temper.kicad_pro` resolvable |
| `pcb/temper.kicad_dru` | regenerated from `scripts/generate_kicad_dru.py`; 33 208 bytes, sha256 `488a01a81ea29dd6b4ed3106d3f5c0b036a9d07bf9a545a60b1ca6fbc74a0fdb`. **Gitignored — without regenerating it, creepage reads 0.** |
| `pcb/fp-lib-table` | present beside the board. Without it `lib_footprint_issues` reads exactly 168 and `lib_footprint_mismatch` reads 0; here they read 13 and 26, so the harness is correct. |
| `scripts/check_stale_extensions.py` | run immediately before measuring: **PASSED, 10/10 fresh**, in this worktree's own isolated `.venv` (`make venv-isolate`) |
| samples | 3 consecutive runs, intersected |
| board sha256 verified | before and after every run; never modified |

Raw reports are committed verbatim at
`packages/temper-placer/tests/validation/fixtures/kicad_drc_reports/temper_26981fea_run{0,1,2}.json`.

## 1. The complete top-level key audit

kicad-cli 10.0.5 (`$schema: https://schemas.kicad.org/drc.v1.json`) emits
exactly ten top-level keys. Identical in all three runs.

| key | kind | count on this board | read before | read now |
| --- | --- | --- | --- | --- |
| `violations` | array | 776 | **yes** | yes |
| `unconnected_items` | array | **339** | **no** | yes → errors |
| `schematic_parity` | array | 0 | **no** | yes → errors/warnings |
| `ignored_checks` | array | 4 | **no** | yes → `DrcResult.ignored_checks` |
| `included_severities` | array | 2 | **no** | yes → `DrcResult.included_severities` |
| `$schema` | scalar | — | no | recognized, not surfaced |
| `coordinate_units` | scalar | `"mm"` | no | recognized, not surfaced |
| `date` | scalar | — | no | recognized, not surfaced |
| `kicad_version` | scalar | `"10.0.5"` | no | recognized, not surfaced |
| `source` | scalar | `"temper.kicad_pcb"` | no | recognized, not surfaced |

So there were **four** dropped arrays, not one.

### `schematic_parity` reads 0 because the check never runs

Not because the board is clean. `kicad-cli pcb drc` has a `--schematic-parity`
flag; `run_drc` does not pass it, so the array is emitted empty regardless of
the board's state. Probed directly on a scratch copy: without the flag, 777
violations / 339 unconnected / 0 parity; **with** the flag, kicad-cli exits
**255** and writes no report at all on this board. An empty
`schematic_parity` in this repo therefore means "not measured", never "clean".
The parser now consumes the array so it cannot be dropped the day someone
enables the flag — but *enabling* it is a separate, owner-level decision with
its own evidence requirement, and is deliberately not part of this change.

### `ignored_checks` names four checks kicad-cli disabled

`track_not_centered_on_via`, `tuning_profile_track_geometries`,
`footprint_filters_mismatch`, `footprint_type_mismatch`. Each reports nothing
— indistinguishable from clean unless the consumer can see the check never
ran. `DrcResult` now carries the list.

## 2. The blindness, demonstrated (anti-vacuity)

A fix to a silent under-report is worth nothing unless the instrument can be
shown reading wrong first. `packages/temper-placer/tests/validation/test_drc_json_top_level_keys.py`
(40 tests) pins the **pre-fix parser body verbatim** and runs both arms over
the same real bytes:

* `test_the_board_really_has_339_unconnected_items` — ground truth, straight
  from the report, no parser involved.
* `test_pre_fix_parser_is_blind_to_all_339_unconnected_items` — the pinned old
  body returns **zero** unconnected_items and `error_count == 379`.
* `test_current_parser_sees_all_339_unconnected_items` — same bytes, the
  shipped parser returns 339 and `error_count == 718`.
* `test_fix_adds_unconnected_items_and_changes_nothing_else` — multiset diff
  of the parsed violations: nothing removed, everything added is
  `unconnected_items`, warnings byte-identical.

**Verified non-vacuous by reverting the fix:** with `_VIOLATION_ARRAY_KEYS`
set back to `("violations",)`, **20 of the 40 tests fail**. Editing the
fixture to hide the problem fails the pre-fix arm instead. A mock was
deliberately not used — a mock proves only that mocks work.

The pre-fix arm is a copy of the old body, not a reference to it, precisely so
that "updating it to match" is visibly the wrong move.

## 3. Per-category counts — the correctness bar

Identical in all three runs. The fix must not move any pre-existing category,
and does not:

| errors | count | | warnings | count |
| --- | --- | --- | --- | --- |
| clearance | 179 | | silk_overlap | **199 (SATURATED)** |
| creepage | 106 | | via_dangling | 111 |
| shorting_items | 39 | | silk_over_copper | 42 |
| hole_clearance | 33 | | lib_footprint_mismatch | 26 |
| copper_edge_clearance | 11 | | lib_footprint_issues | 13 |
| drill_out_of_range | 6 | | missing_courtyard | 5 |
| solder_mask_bridge | 4 | | silk_edge_clearance | 1 |
| courtyards_overlap | 1 | | | |
| **unconnected_items** | **339 (new visibility)** | | | |
| **total** | **718** (was 379) | | **total** | **397** (unchanged) |

Cap discipline: `silk_overlap` reads **exactly 199 = `ERROR_LIMIT`** — a
saturation floor, not a count. `clearance` reads 179, below both 199 and
`EXTENDED_ERROR_LIMIT` (499), so it is a true count. `unconnected_items` caps
at 499 and reads 339, so **339 is a true count, not a floor.**

Of the 339: **290** name at least one owning footprint; the remaining **49**
are Via/Track-to-Via misses — bare copper with no owning component (82 `Via`
and 16 `Track` item descriptions between them). All 339 resolve a net name.
That split is asserted, so the category cannot silently degrade into 339 empty
shells.

## 4. What becomes visible — and why nothing was re-baselined

`power_pcb_dataset/drc_ceiling.json` **was not touched.** It is already stale
(it provenances board `9c1f4a37…` while main is `26981fea…`) and
`ci_check_drc` is already red on three categories — issue #1370. Re-baselining
now would absorb six other PRs' unattributed regressions **and** silently
accept a category nobody has ever reviewed.

`scripts/ci_check_drc.py --backend kicad-cli`, measured on this branch and
again with the parser reverted in place:

**Before the fix (origin/main parser) — exit 4:**
```
  per-type errors: 2 categories over ceiling (0 new, 2 regressed):
    [   ] copper_edge_clearance 11 > 4 (+7)
    [   ] drill_out_of_range 6 > 4 (+2)
  per-type warnings: 1 category over ceiling (0 new, 1 regressed):
    [   ] via_dangling 111 > 25 (+86)
FAIL: cap-saturation guard -- silk_overlap: 199 (CAPPED — true count >= 199)
```

**After the fix — exit 4 (same code):**
```
  per-type errors: 3 categories over ceiling (1 new, 2 regressed):
    [NEW] unconnected_items 339 > 0 (+339)
    [   ] copper_edge_clearance 11 > 4 (+7)
    [   ] drill_out_of_range 6 > 4 (+2)
  per-type warnings: 1 category over ceiling (0 new, 1 regressed):
    [   ] via_dangling 111 > 25 (+86)
FAIL: cap-saturation guard -- silk_overlap: 199 (CAPPED — true count >= 199)
```

**The gate was already failing before this change and fails with the same exit
code after it.** This change does not turn CI red; it adds a fourth true
finding to an already-red gate. `unconnected_items` is absent from
`violations_by_type`, which the ratchet's own contract treats as an implicit
ceiling of 0 — so it reports `[NEW] unconnected_items 339 > 0`. **That is
correct behaviour and it is the finding.** Excluding the category from the
ratchet to make it green would be exactly the prohibited move.

### What a first ceiling would have to be — OWNER DECISION, not taken here

Anyone setting one needs all of the following, and none of it is a mechanical
edit:

1. **Value: 339**, measured on board `26981fea…`, kicad-cli 10.0.5, 3 runs,
   deterministic (`339/339` stable, zero spread). Not saturated (cap 499).
2. **`nondeterministic_error_types` needs no entry** for it on the evidence
   here — but the file's own protocol demands **≥120 samples** before a
   category's spread may be called zero. Three runs is enough to publish a
   measurement; it is not enough to certify determinism under that protocol.
3. **Provenance must be a fresh `measured-live` record for board
   `26981fea…`.** The committed provenance is for `9c1f4a37…`. A ceiling
   cannot be added to a record whose board hash does not match main —
   `scripts/check_drc_ceiling_approval.py` (R27) would be comparing against a
   board that no longer exists.
4. **It must not be bundled with a re-baseline of the three already-red
   categories** (`copper_edge_clearance`, `drill_out_of_range`,
   `via_dangling`). Those are #1370's unattributed regressions from six
   board-changing PRs; folding them in under one "remeasure" is how
   attribution gets lost.
5. **A ceiling of 339 is 339 units of debt, not budget.** The file's own
   `_goal` is `error_ceiling: 0`. 339 unconnected items on a board whose
   purpose is to be connected is a routing-completion problem, not a
   measurement-tolerance problem. The right response may well be "do not set a
   ceiling; fix the board" — which is precisely why this is left to the owner.

## 5. The sibling defect: synthesized uuids

kicad-cli invents item uuids for objects the board file does not name.

* `pcb/temper.kicad_pcb` carries exactly **10** `(uuid …)` tokens.
* One DRC report references **825** distinct item uuids.
* Across three runs of the byte-identical board, only **291** recur.

Same three reports, three different keys:

| key | violations stable / unstable | unconnected_items stable / unstable |
| --- | --- | --- |
| item `uuid` | 310 / **1398** | 49 / **870** |
| `(type, description, item desc+x+y)` | 774 / 4 | 339 / 0 |
| `drc_violation_key` (shipped) | **776 / 0** | **339 / 0** |

A board whose every per-category count is identical across all three runs
reads as almost entirely unstable under uuid keying. That is manufactured
nondeterminism, and it is exactly the shape of the "nondeterministic on CI
runners" write-off this repo has been burned by before.

**Audit result: nothing in `_parse_drc_json` or any of its consumers keys on
uuid.** `_parse_drc_json` discards uuids entirely; `compare_drc_reports.py`
keys on `type`; `placer/cp_sat/gates.py` and
`deterministic/feedback/drc_parser.py` do not use them. So there was no live
bug to repair — but the raw uuid sits right there in every report, and the
next person to write a set diff will reach for it. `_drc_api.drc_violation_key`
is now the committed, documented, uuid-free key, with the numbers above in its
docstring and a test that pins them.

The middle row's 4 "unstable" violations are the `shorting_items` net-order
swap AGENTS.md already warns about (`nets A and B` vs `nets B and A`); 39 of
the 776 violations carry such a pair and 4 actually swap. `drc_violation_key`
normalizes it, which is what turns 774/4 into 776/0.

## 6. Same defect in two more instruments

Fixed in the same change, because they inherit the identical blindness:

* **`scripts/measure_uncapped_drc.py`** — the sharpest case. Its own cap table
  names `unconnected_items` as one of the two `EXTENDED_ERROR_LIMIT` (499)
  categories, while its counting functions read `violations` only. Asking it
  for the true uncapped count of `unconnected_items` returned **0** —
  contradicting the module's own constants. A tool reporting 0 for a category
  it knows exists is worse than one that refuses: 0 reads as "solved".
* **`scripts/compare_drc_reports.py`** — live (`scripts/sprint1_validation.sh`,
  and cited in `docs/evidence/2026-08-08-drc-power-token-jump-root-cause.md`).
  A board could lose connections between two runs and compare clean.

Three other readers in this repo were **already correct** —
`deterministic/feedback/drc_parser.py`, `placer/cp_sat/gates.py`, and
`temper-drc-rs`'s `violation_contracts.rs::DrcReport` (whose docstring even
pins "the merged `violations` + `unconnected_items` parse in order").
`_parse_drc_json` was the one reader that never got the merge, and nothing
compared the five readers to each other.
`scripts/tests/test_drc_report_array_keys.py` is that comparison.

## 7. Regression check

Every failing test below was baselined by physically reverting this change in
place (restoring the four modified files from HEAD, moving the three new test
artifacts aside) and re-running the identical selection. `git stash` was not
used.

* `packages/temper-placer/tests/validation/` + the two DRC-parser differential
  suites: **2120 passed, 13 failed** — all 13 reproduce identically on pristine
  `origin/main`. They are CI-registration drift, a missing `ngspice`, a missing
  MFEM binary, and a test that assumes kicad-cli is absent from the host.
* `scripts/tests/` + `tests/deterministic/` + `tests/analysis/` + three
  coverage suites: **41 failed on this branch, 41 failed on pristine
  `origin/main`, and `diff` of the two FAILED lists is empty.** Passing count
  rises 3942 → 3947, which is exactly the five new tests in
  `scripts/tests/test_drc_report_array_keys.py`.
* **Zero regressions attributable to this change.**
* Pre-existing gate failures confirmed unrelated (present with the change
  removed): `scripts/regen_derived.py --check` REFUSEs on three hash-order
  NEW_SITEs in `physics/gate_drive.py`; `scripts/check_manifest_gate.py` warns
  that `measure_uncapped_drc.py` has an empty `imports:` list.
* `ruff check` / `ruff format --check` clean on every touched file.
* `scripts/check_manifest_gate.py` PASSED (175 files, 176 entries).
* The pinned differential oracle
  (`test_validation_glue_rust_differential.py`) is untouched and green: the
  Rust kernel's contract is "parse a list of violation dicts", and merging the
  arrays before the call leaves that contract, and its oracle, unchanged.

## What to re-check because of this

Any DRC conclusion dated before 2026-08-19 that depended on connectivity is
missing 339 errors' worth of signal. In particular, every `error_ceiling` and
`violations_by_type` figure in `drc_ceiling.json`'s 39-entry `_march` log was
measured with this parser.
