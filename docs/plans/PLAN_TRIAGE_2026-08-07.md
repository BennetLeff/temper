# Plan Triage — 2026-08-07

`docs/STRATEGY.md`'s Superseded section closed with: "A sweep of the
remaining 143 plans for superseded status is outstanding." This document
records that sweep and where its output lives.

## Where the results actually are

For the 195 of 202 plans in `docs/plans/` that carry a YAML frontmatter
block, the verdict is recorded **in the plan's own frontmatter** — the
`status:` field (one of `active`, `completed`, `superseded`, `abandoned`,
`stale`), plus `swept: 2026-08-07` and a `swept_basis:` line giving the
one-line evidence (and, for `superseded`, the successor plan's filename).
This follows the precedent already set by the 2026-07-25 mechanical sweep
(`scripts/sweep_plan_status.py`) rather than inventing a new field.
`docs/plans/README.md`'s generated table (`scripts/gen_repo_state.py`) is
the up-to-date summary of that data — regenerated as part of this sweep.

This file exists only for the **7 plans where that schema does not apply**
— either they carry no YAML frontmatter block at all, or their existing
"frontmatter" is a malformed fragment left by an earlier, different sweep.
Per the task's instruction not to silently invent a new frontmatter field
where the schema doesn't support one, their verdicts are recorded here
instead of being hand-added to the file.

## The 7

| file | verdict | evidence |
|---|---|---|
| `2026-07-23-001-perf-cp-sat-benchmarks-plan.md` | **completed** | `benchmarks/cp_sat_bench.py` and `.github/workflows/cp-sat-benchmarks.yml` exist and run in CI, with `benchmarks/scenarios/{trivial,small}.yaml`; the workflow is advisory (`ci-advisory` label) rather than the plan's originally-specified blocking gate |
| `2026-07-23-002-perf-profiling-setup-plan.md` | **abandoned** | no py-spy/flame-graph tooling anywhere in the repo; only 3 `profiler.stage/sub_step` call sites total, none of the 4 hot paths the plan named (CP-SAT, KiCad I/O, copper, thermal) are wired; no commits after the plan was written |
| `2026-07-30-001-fix-handoff-actionables-implementation-plan.md` | **active** | see "The handoff-actionables landmine" below |
| `2026-08-06-001-docs-python-removal-retriage-plan.md` | **active** | current re-triage of the `NEVER-PORT` corpus against the "remove Python entirely" question; feeds goal-set goal 1 (Rust consolidation) directly and is dated three days before this sweep |
| `AUTOMATED_PCB_LAYOUT_SYSTEM.md` | **abandoned** | dated 2025-12-29, hand-written `**Status**: Planning`, describes a 31%-complete greedy-A\* router predating router_v6, the CP-SAT placer, and the SAT-based router entirely; superseded by the whole subsequent project, not by one plan |
| `ROUTER_IMPROVEMENT_STRATEGY.md` | **abandoned** | same era (targets "26% to >98%" completion on `MazeRouter`/`internal_route.py` greedy A\*), no YAML frontmatter, superseded by router_v6 |
| `ROUTER_V3_DRC_COMPLIANCE.md` | **abandoned** | same era (dated 2025-12-29); already carries a mangled `---status: abandoned` fragment from an earlier sweep (commit `cac98f5d`) glued onto a markdown horizontal rule mid-document — left as-is rather than hand-repaired, since fixing that cosmetic damage is outside this triage's scope, but the verdict it recorded (`abandoned`) is corroborated independently here |

## The handoff-actionables landmine

`docs/plans/2026-07-30-001-fix-handoff-actionables-plan.md` and its sibling
`-implementation-plan.md` describe integrating four units of work from other
branches (commits `5401a827f`, `3cd4fc4c6`, `43082f16b`). Re-checking against
the actual repo:

- **U1 and U4 (creepage measurement tooling, docs) landed** — under
  different commit hashes than the plan cites (`6ef9dde8`, `01ece8c9`, from
  "PR #498 rework"), which is why a naive path/hash check would miss them.
- **U2 and U3 — deleting the H11L1 mains-ZCD optocoupler that permanently
  fails the 12.6 mm PD3 creepage target, and the board reconciliation that
  follows — did not land.** The two commits the plan names (`27725af9`,
  `70b84342`) exist only on `origin/codex/handoff-actionables`, an unmerged
  branch 835 commits behind current `main` and 13 ahead of where it forked.
  `git merge-base --is-ancestor 27725af9 HEAD` (and the same for `70b84342`)
  both fail. `H11L1` is still present in `elec/src/` and `pcb/` on `main`
  today.

Both plans are marked `active`, not `completed` or `abandoned`, because the
work is real, partially done, and the remaining half is a **live, unfixed
safety-relevant debt** (a creepage-clearance violation on a mains-adjacent
component) sitting behind documentation that, read at a glance, looks
finished. This is the single highest-priority finding in this triage.

## Two systematic blind spots in the 2026-07-25 mechanical sweep

Confirmed on multiple examples while re-triaging plans the mechanical sweep
had called `stale` or `abandoned` (see the frontmatter `swept_basis` on each
named file for the individual evidence):

1. **Deletion/retirement plans read their own success as failure.** The
   sweep's heuristic scores a plan by what fraction of its named file paths
   still exist. For a plan whose entire point is deleting code — JAX
   descent-optimizer retirement (`2026-07-05-001`), the dead Cython A\* twin
   cleanup (`2026-06-22-007`) — the named paths correctly *not* existing
   afterward is the success signature, and the heuristic read it as
   `abandoned`. Both are fully landed (`docs/solutions/architecture-patterns/jax-framework-retirement-reverse-topological-deletion-2026-07-05.md`,
   `docs/specs/cython_twin_threshold.md`).
2. **A `src/`-layout migration broke path matching for older plans.** Several
   June plans cite paths like `packages/temper-placer/temper_placer/core/...`
   (no `src/` component); the repo was later restructured to
   `packages/temper-placer/src/temper_placer/...`, so those plans scored
   near-zero path existence even though the work landed at the new path
   (`2026-06-22-004-feat-net-class-rules-fields-plan.md`,
   `2026-07-05-002-feat-constraint-completion-cp-sat-encoder-plan.md`).

Both blind spots were corrected in the affected plans' own frontmatter as
part of this sweep, and are flagged here because they generalize: any future
mechanical re-sweep should special-case deletion-shaped plans and try both
the literal and `src/`-inserted path forms before scoring `abandoned`.

## Missing-plan citations (not a triage verdict, a repo-hygiene finding)

Two currently-`active` anchor plans — `docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md`
(the current 5-goal north star) and `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`
— cite `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` and
`docs/plans/2026-08-03-001-perf-drc-trio-parallelization-plan.md` by name as
the plans owning "disposition of findings" and "everyday PR throughput"
respectively. **Neither file exists in `docs/plans/` on `main`.** Both exist
only on `origin/docs/phase3-formats-io-plan`, an unmerged branch 834 commits
behind `main`, one of whose PRs is already flagged "Close — targets a dead
base" in `docs/audits/2026-08-05-open-pr-backlog-triage.md`. Anyone
following either citation from the goal-set plan today hits a dead link.
This wasn't touched (the two anchor plans are edited above only to add
`status`/`swept`/`swept_basis`, not to alter the citation), but the
maintainer should know the citation is broken before relying on it —
exactly the "acted on a stale/false premise" failure mode `docs/STRATEGY.md`
already names twice.
