# Schematic/source drift gate: diagnosis, not a new checker

**Date:** 2026-07-26
**Scope:** `scripts/gen_schematics.py`, `.github/workflows/python-tests.yml`'s
"Regenerate schematics and check drift" step, `elec/build/default.net`,
`elec/build/default.csv`.
**Status:** diagnosis complete. No new checker built. This document is the
deliverable.

---

## Re-scope, stated up front

This task started as "build a new CI gate to catch `.ato` vs `.kicad_sch`
drift, using the OVP-01 R51/R52/R53/R55/R57/R58 defect as the motivating
fixture." Partway through, a coordinator review found that a gate for
exactly this purpose already exists and is already wired into CI:

```yaml
      - name: Regenerate schematics and check drift
        continue-on-error: true  # TODO: temper-NNN -- make netlist (atopile) invokes kicad-cli in container; hard-fail after 2026-09-01
        run: |
          uv run python3 scripts/gen_schematics.py --check --no-oracle
          git diff --exit-code pcb/*.kicad_sch
```

Building a second, parallel checker next to a working-but-neutered one would
have been worse than the disease. The task was re-scoped to: **does this
gate actually work, and if not, precisely why not.** It does not, for three
independent reasons, only one of which is the `continue-on-error: true`
this task started from. All three are reported below with real command
output.

---

## Finding 1 — `continue-on-error: true` (known going in)

The step is `continue-on-error: true` with a placeholder `temper-NNN` ticket,
so even a real failure never blocks a merge. This was the premise of the
original task and is confirmed correct as far as it goes, but it is not the
whole story (see Findings 2 and 3).

## Finding 2 — CI-only git-ownership failure (reported by coordinator, not independently reproduced here)

The coordinator identified, and fixed on the parent branch (commit
`84eeb51c`, not present in this worktree since it branched earlier), a
second, independent kill mechanism: the `test` job runs inside
`container: ghcr.io/bennetleff/temper-ci:latest` with `--user root`, while
`actions/checkout` marks the repo safe only under its own runner-user
`HOME`. `git diff --exit-code pcb/*.kicad_sch`, run as root, hit `fatal:
detected dubious ownership` and exited 128 — a git plumbing error, not a
drift verdict. Combined with Finding 1, the step could not have reported
drift even if `gen_schematics.py --check` itself worked perfectly.

**This failure mode is CI-only.** It was not and could not be reproduced in
this local worktree, which has normal file ownership. A passing local run
(Finding 3 below) proves the *checker* is exercised correctly, not that the
*gate* was ever functioning in CI before commit `84eeb51c`.

## Finding 3 — the checker itself is blind to this exact defect class (the real finding)

This is the one that matters: **even with Findings 1 and 2 both fixed**,
running the checker's actual logic locally against today's tree —
real command, real output, no fixture, no edits to `elec/src/*.ato` or
`pcb/*.kicad_sch` —

```
$ make netlist
...
Build complete!

$ uv run python3 scripts/gen_schematics.py --check --no-oracle
Reading netlist: elec/build/default.net
  167 components, 160 nets, 40 unique parts
Regenerating to temp dir: /var/folders/.../tmp3637rsjn
Skipping oracle (--no-oracle)
Diffing against committed schematics...
CHECK PASS: all schematics match netlist
```

Exit 0. **"CHECK PASS" is a false clean.** The R51/R52/R53/R55/R57/R58
drift documented in this task's brief is real and present in this tree at
the moment this ran (nothing was fixed to produce this result). Confirmed
directly with a persistent output dir instead of the checker's temp dir, so
the regenerated file could be inspected and diffed by hand:

```
$ uv run python3 scripts/gen_schematics.py --no-oracle --output-dir /tmp/gen_check
...
$ diff -u pcb/safety_interlock.kicad_sch /tmp/gen_check/safety_interlock.kicad_sch
(no output -- files are byte-identical)

$ grep -A1 'Reference" "R51"' /tmp/gen_check/safety_interlock.kicad_sch
    (property "Reference" "R51" ...)
    (property "Value" "RC1206FR-07220KL" ...)
```

`elec/src/modules.ato:1739-1743` currently sets
`r_div_top1.mpn = "RC1206FR-07430KL"` (430 kΩ). The freshly-regenerated
schematic — produced from today's netlist, built from today's `.ato`
source, right now, in this run — still says `RC1206FR-07220KL` (220 kΩ).
The generator itself cannot see the source value that changed.

### Root cause

`gen_schematics.py`'s `_symbol_instance()` writes the schematic's `Value`
property from `comp.part_name` (`gen_schematics.py:434-436`, passed in from
`generate_sheet` at `gen_schematics.py:654`), which is populated from the
**netlist's `libsource` `part` field** (`_part_name_from_libsource`,
`gen_schematics.py:174-177`, consumed at `gen_schematics.py:234-236`).
`comp.value` — the netlist's actual `value` field — is parsed
(`gen_schematics.py:228`) but never used for anything; it is always the
literal string `"?"` in atopile's export, confirmed directly:

```
$ grep -n '(value "' elec/build/default.net | sort -u | head -3
      (value "?")
```

The `libsource part` field is exactly the field `docs/STRATEGY.md`'s
"`default.net` aliases part identity by footprint — use `default.csv`"
entry (2026-07-26) already documented as unreliable: atopile's netlist
exporter collapses every component sharing a footprint onto one canonical
libpart. Confirmed directly for the six drifted parts:

```
$ grep -n 'safety.ovp.r_div_top1\|safety.ovp.r_ref_top\|safety.ovp.r_hyst\|safety.ovp.r_adc_top' elec/build/default.net
      (libsource (lib "lib") (part "RC1206FR-07220KL") ...)   # R51 = r_div_top1, true value 430k
      ...
      (libsource (lib "lib") (part "RC0603FR-0710KL") ...)    # R55 = r_ref_top,  true value 1.1k
      (libsource (lib "lib") (part "RC0603FR-0710KL") ...)    # R57 = r_hyst,     true value 287k
      (libsource (lib "lib") (part "RC1206FR-07220KL") ...)   # R58 = r_adc_top,  true value 510k

$ grep -n 'R51\|R55\|R57\|R58' elec/build/default.csv
RC1206FR-07430KL,"R51,R52,R53",Resistor_SMD:R_1206_3216Metric,...
RC0603FR-071K1L,R55,Resistor_SMD:R_0603_1608Metric,...
RC0603FR-07287KL,R57,Resistor_SMD:R_0603_1608Metric,...
RC1206FR-07510KL,R58,Resistor_SMD:R_1206_3216Metric,...
```

`default.csv` — sourced from the same build, same instant — has the
correct, per-designator value for every one of these six parts.
`default.net`'s `libsource` does not, for any of them. `gen_schematics.py`
reads only `default.net`, and only its `libsource` field, for the `Value`
property it writes and diffs. It never reads `default.csv`.

**Consequence, stated precisely:** the checker's own "regenerated ground
truth" is built from the same aliased field that produced the stale
committed schematic in the first place. A diff between "aliased value,
computed today" and "aliased value, computed whenever the schematic was
last generated" is clean **whenever the footprint-level canonical MPN for
that footprint hasn't changed** — which is true here, since other
components elsewhere in the design still legitimately use
`RC1206FR-07220KL` (1206 footprint) and `RC0603FR-0710KL` (0603 footprint)
as their real value. The diff is not merely weak on this defect; it is
**structurally incapable of ever catching a value-only change to a
resistor or capacitor that shares its footprint with any other component
in the design** — which on this board means essentially every passive,
since `R_0603_1608Metric` and `R_1206_3216Metric` are the two standard
passive footprints used throughout. This is not a narrow edge case; it is
the checker's blind spot for the exact defect category this task exists to
catch.

**What the checker can still catch**, for completeness: structural changes
— added/removed components, footprint changes, connectivity/net-topology
changes, reference/designator changes — since those are reflected in fields
outside the aliased `libsource.part` string. It is not a no-op gate; it is
a gate with one specific, large, and currently-live blind spot.

---

## Falsifier and result

**Falsifier, stated before running anything:** if `gen_schematics.py
--check --no-oracle` reports `CHECK PASS` against the current tree (which
carries the real, uncorrected OVP-01 drift from this task's brief), the
existing gate does not do the job Finding 1's `continue-on-error` removal
alone would imply, and the defect is in the checker, not only in CI wiring.

**Result: it fired.** `CHECK PASS`, exit 0, against a tree with six live,
uncorrected value drifts. See Finding 3 above for the full commands and
output. Nothing in `elec/src/*.ato` or `pcb/*.kicad_sch` was edited to
produce this result, per the task's constraint.

---

## Recommendation

1. **Un-neutering `continue-on-error` alone is not sufficient** and would
   give false confidence — the step would still report `CHECK PASS` on
   today's tree, silently, because Finding 3 is independent of Finding 1
   and Finding 2.
2. **The fix belongs in `gen_schematics.py`, not in the workflow file.**
   Concretely: the `Value` property written in `_symbol_instance` (and
   compared in `--check` mode) needs to come from a per-designator source
   that isn't footprint-aliased — `elec/build/default.csv`'s
   `Comment`/`Designator` columns (already proven reliable by this
   diagnosis and independently by `docs/STRATEGY.md`'s prior finding), not
   `default.net`'s `libsource.part`. This is a small, targeted change
   (change what one field is sourced from, in one function), not a rewrite
   of the generator.
3. Sequencing, once (2) lands: fix or confirm the ownership fix from
   commit `84eeb51c` covers this job (it does, per the coordinator's
   report), then remove `continue-on-error: true` from this step with a
   real cutover date, following the `CUTOVER_DATE` soft-launch pattern
   already used by `scripts/import_linter_gate.py` and
   `scripts/check_derived_doc_drift.py` elsewhere in this repo.
4. **Not done here, deliberately**: implementing (2). The coordinator's
   redirect was explicit that the deliverable for this pass is the
   diagnosis, not a larger change to the generator, so the fix is
   characterized precisely above rather than attempted partially.

### Status update — recommendation (2) landed

Item 2 was implemented immediately after this diagnosis, in the commit that
carries this line. `gen_schematics.py` now sources the `Value` property from
`elec/build/default.csv` via `load_bom_values()` / `apply_bom_values()`, and
refuses to emit a symbol without one rather than falling back to the aliased
`libsource.part`.

Measured result on the tree as of this commit:

    $ uv run python3 scripts/gen_schematics.py --check --no-oracle
    CHECK FAIL: 6 of 7 schematic(s) drifted from the netlist: half_bridge,
    mcu, power_input, power_management, safety_interlock, sensing
    exit 1                          # was: "CHECK PASS", exit 0

All six OVP-01 designators are now caught (R51/R52/R53 → `RC1206FR-07430KL`,
R55 → `RC0603FR-071K1L`, R57 → `RC0603FR-07287KL`, R58 → `RC1206FR-07510KL`),
matching `elec/src/modules.ato` exactly. The blast radius is wider than
OVP-01: five further sheets carry the same aliasing, including C27, which the
committed schematic had labelled with its neighbour's `C0603C104K5RACTU`
instead of its own `GRM1885C1H104JA01D`.

Items 1 and 3 remain open and are deliberately not done: `continue-on-error:
true` is still on the step, so the gate reports but does not block. Removing
it is a separate decision, and it should be taken together with the question
of whether to regenerate the six drifted schematics.

## What was not verified

- Whether `make netlist` / `gen_schematics.py --check --no-oracle` runs
  successfully inside the actual
  `ghcr.io/bennetleff/temper-ci:latest` container (network access for
  `uv tool run --from 'atopile>=0.2,<0.3' ato ...` to resolve the atopile
  package, in particular). It ran to completion locally, without invoking
  `kicad-cli` at any point when `--no-oracle` is passed (the only
  `kicad-cli` call in this script is inside `oracle_verify`, which
  `--no-oracle` skips entirely) — so the TODO comment's stated reason
  ("make netlist (atopile) invokes kicad-cli in container") does not match
  what was observed locally. Whether the container has a different,
  real blocker (e.g. no network egress for `uv tool run` to fetch
  atopile) was not tested from this worktree and is flagged as
  unverified rather than assumed either way.
- Whether `oracle_verify` (skipped here via `--no-oracle`) would add any
  value once Finding 3's `Value`-sourcing defect is fixed. It checks
  connectivity-partition round-trip fidelity of the generator itself, not
  committed-vs-source drift, so it is orthogonal to this defect either way.
