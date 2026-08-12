<!-- provenance: commit=112a60b8b (base, origin/main), branch spike/referential-integrity-solo,
worktree .claude/worktrees/refint-solo. All counts in this document were measured directly against
this commit by running the repo's own gate scripts (or, where no gate exists, a one-shot script
written for this survey) -- see "Measured, not inferred" note per section. No pcb/** file modified.
One proof-of-concept gate is included: scripts/check_manifest_ci_gate_wiring.py (commit 75ae83490,
carried onto this base), landed advisory. -->

# Referential integrity: an inventory of "names something that doesn't exist," measured

**Verdict up front:** this repo has at least fourteen distinct instances of the pattern, spanning
nine relationship families. Seven families already have a working, repo-specific gate (four of
those are clean; three still fail on a real, live violation). Four families have **no gate at
all**, and hand-measuring them here found real, non-trivial dangling-reference counts in three of
the four -- including one (a "CI gate" manifest label that lies about being wired into CI) that
generalizes the exact defect named in this task's brief from 1 known instance to **11**. One
family (the pyo3 Rust/Python boundary) is gated for exactly 1 of 4 extension crates, with no
current drift but no structural protection either for the other 3. **A single generic mechanism is
not the right shape for most of this.** The relationships differ enough in what "ground truth"
means, what counts as a legitimate exception, and how cheaply resolution can be checked that seven
bespoke, narrow gates (the shape this repo has already converged on) outperform one framework. Two
places really do share a resolution rule and could plausibly share code; that's it. One small,
cheap gate is implemented and landed as proof (advisory): `scripts/check_manifest_ci_gate_wiring.py`.

---

## 1. The inventory

Fourteen relationships, grouped by what already exists. "Status" is the gate's real CI wiring today
(blocking / advisory / **unwired** / none exists), not its aspiration. All counts below are live
measurements against `112a60b8b` (`origin/main`, 2026-08-12), reproduced independently across two
worktrees roughly 15 commits apart during this survey -- every number was stable across that gap
except where noted.

### 1a. Gated, currently clean

| # | Relationship | Gate | Wiring | Measured |
|---|---|---|---|---|
| 1 | `configs/*.yaml` `net_classes:` key -> real board net | `scripts/check_netclass_map_board_correspondence.py` | **Blocking** (`.github/workflows/python-tests.yml:2010`, no `continue-on-error`) | **0 / 58** broken keys. Was 31/70 across 4 files when the gate's own evidence doc (`docs/evidence/2026-08-11-correspondence-gates.md`) was written a day earlier -- fixed since. |
| 2 | `pcb/temper.kicad_pro` netclass param values (clearance/track_width/via_diameter/via_drill) <-> `design_rules.py` `TEMPER_NET_CLASSES` | `scripts/check_netclass_class_param_correspondence.py` | **Blocking** | **0 / 8** classes mismatched. Was 5 mismatches (`HighVoltage.clearance` 6.0 vs 2.0, plus 4 `Power` fields) at gate introduction -- fixed since. |
| 3 | HV-domain net -> `TEMPER_NET_ASSIGNMENTS` classification, and declared netclass -> at least one emitted DRU rule | `scripts/check_hv_netclass_coverage.py` | **Blocking** | **0 / 0**. Clean on both properties. |
| 4 | `elec/domain_manifest.yaml` declared nets/isolators/protective-impedance chains <-> compiled netlist | `scripts/check_domain_partition.py` | **Blocking** | **0 / 0** across 51 declared nets, 2 domains, 10 isolators, 2 chains. |
| 5 | Net classification via keyword-substring fallback <-> `elec/domain_manifest.yaml` | `scripts/check_net_classification.py` | **Blocking** | Passed (0 violations; many `UNRESOLVED` diagnostic entries not further audited here -- out of this survey's scope). |
| 6 | `scripts/` `.py` file -> `scripts/manifest.yaml` entry (reverse of #12 below) | `scripts/check_manifest_gate.py` | **Blocking** | **0 / 153** files missing an entry (1 non-blocking warning: `deadcode-baseline.py` has an empty `imports:` list). |

### 1b. Gated, currently violating (advisory)

| # | Relationship | Gate | Wiring | Measured |
|---|---|---|---|---|
| 7 | PCL placement config component refs / zones -> board designators / outline | `scripts/check_pcl_config_board_correspondence.py` | **Advisory** (`continue-on-error: true`) | **24** broken component references (`J_AC_IN`, `J_COIL`, `J_DEBUG`, `adj_Q1_Q2` resolving to the *wrong* real designators) + **3** zones outside the board outline. Unchanged since gate introduction -- no safe mechanical fix exists (see `docs/evidence/2026-08-11-correspondence-gates.md` Gate 1). |
| 8 | Declared power-plane board layer -> zone-pour emitter code path | `scripts/check_layer_plane_emission_coverage.py` | **Advisory** | **1** plane layer (`In1.Cu`) with no emitter path, down from 2 at gate introduction (`In2.Cu` fixed since) + 1 parser role-token-fidelity violation (`parse_engine.rs` still discards index 2 of `(N "Name" role)`). |
| 9 | `pcb/temper.kicad_pcb` copper (segment/via/zone net ordinal, per-pad net) <-> freshly compiled `elec/*.ato` netlist | `scripts/check_copper_net_consistency.py` | **Nominally blocking** -- its own workflow comment reads "Never `continue-on-error`: a gate that cannot run must exit non-zero" | **347** per-pad/segment net mismatches, measured against a `make netlist`-regenerated netlist (matching CI's own build step) both times, ~15 commits apart. See "A finding worth flagging on its own," below. |
| 10 | `elec/*.ato` component instantiation <-> `pcb/temper.kicad_pcb` footprint/sheetpath | `scripts/check_footprint_drift.py` | **Nominally blocking**, same convention as #9 | **13** violations (6 `missing-from-board`, 7 `missing-from-netlist`) -- the OCP-02 circuit and the ZCD-clamp subcircuit are wired on one side and absent on the other. Stable across the ~15-commit gap. |
| 11 | `docs/hardware/BOM.md` designator/MPN <-> `elec/src/*.ato` instantiation | `scripts/check_bom_source_reconciliation.py` | **Blocking** | **8** findings (6 `costed_no_circuit`: BOM.md prices a part with no matching instantiation; 2 `wired_uncosted`: source instantiates something with no BOM row). Has a well-designed, hand-maintained-only allowlist -- see Section 3. |

### 1c. No gate exists today

| # | Relationship | Measured dangling count | This survey's method |
|---|---|---|---|
| 12 | `scripts/manifest.yaml` `path:` field -> real script file | **0 / 154** (vacuously clean; see caveat below) | Line-parsed every `- path:` entry, resolved repo-root-relative then `scripts/`-relative, checked `is_file()`. |
| 13 | `scripts/manifest.yaml` `disposition: ci-gate` -> script actually invoked by a `.github/workflows/*.yml` `run:` step | **10 / 94** unwired (**11.7%**) | Cross-checked every `ci-gate`-labeled basename against the concatenated text of every workflow file. **Proof-of-concept gate implemented and landed advisory this session** -- see Section 4. |
| 14 | `.github/workflows/*.yml` `run:` step -> script file it invokes | **0 / 163** real dangling (10 apparent hits were all false positives: `working-directory`-relative paths, a URL, template `.j2` files, a runtime checkout path) | Token-extracted every `scripts/...`-shaped path from workflow YAML, resolved each against its step's actual working directory. |
| 15 | Production (non-test) code -> `docs/evidence/*.md` path citation | **11 / 167** dangling (**6.6%**) | Regex-swept every tracked `.py`/`.rs` file (excluding `docs/evidence/` and test directories) for `docs/evidence/...` path literals (joining adjacent string-literal lines), checked `is_file()`. |
| 16 | Rust `#[pymodule]`-registered symbol -> Python-importable module attribute (pyo3 boundary) | **1 of 4** extension crates protected; 0 measured drift on the other 3 right now | Compared `wrap_pyfunction!`-registered names in each crate's `lib.rs` against the installed module's `dir()`. See Section 1e. |
| 17 | `@req(plan_id, req_id)` code annotation -> plan-declared requirement ID | **Gate exists, unwired to CI at all**, plus a severe scope gap: **47 of 63** files containing `@req(` annotations (**~151 of 167** individual annotations) are never scanned, because 17 of 19 distinct `plan_id` tokens used in real annotations are not registered in `docs/traceability-registry.yaml` at all | See Section 1d. |

### 1d. `check_traceability.py`: exists, three separate findings

`scripts/check_traceability.py` (`--check-annotations`, `--check-coverage`,
`--check-registry-scope`) is the closest thing this repo has to a generic `@req` <-> plan gate, and
it is genuinely well-built for what it scans. It is **invoked by zero workflows** -- `grep -rn
check_traceability .github/` returns nothing, and its `scripts/manifest.yaml` entry (line 1137, this
survey's commit) is honestly labeled `disposition: utility`, not `ci-gate` -- it does not make the
false-wiring claim that Section 1c #13's ten scripts do. Running it by hand today:

```
$ uv run python scripts/check_traceability.py --all
VIOLATION: .../conftest.py:3: requirement 'U1' not defined in docs/plans/2026-06-28-004-...md
VIOLATION: .../test_clearance_induction.py:3: requirement 'U2' not defined in ...
VIOLATION: .../test_clearance_segment_dist.py:3: requirement 'U4' not defined in ...
VIOLATION: .../test_induction_base.py:26: requirement 'U3' not defined in ...
VIOLATION: .../test_all_pad_tree_routing.py:1: plan 'APC1' has status 'completed', expected 'active'
  ... (6 total plan-status mismatches)
SCOPE ISSUE: APC1: scope entry '.../all_pad_evidence.py' is not tracked by git
SCOPE ISSUE: N2: scope entry 'packages/temper-drc/tests/test_safety_constant_lint.py' is not tracked by git
SCOPE ISSUE: N4: scope entry 'packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py' is not tracked by git
  ... (7 total: 2 for APC1, 5 for N2/N4, all under the deleted packages/temper-drc/ package)
```
Exit code 1. Three genuinely distinct findings live in that one run:

1. **A false positive in the checker itself.** `_parse_requirements`'s two regexes
   (`check_traceability.py:218-219`) are hardcoded to `R\d+` -- they can never recognize a `U`-prefixed
   requirement ID. The cited plan
   (`docs/plans/2026-06-28-004-feat-mathematical-rigor-deferred-items-plan.md:45,78,122,173`) genuinely
   defines `U1`-`U4` as its own numbering convention (`### U1. CI budget benchmarks...`), matching the
   `U1`/`U4`/`U-E` unit-numbering convention visible in this repo's own recent commit history (e.g.
   `f98dfd207 feat(migration-pipeline): FREEZE oracle-retirement tooling (U4) + first retirement (U5)`).
   The four `@req(N10, U1..U4)` annotations are real and correctly cite a real plan; the gate's own
   resolution logic just cannot see that plan's ID namespace. This is exactly the class of "different
   relationships have different resolution rules" the task brief warns a generic mechanism would
   struggle with, found inside the one gate that already tries to be general.
2. **A real, live dangling reference:** `docs/traceability-registry.yaml`'s `scope:` list for plans
   `N2` and `N4` names five files under `packages/temper-drc/`, a package `AGENTS.md` itself records
   as deleted ("the Python `temper-drc` package was deleted in the shim-then-delete migration"). The
   registry was never updated. Two more (`APC1`'s scope) name paths that were apparently never
   committed at all.
3. **A severe, unmeasured-until-now scope gap.** `check_traceability.py --check-annotations` only
   scans files that fall inside a *registered* plan's `scope:` list (11 plans registered:
   `N1`-`N10`, `APC1`). This survey found **19 distinct `plan_id` tokens** actually used inside
   `@req(...)` calls repo-wide (167 annotations across 63 files); only **2** of those 19
   (`N10`, `APC1`) are registered. **47 of the 63 files -- roughly 151 of the 167 annotations --
   sit entirely outside any registered scope and are never examined by the tool at all,** regardless
   of whether their requirement IDs are real. The gate's own summary line makes this precisely
   measurable: "Scanned 332 file(s) across 8 of 11 registered plan(s)' declared scope ... found 12
   `@req` annotation(s)" -- 12 out of 167.

None of these three needed inference; all three are direct output of the existing tool plus one
`grep`/diff pass. This is the richest single finding in this survey and the strongest argument
against a naive "just run the existing checker" fix: the checker exists, is correct in its own
narrow terms, and still misses over 90% of the relationship it claims to check.

### 1e. The pyo3 boundary: one crate protected, three exposed

`scripts/check_rust_drc_presence.py` exists *because* of a real incident (2026-07-26): `temper-drc-rs`
gained a new exported symbol; a stale installed wheel still imported successfully (`import
temper_drc_rs` doesn't fail on a missing *new* symbol, only a missing module), so a differential
test silently skipped and a fast-path dispatch silently fell back to slow Python -- both exit 0,
invisible in a CI summary. The gate derives expected symbol names from `lib.rs`'s `#[pymodule]`
block and diffs them against the installed module's real attributes. It is wired **blocking**
(`.github/workflows/python-tests.yml:510`, explicit "Never `continue-on-error`" comment) --
but only for `temper_drc_rs`.

This repo has three more first-party pyo3 extension crates (`temper_rust_router`,
`temper_design_bundle_python`, `temper_constraints`, plus the deleted `temper_drc`'s replacement path
already covered). Each gets only a bare `import x; print('loaded OK')` smoke test in CI -- exactly
the check the presence-gate's own docstring calls insufficient ("a bare import ... cannot catch this:
the module *is* importable. What's missing is present, not absent."). Comparing each crate's
`wrap_pyfunction!`-registered names (in `lib.rs`) against its currently-installed `dir()`: no
drift measured right now on any of the three. That is not evidence of safety -- it is evidence the
exact incident that motivated the one gate that exists simply has not recurred yet on the three
crates with no structural protection against it.

### A finding worth flagging on its own

`check_copper_net_consistency.py` (#9) and `check_footprint_drift.py` (#10) are the two gates in
this survey whose own workflow comments explicitly say "Never `continue-on-error`" -- meaning they
are meant to hard-block every PR. Measured directly against `origin/main`, freshly regenerated with
`make netlist` (matching CI's own build step) on two separate worktrees roughly 15 commits apart:
**347** and **13** violations respectively, both times. Either CI on `main` is red right now for
this reason, or something about how/when this job actually triggers keeps it from being felt --
this survey did not have access to live CI run history to distinguish the two, and says so rather
than guessing. Whichever it is, it is the single most surprising number in this whole exercise, and
worth a maintainer's five minutes to check `main`'s actual CI status before anything else in this
document.

### An adjacent, related finding not on the task's list

`scripts/check_refdes_identity_stability.py` checks a fifth kind of drift: not "does this
designator exist" but "does this designator, cited in a *safety-relevant test assertion*, still
mean the same real component it meant when the assertion was written." (KiCad/atopile ref
designators are positional -- deleting `U3` reflows every later `U`-prefixed ref down a slot.) It is
honestly unwired (`disposition: utility`, and its own `manifest.yaml` purpose text says "never wired
into CI (false-positive rate unmeasured on first pass)" -- no false claim here, unlike #13).
Run by hand: of 8081 candidate ref-designator-shaped string literals, 59 are real-board-bound and
individually verifiable, and **8 are VERIFIED MISMATCH** -- e.g. a test asserting `U7` denotes the
gate-driver isolator, when `U7` currently denotes `hb.gate_hs.boot_diode`. Two of the eight are the
exact `Q1`/`Q2` pair already named in #7's `adj_Q1_Q2` finding, independently rediscovered by a
completely different mechanism (compiled-netlist identity, not config-string matching) -- the same
underlying board-history event (a component deletion reflowing refs) surfaces in two unrelated
relationships this survey covers, which is itself a small piece of evidence that the relationships,
while requiring separate gates, are not causally independent.

---

## 2. A worth-noting aside: the manifest's own header lies about itself

`scripts/manifest.yaml`'s `_meta` block (`total_scripts: 119`, `counts.keep: 115`,
`last_audit_date: '2026-08-05'`) disagrees with its own body -- 153 (now 154) real entries, all
`category: keep`, as of this commit. Not one of the 17 relationships above; just a reminder that
this exact pattern -- a declared summary drifting from the thing it summarizes -- shows up even
inside the file that is itself trying to be a source of truth for other checks.

---

## 3. Generic mechanism, or bespoke gates? Bespoke, with two narrow exceptions

**Recommendation: keep building bespoke, single-purpose `scripts/check_*_correspondence.py`
scripts.** This repo has already converged on that shape independently seven times (Section 1a/1b),
and the shape is working -- four of those seven are clean and blocking, and the family has a
consistent, legible idiom (`GateError`, `run() -> (state, Report)`, exit 0/3/5, a `--kicad-pro`/
`--manifest`-style override for testability, `TestAntiVacuity` + `TestRealRepoIntegration` test
groups). A generic framework would have to abstract over properties that are genuinely different
per relationship:

- **What counts as ground truth is not uniform.** For net names it's `pcb/temper.kicad_pcb`'s own
  net table (#1, #4); for evidence citations it's a `git cat-file`-verifiable commit SHA (a
  *different* file's provenance stamp, not the citing file); for `@req` it's a plan document's prose
  structure (heading levels, section names) with no schema at all; for the pyo3 boundary it's a
  `.rs` macro invocation pattern. A shared "resolver" abstraction would need a plugin per relationship
  anyway -- at which point it is the bespoke-scripts world with extra indirection, not less.
- **Legitimate dangling references exist, and the criteria for "legitimate" differ per relationship.**
  `sync_kicad_netclass_assignments.py`'s 37 dead-alias `kicad_pro` `netclass_assignments` entries
  (confirmed exactly 37, of 99 total, this survey) are *never* removed by design -- deleting them
  risks dropping something a human added for a reason the script doesn't know. `check_pcl_config_
  board_correspondence.py`'s Gate 1 tolerates commented-out `DISABLED (config<->netlist drift)`
  constraints. `check_bom_source_reconciliation.py` has a three-way split: hand-verified-real
  (justified allowlist), pre-existing-untriaged (dated `backlog:` entry), and neither (a live
  finding). A generic gate would need all three exemption shapes simultaneously, which is really
  three gates wearing one frontend.
- **Resolution timing differs.** Net names and manifest paths are static, resolvable at any commit.
  Board/netlist consistency (#9) depends on a freshly-compiled artifact (`make netlist`) that isn't
  even checked into git. `@req` coverage depends on a plan's *lifecycle status* (`active` vs.
  `completed`), which is a property of time, not of the text.

**Two places a shared mechanism is plausible, not a slam dunk:**

1. **"Does file A contain literal path/name X, and does X exist" is genuinely the same shape** for
   #12/#13/#14/#15/#17's registry-scope check -- all four are "scan a corpus of files for a
   string-shaped reference, check existence/presence of the referent." A shared *helper* (parse a
   corpus, extract path-or-name-shaped tokens by a supplied regex, check existence, report
   `path:line`) would remove real duplication -- this survey's own one-off scripts for #14/#15
   independently reimplemented the same 15 lines three times. This is worth extracting as a shared
   `scripts/_lib/reference_scan.py` helper *function*, not a generic gate -- each relationship still
   needs its own regex, its own resolution order (manifest-first vs. board-first, as Gate 1's own
   design note explains), and its own exemption policy.
2. **The `run() -> (state, Report)` / exit-0/3/5 / `--override-for-testing` skeleton already *is* a
   shared convention**, just not formalized as shared code. Extracting it into a tiny base (a
   `GateResult` dataclass, the three exit constants, the `tool_error`/`violation`/`clean` state
   enum) would cut boilerplate without hiding any relationship-specific logic. This is refactoring
   the existing successful pattern, not building a new one -- and it's the only piece of this
   whole survey that looks like genuine, low-risk, mechanizable duplication.

**Not mechanizable at all:** #7's `adj_Q1_Q2` (needs a human to decide which real IGBT pair was
meant), #9/#10's board/netlist reconciliation (needs a `resync_pcb_netlist.py` run and human review
of which side is authoritative), #16's "was this symbol *meant* to be removed" (a `#[pymodule]`
entry with no Python caller could be dead code or an in-flight addition -- presence-checking can't
tell which), and #17's `U`-vs-`R` ID-namespace gap (needs someone to decide whether
`check_traceability.py` should support multiple ID conventions or whether the repo should
standardize on one). These are judgment calls a gate can surface but never resolve.

---

## 4. What was built, and shown failing before being wired

**`scripts/check_manifest_ci_gate_wiring.py`** (+ `scripts/tests/test_check_manifest_ci_gate_wiring.py`,
19 tests) closes relationship #13: every `scripts/manifest.yaml` entry self-labeled `disposition:
ci-gate` must be invoked by a `run:` step somewhere under `.github/workflows/*.yml`. This directly
generalizes the task brief's own example (`sync_kicad_netclass_assignments.py`'s docstring/manifest
both falsely claim "wired into CI") from 1 known instance to the full, measured set of **10**:
`bmc_adoption_gate.py`, `check_drc_determinism.py`, `check_migration_narrowing.py`,
`gen_pcb_skeleton.py`, `update_regression_cache.py`, `verify_proofs.py`, `write_build_stamp.py`,
`check_ceiling_raise_evidence_corpus.py`, `check_component_defect_corpus.py`,
`check_corpus_specificity.py`. Shown failing on the real repo before being wired:

```
$ uv run python scripts/check_manifest_ci_gate_wiring.py
Manifest ci-gate <-> workflow-wiring gate -- 94 'disposition: ci-gate' entry/entries checked...
=== UNWIRED ci-gate ENTRIES: 10 ===
  VIOLATION scripts/manifest.yaml:88 path='bmc_adoption_gate.py' is disposition: ci-gate but ...
  ... (10 total)
FAILED -- 10 unwired ci-gate entry/entries
$ echo $?
3
```

Landed **advisory** (`continue-on-error: true`), matching this repo's own convention for a
freshly-introduced gate with real pre-existing violations (Gates 1/2 in Section 1b). Committed at
`75ae83490` on `spike/referential-integrity-solo`.

**Why this one, and not one of the other three ungated relationships:** #14 (workflow -> script) is
already clean, so a gate there would protect against regression only, not close an active gap.
#15 (evidence citations) and #17 (`@req` scope) are real and larger, but neither has a single
obviously-correct exemption policy yet -- #15 mixes "doc genuinely never written," "doc exists on a
side branch," and "doc was deleted on purpose," which is exactly the kind of maintainer call
Section 3 says a gate should surface, not resolve, and #17 first needs the `R\d+`-only regex bug
fixed before a coverage gate on top of it would mean anything. #13 was buildable, provably correct,
and non-controversial in under an hour, which is what "small and cheap" means here.

---

## 5. Exemptions stay reviewable: no allowlist for this one, on purpose

The task's Monotonic-Shrink Rule (`AGENTS.md`, coverage-allowlist section) exists because an
allowlist that only grows is a gate decaying into a no-op. For relationship #13 specifically, this
survey deliberately used **no allowlist file at all** -- not because exemptions don't matter, but
because the honest fix for "this manifest entry falsely claims CI wiring" is not "exempt it," it is
one of exactly two actions, both of which are already visible in an ordinary code review:

1. **Wire it** -- add the `run:` step; the gate goes green for that entry on its own.
2. **Stop claiming it** -- change `disposition: ci-gate` to `utility` (or whatever it actually is)
   in the same diff that acknowledges it isn't CI-wired.

Both are single-line, diff-visible, reviewer-legible changes to the *declaration itself* — there is
nothing left over that needs a separate reviewable list, and so nothing that can silently
accumulate the way an allowlist can. Where this survey found relationships that *do* have
legitimate, permanent exceptions -- `sync_kicad_netclass_assignments.py`'s 37 dead aliases,
`bom-reconciliation-allowlist.yaml`'s hand-verified/backlog split -- the existing repo convention
already satisfies the reviewability bar and should be the template for any future one:
**hand-edited only** (no `--init`/`--regenerate` mode that could bulk-populate it), **every entry
requires either a human-verified justification or a dated `backlog:` marker distinguishing
"known-and-accepted" from "known-and-not-yet-triaged,"** and a `--check-shrink` mode (as
`check_evidence_provenance.py`'s `.evidence-provenance-allowlist` already has) that fails CI if an
entry is *removed* without either fixing the underlying code or citing why it's now moot. That
combination -- hand-edited, justified-or-backlogged, shrink-checked -- is the reusable piece from
this survey, more so than any shared scanning code: it is a policy pattern, applicable to relationship
#7's harder-half reconciliations and #17's registry-scope cleanup alike, not a library import.
