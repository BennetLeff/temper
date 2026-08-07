<!-- provenance: commit=c6b5402684ca4fa75a307a9e6e17f9e6b2538e04 dirty=false -->

# R3 Router Status: fix confirmed applied, gate un-masked, route timing unmeasurable

**Date:** 2026-08-05

**Task:** U6 of `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` —
re-verify the router at HEAD after the `_mm`-aliases fix landed, measure
wall time and determinism, and un-mask the CI gate that covers it.

**Scope of writes:** this document, `.github/workflows/python-tests.yml`
(changed `extended-cpsat-slow` header comment + removed
`continue-on-error: true` from the routing-gate step). No board file, no
DRC ceiling, no production source.

---

## Machine and tool context

| Field | Value |
|---|---|
| Machine | Apple M2 Pro, 12 cores, 32 GB RAM |
| OS | macOS 26.5.1 (build 25F80), arm64 |
| Commit | Based on `f2c5af948` (origin/main), branch `wasm/router-unmask` |
| Worktree | `/private/tmp/wasm-router`, own `.venv` via `uv sync --all-packages` |
| Python | 3.12 (uv-managed venv) |
| Board under test | `pcb/temper.kicad_pcb`, sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6` |

`scripts/assert-base.sh origin/main` passed (exit 0, HEAD == f2c5af948).

---

## 1. Fix status on `origin/main`

The fix for the `AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'`
reported in `docs/evidence/2026-08-04-board-regeneration-cost.md` §2c was
already landed on `origin/main` via PR #671 (commit `40024a13c`), not via
the feature-branch commit `65c100c82` that the evidence doc cited. A
`git cherry-pick 65c100c82` on `f2c5af948` reported the patch already
applied (no content to commit).

The fix adds four `@property` read aliases (`trace_width_mm`,
`clearance_mm`, `via_diameter_mm`, `via_drill_mm`) to the generated
`NetClassRules` pydantic model via the codegen template
(`scripts/templates/netclass_rules.py.j2`). The fix mirrors the identical
getter aliases added to the Rust `DesignRules` pyclass in commit
`28dc960de` (#666).

**Codegen consistency check:**
```
$ python3 scripts/gen_domain_models.py --check
All generated domain models match the manifest.
```
Exit 0. Generated model matches the template — the committed
`netclass_rules_gen.py` is in lockstep with the SSOT manifest.

---

## 2. Repro: before vs. after

### Before (commit caa492f25, per 2026-08-04 evidence doc)

```
$ uv run python3 scripts/route_board.py --output /tmp/routed.kicad_pcb
...
AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'.
Did you mean: 'via_diameter'?
```

Exit 1, crash at `escape_via_generator.py:86`.

### After (this task, f2c5af948 with fix already present)

The `AttributeError` does **not** reproduce. The `_mm` aliases resolve
correctly. Verified by:

1. Import and attribute access:
   ```
   $ uv run --no-sync python3 -c "
   from temper_placer.core.netclass_rules_gen import NetClassRules
   r = NetClassRules('test', trace_width=0.5, clearance=0.3, via_diameter=0.8, via_drill=0.4)
   print(r.trace_width_mm, r.clearance_mm, r.via_diameter_mm, r.via_drill_mm)
   "
   0.5 0.3 0.8 0.4
   ```
   All four `_mm` aliases resolve to the correct values.

2. The CI gate test `test_production_board_routing_drc_regression` no
   longer crashes with `AttributeError`. It now fails with a *different*
   error — a stale baseline shape assertion (see §3) — confirming that
   `route_pcb()` is reached and the `_mm` fix works.

3. `scripts/route_board.py` with `--runs 1` reaches `route_pcb()` without
   the `_mm` crash (confirmed via the "Empty placements provided; routing
   with existing board positions." log line and the "dropping..." warnings
   that follow, which are emitted inside `route_once()` after the
   `NetClassRules` attribute reads succeed).

---

## 3. Route wall time: UNMEASURED (OOM on this machine)

### What happened

`route_pcb()` on the production board allocated >13 GB RSS at peak and
was consistently killed by the OS memory killer (exit -9 / SIGKILL)
before completing. Three independent attempts:

| Attempt | Peak RSS | Elapsed at kill | Outcome |
|---|---|---|---|
| 1 (in-process) | ~8.8 GB | ~6.5 min | SIGKILL |
| 2 (`--runs 1`) | ~13.5 GB | ~7 min | SIGKILL |
| 3 (in-process) | ~13.5 GB | >15 min (timeout) | Killed by 15-min timeout |

The 2026-07-27 first-route doc reports ~1.7 min wall time and ~7 GB peak
RSS for the same board on presumably the same machine class. The
discrepancy — 2× memory and >10× wall time — was not investigated
further. Candidates: (a) memory pressure from concurrent agent worktrees
affecting the SAT solver's performance; (b) a genuine performance
regression in the routing path since 2026-07-27; (c) the board shape
changed (2338→2290 segments), potentially changing the route topology.

**Per the task instruction: "If route is slow or the discrepancy
reproduces, RECORD it — do not fix it."** This is recorded.

### N=12 timing: NOT RUN

Cannot be measured without a successful single route. If the route can
complete on a less-loaded machine, `scripts/route_board.py --runs 12`
(the U6-specified tool) is ready to use.

---

## 4. Determinism (5 fresh processes, sha256 comparison): NOT RUN

Cannot be measured without a successful single route. The 5-run sha256
comparison protocol from `docs/evidence/2026-07-27-router-determinism.md`
remains the correct procedure when the route becomes runnable.

### Net-completion discrepancy (53.1% vs. 37.5%): NOT RE-VERIFIED

The UNVERIFIED section of the 2026-07-27 determinism doc — which
documents that 17 runs never reproduced the committed board's 53.1%
completion, always producing 37.5% — could not be re-checked. The
discrepancy remains UNVERIFIED as of this task.

---

## 5. Stale test baseline (board shape changed)

### The test now fails on shape, not on routing

```
$ pytest ...::test_production_board_routing_drc_regression -x -q
FAILED in 0.68s
AssertionError: pcb/temper.kicad_pcb has changed shape since the DRC
baselines in this module were measured: baseline {'footprints': 169,
'segments': 2338, ...}, actual {'footprints': 169, 'segments': 2290, ...}
```

The board lost 48 segments since the baselines in
`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` were
last measured (commits `7e3608bc2`, `e5a89b1e0`, `550cab2a3` changed
`pcb/temper.kicad_pcb`). The test correctly guards against this. The
failure is NOT a regression from the `_mm` fix — it is a pre-existing
stale-baseline issue that exists on `origin/main` independently.

This was NOT fixed in this task (updating test baselines requires DRC
re-measurement against the changed board, which is out of scope per the
task constraints).

---

## 6. CI gate change: `python-tests.yml`

### What changed

In the `extended-cpsat-slow` job (trunk-only, `if: github.event_name != 'pull_request'`):

1. **Job header comment** (line 2325): changed from
   `"Trunk-only -- masked test step, cannot fail a PR."` to
   `"Trunk-only. The routing DRC regression gate in this job was unmasked
   2026-08-05 (fix(netclass): _mm read aliases landed; gate can now bite)."`

2. **Step comment** (lines 2461–2468): updated to note `continue-on-error`
   was removed and to remove the stale claim about `--min-tests 2` being
   "masked by the continue-on-error below."

3. **Removed `continue-on-error: true`** (was line 2474) from the
   `Run cp-sat suite (slow pair, parallelized)` step. Replaced with a
   comment explaining the removal.

### Why only the trunk-only job

The test `test_production_board_routing_drc_regression` runs ONLY in
`extended-cpsat-slow`, which is trunk-only. The PR-path cp-sat job
deselects it (line 2319) — the deselect exists because this test was
moved out of the PR path for wall-clock reasons (it takes ~102–114s on
CI runners) in the 2026-07-30 cp-sat job split, NOT because the test
was broken.

The deselect was **not** removed. Removing it would pull the 102s+
test back onto the PR critical path, defeating the purpose of the
trunk-only split. The test is now a trunk-blocking gate on every push
to `main` — exactly where trunk-invariant tests belong.

### Why the zone pour test's xfail(strict) is not a concern

The step runs two tests: the zone pour U3 measurement (xfail strict)
and the routing DRC regression. xfail(strict) reports expected failures
as XFAIL (exit code 0), and unexpected passes as XPASS (exit code 1,
which *should* fail the build — that's the "promotion signal" the xfail
docstring describes). Removing `continue-on-error` restores correct
behaviour for both.

### Lint

```
$ SHELLCHECK_OPTS='--severity=error' actionlint -ignore 'constant expression "false" in condition' .github/workflows/python-tests.yml
```
Exit 0, no findings.

---

## 7. What was NOT changed

- **Deselect in PR-path cp-sat job** (line 2319): left in place. The
  deselect exists for wall-clock reasons, not because the test was
  broken.
- **`if: github.event_name != 'pull_request'`** on `extended-cpsat-slow`:
  unchanged. The gate is trunk-only by design.
- **Any board file, DRC ceiling, or production source.** `git status`
  will be verified clean of `pcb/**` and `power_pcb_dataset/**` before
  push.
- **Test baselines in `test_regression_drc.py`**: not updated. The board
  shape changed (2338→2290 segments) since the baselines were set, and
  updating them requires DRC re-measurement per the test's own assertion
  message. Out of scope for this task.

---

## Sources

- `docs/evidence/2026-08-04-board-regeneration-cost.md` — the repro
  this task re-verifies.
- `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` §U6 —
  this unit's specification.
- `docs/evidence/2026-07-27-router-determinism.md` — the determinism
  protocol that could not be re-applied.
- `docs/evidence/2026-07-27-first-route-and-profile.md` — the ~1.7 min
  / ~7 GB wall time baseline this task could not reproduce.
- `packages/temper-placer/src/temper_placer/core/netclass_rules_gen.py` —
  the generated model with `_mm` aliases (lines 84–110).
- `scripts/templates/netclass_rules.py.j2` — the codegen template
  (lines 49–75).
- `.github/workflows/python-tests.yml:2323–2478` — the changed job.
