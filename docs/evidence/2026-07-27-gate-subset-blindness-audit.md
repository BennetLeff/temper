# Gate subset-blindness audit: which CI gates inspect a fraction of their
intended input without saying so

**Date:** 2026-07-27
**Scope:** every gate named in the audit brief -- `check_vacuous_gates`,
`check_physics_provenance`, `check_fault_list_consistency`,
`check_traceability`, `check_coverage_gate`, `check_manifest_gate`,
`check_script_sunset`, `check_undeclared_imports`, `import_linter_gate`,
`check_typecheck_gate`, `bmc_adoption_gate`, `capacity_budget_gate`,
`mpn_fabrication_gate`, `check_derived_doc_drift`, `check_domain_partition`,
`check_rust_drc_presence` -- plus the shared allowlist infrastructure
(`scripts/_lib/gate_allowlist.py`) they draw on.
**Fixed this pass:** `scripts/check_vacuous_gates.py` (scope rewrite, mandatory
per brief), `scripts/check_physics_provenance.py` (denominator reporting +
zero-scan fail-closed). Everything else: audited, not modified -- see
"Findings ranked by consequence" for what would need follow-up.
**Base:** `origin/docs/methodology-loop-discipline` @ `043debdf` (see note on
base drift below).

---

## Falsifier

Stated before implementing, per the brief: **"widening the scope finds
nothing, meaning the narrow scope was adequate."**

**It did not fire.** Widening `check_vacuous_gates.py`'s scope from 52 files
to 526 files found **13 real unguarded `all()` calls** that the narrow scope
never saw, in 6 files, three of them CI gate scripts themselves
(`scripts/mpn_fabrication_gate.py`, `scripts/check_derived_doc_drift.py`,
`scripts/import_linter_gate.py`, plus `scripts/ci_identity_check.py`,
`scripts/spc_rules.py`, and two `packages/temper-placer/src` modules). The
narrow scope was not adequate; it was blind to the majority of the files it
was supposed to guard, including several of the very CI gates this audit
was asked to review. The gate is now red. It is left red -- see "What was
fixed" for why that is the correct outcome, not a regression to walk back.

A quick note on the base: `scripts/assert-base.sh docs/methodology-loop-discipline`
failed twice. The first failure (250 commits behind, on an unrelated branch)
was fixed per the brief's exact repoint recipe. The second failure was a
different shape: the *local* branch ref `docs/methodology-loop-discipline` is
currently checked out in the primary worktree (`/Users/bennet/Desktop/temper`)
two commits ahead of `origin/docs/methodology-loop-discipline` (unpushed,
unrelated UVLO/placement work). `git rev-parse HEAD` in this worktree equals
`git rev-parse origin/docs/methodology-loop-discipline` exactly
(`043debdfc05208799dc9560e3e327d91673cbfbb`), which is also the SHA the task
brief names as the canonical pushed tip. Treated as verified-correct base and
proceeded; documented here rather than silently ignored.

---

## Per-gate table

Legend: **ratio** = files/items actually inspected over the intended
universe, measured live in this tree. **Denominator?** = does the gate print
"N passed / M possible" (or equivalent) on *both* pass and fail, not just
pass. **Shrink-to-zero?** = does pointing it at empty/missing/non-matching
input still exit 0. **Allowlist growable?** = is there a code path (`--init`
or otherwise) that adds entries without a human writing them by hand.

| Gate | Intends to inspect | Actually inspects (this tree) | Ratio | Denominator? | Shrinks to 0 and passes? | Allowlist growable? |
|---|---|---|---|---|---|---|
| `check_vacuous_gates.py` **(fixed)** | Every gate/validator module for unguarded `all()` | **Before:** `packages/*/src` only, path-substring `"gate"`/`"valid"`. **After:** `packages/*/src`+`*/tests` (minus `router_v6`, minus test-file-named modules) + top-level `scripts/*.py` | Before: 52/~585 candidate `.py` files (2/13 named validator modules). After: 526/~585 (13/13) | No -> **Yes** (both branches, plus explicit zero-scan fail) | **Was** yes (0 files -> "gate passed"). **Now** exits 1 on 0 files scanned | N/A (no allowlist; asserts zero directly) |
| `check_physics_provenance.py` **(denominator added)** | Every module-level float constant in `physics/` | All 2 files / 3 constants under `packages/temper-placer/src/temper_placer/physics/` -- narrow by design (documented scope boundary: `BinOp` exprs, function-body constants excluded), not a subset-blindness defect | 1:1 of its documented target | No -> **Yes** (pass and fail) | **Was** yes (0 constants -> silent pass, no message). **Now** exits 1 on 0 constants | **Yes -- verified, not fixed.** `--init` fully overwrites the allowlist (destructive, not additive) with every currently-undocumented constant, tagged `# TODO: temper-xxx`. `TICKET_PATTERN = r"TODO:\s*temper-(?:\d+\|xxx)"` accepts the literal placeholder `xxx` as a valid ticket reference -- confirmed by direct regex test (`TICKET_PATTERN.search("TODO: temper-xxx")` -> `True`). Currently 0 blast radius (allowlist is empty), but the ticket-required check is a no-op for anything `--init` ever writes. Not fixed here: `TICKET_PATTERN` is shared via `_lib/gate_allowlist.py` with `check_coverage_gate.py`, whose allowlist already has **~1927 entries, every one tagged `xxx`** -- tightening the regex would flip that gate red for reasons unrelated to this audit. Recommending as a follow-up, not doing it unilaterally. |
| `check_coverage_gate.py` | Every public function, zero coverage | Whatever `coverage.json` covers (source of truth is the coverage run, not this gate) | 1:1 of the coverage run it's given | Partial: reports allowlist size, not "N public functions scanned, M zero-coverage" as an explicit ratio | Fails closed: missing `coverage.json` -> exit 1; empty `files` dict -> exit 1 (code-verified, not live-tested: needs a real coverage run) | **Yes, same `TICKET_PATTERN` defect as above**, but here it already bit: **~1927/1927** allowlist entries carry the literal placeholder `# TODO: temper-xxx`, none a real ticket. `--init` here is *additive* (preserves existing entries) -- better than physics-provenance's overwrite, but the ticket-check is still defeated for every entry ever added by tooling. |
| `check_fault_list_consistency.py` | manifest.json fault codes vs `fault_list_generated.h` vs supplemental | All three files, in full, when present | 1:1 | **Pass only.** Fail path (`sys.exit(1)` inside the `if errors:` block) returns before the count-printing lines run -- no denominator on fail | Fails closed for empty manifest/generated (explicit `if not X_codes: errors.append(...)`). **Fragile, not vacuous:** if `fault_list_generated.h` is missing, `generated_codes` is never assigned, and the `if manifest_codes and generated_codes:` line at the module scope raises `NameError` rather than a clean message -- still non-zero exit, just an ugly crash instead of a diagnosed one | N/A (no allowlist) |
| `check_traceability.py` | Every `@req(...)` annotation and every non-deferred requirement, repo-wide | Only directories containing a `TRACEABILITY` opt-in sentinel file. **Live count: exactly 1** (`packages/temper-placer/tests/router_v6/TRACEABILITY`) out of the whole repo | **1 opted-in directory total.** R3 ("coverage") gate's own registry has 11 plans; only plans whose `scope` overlaps that one directory are ever checked -- the rest are silently skipped (`continue`) with no note in the output | **No, worst case in this audit.** Live run: `R3 gate passed: all requirements are covered.` -- printed with **zero mention** that only 1 of the repo's many source trees was ever eligible to contribute an annotation | **Yes, structurally.** If the last `TRACEABILITY` sentinel were deleted, `opted_in` is empty, every plan's `scope_opted_in` stays `False`, the coverage loop `continue`s for every plan, and R3 still prints "all requirements are covered." Live-tested: confirmed by reading `check_coverage()`'s logic and the current live run (1 sentinel, 6/11 plans touched, 0 uncovered found among those) |
| `check_manifest_gate.py` | Every `scripts/*.py` file has a manifest entry | `SCRIPTS_DIR.glob("*.py")`, top-level only (correctly excludes `_lib/`, `tests/` etc. by construction, not by exclusion list) | 1:1 of its documented (top-level-only) target | **Pass only** (`"N files, M manifest entries..."`). Fail path prints violation counts but not the on-disk total | No CLI override to point at an empty/missing dir (hardcoded `REPO_ROOT`); missing `manifest.yaml` -> exit 5 (fail-closed, code-verified) | N/A (no allowlist; violations block directly) |
| `check_script_sunset.py` | Staleness of every `scripts/manifest.yaml` entry | Every manifest entry with a parseable `last_run` | 1:1 of manifest entries, but **exit code is always 0 by design** ("Sunset never blocks PR merge" -- explicit, intentional, not a defect) | Fail path N/A (never fails). Pass path with 0 warnings just prints "no stale scripts" with **no count of how many entries were actually checked** | Vacuously "OK" with an empty manifest, structurally -- but since this check can never gate a merge, the consequence is advisory-only, not a false safety signal | N/A |
| `check_undeclared_imports.py` | Module-level 3rd-party imports in explicitly documented trees | `scripts/`, `scripts/_lib/`, `scripts/tests/`, `packages/temper-placer/tests/`, `packages/temper-workflow/tests/`, `elec/validation/`. **Deliberately excludes `packages/*/src`**, with two known live findings (`jax` in `temper_workflow`, a `sys.path` test-tree shim in `domain_clearance.py`) explicitly logged rather than silently dropped -- see `docs/evidence/2026-07-27-undeclared-import-gate.md` | Matches its documented scope exactly; the exclusion is disclosed, not accidental | **Yes.** Exit 5 "vacuous-run backstop": zero import statements found across every parsed file is a tool error, never conflated with 0 violations | Code-verified fail-closed (missing scan root, zero files, zero imports all -> exit 5, not 0) | Per-entry allowlist requires **both** module name and file glob to match (no bare-module wildcarding) plus a mandatory justification comment; no `--init`. Already hardened -- good example |
| `import_linter_gate.py` | Architectural import-boundary contracts | Whatever `lint-imports` scans per its own config; this wrapper adds allowlist + exit-code translation | Not independently measured (delegates to `lint-imports`) | Reports `Analyzed N files... Contracts: X kept, Y broken` when the tool completes normally; explicitly treats a run that doesn't produce that marker as **tool error (exit 5)**, never a silent pass | Could not exercise live in this environment (`temper_placer` not resolvable from a bare `python3`/`uv run` in this worktree -- pre-existing environment/tooling gap, unrelated to this audit); code-verified: missing completion markers -> exit 5, not 0 | `import-linter-allowlist.yaml` -- hand-edited only, no `--init`/auto-populate path found in the script |
| `check_typecheck_gate.py` | mypy errors, `packages/temper-placer/src`, `temper-workflow/src`, `temper-tools/src` | All three configured `SCOPE` paths (2 exist in this tree; `temper-tools` does not, silently skipped by `if not scope_path.exists(): continue` -- **this is itself a small, real, undocumented instance of the pattern**: a configured-but-absent scope path is dropped with no note) | 2/3 configured scope paths | **Yes**, extensively -- "Total (excl. call-arg): N errors in M files (baseline: K)" | **Already fixed**, referencing this exact audit's failure class: `if not existing_scope: FAIL (closed)`. Already-hardened example, cites `docs/evidence/2026-07-26-api-signature-drift-gate.md` | `.typecheck-allowlist` per-file counts via `--init` -- but the historically-dangerous "any regression absorbed silently" mechanism was closed by carving `call-arg` errors into a **separate, hand-curated, `--init`-untouched** file (`.call-arg-allowlist`). Already hardened |
| `bmc_adoption_gate.py` | Every `Constraint` subclass in one file | `constraint_model.py` (AST) + `sat_model.py` (text) + `tests/router_v6/test_bmc_*.py` glob -- 2 hardcoded files + 1 glob, matches its single-purpose design | 1:1 of its (intentionally narrow) target | Pass: "N constraint types have full coverage". Fail: lists each violating class but doesn't restate "N of M total" | **No** -- explicitly fails closed: `if not subclasses: _die(EXIT_ERROR, "No Constraint subclasses found — parser error?")` (code-verified) | N/A (no allowlist) |
| `capacity_budget_gate.py` **(protected, exit 0 preserved)** | Fan-in reachability across all tracked fault-tree aggregator packages | All packages in `capacity_budget_packages.yaml` against the live netlist/BOM | 1:1 | **Yes, always** -- "Packages inspected: N \| nets inspected: M \| pins inspected: K \| SET-path inputs evaluated: J" printed before the pass/fail branch, every run | Missing netlist/BOM -> `GateError` -> exit 5 (verified live: failed exit 5 before `make netlist`, exit 0 after). 0-available-inputs case explicitly called out as a "human decision, not a gate failure" rather than silently passing | N/A (no allowlist) |
| `mpn_fabrication_gate.py` **(protected, exit 0 preserved)** | Every resistor/capacitor value+MPN pair in `elec/src/**/*.ato` | All matched `.ato` files, all parsed parts | 1:1 | **Yes, always** -- "Parts inspected: N (from M .ato files)", "Allowlist entries loaded: K", printed unconditionally | Zero `.ato` files or zero parsed parts -> exit 5, explicit "never treated as 0 violations" comment. Live-verified: exit 0 with real netlist | **No** -- allowlist (`mpn-fabrication-allowlist.yaml`) is hand-curated only, no `--init`; docstring explicitly cites the typecheck-gate incident as the reason. Already hardened, best example in this audit |
| `check_derived_doc_drift.py` **(protected, exit 0 preserved)** | Derived docs vs. source-of-truth per `derived_doc_gates.yaml` | Not independently re-derived this pass beyond confirming live exit 0; contains 4 of the 13 unguarded-`all()` findings surfaced by the fixed `check_vacuous_gates.py` (lines 197, 201, 216, 405) | Not separately measured | Not assessed beyond the `all()` finding | Not assessed | `CUTOVER_DATE`-style soft-launch pattern referenced in `check_undeclared_imports.py`'s docstring as a contrast case; not independently re-verified here |
| `check_domain_partition.py` **(protected, exit 0 preserved; good example)** | Net/component domain classification | Declared nets/domains/isolators/protective-impedance chains vs. the full compiled netlist | Live: "Checked 39 declared nets across 2 domains ... over 165 compiled nets / 170 components" -- **reports its own ratio unprompted, in every run** | **Yes -- the reference example this whole audit is measured against** | **No.** Live-tested: an empty `domains: {}` manifest exits 5 with `"an empty or absent domain declaration must fail the gate, not pass it vacuously (METHODOLOGY.md Sec 5, anti-vacuous-truth)"` -- explicit, on-the-nose | N/A (declarative manifest, not an allowlist) |
| `check_rust_drc_presence.py` | Presence/freshness of `temper_drc_rs`'s exported symbols | Symbols registered in `lib.rs`'s `#[pymodule]` block vs. the installed module | 1:1 (source-derived expectation vs. runtime reality, by construction) | **Yes** -- "OK: ... symbols [...] all found" names every symbol checked | Unparseable/missing `lib.rs` -> hard fail under `TEMPER_REQUIRE_RUST_DRC=1` (explicit "fails closed... never a silent pass" in the docstring); optional/warn-only otherwise, by explicit design (local dev without Rust toolchain) | N/A (no allowlist; symbol list is source-derived every run) |

---

## Findings ranked by consequence

1. **`check_traceability.py`'s R2/R3 gates cover 1 directory out of the whole
   repo, and say "all requirements are covered" without ever stating that.**
   This is the worst finding in the audit: it is a *requirements
   traceability* gate -- its entire job is to prove coverage -- and its
   headline pass message is indistinguishable from what it would print if
   nobody had opted in to traceability at all, because that is almost
   exactly the current state (1 sentinel file, in a router test directory,
   not in firmware or elec/). Not fixed this pass (would require either
   changing the opt-in model, which is a scope decision the brief's own
   instructions caution against making unilaterally, or at minimum adding a
   denominator line -- recommended as the smallest safe fix, not applied
   here to stay inside the brief's specific mandate).
2. **`check_vacuous_gates.py` itself, fixed this pass.** Ranked second only
   because it is now fixed: 2/13 validator-module coverage, structurally
   blind to `scripts/*.py` entirely (meaning it could never see
   `check_domain_partition.py`, `capacity_budget_gate.py`,
   `mpn_fabrication_gate.py`, `check_derived_doc_drift.py`, or itself,
   regardless of filename). Widened to 526 files; found 13 real violations,
   left red.
3. **`_lib/gate_allowlist.py`'s `TICKET_PATTERN` accepts its own placeholder
   text as a valid ticket.** `TODO:\s*temper-(?:\d+|xxx)` treats the literal
   string `--init` writes (`# TODO: temper-xxx`) as already satisfying the
   "has a ticket" requirement, permanently. Confirmed live:
   `TICKET_PATTERN.search("TODO: temper-xxx")` returns `True`. This defeats
   the one check that was supposed to force human review of anything
   auto-added to `.physics-provenance-allowlist` or `.coverage-allowlist`.
   Currently low-consequence for physics-provenance (allowlist is empty) but
   already fully realized in `check_coverage_gate.py` (1927/1927 entries
   carry the unresolved placeholder). Not fixed: shared code, and tightening
   it would turn a currently-green, actively-managed gate red for a reason
   outside this audit's mandate. Flagged as the clearest follow-up ticket
   this audit produces.
4. **`check_typecheck_gate.py`'s `SCOPE` includes a path that doesn't exist**
   (`packages/temper-tools/src`) and silently drops it via
   `if not scope_path.exists(): continue`. Low consequence here because the
   gate already fails closed if *all* scope paths vanish, and 2/3 present
   paths are the ones that matter (`temper-placer`, `temper-workflow`) --
   but a silently-dropped configured path is the same shape of bug as
   everything else in this audit, just smaller.
5. **`check_fault_list_consistency.py` doesn't report a denominator on
   failure**, and crashes with `NameError` (rather than a clean message) if
   `fault_list_generated.h` is missing while `manifest.json` exists. Both
   still fail closed (non-zero exit either way) -- ranked low because
   nothing passes vacuously, it just fails less gracefully than it could.
6. **`check_script_sunset.py` and `check_manifest_gate.py`** both have minor
   denominator gaps (sunset never states how many entries it checked before
   saying "no stale scripts"; manifest gate's fail path doesn't restate the
   on-disk total). Ranked lowest: sunset is explicitly advisory
   (`continue-on-error` / always-exit-0 by design) and manifest gate's scope
   is a fixed, always-nonempty directory with no way to point it at nothing.

**Already-hardened gates, cited as reference examples, not touched:**
`check_domain_partition.py` (the brief's own gold standard), `mpn_fabrication_gate.py`
(hand-curated allowlist, explicit anti-`--init` design note, full denominator
always), `capacity_budget_gate.py` (full denominator always), `check_typecheck_gate.py`
(call-arg hard gate carved out of `--init`'s reach), `check_undeclared_imports.py`
(disclosed scope exclusions, vacuous-run backstop, per-entry justification
requirement), `check_rust_drc_presence.py`, `import_linter_gate.py`
(hand-edited allowlist, tool-completion-marker check rather than trusting
bare exit code).

---

## What was fixed

### 1. `scripts/check_vacuous_gates.py` -- scope rewrite (mandatory per brief)

**Before:** `find_scope_files()` globbed only `packages/*/src`, then filtered
by `SCOPE_TOKENS = ("gate", "valid")` matched as a **path substring**
(case-insensitive), excluding anything containing `"router_v6"`, `"/tests/"`,
or `"test_"`. Measured: **52 files**, 0 violations, no denominator printed
either way.

Two independent defects, not one:
- **Structural:** `scripts/*.py` was never globbed at all. Every CI gate
  script this audit was asked to review lives in `scripts/`, including
  `check_vacuous_gates.py` itself -- the gate could not have found a defect
  in its own file, or in `check_domain_partition.py`,
  `capacity_budget_gate.py`, `mpn_fabrication_gate.py`, or
  `check_derived_doc_drift.py`, regardless of what their filenames contained.
- **Filter:** a path-substring include-list is simultaneously too broad (a
  directory named `validation/` sweeps in anything under it, coincidentally
  including `scorecard.py` -- so the brief's specific claim that
  `scorecard.py` is skipped does **not** hold under the code as currently
  written; verified directly, not assumed) and too narrow
  (`domain_clearance.py`, `deterministic/feedback/drc_runner.py`, and the
  real validator implementations under
  `packages/temper-placer/tests/requirements/validators/` -- `isolation.py`,
  `emi_filter.py`, `ground_plane.py`, `pick_and_place.py`,
  `routability_check.py`, `clearance_check.py` -- have neither `"gate"` nor
  `"valid"` anywhere in their path, or were excluded by the blanket
  `"/tests/"` substring rule despite not being test files themselves).

**After:** default-include, narrow documented-exclude, three-part union:
`packages/*/src` (recursive) + `packages/*/tests` (recursive, minus files
matching `test_*.py`/`*_test.py`/`conftest.py` by filename, not path
substring) + top-level `scripts/*.py` (non-recursive, so `_lib/`, `tests/`,
`spikes/`, `templates/` are excluded by construction). `router_v6` stays
excluded pending the forced-segment fail-closed plan -- flagged UNVERIFIED
below, not touched, since a concurrent agent is actively working router_v6
code.

**Why default-include over an allowlist:** the brief asks for a mechanism
that isn't a filename-substring include-list. An allowlist of any kind
(explicit file list, or filename/path tokens) requires a maintainer to
remember to add every new validator to it -- exactly the failure mode that
produced 2/13 coverage. A short, documented denylist (test-file naming
convention, one frozen package) only has to name what's *not* in scope; a
new validator module dropped anywhere in scope is scanned with zero action
required. The accepted cost: some non-validator fixture/helper modules under
`packages/*/tests` are now scanned too, but since the detector only flags
unguarded `all()`, a module with no such call produces no output regardless
of whether it "should" have been in scope.

**Files scanned: 52 -> 526** (`460` under packages `src`+`tests`, `66`
top-level `scripts/*.py`). **Violations: 0 -> 13**, across 6 files:

```
packages/temper-placer/src/temper_placer/pcl/_constraint_parser.py:68, :79
packages/temper-placer/src/temper_placer/pcl/tiers.py:81
packages/temper-placer/src/temper_placer/pipeline/dag_expr.py:253
scripts/check_derived_doc_drift.py:197, :201, :216, :405
scripts/ci_identity_check.py:76
scripts/import_linter_gate.py:79
scripts/mpn_fabrication_gate.py:402, :407
scripts/spc_rules.py:51
```

**These are left unfixed, deliberately.** The brief: *"Expect the fixed gate
to find real violations... Report what it finds — do not narrow the scope
back to keep it green."* Fixing 13 call sites across three files this audit
was told must keep exiting 0 on their own invocation
(`check_derived_doc_drift.py`, `mpn_fabrication_gate.py`) is a materially
different, riskier task than a scoping audit, and was not attempted. `check_vacuous_gates.py`
now exits 1; that is reported as the correct, successful outcome of this
fix, not walked back.

Also added: the gate now reports its denominator on both pass and fail
(`"Scanned N file(s) in scope (...)"`), and fails closed if the effective
scope is empty (a `--packages-dir`/`--scripts-dir` combination that matches
zero files now exits 1 with an explicit message, rather than the previous
silent "gate passed" on 0 files -- eating the gate's own dog food).

### 2. `scripts/check_physics_provenance.py` -- denominator + zero-scan fail-closed

Explicitly named in the brief as a "verify" item, not a mandatory fix; fixed
the low-risk part (denominator reporting, requested for any gate touched)
and left the higher-risk part (shared `TICKET_PATTERN`) as a documented
finding rather than a unilateral fix -- see finding #3 above for why.

- Both pass and fail paths now print
  `"Scanned N module-level float constant(s) across M file(s) under <dir>: K undocumented. Allowlist: J entries loaded from <path>."`
  Previously: `"[green]Physics provenance gate passed[/]"` with no counts on
  pass, and nothing at all (just the per-violation FAIL lines) on fail.
- Zero constants found now fails closed (`exit 1`) rather than silently
  reporting "0 undocumented" as a pass with no context. This is a genuine
  behavior change but a defensible one: the real `physics/` directory has 3
  constants across 2 files and will never hit this path in practice; it only
  fires for a misconfigured `--physics-dir` (verified below).
- Verified against the real CI invocation
  (`--allowlist ../../.physics-provenance-allowlist --physics-dir src/temper_placer/physics/`
  from `packages/temper-placer/`) in both default and `--check-shrink` mode:
  still exits 0, output now includes `"Scanned 3 module-level float
  constant(s) across 2 file(s)... 0 undocumented. Allowlist: 0 entries..."`

---

## Verification

### Falsifier: did NOT fire (see above) -- widening found 13 real violations.

### Fail-closed proofs, `check_vacuous_gates.py`

| Test | Command | Result |
|---|---|---|
| Missing `--packages-dir` | `--packages-dir <nonexistent>` | `Packages directory not found: ...` / exit 1 |
| Empty `--packages-dir` + empty `--scripts-dir` (both exist, no matching files) | `--packages-dir <empty dir>` `--scripts-dir <empty dir>` | `FAIL (closed): Scanned 0 file(s) in scope ... An anti-vacuous-truth gate that scans zero files cannot report a meaningful pass` / exit 1 |
| Zero-match scope (`--scripts-dir` nonexistent, `--packages-dir` empty) | as above | Same fail-closed message / exit 1 |
| Real repo, default args | `python3 scripts/check_vacuous_gates.py` | exit 1, 13 violations, `Scanned 526 file(s) in scope ...` |

### Fail-closed proofs, `check_physics_provenance.py`

| Test | Command | Result |
|---|---|---|
| Empty `--physics-dir` (exists, 0 constants) | `--physics-dir <empty dir>` | `FAIL (closed): Scanned 0 module-level float constant(s) across 0 file(s)... cannot report a meaningful pass` / exit 1 |
| Missing `--physics-dir` | `--physics-dir <nonexistent>` | `Physics directory not found: ...` / exit 1 |
| One undocumented constant (synthetic) | `--physics-dir <dir with 1 bad const>` | `FAIL: .../const.py::UNDOCUMENTED_CONST:1 ...` + `Scanned 1 module-level float constant(s) across 1 file(s)... 1 undocumented. ... FAILED.` / exit 1 |
| Real repo, both CI invocations | default mode + `--check-shrink`, from `packages/temper-placer/` | Both exit 0, denominator now printed |

### Protected-gate exit codes, before and after these changes

All four required to stay at their current state -- confirmed unchanged
(these gates were not modified; verified only that my `check_vacuous_gates.py`/
`check_physics_provenance.py` edits have no effect on them):

| Gate | Exit code |
|---|---|
| `make netlist` | 0, **76** assertion rows (confirmed by counting PASSED/FAILED rows in the build output) |
| `check_domain_partition.py` | 0 (after `make netlist`; was 5 with "netlist not found" before -- expected, `elec/build/` is gitignored) |
| `capacity_budget_gate.py` | 0 (same netlist dependency) |
| `mpn_fabrication_gate.py` | 0 |
| `check_derived_doc_drift.py` | 0 |

No files under `pcb/temper.kicad_pcb`, `elec/domain_manifest.yaml`,
`domain_clearance.py`, or `elec/src/*.ato` were modified.

---

## UNVERIFIED

- **Whether the `router_v6` exclusion in `check_vacuous_gates.py` is still
  current.** Its docstring cites "the forced-segment fail-closed plan." In
  this worktree, `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`
  has `status: superseded`; a different worktree's commit message (not on
  this branch) claims the plan's units all shipped. Not resolved here --
  `router_v6` is actively being worked by a concurrent agent per this
  session's own instructions, and lifting a freeze on code someone else is
  mid-edit on is out of scope for a scoping audit.
- **`import_linter_gate.py`'s actual current pass/fail state.** Could not
  get a clean run in this environment: both a bare `python3` and `uv run`
  invocation fail with `Could not find package 'temper_placer' in your
  Python path` (exit 5, itself a correct fail-closed tool-error response --
  not a vacuous pass). This looks like a pre-existing environment/build gap
  (likely needs a `maturin develop` step for the Rust extensions) rather
  than anything this audit touched; not chased further.
- **`check_coverage_gate.py`'s live shrink-to-zero behavior.** Verified by
  code reading only (`if not args.coverage_json.exists(): sys.exit(1)`,
  `if not files: sys.exit(1)`) -- not exercised against a live
  `coverage.json`, which requires a full pytest+coverage run not attempted
  in this pass.
- **The exact current pass/fail state of `check_derived_doc_drift.py`
  beyond its own exit code.** Confirmed exit 0 (protected requirement) and
  confirmed it contains 4 of the 13 newly-surfaced `check_vacuous_gates.py`
  findings; did not independently re-derive its own scope/denominator
  properties given time constraints and that it is explicitly a "must stay
  exit 0" file this audit was told not to destabilize.
- **Whether `packages/temper-tools/src`** (configured in
  `check_typecheck_gate.py`'s `SCOPE` but absent from this tree) is a
  package that was removed/renamed, or one that hasn't been created yet.
  Either way it is silently skipped rather than flagged; not chased further
  since the gate already fails closed if *all* scope paths vanish.
