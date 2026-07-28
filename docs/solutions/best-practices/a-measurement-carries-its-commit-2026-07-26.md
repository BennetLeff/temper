---
title: "A measurement carries its commit, or it is not a measurement — four wrong conclusions from stale checkouts in one day"
date: "2026-07-26"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "running a control experiment, survey, or diagnosis in a worktree you did not just create"
  - "about to report a build, crate, or tool as broken, especially as a project blocker"
  - "surveying available capacity (a free input, a free slot, a free gate) before wiring something to it"
  - "an agent's report cites a commit hash you have not checked for ancestry against the branch you care about"
  - "40+ worktrees exist in the repo and you are not sure which ones are still live"
tags:
  - stale-worktree
  - measurement-provenance
  - commit-ancestry
  - evaporated-breakage
  - temporally-wrong-survey
  - control-experiment
  - worktree-hygiene
---

# A measurement carries its commit, or it is not a measurement

## Context

`docs/solutions/best-practices/the-reader-is-not-exempt-2026-07-26.md`
documents six instances where a shell pipeline between a real measurement and
the person reading it silently lied — truncation, exit-code misattribution,
line-wrap, and the like. All six had a real, correct number sitting one layer
beneath the misread. This is the sibling failure one layer further out: **the
number was real, the pipeline was clean, and the checkout that produced it was
old.** Four instances in one day, now outnumbering the six pipeline-reading
errors `docs/METHODOLOGY.md` §5 was originally written for:

| Agent / task | Stale artifact | Consequence |
|---|---|---|
| `temper-drc-rs` control experiment | worktree branched before `12a845e3` (pyo3 0.23→0.29 migration, 2026-07-24) | Declared a crate that builds cleanly "broken," reported to the user as the project's **#1 blocker**, used to rank the entire work queue |
| UVL-02 fault-latch survey | tree predating `d99c88e2` (THM-02 circuit, 2026-07-26) | Correctly found `fault_any_or.C1` free in its own tree and wired to it — `d99c88e2` had already given that input to THM-02 in the tree that exists |
| Bus-capacitor reselection agent | started on `ee9ba6ba`, an unrelated router branch (`chore: update regression cache [skip ci]`) | Work began from the wrong lineage entirely |
| BOM procurement agent | started on `b259419f`, where `docs/hardware/BOM.md` was still **Version 1.1, dated 2025-12-17** — a document unrelated to the current `elec/src` | Reconciliation and conclusions drawn against a BOM eight months out of date |

The `temper-drc-rs` claim was independently re-verified for this document:
`cargo build` and `cargo test` on the current tip both exit 0, **49/49 tests
pass**, and the compiled extension imports and runs `safety_isolation`,
`routing_isolation_barrier`, and `routing_isolation_slot` successfully. Full
re-investigation: `docs/evidence/2026-07-26-temper-drc-rs-arm64-build.md`.

Two distinct sub-lessons live in this table, and they are not the same
failure:

- **Reported breakages that evaporate.** The `temper-drc-rs` case: a real
  failure existed, was already fixed upstream, and the fix predates the
  worktree that "found" it again. The pipeline output was completely honest
  about a tree that no longer exists.
- **Surveys that are internally correct but temporally wrong.** The UVL-02
  case: the survey logic was sound and its conclusion (`fault_any_or.C1` is
  free) was true — *for its own tree*. It was false for the tree that
  actually exists, because a sibling change had landed on the real branch
  after the survey's worktree was cut. This is the more dangerous of the two,
  because nothing about the survey itself looks wrong; only cross-checking
  against the current tip reveals it.

In every case the pipeline was clean and the number was real. Nothing in any
tool's output said which tree produced it.

**A caveat found while re-verifying this document, not in the original
report:** the BOM agent's stale `BOM.md` is independently confirmed (`git show
b259419f:docs/hardware/BOM.md` shows Version 1.1 / 2025-12-17). The claim that
it *also* wrongly reported `ato build` as broken did not hold up under direct
re-testing: `ato build` was run twice against this document's own current,
correctly-based checkout — once with the installed `ato 0.2.69`, once pinned
to `0.2.68` via `uv tool run` — and **both fail** with
`atopile.address.AddressError: Cannot add instance to something without an
entry section`, matching what
`docs/evidence/2026-07-26-bom-blocker-resolution.md` itself already recorded
("`ato build` could not be run in this environment... reproduced on a clean,
unmodified checkout too"). That failure does not evaporate on the current tip
and is not explained by staleness — it looks like a live, separate toolchain
issue. Do not read this document as evidence that `ato build` currently
works; only the stale-`BOM.md` half of that incident is established.

## Guidance

1. **Before trusting a measurement, tool result, or survey conclusion, check
   what commit produced it and whether that commit is an ancestor of the
   branch the conclusion will be acted on.**
   `git merge-base --is-ancestor <fix-commit> <target-branch>` is a five-second
   check that would have caught three of the four instances above before they
   were reported.
2. **A control experiment run in a worktree you didn't just create is not
   control for anything.** If the point of the experiment is "does this still
   fail on the current tree," branch it from the current tip at the moment
   you run it, not from whatever worktree happened to be lying around.
3. **A capacity survey ("is there a free input/slot/gate") has a shelf life of
   exactly until the next commit that touches the same resource.** Re-run it
   against the tip immediately before wiring, not against whatever tree the
   survey was originally done in — see the UVL-02 case, where re-surveying
   against the current tree (which now includes THM-02) reversed the
   conclusion. `docs/solutions/best-practices/fault-latch-fan-in-capacity-budget-2026-07-26.md`
   covers the capacity-tracking side of this same incident.
4. **Record the commit alongside every measured claim**, especially one used
   to rank work or declare a blocker. "X is broken" without "as of commit Y"
   is a claim about the past presented as a claim about the present.
5. **Before ranking anything as a blocker, re-measure in the main checkout**,
   not the worktree the finding came from. This is cheap insurance against
   exactly the `temper-drc-rs` failure mode: a real, expensive-sounding claim
   ("the project's #1 blocker") that a thirty-second ancestry check would have
   downgraded to "already fixed."
6. **Prune stale worktrees; do not just tolerate them as clutter.** Each one
   is a checkout of the past that answers present-tense questions. This
   repository had 40+ live worktrees the day these four incidents occurred
   (`docs/METHODOLOGY.md` §5); at last count in this tree, 51 `git worktree
   list` entries persisted. The scale of the hazard tracks the worktree count
   directly — more stale trees means more chances an agent starts one without
   noticing.

## Why This Matters

The `temper-drc-rs` claim was reported to the user as the project's #1
blocker and used to rank the entire work queue — the highest-leverage wrong
conclusion of the four, from the cheapest-to-prevent mistake. None of these
four required a subtle diagnosis to catch: every one resolves with a single
`git log -1` or `git merge-base --is-ancestor` check against the worktree's
HEAD before trusting what came out of it. What makes this class expensive is
that it produces zero symptoms in the output itself — a clean `cargo build`
exit code, a syntactically sound survey, a normally-formatted BOM document all
look identical whether they came from the tip or from a two-day-old branch.
The staleness is invisible exactly where `docs/solutions/best-practices/the-reader-is-not-exempt-2026-07-26.md`'s
six pipeline failures were visible (in the reading), which is why it needs
its own discipline rather than folding into that one.

## When to Apply

- Before reporting any build/test/tool result as a project-level blocker —
  check the commit it ran against is the current tip, not an old worktree.
- Before trusting a "spare capacity" survey (free input, free slot, free
  resource) more than a few commits old, or from a different worktree than
  the one you're about to wire into.
- Before starting any delegated agent's work — confirm its worktree was cut
  from the current tip, not an arbitrary pre-existing branch.
- Whenever a finding's severity would justify re-prioritizing other work —
  the higher the stakes of the claim, the more the five-second ancestry check
  is worth running first.
- Periodically, independent of any specific investigation: prune worktrees
  that no longer track active work, before disk pressure or accidental reuse
  turns them into measurement hazards.

## Examples

```bash
# Before trusting a "broken" finding from a worktree, check what it's missing
cd /path/to/suspect-worktree
git log -1 --oneline                       # what commit is this tree on?
git merge-base --is-ancestor <known-fix-commit> HEAD \
  && echo "fix included" || echo "fix MISSING — this tree predates the fix"

# Re-verify directly rather than trust the worktree's own report
cd /path/to/current/main/checkout
cargo build && cargo test    # exit 0, 49/49 — the crate is not broken here
```

```
# WRONG: survey conclusion carried across a worktree boundary without re-check
"fault_any_or.C1 is free" (true in worktree cut 2026-07-25)
  -> wired to it in a tree where d99c88e2 (2026-07-26) already claimed it
  -> conclusion was correct for its own tree, wrong for the one that exists

# RIGHT
Before wiring: re-run the same survey against `git rev-parse HEAD` of the
target branch, not the worktree's original branch point.
```

## Related

- `docs/solutions/best-practices/the-reader-is-not-exempt-2026-07-26.md` —
  the sibling failure one layer in: a clean pipeline misread, rather than a
  clean pipeline run against a stale tree. Same root discipline
  (`docs/METHODOLOGY.md` §5, "The reader is not exempt either"), different
  failure surface.
- `docs/solutions/best-practices/fault-latch-fan-in-capacity-budget-2026-07-26.md`
  — the UVL-02/OCP-02 capacity-tracking lesson this incident's second row
  also feeds into.
- `docs/evidence/2026-07-26-temper-drc-rs-arm64-build.md` — the investigation
  that established the crate builds cleanly on the current tip and traced the
  original claim to a pre-`12a845e3` worktree.
- `docs/evidence/2026-07-26-bom-blocker-resolution.md` — records both the
  stale-`BOM.md` starting point and the still-unresolved, non-stale `ato
  build` failure; read before assuming the toolchain issue is the same class
  of problem as the other three rows in this table.
- `docs/METHODOLOGY.md` §5, "The reader is not exempt either" — the
  seven-instance table (six pipeline reads plus the `temper-drc-rs` stale
  worktree) and the "record the commit" rule this document instantiates
  further.

---

## A fifth instance, one day later: two numbers, two different netlists, compared as if controlled

Router V6 completion on `pcb/temper.kicad_pcb` was reported varying
**37.5%–53.1%** across measurements and initially treated as
non-determinism worth root-causing. Seventeen independent process
launches of `route_pcb()` against a fixed commit did find one real,
fixed source of run-to-run output difference — `uuid.uuid4()` generating
KiCad `tstamp` fields, which carries no electrical, geometric, or DRC
meaning — and confirmed it was **not** the completion-rate driver: 10
pre-fix runs at randomized `PYTHONHASHSEED` all produced the exact same
0.375 completion rate and the exact same 60-net failure set, differing
only in `tstamp` values; a post-fix determinism proof (5 consecutive runs)
was byte-identical.

That leaves the 37.5%–53.1% spread itself unexplained by anything
internal to the router, and the honest state of the evidence is
**partial, not closed**: the deterministic code, run 17 times on one
machine, never once reproduced the historical 53.1% figure — it produced
37.5% every time. The same investigation separately, independently
documented that `pcb/temper.kicad_pcb`'s footprint/netlist count changed
during the day (a resync added, removed, and relabeled components — see
`docs/evidence/2026-07-27-pcb-netlist-resync.md`), and flagged, but did
**not** confirm, that the 53.1% figure and the 37.5% figures may have been
measured against two different netlist revisions rather than the same
input run twice. This is stated as **UNVERIFIED** in the router's own
determinism evidence doc, not as a settled explanation — flagged here
precisely because the temptation, mid-investigation, is to reach for
"different netlist size" as a satisfying closure the moment two candidate
explanations (code non-determinism, input drift) are both on the table,
without actually pinning down which measurement ran against which commit.

The lesson this instance adds, distinct from the four above: **a
completion-rate, coverage, or count comparison across two points in time
is only a comparison of the same experiment if both measurements are
tied to the commit/artifact-state that produced them.** Where the four
original instances were the *reader* trusting a stale checkout without
checking its age, this one is the *investigator* comparing two numbers
that look like repeated trials of one controlled experiment when they may
be one trial each of two different experiments — and correctly refusing
to collapse that ambiguity into a confident root cause just because a
plausible one (netlist drift) was available. Guidance item 4 above
("record the commit alongside every measured claim") is exactly the
missing practice that would resolve this cleanly: neither the 53.1% board
nor the 37.5% runs were logged against a specific netlist/footprint-count
fingerprint at measurement time, so reconstructing which ran against which
after the fact is now an archaeology problem rather than a lookup.

**Related to this instance specifically:**
`docs/evidence/2026-07-27-router-determinism.md` (the `uuid4`/`tstamp` root
cause and the byte-identical post-fix proof), `docs/evidence/2026-07-27-committed-route.md`
(the original 37.5%–53.1% four-run observation), `docs/evidence/2026-07-27-pcb-netlist-resync.md`
(the footprint/netlist count changes during the same day, flagged but not
tied to the completion-rate spread).
