<!-- provenance: commit=067527c96cefb2fb14e8d491f371b6ec9483cf7d dirty=true (branch fix/pd2-creepage-row-determination, rebased onto origin/main tip 067527c9; this session's own new-doc/test additions are layered on top and are what "dirty" reflects) -->

# PD2 creepage row determination: Table 17 row iv is a range (>250V, <=400V); 400V is inside it, not between rows. PR #442's 10.0mm was wrong; the correct PD2 figure is 8.0mm -- but PD3/12.6mm is what's operative today, and this document does not change that.

## Read this first: what this document does and does not change

- **What changed on `main` since this investigation started:** PR #464
  merged first and corrected the *pollution degree* axis (PD2 -> PD3),
  replacing the entire operative `IEC60335_REQUIREMENTS` matrix with PD3
  figures (6.3mm basic / **12.6mm reinforced**, Table 17 row iv, PD3,
  Material Group IIIa/IIIb). **That is the enforced, operative figure on
  this branch today, and this document does not touch it, revert it, or
  argue against it.**
- **What this document actually resolves:** a narrower, disclosed-but-not-
  closed question that PR #464's own spec edit explicitly flagged and
  deferred ("a human should reconcile... as a separate follow-up"): *if*
  Pollution Degree 2 is ever legitimately earned (the sealed-compartment
  architecture option), *what is the correct PD2 row-iv figure* -- PR #442's
  originally-merged 10.0mm, or 8.0mm? This document settles that from
  primary text: **8.0mm is correct; PR #442's 10.0mm was an off-by-one-row
  error.** This matters concretely because it is what
  `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md`'s
  Option 2 (sealed electronics compartment) would need to clear, and
  8.0mm vs. 10.0mm is the difference between U3/U7 clearing (barely) and
  not.
- **This is not a safety-constant change.** The operative validator
  constant on this branch, before and after this document, is unchanged:
  PD3, 12.6mm reinforced. Nothing in `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
  or `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` is modified by this PR.

## Provenance labels

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched and read directly this session (page image inspected, not OCR'd blindly). |
| **CITED-SECONDARY** | A prior session's finding, cross-checked but not the basis of the conclusion by itself. |
| **MEASURED** | Computed this session from real repo files (test run, primary-text page render). |
| **DERIVED** | Arithmetic/logic on labelled inputs, shown in full. |

## 1. The question, and why it is not moot even though PD3 governs today

Two prior PRs disagreed about the PD2 figure at this design's 340-400V
boundaries:

- **PR #442** (merged, since superseded on the pollution-degree axis by
  PR #464): read a working voltage of 400V as falling *between* two
  tabulated rows and applied a "round up to the next row" rule, landing on
  **10.0mm** reinforced.
- **PR #464** (merged): while investigating a *different* question
  (pollution degree), independently re-read Table 17 row iv as the literal
  range **">250V and <=400V"** -- 400V sits at the row's own inclusive
  ceiling, *inside* it, not between rows -- giving **8.0mm** reinforced at
  PD2. PR #464 used this correctly for its own PD3 derivation (PD3's row iv
  figure, 12.6mm, is what's operative today) but explicitly did **not**
  correct PR #442's now-orphaned PD2 claim, flagging it instead: "A human
  should reconcile whether PR #442's 10.0mm was itself an off-by-one-row...
  as a separate follow-up." `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  Sec 5.1 (as PR #464 left it) still contains this exact unresolved flag,
  and `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md`
  lists "the PD2 row-iv figure: 8.0mm or 10.0mm?" as its top-ranked,
  "resolve first" open question -- because Option 2 (a sealed compartment
  to legitimately earn PD2) only clears U3/U7 if the answer is 8.0mm, not
  10.0mm.

**This document closes that flag**, from primary text read independently
this session (not by counting how many prior docs already agree, though
five independently do).

## 2. What the primary text actually says

### 2.1 Source and method

Same approach several prior sessions in this repo already used and
disclosed: IS 302-1:2008 ("Safety of household and similar electrical
appliances, Part 1: General Requirements"), the identical Indian national
adoption of IEC 60335-1, fetched fresh this session from
`https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf` (80-page PDF, no
text layer -- a scan). Rather than trust OCR on a dense numeric table, pages
56-58 were rendered directly to 150dpi PNG images (`pdftoppm`) and inspected
visually, digit by digit, not parsed as text.

### 2.2 Table 17, verbatim (page 58)

Header: **"Table 17 Minimum Creepage Distances for Basic Insulation
(Clauses 29.2.1, 29.2.2 and 29.2.3)"**. Columns: Sl No., Working Voltage
(V) (two sub-columns, lower and upper bound joined by the word "and"), and
Creepage Distance (mm), split into Pollution Degree 1 / 2 / 3, with PD2/PD3
further split into Material Group I / II / IIIa-IIIb. Rows relevant to this
design (i-vi of xviii total, reproduced verbatim from the image):

| Sl No. | Working Voltage (V) | PD1 | PD2-I | PD2-II | **PD2-IIIa/IIIb** | PD3-I | PD3-II | **PD3-IIIa/IIIb** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| i | <=50 | 0.2 | 0.6 | 0.9 | 1.2 | 1.5 | 1.7 | 1.9 |
| ii | >50 and <=125 | 0.3 | 0.8 | 1.1 | 1.5 | 1.9 | 2.1 | 2.4 |
| iii | >125 and <=250 | 0.6 | 1.3 | 1.8 | 2.5 | 3.2 | 3.6 | 4.0 |
| **iv** | **>250 and <=400** | 1.0 | 2.0 | 2.8 | **4.0** | 5.0 | 5.6 | **6.3** |
| v | >400 and <=500 | 1.3 | 2.5 | 3.6 | 5.0 | 6.3 | 7.1 | 8.0 |
| vi | >500 and <=800 | 1.8 | 3.2 | 4.5 | 6.3 | 8.0 | 9.0 | 10.0 |

**Every "Working Voltage" cell is stated as a bounded range with an
explicit "and"** (e.g. "**>250** and **<=400**"), never as a single number.
400V, therefore, is **inside** row iv, not between two rows -- there is
nothing to round up to, for either pollution-degree column.

Cross-check against what's already operative on `main`: row iv,
**PD3**-IIIa/IIIb = 6.3mm basic. Clause 29.2.3 (double for reinforced) =
**12.6mm** -- exactly PR #464's merged, currently-enforced figure. This is
an independent confirmation, from a fresh primary-text read, that PR #464's
PD3 derivation used the correct row. Row iv, **PD2**-IIIa/IIIb = 4.0mm
basic -> **8.0mm** reinforced -- the figure this document is about.

### 2.3 Clause 29.2 - 29.2.3, verbatim (page 57)

> "**29.2** Appliances shall be constructed so that creepage distances are
> not less than those appropriate for the working voltage, taking into
> account the material group and the pollution degree.
>
> **29.2.1** Creepage distances of basic insulation shall not be less than
> those specified in Table 17. ...
>
> **29.2.3** Creepage distances of reinforced insulation shall be at least
> double those specified for basic insulation in Table 17. ..."

Reinforced = 2x basic, applied to row iv's PD2-IIIa/IIIb figure of 4.0mm
gives exactly **8.0mm**.

## 3. Which table governs -- Table 16 vs Table 17

Also already resolved by PR #464's own Sec 5.1 correction (Table 17 is
creepage, Table 16 is clearance, keyed to a different axis -- rated impulse
voltage via Table 15's overvoltage-category lookup, not working voltage
directly) and independently re-confirmed this session against the same
primary-text pages: Table 16 is referenced by clause 29.1 material for
*clearance* and carries its own note, "Clearances for intermediate values
of Table 16 may be determined by interpolation" -- a genuinely different
lookup mechanism (interpolation-permitting, discrete-step-keyed) from
Table 17's already-exhaustive range partition. Nothing new to correct here;
recorded for completeness since the task that produced PR #442 originally
conflated the two.

## 4. Why PR #442 got 10.0mm

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 5.1, prior to PR #464's
correction, transcribed Table 17 with invented round-number row labels --
50/100/150/200/**300**/**400**/600V -- that do not match Table 17's actual
breakpoints (50/125/250/**400**/**500**/800V) at every row. Each label was,
in effect, a nearby real breakpoint relabeled to a round number, with the
range notation itself dropped. Reading a 400V working voltage against a
table shaped that way makes the row labelled "400" look like the obvious,
literal match -- but that label's own mm values (5.0mm basic / 10.0mm
reinforced at PD2) are actually Table 17's **row v** (>400V, <=500V)
figures, not row iv's. Once the table's real range form is restored (as
PR #464 already did in Sec 5.1, and as this document confirms
independently from primary text), 400V is unambiguous: it satisfies row
iv's own inclusive upper bound ("<=400") directly, and never needed a
round-up rule to resolve in the first place. **PR #442's reasoning was
wrong** -- not because "round up to the next row" is never a real rule
(Table 16 permits its own version of intermediate-value resolution), but
because Table 17's rows already partition the entire voltage axis, so no
working voltage on this design's boundaries (340V, 355V, 400V) ever falls
between two of them.

## 5. What this means for Option 2 (sealed compartment)

`docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md` already
states the favorable-reading consequence and has been updated (this
session) with a pointer to this document's resolution: **if** PD2 is
legitimately earned (a real, gasketed, non-vented enclosure around U3/U7,
excluded from the forced-air path -- not yet designed or argued for on this
project's own mechanical documents, per PR #464's own PD2-vs-PD3
determination), the requirement it would need to clear is **8.0mm**
reinforced, not 10.0mm. At 8.0mm, U3 (8.560mm best achievable) and U7
(8.100mm best achievable) both clear, barely. At 10.0mm, neither does. This
document supplies the primary-text-verified arithmetic; it does not resolve
whether the PD2 exception can actually be earned (a separate mechanical/
thermal question the brainstorm document already covers and this document
does not re-litigate), and it does not change what's enforced today (PD3,
12.6mm, which U3/U7 do not clear regardless).

## 6. REQ-SAFE-01, measured on this rebased branch

`main` has moved substantially since this investigation started (PR #464,
#468, #472, and others landed). This branch was rebased onto current
`origin/main` (tip `067527c9`) rather than measuring against a stale base,
per this task's own instruction to establish an independent baseline. The
validator's operative constants are **unchanged from `origin/main`** by
this PR (PD3, 12.6mm reinforced / 6.3mm basic) -- there is no "before/after"
delta to report for this change, only the current, single operative count:

```
make netlist   # elec/build/default.net rebuilt fresh on the rebased tree
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

```
109 REQ-SAFE-01 clearance/creepage violations on the real board across
75 pair(s) (11 of the records are intra-footprint). Components matched: 159.
```

This is higher than PR #464's own reported 138/86 at its own base commit
and different again from an earlier measurement this session took before
the coordinator flagged the sequencing problem this document now corrects
(75/44 at an erroneously-reverted-to 8.0mm figure, which must **not** be
read as this document's contribution -- that number was measured against a
tree that had incorrectly reverted the operative PD3 constant to PD2 levels
and has been discarded; see Sec 7). 109/75/11 is the correct, current,
rebased-tree count at the actually-enforced 12.6mm/6.3mm figures, and is
not modified by anything in this PR.
`packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`
is not modified to pass, per this task's hard constraint, and does not
pass.

## 7. Sequencing note: an earlier version of this branch would have been a safety regression, and was corrected before merging

This branch was originally built (and its first commit pushed as PR #469)
against an `origin/main` base that predated PR #464's merge. At that base,
the correct fix genuinely was to lower the validator's PD2 figure from
10.0mm to 8.0mm, and REQ-SAFE-01 dropped from 75 to 51 violations on that
now-superseded baseline. **PR #464 merged before this PR did**, replacing
the entire operative matrix with PD3 figures (12.6mm reinforced). A naive
rebase (taking this branch's own version of the conflicting hunks) would
have silently reverted that PD3 tightening back down to 8.0mm -- moving the
*operative*, enforced safety constant in the permissive direction, on the
basis of a correction that was only ever about a different pollution-degree
scenario. This was caught before pushing: the rebase conflict in
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`,
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, and the three dependent test
files was resolved by taking `origin/main`'s side entirely (PD3, 12.6mm,
unchanged) and discarding this branch's own PD2-figure edits to those
files -- this document, the new regression test (Sec 8), and the
brainstorm-doc update are the only substantive content this PR now
contributes. **No file in this PR sets `min_creepage_mm` (or any other
enforced field of `IEC60335_REQUIREMENTS`) to anything other than what
`origin/main` already has.**

## 8. A regression test against this table-form drifting back

Added: `packages/temper-placer/tests/requirements/safety/test_creepage_spec_row_form.py`
-- three tests that parse the live `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
Sec 5.1 table directly and fail if its Working Voltage column ever reverts
to a discrete-point label (PR #442's root cause) instead of Table 17's own
bounded-range form. Falsifier verified directly this session (a scratch
copy of the doc with Sec 5.1 swapped back to the old
`| 300 | ... |` / `| 400 | ... |` form was fed to the parser and the test
failed exactly as expected, listing `['300', '400']` as the offending
cells; the fixture was not committed). A third test pins row iv's specific
boundary (">250, <=400") present by name, guarding against a subtler drift
(every cell still well-formed, but row iv itself renumbered or merged away).

**Why this is a standalone test, not a new `scripts/check_derived_doc_drift.py`
config entry, assessed and rejected, not skipped:** that gate's model is "a
named gate (e.g. `OCP-01`) restated from an in-repo source-of-truth
document (`docs/FUNCTIONAL_TEST_CRITERIA.md`) into derived summary
documents, checking that qualifier words/columns survive the restatement."
Neither half fits here: (1) there is no in-repo source-of-truth document to
diff against -- the source is IEC 60335-1/IS 302-1 itself, an external,
paywalled standard this repo cannot commit a machine-readable copy of (the
same caveat this project's prior creepage evidence docs already carry
repeatedly); (2) Table 17's rows are keyed by voltage range, not a named
gate ID, so that gate's row-locator-by-gate-ID matching has nothing to
anchor to. Building a `check_derived_doc_drift.py` config entry here would
be reshaping a different problem to fit a tool built for it, not for this
one -- a plain, targeted, regex-based structural check on the one document
that actually failed is the cheap fit, and needs no new CI wiring: it lives
under `packages/temper-placer/tests/requirements/safety/`, already covered
by the `requirements-tests` GitHub Actions job's
`tests/requirements/safety/` glob (`.github/workflows/python-tests.yml`),
so it runs on every PR without any workflow-file change.

Confirmed all three new tests pass against the real, current doc, and the
full `packages/temper-placer/tests/requirements/` suite (296 passed, 5
skipped, 1 expected failure -- the real-board integration test) is
unaffected otherwise.

## 9. Sources

- IS 302-1:2008 (= IEC 60335-1, identical adoption) -- fetched fresh this
  session, `https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf`,
  pages 56-58 rendered to 150dpi PNG and read directly (not OCR'd).
- `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` (PR
  #442, the PD2 determination corrected here) -- read in full.
- `docs/evidence/2026-07-30-pollution-degree-determination.md` (PR #464,
  merged) -- read in full; independently reached the same row-iv
  conclusion for its own PD3 derivation, and is the source of the "human
  should reconcile" flag this document closes.
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 5.1 (as PR #464 left it,
  currently on `main`) -- already correctly transcribes Table 17's real
  range form and shows both PD2 and PD3 columns; unmodified by this PR.
- `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md` (PR
  #466) -- updated this session with a pointer to this document's
  resolution; its Option 2 analysis and mechanical/thermal open questions
  are otherwise unchanged.
- `packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`
  -- run this session on the rebased tree, `elec/build/default.net` built
  fresh.

## 10. Constraints honoured

- No figure invented: every number traces to the primary-text page image
  read directly this session, or to this project's own already-established
  working voltages.
- **The operative validator constant is unchanged by this PR** -- PD3,
  12.6mm reinforced, exactly as `origin/main` already has it. This PR does
  not move any enforced safety constant in either direction.
- `test_clearance.py`'s real-board integration test was not modified to
  pass, and does not pass.
- `pcb/**` and `elec/src/**` were not touched.
- No skip/xfail/deletion/assertion-weakening/`continue-on-error`/`git
  stash` used anywhere in this change. The rebase conflict was resolved via
  `git checkout --ours -- <path>` (rebase semantics: "ours" is the upstream
  commit being rebased onto, i.e. `origin/main`) followed by `git rebase
  --continue` -- no `git stash` at any point.
