<!-- provenance: commit=ca703e7186e2aca90e36f76c3437e4bcc0e745c8, base=3541512ab4786b8637c69ac592e2a572022d98bc (origin/main, post-rebase), dirty=false, branch fix/traceability-regex-and-dangling-reqs, worktree /home/bennet/Desktop/temper-worktrees/fix-traceability-regex. All commands below were run directly against this commit on this machine (Linux x86_64, Python 3.12.3 via /home/bennet/Desktop/temper/.venv/bin/python). No pcb/** file was modified. Builds on docs/evidence/2026-08-12-dangling-reference-count-verification.md (PR #1093, branch verify/dangling-reference-counts, commit 2c98375b2, not yet merged to main at time of writing) -- that report's hand-verified 15-genuinely-dangling / 28-ambiguous / 103-resolvable breakdown is independently re-confirmed here against this fix's actual output, not re-derived from scratch. -->

# Traceability gate: fix the `\w+` regex, then triage what it reveals

**Verdict up front:** the defect was real and is fixed. `check_traceability.py`'s
`@req` regex used `\w+` for both the plan-id and req-id fields, which cannot
match a hyphen — every date-stamped plan-id (`2026-06-23-004`) and every
hyphenated req-id (`R-D5`, `U8-1`, `FR-ADOPT1`) failed to match, in or out of
scope. Widened both character classes based on a survey of every `@req(...)`
call-site actually in this repo (`scripts/check_traceability.py:168-169`).
**In-scope annotations found by the gate's own `--check-annotations` run: 12 →
46.** All 46 still fail (0 pass, same as before: all 12 pre-fix annotations
already failed too) — but the *composition* of the failures changed, and that
composition is the real finding. Of the 34 newly-visible violations: **3 are
one of the 15 genuinely-dangling references** (`2026-06-29-feat-los-bb`,
confirmed nonexistent), **25 are members of the "ambiguous same-date sibling
plan" class** documented in the prior verification, and **6 are real,
resolvable annotations that fail for an orthogonal reason** — the registry
(`docs/traceability-registry.yaml`) indexes plans by an 11-entry short-code
list (`N1`-`N10`, `APC1`), not by date-stamped id, so a correctly-cited
`@req(2026-06-23-007, R3)` fails R2 not because anything about it is wrong but
because `2026-06-23-007` was never added to the registry under that string.
**That is a new, separate, and much larger structural gap than the 15
dangling references this task was scoped to triage** — it affects the
majority of this repo's real annotations and is reported, not fixed, per the
"do not soften the gate" instruction. Repo-wide (not gate-scope-limited): the
fixed regex now matches **111 of ~165** real `@req(...)` call-sites (up from
14 matched by the old regex, repo-wide). The residual 54 are invisible for two
*further* dialects the character-class fix does not address — a 3+-field call
form (5 sites) and, far more significantly, a no-comment-marker docstring form
(**49 sites**, not the "1" the prior verification's Category D estimated —
see §4). Also fixed: the `--check-registry-scope` false positive on
directory-shaped scope entries, and `docs/TRACEABILITY.md`'s description of a
scope model the code stopped implementing on 2026-07-27. No `pcb/**` file was
touched.

---

## 1. The defect, and the character-class survey it was fixed against

`scripts/check_traceability.py:139-140` (pre-fix):

```python
_PYTHON_REQ_RE = _re.compile(r"#\s*@req\((\w+),\s*(\w+)\):?(.*)")
_C_REQ_RE = _re.compile(r"//\s*@req\((\w+),\s*(\w+)\):?(.*)")
```

`\w+` is `[A-Za-z0-9_]+` — no hyphen, no slash. Before choosing a wider
character class, surveyed every `@req(...)` call-site actually present in the
repo (`git ls-files | grep -E '\.(py|c|h|rs)$' | xargs grep -ho '@req([^)]*)'
| sort -u`, 100 distinct call shapes) and `docs/plans/` filenames
(`ls docs/plans/`, all `YYYY-MM-DD-NNN-<slug>-plan.md`). Two real shapes
needed a wider plan-id class:

- Bare date-stamped id: `2026-06-23-004` — digits and hyphens.
- Full filename stem: `2026-07-09-001-feat-physics-verification-rigor-plan`
  — digits, hyphens, and lowercase words.

And req-ids in real use are not always bare `R<num>`: `R-D5`
(`packages/temper-placer/tests/integration/_seed_filter_synthetic_routing.py:14`),
`U8-1`/`U8-2`/`U8-3` (`scripts/pr_scorecard.py:21,45,107`), `FR-ADOPT1`
etc. (`packages/temper-placer/tests/router_v6/sat_property_strategies.py`),
and one dialect packs two ids into one field with `/` instead of a second
comma: `R2/K4`
(`packages/temper-orchestration/src/zone_aware_slot_generation_stage.rs:66,69`).

Fix (`scripts/check_traceability.py:168-169`):

```python
_PYTHON_REQ_RE = _re.compile(r"#\s*@req\(([\w-]+),\s*([\w/-]+)\):?(.*)")
_C_REQ_RE = _re.compile(r"//\s*@req\(([\w-]+),\s*([\w/-]+)\):?(.*)")
```

Plan-id: `[\w-]+`. Req-id: `[\w/-]+` (adds `/` for the slash dialect).

**Other languages carrying `@req` the old regexes couldn't reach, checked per
the task's instruction:** Rust. `grep -rl '@req(' --include='*.rs'` finds 2
files (`packages/temper-drc-rs/src/drc_oracle.rs`,
`packages/temper-orchestration/src/zone_aware_slot_generation_stage.rs`), and
`.rs` was entirely absent from `_SOURCE_SUFFIXES = (".py", ".c", ".h")`
(`:72`) — invisible for a second, independent reason on top of the regex.
Added `.rs`; it reuses `_C_REQ_RE` via the existing
`suffix == ".py" ? PY : C` fallback, no new regex needed. **This has zero
effect on today's scanned-file count** — no registered plan's `scope:` in
`docs/traceability-registry.yaml` names any `.rs` path, so no `.rs` file is
in the scan universe regardless — it closes the gap for whenever one is
added. One of the two Rust call-sites
(`drc_oracle.rs:20-21`, `` `@req(2026-06-23-007,\n  R3)` ``) splits the
annotation across two lines inside a `//!` doc-comment; no single-line regex,
in any language, can match that. Left unaddressed — a distinct, multi-line
parsing problem, not a character-class problem.

## 2. Verification: the fixed gate matches what the old one couldn't, and fails on a confirmed-dangling one

Before (pre-fix, this exact command, same commit and scope):

```
$ .venv/bin/python scripts/check_traceability.py --check-annotations
VIOLATION: .../conftest.py:3: requirement 'U1' not defined in ...
VIOLATION: .../test_all_pad_tree_routing.py:1: plan 'APC1' has status 'completed', expected 'active'
  ... (12 VIOLATION lines total)
Scanned 335 file(s) across 8 of 11 registered plan(s)' declared scope in docs/traceability-registry.yaml; found 12 @req annotation(s).
```

After (this commit):

```
$ .venv/bin/python scripts/check_traceability.py --check-annotations
VIOLATION: packages/temper-placer/tests/router_v6/test_constraints_drc_oracle_rust_differential.py:171: plan-id '2026-06-23-007' is not in the registry
VIOLATION: packages/temper-placer/tests/router_v6/test_astar_cluster_rust_differential.py:128: plan-id '2026-06-29-feat-los-bb' is not in the registry
VIOLATION: packages/temper-placer/tests/router_v6/test_los_bb_shortcut.py:85: plan-id '2026-06-29-feat-los-bb' is not in the registry
VIOLATION: packages/temper-placer/tests/router_v6/test_los_bb_shortcut.py:110: plan-id '2026-06-29-feat-los-bb' is not in the registry
  ... (46 VIOLATION lines total)
Scanned 336 file(s) across 8 of 11 registered plan(s)' declared scope in docs/traceability-registry.yaml; found 46 @req annotation(s).
```

(335 -> 336 files scanned between the "before" and "after" runs above is
unrelated churn: this branch was rebased onto a newer `origin/main` between
those two measurements, which landed one additional file into an
already-in-scope directory. Confirmed it carries no `@req` annotation of its
own — the found-annotation count is unaffected, 46 either way.)

Exit code: 1 (unchanged — the gate already failed pre-fix; it now fails
*louder and for more distinguishable reasons*).

**Matching what the old regex structurally could not**:
`test_constraints_drc_oracle_rust_differential.py:171` cites
`@req(2026-06-23-007, R3)`. The old regex fails at the first character of
`2026-06-23-007` (the `2026` matches `\w+`, then the literal `-` breaks the
match — no fallback, no partial credit). The fixed regex parses it correctly
(`plan_id='2026-06-23-007'`, `req_id='R3'`) — the gate now knows this
annotation exists at all. It still reports a violation, but for a
*legitimate, orthogonal* reason (§3): `2026-06-23-007` is a real plan
(`docs/plans/2026-06-23-007-feat-isolation-slots-slotgen-plan.md`), `R3` is a
real, defined requirement there (`:102`, `"R3 (K4 constants are
config-derived)."`), and it is simply not a key in
`docs/traceability-registry.yaml`.

**Failing on one of the 15 genuinely-dangling references**:
`test_astar_cluster_rust_differential.py:128` and
`test_los_bb_shortcut.py:85,110` cite `@req(2026-06-29-feat-los-bb, ...)`.
`git log --all --oneline --diff-filter=A -- "docs/plans/2026-06-29*"` returns
only `2026-06-29-001-feat-coarse-to-fine-a-star-corridor-routing-plan.md` —
no `2026-06-29-feat-los-bb` document, ever, on any branch. The fixed gate
correctly reports `plan-id '2026-06-29-feat-los-bb' is not in the registry`
for all 3 in-scope instances of this dangling reference (2 more instances of
the same dangling id live outside the registry's declared scope — see §4).

## 3. The registry-namespace gap this fix exposed (not fixed — reported)

Of the 34 newly-visible violations, breaking down the 5 distinct plan-ids
involved:

| Plan-id | Count | Status |
|---|---:|---|
| `2026-06-23-007` | 4 | Real plan, real requirement. Not registered under this string. |
| `2026-06-28-001` | 15 | **Ambiguous** — 3 same-date candidate plans (§5). |
| `2026-06-28-006` | 10 | **Ambiguous** — 2 same-date candidate plans (§5). |
| `2026-06-29-001` | 2 | Real plan (`R5`, coarse-to-fine A* corridor routing plan), not registered. |
| `2026-06-29-feat-los-bb` | 3 | **Genuinely dangling** — no such plan ever existed (§4). |

`check_annotations`'s R2 gate (`scripts/check_traceability.py:296-376`)
requires `plan_id in plans` where `plans` is
`docs/traceability-registry.yaml`'s 11-key dict (`N1`-`N10`, `APC1`). Almost
no date-stamped plan-id is registered under its own string — the registry was
built to alias a small hand-picked set of plans to short codes, not to index
every plan in `docs/plans/`. **This means essentially every correctly-cited,
non-dangling, non-ambiguous date-stamped annotation in this repo will fail R2
forever, regardless of the regex fix**, until either the registry is
populated with an entry per cited plan-id, or R2's validity check is changed
to resolve a date-stamped plan-id directly against `docs/plans/` filenames
instead of requiring a registry alias. **This is not part of the 15
genuinely-dangling references** — conflating "not a registry key" with
"dangling" would be exactly the kind of over-count the task warned against.
It is reported here as a distinct, much larger, structural finding, not
fixed — fixing it is a registry-design decision (bulk-populate vs.
change-the-lookup) out of this task's stated scope (character-class fix +
the two named Part 3 defects).

## 4. Triage of the 15 genuinely-dangling references

Independently re-derived from this repo's current `HEAD`, not copied from the
prior verification — every location below was re-located and re-checked by
hand for this report.

| Plan-id / req-id | Locations | Finding | Action |
|---|---|---|---|
| `2026-06-29-feat-los-bb`, `R1`/`R3`/`R4` (5 sites) | `packages/temper-placer/tests/router_v6/test_astar_cluster_rust_differential.py:128`; `.../test_los_bb_shortcut.py:7,85,110`; `packages/temper-placer/src/temper_placer/router_v6/_astar_theta_star.py:80` | No plan document named `2026-06-29-feat-los-bb` (or similar) has ever existed on any branch (`git log --all --diff-filter=A -- "docs/plans/2026-06-29*"` → only `2026-06-29-001-...corridor-routing...md`, unrelated content). The implementing commits are real (`49c422937` "add BB empty-space shortcut... (U1)", `23d73e15a` "(U3)", `87bd70f1a` "(U2)", merged at `3484450c4` "feat/bb-empty-shortcut") — real work, against a plan that was apparently never written or never committed. The 2026-06-29-001 sibling plan (same date) was checked as a candidate and ruled out: its R1/R3/R4 are about coarse-grid max-pooling and corridor extraction, not the BB (bounding-box) line-of-sight shortcut these annotations describe. **No renamable target found. Reported, not rewritten.** |
| `2026-07-22-005`, `R1`/`R2`/`R6` (5 sites) | `packages/temper-placer/tests/constraint_types/test_placement_constraints.py:3,4,5`; `.../test_config.py:3,4` | No plan document named `2026-07-22-005` has ever existed (`git log --all --diff-filter=A -- "docs/plans/2026-07-22*"` → `2026-07-22-001` and `2026-07-22-004`, neither matching). Two *other* files independently cite the same id in prose — `.github/workflows/python-tests.yml:2113` (`"Verify config reference doc is up-to-date (plan 2026-07-22-005, U7)"`) and `scripts/manifest.yaml:1757` (`"...(plan 2026-07-22-005)"`) — confirming this id was assigned and used consistently across 3 independent files, not a one-off typo, but the document itself is simply absent everywhere. The implementing commits (`e76aaf645` "U1-U4", `9113a808d` "U5-U7") describe real Pydantic-migration work matching the cited requirements' shape but name no plan file in their own commit messages. **No candidate document found to rename to. Reported, not rewritten.** |
| `2026-06-28-011`, `U8-1`/`U8-2`/`U8-3` (3 sites) | `scripts/pr_scorecard.py:21,45,107` | Plan exists (`docs/plans/2026-06-28-011-feat-pipeline-observability-plan.md`) and its `### U8. PR scorecard CI workflow` unit exists and clearly matches this file's purpose — but `U8`'s own **Requirements: R9, R10** (`:380`), no `U8-1`/`U8-2`/`U8-3` subdivision anywhere in the document. The 3 annotations' own notes ("Load metrics files...", "Group records...compute deltas", "Formatted markdown table output") plausibly map onto R9 ("PR-triggered CI workflow runs pipeline...") and R10 ("Auto-posted PR comment delta table...") — but not 1:1 (3 sub-annotations, 2 defined requirements; `U8-1`'s "load metrics" step plausibly supports both). **Not rewritten**: correcting `U8-1`/`U8-2`/`U8-3` to `R9`/`R10` requires an editorial judgment call about which annotation maps to which requirement that the plan document itself never made — a fabricated mapping, not a recovered one. Reported instead. |
| `U9`, `R1` (2 sites) | `packages/temper-placer/src/temper_placer/validation/drc_oracle.py:250`; `packages/temper-placer/tests/validation/_drc_oracle_py_oracle.py:195` | `U9` is not a registered plan-id, not a `docs/plans/` filename prefix, and — checked independently here — `git blame`/`log -S` traces the introducing commit to `2f4f96291` ("feat(drc): Rust DRC engine (temper-drc-rs) with 33 checks"), whose own commit message names `Plan: docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md` — **that plan document has also never existed on any branch** (`git log --all --diff-filter=A -- "docs/plans/2026-06-30-003*"` returns nothing). So chasing this one goes two levels deep before terminating in a *second*, independently-orphaned plan citation (this one in a commit message, not an `@req` tag, so it isn't part of the 164-call-site count, but it corroborates that `U9` is not a slipped digit for some other real id — the trail runs out at a plan that was never written, same as `2026-06-29-feat-los-bb` and `2026-07-22-005`). `### U9.` is also, independently, a common internal section label in 24+ other plan documents (`grep -c '^### U9\.' docs/plans/*.md`), so even setting the missing-plan trail aside, the bare token can't identify a target. **Unresolvable by any means tried. Reported, not rewritten.** |

**5 + 5 + 3 + 2 = 15**, matching the prior verification's hand-count exactly.
None of the 15 were rewritten: every one was checked for a same-day sibling
or a commit-message trail that would make the correction mechanical
(a genuine typo or rename), and none had one — every trail terminates in
either "no such document, anywhere" or "the document exists but never defined
the cited sub-unit." Per the task's instruction, a dangling `@req` is
evidence real work was done against a requirement someone believed existed;
none of the 15 annotations were deleted or edited.

## 5. The 28 ambiguous cases: a distinct defect class, not hand-resolved

Re-confirmed here (not re-hand-resolved — the prior verification already
walked all 4 groups against plan content):

| Plan-id | In-scope count (this report) | Candidate plans sharing the date |
|---|---:|---|
| `2026-06-23-001` | (out of registry scope; not in the 34) | `2026-06-23-001-feat-hv-lv-guard-strip-plan.md`, `...-feat-strangler-stage4-astar-plan.md`, `...-feat-wholesale-stale-dir-purge-plan.md` |
| `2026-06-28-001` | 15 | `...-feat-astar-pathfinding-validation-plan.md`, `...-feat-constraint-lowering-compiler-plan.md`, `...-feat-router-v6-rust-topology-plan.md` |
| `2026-06-28-006` | 10 | `...-feat-railway-bmc-encoding-correctness-plan.md`, `...-feat-sat-encoding-optimization-experiment-plan.md` |
| `2026-07-23-001` | (out of registry scope) | `...-feat-finish-the-board-drc-erc-guard-plan.md`, `...-perf-cp-sat-benchmarks-plan.md` |

Confirmed by `ls docs/plans/ | grep '^<date>'` for each date: every group
genuinely has 2-3 plan documents sharing the same `YYYY-MM-DD-NNN` prefix.
The `@req(2026-06-28-001, R7)` annotation, by itself, is not machine-resolvable
— it requires reading the annotation's own free-form note and matching it
against each candidate plan's content to pick the right one (the prior
verification did exactly this for all 28, by hand). This is **not** hand-fixed
in this PR, per the task's instruction that it would "re-break": today's
plan-id format (`YYYY-MM-DD-NNN`) is not a unique key across the repo's own
plan-naming convention, and any hand-resolution encoded into an annotation's
literal text would silently stop being verifiable the next time two plans
share a date.

**Structural fix recommendation** (not implemented — a plan-naming-convention
change, out of this task's scope): three options, in order of preference:

1. **Require the full plan filename stem as the plan-id**, not just the date
   prefix — this repo already has annotations doing this voluntarily
   (`2026-07-09-001-feat-physics-verification-rigor-plan`, §1) and it is
   unambiguous by construction, since `docs/plans/` filenames are unique.
   Costs verbosity per annotation.
2. **A uniqueness check on `docs/plans/` filenames** (a new, cheap CI gate:
   fail if two plan files share a `YYYY-MM-DD-NNN` prefix) — doesn't fix
   existing ambiguous annotations but stops the count from growing, and is a
   five-line script.
3. **A disambiguating suffix convention** (`2026-06-28-001a`,
   `2026-06-28-001b` assigned at plan-creation time) — smaller diff to
   existing filenames than (1), but requires a one-time rename pass across
   every colliding plan and every citing annotation, and is more work than
   (2) for less benefit than (1).

## 6. `--check-registry-scope` false positive (fixed)

`scripts/check_traceability.py:219-224` (pre-fix) tested every scope entry
for exact membership in `git ls-files`' output:

```python
for scope_entry in plan_entry.get("scope", []):
    if scope_entry not in git_files_set:
        violations.append(f"{plan_id}: scope entry '{scope_entry}' is not tracked by git")
```

`git` does not track directories as entries in their own right — `git
ls-files` lists files only — so a directory-shaped scope entry (trailing
slash, e.g. `packages/temper-placer/tests/router_v6/`, the same convention
`_iter_source_files` already treats as "recurse this directory",
`:98-104`) can **never** pass this exact-membership test, regardless of
whether the directory or its 300+ real files exist:

```
$ git ls-files | grep -c '^packages/temper-placer/tests/router_v6/'
310
```

Before fix: `SCOPE ISSUE: APC1: scope entry
'packages/temper-placer/tests/router_v6/' is not tracked by git` — a false
positive on real content. Fixed (`scripts/check_traceability.py:233-238`) by
checking any-file-under-prefix for a directory-shaped entry instead of exact
membership:

```python
if scope_entry.endswith("/"):
    if not any(f.startswith(scope_entry) for f in git_files_set):
        violations.append(...)
elif scope_entry not in git_files_set:
    violations.append(...)
```

Before: 7 `SCOPE ISSUE:` lines (6 real, 1 false positive). After: 6
`SCOPE ISSUE:` lines, all real (5 pointing into the deleted
`packages/temper-drc/`, 1 for APC1's retired `all_pad_evidence.py`) — the
false positive is gone, nothing real was suppressed:

```
$ .venv/bin/python scripts/check_traceability.py --check-registry-scope
SCOPE ISSUE: APC1: scope entry '.../all_pad_evidence.py' is not tracked by git
SCOPE ISSUE: N2: scope entry '.../test_safety_constant_lint.py' is not tracked by git
SCOPE ISSUE: N4: scope entry '.../_safety_keywords.py' is not tracked by git
SCOPE ISSUE: N4: scope entry '.../creepage.py' is not tracked by git
SCOPE ISSUE: N4: scope entry '.../hv_lv_separation.py' is not tracked by git
SCOPE ISSUE: N4: scope entry '.../isolation.py' is not tracked by git
Checked 11 plan(s), 55 scope entrie(s).
```
Exit code: 1 (still red, correctly — the 6 real issues are unrelated to this fix and remain).

## 7. `docs/TRACEABILITY.md` (corrected)

Rewrote the doc's description of the scope model from the pre-2026-07-27
per-directory `TRACEABILITY`-sentinel-gates-scanning model to the current
registry-`scope:`-driven model (matching
`scripts/check_traceability.py`'s own module docstring, `:12-60`). Also:
removed the reference to `packages/temper-drc/tests/test_traceability_gate.py`
(deleted along with `packages/temper-drc/`); documented the real plan-id/
req-id character classes and the two dialects still unhandled after this fix
(3+-field, no-comment-marker); documented `--check-registry-scope` (previously
undocumented entirely); and added a "CI Wiring" section stating plainly that
`check_traceability.py` is `disposition: utility`
(`scripts/manifest.yaml:1142`) and is not invoked by any
`.github/workflows/*.yml` job — a red or green run today has no effect on
whether a PR merges. Full diff in this PR's commit
`docs(traceability): correct TRACEABILITY.md to describe the post-2026-07-27
scope model`.

## 8. The no-comment-marker dialect: bigger than previously estimated

Measuring directly (excluding `scripts/check_traceability.py`'s own
in-source example text, which pollutes a naive line-scan): **165** raw
`@req(...)` call-sites across `.py`/`.c`/`.h`/`.rs` files (163 in `.py`/`.c`/
`.h` alone — 1 less than the prior verification's 164, most likely a single
counting-convention edge case, not chased further). The fixed regex matches
**111**. The **54** unmatched split as:

- **49** are a bare `@req(plan-id, req-id)` with **no `#`/`//` comment-marker
  prefix at all** — inside a module or function docstring
  (e.g. `packages/temper-placer/tests/physics/test_thermal_fdm_invariants_pbt.py:14-18`,
  five sites in one docstring; `packages/temper-placer/tests/constraint_types/test_config.py:3-4`).
  This is the same dialect the prior verification's "Category D" identified,
  but that report counted only **1** instance
  (`test_bottleneck_map.py:3`) because it defined Category D narrowly as
  "non-hyphenated" specifically to avoid double-counting against Category C
  — every hyphenated no-marker instance was folded into C's 144 instead.
  Measuring "how many call-sites lack a comment marker at all," regardless of
  hyphenation, the real count is **49**, not 1.
- **5** are the 3+-comma multi-field form (`@req(id, R1, R2, R3, ...)`),
  matching the prior verification's Category E exactly.

Neither dialect is addressed by this fix — both are a different defect class
from the character-class problem this task was scoped to fix (the comment-marker
requirement and the fixed-2-argument shape are structural parser limitations,
not a too-narrow character class), and are reported here rather than folded
into an expanded regex, consistent with keeping this fix to what was asked.

## 9. Before/after summary

| Metric | Before | After |
|---|---:|---:|
| Files in gate's declared scan universe | 335 | 336 (+1 unrelated rebase churn mid-task, not from this fix — the `.rs` addition itself affects 0 files, no registry scope entry names one) |
| `@req` annotations found **in scope** (gate's own report) | 12 | **46** |
| Of those, violations (gate's own report) | 12 (100%) | 46 (100%) |
| `--check-registry-scope` false positives | 1 | 0 |
| `--check-registry-scope` real issues | 6 | 6 (unchanged) |
| `@req` call-sites matched **repo-wide**, any scope (independent measurement) | 14 | **111** (of 165 real call-sites) |
| Genuinely-dangling references (hand-verified) | 15 (prior verification) | **15 confirmed** (independently re-derived here) |
| Ambiguous references (structural, same-date collision) | 28 (prior verification) | **28 confirmed** (not hand-resolved — see §5) |
| Newly-discovered residual blind spots | — | 49 no-comment-marker + 5 multi-field = 54 call-sites, repo-wide, still unmatched (§8) |

## 10. Is the gate blocking, or does it need staging?

**Non-blocking today, and should stay that way for now.**
`scripts/check_traceability.py` is `disposition: utility`
(`scripts/manifest.yaml:1142`) and `grep -rn "check_traceability"
.github/workflows/` returns nothing — no workflow invokes it, so nothing
about this fix changes whether any PR merges. It should not be flipped to a
hard CI gate as-is, for a reason independent of the 15/28 triage above: doing
so today would reject essentially every real, correctly-cited date-stamped
annotation in the repo, because of the registry-namespace gap in §3, not
because those annotations are wrong. Turning this into a blocking gate needs,
at minimum: (a) the registry populated with an entry for every plan-id
actually cited by a real annotation (or R2 changed to resolve a date-stamped
plan-id directly against `docs/plans/` filenames, bypassing the registry-alias
requirement for that case), and (b) a structural fix for the 28 ambiguous
cases (§5) so a same-date collision doesn't manufacture a permanent false
positive. Neither is done here — both are reported as follow-up work, per the
task's instruction not to launder new findings into invisible scope creep.
