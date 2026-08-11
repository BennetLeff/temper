# Gate vacuity audit: are the rest of this repo's gates measuring what they claim?

<!-- provenance: commit=a13edb35227f82daaa92613e8598ed43172e19e8 dirty=false (HEAD at second-pass audit time, branch docs/gate-vacuity-audit; the first pass was measured at 15919a964c52bd3f0f4cb31891efe589e0be49c4, this file's parent commit). This PR adds only this file. No repo file was modified during either pass — every falsification was run against a scratch copy or a synthetic input outside the working tree. -->

**Date:** 2026-08-11
**Branch:** `docs/gate-vacuity-audit`
**Scope:** reconnaissance only. Nothing is fixed here; several findings sit in
files other agents are actively editing.

## Summary — the count first

**94 gate/checker/ratchet units audited** across `scripts/check_*.py`,
`scripts/*_gate.py`, `packages/temper-placer/src/temper_placer/regression/`,
the `.github/workflows/` steps that invoke them (all 70 `continue-on-error`
sites, and `required_contexts` vs. every real job name **in all 31 workflow
files**), and the mutation-testing machinery that is supposed to prove the
other gates fail when the guarded thing breaks.

| Class | Count | |
|---|---|---|
| **SOUND** | 76 | genuinely checks what it claims |
| **VACUOUS** | 9 | cannot fail, or cannot fail for the reason claimed |
| **MISCALIBRATED** | 6 | fires on the wrong threshold, category, extension, or scan set |
| **MISNAMED** | 3 | measures something real, but not what the name/docstring promises |

Plus **3 CI wiring gaps** (findings 11, 12, 21) — not a property of any one
script, but of how correct gates are connected — and **9 unverified leads**,
recorded below and deliberately *not* counted as findings.

> **Note on this document's history.** The first pass (findings 1–7, §9)
> audited 83 units. A second pass re-audited the regression, mutation and
> bookkeeping layers at greater depth, enumerated the 11
> `regression/` modules the first pass had not listed individually, and
> widened the `required_contexts` cross-check from two workflow files to all
> 31 — adding findings 8–21. The second pass therefore deepened the same
> population far more than it widened it; 94 is the union, not 83 + 29.
>
> **The second pass falsified one of the first pass's reassuring claims** —
> see finding 21 and the amended bullet under "What the audit did not find."
> The correction is called out rather than quietly edited, because the
> mechanism by which the first pass got it wrong — cross-checking
> `required_contexts` against only the two workflow files that happened to
> contain the required jobs — is itself an instance of the failure class this
> document is about: a sound check reporting a confident negative over a scan
> set narrower than its claim.

**The headline is the 76, not the 18.** This machinery is overwhelmingly
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

That said, the seven-that-were-found were not the whole tail. Eighteen more
survive, plus three wiring gaps. The top two are directly on the safety path — an HV net-integrity
gate and the regenerated-board DRC acceptance gate — and both are CI-wired,
hard-gating, and green today.

A structural note that ties most of the findings together: **they are gates
that scan for a Python construct the Rust migration removed, or gates that
were never wired to CI at all.** The common mechanism is not sloppy logic —
the logic is fine — it is that a gate's *input set* silently went to zero
underneath it while the gate kept reporting on the empty set. **Three
separate gates share this exact blind spot** (§9), which is the single most
actionable thing in this document.

The second pass sharpens that framing rather than replacing it. Its findings
divide into the same two mechanisms — **an empty or stale input set**
(findings 13, 14, 16, 17) and **a correct gate whose verdict goes nowhere**
(findings 11, 12, 20, 21). The second mechanism is the one that dominates the
second pass, and it is worth naming separately: these are failures of
*wiring and labeling*, not of logic. Reading the script tells you nothing,
because the script is fine. You have to read the script *and* the workflow
*and* `required-checks.json` *and* the manifest to see it. The measurable
form of that, and finding 12's mechanism in one number: **11 of the 86
scripts labeled `disposition: ci-gate` in `scripts/manifest.yaml` do not run
in any live CI step** (12.8%), two of them present only inside commented-out
blocks.

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

### 8. `constraint_mutation_gate.py` — a required, merge-blocking gate that cannot fail when the encoder it guards is emptied (CP-SAT / mains-board keepout)

This is the highest-consequence finding in the document, and it is a
*different* defect from the empty-scan one §9 describes in the same file.
§9 covers the gate's **reverse** direction (stale register entries that no
longer resolve). This is the **forward** direction: the thing the gate exists
to assert.

**Claims** (docstring): "every CP-SAT constraint encoding must carry a
registered, non-empty kill set (**the R4 bug-class mutations its own defenses
catch**)". The name and the R32 framing both promise that each encoder's
*defenses* were shown to kill injected bugs.

**Wiring:** `python-tests.yml:2380`, job **`Repo Hygiene & Import Gates`** —
which **is** in `required_contexts`. No `continue-on-error`. This is one of
the eight checks that actually block a merge.

**Mechanism.** The gate never runs a mutation. It AST-scans for a
`@register_handler` decorator and then reads a static YAML file:

```
$ grep -n "subprocess\|import_module\|exec(\|runpy\|constraint_mutation_runner" scripts/constraint_mutation_gate.py
(no output)
```

Its only inputs are the decorator's presence and
`power_pcb_dataset/constraint_kill_sets.yaml` — a register regenerated solely
by `constraint_mutation_runner.py`, which no workflow invokes on any cadence
(`grep -rn constraint_mutation_runner .github/workflows/` → nothing;
`scripts/manifest.yaml` records `last_run: '2026-08-02'`). The workflow's own
comment states the design — "the runner that regenerates the register is
invoked manually/periodically" — but nothing enforces the "periodically", so
the register is free to drift arbitrarily far from the code it certifies.

**Proof.** A scratch tree containing the real gate, the real
`handlers/keepout.py`, and the matching register entry. Baseline:

```
$ .venv/bin/python cmg_mine/scripts/constraint_mutation_gate.py
[MUTATION-GATE] OK: 1 handler surface(s) with non-empty, triaged kill sets; 0 router-V6 class(es) registered
BASELINE EXIT: 0
```

Then every enforcement line of `encode_keepout` is deleted — including the
`AddNoOverlap2D` call that is the sole mechanism keeping components out of
the isolation keepout zone on a mains-voltage board — leaving only the
decorator and `return []`:

```
$ grep -c "AddNoOverlap2D" .../handlers/keepout.py
0
$ .venv/bin/python cmg_mine/scripts/constraint_mutation_gate.py
[MUTATION-GATE] OK: 1 handler surface(s) with non-empty, triaged kill sets; 0 router-V6 class(es) registered
EXIT AFTER GUTTING: 0
```

The gate passes, unchanged, on an encoder with no enforcement left in it. The
register still testifies that eleven R4 mutations were killed by defenses that
no longer exist. What the gate actually verifies is **register bookkeeping**;
what its name, docstring and R32 framing claim is **that the defenses hold**.

**Second defect, same file: it is red today for a reason unrelated to any of
this.** Confirmed on `main`, not merely locally:

```
$ .venv/bin/python scripts/constraint_mutation_gate.py            ; EXIT=3
  CapacityConstraint: register entry resolves to no router-V6 class      (x4)

$ gh run view 31541582172 --json jobs --jq '...'
{"conclusion":"failure","name":"Repo Hygiene & Import Gates"}
$ gh run view 31541582172 --log-failed | grep MUTATION-GATE
Repo Hygiene & Import Gates  Constraint mutation gate (kill-set register)  [MUTATION-GATE] ... FAILED: 4 violation(s)
```

Root cause is §9's migration (`8dce8f8ae`, 2026-08-08): the four classes are
now `X = _mb.X` re-exports, invisible to an `ast.ClassDef` scan, though they
exist and are registered in `ESL_REGISTRY` (`constraint_model.py:155`). So a
**required** check has been red on `main` for three days, for a false-positive
reason, while being structurally unable to fail for its real one. Both halves
of the pattern this audit is about, in one file.

**One-line fix** (not applied): resolve the classes by importing the module
and walking `ESL_REGISTRY`, rather than AST-scanning for `class X(Constraint)`
— which also fixes §9's other two gates. The forward-direction vacuity needs
the runner wired to a cadence, which is a maintainer call.

---

### 9. `generate_kicad_dru.py` omits an HV net class from trace-width rule emission — and the coverage gate that exists to catch exactly this cannot see it

**Mechanism.** `TEMPER_NET_CLASSES` (`core/design_rules.py:222`) declares
**11** net classes. `generate_kicad_dru.py`'s trace-width section iterates a
hand-maintained literal, `class_order` (`scripts/generate_kicad_dru.py:1012`),
listing **10**:

```
$ .venv/bin/python prove_dru_gap.py core/design_rules.py scripts/generate_kicad_dru.py
TEMPER_NET_CLASSES declares 11 classes:   ... HighVoltageIsolated
generate_kicad_dru.py class_order lists 10
>>> declared but NO trace-width rule emitted: ['HighVoltageIsolated']
>>> listed but not declared (would KeyError): []

HighVoltageIsolated declares: ['trace_width=2.0,', 'safety_category="HV",']
```

`HighVoltageIsolated` is the gate-drive floating bootstrap supply
(`+5V_ISO`, `VBOOT_H/L`), `safety_category="HV"`, declared `trace_width=2.0`
mm. It is the 11th and last entry — appended to the SSOT after `class_order`
was written. No `(rule "HighVoltageIsolated trace width" ...)` is ever
emitted, so DRC enforces nothing above the board default for it.

This is **live on every CI DRC run**, not a stale artifact:
`pcb/temper.kicad_dru` is gitignored and `ci_check_drc.py:94` regenerates it
from this generator before every kicad-cli measurement.

The neighbouring comment is the sharp detail. `class_order` carries a warning
added by the 2026-07-28 `GateDrive` split — "both halves must be listed **or
this loop KeyErrors**". The guard rail was written for the direction that
crashes loudly (a *removed* class) and not for the direction that fails
silently (an *added* one). `prove_dru_gap.py`'s second line confirms the
KeyError direction is clean today; only the silent direction is broken.

**Why no gate caught it.** `check_hv_netclass_coverage.py` exists to catch
class-list drift — its own motivating incident was that same `GateDrive`
split. But its coverage test is "≥1 positive rule of *any* kind":

```python
def positively_referenced_classes(dru_content) -> set[str]:   # :267
    return set(_NETCLASS_EQ_RE.findall(dru_content))
def check_netclass_rule_coverage(declared, kicad_class_name_fn, referenced):
    return sorted(k for k in declared if kicad_class_name_fn(k) not in referenced)
```

Fed a DRU with `HighVoltageIsolated` clearance rules (which the generator
*does* emit, rules 4a/4b) but zero trace-width rules, the **real** functions
report full coverage:

```
$ .venv/bin/python prove_coverage_blind.py scripts/check_hv_netclass_coverage.py
DRU under test contains, for HighVoltageIsolated:
   clearance rules : YES (2)
   trace-width rule: NO  (0)   <-- the guarded thing is BROKEN
positively_referenced_classes() -> ['ACMains', 'HighVoltageIsolated']
check_netclass_rule_coverage()  -> missing = []
VERDICT: gate reports FULL COVERAGE.
```

`HighVoltageIsolated` is "covered" by its clearance rules, so its empty
trace-width category is invisible. The blindness is symmetric and not
specific to trace width: three classes (`FinePitch`, `Signal`,
`HighCurrent`) are positively referenced *only* by loop-emitted trace-width
rules, so an omitted **clearance** rule for one of them would pass the same
way.

**Consequence, stated honestly.** The missing constraint is *ampacity*, not
isolation — `HighVoltageIsolated`'s clearance and creepage rules are emitted
correctly, and the class carries low current, so the direct physical risk is
moderate rather than severe. The finding that matters is the second one: a
gate named "netclass **coverage**" that measures rule *existence* would hide
an omitted clearance rule just as completely.

**One-line fix** (not applied): iterate `TEMPER_NET_CLASSES` instead of
`class_order`; separately, make coverage per-constraint-category.

---

### 10. `metrics-trend-check.yml` — the drift branch is unreachable shell, and the two checks after it call subcommands that do not exist

**Claims:** a weekly job that detects pipeline-metrics drift and files a
GitHub issue. Schedule-only; not in `required_contexts`, so no merge is
blocked — consequence is bounded to "the alerting never fires."

**Defect A — `$?` after `|| true` is always 0** (`metrics-trend-check.yml:57-60`):

```bash
result=$(uv run python scripts/pipeline_metrics.py trend ... --json 2>&1) || true
exit_code=$?
if [ "$exit_code" = "1" ]; then DRIFT_FOUND=true; ...
```

`cmd || true` always terminates 0, so `exit_code` is unconditionally 0 and
the `DRIFT_FOUND` branch is dead code. The exit code is the only drift
channel: `cmd_trend` returns `1 if result.get("has_regression") else 0`
(`pipeline_metrics.py:138`).

Driving the **real** `_compute_trends` with a genuinely drifted series, then
running it under the workflow's own idiom:

```
### Baseline: what the detector actually reports
  wall_clock_seconds: latest=500.0 mean=136.77 drift=3.0151s status=REGRESSION
  has_regression = True
detector standalone exit = 1  (1 == REGRESSION detected)

### Now under the workflow's idiom (metrics-trend-check.yml:57-60)
captured exit_code = 0
drift_found=false   <-- this is what feeds $GITHUB_OUTPUT

### Consequence
'Create drift issue' guard: if: steps.trend.outputs.drift_found == 'true'
=> drift issue is NEVER filed, despite a real 3.0-sigma REGRESSION
```

The contrast is in the same file: the **next** step (`Run SPC check`, line 76)
uses the correct idiom, `|| SPC_EXIT=$?`, which does capture the status. One
step gets it right and the one above it does not. Introduced 2026-06-22
(`b42d15391`) — dead for 50 days.

**Defect B — `spc` and `slo` subcommands were never implemented:**

```
$ .venv/bin/python scripts/pipeline_metrics.py spc --board temper --window 20 --json
usage: pipeline_metrics [-h] {trend,record} ...
pipeline_metrics: error: argument command: invalid choice: 'spc' (choose from 'trend', 'record')
EXIT: 2
```

The step captures that usage error into `spc-result.json` and `json.load()`s
it, which raises under Actions' default `bash -e`. `spc_rules.py` and
`slo_evaluator.py` are real, unit-tested libraries reachable only from their
own tests. Because "Run SPC check" is ordered **before** "Create drift
issue", this aborts the job first — so the drift issue is unreachable by two
independent defects at once, and the SPC/SLO alerting has never run.

---

### 11. Two real safety gates are not in `required_contexts` — a second gap, beyond the one AGENTS.md documents

This **corrects a claim made earlier in this document's first pass** (see
"What the audit did not find", now amended). `required_contexts` contains 8
entries, all jobs of `python-tests.yml`. Two non-`python-tests.yml` jobs are
genuine hard gates that are neither `continue-on-error`-masked nor
trunk/nightly-only:

| Workflow | Job / check name | Triggers | Masked? | In `required_contexts`? |
|---|---|---|---|---|
| `erc-gate.yml:44` | `ERC ratchet (kicad-cli sch erc)` | `push: main` **and** `pull_request` | no | **no** |
| `firmware-tests.yml:37` | `test` (job id, no `name:`) | `push`/`pull_request` on `firmware/**`, `pcb/**` | no | **no** |

`erc-gate.yml`'s own header describes it as closing a real gap — "runs ERC on
both schematics on every push/PR that touches them and **hard-fails on any
ERC error**" — and its single step carries the comment "No `continue-on-error`
here, and none should be added: a gate that cannot run must exit non-zero."
It is a real electrical-rules gate on a mains board whose red run does not
block a merge. `firmware-tests.yml`'s `test` job likewise carries the
state-machine reachability (R28), invariant proofs (R29), transition-table
mutation sweep and SIL fault-injection coverage.

This is the same class as the `Board, Provenance & Requirements Gates` gap
AGENTS.md already documents — a gate that runs, reports red, and still does
not block — but these two are not recorded anywhere. Whether to add them is a
maintainer call (it changes what blocks every PR), which is precisely why
AGENTS.md leaves the known one unapplied too.

---

### 12. `scripts/manifest.yaml`'s `disposition: ci-gate` is read by nothing — the mechanism behind findings 4, 5 and 7

Findings 4, 5 and 7 each report a script labelled `ci-gate` that no workflow
runs. That is not three coincidences; it is one missing check:

```
$ grep -rn "ci-gate" --include=*.py --include=*.yml --include=*.yaml . | grep -v scripts/manifest.yaml
docs/wave4-verdicts.yaml:672  (prose)
scripts/tests/test_trace_invocations_manifest.py:38  (a fixture literal)
```

No code reads the field. `check_manifest_gate.py` validates that an entry
*exists* and `check_script_sunset.py` ages `last_run`, but nothing asserts
that a script claiming to be a CI gate is reachable from CI. A deliberately
generous reachability scan — counting a script as wired if its name appears
in any workflow, the `Makefile`, `conftest.py`, `pyproject.toml`, or if a
`scripts/tests/test_<name>.py` exists under the pytest sweep — still leaves:

```
declared ci-gate : 86
  reachable from CI: 79
  NOT reachable    : 7
bmc_adoption_gate.py, check_ceiling_raise_evidence_corpus.py,
check_component_defect_corpus.py, check_corpus_specificity.py,
gen_pcb_skeleton.py, update_regression_cache.py, verify_proofs.py
```

(The first pass's stricter scan, which also counts scripts present only
inside commented-out workflow blocks, put the figure at 11/86 — 12.8%. Both
counts are lower bounds on the same defect; the 7 above survive the most
generous reading.) Two of the seven — `gen_pcb_skeleton.py` and
`update_regression_cache.py` — look like generators mislabelled as gates, a
manifest error rather than a missing gate. The rest are findings 4 and 5 and
the three already-documented corpus runners.

**One-line fix** (not applied): a check that every `disposition: ci-gate`
entry appears in a live workflow step — which would have failed the moment
each of these went dark, instead of an audit finding them one at a time.

---

### 13. `quarantine_report.py` in `regression.yml` — reports on a manifest nothing in that workflow writes

`regression.yml:214` runs a "Quarantine Report" step after the round-trip,
metamorphic-oracle, CP-SAT and zone-pour tests. The only writer of
`power_pcb_dataset/quarantine/manifest.json` is `batch_pipeline_validate.py`
(via `temper_placer.testing.quarantine`), which runs **only** in the weekly
`corpus-batch.yml`. None of `regression.yml`'s own steps write it:

```
$ ls power_pcb_dataset/quarantine/
baseline.json                       # no manifest.json
$ .venv/bin/python scripts/quarantine_report.py
Quarantine entries: 0

Quarantine empty — no entries.
EXIT: 0
```

`corpus-batch.yml` already carries an in-file comment conceding this shape
for its own usage ("has never had anything to fail on"); the identical step
in `regression.yml` is undocumented. Low consequence — it is a reporter, not
a gate — but it reads as quarantine coverage that does not exist.

---

### 14. `drc_clearance_pass_pct` cannot distinguish "DRC ran clean" from "DRC never ran" — VACUOUS (board safety)

`packages/temper-placer/src/temper_placer/regression/closure_test.py:372-393`
initializes `drc_errors = 0` before Step 4 and puts `stages_exercised += 1`
*inside* the `try`. Every DRC failure path — kicad-cli missing (`ImportError`),
crash, timeout (`except Exception`) — is caught and logged as a **warning**
without ever touching `drc_errors`. Four stages already increment before DRC
(lines 261, 281, 330, 358), so `stages_exercised` reaches 4 regardless.

The scoring rule in `measure_closure.py:106` then reads
`compute_drc_clearance_pass_pct(stages_exercised, drc_errors)`, whose first
branch is `100.0 if stages_exercised >= 4 and drc_errors == 0`.

**Proof**, against the real compiled kernel:

```
$ .venv/bin/python -c "import temper_design_bundle_python as t; f=t.compute_drc_clearance_pass_pct
print('DRC ran clean  (4,0):', f(4,0)); print('DRC never ran  (4,0):', f(4,0)); print('1 real error   (4,1):', f(4,1))"
DRC ran clean  (4,0): 100.0
DRC never ran  (4,0): 100.0     <-- indistinguishable
1 real error   (4,1): 90.0
```

A DRC step that never executed scores a **perfect** 100.0 — identical to one
that ran and found zero violations. The consumer,
`tests/closure/test_router_completion.py:270`, guards only
`assert candidate.drc_clearance_pass_pct > 0.0`, which 100.0 sails through;
and the committed baseline fixture (`tests/closure/fixtures/baseline_closure.json`)
itself records `100.0`, so the companion `>= baseline` comparison is trivially
satisfied by "DRC didn't run" too.

This is the closure-pipeline mirror of the anti-pattern `runner.py` was
explicitly hardened against
(`docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`:
*"falling back to a fabricated 0 would always pass… turning a genuine ratchet
into a vacuous one"*) — except here the fabricated value is a *perfect* score
rather than 0, which is strictly worse: it also satisfies every `>=` comparison
downstream.

**One-line fix:** initialize `drc_errors = None` and treat `None` as a hard
failure of the closure measurement rather than as zero errors.

---

---

### 15. `check_vacuous_gates.py` misses the negated form of the idiom it exists to catch — MISCALIBRATED (meta)

`AGGREGATORS = {"all"}` (`scripts/check_vacuous_gates.py:236`). The docstring
deliberately and *correctly* excludes bare `any()`: over an empty collection it
returns `False`, which is already fail-closed. **But `not any(...)` inverts that
to `True` — fail-open — and is semantically identical to an unguarded
`all()`.** The docstring's justification does not cover the negated form, and
the detector does not look for it.

Nine live sites, in the exact validator files the gate's own docstring names as
in-scope:

```
$ grep -n "not any(" packages/temper-placer/tests/requirements/validators/{isolation,emi_filter}.py
isolation.py:442:   passed = not any(v.severity == "error" for v in violations)
emi_filter.py:201:  passed = not any(v.severity == "error" for v in violations)
   ... (7 more in emi_filter.py: 236, 314, 386, 485, 543, 612, 666)
```

Called with empty inputs, these report a clean pass having measured nothing:

```
check_filter_component_order({})       -> passed=True, violations=[]
check_filter_signal_flow({}, (0,0))    -> passed=True, violations=[]
check_power_domain_separation({}, [])  -> passed=True, violations=[]
```

A full run of the gate never mentions either file:

```
$ .venv/bin/python scripts/check_vacuous_gates.py > /tmp/vg.txt; echo "EXIT=$?"
EXIT=1
$ grep -c "isolation.py\|emi_filter.py" /tmp/vg.txt
0
```

**Second, independent gap in the same script:** `_preceding_guard` matches
`assert len(EXPR)` as a bare textual substring regardless of the comparison
that follows, so `assert len(results) == len(MUTATIONS)` — true when both are 0
— is accepted as a non-emptiness guard. Neither gap has a test in
`scripts/tests/test_check_vacuous_gates.py`.

This is the recursive gap
`docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md` predicted in its own
Coverage section: *"worth noting `check_vacuous_gates.py` exists and its own
vacuity was not checked here, which would be a fittingly recursive gap to close
next."*

**One-line fix:** extend the detector to `UnaryOp(Not, Call(any, ...))`, and
require the `len()` guard's comparison to be against a literal rather than
another `len()`.

---

---

### 16. `should_skip()`'s source fingerprint hashes a deleted directory and is blind to the crate holding the real constraint logic — MISCALIBRATED

`packages/temper-placer/src/temper_placer/regression/fingerprint.py:44`:

```python
SOURCE_FINGERPRINT_DIRS = ["packages/temper-placer/src", "packages/temper-drc/src"]
```

`packages/temper-drc` does not exist — it was removed in `f438ca0e4`
("remove deprecated temper-drc package"); only `temper-drc-rs`, a different
package, remains. `compute_source_fingerprint` silently `continue`s past
missing directories, so in practice only `temper-placer/src`'s 469 `.py` files
are hashed.

Meanwhile `packages/temper-placer/temper-constraints/src/*.rs` — the CP-SAT
loss/constraint crate imported by `cp_sat/model.py`, `domain_clearance.py`,
`gates.py`, `handlers/keepout.py`, `core/design_rules.py`, and
`router_v6/_zone_pour_stitch.py` — is covered by **neither** the directory list
**nor** the `*.py` glob. A change to the placer's actual constraint/loss logic
therefore leaves `source_fingerprint` byte-identical, so `--skip-unchanged`
(consumed by `corpus_runner.py`) serves a stale cached "pass" for a board whose
constraint behavior genuinely changed.

Same mechanism as §9's empty-scan-set family, one level up: the scan set did
not go to zero, it went *stale* — one entry pointing at a deleted tree, and the
language the logic migrated *to* excluded by the glob.

---

---

### 17. `phase5_hubs_mutations.py` always exits 0 regardless of catch rate — VACUOUS

`main()`'s only non-zero return path is an infrastructure check ("suites still
failing after reverting every mutation", lines 198-201), unrelated to mutation
outcomes. The per-mutation `caught` / `SURVIVED` / `UNEXPECTED` classification
is computed and printed (lines 187-206) but never gates the return value —
line 207 is an unconditional `return 0`, reached even when all 11 mutations
SURVIVED or every verdict was UNEXPECTED. Checking `echo $?`, the natural way
to consume it, always reports success.

Its sibling `phase5_cli_adapters_workflow_mutations.py:200-210` has a related
but distinct defect, and is the file that demonstrates finding 15's second gap:

```python
assert len(results) == len(MUTATIONS), (...)   # true even when both == 0
return 0 if all(k for _, k, _ in results) else 1   # vacuously True over empty results
```

The comment above it explicitly cites `check_vacuous_gates.py` as the reason
the guard is there. The guard does not work, and the linter it cites cannot see
that it does not work. Not currently exploited — `MUTATIONS` has 11 real
entries — but broken by construction. **(MISCALIBRATED)**

---

---

### 18. `check_script_sunset.py`'s `has_caller` signal is provably stale — MISCALIBRATED

The script's own exit-code discipline is honest (`sys.exit(0)` always,
warnings-only, documented). The defect is upstream: `has_caller` comes from
`scripts/invocation_graph.json`, built by a static regex scan
(`trace_invocations.py`'s `SCRIPT_RE`) that does **not** cover `scripts/*.py` or
`scripts/tests/*.py`, despite the module docstring claiming otherwise.

```
$ python3 -c "import json; print(json.load(open('scripts/invocation_graph.json'))['check_netlist_stage_checks.py'])"
[]
```

— zero callers recorded for a script wired into `python-tests.yml` and gating
every PR. The graph was last committed 2026-08-07 15:49; that wiring landed at
16:10 the same day (`9c8a7aae`). `trace_invocations.py` does re-run in CI, but
only on `push`, and **`check_script_sunset.py` runs at `python-tests.yml:2296`,
before the rebuild step at line 2337** — so even the CI run reads the stale
committed file, which is never committed back.

`--update-manifest` is invoked nowhere in any workflow, so `last_run` across all
142 manifest entries is a hand-typed field, never verified against real
invocation. `check_netlist_stage_checks.py` will misfire a false "verify it is
still needed" warning on 2026-09-06.

---

---

### 19. Two hardcoded-filter gates, same shape as the R27 bug — MISCALIBRATED

**(a) `check_workflow_pr_triggers.py:102` globs `*.yml` only.** GitHub Actions
fully supports `.yaml`. Proven on a scratch directory: a push-only,
no-PR-trigger, no-opt-out workflow named `rogue.yaml` — exactly the issue-#315
failure mode this gate exists to catch — yields

```
Workflow PR trigger check passed — 0 file(s) checked, all compliant
```

Latent only because every file in `.github/workflows/` happens to use `.yml`
today. *Fix:* `glob("*.yml")` → `glob("*.y*ml")`. (Separately: unparseable
workflow files are excluded from the compliance count with only a stderr
warning.)

**(b) `check_wire_format_fidelity.py`'s `OWN_COPY` regex** hardcodes three
function names (`pin_world_position|world_radius|pad_world_position`) to decide
which Rust files are scanned at all.
`packages/temper-geometry/src/pad_geometry.rs::bounding_radius` matches the
gate's own documented trigger (`bounding_radius|pad_bounding`) and takes `shape`
and `ratio` as explicit parameters — but is never scanned, because its *name*
is not one of the three. Not a live false-pass (that file already references
`roundrect_ratio`/`shape`), but the detection mechanism is a name allowlist with
the same structural weakness as the R27 category allowlist, and would silently
skip any newly-named radius-reimplementing kernel.

---

---

### 20. `check_component_defect_corpus.py` — MISNAMED disposition

`scripts/manifest.yaml:2181` declares `disposition: ci-gate`;
`grep -rn "check_component_defect_corpus" .github/workflows/` returns nothing.
Internal logic is sound (independent re-parse self-verification, real-gate
invocation, an anti-vacuity clean-fixture control). Independently corroborated
the same day in
`docs/evidence/2026-08-11-phase3-mutation-state-of-play.md:108`. Same class as
findings 4, 5, 7 and 12 — listed for completeness of the count.

Also in this class, proven but low-severity: **`check_board_containment.py`'s
Rust-bundle bypass catches only `ImportError`**, while a stale build raises
`AttributeError` (via `temper_placer/__init__.py`), so the documented fallback
never fires under the exact failure it was written for. Reproduced live. **Not**
a false pass — the script still exits non-zero — so this is robustness, not
safety.

---

### 21. Finding 11, widened: five workflows are unrequired, not two — and the documented gap's blast radius is larger than AGENTS.md states

Finding 11 above cross-referenced `required_contexts` against `erc-gate.yml`
and `firmware-tests.yml`. Extending the same check to **all 31** workflow
files finds three more of the same shape. None of the five is
`continue-on-error`-masked; all five trigger on `pull_request` against `main`
with hard-failing steps (verified by reading each file's `on:` block):

| Workflow | `name:` | Guards |
|---|---|---|
| `regression.yml` | `Regression Suite` | the live kicad-cli DRC-vs-ceiling truth gate |
| `erc-gate.yml` | `ERC Gate` | `ci_check_erc.py` on mains schematics (finding 11) |
| `golden-check.yml` | `Golden Regression Check` | the golden-board regression |
| `placer-regression.yml` | `Placer Regression` | corpus baseline changes without `Ceiling-Approval:` |
| `firmware-tests.yml` | `Firmware Tests` | R29 invariant proofs, R28 exhaustive state-machine reachability, fault-list consistency (finding 11) |

Two details sharpen this.

**(a) `scripts/ci_check_drc.py` runs in exactly one place repo-wide** — and it
is not the job most readers would assume:

```
$ grep -rn "ci_check_drc.py" .github/workflows/
.github/workflows/regression.yml:190:  run: uv run python scripts/ci_check_drc.py --backend kicad-cli
   (plus two path-trigger lines in the same file)
```

It is **not** in `python-tests.yml`'s `board-provenance-requirements-gates`
job, which runs only the provenance/trailer bookkeeping
(`check_measurement_provenance.py`, `check_drc_ceiling_approval.py`). So the
one CI step that actually re-runs kicad-cli DRC and compares it against
`drc_ceiling.json` — the ratchet AGENTS.md describes at length, and the
subject of two of today's seven — has no path to blocking a merge.
`regression.yml:49-51` says so itself: *"'Regression Suite' is not in
`.github/required-checks.json`'s `required_contexts`, so neither copy can
block a merge."*

**(b) The `Board, Provenance & Requirements Gates` gap AGENTS.md documents has
a materially larger blast radius than AGENTS.md states.** AGENTS.md records
that job's exclusion in the context of the DRC-ceiling and
measurement-provenance checks. But *every* invocation of
`check_isolation_keepout.py` (whose docstring calls the mains↔SELV barrier
"the single most safety-critical property of this board's layout"),
`check_domain_partition.py` (galvanic-isolation graph reachability),
`check_hv_netclass_coverage.py`, `check_copper_net_consistency.py`,
`check_pad_orientation.py` (intra-component copper shorts) and
`check_board_containment.py` — both the live-board run *and* its unit tests —
falls inside that same job (`python-tests.yml` lines 1174–1767) and nowhere
else. A PR that shorted the isolation barrier, corrupted a net ordinal, or
reintroduced the rotated-pad-body short would show a red ❌ and remain
mergeable.

Of the five, `firmware-tests.yml` is arguably the sharpest: exhaustive
reachability proofs for the ESP32-S3 state machine controlling a mains
induction cooker, written explicitly as hard gates ("No continue-on-error"),
with no path to blocking a merge.

**Fix** (a maintainer call, not applied here — it changes what blocks every
PR): add the relevant contexts to `required_contexts`. Read lead 9 first:
`regression.yml` and `placer-regression.yml` both post a check run named
`regression`, so adding that bare string without first giving each job a
distinguishing `name:` would let the aggregator observe the wrong workflow's
verdict.

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
7. **`physics_oracle.py`'s thresholds are invisible to the provenance gate.**
   `_CLEARANCE_PASS_THRESHOLD = 0.95` — the pass/fail threshold for the HV/LV
   clearance score on a mains board — carries no `# source:` citation, and
   `check_physics_provenance.py` defaults to `temper_placer/physics/`, a
   sibling directory that does not include `regression/`. Its AST scan only
   walks `physics_dir.rglob("*.py")`, so this constant and the function-default
   thresholds (`max_heatspread_mm=10.0`, `hv_lv_threshold_mm=6.5`,
   `max_loop_area_mm2=100.0`) are structurally invisible to the one gate meant
   to catch exactly this. Separately, `score_placement()` hardcodes
   `min_clearance=8.0` where `run_physics_oracle()` uses the spec-derived 6.5mm.
   **Why only a lead:** no live caller of `score_placement` was found, so the
   impact of the inconsistency is unconfirmed.
8. **`check_required_checks.py`'s static lint covers only 7 of the 8 required
   contexts.** `validate_job_conditions` cross-checks only contexts that have
   `job_triggers` entries, so `Fast Gates` (unconditional, no entry) and
   `PR Performance Comparison` (owned by `pr-perf-check.yml`, reached via
   `context_triggers`) are never verified to correspond to a real job `name:`.
   Both match today (`python-tests.yml:3739`, `pr-perf-check.yml:84`). **Why
   only a lead, and why it is mild:** the *runtime* path is sound — a missing
   context is treated as neither passed nor skipped, and the poll loop fails
   closed after ~2h45m rather than passing by omission — so a future silent
   rename produces a stalled-then-red PR, not a false green.
9. **Job-name collision between `regression.yml` and `placer-regression.yml`.**
   Both declare a job keyed `regression:` with no job-level `name:`
   (`regression.yml:85`, `placer-regression.yml:35`), so both post a check run
   named `regression` on the same commit. `check_required_checks.py:526-536`
   dedups purely by `run.name`, taking whichever has the later
   `(updated_at, run_id)`, with no per-workflow discriminator. Inert today —
   neither is required — but this is a live hazard for the finding-21 fix: adding the
   bare string `"regression"` to `required_contexts` without first giving each
   job a distinguishing `name:` would let the aggregator observe the wrong
   workflow's verdict.

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

- ~~**No second `required_contexts` gap.**~~ **AMENDED by finding 11 — this
  claim was wrong.** The first pass cross-checked the 8 required contexts
  against every `name:` in `python-tests.yml` and `pr-perf-check.yml` and
  concluded that every unlisted job was either `continue-on-error`-masked or
  trunk/nightly-only. That conclusion held only *within the two workflows
  checked*. Extending the cross-reference to all 31 workflow files finds two
  unmasked, PR-triggered hard gates outside them — `erc-gate.yml`'s ERC
  ratchet and `firmware-tests.yml`'s `test` job — neither masked, neither
  nightly-only, neither required. **Finding 21 widens this again: it is five
  workflows, not two** — `Regression Suite`, `Golden Regression Check` and
  `Placer Regression` are in the same position, and the `Regression Suite`
  one carries the repo's only invocation of `scripts/ci_check_drc.py`. The
  original claim is left visible rather than deleted: a scope-limited check
  reported as a general negative is the same failure mode this document is
  about, and it happened here — twice, at two different scopes.
- ~~**No exit-code swallowing in workflow steps.**~~ **AMENDED by finding 10
  — also wrong, for the same reason.** All 70 `continue-on-error` sites were
  enumerated and each is genuinely advisory, which is true and worth keeping.
  But the accompanying "no `|| true`, no `set +e`" claim was not verified
  across all workflows: `metrics-trend-check.yml:58` contains exactly the
  `|| true` construct the sentence denies, and it makes that step's drift
  detection unreachable. What survives is the narrower, verified statement:
  **no `continue-on-error` site masks a gate that was meant to block.**
- ~~**No vacuity in the mutation-testing machinery itself.**~~ **AMENDED —
  the third and last of the first pass's reassuring claims to fall, and the
  most consequential.** What survives is narrower but still real: the two
  *corpus* runners below are genuinely sound, and were exercised rather than
  read. What does not survive is the generalization to the whole layer.
  Findings 8, 15 and 17 each break it: `constraint_mutation_gate.py` — a
  **required, merge-blocking** check — passes unchanged on an encoder whose
  entire enforcement body has been deleted (finding 8, proven by gutting it);
  `phase5_hubs_mutations.py` returns 0 whether its mutations were caught or
  survived (finding 17); and `check_vacuous_gates.py`, the repo's own
  anti-vacuity linter, cannot see the negated form of the idiom it exists to
  catch (finding 15). This was indeed "the layer worth worrying about most" —
  the first pass's instinct was right and only its conclusion was wrong. The
  sound parts, verified:

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

Added by the second pass (findings 8–21):

- **11** `temper_placer/regression/` modules the first pass counted in bulk
  but did not enumerate individually: `cli`, `closure_test`,
  `cp_sat_comparison`, `fingerprint`, `manifest`, `measure_closure`,
  `metrics_recorder`, `physics_oracle`, `reporter`, `runner`,
  `schema_validator`. These 11 are what takes the total from 83 to **94**;
  everything else the second pass touched was already inside the first
  pass's 83, re-audited at greater depth rather than added.
- The workflow-wiring unit was **re-run against all 31 workflow files**
  rather than two, which is what produced findings 11 and 21.
- A systematic `scripts/manifest.yaml` sweep: every entry marked
  `disposition: ci-gate` was matched against uncommented workflow and
  Makefile lines (finding 12's 11-of-86 figure).

Depth was not uniform. Roughly two-thirds were read end-to-end or executed;
the remainder were read for decision logic and CI wiring, with targeted
greps for the specific anti-patterns in today's seven (swallowed exception,
single-hardcoded-category, always-empty input, default-on-error return). A
gate marked SOUND here means "no instance of this failure class found,"
not "formally verified."

The seven already-confirmed instances from 2026-08-11 were excluded from
the audit set and are not counted in the 94. `scripts/check_unwired_kernels.py`
(#1020) was likewise excluded as already documented.

**Not reached, stated plainly:** the ~12 lower-priority `routing/` Rust rules
that `docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md` also left
unreached; `router_v6/constraints_drc_oracle.py`'s internal
`INTERNAL_LAYER_CREEPAGE_FACTOR` creepage model; the
`requirements/validators/` Python modules beyond the nine `not any(...)` sites
named in finding 15; and `firmware/` C-level test helpers. The
`check_unwired_kernels.py` false-positive rate was not re-measured.
