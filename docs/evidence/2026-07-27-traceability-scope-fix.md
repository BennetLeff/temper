# `check_traceability.py` scope fix: from 1 sentinel directory to the registry itself

<!-- provenance: commit=220fd89ac45b5e5efa8b3be365af3e1653ed2967 dirty=true (scripts/check_traceability.py) -->

**Date:** 2026-07-27
**Responds to:** `docs/evidence/2026-07-27-gate-subset-blindness-audit.md`, finding #1
("the worst finding in the audit"): `check_traceability.py`'s R2/R3 checks
were opt-in via a `TRACEABILITY` sentinel file, exactly one directory in the
repo had one, and a live run printed `R3 gate passed: all requirements are
covered.` with zero indication that only 1 of the registry's 11 plans was
ever eligible to be checked.
**File changed:** `scripts/check_traceability.py` only.

---

## Falsifier

Stated before implementing, per the brief: **"widening the scope finds no
uncovered requirements, so the sentinel model was adequate."**

**It did not fire — and the way it failed to fire is worse than expected.**
Widening the scope did not surface a pile of newly-visible uncovered
requirements in the way `check_vacuous_gates.py`'s widening did (13 new
violations across 6 files). Instead it surfaced something more fundamental:
**the one plan that was ever eligible under the old model was itself
invisible to the requirement parser**, so R3 has been evaluating **zero**
requirements — not "some, and they happened to pass" — the entire time. The
widened, fail-closed gate now refuses to call that a pass. See "What the
widened gate found" below.

---

## The gap, quantified

| | Old model (sentinel opt-in) | New model (registry-driven) |
|---|---|---|
| Registry plans total | 11 | 11 |
| Directories eligible to be scanned for `@req` annotations | 1 (`packages/temper-placer/tests/router_v6/`) | 8 of 11 plans have non-empty `scope` → every file/dir any of them names |
| Files scanned (live, this commit) | Not reported by the gate at all | **196** (verified: `Scanned 196 file(s) across 8 of 11 registered plan(s)' declared scope`) |
| Plans whose coverage was ever actually evaluated | 1 (`N10`, the only `status: active` plan, whose scope happens to fully overlap the one sentinel directory) | Still 1 (`N10` remains the only active plan — see below for why widening scope didn't change this number) |
| Non-deferred requirements actually parsed and checked by R3 | **0** — `N10`'s own plan document doesn't use the `R<n>` requirement-ID convention the parser expects (see below), so `_parse_requirements` returns an empty set for it, and it was the *only* plan the old model would ever reach | **0** — same root cause, now reported and fail-closed instead of silently passed |
| R3's printed verdict | `R3 gate passed: all requirements are covered.` (no denominator) | `FAIL (closed): ... 0 non-deferred requirement(s) parsed ... an R3 gate that never evaluated a single requirement cannot report a meaningful pass.` |

**Why widening scope alone didn't change the requirement count:** of the 11
registered plans, only `N10` currently has `status: active`
(`docs/plans/2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md`);
the other 10 are `stale` (5), `abandoned` (3), or `completed` (2), and R3 by
design (`docs/TRACEABILITY.md`) only grades active plans — that filter is
intentional and untouched by this fix. So the *sentinel* axis (which
directory) and the *status* axis (which plan) are independent, and in this
repo's current state only the status axis was ever going to matter for R3,
because there's only one active plan to begin with.

**The second, compounding defect this surfaced:** `N10`'s plan document
structures its work as `### U1.`–`### U4.` "Implementation Units" under an
`## Implementation Units` heading, not as `- R<n>.` bullets inside an "In
scope"/"Requirements" section as `docs/TRACEABILITY.md`'s "Plan Requirement
Format" specifies. `_parse_requirements`'s regexes
(`^-\s*(R\d+)[.:]` and `\b(R\d+)\b`) only ever match `R`-prefixed IDs, so
`N10` parses to `all_reqs=set()`, `required=set()` — **before and after this
fix**. This is a pre-existing plan-document/parser format mismatch, not
something introduced by the scope-model change; it is reported here (see
"Genuinely uncovered requirements" below) rather than fixed, per the task's
instruction not to fix underlying traceability gaps in this pass.

Net effect: **R3 has been reporting "all requirements are covered" while
checking absolutely nothing** — not "a narrow but real 1/11 slice," but
zero, for two independent reasons stacked on top of each other. The old
model's blindness (sentinel gating) hid the fact that even the one plan it
could reach was itself unreadable to the parser.

**Not wired into CI.** `grep -rn check_traceability.py .github/ Makefile`
finds no invocation anywhere; `scripts/manifest.yaml` lists it and
`invocation_graph.json` shows zero importers. It is a standalone developer
tool today, not a merge gate. This doesn't change the fix (the task is
about the gate's own honesty, not its CI wiring), but it does mean nothing
in this repo's CI pipeline flips from green to red as a result of this
change — the newly-red exit code is only visible to someone running the
script directly.

---

## Scope model chosen, and why

**Chosen: drive scope from `docs/traceability-registry.yaml` itself**
(the second option the brief listed), combined with fixing a
previously-dead scope-precision check (`_is_file_in_scope`, defined but
never called in the old code) so coverage can't be gamed once the scan
universe widens.

Concretely:
- The scan universe for `@req` annotations is now the **union of every
  registered plan's `scope` entries** (files and directories), computed by
  `_collect_scope_targets()`. A `TRACEABILITY` sentinel file no longer
  gates whether a directory's annotations are scanned, or whether a plan's
  coverage is checked, at all.
- A `TRACEABILITY` sentinel that does exist still narrows which plan-ids
  are *accepted* in the directory it sits in (`docs/TRACEABILITY.md`'s
  "scoped sentinel" feature) — that per-directory restriction is preserved
  via an ancestor-directory walk (`_governing_sentinel`), so the one
  existing sentinel (`packages/temper-placer/tests/router_v6/TRACEABILITY`)
  behaves exactly as before for files under it.
- **Coverage is now scope-precise per plan.** An `@req(plan_id, req_id)`
  annotation only counts toward that requirement's coverage if the
  annotation's file is within *that same plan's* declared `scope`
  (`_is_file_in_scope`, previously written but never wired up — confirmed
  by grep before this fix: zero call sites). Without this, once the scan
  universe is no longer a single directory, an annotation belonging to one
  plan could accidentally satisfy a same-named requirement ID for a
  completely different plan sharing that directory. Verified live with a
  synthetic two-plan registry (see "Fail-closed proofs" below): an
  `@req(FAKE3, R1)` annotation sitting in a file that is *not* `FAKE3`'s
  declared scope correctly reports `FAKE3 R1` as uncovered.

**Why not the other two options:**
- *Default-include with a narrow checked-in exclude list* (the
  `check_vacuous_gates.py` shape) doesn't have a natural referent here —
  there's no fixed directory convention analogous to `packages/*/src` for
  "where annotatable code lives." The registry's `scope` field already
  names the exact files; "default-include" in this domain *is* "scan what
  the registry says," which is the option chosen.
- *Keep opt-in but fail closed on an unclaimed plan* would fix R3's silent
  skip but leaves R2 exactly as blind as before to any `@req` annotation
  written outside whichever directories happen to hold a sentinel. The
  registry already encodes, per plan, precisely which files implement it —
  more precisely than a per-directory sentinel ever could — so driving
  directly off it fixes both R2 and R3's blindness with one mechanism
  rather than patching R3 alone. (The "unclaimed plan" idea from this
  option is still implemented, just at plan-scope granularity rather than
  sentinel granularity — see next paragraph.)

**Unclaimed-scope plans still fail closed.** An active plan with an empty
`scope: []` in the registry (`N5`, `N6`, `N7` today, none of which are
currently active) now produces an explicit violation — `"{plan_id}: plan
has no declared scope ... requirement coverage cannot be verified"` —
rather than being silently `continue`d past, which is what the old code did
for exactly this case regardless of the sentinel model. Verified with a
synthetic registry below.

**No allowlist added.** The scope is 100% derived from
`docs/traceability-registry.yaml`, which is itself kept honest by
`--check-registry-scope` (every scope entry must be a git-tracked file).
There is no new file a maintainer must remember to update, and nothing here
can silently accumulate stale entries the way a hand-maintained include-list
or `--init`-populated allowlist could.

---

## Denominator reporting (task item 3)

All three sub-checks now print their denominator on **both** pass and fail,
matching `check_domain_partition.py`'s reference pattern:

- **R2** (`--check-annotations`): `"Scanned N file(s) across P of Q
  registered plan(s)' declared scope ...; found A @req annotation(s)."`
- **R3** (`--check-coverage`): `"Annotation scan: N file(s) across P of Q
  ...; Checked C of X active plan(s) (U with no declared scope) out of Q
  total registered plan(s); R non-deferred requirement(s) parsed; V
  uncovered."`
- **Registry scope** (`--check-registry-scope`): `"Checked Q plan(s), S
  scope entrie(s)."`

Live, this commit: R2 — `Scanned 196 file(s) across 8 of 11 registered
plan(s)' declared scope ...; found 10 @req annotation(s).` R3 — `Annotation
scan: 196 file(s) across 8 of 11 ...; Checked 1 of 1 active plan(s) (0 with
no declared scope) out of 11 total registered plan(s); 0 non-deferred
requirement(s) parsed; 0 uncovered.` Registry scope — `Checked 11 plan(s),
55 scope entrie(s).`

---

## What the widened gate found

Running `--all` at this commit (`python3 scripts/check_traceability.py
--all`, exit 1 both before and after this fix, for different reasons):

**R2 (annotation validity) — 10 violations, unchanged in content by this
fix** (pre-existing, not introduced by the scope-model change — the
annotations triggering them were already the only annotations the old
model could see, since they live in the one sentinel directory):
- 6× `requirement 'U1'..'U4' not defined` — `N10`'s own annotations,
  invisible to the `R<n>`-only parser (see above).
- 4× (in pairs, 2 lines each) `plan 'APC1' has status 'completed', expected
  'active'` — `APC1` was marked `completed` by
  `docs/plans/2026-07-24-...`-era plan sweeps after its annotations were
  written; the annotations were never removed.

**R3 (coverage) — flips from a false pass to a correctly fail-closed
result**, as detailed above: 0 of 11 plans have a non-deferred requirement
that was ever actually parsed and checked, because the only active plan
uses a requirement-ID convention the parser doesn't recognize.

**Registry scope — 6 pre-existing violations, unchanged by this fix:**
`packages/temper-drc/` no longer exists as a package (renamed/restructured
to `temper-drc-rs`, a Rust crate) — `N2`'s and `N4`'s `scope` entries
(5 files total) point at a Python package tree that is gone, plus `APC1`'s
scope lists the `router_v6/` directory itself, which trivially isn't a
single git-tracked *file*.

---

## Genuinely uncovered requirements, ranked by consequence

*(Per the task: these are reported, not fixed — fixing plan-document
format drift or registry staleness is separate work.)*

1. **`N10`'s 4 implementation units (`U1`–`U4`) are functionally
   ungraded by R3, despite having live `@req` annotations in code.**
   This is the highest-consequence finding: a developer did exactly the
   right thing (wrote `@req(N10, U1)`-style annotations, placed a
   `TRACEABILITY` sentinel, registered the plan) and the gate still cannot
   verify coverage, because the plan document's own "Implementation Units"
   heading convention (`### U1.`) isn't one of the three heading patterns
   `_parse_requirements` recognizes (`In scope`, `Requirements`, `Scope
   Boundaries`) and its list items aren't `R<n>`-prefixed. **Fix options
   for a follow-up** (not applied here): either restructure `N10`'s plan
   document to use `R<n>` IDs under a recognized heading, or extend
   `_parse_requirements`'s heading/ID recognition to also accept `U<n>`
   under `## Implementation Units` — the latter is a parser change, which
   is explicitly out of scope for this pass per the brief.
2. **`APC1`'s in-code annotations reference a plan that is no longer
   `active`.** 4 violations, all in `packages/temper-placer/tests/
   router_v6/test_*.py`. Since `APC1` (`docs/plans/2026-07-19-001-...`) is
   now `completed`, R2 already, correctly, flags these — this was true
   before this fix and remains true after. Ranked lower than #1 because
   it's a loud, already-firing violation (not a silent gap) and the fix is
   mechanical: either restore `APC1` to `active` if work continues, or
   strip the stale annotations.
3. **`N2` and `N4`'s registry scope entries point at a package
   (`packages/temper-drc/`) that no longer exists.** Both plans are
   non-active (`stale`/`abandoned`) so this doesn't affect R3's coverage
   grading today, but it means `--check-registry-scope` will keep failing
   on stale data indefinitely unless someone either updates the entries to
   `temper-drc-rs`'s current file layout or removes the scope entries for
   these abandoned plans. Pre-existing; unchanged by this fix.
4. **`N5`, `N6`, `N7` have empty `scope: []` in the registry.** All three
   are `stale`/`abandoned` today, so the new "unclaimed active plan is a
   violation" logic added by this fix doesn't currently fire for them —
   but if any of the three were ever reactivated without also populating
   `scope`, the new fail-closed check would immediately catch it (verified
   synthetically below), which is the intended improvement.
5. **`APC1`'s own registry `scope` entry includes the directory
   `packages/temper-placer/tests/router_v6/` itself**, in addition to
   13 specific `router_v6` source files. This is legal under the new model
   (a directory scope entry pulls in every `.py`/`.c`/`.h` file under it)
   but is unusually broad for a single plan and is why `APC1` shows up as
   git-scope-invalid in finding #3's sibling violation (a directory isn't
   a "file"). Not fixed; flagged for whoever next touches `APC1`'s
   registry entry.

## UNVERIFIED

- **Whether extending `_parse_requirements` to recognize `U<n>` IDs under
  `## Implementation Units` would be the right fix for finding #1**, versus
  requiring plan authors to use `R<n>` IDs consistently. Not resolved here
  — a parser-format change is explicitly the kind of "underlying
  traceability gap" fix the brief said not to make in this pass.
- **Whether any other active-status plan exists in a different worktree's
  in-progress edits to `docs/traceability-registry.yaml`** that would
  change the "1 active plan" count measured here. This was measured
  exactly at this commit (`220fd89a`); three other agents are working
  concurrently on `pcb/`, `elec/src`, and docs per this session's own
  instructions, none of which this fix touched.
- **Whether `packages/temper-drc`'s Rust successor (`temper-drc-rs`)
  should be re-registered under `N2`/`N4`'s scope**, or whether those two
  plans should simply be left `stale` with acknowledged-dead scope
  entries. A registry-content decision, not a gate-mechanism one.

---

## Fail-closed proofs

All proofs run against synthetic registries via the new `--registry`
CLI override (added specifically so these could be exercised without
touching the real `docs/traceability-registry.yaml`); none left any file
in the repo tree (a single transient in-repo fixture,
`scripts/_traceability_proof_harness.py`, was created for the
scope-precision and happy-path proofs and deleted immediately after; `git
status --porcelain` confirmed clean before and after).

| Test | Setup | Result |
|---|---|---|
| Missing registry | `--registry <nonexistent path>` | `FAIL (closed): traceability registry not found at ...` / exit 1 |
| Empty registry (zero plans) | `--registry <file with 'plans: {}'>`, `--all` | All three sub-checks fail closed: R2/R3 report `Scanned/Annotation scan: 0 file(s) across 0 of 0 ...` and refuse to pass on zero files; registry-scope reports `declares zero plans` / exit 1 |
| Zero requirements parsed | 1 active plan, non-empty scope (1 real file, 0 annotations), plan doc with prose but no `R<n>` items | `FAIL (closed): ... 1 file(s) ... 0 non-deferred requirement(s) parsed ... never evaluated a single requirement` / exit 1 — distinct code path from the zero-files case (1 file *was* scanned) |
| Unclaimed active plan (empty `scope: []`) | 2 plans: one real scope + 0 reqs, one active with `scope: []` | `UNCOVERED: FAKE2: plan has no declared scope ...` printed as a violation, not silently skipped / exit 1 |
| Scope-precision (annotation in the wrong plan's scope) | `FAKE3` scope = file A (no annotations); `FAKE4` scope = file B, which carries `@req(FAKE3, R1)` | `UNCOVERED: FAKE3 R1: no @req annotation found in the plan's declared scope` — the annotation existing elsewhere in the scan universe does NOT satisfy `FAKE3`'s coverage / exit 1 |
| Happy path (real coverage) | 1 active plan, scope = 1 file containing a matching, correctly-scoped `@req` annotation | `R3 gate passed: all requirements are covered. ... 1 non-deferred requirement(s) parsed; 0 uncovered.` / exit 0 |
| Real repo, `--all` | `python3 scripts/check_traceability.py --all` | exit 1 (10 R2 violations + R3 fail-closed + 6 registry-scope violations, all detailed above) |

---

## Protected-gate verification

Required to stay exit 0 (none of these were modified; verified unaffected):

| Gate | Result |
|---|---|
| `make netlist` | exit 0, **76** assertion rows (counted `PASSED`/`FAILED` rows in build output) |
| `check_domain_partition.py` | exit 0 — `Checked 48 declared nets across 2 domains (HV, SELV) ... over 165 compiled nets / 170 components` |
| `capacity_budget_gate.py` | exit 0 — `Design capacity budget gate PASSED — 0 defects` |
| `mpn_fabrication_gate.py` | exit 0 — `MPN fabrication gate PASSED -- 0 new violations` |
| `check_derived_doc_drift.py` | exit 0 — `Derived-document drift gate passed` |
| `check_vacuous_gates.py` | exit 0 — `Anti-vacuous-truth gate passed ... 0 violations` (not modified by this fix; this repo state already has zero unguarded `all()` calls, independent of this change) |

No files under `pcb/`, `elec/`, or router source were touched. `git diff
--stat` against base: `scripts/check_traceability.py | 327
+++++++++++++++++++++++++++++++++++-------` — the only file changed.

---

## Verification: falsifier restated

**"Widening the scope finds no uncovered requirements, so the sentinel
model was adequate."** Did not fire. What it found instead is arguably
worse than a pile of newly-visible uncovered requirements would have been:
the sentinel model's one reachable plan was *also* unreachable to the
requirement parser, meaning R3's true historical checked-requirement count
at this commit, under both the old and new model, is zero. The fix's value
is not "found N new violations" — it's that `R3 gate passed: all
requirements are covered` can no longer be printed when nothing was ever
checked; the gate now says so, loudly, in the same run.
