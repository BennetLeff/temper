<!-- provenance: commit=fbc5ce517fec9bbefcbaf632efa6b0ee4062d047 dirty=UNKNOWN -->
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged at task start and at every commit below (read-only investigation,
no board writes attempted). No pyo3 rebuild performed; no `.venv` touched. -->

# Spike: port the placer's constraint/clearance layer to Rust — staged deletion plan

**Reframed mid-task by the owner.** The question is not "is this worth it" —
Rust-over-Python is settled project direction (`docs/HANDOFF-2026-08-17.md` §1,
`docs/migration-pipeline.md`, and six landed PRs today alone: #1239/#1252/#1253/
`spike/pyclass-removal`/#1302/#1314). This document plans the shortest safe path
to deleting the Python in the constraint/clearance layer, staged cheapest-and-
safest first, per PR #1302's own ranking method.

Builds on `docs/evidence/2026-08-17-placer-creepage-constraint-spike.md` (PR
#1317, committed on a sibling branch, not yet on `main` at task start — read via
`git show 659f62759:...`), which mapped this layer's liveness: `domain_clearance.py`
is correct but unwired from the default solve path; `netclass_constraints.py` is
live by default and misclassifies K1's HV relay contacts as "signal" (same
bucket as J1's SELV RTD lines), generating zero protection for exactly that
pair; `IECCreepageGate` is dead code with a stale hardcoded 6.0mm (vs the
current 12.6mm PD3 figure) that also leaks into `DeltaMapper`'s feedback path.
This document does not re-derive that liveness map; it answers the Rust-port
question specifically.

---

## 0. The headline finding: two of the four target files are already mid-port

**This is the single most load-bearing fact in this document and it changes
the shape of the plan.** Before assuming "port to Rust" means writing new
Rust, the actual state of each named target was checked by reading the file,
not its name or its own docstring's claims:

| File | LOC | Actual state, verified by reading the code |
|---|---:|---|
| `placer/cp_sat/domain_clearance.py` | 632 | **Already substantially ported.** Every compute-heavy function (`generate_domain_clearance_constraints`, `generate_unclassified_hv_keepaway_constraints`, `find_intra_footprint_domain_conflicts`, `audit_domain_clearance`) is a thin wrapper calling `temper_orchestration`'s Rust FFI (`_to.domain_clearance_constraints_py`, `_to.keepaway_constraints_py`, `_to.intra_footprint_conflicts_py`, `_to.audit_domain_clearance_py` — `domain_clearance.py:343,474,554,622`). The matrix walk, pair canonicalization, and margin/reason dedup run in `packages/temper-orchestration/src/clearance.rs` (1,890 LOC, "Phase E batch E3" per its own header comment, `clearance.rs:1-30`). Remaining Python: dataclass reconstruction from returned tuples, logging, and marshalling the `IEC60335_REQUIREMENTS` dict into flat rows (`_matrix_rows()`, `domain_clearance.py:243-262`). |
| `placer/cp_sat/netclass_constraints.py` | 155 | **Partially ported at the leaf level, not at the orchestration level.** `classify_net_type()` (the keyword classifier) is a 1-line Rust FFI call (`core/net_classification.py:151`, `return _rs.classify_net_type(name)`) into `temper_drc_rs`. `DesignRules.get_rules_for_net()` (`design_rules.py:58`, `DesignRules = _tdb.DesignRules`) is the Rust `temper_design_bundle` pyclass, not Python. **The O(n²) pairing loop, severity-rank resolution, and `SeparatedConstraint` construction are genuine, unported Python** (`netclass_constraints.py:63-155`). |
| `placer/cp_sat/pair_clearance.py`, `pair_creepage.py` (router-side consumers of the generated YAML) | 261 + 127 | Genuine, unported Python — YAML loading (`yaml.safe_load`), `@lru_cache` table construction, class-pair lookup. No Rust delegation found (`import yaml`, no `_rs`/`_tdb`/`_to` import in either file). |
| `placer/cp_sat/gates.py::IECCreepageGate` | 60 (743-803) | Pure Python, dead in production (§4 of the sibling spike; not re-derived here), pinned by exactly one oracle (`_gates_py_oracle.py`, `scripts/oracle_hashes.json:113`). |

**Consequence for the plan:** "port `domain_clearance.py` to Rust" is
**~85% already done**. What remains for that file is small (matrix
marshalling + a handful of dataclass rebuilds), and the actual outstanding
work in that file is not translation — it's **wiring** (getting the
already-correct, already-Rust-backed constraint generator called from
`solve_placement`'s default path, which the sibling spike found it currently
isn't). `netclass_constraints.py` and `pair_clearance.py`/`pair_creepage.py`
are earlier-stage candidates: the string/lookup primitives are Rust, the
orchestration is not.

---

## 1. Duplicate-vs-unique inventory

### 1a. A live, duplicated fact: the IEC60335_REQUIREMENTS matrix has two homes today

This is not hypothetical drift-risk — it is a **measured, present-tense**
instance of the handoff's mechanism 1 ("one fact, many homes"), inside the
very machinery this spike was asked to assess:

- **Home 1 (Python, the stated SSOT):** `IEC60335_REQUIREMENTS`, a
  tuple-keyed dict, `requirements/validators/clearance.py:262-293`. 6 rows.
  Consumed by `domain_clearance.py::_matrix_rows()` for CP-SAT constraint
  generation, and by `clearance.py`'s own validator logic.
- **Home 2 (Rust, a from-spec reimplementation):** `MATRIX_ROWS`, a `const
  [(&str,&str,&str,f64,f64,f64); 6]`, `packages/temper-drc-rs/src/
  req_safe_01.rs:1121-1129`, with a **13-line provenance comment citing the
  2026-08-15 safety-assertion audit directly** (Table 17 row iv, clause
  29.2.3, the debunked Table-16-at-400V citation, the PD2/PD3 fallback) —
  i.e. written from the standard, not transcribed from the Python. Consumed
  by `req_safe_01_verify_iec60335` (`req_safe_01.rs:1133`), which is what
  `clearance.py:512`'s `verify_iec60335_compliance()` — **the live CI-gate
  safety validator** — actually calls.

Both currently hold the same 6 values. They are kept in sync **by a pinning
test**, not by single-sourcing: `req_safe_01.rs:34-37`'s own comment names
`test_requirement_matrix_values_pinned` as the mechanism, and
`requirements/validators/clearance.py:260` cross-references it. This is a
real defense (an edit to one side without the other fails CI), but it is
still two representations of the same safety table that a human must keep
in sync by hand, and it is exactly the shape — "a running check pinned to a
wrong number manufactures confidence" (handoff §11) — that has bitten this
project repeatedly today (14.0mm creepage, 6.0mm stale gate threshold, two
HV-keyword lists in the very same domain). **Per the migration-pipeline
doc's REIMPLEMENT route** (an independent Rust oracle written from spec is
the *correct* discipline for a safety kernel's continuous adversarial
differential — this is not a bug, it is stage 8's REIMPLEMENT route already
applied), but the pipeline's own stage 8 says REIMPLEMENT kernels "keep a
live differential indefinitely by design" — and there is no evidence a
Python↔Rust differential *runs regularly*, only that the values were pinned
once. This is flagged, not fixed (task hard rule: never change a clearance/
creepage value) — but the single-sourcing fix (encode the matrix once, in
Rust, as `SafetyValue`-typed data per `packages/temper-design-bundle/src/
safety_value.rs`'s existing pattern for Table 16/17/18, and generate the
Python view from it rather than hand-duplicating) is exactly the kind of
consolidation a "port to Rust and delete the Python copy" move should do —
see §3 stage 1.

### 1b. `classify_net_type`'s keyword lists — Rust already, wrong regardless of language

The sibling spike's K1/J1 finding (`netclass_constraints.py`'s classifier
puts K1's HV relay contacts and J1's SELV RTD lines in the same "signal"
bucket) is **not a Python-vs-Rust problem**. `classify_net_type` is already
a 1-line delegation to `temper_drc_rs::classify_net_type` (Rust). The defect
is in the **keyword list and the 4-bucket design** (ground/power/hv/signal
by net-name substring), which exists identically whether the caller is
Python or Rust. **Porting `netclass_constraints.py`'s orchestration to Rust
would not fix this defect — it would preserve it, faithfully, in Rust.** The
actual fix (documented, not attempted, per the sibling spike §7 item 3) is
routing the classifier through `elec/domain_manifest.yaml`'s hand-reviewed
domain authority instead of net-name pattern matching — a data-source
change, orthogonal to which language holds the loop. This distinction
matters for sequencing: **do not let a Rust port of this file's orchestration
be mistaken for fixing the K1/J1 defect.** They are two different pieces of
work; the port is real value (deletes a home), but it is not a safety fix.

### 1c. Router-side generated tables — a third, independently-maintained classifier

Per the sibling spike §3 (not re-derived here, cited for completeness):
`pair_clearance.generated.yaml`/`pair_creepage.generated.yaml` carry correct
current figures (12.6mm PD3 for `Default|HighVoltage`) but are keyed on 14
**KiCad NetClass** names resolved from `pcb/temper.kicad_dru`, a genuinely
different classification scheme from both `domain_clearance.py`'s 5
**VoltageDomain** buckets (`elec/domain_manifest.yaml`-backed) and
`netclass_constraints.py`'s 4-bucket keyword classifier. All three currently
agree on the PD3 number by coincidence, not construction (86 distinct
component-ref pairs violate under the 14-class scheme vs "14" under the
5-domain scheme, on the identical board, at the identical instant — the
sibling spike's own measured number). **A Rust port that collapses these
three classifiers into one would be a genuine, large surface-area win — the
biggest one available in this domain.** A Rust port that ports each of the
three classifiers' orchestration separately, keeping three homes, is the
trap the task brief named explicitly: it adds a fourth (Rust) home to each
without removing any of the existing three.

### 1d. CP-SAT encoding stays genuinely Python — not a duplication, a real boundary

`handlers/separated.py::encode_separated` (124 LOC, read in full for this
spike) calls `model.model_ref.Add(...).OnlyEnforceIf(...)`,
`.AddBoolOr(...)`, `model.new_bool_var(...)` — direct calls into ortools'
Python `cp_model.CpModel` object. This is not delegatable logic sitting next
to a Rust equivalent; it *is* the ortools Python binding surface. There is
no duplicate here to consolidate — see §2 for the CP-SAT verdict.

---

## 2. The CP-SAT verdict — recommendation, not a survey

**Recommendation: port constraint *generation* to Rust; keep the CP-SAT
*solve* (model construction via `cp_model.CpModel`, `.Solve()`) in Python.**
This is not a new position — it is the **already-settled program verdict**
(`docs/evidence/2026-08-01-ortools-cpsat-spike.md`, re-confirmed
`2026-08-04-wave4-residual-verdicts.md`), and this spike's own file-reading
in §0/§1d independently reproduces why it is the right call for *this*
domain specifically, not just in general:

- **No mature pure-Rust CP-SAT engine covers this project's constraint
  vocabulary.** The 2026-08-01 spike's feature enumeration (§1.2 of that
  doc) found no pure-Rust engine (Pumpkin, aries-solver, huub) implements
  `no_overlap_2d` (needed for courtyard non-overlap) or documents 2D-element/
  reification support at the coverage this placer needs — verdict "KEEP",
  named blocker "no mature pure-Rust CP-SAT engine implements the full
  vocabulary at competitive search quality."
- **The two Rust *FFI bindings to the same ortools C++ engine*** (`cp_sat`
  crate 0.4.1, `cpsat-rs` 0.1.2) are "achievable in principle" (same engine
  ⇒ same deterministic output for a pinned version+seed) but rated too
  immature to pin as production (0 dependents / 198 downloads at spike
  time) — a real path, not a dead end, but not today's path.
- **The boundary this project has already drawn is exactly the right one**:
  `handlers/separated.py:50-53`'s own docstring records the R24 post-solve
  audit as "already Rust-backed via temper-geometry" — i.e. the KEEP
  contract already routes everything *around* the ortools call into Rust
  (constraint math, audit, geometry) and keeps only the literal
  `CpModel.Add(...)` calls in Python. `domain_clearance.py`'s Phase-E-batch-E3
  migration (§0) is a **second, independent instance of the exact same
  pattern already landed and working** — the matrix walk, pairing, and
  audit are Rust; only the final `SeparatedConstraint` dataclass
  construction and the CP-SAT encoding step stay Python.

**So "port constraint generation while leaving the solve in Python" is not
a hedge — it is what this codebase has already built twice (`domain_clearance.py`
via `temper-orchestration::clearance.rs`, and the general R24 audit via
`temper-geometry`), and it is what the dedicated CP-SAT spike separately
concluded from the solver-engine side.** `netclass_constraints.py`'s
orchestration (§0, §1b) should follow the identical shape:
pairing/severity-resolution/margin-lookup logic moves to Rust (mirroring
`clearance.rs`'s `domain_clearance_constraints_py` shape almost exactly —
same "walk components, classify, pair, dedup, emit tuples" structure), the
final `SeparatedConstraint` object construction and the `encode_separated`
CP-SAT call stay Python.

---

## 3. Staged deletion plan

Sequenced cheapest-and-safest first, per PR #1302's own ranking method
(shim/thin-wrapper collapse before real migration work; oracle-blocked items
named explicitly rather than assumed clear).

### Stage 0 — prerequisite, not a port: wire `domain_clearance.py` in

Per the sibling spike (§7 there): `domain_clearance.py`'s Rust-backed
constraint generator is correct and unwired. Wiring it into
`solve_placement`'s default path is **not this spike's job** (a different
sibling is on `domain_clearance.py`/`solve_placement()` per this task's own
coordination note) and is not a Rust-port question at all — it is a call-site
change with zero new Rust. Flagged here only because every stage below
compounds on top of whatever the wiring decision does to call volume
(a wired-in generator running on every full-board solve is a very different
performance/oracle-coverage target than one running only inside
`repair-unplaced`).

### Stage 1 — finish `domain_clearance.py`'s already-started port (cheapest, ~85% done)

**What ports:** `_matrix_rows()` (`domain_clearance.py:243-262`) — the
marshalling of `IEC60335_REQUIREMENTS` into the flat-tuple shape
`temper-orchestration` consumes. **What this also fixes, as a side effect,
not a separate task:** §1a's two-home matrix problem. Move
`IEC60335_REQUIREMENTS`'s 6 rows into `packages/temper-design-bundle/src/
safety_value.rs` as `SafetyValue`-typed constants (the module already exists
and already encodes Table 16/17/18 in exactly this shape —
`safety_value.rs`'s own header table). Generate **both** consumers
(`req_safe_01.rs`'s `MATRIX_ROWS` and the Python `_matrix_rows()` view) from
that single Rust source — `req_safe_01_requirement_matrix()` already exists
as a Python-callable accessor (`req_safe_01.rs:1235`, `get_requirement_matrix()`
— currently unused by `domain_clearance.py`, which reads the Python dict
directly instead). Wiring `domain_clearance.py` to call this accessor
instead of importing the Python dict collapses **two homes into one**, with
the Rust side already carrying superior provenance (the 13-line audit
citation at `req_safe_01.rs:1093-1120` vs the Python dict's bare literals).

**What deletes:** the Python `IEC60335_REQUIREMENTS` dict body
(`clearance.py:262-293`, 32 lines) — the `VoltageDomain`/`InsulationType`
enum definitions stay Python (they are used as dict keys and type
annotations across the module, and moving an Enum's *identity* into Rust is
a much larger, unrelated boundary change not needed for this consolidation).

**Oracle status:** `grep scripts/oracle_hashes.json` for `domain_clearance`
or `netclass_constraints`: **zero hits.** Neither file has a pinned
differential oracle today. `test_requirement_matrix_values_pinned`
(referenced by both the Python and Rust comments, not yet located in a
specific test file during this spike — needs confirming before executing,
flagged as **UNVERIFIED**) is the closest thing to a pin, and it pins
*values*, not *which file is the source of truth*. **This means the re-pin
ceremony (PR #1315's bar: independently reproduce the evidence + add a
positive control) does not apply here in its usual form** — there is no
existing oracle to re-pin. What stage 1 needs instead, per
`docs/migration-pipeline.md` stage 3 (TDD: pin the pre-migration Python as
oracle *first*, red, then green): **write the missing oracle before
deleting the dict** — freeze `IEC60335_REQUIREMENTS` as
`tests/requirements/clearance_oracle/_iec60335_requirements_py_oracle.py`
(mirroring the existing `_gates_py_oracle.py`/`clearance_oracle/` pattern
already in this tree), assert it equals `get_requirement_matrix()`'s Rust
output row-for-row, *then* delete the Python dict body and point
`_matrix_rows()`/`clearance.py` at the Rust accessor. This is new oracle
creation, not oracle re-pinning — a materially cheaper and lower-risk
operation.

**Cost:** ~30 LOC Rust (the `SafetyValue` conversion + wiring
`req_safe_01_requirement_matrix()` into `domain_clearance.py`'s import),
~32 LOC Python deleted, one new oracle file (~40 LOC, mechanical). **Risk:
low** — no behavior change (values identical, pinned test already asserts
this), the two call sites (`domain_clearance.py`, `clearance.py`'s own
validator) are both already exercised by `test_domain_clearance.py` (773
LOC) and `test_clearance_validator_rust_differential.py`.

### Stage 2 — port `netclass_constraints.py`'s orchestration (real migration, small)

**What ports:** the O(n²) pairing loop, severity-rank resolution
(`_resolve_component_net_class`, `netclass_constraints.py:28-60`), and
class-pair-override lookup (`netclass_constraints.py:129-142`) — ~110 LOC of
genuine, unported orchestration (§0). Target shape: a new
`temper-orchestration` function alongside `clearance.rs`'s
`domain_clearance_constraints_py` — same "classify every component, walk
all pairs, dedup, emit tuples" structure that file already implements for a
sibling problem, so this is pattern-reuse, not new design.

**What this does NOT fix:** the K1/J1 misclassification (§1b) — that is a
data-source defect (net-name keywords vs `elec/domain_manifest.yaml`), not
a language defect, and is out of scope for a Rust-port stage. **Recommend
explicitly deciding whether to fix the classifier data source *before* or
*as part of* this port** — porting the current (wrong) keyword-based logic
to Rust faithfully preserves the defect one layer deeper, which is exactly
the "relocates the surface area" failure mode the task brief warns against.
If the owner's `netclass_constraints.py`-editing sibling (per this task's
coordination note) is already changing the classification source, this
stage should follow that fix, not precede it, so the Rust port isn't itself
a second thing to re-verify against a moving target.

**Oracle status:** zero pinned oracles (confirmed by the same grep as
stage 1). `tests/pcl/test_netclass_constraints.py` (237 LOC) exists as
ordinary pytest coverage, not an oracle. Same consequence: write a fresh
oracle (freeze current *paired* behavior, not the classifier's wrong
verdicts specifically — the point is behavior parity during the port, the
classifier fix is a separate, subsequent change) before porting, per stage
3's TDD requirement.

**Cost:** ~150-200 LOC Rust (new function + FFI wrapper + tests, matching
`clearance.rs`'s existing scale for a comparable function), ~110 LOC Python
deleted (shim remains as a thin `_to.netclass_constraints_py(...)` wrapper,
matching `domain_clearance.py`'s own current shape post-stage-0). **Risk:
low-medium** — the pairing logic is simple (no CP-SAT-specific math, unlike
`handlers/separated.py`), but it is live-by-default code (unlike
`domain_clearance.py`, which is currently unwired), so a regression here
changes every solve's output today, not just a future one. Needs the full
differential (old Python output vs new Rust output, on the real board's
component/net list) run and green before landing, not just unit coverage.

### Stage 3 — collapse the three classifiers (largest win, largest risk, owner decision first)

Per §1c: this is the biggest available surface-area reduction in this
domain, but it is **not a Rust-port task at its core — it is a
classification-scheme unification decision** (which of the three bucket
systems — 4-keyword, 14-KiCad-NetClass, 5-VoltageDomain — becomes the one
source, and what happens to the two others' call sites). Recommend against
attempting this as a Rust translation exercise: translating three
classifiers faithfully into Rust would produce three Rust homes instead of
three Python ones — a literal instance of the task brief's named trap.
**This needs an owner decision on which classifier wins (§1c already shows
`elec/domain_manifest.yaml`'s hand-reviewed `VoltageDomain` is the one the
codebase's own ground rule endorses — "domain membership must never be
inferred from how a net is spelled", per the sibling spike's quote of
`elec/domain_manifest.yaml`'s own docstring) before any porting work is
scoped.** Once decided, the port itself is mechanical: repoint
`netclass_constraints.py` and `pair_clearance.py`/`pair_creepage.py` at the
winning classifier's already-Rust-backed accessor
(`req_safe_01_nets_domain_map` already exists, `req_safe_01.rs:1435`, and is
already what `domain_clearance.py` uses) rather than building new Rust for
this stage.

**Cost:** not sized — depends entirely on the classification decision's
scope (does it touch the router's obstacle-halo stamping, which is a live,
safety-relevant, currently-working code path per PR #1267?). Flagged as
"needs its own scoping pass," not estimated here to avoid the "optimistic
claim" pattern this repo has been burned by today.

### Stage 4 (parallel track, independent of 1-3) — `pair_clearance.py`/`pair_creepage.py`

**What ports:** YAML loading + `@lru_cache` table construction (§0, ~388
LOC combined). Genuinely unported, no `_rs`/`_tdb`/`_to` delegation found by
direct grep. Not blocked by the classifier-unification decision (stage 3)
if scoped narrowly as "load this YAML file into a lookup table in Rust
instead of Python" — the *keying scheme* (14 KiCad NetClasses) stays
whatever it is regardless of language. **Independent of stages 1-3**; can
run in parallel or be deferred without blocking them.

**Oracle status:** not checked in this spike (out of the four named target
files in the task's concrete-target list, but included in the task's
"clearance/creepage geometry those depend on" clause) — flagged as a gap,
not assumed clear.

**Cost:** not sized this pass — lower priority than stages 1-2 given it is
router-consumption-side, not placement-time, and the router's post-route
clearance/creepage enforcement is already independently Rust-ported and
proven (`docs/evidence/2026-07-26-clearance-rust-port.md` —
`router_v6/clearance_check.py::verify_clearance()` → `temper-drc-rs/src/
router_clearance.rs`, 9.7x-124x measured speedup, full differential proof;
**this is the "always-on clearance gate" the task brief names explicitly,
already done and already the model this plan's stages 1-2 follow**).

### Explicitly not staged: `IECCreepageGate` / `DeltaMapper`'s stale 6.0mm

Per this task's own coordination note, a sibling is actively editing
`IECCreepageGate`/`DeltaMapper`. Not scoped here beyond what §0 and the
sibling spike already established (dead code, stale threshold, one pinned
oracle at `_gates_py_oracle.py`). A Rust port of dead code is not a
priority; if the gate is revived (wired + threshold-corrected) by the
sibling's work, it becomes a stage-2-shaped candidate (small orchestration,
one existing oracle to extend, not re-pin, since the number itself would be
changing as part of reviving it — which is that sibling's call, not this
port plan's).

---

## 4. What the sibling `router_clearance.rs` port already proves about this class of work

`docs/evidence/2026-07-26-clearance-rust-port.md` (`router_v6/
clearance_check.py::verify_clearance()` → `temper-drc-rs/src/
router_clearance.rs`) is the closest existing precedent in this codebase
for exactly this kind of port — a safety-relevant geometry/clearance
function moved to Rust with a full differential-equivalence proof — and its
own findings bound expectations for stages 1-2 above:

- **Six non-obvious porting subtleties** were found only by reading the
  Python line-by-line before writing Rust (two different HV-keyword lists —
  the *same* dual-keyword-list pattern §1b found in `netclass_constraints.py`
  independently; CPython's NaN-comparison semantics; a NaN-poisoning
  accumulator; an asymmetric per-pair diameter quirk preserved as existing
  behavior, not fixed; hash-iteration-order non-determinism caught by an
  existing Hypothesis test, not new code). **Expect a comparable density of
  subtleties in stages 1-2** — `netclass_constraints.py`'s severity-rank
  resolution and existing-constraint dedup (`netclass_constraints.py:98-113`)
  have the same shape of "looks simple, has an order-dependent or
  type-discrimination subtlety" risk (the `isinstance(c, SeparatedConstraint)`
  vs duck-typing fix documented in that file's own comment, `:98-107`, is
  exactly this class of bug already found and fixed once in Python — a port
  must not silently regress it).
- **The actual, hard-won bug-catcher was the pre-existing test suite**, not
  new tests written for the port (the HashMap-ordering bug was caught by
  `test_dfm_hypothesis_fuzzing.py::test_clearance_idempotent`, already in
  the repo). This argues for running stages 1-2's new Rust against the
  *existing* `test_domain_clearance.py` (773 LOC) / `test_netclass_
  constraints.py` (237 LOC) suites as the primary bug-catching mechanism,
  not just new differential fixtures.
- **A real, measured performance ceiling for what "port to Rust" buys at
  this board's current scale**: the router-side port's own honest finding
  (§7 of that doc) is that at the real board's *current* trivial routing
  scale, Rust was *slower* than Python for the smallest case (FFI overhead
  dominates) and the win only compounds at scale the current board doesn't
  reach yet. **The placement-time constraint generation this spike is
  planning is smaller in scale than the router's per-segment clearance
  checks** (hundreds of components/pairs, not thousands of trace segments)
  — the performance case for stages 1-2 is weaker than it was for the
  already-landed router port. This plan's stages are justified by
  **surface-area consolidation** (§1a/§1b/§1c), not by a performance need;
  say so plainly rather than implying a speed win that the router precedent
  itself shows may not materialize at today's board scale.

---

## 5. Honest cost summary

| Stage | LOC ported (Rust, new) | LOC deleted (Python) | Oracle work | Risk | Blocking? |
|---|---:|---:|---|---|---|
| 0 — wire `domain_clearance.py` in | 0 | 0 | none (not a port) | owner/sibling call | Not this spike's scope |
| 1 — finish `domain_clearance.py`, single-source the matrix | ~30 | ~32 | 1 new oracle (no re-pin) | Low | None |
| 2 — port `netclass_constraints.py` orchestration | ~150-200 | ~110 (shimmed, not deleted outright) | 1 new oracle + full differential (live-by-default code) | Low-medium | Best sequenced after classifier-source decision (stage 3) if that decision is imminent |
| 3 — collapse 3 classifiers | not sized | not sized | depends on scope | High (touches live router obstacle halos) | **Owner decision required before scoping** |
| 4 — `pair_clearance.py`/`pair_creepage.py` | not sized this pass | ~388 | not checked this pass | Unassessed | Independent, can run parallel to 1-2 |

**Zero oracle re-pins are required for stages 1-2** — both target files have
no pinned oracle today (confirmed by direct grep of
`scripts/oracle_hashes.json`), so the work is oracle *creation* (the
migration pipeline's stage-3 TDD requirement: pin the pre-migration Python
first, red, then Rust green), which is materially cheaper and lower-risk
than the re-pin ceremony PR #1315 set today's bar for (independently
reproduce the evidence + add a positive control) — that ceremony is for
*changing* a value behind an existing pin, which does not apply to a file
with no pin yet.

**What this plan does not include**: any change to a clearance/creepage/
copper-weight/DRU threshold (hard rule); any deletion of a pinned oracle
(none exist for the stage-1/2 targets, so this is moot for them, but
applies fully to stage 0's `_gates_py_oracle.py` if that work ever touches
`IECCreepageGate`); the classifier-unification *decision* itself (stage 3
is scoped as "port after the decision," not "make the decision").

---

## Files referenced (read directly for this spike, not inherited from citation)

- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` (632 LOC, read in full)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py` (155 LOC, read in full)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/separated.py` (124 LOC, read in full)
- `packages/temper-placer/src/temper_placer/core/net_classification.py:145-167` (classify_net_type Rust delegation)
- `packages/temper-placer/src/temper_placer/core/design_rules.py:57-58` (`DesignRules = _tdb.DesignRules`)
- `packages/temper-placer/src/temper_placer/router_v6/pair_creepage.py`, `pair_clearance.py` (388 LOC combined)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/delta_mapper.py:131,148-153` (stale threshold feedback, confirmed not re-derived)
- `packages/temper-orchestration/src/clearance.rs` (1,890 LOC, "Phase E batch E3")
- `packages/temper-drc-rs/src/req_safe_01.rs` (1,585 LOC; `MATRIX_ROWS` at :1121, `req_safe_01_verify_iec60335` at :1133, `req_safe_01_requirement_matrix` at :1235, `req_safe_01_nets_domain_map` at :1435)
- `packages/temper-design-bundle/src/safety_value.rs` (`SafetyValue`/`Provenance` types, Table 16/17/18)
- `packages/temper-geometry/src/clearance_halo.rs`, `world_position.rs` — confirmed router/zone-generation-domain geometry primitives, NOT duplicated with the placer's CP-SAT box-separation math (different problem: obstacle halos around routed copper vs whole-component box separation at placement time)
- `packages/temper-drc-rs/src/router_clearance.rs` — the always-on post-route clearance gate (per task framing), confirmed distinct from this spike's placement-time target; its own port evidence (`docs/evidence/2026-07-26-clearance-rust-port.md`) is the closest precedent for this plan's stages 1-2
- `scripts/oracle_hashes.json` — grepped directly; zero entries for `domain_clearance`/`netclass_constraints`, one entry for `_gates_py_oracle.py` (`:113`)
- `docs/evidence/2026-08-01-ortools-cpsat-spike.md`, `2026-08-04-wave4-residual-verdicts.md` — CP-SAT KEEP verdict, read for §2
- `docs/evidence/2026-08-17-placer-creepage-constraint-spike.md` (PR #1317, sibling branch) — the liveness map this document builds on
- `docs/migration-pipeline.md` — the standing per-migration pipeline stages 1-8 referenced throughout

## What this spike did not settle

- Whether `test_requirement_matrix_values_pinned` (referenced by both
  Python and Rust comments) is a live, currently-run test or a stale
  reference — its exact file location was not confirmed in the time
  available. **UNVERIFIED**, flagged rather than assumed either way.
- Stage 3's and stage 4's precise LOC/risk sizing — deliberately left
  unsized pending the classifier-unification owner decision (stage 3) and
  a not-yet-performed oracle check (stage 4), rather than estimated
  optimistically.
- Whether `netclass_constraints.py`'s severity-rank resolution
  (`_SEVERITY_RANK`, ground>power>hv>signal precedence when a component has
  pins in multiple classes) has any test asserting that exact precedence
  order independent of the classifier's keyword defect — not traced this
  pass.
