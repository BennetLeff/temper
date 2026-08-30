<!-- provenance: commit=0123cc07848ed12b508227fc3937109a4d080009 dirty=UNKNOWN -->
branch fix/scipy-migration-regression, base origin/main 66a277d94 (tip at task start).
All counts below are direct grep over the working tree at that commit (plus the fix
commit cff390182 for the "after" state); no counts are inferred from docs. -->

# Migration-reversal sweep: how many closed migrations were silently reversed?

**Question.** PR #1052 (`d8e6efd48`) reintroduced `scipy.ndimage.label` in
`_corridor_backbone.py` — a dependency this repo had already migrated off,
twice (`1efa1cb33` for EDT call sites, `3ba16bfbd` for connected-component
labeling). Is that an isolated incident, or one of many?

**Headline answer: it is the only one.** A full-tree sweep for production
imports of every library named in the task brief (scipy, networkx, shapely,
ortools) found exactly **one** reversed-migration import in the entire repo
— the one already named in the task, now fixed. Both libraries with a
provably *closed* migration (scipy, networkx) are at **zero** production
imports after the fix. shapely and ortools have many production imports, but
neither is a closed migration — both are extensively documented as
deliberate, currently-necessary dependencies (see §3), so their imports are
not reversals of anything.

## 1. Method

"Production" uses the same definition `scripts/check_migration_narrowing.py`
uses elsewhere in this repo's own migration tooling: `packages/`, `scripts/`,
`tools/`, excluding any path containing `/tests/`, `test_`, `_py_oracle`,
`/spikes/`, `/benchmarks/`, `/experiments/` — i.e. code that actually runs in
the shipped pipeline, not test oracles (which are *retained by design*, see
`docs/evidence/2026-08-11-python-deprecation-inventory.md` bucket 5) or
throwaway measurement scripts.

```
grep -rnE "^\s*(import scipy|from scipy)" --include="*.py" packages scripts tools \
  | grep -viE "/tests?/|_py_oracle|test_|/spikes/|/benchmarks/|experiments/"
```
(same pattern for `networkx`, `shapely`, `ortools`)

## 2. scipy: 1 production import, now 0

Before the fix (`origin/main` 66a277d94, i.e. current `main` with #1052
merged):

```
packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py:549:    from scipy.ndimage import label
```

**Exactly one hit, repo-wide.** This is the regression the task named — no
others exist. After the fix (this branch, `cff390182`): zero hits. Every
other scipy reference anywhere in `packages/`, `scripts/`, `tools/` is
either (a) inside `tests/` — a pinned pre-migration oracle for a
`test_*_rust_differential.py` suite (R19 convention,
`docs/migration-pipeline.md` stage 3), (b) a docstring/comment describing
the migration history (no live import), or (c) an experiments/ file
unrelated to the production pipeline
(`packages/temper-placer/experiments/framework/EXPERIMENT_PROTOCOL.md`,
a doc, not code).

Confirmed no-scipy state of every module the task named as previously
migrated: `channel_widths.py`, `_astar_heuristics.py`, `routability_check.py`,
`channel_skeleton.py` — all scipy-free in production; their only `scipy`
occurrences are docstring prose citing the pre-migration oracle by name.

## 3. networkx: 0 production imports

```
grep -rnE "^\s*(import networkx|from networkx)" --include="*.py" packages scripts tools \
  | grep -viE "/tests?/|_py_oracle|test_"
=> (no output)
```

Zero, including `packages/temper-placer/src/temper_placer/core/community.py`
and `router_v6/channel_skeleton.py` — both cited in
`docs/evidence/2026-08-06-never-port-triage.md` as networkx-backed at the
time that document was written. Neither imports networkx today. This is a
**closed migration with zero reversals**, not merely an untouched one — no
production networkx import exists to reverse.

## 4. shapely: 26 production imports — not a closed migration, not in scope

```
grep -rlnE "^\s*(import shapely|from shapely)" --include="*.py" packages scripts tools \
  | grep -viE "/tests?/|_py_oracle|test_" | wc -l
=> 26
```

Every one of these is a **live, deliberately retained** GEOS/shapely
dependency, not a reversion. `docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md`,
`2026-08-06-never-port-triage.md`, and `2026-08-06-wave4-owned-surface-closeout.md`
all independently record the same verdict: shapely/GEOS is the systemic
geometry boundary this repo has **not** migrated off and has no committed
plan to (`channel_skeleton.py`'s Voronoi kernel, `constraints_zones.py`'s
`STRtree`, `guard_strip.py`'s `buffer`/`difference`, etc. — all spike-gated
**KEEP**, not PORT-then-reversed). Because there is no closed shapely
migration, a shapely import cannot be a *reversal* of one, by definition —
these 26 files are correctly out of scope for this sweep and for the
prevention gate in §5 of the companion plan document.

## 5. ortools: 4 production imports — architecturally blocked, not migrated

```
packages/temper-placer/spikes/cp_sat_feasibility.py
packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/_registry.py
packages/temper-placer/src/temper_placer/placer/cp_sat/model.py
packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/_protocol.py
```

All four are the `BLOCKER-ORTOOLS` cluster named in
`docs/evidence/2026-08-11-python-deprecation-inventory.md` §5: "No mature
Rust CP-SAT solver exists; remediation is an FFI project... not a
translation task." Not a closed migration; out of scope for the same reason
as shapely.

## 6. Conclusion

| Library | Closed migration? | Production imports found | Reversals |
|---|---|---:|---:|
| scipy | Yes (`1efa1cb33`, `3ba16bfbd`) | 1 (pre-fix) / 0 (post-fix) | **1** — `_corridor_backbone.py:549`, fixed on this branch |
| networkx | Yes (untraced commit; verified closed by absence) | 0 | 0 |
| shapely | No — deliberate, documented KEEP | 26 | N/A, not a migration to reverse |
| ortools | No — architecturally blocked | 4 | N/A, not a migration to reverse |

**The count is 1, not 20.** This changes the priority calculus for §5 of the
companion plan: the prevention mechanism does not need to solve a
widespread-drift problem, and a narrow, already-armed gate (ratchet-at-zero
for scipy and networkx specifically, via the existing import-linter
boundary check) is proportionate. See
`docs/plans/2026-08-12-005-feat-migration-regression-prevention-plan.md`.
