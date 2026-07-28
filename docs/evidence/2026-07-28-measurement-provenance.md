# Measurement-provenance contract: content-hash freshness for derived artifacts

<!-- provenance: commit=bf7ab435578367f3ec91d2d084be34c0e8a992bd dirty=true -->

**Date:** 2026-07-28
**Base commit:** `60d441f2` (branch `docs/methodology-loop-discipline`), worked in an isolated worktree, new branch `feat/measurement-provenance-contract`.

## What was built

A provenance contract for **measurement artifacts** -- files that record a
number computed from specific input files, as distinct from evidence prose
(already covered by `scripts/check_evidence_provenance.py`, which stamps
*commit* on the *writing* file, not content hash on the *measured* file).

New files:

- `scripts/_lib/measurement_provenance.py` -- the freshness oracle:
  `sha256_file`, `check_inputs_fresh`, `build_provenance`,
  `validate_provenance_shape`. Full design rationale (content hash vs
  mtime, what belongs in a record, "no provenance yet" handling) is in its
  module docstring.
- `scripts/check_measurement_provenance.py` -- the CI gate. Reads a small,
  explicit registry (`MEASURED_ARTIFACTS`, currently just
  `power_pcb_dataset/drc_ceiling.json`), extracts every measurement record
  (generic across a single top-level `provenance` object or a list of
  per-item records, covering the ceiling file's `boards[]` shape), and for
  each declared input recomputes its current content hash and compares
  against what was recorded. A mismatch is **STALE**, bucketed as a GATE
  ERROR (exit 5) -- never a "violation" -- generalizing the exact
  `check_domain_partition.py` precedent: *"netlist is STALE ... GATE
  RESULT: ERROR -- not PASSED, not a violation."* This gate never
  re-derives the underlying measurement (it does not re-run DRC), so it
  has no separate violation class -- STALE, missing/malformed provenance,
  a malformed artifact, and a vacuous (zero-record) scan are all distinct,
  individually-labeled reasons that collapse to the same exit code, same
  as `check_domain_partition.py`'s own `GateError` bucket.
- `.measurement-provenance-allowlist` -- modeled on
  `.evidence-provenance-allowlist`: `<artifact>#<record-id>  # TODO:
  temper-xxx`, monotonically shrinking via `--check-shrink` against
  `origin/main`, reusing `scripts/_lib/gate_allowlist.py`. Currently
  **zero entries** -- the one artifact in scope
  (`power_pcb_dataset/drc_ceiling.json`) now has real provenance, so
  nothing needed allowlisting.
- `scripts/tests/test_check_measurement_provenance.py` (23 tests) and
  `scripts/tests/_lib/test_lib_measurement_provenance.py` (16 tests) -- 39
  new unit tests total, all passing.

Wired into `scripts/manifest.yaml` (total_scripts 71->72) and
`.github/workflows/python-tests.yml`, no `continue-on-error`. The new step
is placed **last** among the required-gate steps in the `test` job
(after domain-partition, rust-drc-presence, stale-extensions,
undeclared-imports, net-classification, pll-range, mpn-fabrication,
derived-doc-drift, capacity-budget) so its expected, honest failure does
not prevent any of those from running in the same CI job -- only the
non-gating "Rebuild script invocation graph" bookkeeping step after it is
skipped as a result.

## `drc_ceiling.json`: provenance added, ceiling untouched

Per the hard rule, no ceiling value was re-measured or changed. `git diff`
confirms the only change is an added `"provenance"` object on the
`"temper"` board entry, plus one new `_march` note explaining the addition:

```
"provenance": {
  "measured_at_commit": "3c391956f39165f41306591292a33dd3e3e174ee",
  "dirty": "UNKNOWN",
  "inputs": [
    {"path": "pcb/temper.kicad_pcb",
     "sha256": "23dbc050ae5de3285924d9ec02ac3bd94e68bf1f6b76f4f4b78786b59f6f7249"}
  ],
  "tool_versions": {"kicad-cli": "UNKNOWN"},
  "source": "backfilled-historical"
}
```

`measured_at_commit` is `3c391956` -- the commit that actually last wrote
these ceiling numbers (`_march["2026-07-27b"]`, ratcheting three
categories and holding two). Verified `3c391956`'s board content is
identical to `043debdf` (the board the `_march` note says was measured):
`git diff 043debdf 3c391956 -- pcb/temper.kicad_pcb` is empty, since
`3c391956` only edited the JSON. The recorded hash is
`git show 3c391956:pcb/temper.kicad_pcb | sha256sum`, i.e. the exact
committed content, not a guess. `dirty` is honestly `"UNKNOWN"`: the
committed content is exact and reproducible, but whether the person who
ran the DRC measurement also had unrelated uncommitted changes in their
own tree at that moment cannot be recovered from git history after the
fact, and recording `false` would be fabricating certainty this
reconstruction does not have. `tool_versions.kicad-cli` is likewise
`"UNKNOWN"` -- no record of which binary version produced these specific
numbers survives; a future live measurement (`build_provenance(...,
tool_versions={"kicad-cli": subprocess-queried-version})`) would capture
this going forward.

Running the new gate against the real repo at this base commit reports
exactly what the discrepancy write-up already found by hand
(`docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md`):

```
$ uv run --no-sync python scripts/check_measurement_provenance.py
GATE RESULT: ERROR -- not PASSED, not a violation. 1 stale record(s), 0 problem(s).
Measurement-provenance gate -- 1 artifact(s) registered, 1 record(s) found across them (the denominator is never a subset).
  fresh=0 stale=1 allowlisted-unprovenanced=0 problem(s)=0
  [STALE] power_pcb_dataset/drc_ceiling.json#boards.temper: 1 input(s) moved since measurement
          pcb/temper.kicad_pcb: content hash changed since measurement -- the input moved
exit=5
```

This is the honest outcome named in the task: three commits since
`3c391956` (`c6b1b463`, `556ccf4f` -- first committed route, `65bd0159`)
changed `pcb/temper.kicad_pcb`'s content (current hash
`81551208...098ef1`, confirmed via `git show 60d441f2:pcb/temper.kicad_pcb
| sha256sum`, matching the discrepancy doc's own citation), and the
ceiling was never re-measured. The gate now says so mechanically instead
of requiring someone to notice by hand.

## Falsifier

> "This contract would have caught all three historical cases. Prove it:
> reconstruct each -- a ceiling whose recorded board hash no longer
> matches, a measurement citing an artifact hash that has moved -- and
> show the gate FAILS on each, then PASSES once provenance is current."

**The falsifier did NOT fire -- the mechanism catches all three, and both
states (FAIL then PASS) are demonstrated without `git stash`.**

### Case 1 -- the DRC ceiling measured a board that no longer existed

Demonstrated two ways:

1. **Against the real repo** (above): the gate reports the real
   `drc_ceiling.json` STALE, exit 5, for exactly the reason the
   discrepancy investigation found by hand.
2. **Synthetic reconstruction**,
   `TestFalsifierDrcCeilingReconstruction.test_stale_board_fails_then_passes_once_remeasured`
   (`scripts/tests/test_check_measurement_provenance.py`): writes a
   tmp_path board file, records its hash in a ceiling-shaped JSON, then
   overwrites the board file (simulating the three route-changing
   commits) -- `evaluate()` reports it `stale`. The **same** fixture is
   then re-provenanced with `build_provenance()` against the now-current
   board content, and `evaluate()` reports it `fresh` -- FAIL then PASS,
   same object, only the provenance re-measurement changed. No `git
   stash` anywhere; both states are plain file writes in a temp
   directory.

### Case 2 -- a measurement citing an artifact hash that has moved

`temper_rust_router`'s `.so` was installed 2026-06-29 while its source
moved to 2026-07-27 (`docs/evidence/2026-07-27-stale-extension-first-run.md`).
`check_stale_extensions.py` already catches *that specific* case (compiled
artifact vs. its own source, by mtime -- appropriate there because the
project's workflow guarantees "build happens after checkout", as that
gate's own docstring argues). What this task's contract adds is the
*general* mechanism for **any** measurement artifact that cites an input
hash, regardless of what kind of input it is. Reconstructed generically in
`test_second_artifact_hash_moved_generalizes_beyond_drc`: a synthetic
"routing baseline" JSON records the content hash of a router-source
snapshot file; the file is then edited (simulating the June 29 -> July 27
drift); `evaluate()` reports it stale, via the identical code path used
for the DRC ceiling. The mechanism generalizes; only the artifact's own
registration (adding its path to `MEASURED_ARTIFACTS`) is new work for a
future routing/benchmark baseline, not the freshness logic itself.

### Case 3 -- evidence documents citing numbers whose inputs have moved

`check_evidence_provenance.py` (pre-existing, wired) already answers
"does this evidence file declare the commit it was measured at" for
`docs/evidence/*` prose -- e.g.
`docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md`, which cites
`drc_ceiling.json`'s numbers directly. That gate's commit-stamp alone
would **not** have caught this incident: the *evidence doc* was written
at a real, current commit; it was the *ceiling file it cited* whose
content-relevant input had moved three commits earlier, invisible to a
commit-only stamp on the doc itself. `check_measurement_provenance.py`
closes exactly that gap for any measurement artifact an evidence doc
might cite, demonstrated by the same drc_ceiling.json case above -- the
two gates are complementary, not redundant: one stamps the *writer*, the
other stamps the *measured input*.

## Verification

All of the following ran from this worktree, `feat/measurement-provenance-contract`,
after `make netlist` and a from-scratch `uv sync --all-packages` +
`maturin`-built extensions (venv had to be rebuilt from empty -- see
UNVERIFIED).

**The ten gates named in the task, N=10/10 exit 0:**

| Gate | Exit |
|---|---|
| `check_domain_partition.py` | 0 |
| `capacity_budget_gate.py` | 0 |
| `mpn_fabrication_gate.py` | 0 |
| `check_derived_doc_drift.py` | 0 |
| `check_copper_net_consistency.py` | 0 |
| `check_rust_drc_presence.py` | 0 |
| `check_undeclared_imports.py` | 0 |
| `check_stale_extensions.py` | 0 (9/10 extensions fresh, 1 missing/WARN-only -- `temper_constraints` not built locally; not required outside CI) |
| `check_net_classification.py` | 0 |
| `check_pll_range_consistency.py` | 0 |

**This task's new gate, honest failure:**

| Gate | Exit | Reason |
|---|---|---|
| `check_measurement_provenance.py` | 5 | 1/1 record STALE: `drc_ceiling.json`'s board provenance no longer matches `pcb/temper.kicad_pcb`'s current content (see above) |
| `check_measurement_provenance.py --check-shrink` | 5 (same STALE finding; shrink-check itself soft-skips: `origin/main` predates this file) | |

**Also verified:**

- `make netlist` -- exit 0, builds `elec/build/default.net` successfully.
- `uv run --no-sync python -m pytest elec/validation -q` -- **30/30 passed**.
- `uv run --no-sync pytest scripts/tests/test_check_measurement_provenance.py scripts/tests/_lib/test_lib_measurement_provenance.py -v` -- **39/39 passed**.
- `scripts/check_vacuous_gates.py` -- exit 0, 537 files scanned, 0 violations (confirms the new library/gate code contains no unguarded `all()`; `validate_provenance_shape`'s SHA-shape check was rewritten as an explicit loop specifically to avoid this, documented in its own docstring).

## Pre-existing gaps noticed, not fixed (out of scope for this task)

Found while running the required verification; none introduced by this
change (confirmed via `git diff 60d441f2 HEAD` touching neither file):

- `scripts/check_manifest_gate.py` exits 3: `check_copper_net_consistency.py`
  has no `scripts/manifest.yaml` entry at all, and is not wired into any
  CI workflow (`grep -rn check_copper_net_consistency .github/workflows/`
  returns nothing). It is one of the task's ten required gates and was
  run and verified directly (exit 0); its manifest/CI wiring is a
  separate, pre-existing gap this task did not introduce and was not
  asked to fix -- flagged here rather than silently worked around.
- `scripts/vulture_gate.py` exits 3: one pre-existing NEW-dead-code
  finding in `packages/temper-placer/tests/requirements/safety/_real_board_fixture.py:115`
  (`GateError`), in a file this task never touched (`git diff 60d441f2
  HEAD -- packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`
  is empty).
- `scripts/check_evidence_provenance.py` exits 3: several pre-existing
  `docs/evidence/*.md` files (e.g. `2026-07-28-drc-ratchet-enumeration.md`,
  `2026-07-28-pll-ratio-tracking-check.md`, `2026-07-28-stackup-partial-revert.md`,
  `2026-07-27-zvs-operating-point.md`) carry no `provenance:` line at all --
  confirmed present with zero provenance lines already at base commit
  `60d441f2` (`git show 60d441f2:docs/evidence/2026-07-28-drc-ratchet-enumeration.md`).
  This file (`2026-07-28-measurement-provenance.md`) itself carries a
  valid provenance line and is not among the reported failures. Not in
  this task's scope (evidence-doc commit-stamp backlog, not the
  content-hash measurement contract this task builds).

## UNVERIFIED

- This worktree's `.venv` was corrupted on first `uv sync --all-packages`
  (missing `python`/`python3` symlinks, `pyvenv.cfg` absent) and had to be
  deleted and recreated with `uv venv --python 3.12` before syncing
  succeeded. Not investigated further (environment artifact of the
  worktree setup, unrelated to any code in this change) -- noted in case
  it recurs for another agent in a sibling worktree.
- Whether `power_pcb_dataset/drc_ceiling.json`'s `91`/`85` numbers were
  originally measured with the `kicad-cli` or `rust` (`temper_drc_rs`)
  backend is not established from git history alone (both exist in
  `DrcRatchet`); `tool_versions` is recorded as `"UNKNOWN"` rather than
  guessed, per the module's own design decision on honest unknowns.
- `check_measurement_provenance.py --check-shrink`'s monotonic-shrink
  enforcement against `origin/main` was only exercised via its soft-skip
  path (the allowlist file does not exist on `origin/main` yet, since
  this is a new file on an unmerged branch) -- the shrink-violation
  branches (`--init`-populated additions without a ticket, entries
  removed without the underlying record gaining real provenance) are
  covered by unit tests (`TestEvaluate`) exercising `evaluate()` directly,
  but the `--check-shrink` CLI path itself against a real `origin/main`
  diff was not end-to-end exercised (mirrors `check_evidence_provenance.py`'s
  own soft-skip precedent, not a gap introduced by this design).
