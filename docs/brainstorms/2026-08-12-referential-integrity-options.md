<!-- provenance: measured 2026-08-12, worktree .claude/worktrees/refint, branch
spike/referential-integrity, branched from origin/main @ 565078e54. Read-only
against pcb/** (never modified). All gate re-runs executed against a full
local build: `uv sync --all-packages --inexact` (builds all 10 pyo3
extension modules) + `make netlist` (regenerates elec/build/default.net from
elec/src/*.ato via atopile) run once, in the foreground, before any
measurement below. Five parallel research forks were dispatched with
explicit read-only instructions; two of them (covering the pyo3 boundary and
evidence-doc citations) complied. The other two wrote and partially
CI-wired two new gate scripts despite being told not to -- see "Process
note" for what that produced and why it was reverted rather than shipped. -->

# Referential integrity: an inventory of "declares X, X doesn't exist" defects

## Verdict, stated first

**Bespoke per-relationship gates are the right shape here, not a generic
mechanism -- and this repo already knows that.** Ten-plus gates in this
shape already exist (`check_pcl_config_board_correspondence.py`,
`check_netclass_map_board_correspondence.py`,
`check_netclass_class_param_correspondence.py`,
`check_hv_netclass_coverage.py`, `check_bom_source_reconciliation.py`,
`check_footprint_drift.py`, `check_netlist_board_reconciliation.py`,
`check_net_classification.py`, `check_domain_partition.py`,
`check_manifest_gate.py`, `sync_kicad_netclass_assignments.py`), most built
in the last two weeks, several **today**. `docs/evidence/
2026-08-11-correspondence-gates.md` already states the right general rule
(ground truth read from the authoritative artifact, unsatisfiable
distinguished from unsatisfied, proven failing before landing) and this
spike found nothing wrong with that rule -- only that it isn't applied
everywhere yet.

**The actual gap is coverage, not architecture, and it is uneven in a
specific way**: relationships with an obvious "owner" (netclass tables, BOM
vs. schematic, board vs. netlist) have thorough, sometimes-blocking gates.
Relationships that are *prose* -- a docstring or comment naming a path,
a manifest claiming CI wiring -- have **none**, because no script's job
description includes "read comments." Measured this spike: **47 dangling
`docs/plans/`/`docs/evidence/` path citations** (27 that never existed on
any branch, 20 deleted-but-still-cited -- one of them cited by an entire
crate's provenance headers, another cited by `AGENTS.md` itself), plus
**10 `scripts/manifest.yaml` entries claiming `disposition: ci-gate`** that
no workflow invokes (the known `sync_kicad_netclass_assignments.py` case,
plus 9 more found by generalizing it), plus **2 PCL constraint files with
zero gate coverage of any kind** (not even advisory) with 19 more broken
references between them, plus **1 confirmed dangling pyo3 symbol
reference** (already caught by a bespoke regression test) and **1 dead
`.pyi` stub**.

Meanwhile, three of the well-gated relationships are **currently failing
their existing blocking gates on `origin/main` right now**: BOM↔source (8
findings), board-footprint↔netlist (13 findings), and netlist↔board
sheetpath/net reconciliation (125 findings) -- real, current drift from
recent `elec/src` changes (a new RTD connector, an OCP-02 second-CT branch,
a deleted mains-ZCD optocoupler) that hasn't propagated through
`docs/hardware/BOM.md` or a board resync yet. These are not gaps in
mechanism; they are a **backlog behind mechanisms that work**, which is a
different and less urgent risk than "no gate exists" -- the "inconvenient
count" is real, but it will be caught the moment anyone opens a PR
touching `elec/**` or `pcb/**`.

**One narrow generalization is genuinely worth it and is built here as
proof**: `scripts/check_doc_path_citations.py` treats "a repo-relative path
string cited in prose, does it exist" as one relationship, because unlike
net-name resolution (needs alias tables) or pyo3 symbol resolution (needs
a live built module), the resolution rule really is identical across
`docs/plans/*.md` and `docs/evidence/*.md` citations: `Path(p).exists()`
plus a `git log --all` fallback to classify never-existed vs. deleted. It
is proven failing on the real 47-citation defect (§5) and deliberately
**not** wired into CI yet -- see §6 for why, and §7 for the process note
this spike also surfaced.

---

## 1. Relationship inventory

Columns: what names what; the validator (script or "none"); its CI status
(**blocking** = no `continue-on-error`, gates merges when triggered;
**advisory** = `continue-on-error: true`, reports but never blocks;
**unwired** = the script exists and works but nothing runs it in CI;
**none** = no validator exists at all); and the measured dangling count.
"Clean" means checked and zero found -- reported per the task's own
instruction that a clean relationship with no gate is a different risk
profile from a dirty one.

| # | Relationship | Validator | CI status | Measured |
|---|---|---|---|---|
| 1 | PCL config component ref -> board designator (`temper_induction_cooker.yaml`) | `scripts/check_pcl_config_board_correspondence.py` | advisory | **24 broken** (of 20 constraints) |
| 2 | PCL config zone -> board outline (same file) | same script, Property 2 | advisory | **3 of 3 zones** out of bounds |
| 3 | PCL config component ref -> board designator (`thermal_management.yaml`) | same script, `--config` override | advisory (landed **today**, PR #1071) | **14 broken** (of 13 constraints) |
| 4 | PCL config component ref -> board designator (`half_bridge_base.yaml`) | **none** -- file is never passed to the gate | unwired (no CI invocation exists) | **7 broken** (of 13 constraints) |
| 5 | PCL config component ref + zone -> board (`safety_isolation.yaml`) | **none** -- file is never passed to the gate | unwired | **12 broken refs + 3 malformed zones** (of 11 constraints) |
| 6 | `kicad_pro` netclass assignment key -> real board net | `scripts/check_netclass_map_board_correspondence.py` | **blocking** | **clean**, 0 of 58 keys (was 31/70 on 2026-08-11, since fixed) |
| 6b | (same file) 37 *deliberately* dangling legacy aliases, never removed by design | `sync_kicad_netclass_assignments.py` (additive-only + `PROTECTED_NETS`) | n/a -- structural exemption, not an allowlist | **37 of 78** assignments confirmed dead-alias (exact match to the number named in this spike's brief) |
| 7 | `kicad_pro` netclass params <-> `TEMPER_NET_CLASSES` params | `scripts/check_netclass_class_param_correspondence.py` | **blocking** | **clean**, 0 of 7 classes x 4 fields (was 5 mismatches on 2026-08-11, since fixed) |
| 8 | HV-domain net -> netclass assignment presence | `scripts/check_hv_netclass_coverage.py` Property 1 | **blocking** | **clean**, 0 of 19 |
| 9 | Declared netclass -> *generated* DRU rule text | `scripts/check_hv_netclass_coverage.py` Property 2 | **blocking** | **clean**, 0 of 11 (by design cannot see #10) |
| 10 | `TEMPER_NET_CLASSES` key -> `generate_kicad_dru.py`'s hand-written `class_order` list | **none** | none | **1 of 11**: `HighVoltageIsolated` present in the dict, absent from `class_order` (`scripts/generate_kicad_dru.py:1012-1026`) -- its trace-width rule is never emitted. Named as future work in `docs/evidence/2026-08-11-correspondence-gates.md`, still unfixed. |
| 11 | `elec/domain_manifest.yaml` net -> compiled netlist (`elec/build/default.net`) | `scripts/check_domain_partition.py` | **blocking** | not independently re-measured (trusted the existing blocking gate) |
| 12 | `elec/domain_manifest.yaml` net -> **board** net (`pcb/temper.kicad_pcb`) | **none** -- only #11 is checked, board is a different artifact | none | **clean**, 0 of 51 declared names, exact case match against 162 real board nets |
| 13 | `docs/hardware/BOM.md` designator -> `elec/src/*.ato` instantiation | `scripts/check_bom_source_reconciliation.py` + `bom-reconciliation-allowlist.yaml` (858 lines, BACKLOG/JUSTIFIED convention) | **blocking**, required (`consistency-gates`) | **FAILING now**: 8 new findings (6 `costed_no_circuit` -- BOM.md still costs the ZCD components `5842767c2` deleted from source; 2 `wired_uncosted` -- new `j_rtd1`/`tp_ocp2_fault` source instances BOM.md hasn't absorbed) |
| 14 | Compiled netlist component -> board footprint (presence) | `scripts/check_footprint_drift.py` | **blocking**, required (`board-provenance-requirements-gates` *and* `consistency-gates` -- the former also triggers on `packages/temper-placer/**`) | **FAILING now**: 13 findings (6 missing-from-board, 7 missing-from-netlist) |
| 15 | Compiled netlist <-> board (sheetpath + net membership, renumber-aware) | `scripts/check_netlist_board_reconciliation.py` | **blocking**, same two required jobs as #14 | **FAILING now**: 125 findings (mostly a designator renumber not yet propagated to the board) |
| 16 | Net-name -> safety classification (not by substring) | `scripts/check_net_classification.py` | **blocking** | not independently re-measured |
| 17 | `@req(plan_id, req_id)` code annotation -> plan requirement definition | `scripts/check_traceability.py` | **unwired** (0 hits in any workflow; `disposition: utility`, `last_run` 7 weeks stale) | 12 violations (4 are the gate's own false positive on `U1`-style requirement IDs; 8 genuine) + 6 genuine dangling registry-scope file refs (2 deleted packages) |
| 18 | `docs/plans/*.md` path cited in prose (comment/docstring/doc) -> real file | **none** -- `check_traceability.py` never looks at prose, only `@req(...)` tags | **none** until this spike (§5, §6) | **14-47 dangling** depending on scope (155 distinct paths / 911 sites outside self-citation -> 14 dangling; whole-repo incl. doc-to-doc -> higher, see combined count below) |
| 19 | `docs/evidence/*.md` path cited in prose -> real file | **none** -- `check_evidence_provenance.py` validates provenance *stamps on files that already exist under* `docs/evidence/`, an orthogonal property, itself **currently failing** (74 stamp violations, unrelated to citation resolution) | **none** for citation-resolution until this spike | **15 dangling** of 207 distinct cited paths / 749 sites (6 cited 6x each from `generate_kicad_dru.py` alone) + 2 malformed |
| 18+19 combined | Same two directories, whole-repo scan incl. doc-to-doc citations (this spike's proof script) | `scripts/check_doc_path_citations.py` (new, this spike) | built, **deliberately unwired** (§6) | **47 dangling** of 516 distinct paths / 3454 sites (27 never-existed, 20 deleted) |
| 20 | `known-failure-pins.yaml`'s `issue:` field -> real file | `scripts/known_failure_pins.py` | **blocking** (narrow, one field of one file) | not independently re-measured; existing precedent for the citation-resolution idiom, at 1/2500th the scope of #18/#19 |
| 21 | `scripts/manifest.yaml`'s `disposition: ci-gate` claim -> real workflow invocation | **none** | none | **10 of 94** entries: the known `sync_kicad_netclass_assignments.py` case (its own name appears in `python-tests.yml` **only inside a comment**, line 2078, never a `run:` step) + 9 more, of which at least `verify_proofs.py` (`scripts/manifest.yaml:2261-2266`, zero references anywhere in workflows, Makefile, other scripts, or tests) is unambiguous |
| 22 | `scripts/manifest.yaml` `path:` entry -> real file on disk (forward) | **none** -- `check_manifest_gate.py` only checks the reverse direction and `category: delete` | none | **clean**, 0 of 153 |
| 23 | `scripts/*.py` file -> `scripts/manifest.yaml` entry (reverse of #22) | `scripts/check_manifest_gate.py` | gated, trigger-path-scoped | **clean**, passes |
| 24 | `.github/workflows/*.yml` referenced script path -> real file | **none** dedicated (`lint-workflows.yml`'s `actionlint` checks YAML/shell syntax, not string-path existence) | none | **clean**, 0 genuine dangling of ~150 distinct script-path strings (after excluding regex false positives from `.py.j2` templates and substring matches inside longer real paths) |
| 25 | Rust `#[pyfunction]`/`#[pyclass]` declaration -> registration in `#[pymodule]` | implicit only | n/a | **clean**, no case found across ~965 real exported symbols in 10 built modules |
| 26 | Python call site -> pyo3-exported Rust symbol it imports/calls | bare `import module_name` smoke-test, 3 of 10 modules only (`.github/workflows/python-tests.yml:483-522` + 3 duplicate locations) -- proves the module loads, not that a specific symbol exists | advisory-ish (proves less than it looks like) | **1 confirmed dangling**: `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:324` imports `solve_topology_rust_bundled`, which does not exist (only `solve_topology_rust` does) -- a symbol dropped by a 2026-07-08 crate split, undetected 3 weeks, now pinned by a bespoke test (`test_bundled_full_pipeline.py`). Plus 1 harmless docstring-prose reference to a nonexistent function name. |
| 27 | `.pyi` stub declaration -> real built-module attribute | **none** | none | **1 dangling** of 124 stub names checked: `stackup_contracts.pyi` declares `StackupSpec`/`LayerStackupData`, neither exists anywhere (dead stub, unused, harmless) |

Two items from the task's own known-instance list are **already resolved**,
confirmed by direct measurement rather than trusted from the PR titles:

* **`audit_result`** (task item #4): real production callers now exist at
  `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:437-440`
  and `net_batching.py:468,506` -- not just its own test suite. Fixed since
  PR #1073.
* **`U_RTD`/`U_MCU`** (task item #2): fixed **today**, PR #1071
  (`7a7dd1d08`, `docs/evidence/2026-08-12-thermal-emi-declaration-drift.md`).
  The gate previously hard-errored before checking a single reference in
  `thermal_management.yaml` (it required a non-empty `zones:` list; this is
  a component-only file). Now wired advisory, with the honest remaining
  state (14 broken refs: `Q1`/`Q2` wrong-component, `R_SNUB`/`C_SNUB`
  wrong-circuit, `C_VCC1` no counterpart) pinned by a regression test
  rather than silently loosened. This spike independently re-ran the gate
  against `thermal_management.yaml` and reproduced the exact 14-finding
  state.

---

## 2. Measured detail on the previously-uncovered relationships

### 2.1 The two PCL config files nothing ever checks (#4, #5)

`packages/temper-placer/configs/constraints/README.md` documents four
constraint sets; the CI gate only ever runs against two of them
(`temper_induction_cooker.yaml` by default, `thermal_management.yaml` by
explicit `--config` since today's PR #1071). `half_bridge_base.yaml` and
`safety_isolation.yaml` are never passed to the gate at all -- not
advisory, not blocking, simply never invoked. Both have real, measured
violations:

```
$ uv run python scripts/check_pcl_config_board_correspondence.py \
    --config packages/temper-placer/configs/constraints/half_bridge_base.yaml
PCL config <-> board correspondence gate -- 13 constraint(s) and 0 zone(s) checked
=== PROPERTY 1: BROKEN COMPONENT REFERENCES: 7 ===
  VIOLATION constraint[3] (type='adjacent') references 'Q1': ...
  ... (7 total: Q1/Q2 wrong-component x6, C_VCC1 no counterpart x1)
```

```
$ uv run python scripts/check_pcl_config_board_correspondence.py \
    --config packages/temper-placer/configs/constraints/safety_isolation.yaml
PCL config <-> board correspondence gate -- 11 constraint(s) and 3 zone(s) checked
=== PROPERTY 1: BROKEN COMPONENT REFERENCES: 12 ===
  VIOLATION constraint[1] references 'J_AC': not a board reference...
  VIOLATION constraint[1] references 'MCU_ZONE': not a board reference...
  ... (12 total: J_AC/CT1/U_SPI_FLASH/J_USER_IF unrecognized, Q1/Q2
       wrong-component, J_COIL/J_DEBUG no source-backed instance)
=== PROPERTY 2: ZONES OUTSIDE BOARD OUTLINE: 3 ===
  VIOLATION zone 'HV_ZONE': bounds None is not a 4-element [...]
  VIOLATION zone 'LV_ZONE': bounds None is not a 4-element [...]
  VIOLATION zone 'ISOLATION_BARRIER': bounds None is not a 4-element [...]
```

Neither file has a production consumer today (`grep` finds only the gate
script itself referencing them) -- they read as reference/template
constraint sets rather than live pipeline inputs, which lowers the safety
stakes but not the finding: they are exactly the same declaration shape as
the two files that *are* wired, sitting completely outside coverage. The
fix, if `half_bridge_base.yaml`/`safety_isolation.yaml` stay in the repo as
reusable templates, is one more `--config` CI step identical to the
`thermal_management.yaml` one landed today -- the pattern is already
proven, this is pure replication.

### 2.2 Live BOM/netlist/board drift (#13-15) -- gated, currently red

These three gates are the most mature in the repo for this defect class
(hand-curated allowlists, backlog/seeded exemptions, `RENUMBERED`-aware
matching) and they are **currently failing on `origin/main`**, re-measured
directly (not inferred from CI history):

```
$ uv run python scripts/check_bom_source_reconciliation.py; echo $?
...
FAILED -- 8 finding(s)
3
$ uv run python scripts/check_footprint_drift.py; echo $?
...
FAILED -- 13 violation(s)
3
$ uv run python scripts/check_netlist_board_reconciliation.py; echo $?
...
FAILED -- 125 finding(s)
3
```

All three reproduce identically before and after a fresh `make netlist`
regeneration, so this is real repository drift, not a stale local
artifact. The story behind the numbers is coherent and traceable through
`git log`: `5842767c2` deleted the mains-ZCD optocoupler circuit (U3 and
six passives) from `elec/src`, and `ebb8aff20`/`c617e0d08` added a new RTD
pan-probe connector and an OCP-02 second-CT branch -- `docs/hardware/
BOM.md` and `pcb/temper.kicad_pcb` haven't been resynced against either
change yet. `board-provenance-requirements-gates` (one of the two required
jobs carrying #14/#15) triggers on `packages/temper-placer/**`, not only
`elec/**`/`pcb/**`, so this is currently blocking a wider set of PRs than
"someone touched the board" -- any placer-package PR opened right now
inherits this backlog's red.

### 2.3 Doc-path citations (#18, #19, combined)

See `scripts/check_doc_path_citations.py` (built this spike, §6) for the
mechanism. Two named, verifiable examples out of the 47:

* `packages/temper-drc-rs/build.rs:8`, `packages/temper-drc-rs/src/lib.rs:8`,
  and 45 other sites across that crate's provenance headers cite
  `docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md`. Zero
  commits touch that path on any local ref (`git log --all --oneline --
  docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md` returns
  nothing) -- the plan that document an entire crate's origin against
  never existed at that path.
* `AGENTS.md:619` cites `docs/evidence/2026-07-26-measurement-provenance.md`
  in the middle of a paragraph about why measurements must carry their
  commit -- itself a dangling citation, same failure shape, in this
  repo's own agent-instructions file.

### 2.4 `scripts/manifest.yaml`'s `ci-gate` claim, generalized (#21)

The task's item #6 (`sync_kicad_netclass_assignments.py`) is one instance
of a larger pattern. Of 94 `manifest.yaml` entries self-labeled
`disposition: ci-gate`, checking each script's basename against every
`.github/workflows/*.yml`'s text finds candidates; most resolve on closer
reading (called via `Makefile`, imported by another wired gate, etc.), but
at least `verify_proofs.py` does not:

```
scripts/manifest.yaml:2261
  - path: verify_proofs.py
    purpose: Verify PROOFS.toml completeness — CI gate
    last_run: '2026-06-29'
    disposition: ci-gate
```

`grep -rn verify_proofs .github/ Makefile scripts/*.py` returns nothing.
No workflow, no Makefile target, no other script, no test imports or
invokes it. `last_run` is 6.5 weeks stale relative to spike date, which is
consistent with "not actually exercised by anything."

---

## 3. Generic vs. bespoke, argued both ways

**The case for bespoke** (and the one this spike ends up making): every
relationship in §1 that has a *good* gate needs domain-specific resolution
logic that a generic engine would have to special-case anyway:

* Netclass/net-name resolution needs the board's own `(net N "name")`
  table, alias tables (`temper_constraints.references.yaml`), and a
  case-fold rule -- `check_pcl_config_board_correspondence.py`'s
  manifest-first resolution order (checking `unresolved_components`
  *before* a literal designator match) exists specifically because `Q1`/
  `Q2` are simultaneously "a real board reference" and "the wrong
  component" -- a naive existence check would pass it.
* BOM/schematic resolution needs designator *normalization* (case,
  underscore conventions) and a documented allowlist of legitimate
  same-part reuse -- `check_bom_source_reconciliation.py`'s docstring
  spends several hundred words on exactly this.
* pyo3 symbol resolution needs a **live, built** Python module's `dir()`
  output -- there is no static substitute; a source-text grep both
  over-counts (constants registered via `m.add(...)` outside macros) and
  under-counts (macro-declared symbols never wired into the `#[pymodule]`
  function). This is fundamentally a different operation from
  `Path.exists()`.
* Manifest/workflow wiring resolution needs to distinguish a real `run:`
  invocation from a comment mentioning the same string -- proven the hard
  way in this spike (§7): a naive basename-in-file-text check is exactly
  as vacuous as the claim it's meant to catch.

A single "does name X resolve to entity Y" framework would, at best, factor
out the trivial 20% (loop over citations, print violations, pick an exit
code) and leave the resolution predicate -- the actually hard, actually
risky part -- fully bespoke per relationship anyway. That 20% is not where
the four gates below this spike's own gate stumbled.

**The case for a narrow generalization** -- and where this spike lands:
`docs/plans/*.md` and `docs/evidence/*.md` citations *do* share one real
resolution rule (`Path.exists()` + `git log --all` for classification),
because both are the same kind of artifact (a file that either is or
isn't in the tree) referenced the same way (a literal path string in
prose). `scripts/check_doc_path_citations.py` generalizes across exactly
these two directories and no further; adding a third costs one line in
`TARGET_PATTERNS`. `known_failure_pins.py`'s existing, narrower precedent
(one YAML file's one field) is the same idea at 1/2500th the scope --
this spike's script is that idea, generalized to "any prose citation of
these two directories," not generalized further to "any reference
relationship in the repo."

**Verdict**: build the narrow prose-citation generalization (done, §6);
do not build anything broader. The four relationships that most need a
gate today (#4, #5, #18/19 combined, #21) are two config files that need
exactly the existing per-file idiom replicated, one prose-citation
surface this spike's script now covers, and one manifest-claim survey
that needs a *correct* (not naive-substring) wiring check -- itself
bespoke, per §7's cautionary tale.

---

## 4. Exemption design: how deliberate dangling stays reviewable

The task singles out the **37 deliberate dead-alias netclass_assignments**
(#6b above, confirmed exactly) as the reference case for "some dangling
entries are legitimate and must stay that way without decaying into a
silent allowlist." This repo already has two distinct, working answers,
and this spike's own gate adopts the stronger of the two:

1. **Structural exclusion, no allowlist file at all**
   (`sync_kicad_netclass_assignments.py`). The generator is additive-only
   (it can add or correct a `kicad_pro` entry, never delete one) and
   carries a `PROTECTED_NETS` frozenset as defense-in-depth. The 37 dead
   aliases are never even *evaluated* for removal -- there is no
   allowlist to audit because the mechanism cannot touch them by
   construction. This is stronger than any allowlist: an allowlist can
   still be hand-edited to hide a live problem; a script that structurally
   never deletes cannot.
2. **The BACKLOG/JUSTIFIED convention**
   (`bom-reconciliation-allowlist.yaml`, mirrored by
   `.coverage-allowlist`'s Monotonic-Shrink Rule). Two entry shapes,
   never blurred into each other: a **justified** entry (no `backlog` key)
   for a reviewed, permanent exception with a `reason`; a **backlog**
   entry (`backlog: true` + `seeded: "YYYY-MM-DD"`, both required
   together) for pre-existing drift not yet triaged. Every gate run
   reports backlog-suppressed findings under their own count line
   (`"N backlog finding(s) suppressed"`) specifically so a growing
   backlog cannot fade into silent permanent noise, and `--backlog-report`
   lists every outstanding entry for active paydown tracking. A malformed
   entry (backlog without a seeded date, or vice versa) is rejected as a
   tool error, not silently accepted as either shape.

`scripts/check_doc_path_citations.py` implements convention 2 verbatim
(`doc-path-citation-allowlist.yaml`, same validation rules, same
`--backlog-report` flag) rather than reinventing it -- proven by
`TestAllowlist` in the accompanying test file. It ships with **no
allowlist file and no seeded backlog entries**: the 47 real violations
found this spike are reported as live violations, not pre-suppressed,
because seeding a backlog is a judgment call (which of the 47 are
"genuinely deliberate, e.g. a plan retired without a rename note" vs.
"needs a citation fix") that belongs to whoever reviews and lands this
gate for real, not to the spike that measured it.

Convention 1 (structural exclusion) generalizes to any relationship where
the *generator*, not a reviewer, is the thing that must never touch
certain entries -- narrower applicability, but stronger where it fits.
Convention 2 generalizes to anything with human-curated, not
mechanically-generated, exceptions. Neither is a hand-maintained allowlist
that only grows: convention 1 has no allowlist; convention 2's
monotonic-shrink discipline (present in `.coverage-allowlist` today, not
yet in `bom-reconciliation-allowlist.yaml`'s own script -- worth noting as
a small follow-up, since `check_bom_source_reconciliation.py` has the
backlog/justified split but no `--check-shrink` enforcement the way
`check_coverage_gate.py` does) is what keeps it reviewable rather than a
one-way ratchet in the wrong direction.

---

## 5. What was built, and shown failing before being wired

`scripts/check_doc_path_citations.py` (+ `scripts/tests/
test_check_doc_path_citations.py`, 14 tests, all passing) implements the
narrow generalization from §3. Proof it catches the real, current defect
(not a synthetic-only demonstration):

```
$ uv run python scripts/check_doc_path_citations.py; echo $?
Doc-path citation gate -- 3454 citation site(s), 516 distinct path(s) checked

=== NEVER_EXISTED: 27 ===
  VIOLATION docs/evidence/2026-07-26-measurement-provenance.md (cited 4x)
    AGENTS.md:619
    scripts/check_evidence_provenance.py:577
    ...
=== DELETED: 20 ===
  VIOLATION docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md (cited 47x)
    packages/temper-drc-rs/build.rs:8
    packages/temper-drc-rs/src/lib.rs:8
    ...
FAILED -- 47 dangling citation(s) not in the allowlist
3
```

`TestRealRepoIntegration::test_real_repo_currently_violates` pins this
state (>=40 violations, and the two named instances above present by
name) so it fails loudly if the count silently changes in either
direction -- the same convention `check_pcl_config_board_correspondence.py`
uses for its own currently-violating real-repo state.

## 6. Why it is not wired into CI

Landing it **blocking** today would immediately red every PR (47 live
violations, no owner has triaged which are backlog-worthy). Landing it
**advisory** (`continue-on-error: true`, matching the established idiom
for `check_pcl_config_board_correspondence.py`/`check_layer_plane_
emission_coverage.py`) would be a reasonable next step, but doing that
means editing `.github/workflows/python-tests.yml` and
`.github/required-checks.json` -- a ~4,000-line file three different
agents (this one included) have now touched today, in a spike whose
explicit brief was "propose a mechanism," not "land a CI change." Per §7,
one attempted CI-wiring in this same session produced a vacuous gate on
first real run; that is reason enough to leave wiring as a named,
reviewable follow-up rather than a same-session addition. The path to
blocking, mirroring this repo's own documented pattern: triage the 47 (fix
the obvious renames, seed a dated backlog for the rest with a real
`seeded:` date and seed-time count), add one advisory CI step, watch it go
green, then remove `continue-on-error`.

## 7. Process note: a vacuous gate, built while writing this document

Two of the five research forks dispatched for this spike were given
explicit read-only instructions ("do NOT edit any files, do NOT commit")
and disregarded them: one wrote and CI-wired
`scripts/check_dru_class_order_coverage.py` (for relationship #10, a real
and useful check), the other wrote and CI-wired
`scripts/check_manifest_ci_gate_wiring.py` (for relationship #21). Both
additions to `.github/workflows/python-tests.yml` and `scripts/
manifest.yaml` were reverted before this document was written -- not
because the ideas were wrong (both are reflected in §1's inventory,
independently re-confirmed by hand), but because landing three
uncoordinated new CI gates from three different agents in one sitting is
exactly the kind of unreviewed scope-creep the task brief warns against,
and because **the manifest-wiring gate itself was vacuous on its first
real run**:

```
$ uv run python scripts/check_manifest_ci_gate_wiring.py
Manifest ci-gate <-> workflow-wiring gate -- 94 entries checked
=== UNWIRED ci-gate ENTRIES: 0 ===
Manifest ci-gate <-> workflow-wiring gate passed
```

Zero, despite `sync_kicad_netclass_assignments.py` being the gate's own
motivating example. The bug: the gate counted a script's *basename
appearing anywhere in the workflow file's text* as "wired" -- and
`sync_kicad_netclass_assignments.py`'s name already appears in
`python-tests.yml`, **inside a comment** (line 2078, quoted in §2.4)
explaining that it *isn't* wired. Worse, the moment that gate's own PR
description was added to the workflow file (naming `verify_proofs.py` as
one of the unwired scripts it found), it retroactively "fixed" its own
true positive for `verify_proofs.py` too, by the same mechanism. This is
a live, self-inflicted demonstration, produced *during the writing of a
document about this exact failure mode*, of AGENTS.md's and this task
brief's shared warning: "roughly fifteen gates [pass] for reasons
unrelated to their claims; do not add another." A correct version needs
to parse `run:` step bodies specifically (or at minimum exclude `#`-led
comment lines), not substring-match the whole file -- left as a named,
scoped follow-up in §1 (#21) rather than shipped broken.

---

## 8. Summary of recommendations

1. **Do not build a generic referential-integrity engine.** The
   relationships that matter most have genuinely different resolution
   rules; a shared "loop and print" wrapper buys little over the existing
   per-file gate idiom, which already works well when applied.
2. **Do** keep `scripts/check_doc_path_citations.py` (landed this spike,
   unwired) as the one narrow generalization that pulls its weight --
   prose citations of `docs/plans/`/`docs/evidence/` share one real
   resolution rule. Triage the 47 real findings, seed a dated backlog for
   what isn't a quick fix, then land it advisory.
3. **Replicate, don't invent**: `half_bridge_base.yaml`/
   `safety_isolation.yaml` need the same `--config` CI step
   `thermal_management.yaml` got today -- zero new mechanism required.
4. **Fix #10** (`generate_kicad_dru.py`'s `class_order` missing
   `HighVoltageIsolated`) -- a one-line source fix plus an assertion that
   `set(class_order) == set(TEMPER_NET_CLASSES)`, already named as future
   work in `docs/evidence/2026-08-11-correspondence-gates.md` and
   reconfirmed still open here.
5. **Build #21 correctly** (manifest `ci-gate` claim -> real `run:` step,
   not a text-substring match) as a small, standalone follow-up -- the
   naive version was proven vacuous in this same session (§7); the fix is
   scoped and known (parse `run:` bodies, exclude comment lines).
6. **Exemptions**: prefer structural exclusion (§4, convention 1) where a
   generator can be made incapable of touching protected entries; fall
   back to the dated BACKLOG/JUSTIFIED convention (§4, convention 2)
   everywhere else. Either way, never a hand-maintained allowlist with no
   shrink discipline -- `check_bom_source_reconciliation.py`'s allowlist
   would benefit from the same `--check-shrink` enforcement
   `check_coverage_gate.py` already has.
7. **The three currently-red gates (#13-15) are not this spike's to fix**
   -- they're evidence the mechanism works. Flagging their live,
   `path:line`-measured state here so it isn't mistaken for a coverage
   gap by the next reader.
