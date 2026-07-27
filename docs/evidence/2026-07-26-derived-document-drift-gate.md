# Derived-document drift gate: decision, proofs, and live findings

<!-- provenance: commit=f46c32d122312533cf136b02c262c648c2627034 dirty=UNKNOWN -->

**Date:** 2026-07-26
**Scope:** `scripts/check_derived_doc_drift.py`, `scripts/derived_doc_gates.yaml`,
`scripts/tests/test_check_derived_doc_drift.py`, CI wiring in
`.github/workflows/python-tests.yml`.
**Status:** implemented, tested, wired fail-closed, soft-launched (see
"Wiring and soft launch" below). Not a design document — this is the
as-built report.

---

## The failure class, restated

A requirement is stated with a qualifier in a source-of-truth document. A
summary elsewhere restates it and silently drops the qualifier — a whole
column, or a word inside a cell. Engineers design against the summary; the
design looks correct and passes review because the qualifier that would
have constrained it was never visible to them.

Three historical instances, all in `docs/STRATEGY.md`'s gate summary table
against `docs/FUNCTIONAL_TEST_CRITERIA.md`:

1. **OCP-01**: source says "50A **Peak**"; summary said "45-55A" only.
   Real cost: a from-scratch peak-vs-RMS "ambiguity" investigation, publicly
   corrected.
2. **OVP-01**: source has a `10-20 V` **Hysteresis** column; summary dropped
   the column entirely. Real cost: OVP-01 was "fixed" with a 732 Ω reference
   and no hysteresis resistor at all, then had to be redone with a 287 kΩ
   feedback resistor.
3. **UVL-02**: source has separate `Trip Threshold (Falling)` /
   `Recovery (Rising)` columns; summary collapsed both to an undirected
   `<2.9V`. Real cost: a reviewer's verdict on a marginal part reversed once
   direction was restored.

A fourth, related-but-distinct instance, found live in this repo's current
tree while building this gate (see "What it found on today's tree" below):
`docs/STRATEGY.md`'s own "Full protection-gate audit" table marks OVP-01
**"FIXED"** at 399.88 V, in a row that a later section of the *same
document* ("Recovered gate qualifiers invalidate three of today's fixes")
shows lacks the required hysteresis network entirely. The "FIXED" row was
never corrected. This is a stale verdict, not a dropped qualifier — the gate
handles it with a second, narrower mechanism (below).

---

## A vs. B: verify, don't generate

**Decision: Option B (verify).** A checker parses both documents and
asserts field-for-field correspondence; neither document is generated.

**Why not generate (Option A):**

- `docs/STRATEGY.md` is a living narrative, not a data table with prose
  wrapped around it. Between this spike starting and finishing, it
  accumulated multiple new dated sections (bus capacitor ripple failure,
  BOM audit, ZVS margin, OCP-01 RMS analysis) from other agents working
  concurrently — the coordinator explicitly warned "STRATEGY.md is being
  appended to frequently today" and asked for a minimal diff to it. A
  generator would own the gate-table block's exact prose and require a
  human-editable "commit the generated output, CI checks it matches"
  workflow on a file that already changes every few minutes for unrelated
  reasons. That is friction the repo does not have today and this spike
  should not introduce.
- The repo's existing CI gates for exactly this shape of problem —
  `scripts/import_linter_gate.py` (module boundaries), `scripts/check_vacuous_gates.py`
  (unguarded `all()`), `scripts/check_physics_provenance.py` (physics
  constant citations) — are all verifiers, not generators. There is no
  precedent in this repo for "regenerate a hand-maintained markdown
  section and diff it," and introducing one for this spike alone would be
  a new pattern, not a reuse of an established one.
- The actual defect shape is **lossy restatement of specific fields**, not
  **structural divergence** (wrong gate count, wrong row order, wrong
  section). A verifier that locates each gate's row in both documents and
  checks required fields survived targets that shape directly. Generation
  would solve a superset of the problem (any rewording at all) at the cost
  of prose freedom the document currently uses (bold emphasis choices,
  inline citations, `→` vs `-` for ranges, `QP`/`avg` abbreviations in the
  EMC rows) — freedom that, per the instructions, is explicitly something
  Option B was scoped to preserve.

**Hybrid considered and rejected:** generating only the "requirement"
column while leaving surrounding prose free would still require agreeing
on a generation format for that column, and STRATEGY.md's actual gate rows
already mix qualifier and value in a single free-text cell ("Primary OCP
45-55A **peak**, <1µs") rather than a separate qualifier column — there is
no clean column boundary to generate against without restructuring the
table, which the "keep your diff to STRATEGY.md minimal" constraint rules
out for this pass.

**Where a hybrid mechanism *was* used:** the source-document mapping
itself (`scripts/derived_doc_gates.yaml`'s `gates:` section) is
**self-validating** rather than either fully generated or fully static.
Every `required_fields[].any_of` alternative for a gate must be found in
the current source row at run time; if none is, the run fails closed
(`tool_error`) rather than silently checking against a stale assumption.
This is the concrete answer to Option B's stated maintenance cost
("keeping the mapping current") — it is enforced by the tool on every run,
not hoped for.

---

## Falsifier (stated before reconstruction)

**If reconstructing any of the four historical defects against the
checker does not produce a violation that names the specific missing
field, the design is inadequate for the failure class it targets** — a
row-level or gate-ID-level check would pass all four inputs unchanged,
which is exactly the failure mode the brief says has already happened
(ten dead CI gates in this project died on "nothing parsed, therefore
nothing wrong").

**Result: it did not fire.** All four reconstructions (below) produced a
violation naming the exact missing field, and a "faithful restatement"
control with nothing dropped passed clean on the same fixture. See
`scripts/tests/test_check_derived_doc_drift.py::TestHistoricalDefectReconstruction`,
24 tests total, run below.

```
uv run pytest scripts/tests/test_check_derived_doc_drift.py -v --tb=short
```

Measured (foreground, exit code checked without a pipeline):

```
$ uv run pytest scripts/tests/test_check_derived_doc_drift.py -v --tb=short > /tmp/pytest_run2.txt 2>&1; echo "exit=$?"
exit=0
============================== 24 passed in 0.16s ==============================
```

### Case 1 — OCP-01's dropped "Peak"

Fixture derived row: `OCP-01 | Primary OCP 45-55A, <1us | SS2.1` (qualifier
removed from `50A Peak`/`45-55A peak`).

```
DRIFT <fixture> :: gate OCP-01 :: field 'basis' -- none of ['peak'] found (source: 'Primary OCP')
```

Named field: `basis`. Not flagged: `OVP-01`, `UVL-02` in the same row set —
proving this is field-level, not document-level (`test_case_1_ocp01_peak_qualifier_dropped`).

### Case 2 — OVP-01's dropped hysteresis column

Fixture derived row: `OVP-01 | DC Bus OVP 390-410V | SS2.2` (the entire
`10-20 V` hysteresis fact is gone, not reworded).

```
DRIFT <fixture> :: gate OVP-01 :: field 'hysteresis_label' -- none of ['hysteresis'] found (source: 'DC Bus OVP')
DRIFT <fixture> :: gate OVP-01 :: field 'hysteresis_value' -- none of ['10-20'] found (source: 'DC Bus OVP')
```

Two named fields — the concept word (from the source column header, since
the header text carries "Hysteresis" even though the data cell is a bare
number) and the value both fire independently
(`test_case_2_ovp01_hysteresis_column_dropped`).

### Case 3 — UVL-02's collapsed rising/falling direction

Fixture derived row: `UVL-02 | Logic UVLO <2.9V | SS2.4` (direction words
and the entire Recovery/Rising column gone).

```
DRIFT <fixture> :: gate UVL-02 :: field 'falling_label' -- none of ['falling'] found
DRIFT <fixture> :: gate UVL-02 :: field 'rising_label' -- none of ['rising'] found
DRIFT <fixture> :: gate UVL-02 :: field 'rising_value' -- none of ['3.0'] found
```

Three named fields (`test_case_3_uvl02_direction_altered_and_dropped`).

### Case 4 — STRATEGY.md's own stale "FIXED" verdict

This is not a dropped qualifier in a restatement; it is a **verdict a
later, documented finding already contradicts, with no acknowledgement in
the same row.** The `gates:` mechanism above checks that a claim's
qualifiers survive a restatement; it has no notion of "true." This needed
a second, narrower mechanism: `consistency_checks:` in the config asserts
that if a row's `stale_tokens` are all present (e.g. `"FIXED"` next to the
specific stale value), at least one `required_mitigating_tokens` phrase
(e.g. `"hysteresis absent"`) must also be present in that row, or it is
flagged.

Fixture: a second table (mimicking STRATEGY.md's "Full protection-gate
audit" table) with row `OVP-01 | 390-410 V | 399.88 V | FIXED` and no
hysteresis acknowledgement anywhere in the row.

```
DRIFT <fixture> :: OVP-01 :: ovp01-stale-verdict -- OVP-01 marked FIXED without acknowledging missing hysteresis
```

Named: the gate (`OVP-01`), the check id, and the message states exactly
what is missing (`test_case_4_stale_fixed_verdict_not_reconciled`). A
control test with the same stale tokens plus a mitigating phrase in the
row (`test_case_4_control_mitigated_verdict_passes`) passes clean —
proving the check does not just fire on the stale value alone, and stops
firing once the document is actually corrected.

---

## Anti-vacuity proofs

Per the brief: empty input, missing source document, zero rows parsed,
and an unrecognized table format must all fail closed, never exit 0.
`scripts/tests/test_check_derived_doc_drift.py::TestAntiVacuity`, 12 tests,
all pass (part of the 24 above). Each asserts `state == "tool_error"`
(exit 5), not `"clean"`:

| Degenerate input | Result |
|---|---|
| Config file missing | `tool_error` |
| Config file empty | `tool_error` |
| Config has zero `gates` | `tool_error` ("zero gates configured") |
| Config has zero `derived_documents` | `tool_error` |
| Source document missing | `tool_error` |
| Source document empty (0 bytes) | `tool_error` ("document is empty") |
| Source document has zero pipe-tables (prose only — unrecognized format) | `tool_error` ("zero pipe-tables parsed") |
| Derived document missing | `tool_error` |
| Derived document empty | `tool_error` |
| A gate's row deleted entirely from a derived doc (0 matches, not a missing field) | `tool_error` (names the gate and doc) |
| Source-row locator ambiguous (matches 2 rows) | `tool_error` ("matched 2 rows") |
| A `required_fields.any_of` no longer found anywhere in the *source* row (config drifted from source) | `tool_error` ("stale relative to the source document") |

There is also a structural backstop in `run()` independent of the tests:
if every check above somehow passed through without tripping and the run
still inspected **zero fields**, the run is forced to `tool_error` with
message `"0 fields were checked -- vacuous run, not a clean pass"` rather
than falling through to `"clean"`. This directly answers "0 violations
over 0 fields is a failure": the code makes that state unreachable as a
`"clean"` result.

Measured, foreground, exit code checked without a pipeline:

```
$ uv run pytest scripts/tests/test_check_derived_doc_drift.py -v --tb=short > /tmp/pytest_run2.txt 2>&1; echo "exit=$?"
exit=0
```

(exit 0 here is *pytest's* exit code for "all 24 tests, including the
anti-vacuity ones, passed" — each individual anti-vacuity test itself
asserts the gate's *own* result was `tool_error`, not that the gate
exited 0.)

---

## What it found on today's tree

Run against the real repository documents (not fixtures), foreground,
exit code checked without a pipeline:

```
$ uv run python3 scripts/check_derived_doc_drift.py > /tmp/drift_run2.txt 2>&1; echo "exit=$?"
exit=0
```

Exit 0 here is the **soft-launch** result (see "Wiring and soft launch"
below) — the run inspected real content and found real, reportable drift;
it is not a vacuous pass. Full counts, printed by the gate itself:

- **3 documents inspected**: `docs/FUNCTIONAL_TEST_CRITERIA.md` (source),
  `docs/STRATEGY.md`, `docs/hardware/PROTECTION_CHAIN_REVIEW.md`
- **35 pipe-tables parsed**
- **52 gate rows matched**: 22 source rows (self-validation) + 22 rows in
  `docs/STRATEGY.md`'s gate table + 7 rows in
  `docs/hardware/PROTECTION_CHAIN_REVIEW.md` (its 7-gate subset) + 1 row
  matched by the `consistency_checks` stale-verdict rule
- **132 fields checked**
- **17 drift violations found, 0 tool errors**

**`docs/STRATEGY.md`'s main gate table (the one the three original
2026-07-26 incidents were about) is currently clean** — it restates
Peak, hysteresis, and falling/rising direction correctly for every gate.
That is a real, positive finding, reported honestly rather than assumed:
the fixes made earlier on 2026-07-26 to restore those qualifiers are
still present in the table today. This was **not** edited to make the
gate pass — it was already correct when this checker was written; see
`git log --oneline -- docs/STRATEGY.md` around commit `8fa4a619`
("restore lost gate qualifiers").

**`docs/hardware/PROTECTION_CHAIN_REVIEW.md` has the same defect class,
uncorrected, today** — 15 of the 17 violations:

```
OCP-01: field 'basis' -- "peak" missing (source: "Primary OCP")
OCP-01: field 'response_time' -- "<1µs" missing
OCP-02: field 'basis' -- "peak" missing (source: "Secondary OCP")
OCP-02: field 'response_time' -- "<5µs" missing
OVP-01: field 'hysteresis_label' -- "hysteresis" missing (source: "DC Bus OVP")
OVP-01: field 'hysteresis_value' -- "10-20" missing
THM-01: field 'recovery_label' -- "recovery"/"release" missing (source: "Heatsink NTC")
THM-01: field 'recovery_value' -- "70°C" missing
THM-02: field 'recovery_label' -- "recovery"/"release" missing (source: "Coil NTC")
THM-02: field 'recovery_value' -- "100°C" missing
UVL-01: field 'falling_label' -- "falling" missing (source: "Gate Drive (15V)")
UVL-01: field 'rising_label' -- "rising" missing
UVL-01: field 'rising_value' -- ">13.0V" missing
UVL-02: field 'falling_label' -- "falling" missing (source: "Logic (3.3V)")
UVL-02: field 'rising_label' -- "rising" missing
UVL-02: field 'rising_value' -- ">3.0V" missing
```

This document's gate summary table (header `Gate | Requirement | As
committed | Disposition`) restates every protection gate's numeric
threshold with the same qualifiers stripped that caused the original
incident — "45-55 A" with no "Peak", `390-410 V` with no hysteresis
column, direction-less UVLO thresholds. It is dated 2026-07-25 and has not
been corrected the way `docs/STRATEGY.md`'s table was on 2026-07-26. This
is reported here rather than fixed quietly, per the instruction to report
honestly rather than make the gate green by editing the document under
test.

**`docs/STRATEGY.md`'s own "Full protection-gate audit" table has a stale
verdict** — 1 of the 17 violations, from `consistency_checks`:

```
STRATEGY.md :: OVP-01 :: ovp01-fixed-verdict-vs-missing-hysteresis --
OVP-01 is marked FIXED at 399.88V with no acknowledgement that the
comparator has no hysteresis network (FUNCTIONAL_TEST_CRITERIA.md SS2.2
requires 10-20V hysteresis; see STRATEGY.md "Recovered gate qualifiers
invalidate three of today's fixes"). This verdict is stale.
```

Concretely: `docs/STRATEGY.md` line ~393 (`| OVP-01 | 390–410 V |
**399.88 V** | **FIXED** 2026-07-26 |`) is contradicted by line ~453 of
the *same document* (`| OVP-01 | 390–410 V trip, hysteresis 10–20 V | no
hysteresis — comparator has no feedback resistor | hysteresis absent
entirely |`), written later in the same file, same day. The earlier
"FIXED" verdict row was never annotated with the correction. This is a
fourth, distinct instance of the same root problem (a claim not carrying
its full context downstream) discovered incidentally while building this
gate, not one of the three the brief named going in.

**A note on scope, not a finding this gate makes:** while investigating
case 4, `docs/hardware/PROTECTION_CHAIN_REVIEW.md` and
`docs/hardware/OCP02_DESIGN.md` were found to assert the OVP divider
senses a "170 V half-bus" while `docs/STRATEGY.md` and
`docs/evidence/2026-07-26-ovp01-trip-point-sim.json` assert the divider
senses the full 340 V bus and is resolved. This is a genuine
cross-document electrical disagreement, but it is a *hardware*
determination (what node a wire connects to), not a *restated-qualifier*
question this gate's mechanism is built to check, and resolving it would
mean editing or asserting facts about `elec/src/*.ato`, which this task
is explicitly scoped out of. Recorded here as a live finding for the
electrical-side track, not addressed by this gate.

**The 200 W ±25% power tier remains a gap.**
`docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2 specifies a 200 W tolerance tier;
`docs/STRATEGY.md`'s gate table has no corresponding gate ID for it at
all (only PWR-01 @1000W and PWR-02 @1800W exist). STRATEGY.md's own
"Recovered gate qualifiers" section already names this as "an omitted
requirement, not a lost qualifier." This gate's `gates:` mechanism cannot
catch it by construction — it checks *fields within a located row*, and
there is no row to locate. See "Explicitly out of scope" below for why a
general row-existence check was not added in this pass.

---

## The inverse defect: a requirement with no counterpart upstream

A second input surfaced after this gate was scoped: `BusDischarge` must
bring the bus to <34 V within <60 s (`elec/src/modules.ato:422-424,566,692-703`)
— safety-relevant, IEC 60335-1 territory (bus discharge for servicing) —
and that requirement **exists only as source comments in
`elec/src/modules.ato`; it has zero matches anywhere in
`docs/FUNCTIONAL_TEST_CRITERIA.md`.** Confirmed directly:

```
$ grep -n "60s\|<60\|34V\|<34\|BusDischarge" elec/src/modules.ato
422:    # Passive bleeders alone need ~9 minutes to safe level (<34V); the
423:    # BusDischarge module (instantiated in Top) adds fail-safe active
424:    # discharge to <34V in <60s on any loss of power. The passive 22k
566:    # <34V). Active discharge to <60s is provided by BusDischarge (see Top);
692:module BusDischarge:
702:    Sizing (per half-bus): tau = 9.4k x 3600uF = 33.8s; 170V -> <34V in
703:    1.61 tau ~= 54s (<60s target). Peak power at contact closure:

$ grep -ni "discharge\|34.?v\|60.?s" docs/FUNCTIONAL_TEST_CRITERIA.md
(no output)
```

This is the mirror image of the class this gate targets: instead of a
requirement losing a qualifier on the way *down* from source to summary,
it never made it *up* into the requirements document at all. It is a real
gap and it is reported here, but it is **not implemented as a general
mechanism, and that is a deliberate scope decision, not an oversight:**

**Why a general heuristic was rejected.** The brief itself offers the
test: "a heuristic that flags numeric targets in `.ato` comments (`<60s
target`, `>= 5A`, `85C`) having no match in the criteria doc." Tried
against this repo's actual source: `elec/src/modules.ato` and
`elec/src/main.ato` contain hundreds of numeric comments — resistor
values, reference voltages, simulated trip points, BOM part ratings,
divider ratios — that are implementation *derivations*, not top-level
*requirements*. A regex over "number + unit in a comment" cannot
distinguish "the tank needs 80µH" (a design parameter) from "<34V in
<60s" (a safety acceptance criterion) without semantic understanding of
which comments describe a pass/fail boundary for the finished product
versus an intermediate calculation. Built naively, this would either:
(a) fire on nearly every numeric comment in the file (vacuous-by-volume,
the opposite defect the brief warns about — "a check that fires on
correct code is a defect," `scripts/check_vacuous_gates.py`'s own
stated design principle), or (b) require a curated allowlist of comment
patterns that means someone already had to read and classify every
comment, at which point the "automatic" part is not actually saving the
manual step it claims to.

**What would work, not built in this pass:** a small, explicit, opt-in
list of safety-relevant module docstrings (mirroring
`docs/TRACEABILITY.md`'s sentinel-file, opt-in-per-directory model rather
than a repo-wide scan) that must each have a citation to a
`FUNCTIONAL_TEST_CRITERIA.md` section or an explicit
`# not-a-criteria-requirement` marker. This is a reasonable follow-up but
is a different, larger piece of work than this spike's scope (a
field-level qualifier-drift checker for an existing pair of documents),
and is called out here as **UNVERIFIED / explicitly out of scope** rather
than attempted partially.

---

## Other derived-table pairs surveyed

`docs/` has **603** markdown files (the brief's estimate of ~140 undercounts
by roughly 4x). A full manual audit of all of them for restated-requirement
tables was not attempted (out of budget for this task); the following were
found and triaged by grepping for the actual requirement values (`45-55`,
`390-410`, `2.9 V`, `85°C`/`70°C` etc.) across `docs/`:

- **`docs/hardware/PROTECTION_CHAIN_REVIEW.md`** — same shape as
  `docs/STRATEGY.md`'s gate table, restating the seven protection gates.
  **Added to this gate's config**, live findings above.
- **`docs/hardware/BOM.md`** — mentions gate IDs and their thresholds
  throughout (e.g. "OCP-01 resolved 2026-07-25... Trip is 50.121 A") but
  is a component-by-component narrative BOM, not a per-gate summary table
  with one row per requirement — there is no single row to locate a
  gate's full qualifier set in. **Not added**: the row-locator mechanism
  this gate uses assumes one row = one gate's full restatement, which
  does not hold here. A future pass could grep BOM.md's prose for the
  same qualifier tokens without a table structure, but that is a
  different parsing problem than this gate solves. UNVERIFIED whether
  BOM.md currently carries a qualifier-drop defect.
- **`docs/hardware/UVLO_TRACEABILITY.md`** vs
  **`docs/hardware/SAFETY_INTERLOCK_DESIGN.md`** — a related but distinct
  precision failure already found and documented by a prior analysis
  (UVLO_TRACEABILITY.md §"This repo's own prior citation is wrong"):
  SAFETY_INTERLOCK_DESIGN.md cites UVLO thresholds transcribed from the
  wrong device grade. This is a **datasheet-citation error**, not a
  source-vs-summary qualifier drop (there is no FUNCTIONAL_TEST_CRITERIA.md
  row this restates) — different failure class, different mechanism
  needed. **Not added.** UNVERIFIED whether it has since been corrected.
- **`docs/TRACEABILITY.md` / `docs/traceability-registry.yaml`** — a
  structurally similar-looking source/derived pair (plan requirements ↔
  code annotations), but it is **already machine-checked** by the R2/R3
  gates described in that document (annotation validity and requirement
  coverage). Not a gap; not touched.
- **`docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2's 200 W tier** — see "What it
  found on today's tree" above; an omitted-requirement gap this gate's
  mechanism cannot catch by construction (no row exists to check fields
  of). UNVERIFIED whether other omitted-tier gaps exist elsewhere in the
  22-gate set; not systematically checked beyond this one, which
  STRATEGY.md's own prose already flags.

**No other candidate pairs were found** restating
`docs/FUNCTIONAL_TEST_CRITERIA.md`'s specific numeric requirements in
table form, based on grepping for the actual threshold values across
`docs/`. This is a search-based survey, not an exhaustive read of all 603
files — genuinely new pairs could exist using different phrasing for the
same values (e.g. a table that says "50 amps" instead of "50A" or "50-55A"
would not have been found by this grep). **UNVERIFIED**: completeness of
the survey beyond the value-grep method described.

---

## Wiring and soft launch

Wired into `.github/workflows/python-tests.yml`'s existing `Core Tests`
job, alongside the other fail-closed gates (`Anti-vacuous-truth gate`,
`Import boundary enforcement`):

```yaml
- name: Derived-document drift gate tests
  run: uv run pytest scripts/tests/test_check_derived_doc_drift.py -v --tb=short

- name: Derived-document drift gate (docs/STRATEGY.md vs FUNCTIONAL_TEST_CRITERIA.md)
  run: uv run python scripts/check_derived_doc_drift.py
```

Path filters added to both `push` and `pull_request` triggers for
`scripts/check_derived_doc_drift.py`, `scripts/derived_doc_gates.yaml`,
`scripts/tests/test_check_derived_doc_drift.py`,
`docs/FUNCTIONAL_TEST_CRITERIA.md`, `docs/STRATEGY.md`, and
`docs/hardware/PROTECTION_CHAIN_REVIEW.md` — previously none of the three
markdown documents were covered by any path filter in this workflow, so
editing them would not even have triggered a CI run that could have
caught drift.

**Exit-code contract, mirroring `scripts/import_linter_gate.py`:**

- `0` — clean (no drift, no tool errors), **or** drift found but still
  inside the soft-launch window (see below).
- `3` — drift found (missing field or unmitigated stale verdict), after
  the soft-launch window.
- `5` — tool error (cannot run: missing/empty/unparseable
  config or document, zero tables, ambiguous or missing row match, or a
  self-validation failure meaning the config no longer reflects the
  source). **Never soft-launched** — a gate that cannot run must never
  report success, regardless of date.

**Soft launch (`CUTOVER_DATE = 2026-08-02` in the script):** this gate
currently finds real, live drift (`docs/hardware/PROTECTION_CHAIN_REVIEW.md`,
17 violations; `docs/STRATEGY.md`'s stale OVP-01 verdict, 1 violation).
Per the instruction not to "fix the table quietly to make your gate
green," those documents were **not edited** to clear the findings.
Following `scripts/import_linter_gate.py`'s own precedent (a documented
WARNING-only window before new violations become merge-blocking), drift
prints in full but exits 0 for about one week after this lands, giving
whoever owns `PROTECTION_CHAIN_REVIEW.md` and the OVP-01 verdict time to
fix the documents on their own schedule rather than this spike blocking
unrelated PRs on day one. Tool errors are never subject to this window.

---

## Summary for the record

- **Chosen approach:** verify (Option B), not generate. Reasoning above.
- **Falsifier:** reconstructing the four historical defects must produce a
  violation naming the specific missing field, or the design is
  inadequate. **It did not fire** — all four fired correctly, plus a
  faithful-restatement control and a case-4 "already corrected" control
  both passed clean, proving no false positives on the same fixtures.
- **Anti-vacuity:** twelve degenerate-input tests, all fail closed
  (`tool_error`, exit 5), plus a structural backstop in `run()` making a
  0-fields "clean" result unreachable in code, not just untested.
- **Today's tree:** 3 documents / 35 tables / 52 gate rows / 132 fields
  inspected; 17 real violations, 0 tool errors. STRATEGY.md's main gate
  table is clean; PROTECTION_CHAIN_REVIEW.md has the historical defect
  pattern uncorrected; STRATEGY.md's own audit table carries a stale
  "FIXED" verdict. None of this was fixed to make the gate green.
- **Other derived-table pairs:** one added to scope
  (PROTECTION_CHAIN_REVIEW.md); three considered and explicitly not added
  with reasons (BOM.md, UVLO_TRACEABILITY.md/SAFETY_INTERLOCK_DESIGN.md,
  TRACEABILITY.md — already machine-checked by a different gate).
- **Explicitly scoped out, not attempted partially:** a general heuristic
  for "requirements that exist only as source comments and never reached
  the criteria document" (the BusDischarge <34V/<60s case). One concrete
  instance confirmed and reported by hand; a general mechanism was judged
  too failure-prone (vacuous-by-volume or requires the same manual
  classification it claims to automate) to build reliably in this pass.
- **UNVERIFIED:**
  - Whether `docs/hardware/BOM.md` currently restates any gate qualifier
    incorrectly in its prose (no row-based mechanism was built for it).
  - Whether `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`'s UVLO citation
    error (documented separately in UVLO_TRACEABILITY.md) has since been
    corrected.
  - Completeness of the docs/ survey beyond grepping for the literal
    requirement values already known from `FUNCTIONAL_TEST_CRITERIA.md`
    — a table restating the same requirement in different units or
    phrasing would not have been found.
  - Whether other §1/§3/§4 gates besides the known 200 W tier have
    similar omitted-requirement gaps; only the one STRATEGY.md's own
    prose already named was checked.
  - The electrical question of whether OVP-01's divider senses the full
    or half bus (PROTECTION_CHAIN_REVIEW.md/OCP02_DESIGN.md say half-bus;
    STRATEGY.md and the 2026-07-26 evidence JSON say full-bus/resolved) —
    out of scope for this gate, flagged for the electrical-side track.
