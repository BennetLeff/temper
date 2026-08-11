# FREEZE (U4/U5) measurement — the production-Python metric does not move, and why

**Date:** 2026-08-11
**Scope:** U4 (build the FREEZE tooling) and U5 (retire the first oracle batch), from
`docs/plans/2026-08-11-003-feat-migration-pipeline-wire-and-retire-plan.md`.
**Branch:** `feat/oracle-freeze-and-retire`.

## Headline finding, stated first because the plan asked for honesty here

`docs/plans/2026-08-11-003-...md` U5 says: *"Report the number honestly — the value of
this plan is a decreasing production-Python figure, and if U5 does not move it, the
approach is wrong."* Measured with the repo's own definition
(`scripts/check_migration_narrowing.py::production_py_files`):

| | files | LOC |
|---|---:|---:|
| Session-start baseline (`origin/main` when this work began) | 665 | 172,296 |
| This PR's immediate parent commit (`origin/main` moved during the session — an unrelated concurrent merge, +1 file/+212 LOC, not caused by this PR) | 666 | 172,508 |
| After this PR (rebased onto that parent) | 670 | 173,340 |
| **This PR's own delta** (measured against its immediate parent, isolating concurrent drift) | **+4** | **+832** |

The two measurement points 172,296 and 172,508 both predate this PR's own changes; the
+4 files/+832 LOC delta is identical either way (verified via a throwaway
`git worktree add -f --detach <tmp> HEAD~1` measurement) — it is entirely this PR's own
tooling, not an artifact of which `origin/main` snapshot is used as the comparison point.

**The production-Python figure went UP, not down, and the reason is structural, not a
mistake in this PR's execution:**

1. `production_py_files()`'s own exclusion filter (`_is_test_path`: any path containing
   `/tests/`) already excludes **every** `_py_oracle.py` file before this PR touches
   anything — all 159 of them live under `packages/*/tests/**`. Deleting one (this PR
   deletes `packages/temper-placer/tests/io/_copper_reach_py_oracle.py`, 28 lines) and
   trimming its differential test (`test_copper_reach_rust_differential.py`, 114 → 62
   lines, -52 lines of oracle-comparison Python) removes real Python from the repository,
   but **removes zero lines from the `production_py_files()` count**, because none of
   those lines were ever counted in it. Verified directly: `production_py_files(root)`
   filtered for `_py_oracle` or `/tests/` returns **zero files**, before or after this PR.
2. The U4 tooling this task was asked to build
   (`scripts/gen_oracle_freeze.py`, `scripts/_lib/oracle_freeze.py`,
   `scripts/oracle_freeze_specs/__init__.py`, `scripts/oracle_freeze_specs/copper_reach.py`
   — 832 LOC total, matching the delta exactly) lives under `scripts/`, one of
   `production_py_files()`'s three scan roots (`PRODUCTION_PY_ROOTS = ("packages",
   "scripts", "tools")`). By the repo's own definition — the same one that already counts
   `scripts/gen_wasm_test_registry.py`, `scripts/check_oracle_hashes.py`, and every other
   generator/gate script as "production Python" — this tooling **is** production Python.
   Building the retirement mechanism itself is therefore the entire explanation for the
   +832 delta.

**Conclusion:** FREEZE-class oracle retirement is invisible to `production_py_files()` by
construction, in both directions — an oracle deletion can never lower it (oracles were
never in it), and the tooling that makes retirement possible necessarily raises it (the
tooling is not test code, it has to live somewhere real and reviewable, and `scripts/` is
where every comparable generator in this repo already lives). The plan's stated success
metric measures **Stage 7 (wire)** progress — deleting dead *production* Python
implementations, U2/U3's job — not **Stage 8 (retire)** progress. This is not a case for
walking back U4/U5; it is a case for the plan's own retirement-bar language (U1, not
touched by this PR per its scope boundary) to state a metric that Stage 8 can actually
move. The honest per-oracle metric is below.

## The metric that DOES move: the oracle bucket itself

`_py_oracle.py` files under `packages/*/tests/**` (this repo's own `docs/evidence/
2026-08-11-python-deprecation-inventory.md` bucket 5.1):

| | files | LOC |
|---|---:|---:|
| Baseline (`origin/main`) | 159 | 51,117 |
| After this PR | 158 | 51,089 |
| **Delta** | **-1** | **-28** |

Plus the differential test's oracle-comparison code (not itself an oracle file, but
retired in the same commit because its only job was comparing against the now-deleted
oracle): `test_copper_reach_rust_differential.py` 114 → 62 lines (-52 LOC). The wiring
check that file also carries (`test_shipped_module_delegates_to_rust`, a Stage 7 concern,
not Stage 8) is unchanged.

**Total real Python deleted by this PR: 80 LOC** (28 oracle + 52 differential), against
832 LOC of new, reusable, general-purpose tooling that makes every future FREEZE cost
close to zero marginal LOC (a new spec module, not a new generator).

## Reproduction

```bash
# production_py_files() before/after (checkout origin/main vs this branch):
python3 -c "
import sys, pathlib
sys.path.insert(0, 'scripts')
from check_migration_narrowing import production_py_files
fs = [str(f) for f in production_py_files(pathlib.Path('.'))]
print(len(fs), 'files', sum(len(open(f, errors='ignore').readlines()) for f in fs), 'LOC')
"

# Confirm zero oracle/test files are ever counted:
python3 -c "
import sys, pathlib
sys.path.insert(0, 'scripts')
from check_migration_narrowing import production_py_files
fs = [str(f) for f in production_py_files(pathlib.Path('.'))]
print('oracle/test hits:', len([f for f in fs if 'py_oracle' in f or '/tests/' in f]))
"

# Oracle bucket count (works against any ref):
git ls-tree -r <ref> --name-only | grep -c '_py_oracle\.py$'
```

## What was retired, and the non-vacuity numbers it cleared

`io/real_board.py::_copper_reach_mm` (kernel: `packages/temper-geometry/src/
copper_reach.rs :: copper_reach_mm`). Chosen because both the oracle and the
differential were unchanged for 863 commits, and the kernel for 182 commits — far past
the plan's 10-consecutive-commit R19-shaped bar — and it is explicitly not a safety
kernel (not creepage/clearance/via-keepout geometry; the only production caller is
`io/real_board.py`'s router-hot-path bounding-radius computation) and has no
host-facility/entropy dependency.

`scripts/gen_oracle_freeze.py --spec copper_reach` corpus (56 cases: 16 curated
edge/named cases + 40 seeded-random volume cases), non-vacuity report:

```
  [PASS] nan_present: 19/56 (>=10%)
  [PASS] inf_present: 6/56 (>=1)
  [PASS] multi_pad: 38/56 (>=40%)
  [PASS] negative_offset: 37/56 (>=15%)
  [PASS] near_tie: 1/56 (>=1)
  [PASS] empty: 1/56 (>=1)
  [PASS] shape_circle: 17/56 (>=1)
  [PASS] shape_oval: 14/56 (>=1)
  [PASS] shape_rect: 22/56 (>=1)
  [PASS] shape_roundrect: 17/56 (>=1)
  [PASS] shape_thru_hole: 15/56 (>=1)
  [PASS] shape_unknown: 14/56 (>=1)
```

The frozen corpus is baked into `packages/temper-geometry/src/copper_reach.rs`'s own
`mod tests` as two new tests (registered in the wasm32 tier registry, +2 entries versus
this PR's own parent commit's count): `frozen_copper_reach_matches_golden_corpus` (the
regression comparison) and
`frozen_copper_reach_corpus_is_non_vacuous` (a runtime re-assertion of the table above,
so the corpus cannot be hand-edited down to something trivially satisfiable without
CI catching it — same convention as `creepage_check.rs`/`via_clearance.rs`, PR #1007,
and `property_campaigns.rs`'s IPC-2221 bracket guard).

## What was deliberately NOT frozen in this batch, and why

- Every other oracle (158 remaining): not verified against the 10-commit bar in this
  pass. A conservative, single-kernel first batch was chosen deliberately — see the
  task brief's own caution ("a conservative first batch that genuinely deletes Python
  beats an ambitious one that gets reverted").
- Safety kernels (creepage, clearance, via/keepout geometry — `creepage_check.rs`,
  `via_clearance.rs`, `clearance_geometry.rs` and their oracles) were not considered as
  FREEZE candidates at all, per the plan's explicit reservation of that class for
  REIMPLEMENT-from-spec.
- A second candidate (`deterministic/stages/slot_generation.py`'s oracle, backed by
  `temper-design-bundle`'s `generate_slots_for_zone`) was investigated and rejected for
  this batch: its Rust module (`deterministic_stages.rs`) is declared
  `#[cfg(feature = "python")]` in `lib.rs`, so it does not exist at all in the
  `--no-default-features` build the wasm32 tier compiles — freezing it would not have
  produced a wasm32-tier-executable test (one of FREEZE's two stated benefits), only a
  Python deletion. Left for a follow-up that either accepts a native-only frozen test or
  first un-gates the pure kernel function.
- `deterministic/geometry/grid_utils.py`'s oracle was investigated and rejected: its
  Rust kernel (`grid_utils.rs::add_endpoint_nudge`) calls `host_math::pow`, a `dlsym`
  boundary to the host libm — the plan's own host-facility exclusion
  ("`dlsym`/libm ... KEEP or REIMPLEMENT by construction").
