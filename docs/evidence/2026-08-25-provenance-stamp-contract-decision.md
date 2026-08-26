<!-- provenance: commit=c2c73c50563756db6de760bba0cf9ed070f93000 dirty=false (clean tree; measurements below are git-history queries against origin/main at this commit, plus two gate runs. No source, board or gate file is modified by this document.) -->

# Provenance-stamp contract: decision — auto-derive the default, require the assertion only where it carries information

**Date:** 2026-08-25
**Base:** `origin/main` @ `c2c73c505`
**Question:** the evidence-provenance and measurement-provenance gates are correct and are re-broken by ordinary merges. Enforce harder, drop them, or change the contract?

## Decision, up front

**Change the contract, do not change the enforcement.**

Default `commit=` to the commit that introduces the file, computed, and require
a hand-written stamp only when the author measured against a *different* tree.
Keep both gates exactly as strict about everything else.

The data below says the gates are catching something real a third of the time
and transcribing something git already knows the other two thirds — and that
the transcription is what fails, at a rate of 45%.

---

## 1. The data

All figures are git-history queries against `origin/main` at
`c2c73c505`; the reproduction is §5.

### 1.1 The repair rate

```
evidence-provenance gate introduced   2026-07-26  (464bd0589)
dedicated repair commits since        37
                                      ~1.2 per day, every day, for 30 days
```

Thirty-seven commits whose entire content is repairing provenance stamps —
`stamp`, `backfill`, `repoint`, `expand SHA`, `repair provenance gate`. The
first lands eight days after the gate itself.

### 1.2 The land-failure rate

21-day window, files added under `docs/evidence/`:

| | |
|---|---:|
| files added | 480 |
| **landed without a conforming stamp** | **214 (45%)** |
| later repaired | 187 |
| still non-conforming today | 27 (allowlisted or below the gate's stricter scan) |

Nearly half of all evidence files fail the gate at the moment they land, and
87% of those are fixed afterwards by someone else.

### 1.3 The board-side equivalent

| 21-day window | |
|---|---:|
| `pcb/temper.kicad_pcb` changes | 20 |
| `temper_constraints.references.yaml` re-pins | 13 |
| **board changes with no re-pin** | **7 (35%)** |

### 1.4 The decisive measurement: what the repair actually writes

For every evidence file that landed unstamped and was later repaired, compare
the stamped commit against the commit that introduced the file:

```
repaired stamps examined                              197
  stamp == introducing commit (or its parent)         134   (68%)
  stamp == some other commit                           63   (32%)
```

**Two thirds of repaired stamps carry no information git did not already have.**
The repairer looked up the introducing commit and typed it in.

**One third do.** Those are the case the gate exists for — a document measured
against a different tree than the one it lands in. That is not a small
residual; it is 63 real assertions in three weeks.

---

## 2. Why the obvious options fail on this data

**"Make the context required."** Both gates live in `Board, Provenance &
Requirements Gates`, which is not in `required_contexts` and cannot be added:
it is red for substantive board findings (tank creepage, the isolation-barrier
gates, R38/R42) that no PR can clear. Requiring it wedges every PR — the
`fix-then-require` failure `.github/required-checks.json` documents about
itself. Blocked, not merely expensive.

**"Drop them / accept advisory."** §1.4 says a third of stamps are real
information about which tree a measurement came from. `METHODOLOGY.md` Sec 5 —
"a measurement carries the commit it was taken at, or it is not a measurement"
— exists because four confirmed incidents came from stale-checkout measurements
reported as current. Dropping the gates re-opens that.

**"Install the pre-commit hook."** `.pre-commit-config.yaml` exists and already
carries a `local` hook, but is **not installed** in this checkout — and the
dominant authors here are agents working in 60+ separate worktrees. A hook that
must be installed per-worktree does not reach the population producing the 45%.
Necessary-but-insufficient at best.

**"Keep repairing."** That is the status quo: 37 commits in 30 days, ~1.2/day,
and it does not converge — #1418 re-broke both gates within an hour of the
previous repair.

---

## 3. Why the contract change is what the data supports

The 45% land-failure is not carelessness distributed randomly. It is
concentrated in exactly the case where the required value is **not knowable at
authoring time**: `commit=` must name a commit, and at the moment an author
writes the file the commit it will land in does not exist yet.

Two independent confirmations that this is the mechanism, not a guess:

- `drc_ceiling.json` shipped `"measured_at_commit": "HEAD"` (#1506) — a literal
  placeholder for a value the author could not compute. Fixed in #1510.
- Repairing that same field, I first wrote a **fabricated SHA** — a real 9-char
  prefix with an invented tail — which is verbatim the failure mode
  `check_evidence_provenance.py`'s own docstring documents. Caught by
  `git rev-parse`, not by reading it back.

So the contract asks every author for a value that is derivable-by-default and
unknowable-at-authoring-time, and 45% of the time they do not supply it.

**The change:** when a file under `docs/evidence/` carries no `commit=`, the
gate computes the introducing commit and treats that as the stamp. When the
author *does* write one, it is enforced exactly as today, including the
resolve-check. The dirty flag stays author-supplied — git cannot know it.

This preserves 100% of the gate's discriminating power (§1.4's 63 real
assertions are all cases where the author writes something different, which
still must be written) while removing the 68% that is transcription.

---

## 4. What this does and does not change

**Does not change:** the measurement-provenance gate's content-hash freshness
check, the resolve-check on written SHAs, `--check-shrink`, the UNKNOWN
allowlist, or the requirement that a measurement name its tree. A document
measured elsewhere still has to say so.

**Does not fix** the board-side 35% (§1.3). `references.yaml` re-pinning needs
the board's Sheetpath→Reference map compared, which is mechanical but not
derivable from the file alone. That is a separate, smaller change: a
`--repin` mode that performs the comparison the file's own four prior entries
performed by hand.

**Does not remove** the need for the context split in
`docs/plans/2026-08-24-002-fix-merge-gating-standing-safety-debt-plan.md`. It
removes the largest single source of churn feeding it.

## 5. Reproducing

```bash
# 1.1  repair commits since the gate shipped
git log --since='30 days ago' --format='%h|%ad|%s' --date=short -- docs/evidence/ \
  | grep -Ei 'stamp|provenance|backfill|repoint|expand' | wc -l

# 1.2 / 1.4  land-failure rate and what repairs write
#   for each commit that ADDED a docs/evidence file: read the blob at that
#   commit, test for 'provenance:' + 'dirty=' in the first 12 lines, then
#   compare origin/main's stamped commit against the introducing commit.
#   Full script in this session's transcript.

# 1.3  board changes vs re-pins
git log --since='21 days ago' --oneline -- pcb/temper.kicad_pcb | wc -l
git log --since='21 days ago' --oneline -- \
  packages/temper-placer/configs/temper_constraints.references.yaml | wc -l
```

## 6. What I did not measure

- Whether the 63 "different commit" stamps are *correct* — only that they
  differ from the introducing commit. Some may be wrong in the other direction.
- The 27 still-non-conforming files: whether each is allowlisted or simply
  below the gate's scan. The gate reports 0 violations, so they are covered;
  the discrepancy is my heuristic being stricter, not a hidden backlog.
- Author breakdown (agent vs human) on the 45%. Plausibly the whole story, and
  it would sharpen §2's pre-commit argument, but `git log` author fields do not
  reliably separate them in this repo.
