---
title: "Shared mutable state is the dominant cost in a multi-agent repo — none of today's five incidents were code defects"
date: "2026-07-28"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "multiple agent sessions run in parallel git worktrees against one shared checkout, shared object database, or shared build cache"
  - "a freshness/staleness gate compares an installed artifact's mtime against source mtimes, and worktrees are created by `git checkout -b`"
  - "a coordinator or agent runs a stash, checkout, or branch-pointer command and it is unclear whether the target is an isolated worktree or the shared main checkout"
  - "diagnosing why a session's own gate result disagrees with what it expected, and the session's own code changes are not the first thing to suspect"
tags:
  - shared-worktree-state
  - git-stash-corruption
  - disk-exhaustion
  - stale-extension-false-positive
  - branch-pointer-churn
  - agent-stall
  - infrastructure-not-code
---

# Shared mutable state is the dominant cost in a multi-agent repo

## Context

Five independent, same-day incidents, none of them a defect in the code any
session was there to change, all traced to the same root: agent worktrees
in this repo share a checkout's mutable state — `.venv`, the Cargo target
directory, the stash ref, the branch pointer, and the disk itself — with the
main checkout and with each other.

**1. Extensions read stale, repeatedly, for a reason that was never a real
staleness.** `check_stale_extensions.py` compares an installed `.so`'s mtime
against its source files' mtimes. `git checkout -b` stamps every tracked
file with the checkout instant, so a worktree built from a fresh branch
always looks "newer" than a `.venv` shared from the main checkout via
`UV_PROJECT_ENVIRONMENT` — regardless of whether the sources actually
changed. This exact false positive fired independently in **five** of
today's evidence sessions
(`docs/evidence/2026-07-28-pd3-retarget-keepout.md`,
`-pd3-retarget-slots.md`, `-pd3-retarget-relay.md`,
`-drc-courtyard-condition-fix.md`, `-drc-coating-failopen-fix.md`), each one
independently re-diagnosing the same checkout-mtime mechanism because
nothing recorded that the previous four sessions had already found it. It
was fixed the same day by replacing the mtime comparison with a
content-hash stamp keyed to the artifact's own bytes (commit `f9c043a6`,
13:35): "a machine that already has a fresh build installed *before*
switching branches... could see source mtimes 'newer' than an install that
is not actually stale."

**2. The shared git stash was corrupted.** `docs/evidence/2026-07-28-drc-
coating-failopen-fix.md` records a session running `git stash` /
`git stash pop` in direct violation of this project's own hard rule (the
stash ref is shared across every worktree) and popping a **different**
session's entry — a race against a concurrent session on
`fix/unresolved-ref-policy-single-source` that briefly placed four unrelated
files in the wrong working tree and dropped that other session's stash
entry outright. Recovery required tagging a dangling commit object before
GC could reclaim it and hand-writing a patch file for the other session to
apply. A second session
(`docs/evidence/2026-07-28-pd3-retarget-keepout.md`, in its own test-fixture
notes) independently reports the stash ref "has already corrupted another
session's entry." A third invocation
(`docs/evidence/2026-07-28-pd3-retarget-slots.md`) was an accidental
same-rule violation that happened to be harmless only because nothing was
uncommitted at the moment it ran. Three violations of one hard rule in one
day, one with real cross-session damage, because the rule exists precisely
because the ref is shared and nothing enforces the rule mechanically.

**3. Disk was exhausted twice by the same regenerable-artifact multiplier.**
Commit `dc8de067` (01:07) found `.claude/worktrees` at **51 GB**, driven by
every worktree cold-compiling all 9 pyo3 crates independently (`uv sync`
resetting `.venv` forced the rebuild a second time on top of that) —
23 GB was reclaimed by deleting 258 per-worktree `target/`/`.venv`
directories. Commit `83ffbdd3` (08:45), the same day, records manual
cleanup taking the tree from **~79 GB to 15 GB**, and **within the hour**
agent worktrees had put **11.3 GB** of fresh `.venv` back — "the worktree
disk problem is a rate problem, not a backlog." The same commit records
hand-cleanup itself causing a real data-loss incident, twice: `target/`
directories held 472 *tracked* files until commit `6f5a71f2`, and any
worktree still on an earlier commit has them; deleting by name instead of
by `git check-ignore` destroyed **10,612 tracked files** on the first
occurrence and had to be undone both times.

**4. The checkout's branch moved under sessions that didn't expect it.**
`docs/STRATEGY.md` (§ "Tempco was never analysed...") records a coordinator
`git checkout -B` instruction landing in the **shared** checkout instead of
an isolated worktree, repointing the branch an in-progress agent session
was on and stashing its edits mid-task — caught only because the agent
re-ran its own gate and saw exit 3 where it expected 0. The same friction
recurred today in a milder, self-inflicted form: two of the PD3-retarget
sessions (`pd3-retarget-keepout.md`, `pd3-retarget-relay.md`) opened in
worktrees whose own prior HEAD was an unrelated branch, and had to
re-point their own local branch onto the task's named base commit before
starting — safe because it was each session's own worktree, but the same
underlying fact (a worktree's branch pointer is not guaranteed to already
be where a new task expects it) that made the shared-checkout case
dangerous.

**5. At least one agent stalled before reaching its own stated
falsifier**, and the commit landed anyway.
`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
covers the consequence: a merge commit (`a1fe623e`/`52ccd14c`) recorded
that its own implementing session had stalled before running the
measurement it had itself specified as the check that would confirm the
fix was safe. The fix's diagnosis was correct; the un-run measurement would
have caught a 12x routing-completion regression before it reached the
tree. Stalling is not a code defect either — it is exactly the same
category as the other four: a process cost that a swarm of concurrently
running sessions incurs at some non-zero rate, silently, unless something
outside any one session's own code changes is watching for it.

## The pattern

**None of these five incidents are bugs in the code any session was there
to change.** Extension staleness is a false positive in a freshness *gate*.
Stash corruption is a consequence of one ref being shared across every
worktree with no serialization. Disk exhaustion is regenerable build output
multiplying once per worktree with no shared cache. Branch-pointer churn is
a worktree's HEAD not being where a new task assumes it is. Stalling is a
session simply not finishing its own stated plan. **The common shape: each
of these is invisible from inside any single session's own diff.** A
session that hits the stale-extension false positive re-diagnoses it from
scratch because nothing it touched is broken — the *shared* `.venv` is.
A session that stalls produces a merge commit whose message says so in
plain language, and the commit lands anyway, because "stalled before its
own falsifier" is not itself a gate that blocks a merge.

**The infrastructure fixes that exist so far each targeted one shared
resource.** `dc8de067` shared the Cargo target directory. `83ffbdd3` built
a safe, `git check-ignore`-gated `--clean-artifacts` flag rather than
relying on hand-cleanup (the mechanism that had already destroyed tracked
files twice). `f9c043a6` replaced a checkout-relative signal (mtime) with a
content-relative one (a source-digest stamp) specifically because the
mtime signal could never be made safe under `git checkout -b`'s own
behavior. **None of the three touched `.venv` sharing itself** — the same
mechanism (`UV_PROJECT_ENVIRONMENT` pointed at the main checkout's
already-synced `.venv`) that every one of today's five stale-extension
false positives independently hit is still the load-bearing workaround for
disk pressure, not a resolved problem. It is the shared-state axis every
fix so far has routed around rather than closed.

## Guidance

1. **Treat a shared stash ref, a shared `.venv`, a shared Cargo target
   directory, and shared disk as first-class hazards in any multi-worktree
   agent setup — not as implementation details beneath a task's own
   scope.** Every incident above cost more investigation time than the
   code change any of the five sessions was actually there to make.
2. **A freshness/staleness gate that keys on filesystem mtime cannot be
   made safe under `git checkout -b`**, which stamps every tracked file
   with the checkout instant regardless of content. Key freshness checks
   on content (a source-digest hash) wherever the check feeds a merge-
   blocking decision, and reserve mtime for advisory signals only.
3. **Never run `git stash` in a worktree whose object database (and stash
   ref) is shared with other active sessions** — this project's own hard
   rule exists because the ref has already been corrupted by exactly this.
   Prefer `git show <ref>:<path>` into a standalone file, or a plain
   `git diff`/`git restore`, for any fail-before/pass-after comparison that
   doesn't need to touch the working tree at all.
4. **Disk reclamation in a shared multi-worktree tree needs a
   confirmed-safe, automatable mechanism (`git check-ignore`-gated, name-
   list-independent) before it needs a bigger disk.** Hand-cleanup under
   time pressure is how a repo loses 10,612 tracked files; a rate problem
   (new worktrees regenerating gigabytes within the hour) is not solved by
   a one-time manual sweep regardless of how large.
5. **Before starting work in an existing worktree, confirm its branch
   pointer is actually where the task assumes it is** — re-point the
   worktree's own local branch rather than assuming a stale HEAD is safe to
   build on, and never run a branch-repointing command (`checkout -B`,
   `reset --hard` to a different ref) against a checkout another session
   might be using.
6. **A session's own merge commit naming its unreached falsifier is a stop
   sign a gate should be able to see, not just a sentence a human has to
   notice.** Until "the implementing session's stated falsifier was never
   run" is itself a machine-checkable precondition on a merge, this class
   of cost recurs regardless of how many shared-resource fixes land.

## Why This Matters

Every fix documented in this project's `docs/solutions/` corpus is, by
definition, a real defect found and closed. These five incidents are the
other ledger: real cost incurred by a multi-agent swarm that had nothing to
do with any defect in the hardware design, the router, or the DRC
generator any session was assigned to work on. A team that only measures
"defects found and fixed" undercounts its own throughput cost by exactly
this category — disk cycling through 79 GB → 15 GB → +11.3 GB within an
hour, five independent sessions re-diagnosing the identical mtime artifact,
a stash pop that briefly erased another session's uncommitted work — none
of which shows up in a diff, a test count, or a gate's pass/fail history,
because none of it is a defect in what any session wrote. It is the
overhead of the worktrees themselves sharing state that was never designed
to be shared safely.

## When to Apply

- Setting up or auditing any multi-agent, multi-worktree development
  workflow against one shared checkout — inventory every resource the
  worktrees share (object database, stash ref, `.venv`, build-cache
  directory, disk) before trusting that isolation at the worktree level
  implies isolation of everything inside it.
- Before trusting a freshness/staleness gate's verdict in a shared-`.venv`
  worktree — check whether it keys on mtime (unsafe under `git checkout
  -b`) or content (safe).
- Before running `git stash` for any reason in a worktree sharing an
  object database with other active sessions — use `git show`/`git diff`/
  `git restore` instead; there is a hard rule against it here for a reason
  already proven out three times in one day.
- When disk pressure appears in a shared multi-worktree tree — build or
  use a `git check-ignore`-confirmed, automatable cleanup mechanism before
  resorting to hand-deletion under time pressure.
- When a session's own commit message reports an unreached falsifier or a
  stall — treat the change as unverified regardless of how sound the
  reasoning that preceded the stall reads.

## Examples

```
# The mtime trap, hit independently 5 times in one day:
git checkout -b <task-branch>   # stamps every tracked source file's mtime
                                 # = now, regardless of content
UV_PROJECT_ENVIRONMENT=<shared .venv>   # .so mtime = whenever it was last built
check_stale_extensions.py: source mtime > .so mtime -> "STALE"
  # ... even when the .so's content exactly matches these sources.

# Fixed by keying on content instead (commit f9c043a6):
stamp = sha256(crate_source_files())   # written beside the installed .so
if stamp matches recomputed digest: FRESH, regardless of any mtime
```

```
# The stash incident (docs/evidence/2026-07-28-drc-coating-failopen-fix.md):
git stash            # push MY changes           <- violates the hard rule
git stash pop         # pops a DIFFERENT session's entry (race, shared ref)
  -> 4 unrelated files land in my working tree
  -> the other session's WIP is now a dangling stash entry

# Recovery, using no further stash subcommand:
git tag rescued-wip-<branch-name> <dangling-commit-sha>   # preserve it
git restore <the 4 unrelated files>                        # undo the pop
git stash show -p stash@{0} | git apply                    # recover MY work
                                                             # (stash@{0} left
                                                             #  untouched)
```

```
# The disk-cycle numbers, same day, two commits:
dc8de067 (01:07): worktrees at 51 GB -> 28 GB (23 GB reclaimed,
                    258 per-worktree target/+.venv dirs deleted)
83ffbdd3 (08:45): worktrees at ~79 GB -> 15 GB (manual cleanup)
                   -> +11.3 GB of fresh .venv within the SAME HOUR
                   -> hand-cleanup itself destroyed 10,612 TRACKED files
                      once (undone), because target/ held tracked content
                      until 6f5a71f2 and name-based deletion doesn't check
```

## Related

- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  — the merge commit that recorded its own stalled-before-falsifier state
  and landed anyway; instance 5 above.
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md`
  — a sibling multi-worktree hazard from earlier in the project: code
  silently dropped during parallel-worktree merge conflict resolution,
  the same "isolation at the worktree level does not imply isolation of
  everything that touches it" root cause, in the merge step instead of the
  build/stash/disk layer.
- `scripts/check_stale_extensions.py` — the mtime-based gate; see its own
  docstring (lines ~103-116) naming the checkout-mtime blind spot before
  this day's fix closed it.
- Commit `f9c043a6` — the content-hash freshness fix.
- Commit `dc8de067` — the shared Cargo target directory and the 51 GB/23 GB
  disk figures.
- Commit `83ffbdd3` — `--clean-artifacts`, the 79 GB → 15 GB → +11.3 GB
  cycle, and the 10,612-tracked-file hand-cleanup incident.
- `docs/evidence/2026-07-28-drc-coating-failopen-fix.md` — the full stash
  corruption incident and its recovery, with no further `git stash` used.
- `docs/evidence/2026-07-28-pd3-retarget-keepout.md`,
  `-pd3-retarget-slots.md`, `-pd3-retarget-relay.md`,
  `-drc-courtyard-condition-fix.md` — four of the five independent
  stale-extension false-positive diagnoses, plus the branch-repointing
  precedent.
- `docs/STRATEGY.md` (§ "Tempco was never analysed, and a fourth part is
  fabricated") — the coordinator `git checkout -B`-in-the-shared-checkout
  precedent.

---

## A sixth incident, 2026-07-29: a stash killed by its own timeout, recovered by luck rather than by process

A `git stash` used for an A/B baseline comparison (route the board, stash,
route again, compare) was followed by a command that ran past a 10-minute
timeout; the shell that would have run `git stash pop` was killed before it
executed. The stashed work survived only because `stash@{0}` had not yet
been touched by anything else — in a stash list already **82 entries deep**
in this shared checkout — and `HEAD` had advanced in the meantime (a
different session committed) while the working tree sat clean, showing no
sign anything was missing. Recovery worked: `git stash show -p stash@{0} |
git apply` restored the work without needing `git stash pop` at all.
Recovery working is not the same as recovery being safe — an 82-entry
stash list is exactly the depth at which "just pop it back" stops being a
reasonable assumption, because any of the other 81 entries could have been
reordered, dropped by GC, or popped by a concurrent session in the interval
between push and the intended pop, as instance 2 above already
demonstrates happened for real. This session separately had staged
(uncommitted, not stashed) work swept into another session's commit three
separate times in the same shared checkout — a distinct mechanism from the
stash-ref race (index/working-tree state shared across sessions rather than
the stash ref specifically) but the identical root cause: state assumed to
be session-local that is not.

**The addition to guidance point 3 this incident earns:** for any
before/after or A/B comparison in a checkout shared with other active
sessions, use `git worktree add --detach <ref>` to materialize the
comparison point in an isolated directory, measure there, and remove the
worktree when done — never `git stash`, even briefly, even for a comparison
expected to take seconds. A worktree's isolation does not depend on timing,
a shared ref staying quiet, or the triggering command finishing before a
timeout; `git stash` depends on all three.

```bash
# WRONG -- even a "quick" A/B stash is exposed to a killed shell, a shared
# 82-deep stash list, and a HEAD that can move under you before the pop:
git stash push -m "baseline A"
route_and_measure()          # if this exceeds the command timeout, the
git stash pop                # pop below never runs
route_and_measure()

# RIGHT -- isolated by construction, no shared ref involved at any point:
git worktree add --detach /tmp/baseline-a HEAD
(cd /tmp/baseline-a && route_and_measure())
route_and_measure()           # measure "B" in the current checkout, untouched
git worktree remove /tmp/baseline-a
```

**Related to this instance specifically:** guidance point 3 above (now
extended with the `git worktree add --detach` recommendation) and instance 2
in this same document (the stash-ref race with real cross-session damage) —
the shared thread across both is that a shared checkout's stash ref and
index are never actually safe to use for a task's own bookkeeping,
regardless of how briefly.
