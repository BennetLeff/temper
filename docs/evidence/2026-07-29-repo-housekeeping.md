# Repo housekeeping — worktree and branch inventory (2026-07-29)

<!-- provenance: commit=df566055bb97f3996f249668eaae55c2bd1eb408 dirty=true -->

Conservative cleanup pass. Only fully-verified-merged branches were deleted, only via
`git branch -d` (never `-D`), and no worktree was removed. Several other agent sessions
were concurrently active in this same repo throughout this pass (see "Concurrency
caveat" below) — counts moved under our feet while we worked.

## Headline numbers

| Metric | Before | After |
|---|---:|---:|
| Worktrees (`git worktree list`) | 38 | 46 (see caveat — grew from concurrent agent activity, not from anything this pass added) |
| Dead worktree registrations pruned | — | 0 (all 38 directories that existed at the start still existed; nothing for `git worktree prune` to clear) |
| Local branches (`git branch`) | 266 | 205 |
| Branches deleted this pass | — | 71 |

Branch classification (measured against the 266-branch snapshot taken at the start of
the run, before concurrent sessions added more):

| Group | Count | Deleted | Refused (kept) |
|---|---:|---:|---:|
| (a) merged into `origin/main` | 81 | 70 | 11 (checked out in a live worktree) |
| (b) merged into `feat/ato-net-classification-ssot` or `feat/provable-safety-place-and-route`, not into `origin/main` | 24 | 1 | 23 (4 checked out in a live worktree; 19 blocked by a `git branch -d` mechanics quirk — see below) |
| (c) unmerged / merged nowhere in scope | 160 | 0 (never attempted) | 160 |
| `main` (never touched) | 1 | 0 | 1 |
| **Total** | **266** | **71** | **195** |

**Concurrency caveat on the "after" count:** `266 − 71 = 195`, but the actual post-run
branch count is 205, i.e. 10 more than arithmetic predicts. Mid-run, a `git branch --format... | wc -l`
check (taken after the first deletion but before the bulk pass) already read 276 — 11 more
than the starting snapshot minus the one branch deleted so far. That confirms other
concurrent sessions were actively creating new branches in this repo throughout the run.
Those branches were never classified or touched by this pass; the discrepancy is entirely
attributable to that concurrent activity, not to any double-counting or missed deletion here.

## What was deleted

### Group (a) — merged into `origin/main` (70 deleted)

Verified via `git branch --merged origin/main` **and** individually confirmed with
`git merge-base --is-ancestor <branch> origin/main` before deletion.

```
chore/git-stash-guard
chore/mpn-gate-name-unchecked
docs/binding-axis-solution
docs/isolator-sourcing-brief
docs/req-safe-01-rederivation
docs/tank-design-envelope-solution
feat/detect-tautological-assertions
feat/mpn-decoder-families
fix/capacity-budget-invariant
fix/clearance-copper-to-copper
fix/concurrency-per-pr
fix/evidence-provenance-pour-audit
fix/measurement-provenance-gate
fix/mpn-gate-stale-test
fix/pad-geometry-model
fix/shorting-items-via-clearance
fix/stitch-threshold-hole
fix/suspect-mpns
fix/tank-cap-and-isolator-footprints
fix/undeclared-import-gate-tests
fix/vulture-dead-code
perf/independent-gate-reporting
rb376
rb377
rb378
worktree-agent-a10b27aad7d7b73c9
worktree-agent-a165c2693ade2af09
worktree-agent-a1a22de5cbbd117fc
worktree-agent-a1a5ce674be409770
worktree-agent-a1a79621cea481d17
worktree-agent-a1f3e1a4f764ece35
worktree-agent-a21496c0216991342
worktree-agent-a25eb29abeacb1bff
worktree-agent-a28aef8d9692747ec
worktree-agent-a29aca3ebb3139d79
worktree-agent-a34ae8c25232c971b
worktree-agent-a36e651653c34ed33
worktree-agent-a3a627b684206b7b8
worktree-agent-a4bbec41adb056ea1
worktree-agent-a4f172b73356d9db5
worktree-agent-a58fd19a4871c78e8
worktree-agent-a5e39612e5d2b78d8
worktree-agent-a6ab6e5290c323ccd
worktree-agent-a734046d954a0db84
worktree-agent-a77b3872e91043cae
worktree-agent-a77e91b84c9fe3b52
worktree-agent-a7a53319d2420d7ee
worktree-agent-a88ea674d0c59e2c5
worktree-agent-a9733d1d504ea838d
worktree-agent-a9891bdf2d16b5e1f
worktree-agent-a98c54f75cb42e5e7
worktree-agent-a9e515e195e63c66b
worktree-agent-aa05e89684b40fd30
worktree-agent-aa2c8677168676e30
worktree-agent-aa7beb67f44906306
worktree-agent-aaec0ab36855ae931
worktree-agent-aaed7f5bc51967399
worktree-agent-abfedceeb7495aa34
worktree-agent-acdb2c0eab5defcb4
worktree-agent-ace33d56fcb5af801
worktree-agent-acf5d9dd830775f3a
worktree-agent-ad212b5b1b0cd0439
worktree-agent-adbbe9d8d9231d0de
worktree-agent-ae555dbe37b619d2a
worktree-agent-ae6c3371e77830d8d
worktree-agent-aebce148126fe4dcc
worktree-agent-aed695f5067ecaa08
worktree-agent-aef910fd49a03fe10
worktree-agent-af7785e917be4da93
worktree-agent-af9e490ec48adaa21
```

Note: several of these `worktree-agent-<hash>` branch names are git's auto-generated
default branch name for a worktree, distinct from the (different) branch that worktree
is *currently* checked out to. E.g. `worktree-agent-a21496c0216991342` (deleted here,
fully merged) is not the same ref as the branch presently checked out in
`.claude/worktrees/agent-a21496c0216991342`, which is `fix/drc-rule1-netclass-redo`
(refused below, still checked out). The former was an orphaned, already-merged
placeholder left over from before that worktree's checkout was switched.

Refused (11 of 81) — all because they are checked out in a currently-existing worktree
under `.claude/worktrees/`. This is the expected, correct `git branch -d` safety
behavior, not a misclassification — each was independently confirmed to be an ancestor
of `origin/main`:

```
docs/coil-selection-research         (.claude/worktrees/agent-acdb2c0eab5defcb4)
docs/part-verification-followup      (.claude/worktrees/agent-a28aef8d9692747ec)
docs/reference-appliance-research    (.claude/worktrees/agent-a9891bdf2d16b5e1f)
feat/occupancy-grid-disk-cache       (.claude/worktrees/agent-aedd5b820c06c84fd)
feat/tank-coil-specification         (.claude/worktrees/agent-aa2c8677168676e30)
fix/pll-floor-above-resonance        (.claude/worktrees/agent-ace33d56fcb5af801)
fix/tank-cap-placement               (.claude/worktrees/agent-a734046d954a0db84)
worktree-agent-a78a5405a30474ffe     (.claude/worktrees/agent-a78a5405a30474ffe)
worktree-agent-aba98c8b4dae7fce8     (.claude/worktrees/agent-aba98c8b4dae7fce8)
worktree-agent-ae3736ddd16914958     (.claude/worktrees/agent-ae3736ddd16914958)
worktree-agent-aeeab152bf155cdb8     (.claude/worktrees/agent-aeeab152bf155cdb8)
```

These 11 remain — left in place per instructions ("do not work around" a live-worktree
refusal). Kept, not deleted.

### Group (b) — merged into `feat/ato-net-classification-ssot` or
`feat/provable-safety-place-and-route`, not into `origin/main` (1 deleted)

Only `docs/methodology-loop-discipline` actually deleted cleanly via `git branch -d`
(it happened to also be merged into locally-checked-out `main`, so the default
HEAD-relative check in `git branch -d` passed).

**Investigation note — 19 branches produced a `git branch -d` refusal that contradicted
verified containment, and were deliberately left un-deleted:**

`git branch -d <name>` does **not** accept an arbitrary comparison ref. It always checks
whether the branch is an ancestor of the *current `HEAD`* (or the branch's own configured
upstream) — never of a ref passed on the command line. `git branch --merged <ref>` (used
for the initial listing) and `git merge-base --is-ancestor <branch> <ref>` (used for
per-branch verification) both accept an arbitrary ref, but `git branch -d` does not. The
primary worktree's `HEAD` was `main` (a fast-forward-only 7 commits behind
`origin/main`), which does **not** contain `feat/ato-net-classification-ssot` or
`feat/provable-safety-place-and-route` — so every branch only reachable via those two
feature branches was refused by `-d` with "not fully merged", even though
`git merge-base --is-ancestor <branch> feat/...` had already confirmed true containment
for all 19:

```
brainstorm/creepage-determination
coating-supplemental-scope
feat/isolator-creepage-slots
feat/k2-k3-discharge-relay-replacement
feat/u2-stackup-role-ssot
fix/drc-coating-failopen-close
fix/drc-courtyard-condition-fix
fix/drc-creepage-constraint
fix/hv-isolated-netclass-and-creepage-triage
fix/netclass-defect-reconciliation
fix/pd3-retarget-u3-u7-slots
fix/worktree-env-isolation
fix/zone-layer-classification
k2k3-discharge-relay-isolation
merge/main-into-methodology-loop-discipline
pd3-retarget-keepout
pd3-retarget-relay
perf/netlist-cache-skip
tank-current-reconciliation
```

Per the task's hard rule ("if `-d` refuses a branch you classified as merged... do NOT
reach for `-D`"), these were **not** deleted. The correct fix (checking out
`feat/ato-net-classification-ssot` as `HEAD` somewhere, then running `-d` there) was
deliberately not attempted in the primary worktree: that worktree's checked-out branch
changed mid-session (from `fix/forced-segment-fail-closed` at task start to `main` by
the time this pass ran), indicating another live session is using it, and switching its
checkout out from under that session was judged too risky. **Recommendation:** a future
pass should create a disposable worktree checked out at `feat/ato-net-classification-ssot`
(and separately at `feat/provable-safety-place-and-route`), run `git branch -d` there for
these 19 names, then have a human remove that worktree.

4 more refused because checked out in a live worktree (same category as group (a)'s 11):

```
agent/derivation-power-reference   (scratchpad/wt-powerref)
agent/h11l1-sourcing                (scratchpad/wt-source)
fix/drc-rule1-netclass-redo          (.claude/worktrees/agent-a21496c0216991342)
relay-board-resync-decision          (.claude/worktrees/agent-a9733d1d504ea838d)
```

## Group (c) — kept, unmerged or merged nowhere in scope (160, none touched)

Per instructions, **none of these were deleted**, regardless of name pattern
(`agent/*`, `worktree-*`, etc.). This includes the two protected long-lived feature
branches themselves (`feat/ato-net-classification-ssot`,
`feat/provable-safety-place-and-route`), which are correctly *not* merged into
`origin/main` and so fall in this bucket by the classification rule — they were never
at risk since they're on the hard-coded never-touch list regardless.

```
chore/loc-baselines
chore/make-extensions-target
chore/merge-temper-ipc-core
chore/remaining-stragglers
chore/untrack-build-artifacts
ci/invariant-coverage-gates
creepage-requirement-determination
dfm/wire-requirements-dfm-into-ci
docs/failure-mechanism-taxonomy
docs/failure-taxonomy
docs/session-solutions-2026-07-29
feat/ato-net-classification-ssot
feat/bulk-refactor-strictness
feat/ce-aware-sessions
feat/content-hash-extensions
feat/coverage-gate-phase2
feat/cp-sat-benchmarks
feat/cp-sat-feasibility-first-placer
feat/cross-language-domain-codegen
feat/encoder-decomposition
feat/gen-schematics
feat/hybrid-pour-trace-stitch
feat/identity-board-ref-check
feat/init-feature-wiring
feat/perf-profiling
feat/physics-informed-placement-routing
feat/physics-routing-constraints
feat/physics-thermal-field
feat/physics-validation-harness
feat/physics-verification-rigor
feat/pipeline-real-board-testing
feat/provable-safety-place-and-route
feat/pydantic-config-migration
feat/pyo3-bridge-framework
feat/rebenchmark-production-board
feat/repo-cleanup-onboarding
feat/rust-congestion-tensor
feat/sat-decomposition-experiment
feat/sat-encoding-experiment
feat/wasm-board-viewer
feat/wire-dfm-requirements
feat/wire-requirements-tests
feature/temper-jbc5
fix/add-sympy-test-dependency
fix/bus-capacitor-reselection
fix/ci-cancel-in-progress-main
fix/ci-churn-followups
fix/ci-loc-cap-gate
fix/cli-placer-retired-contract
fix/collection-errors
fix/config-board-mismatch-error-import
fix/docker-build-pr-trigger
fix/drc-rebaseline-routed-board
fix/drc-rule1-netclass-discrimination
fix/dsn-boundary-registry-import
fix/dsn-ipc-core-split
fix/electrical-design-audit-p0
fix/footprint-land-patterns
fix/invariant-parallel-split
fix/invariant-suite-triage
fix/invariant-triage
fix/land-leftover-build-fixes
fix/los-bbox-and-astar-split
fix/pll-floor-both-tolerances
fix/pll-floor-cap-tolerance
fix/post-audit-build-validation
fix/py-bridge-build
fix/route-segment-3d-patch-target
fix/router-grid-layer-pad-mismatch
fix/rust-router-optional-import
fix/strategy-board-facts-gate
fix/tank-cap-resource
fix/temper-net-mapping
fix/temper-nets-hierarchical-mapping
fix/temper-production-baseline-ovp01-component-count
fix/thermal-fdm-2nd-order-bc
fix/trunk-run-cancellation
fix/unresolved-ref-policy-single-source
fix/untrack-pipeline-artifact
fix/vacuous-gate-aggregates
fix/zone-pour-shape-clearance
integrate/physics-onto-main-v2
investigate/intra-component-shorts
perf/split-core-tests-gates
pr-267-local
refactor/merge-core-crates
refactor/merge-temper-dsn-core
refactor/merge-temper-geometry-core
refactor/physics-parameter-provenance-ci-gate
refactor/rust-quality-sweep
refactor/skill-driven-cleanup
schematic-updates
spike/schematic-source-drift-gate
survey/cleanup
temper-eqzh.3-cont
trial-main
trial376
trial377
update-schematics
worktree-agent-a02a23195c50807a7
worktree-agent-a0911a6c6b35168d3
worktree-agent-a0d9be1d2acaf56fc
worktree-agent-a148abf788131fbe0
worktree-agent-a177eb94c22ae4ac2
worktree-agent-a17b18f067aa11675
worktree-agent-a1f734266f2e73fec
worktree-agent-a208afb2e0996db72
worktree-agent-a2c90a5f56939f84f
worktree-agent-a2f481890549fdeb7
worktree-agent-a3027b77163c0ac33
worktree-agent-a31ad30eb0c63bdac
worktree-agent-a32397c5aca6365ba
worktree-agent-a421ae4b1bb9396a1
worktree-agent-a425619b20a673dff
worktree-agent-a4b6fa4a3162daa44
worktree-agent-a4e258ee59736759f
worktree-agent-a5b8db28b28b881e6
worktree-agent-a5ce0066262a09972
worktree-agent-a62fec70b7941ded4
worktree-agent-a6a495006da27f704
worktree-agent-a76c53d2950b050ef
worktree-agent-a7aebbfd5cd1c8207
worktree-agent-a7f1ef7ea0c234946
worktree-agent-a84a0778c916ff887
worktree-agent-a8a1e68665c822bfe
worktree-agent-a8be94167b2e1d864
worktree-agent-a8d3e0ca8ac55c9a2
worktree-agent-a8d61fc7c29228b34
worktree-agent-a915d6626da61d391
worktree-agent-a95984080c93bffe8
worktree-agent-a997afc1f2a0cd0fc
worktree-agent-a9f661fc83c990274
worktree-agent-aa5c1918bc7ff2241
worktree-agent-aa7cb2251cf3416a5
worktree-agent-aa8ad1838f9ff802c
worktree-agent-ab0ca80a73e309fdf
worktree-agent-ab3afdb26f0503635
worktree-agent-ab3b512f8f93eb9c6
worktree-agent-ab974ec425f4f2220
worktree-agent-abc2b86355e65e0b9
worktree-agent-abd36d48255bd8a02
worktree-agent-abeb3a4f70cf7db4f
worktree-agent-ac248dfa8513b0fc5
worktree-agent-ac48874260cf413c7
worktree-agent-ac6e408e11749cdd6
worktree-agent-ac6e5eb7a36f42c4a
worktree-agent-ac7d945161d7af0fe
worktree-agent-ac7ed8a3e94bc878c
worktree-agent-ac8e3f71930425924
worktree-agent-ac9040ce7a4ff852b
worktree-agent-ac92d250f5f33a1e0
worktree-agent-ad165e39a91df8cfd
worktree-agent-ad829d18dbc460ec2
worktree-agent-ad960bc307ec14bad
worktree-agent-aee3e1dd08d999245
worktree-agent-af68ffc2961085485
worktree-agent-af821f7744926ca4c
worktree-agent-af8c0486a02493e77
worktree-agent-afa2d3ddc206d637a
worktree-agent-afeeaa93efe1571cd
```

## Remaining worktrees (46) — for human staleness review

None removed. Directory existence was the only pruning criterion applied
(`git worktree prune`, step 1); all 38 directories that existed at the start of this
pass still existed, so 0 registrations were cleared. 8 more worktrees appeared between
the start and end of this pass (attributed to concurrent agent sessions, consistent
with the branch-count drift noted above).

| Path | Branch | Last commit date |
|---|---|---|
| `/Users/bennet/Desktop/temper` (primary) | `main` | 2026-07-29 |
| `scratchpad/48e5ea19.../wt-bundle` | `fix/collection-errors` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-conc` | `fix/trunk-run-cancellation` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-cores` | `refactor/merge-core-crates` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-dfm` | `feat/wire-dfm-requirements` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-inv` | `fix/invariant-triage` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-loc` | `chore/loc-baselines` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-los` | `fix/los-bbox-and-astar-split` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-main` | *(detached)* `dc14d569` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-nets` | `fix/temper-net-mapping` | 2026-07-28 |
| `scratchpad/48e5ea19.../wt-plan001` | `fix/vacuous-gate-aggregates` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-req` | `feat/wire-requirements-tests` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-routeseg` | `fix/route-segment-3d-patch-target` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-tax` | `docs/failure-taxonomy` | 2026-07-27 |
| `scratchpad/48e5ea19.../wt-untrack` | `chore/untrack-build-artifacts` | 2026-07-27 |
| `scratchpad/9057d4ee.../drc-baseline` | *(detached)* `96fdee01` (= `origin/main` tip) | 2026-07-29 |
| `scratchpad/b3b19a7e.../landing/wt-baseline` | *(detached)* `96fdee01` (= `origin/main` tip) | 2026-07-29 |
| `scratchpad/b3b19a7e.../landing/wt-slice1` | `feat/build-freshness-and-worktree-isolation` | 2026-07-29 |
| `scratchpad/b3b19a7e.../landing/wt-slice2` | `docs/solutions-lessons-2026-07` | 2026-07-29 |
| `scratchpad/b3b19a7e.../wt-netssot` | `feat/ato-net-classification-ssot` (protected) | 2026-07-29 |
| `scratchpad/b3b19a7e.../wt-powerref` | `agent/derivation-power-reference` | 2026-07-29 |
| `scratchpad/b3b19a7e.../wt-source` | `agent/h11l1-sourcing` | 2026-07-29 |
| `.claude/worktrees/agent-a21496c0216991342` | `fix/drc-rule1-netclass-redo` | 2026-07-28 |
| `.claude/worktrees/agent-a28aef8d9692747ec` | `docs/part-verification-followup` | 2026-07-28 |
| `.claude/worktrees/agent-a34ae8c25232c971b` | `docs/session-solutions-2026-07-29` | 2026-07-29 |
| `.claude/worktrees/agent-a469744fab2d2069d` | `fix/drc-measurement-reproducible` | 2026-07-29 |
| `.claude/worktrees/agent-a58fd19a4871c78e8` | `fix/tank-cap-resource` | 2026-07-29 |
| `.claude/worktrees/agent-a68794d9097f40384` | `docs/pour-derivation-rule` | 2026-07-29 |
| `.claude/worktrees/agent-a734046d954a0db84` | `fix/tank-cap-placement` | 2026-07-28 |
| `.claude/worktrees/agent-a78a5405a30474ffe` | `worktree-agent-a78a5405a30474ffe` | 2026-07-26 |
| `.claude/worktrees/agent-a8a1e68665c822bfe` | `worktree-agent-a8a1e68665c822bfe` | 2026-07-26 |
| `.claude/worktrees/agent-a9708e92cba92a2b2` | `brainstorm/hv-footprint-resolution` | 2026-07-29 |
| `.claude/worktrees/agent-a9733d1d504ea838d` | `relay-board-resync-decision` | 2026-07-28 |
| `.claude/worktrees/agent-a9891bdf2d16b5e1f` | `docs/reference-appliance-research` | 2026-07-28 |
| `.claude/worktrees/agent-aa2c8677168676e30` | `feat/tank-coil-specification` | 2026-07-29 |
| `.claude/worktrees/agent-aba98c8b4dae7fce8` | `worktree-agent-aba98c8b4dae7fce8` | 2026-07-26 |
| `.claude/worktrees/agent-acdb2c0eab5defcb4` | `docs/coil-selection-research` | 2026-07-28 |
| `.claude/worktrees/agent-ace33d56fcb5af801` | `fix/pll-floor-above-resonance` | 2026-07-29 |
| `.claude/worktrees/agent-adfcc3335d2da1572` | *(detached)* `9f869ad2` | 2026-07-26 |
| `.claude/worktrees/agent-ae3736ddd16914958` | `worktree-agent-ae3736ddd16914958` | 2026-07-27 |
| `.claude/worktrees/agent-aed695f5067ecaa08` | `investigate/intra-component-shorts` | 2026-07-29 |
| `.claude/worktrees/agent-aedd5b820c06c84fd` | `feat/occupancy-grid-disk-cache` | 2026-07-28 |
| `.claude/worktrees/agent-aeeab152bf155cdb8` | `worktree-agent-aeeab152bf155cdb8` | 2026-07-24 |
| `.claude/worktrees/agent-aef910fd49a03fe10` | *(detached)* `d6c3cd97` | 2026-07-29 |
| `.claude/worktrees/agent-afcafaa934edd1146` | `feat/provable-safety-clean` | 2026-07-29 |
| `.claude/worktrees/fix-footprints` | `fix/footprint-land-patterns` | 2026-07-29 |

Rough staleness read: most worktrees have commits from the last 1-3 days, so they read
as plausibly-live agent runs, not obviously abandoned. The oldest last-commit dates
(2026-07-24, `agent-aeeab152bf155cdb8`; 2026-07-26, three others) are the most likely
candidates for a human to check first, but "old last commit" isn't proof of
abandonment on its own — worktrees can sit idle between agent turns. No worktree was
removed as part of this pass; that decision is left to a human.

## Hard constraints honored

- No `git branch -D`, no `-f`, no `git worktree remove`, no pushes, `main` untouched.
- Every deletion went through plain `git branch -d`; every refusal was investigated
  (see above) rather than forced.
- Total deleted (71) is well under the 150-branch stop threshold.
- No branch was deleted on name pattern alone; every deletion was backed by a
  `git merge-base --is-ancestor` check against the specific ref it was claimed to be
  merged into.
