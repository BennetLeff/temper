# Gate vacuity audit: are the rest of this repo's gates measuring what they claim?

<!-- provenance: commit=15919a964c52bd3f0f4cb31891efe589e0be49c4 dirty=false (HEAD at audit time, branch docs/gate-vacuity-audit; this PR adds only this file). No repo file was modified during the audit — every falsification was run against a scratch copy or a synthetic input outside the working tree. -->

**Date:** 2026-08-11
**Branch:** `docs/gate-vacuity-audit`
**Scope:** reconnaissance only. Nothing is fixed here; several findings sit in
files other agents are actively editing.

## Summary — the count first

**83 gate/checker/ratchet units audited** across `scripts/check_*.py`,
`scripts/*_gate.py`, `packages/temper-placer/src/temper_placer/regression/`,
the `.github/workflows/` steps that invoke them (all 70 `continue-on-error`
sites, and `required_contexts` vs. every real job name), and the
mutation-testing machinery that is supposed to prove the other gates fail
when the guarded thing breaks.

| Class | Count | |
|---|---|---|
| **SOUND** | 76 | genuinely checks what it claims |
| **VACUOUS** | 4 | cannot fail, or cannot fail for the reason claimed |
| **MISNAMED** | 2 | measures something real, but not what the name/docstring promises |
| **MISCALIBRATED** | 1 | fires on a threshold with enough slack to miss the thing it exists to catch |

Plus **6 unverified leads**, recorded below and deliberately *not* counted
as findings.

**The headline is the 76, not the 7.** This machinery is overwhelmingly
sound, and it is sound in a specific and unusual way: gates here
consistently *fail closed* on the exact edge cases that produced today's
seven incidents. `check_domain_partition.py` carries explicit
`n_domain_nets == 0` non-empty assertions. `mpn_fabrication_gate.py` and
`check_bom_source_reconciliation.py` distinguish `None` (allowlist parse
error → fail) from `[]` (empty allowlist → proceed) rather than collapsing
both to "nothing to check." `check_oracle_hashes.py` fails on an empty
registry, an empty disk scan, *and* an unregistered file. `pytest_guard.py`
exists solely because someone noticed a suite silently collapsing to zero.
Several files audited here document their own prior vacuity incidents in
their docstrings and explain what was changed. Today's seven were largely
the unlucky tail of a body of work that has already internalized this
failure class.

That said, the seven-that-were-found were not the whole tail. Seven more
survive. The top two are directly on the safety path — an HV net-integrity
gate and the regenerated-board DRC acceptance gate — and both are CI-wired,
hard-gating, and green today.

A structural note that ties most of the findings together: **they are gates
that scan for a Python construct the Rust migration removed, or gates that
were never wired to CI at all.** The common mechanism is not sloppy logic —
the logic is fine — it is that a gate's *input set* silently went to zero
underneath it while the gate kept reporting on the empty set. **Three
separate gates share this exact blind spot** (§9), which is the single most
actionable thing in this document.

---

## Findings, ranked by consequence if the guarded thing broke

### 1. `check_erc_off_grid_consequence.py` — VACUOUS on an entire outcome class (HV safety)

**Claims** (docstring, and its own terminal output): for every ERC
`endpoint_off_grid` warning, the schematic net a pin actually sits on
matches the atopile-compiled net *member-for-member* — so that a
cosmetic-looking warning class cannot hide a real "looks connected, isn't"
defect. On success it prints, unqualified:

> `PASSED: every endpoint_off_grid pin's schematic net matches its atopile net member-for-member. No electrical disconnection or unintended short rides on this warning class.`

**Mechanism** — `scripts/check_erc_off_grid_consequence.py:285-300`:

```python
status = 'OK'
detail = ato_name
if ato_name is None:
    status = 'NO_ATOPILE_NET'          # <-- never appended to `mismatches`
else:
    sch_names_for_pin = sch_pin_to_nets.get(key, set())
    if ato_name not in sch_names_for_pin:
        status = 'MISMATCH'
        ...
        mismatches.append((key, domain, detail))
```

`main()` fails only on `if mismatches:` (line 312). A pin that appears in
the schematic and is flagged off-grid, but has **no entry in the
atopile-compiled netlist at all**, is classified `NO_ATOPILE_NET` and
unconditionally excluded from the failure set.

This is not a milder form of "matches." It is the one case the gate
*structurally cannot check* — the design's stated intent says nothing about
this pin — and it is folded into the same green verdict as a fully-verified
member-for-member match.

**Proof** (synthetic inputs, outside the repo tree). Setup: an ERC report
flags both `J1` pin 1 and `U99` pin 1 as `endpoint_off_grid`; the schematic
netlist places **both** on net `HV_LINE`; the atopile netlist declares
`HV_LINE` as containing **only `J1`**, and mentions `U99` nowhere; the
domain manifest declares `HV_LINE` as HV/mains. Running the real,
unmodified script:

```
$ .venv/bin/python scripts/check_erc_off_grid_consequence.py \
    --erc-json erc.json --sch-netlist-xml sch_netlist.xml \
    --atopile-net atopile.net --domain-manifest domain_manifest.yaml

ref      pin   net        domain                                                  status
J1       1     HV_LINE    HV/mains                                                OK
U99      1     None       UNKNOWN (no atopile net -- pin not in compiled design)  NO_ATOPILE_NET

endpoint_off_grid pins checked: 2

Domain breakdown:
     1  UNKNOWN (no atopile net -- pin not in compiled design)
     1  HV/mains

PASSED: every endpoint_off_grid pin's schematic net matches its atopile net
member-for-member. No electrical disconnection or unintended short rides on
this warning class.

REAL_EXIT=0
```

A pin sitting on a live HV net that the compiled design never declares —
precisely the scenario in the gate's own rationale — exits 0 under an
unqualified pass claim.

**The sharpest detail is in that output.** The gate does not fail to notice.
It prints, in its own words, `UNKNOWN (no atopile net -- pin not in
compiled design)`, counts it in the domain breakdown, and *then* asserts
that **every** pin matched member-for-member. The information needed to
fail is computed, displayed, and discarded. That also means the fix is
purely in the verdict logic — no new analysis is required.

**Consequence.** The production board carries **163 live
`endpoint_off_grid` warnings** today, all currently `OK`
(`docs/evidence/2026-08-07-erc-off-grid-endpoint-analysis.md`). Roughly a
third of all pins on this board land off-grid, so this is a well-populated
class, not a corner. A component added to the schematic but not yet (or
incorrectly) declared in atopile — the ordinary shape of an in-progress
design change — lands in exactly this blind spot: HV-adjacent, unverified,
and reported clean. It is CI-wired and hard-gating
(`python-tests.yml:2086`, no `continue-on-error`), which makes the green
result actively load-bearing for a reviewer.

**One-line fix:** treat `NO_ATOPILE_NET` as a second failure class
alongside `MISMATCH` — or at minimum, gate the unqualified "PASSED" wording
on `NO_ATOPILE_NET == 0`.

**Not previously documented** in `docs/evidence/` or `AGENTS.md`.

---

### 2. `verify_regenerated_board.py` Assertion 4 — a brand-new DRC violation *class* is a warning, not a failure (board safety)

**Claims** — "Assertion 4: DRC within the committed ceiling", running N=12
DRC samples against the regenerated board and asserting every observed
range is within `drc_ceiling.json`. This is the acceptance gate for
`board-regeneration.yml`, the workflow that decides whether a
freshly-routed board is equivalent to the committed one — including under
its own deliberate defect-injection mode.

**Mechanism** — `scripts/verify_regenerated_board.py:404-421`:

```python
ceiling = ceilings.get(cat)
if ceiling is None:
    missing_ceiling.append(f"{cat}: observed {lo}-{hi}, no ceiling entry")
    continue                       # <-- not a failure
...
if missing_ceiling:
    print("\n  WARNING: categories without ceiling entries (not failures):")
```

A violation category with no entry in `drc_ceiling.json` is printed as a
warning and skipped. Only categories that *already have* a ceiling can fail
the assertion.

**This inverts the convention the ceiling file itself declares.**
`power_pcb_dataset/drc_ceiling.json`'s own `_march` log, entry
`2026-07-27`, states the rule verbatim:

> "`violations_by_type` is now populated AND enforced — **a category absent
> from it has an implicit ceiling of 0**, so a new violation class cannot
> arrive for free under the aggregate."

`DrcRatchet._check_board` implements exactly that implicit-zero semantics
(`drc_ratchet.py:391-393` and the surrounding docstrings, which reference
"implicit ceiling of 0" in five places). `verify_regenerated_board.py`
implements the opposite: absent category → implicit ceiling of **infinity**.

**Proof** — the real `_assert_drc_within_ceiling`, against the real
`drc_ceiling.json`, with the DRC sampler stubbed to report a violation
class that does not exist in the ceiling:

```
$ .venv/bin/python proof_verify_regen.py
  loaded ceiling: 13 error categories, total=1252
  DRC sample 1/1: 12 errors across 2 categories

  WARNING: categories without ceiling entries (not failures):
    phantom_new_violation_class: observed 7-7, no ceiling entry
[PASS] Assertion 4 (DRC within ceiling): 13 categories OK (N=1), 0 exceedances

>>> RESULT: _assert_drc_within_ceiling returned normally (NO EXCEPTION) <<<
```

Seven instances of a violation class that has never been measured, never
been approved, and appears in no ceiling record — reported as `[PASS]`,
`0 exceedances`.

**Consequence.** The 13 categories currently in the ceiling are the ones
that happened to be non-zero when it was last measured. Every category
*outside* that set is exactly the set of "new violation classes" — the
class of regression this assertion is the last line of defence against, on
a regenerated mains board. `docs/evidence/2026-08-07-missing-courtyard-and-hole-to-hole-classes.md`
shows new classes genuinely do appear on this board. A regeneration that
introduces, say, `silk_over_copper` or a new isolation class passes
Assertion 4 clean.

**One-line fix:** treat `missing_ceiling` as failures (implicit ceiling 0),
matching `drc_ceiling.json`'s own stated convention and `DrcRatchet`'s
implementation.

**Not previously documented.**

---

### 3. `physics_soundness_register_gate.py` — one of its three declared scan targets silently selects zero surfaces

**Claims** (docstring §"What the scan covers"): the gate scans three
surfaces for physics-gated constraint encoders that must carry a
soundness-proof register entry. The third is listed explicitly:

> `router_v6/constraint_model.py` — classes subclassing `Constraint`.

**Mechanism.** The `constraint_subclasses` selector
(`physics_soundness_register_gate.py:351-357`) matches
`ast.ClassDef` nodes with a base named `Constraint`. After the Phase-E Rust
migration, `router_v6/constraint_model.py` no longer contains any such
class — the constraint types are Rust pyclasses re-exported by plain
assignment:

```
packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:56
    CapacityConstraint = _mb.CapacityConstraint
```

There is no per-spec emptiness guard. The `tool_errors` "matched no files"
branch (line 373-374) applies only to `glob` specs; a `path` spec whose
file exists and parses cleanly but selects nothing produces **no error and
no output** — the `for node in _surface_defs(...)` loop body simply never
runs (lines 391-410).

**Proof** — instrumenting the real `discover_surfaces()` against the real
source tree:

```
$ .venv/bin/python proof_physics_scan.py
tool_errors: []
total surfaces: 9
  {'kind': 'handler-encoder',      'physics_gated': False}   x5
  {'kind': 'handler-encoder',      'physics_gated': True}    x2
  {'kind': 'constraint-generator', 'physics_gated': True}    x1
  ...
router_v6/constraint_model.py 'classes subclassing Constraint' surfaces: 0
```

Two of three scan specs contribute all 9 surfaces. The third contributes
zero, silently — so any global "did we find anything at all?" alarm is
satisfied by the other two and never fires.

**What makes this one genuinely nasty: the gate is currently RED, for the
opposite reason.** It exits 3 today:

```
$ .venv/bin/python scripts/physics_soundness_register_gate.py
[PHYS-SND] FAILED: 2 issue(s):
  register entry does not resolve to code: temper_placer.router_v6.constraint_model.CapacityConstraint
    (encoder symbol not found in .../router_v6/constraint_model.py)
  register entry ...CapacityConstraint: proof_location.symbol 'sequential counter' not found ...
EXIT=3
```

The *reverse* direction (every register entry must resolve to real code)
correctly detects the same migration. A reader seeing this gate red
reasonably concludes it is working. It is — in one direction. The forward
direction (every physics-gated surface must have a register entry) has been
scanning an empty set for that surface since the migration, and would keep
doing so after someone fixes the stale entry and turns the gate green.

It is CI-wired and hard-gating (`python-tests.yml:2318`, no
`continue-on-error`) — but in the job `AGENTS.md` already documents as
absent from `required_contexts`, so the red does not block merges today.

**One-line fix:** raise a tool error when any scan spec selects zero
surfaces (matching the existing glob-level behaviour), and re-point the
selector at the Rust re-export assignment form.

**Not previously documented** — `docs/evidence/2026-08-06-wave4-owned-surface-closeout.md`
discusses this surface's migration but not the scan blindness.

---

### 4. `bmc_adoption_gate.py` — VACUOUS twice over: never wired to CI, and currently unable to check anything

**Claims** (docstring): *"BMC adoption gate: enforce ESL + BMC test coverage
for every `Constraint` subclass. Exit codes ... 3 — Missing ESL or BMC test
(blocks merge)."* `scripts/manifest.yaml` marks it `category: keep`,
`disposition: ci-gate`.

**Mechanism.**

1. **Never wired.** `git log -p --all -- .github/workflows/*.yml | grep
   bmc_adoption_gate.py` returns zero hits across the entire history of
   every workflow file. Not "wired then removed" — never present.
2. The repo's own invocation tracer agrees: `scripts/invocation_graph.json`
   records `"bmc_adoption_gate.py": []` — zero callers anywhere.
3. **Also non-functional**, independently of wiring:

```
$ uv run python scripts/bmc_adoption_gate.py
[BMC-GATE] No Constraint subclasses found — parser error?
EXIT: 5
```

Same root cause as finding 3: the Rust migration removed the Python
`class X(Constraint):` forms the AST scan looks for. `constraint_model.py`'s
own docstring adds that the `esl()`/`ESL_REGISTRY` machinery this gate
polices is itself retired — its only consumers (`esl.py`, `bmc.py`) were
deleted before the migration.

**Consequence.** Lower than 1-3: the thing it guarded (ESL/BMC coverage for
Python constraint subclasses) largely no longer exists. The real cost is
the *claim* — a `disposition: ci-gate` label and a "blocks merge" docstring
on something that has never run once. That is the same misreading risk as
findings 6 and 7 in today's set.

Partially noted before: `docs/evidence/2026-08-02-validation-portfolio-review.md`
line 67 records that it "exits 3 today" (an earlier, different failure —
pre-migration), but says nothing about the wiring gap.
`docs/evidence/2026-07-27-gate-subset-blindness-audit.md` reviews its
scan-scope soundness and concludes it fails closed correctly — without ever
checking whether it is invoked.

**One-line fix:** delete it, or re-point it at the Rust pyclass surface and
wire it. Either way, correct the manifest `disposition`.

---

### 5. `verify_proofs.py` / `PROOFS.toml` — MISNAMED registry, and an unwired guard that would have caught it 34 days ago

Two defects, compounding.

**(a) The registry is 100% dangling, and its guard runs nowhere.**
`packages/temper-rust-router/PROOFS.toml` records the soundness proofs for
the SAT constraint-combinator library: 13 entries across three primitives,
three compositions, and the rewrite engine. **Every referenced source file
was deleted from that crate on 2026-07-08** (commit `87bda65e4`, "slim
wrapper to cdylib-only pyo3 crate depending on -core" — it removed
`src/combinator/*.rs` and `src/encoding.rs` wholesale, moving them to
`packages/temper-rust-router-core/`). `PROOFS.toml` was never re-pointed
and has not been touched since it was created.

`verify_proofs.py` *does* detect this — it correctly reports 11 failures
and exits 1. It has simply never been given the chance:
`scripts/invocation_graph.json` records `"verify_proofs.py": []`, zero
callers; no workflow, no Makefile target references it; its manifest entry
says `disposition: ci-gate`, `last_run: '2026-06-29'`. So the registry has
been fully dangling for 34 days with a working guard sitting beside it,
unwired.

**(b) Even repaired, two of the entries are misnamed** — and this is the
part `verify_proofs.py` structurally cannot catch, because it verifies only
that a function *with that name exists*:

```toml
[rewrite.engine]
exhaustive_n6    = "src/combinator/rewrite.rs::tests::exhaustive_rewrite_preserves_sat_n4"
confluence_10000 = "src/combinator/rewrite.rs::tests::exhaustive_rewrite_preserves_sat_n4"
```

Two distinct proof obligations — exhaustive verification at n=6, and a
10,000-case confluence check — are both discharged by **one test, which is
neither**. In `temper-rust-router-core/src/combinator/rewrite.rs:1257`:

```rust
fn exhaustive_rewrite_preserves_sat_n4() {
    // For n=4 variables, exhaustively verify rewrite preserves satisfiability
    for n in 1..=4u32 {
```

It is n≤4, and it tests SAT-preservation, not confluence. Searching the
whole crate: **no confluence test exists at all** (`grep -in confluen` hits
only two doc-comment lines at `rewrite.rs:43,47` asserting confluence in
prose), and **no n=6 test exists**. The same n≤4 test is additionally cited
as `P1_MutualExclusion.exhaustive_test`, `P1.cross_validation`, and
`P2.cross_validation` — one test standing in for five separate claims.

**(c) A third, smaller hole:** `verify_proofs.py`'s docstring promises it
checks that *"Cross-validation tests reference proptest or hypothesis
dependency."* No such check is implemented — `main()` validates `encoding`
and `exhaustive_test` for primitives, `proof` for compositions, and the two
`rewrite.engine` keys. The three `cross_validation` entries are never
validated at all.

**Supporting proof of the name-only weakness** — a commented-out test still
satisfies the check:

```
$ .venv/bin/python -c "...test_function_exists(p, 'exhaustive_rewrite_preserves_sat_n4')"
regex says exists (commented-out fn): True
```

**Consequence.** This is the same shape as today's findings 6 and 7:
`PROOFS.toml` reads as a formal-verification ledger for the constraint
encoder, and a reader consulting it concludes the rewrite engine has been
exhaustively verified to n=6 and checked for confluence over 10,000 cases.
Neither is true, and neither has ever been true. Consequence is bounded by
how much this crate is currently load-bearing — but the registry's whole
purpose is to be the thing you trust instead of re-deriving.

**One-line fix:** re-point the paths at `temper-rust-router-core/`, rename
`exhaustive_n6`/`confluence_10000` to match what the cited test actually
proves (or write the missing tests), and wire `verify_proofs.py` into CI.

---

### 6. `pytest_guard.py` floors — MISCALIBRATED slack on the router_v6 invariant groups

`pytest_guard.py` itself is **SOUND** and is one of the better pieces of
machinery in the repo — it exists precisely because a suite silently
collapsed to zero, and it correctly fails on an unparseable report, a
missing path, and an all-skipped run.

The *floors it is given* are the issue. All three router_v6 invariant groups
run with `--min-tests 500`. `python-tests.yml`'s own inline comment on group
1 records a measured **692 selected** on a full local run (2026-08-07). That
is 192 tests — 28% — of silent slack.

Compounding it, all three groups pass `--continue-on-collection-errors`, so
a file that fails to import does **not** abort the run; its tests simply
vanish from the count. The guard catches total collapse. It does not catch
the loss of any single test file, which is the more likely regression and
is exactly what happened to group 2 on 2026-07-31 (documented in the
workflow's own comment: a deleted file left in the path list zeroed the
group for 7 days).

**Honest labelling:** this is quantified from the workflow's own recorded
measurement, not from a run of my own — local collection currently aborts
on a stale compiled extension (`temper_design_bundle_python` has no
attribute `decision_contracts`), so I could not re-measure the live counts.
The 692-vs-500 gap is from the repo's record; treat the exact number as
that measurement's, not mine.

**One-line fix:** raise each group's floor to its current measured count
minus a small margin, and re-ratchet it when the suite grows — as the
guard's own docstring already instructs.

---

### 7. `check_drc_determinism.py` — MISNAMED disposition

`scripts/manifest.yaml:334-344` declares `disposition: ci-gate`.
`grep -rl check_drc_determinism .github/workflows/` returns nothing. It is a
manual determinism-measurement harness (its own docstring opens
"Measure whether..."), not a gate. The tool appears sound when run; only the
label is wrong. Low consequence, one-line manifest fix — listed for
completeness because the same mislabelling is what made findings 4 and 5
invisible.

---

## Unverified leads (not findings)

Listed so they are not lost, explicitly **not** proven:

1. **`_lib/gate_allowlist.py`'s shrink-mode swallow.** Four gates
   (`check_physics_provenance`, `check_coverage_gate`,
   `check_evidence_provenance`, `check_measurement_provenance`) wrap
   `git_show_main_allowlist()` in `except (RuntimeError, FileNotFoundError):
   return None`, and their `check_shrink_mode` then prints a yellow warning
   and **returns 0 (pass)**. If `origin/main` were unresolvable, the entire
   monotonic-shrink ratchet would silently skip. **Why this is only a lead:**
   the job that runs these uses `fetch-depth: 0` (`python-tests.yml:1197`),
   so `origin/main` does resolve in practice today. It is a latent hazard
   contingent on a checkout config, not a live vacuity.
2. **`bmc_adoption_gate.py`'s `_has_bmc_test_reference`** matches a bare
   substring of the class name anywhere in `test_bmc_*.py` — false-positive
   prone on a name that is a substring of another. Moot while the gate is
   unreachable (finding 4).
3. **`check_wire_format_fidelity.py`'s "field mentioned anywhere, including
   in a comment"** match is weak in the same shape as today's findings — but
   it is explicitly documented as a deliberate design choice in its own
   docstring, not a hidden defect. Not reported as a finding.
4. **`verify_proofs.py`'s regex-level `fn <name>(` check** cannot distinguish
   a live test from a commented-out or `#[ignore]`d one (demonstrated in
   finding 5c). Currently moot — the files are absent entirely — but it
   would become live the moment the paths are repaired.
5. **`known_failure_pins.py`'s `_nodeid_resolves`** uses the same
   `f"def {def_name}(" in text` substring check and inherits the same
   weakness. Its own docstring acknowledges the regex-level tradeoff
   deliberately; flagged only for symmetry with lead 4.
6. **`check_gate_mutations.py` reports a mutation score of `1.00` when zero
   mutations were scored** (`check_gate_mutations.py:144,157,383` —
   `killed / scored if scored else 1.0`). The isolation-keepout block above
   prints `mutation score 1.00 (0 killed / 0 scored, 3 unverified)`. The run
   still exits 1 and the raw counts are printed adjacent, so nobody is
   misled by the exit code — but this repo routinely quotes overall mutation
   scores into evidence docs
   (`docs/evidence/2026-08-07-gate-mutation-sweep.md:70` cites `1.0000`),
   and a `0/0 → 1.00` is exactly the kind of number that survives being
   copied out of context. Reporting-only; not a gate defect.

## Already documented elsewhere — cross-referenced, not re-reported

`check_creepage_clearance_drift.py` (commented out of its workflow) and
`check_refdes_identity_stability.py` (never wired) are both already recorded
— in `docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md` and
`docs/evidence/2026-07-30-refdes-identity-stability-gate.md` respectively.
`check_traceability.py`'s unwired state is stated in
`docs/evidence/2026-07-27-traceability-scope-fix.md:72`. The Pipeline Closure
Test job's `continue-on-error` masking is documented inline and in
`docs/evidence/2026-08-11-python-ci-load-inventory.md`. The
"Board, Provenance & Requirements Gates" job's absence from
`required_contexts` is documented in `AGENTS.md`.

## What the audit did not find

Worth stating plainly, because absence of these is the reassuring result:

- **No second `required_contexts` gap.** All 8 required contexts resolve to
  real job names (cross-checked against every `name:` in `python-tests.yml`
  and `pr-perf-check.yml`). Every job *not* listed is either
  `continue-on-error`-masked or trunk/nightly-only behind an explicit `if:`
  — consistent with the documented design.
- **No exit-code swallowing in workflow steps.** All 70 `continue-on-error`
  sites were enumerated; ~10 non-obvious ones read in full. Every one
  carries an inline comment naming a specific reason, and each is genuinely
  advisory for that reason. No `|| true`, no `set +e`, no bare `exit 0`, no
  pipe-through-`tail` masking a real gate was found.
- **No vacuity in the mutation-testing machinery itself** beyond finding 3's
  cousin in `constraint_mutation_gate.py` (§9). This was the layer worth
  worrying about most — a vacuous mutation gate would have let every other
  vacuous gate through undetected — so it was exercised, not just read:

  ```
  $ .venv/bin/python scripts/check_gate_mutations.py    ; EXIT=1
  OVERALL: 16 killed, 0 survived, 3 unverified, 0 equivalent, 0 not_applicable
  ```

  `check_gate_mutations.py` fails closed on every axis that matters: zero
  registered triples is a failure ("an empty manifest is not '0 survivors'"),
  a mutation whose locator no longer matches current source is
  `NOT_APPLICABLE` and fails ("an entry that never mutated anything cannot
  be reported as evidence of anything"), and a broken baseline is
  `UNVERIFIED` and fails. It hashes the committed gate's bytes before and
  after the sweep to prove it never mutated a tracked file. The 3 UNVERIFIED
  above are a stale local compiled extension
  (`temper_geometry` missing `kicad_rotate_local_to_world_deg_py`), not a
  CI condition — and the run still exits 1, which is the correct behaviour.

  `check_netlist_mutation_corpus.py` is the same quality: it fails the gate
  if a mutation could not be applied, if the owning finding did not fire,
  *and* if the preflight surface did not fail on the mutated netlist — three
  independent ways to catch a mutation that bit nothing.

- **`check_regression.py` and `regression/corpus_runner.py` are retired
  stubs — and say so.** Both are honestly labelled in their own first lines
  (the JAX optimizer they drove was removed; `_run_board` returns a "retired"
  error for every valid board). They claim nothing, so they are not vacuous.
  Noted only so a reader does not mistake them for live coverage.

## §9 — the pattern under findings 3, 4 and 5, and a suggested standing check

Most of the findings share one mechanism, and it is not a logic error:

> A gate's **input set** silently went to zero — or its target files moved —
> while the gate kept running and kept reporting on the empty set.

**Three separate gates scan the same file for the same vanished construct.**
`bmc_adoption_gate.py`, `physics_soundness_register_gate.py`, and
`constraint_mutation_gate.py` all AST-scan
`router_v6/constraint_model.py` for `class X(Constraint):` — a form the
Phase-E Rust migration replaced with `X = _mb.X` re-export assignments. All
three now select **zero** surfaces there. `verify_proofs.py` is the same
shape one level up: it points at a directory tree that moved crates.

In every case the *file still exists and still parses*, so every existence
check the gate performs succeeds; only the selector matches nothing.

Two of the three are currently **red for the reverse reason** — their
register-entry-must-resolve check correctly notices the same migration:

```
$ .venv/bin/python scripts/constraint_mutation_gate.py     ; EXIT=3
[MUTATION-GATE] Constraint mutation gate FAILED: 4 violation(s):
  CapacityConstraint:            register entry resolves to no router-V6 class
  ChannelSeparationConstraint:   register entry resolves to no router-V6 class
  DiffPairConstraint:            register entry resolves to no router-V6 class
  LayerConstraint:               register entry resolves to no router-V6 class
```

This is the trap. The red looks like the gate working — and in one
direction it is. But the fix a maintainer would naturally apply (retire or
re-point the four stale register entries) turns the gate green while
leaving the forward direction scanning an empty set forever. The reverse
check is self-limiting: it can only ever flag entries that already exist.
Nothing would flag a *new* physics-gated constraint class arriving
unregistered.

`check_vacuous_gates.py` is the repo's mechanical form of "every `all()`
needs a non-empty assertion in front of it," and its docstring records two
prior rewrites specifically to widen its scope. The gap this audit surfaces
is adjacent but distinct: **it lints for vacuous aggregation inside a
checker, not for a checker whose scan set is empty.** A per-spec
`if not selected: tool_error(...)` convention — which
`physics_soundness_register_gate.py` already implements for `glob` specs and
merely omits for `path` specs — would have caught all three at the moment
of the migration, on the migration's own PR.

Worth noting the near-miss: `bmc_adoption_gate.py` *does* have exactly this
guard (`[BMC-GATE] No Constraint subclasses found — parser error?`, exit 5).
It is the only one of the three that fails loudly on the empty scan — and
it is the one that has never been wired to CI, so nobody has ever seen it
fire.

That is a maintainer call, not applied here.

## Method

Every VACUOUS/MISCALIBRATED claim above was falsified by breaking the
guarded thing and observing the gate still pass — against a scratch copy or
a synthetic input outside the repo tree. **No file in the working tree was
modified during this audit.** Anything not falsified is labelled
UNVERIFIED-LEAD and is not counted in the finding totals.

Coverage, and its limits, stated honestly:

- **26** PCB/electrical/safety-domain checkers (`check_board_containment`,
  `check_copper_net_consistency`, `check_hv_netclass_coverage`,
  `check_isolation_keepout`, `check_net_classification`,
  `check_erc_off_grid_consequence`, `ci_check_erc`, the firmware-contract and
  state-machine checkers, …).
- **34** provenance / CI-hygiene / build-integrity gates
  (`check_evidence_provenance`, `check_measurement_provenance`,
  `check_oracle_hashes`, `check_typecheck_gate`, `import_linter_gate`,
  `mpn_fabrication_gate`, `part_stress_gate`, `vulture_gate`, …).
- **13** mutation-testing and regression-ratchet modules
  (`check_gate_mutations`, `gate_mutate`, `constraint_mutation_gate`,
  `check_netlist_mutation_corpus`, the three defect-corpus checkers,
  `check_corpus_specificity`, `check_ceiling_raise_evidence_corpus`,
  `corpus_runner`, `drc_ratchet`, …).
- **9** remaining checkers not in the above groups (`verify_proofs`,
  `verify_regenerated_board`, `known_failure_pins`, `pytest_guard`,
  `physics_soundness_register_gate`, `check_manifest_gate`,
  `test_root_hygiene`, `quarantine_report`, `_lib/gate_allowlist`).
- **1** workflow-wiring unit: all 70 `continue-on-error` sites enumerated,
  ~10 read in full, and `required_contexts` cross-checked against every
  `name:` in `python-tests.yml` and `pr-perf-check.yml`.

Depth was not uniform. Roughly two-thirds were read end-to-end or executed;
the remainder were read for decision logic and CI wiring, with targeted
greps for the specific anti-patterns in today's seven (swallowed exception,
single-hardcoded-category, always-empty input, default-on-error return). A
gate marked SOUND here means "no instance of this failure class found,"
not "formally verified."

The seven already-confirmed instances from 2026-08-11 were excluded from
the audit set and are not counted in the 83. `scripts/check_unwired_kernels.py`
(#1020) was likewise excluded as already documented.
