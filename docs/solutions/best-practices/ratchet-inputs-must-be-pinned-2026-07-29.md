---
title: "A ratchet whose inputs are not pinned cannot be ratcheted — a DRC ceiling describing a board that no longer exists, checked by a gate that currently cannot run"
date: "2026-07-29"
category: best-practices
module: ci_infrastructure
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a CI gate compares a measured number against a recorded ceiling/baseline and the recorded value carries a provenance block (a commit, a file hash, a tool version)"
  - "the same tool, run against the same file, is expected to produce the same category breakdown in CI and locally, and hasn't been checked to"
  - "a rule/config file the measurement depends on is generated at build time and its tracked-vs-gitignored status has never been checked"
  - "a red gate is being written off as environment flake without first confirming every input that could move the number is pinned"
tags:
  - ratchet-design
  - measurement-provenance
  - drc-ceiling
  - untracked-generated-file
  - cross-environment-reproducibility
  - gate-rot
---

> **Status update (2026-08-03 refresh):** every state claim below has since been resolved — the `source` enum typo was fixed (`2026-07-28-provenance-source-typo-fix` `_march` entry), `pcb/temper.kicad_dru` is now git-tracked, and the ceiling was re-measured for real (120 samples) with per-category `_march` attribution. The examples below are the historical record of the outage; the guidance stands.


# A ratchet whose inputs are not pinned cannot be ratcheted

## Context

`power_pcb_dataset/drc_ceiling.json` records, per board, a `provenance`
block: the commit it was measured at, a sha256 of the board file it was
measured against, and the DRC tool version. For `pcb/temper.kicad_pcb` that
block currently reads `measured_at_commit: 2d67ee4769b4...` and
`sha256: 815512088fdb81b0b087fe6ed14339096644c2ccc57478f2270039f348098ef1`
— which is exactly the content of `pcb/temper.kicad_pcb` at commit
`65bd0159` (verified: `git show 65bd0159:pcb/temper.kicad_pcb | sha256sum`
reproduces that hash exactly). Two PCB-touching commits have landed since
(`f81317e5`, routed creepage-extension slots; `5ef309d8`, re-targeting
those slots from 8.0mm to 12.6mm for PD3), and the board today hashes to a
third, different value. The ceiling describes a board that no longer
exists, and it has drifted further at least twice since the file's own
provenance block was last written.

**This project already built a gate for exactly this.**
`scripts/check_measurement_provenance.py` exists specifically to fail
closed when a measurement's recorded input hash no longer matches the
input file's current content — its own docstring cites the motivating
incident: a 91-error ceiling that stayed byte-identical through three
board-changing commits while the true count rose to roughly 710. Running
it today does not report the board as stale, however — it errors before
reaching that check at all:

```
GATE RESULT: ERROR -- not PASSED, not a violation. 0 stale record(s), 1 problem(s).
  [ERROR] power_pcb_dataset/drc_ceiling.json#boards.temper: malformed
  provenance: 'source'='measured-live-5-samples' must be one of
  ('measured-live', 'backfilled-historical')
```

The ceiling file's `provenance.source` field was written as
`"measured-live-5-samples"` — a value nobody added to
`measurement_provenance.py`'s `VALID_SOURCES` enum. The purpose-built
anti-staleness gate does not currently detect the board drift it exists to
catch, because a schema mismatch stops it before the hash comparison runs.
A gate built specifically to close this hole is itself now the kind of gate
`docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
catalogs: present, wired, and not currently capable of failing on the exact
condition it was written for.

**Pinning the board is necessary but not sufficient.** Even a board-hash
check that ran cleanly would not close the whole gap: the same commit and
the same board file reportedly produce `copper_edge_clearance 49` /
1050-error aggregate in CI, versus `creepage 62` and `track_width 39`
(categories CI never reports at all) locally — while a bare
`kicad-cli pcb drc --all-track-errors` invocation against the identical
file reports 15 copper-edge violations and zero of both `creepage` and
`track_width`. Three different counts, from what should be one
deterministic tool run against one pinned artifact. And
`pcb/temper.kicad_dru` — the DRC rule file the board is actually checked
against — is a **generated** file: `git status --porcelain` reports it
untracked (`?? pcb/temper.kicad_dru`), `git check-ignore -v` confirms it is
**not** gitignored either, and no CI step in this repository regenerates
it. Whichever copy of that file happens to sit on disk at measurement time
is silently part of the ceiling's real, uncontrolled input set.

## The pattern

A ratchet — a ceiling, ledger, or baseline a gate is only allowed to
tighten, never loosen without explicit approval — is only as meaningful as
the set of things that can move its number. **Board bytes, DRC rule file
content, tool version, and which engine's findings are being counted are
four independent inputs; pinning one and leaving the other three free
still produces a red gate nobody can attribute.** `drc_ceiling.json` pins
two of the four (board sha256, `kicad-cli` version) and, at the moment its
own anti-drift gate is broken, isn't even successfully enforcing those.
The rule file and the CI-vs-local-vs-bare-invocation category discrepancy
are entirely unpinned — nothing in the repository records what
`pcb/temper.kicad_dru`'s content was when any of the recorded numbers were
measured, or which of the three observed category sets ("CI's," "local's,"
"kicad-cli's own default invocation") a given ceiling entry is supposed to
be compared against.

**An unattributable red gate gets written off as flake, and that is
precisely the failure mode this project has already lost a real capability
to once.** `docs/METHODOLOGY.md`'s history records a removed capability
that hid behind a "nondeterministic on CI runners" comment — the same
shape as a gate whose red result cannot be traced to a specific changed
input, because the natural, cheap response to "I can't tell why this is
red" is to assume it's noise rather than signal.

## Guidance

1. **Before trusting any ratchet's green/red verdict, enumerate every input
   that could move the measured number, and check each is pinned and
   reproducible — not just the one the ratchet's own provenance block
   happens to record.** For a DRC ceiling: board bytes, rule file bytes,
   tool binary version, and which engine/invocation path produced the
   count. `drc_ceiling.json` records two of these; the other two
   (`pcb/temper.kicad_dru`'s content, and CI-vs-local-vs-bare-invocation
   category agreement) have never been checked.
2. **A generated file that is neither tracked nor gitignored is an
   uncontrolled input by construction** — whatever happens to be on disk at
   measurement time (last generated when, by whom, from which rule
   source) silently becomes part of every downstream number. Either track
   it (so `git diff` shows every change) or gitignore it and regenerate it
   deterministically as an explicit CI step before the measurement that
   depends on it runs — leaving it in neither state is the one option that
   guarantees it can't be reasoned about.
3. **When the same tool, same file, same commit produces different
   category breakdowns in two environments, treat that as the finding, not
   as noise to average away.** `copper_edge_clearance 49`/1050-aggregate in
   CI versus `creepage 62`/`track_width 39` locally versus 15/`0`/`0` from
   a bare invocation are not three noisy samples of one true number — they
   are evidence that "which engine's findings are being counted" is itself
   an unpinned input, and no amount of re-running any one of the three
   configurations resolves that.
4. **A schema/enum drift in a gate's own input file is a gate outage,
   report it as one.** `check_measurement_provenance.py` was purpose-built
   for exactly the staleness this doc opens with, and currently cannot
   reach that check because `drc_ceiling.json`'s own `source` value
   (`"measured-live-5-samples"`) was never added to the gate's accepted
   enum. A gate that errors before evaluating its target condition is
   indistinguishable, from CI's perspective, from a gate that was never
   wired at all — see
   `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`'s
   catalog of mechanisms that leave a check green (or, here, silently
   non-blocking-red) without ever reaching the logic that matters.
5. **Re-measure and re-pin on every commit that changes a pinned input**,
   not on a schedule. `drc_ceiling.json`'s provenance was last written
   against `65bd0159`; two more PCB-touching commits (`f81317e5`,
   `5ef309d8`) landed after it with no re-measurement, deepening the drift
   this doc measures rather than closing it.

## Why This Matters

A ratchet's entire value proposition is "this number can only get better,
and any regression will be visible." Both halves depend on every input that
can move the number being nailed down — if the board can drift silently,
the rule file can drift silently, and CI/local/bare-tool can each report a
different number for the same nominal measurement, then "the ceiling says
1017" is not a claim about the board in the repository today; it is a
claim about an artifact-tool-environment combination that stopped existing
at least two commits ago, verified by an anti-drift gate that currently
cannot run its own check. The cost of an unattributable red gate is not
just the immediate confusion — it is the standing invitation to write the
result off as flake, which is exactly the path that has already cost this
project a real capability once before.

## When to Apply

- Before trusting any ceiling, baseline, or ratchet file's recorded number
  as a claim about the current state of the repository.
- Before adding a new field value to a provenance/measurement schema —
  check it against the gate's own accepted enum, or the value will pass
  human review while silently breaking the gate that reads it.
- When a gate that checks measurement staleness reports `ERROR` rather than
  `PASS`/`FAIL` — treat that as the gate being down, not as "no staleness
  found."
- Before treating a generated rule/config file as safe to ignore in a
  reproducibility audit — check both `git status` (tracked?) and
  `git check-ignore` (deliberately excluded?); a file that is neither is an
  unpinned input nobody decided to leave unpinned.
- Before attributing a cross-environment measurement discrepancy to
  "runner flakiness" — confirm the same tool version, same rule file, and
  same invocation flags were used in both environments first.

## Examples

```bash
# The ceiling's recorded hash, reproduced from the commit it names --
# confirms the ceiling was correct for a board that has since moved on:
$ git show 65bd0159:pcb/temper.kicad_pcb | shasum -a 256
815512088fdb81b0b087fe6ed14339096644c2ccc57478f2270039f348098ef1  -
# matches power_pcb_dataset/drc_ceiling.json's recorded sha256 exactly.

# The board today (two PCB-touching commits later) hashes to something else
# entirely -- the ceiling's provenance no longer describes what gets DRC'd.
$ git show HEAD:pcb/temper.kicad_pcb | shasum -a 256
7b0dbcf4e42cdac32d60b6454f76d25f5cdd6120b73bf13cb2b10041469adbac  -
```

```bash
# The purpose-built anti-staleness gate, run today -- errors before it can
# even compare the hash above against the recorded one:
$ python3 scripts/check_measurement_provenance.py
GATE RESULT: ERROR -- not PASSED, not a violation. 0 stale record(s), 1 problem(s).
  [ERROR] power_pcb_dataset/drc_ceiling.json#boards.temper: malformed
  provenance: 'source'='measured-live-5-samples' must be one of
  ('measured-live', 'backfilled-historical')
```

```bash
# The generated-but-neither-tracked-nor-ignored rule file:
$ git status --porcelain pcb/temper.kicad_dru
?? pcb/temper.kicad_dru
$ git check-ignore -v pcb/temper.kicad_dru; echo "exit=$?"
exit=1   # not ignored -- and not tracked either (see above)
```

## Related

- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
  and `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` —
  the taxonomy of ways a gate can exist, run, and still not catch its
  target defect; the provenance gate's current `ERROR`-before-check state
  is a new instance of the same family, caused by schema drift rather than
  `continue-on-error` or a narrow scope.
- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — the sibling lesson this doc specializes: a measurement is only valid
  for the commit/artifact state that produced it, generalized here to "a
  ratchet's ceiling is only valid for the full input tuple that produced
  it," of which the commit is one component among several.
- `docs/solutions/best-practices/characterize-oracle-noise-floor-2026-07-26.md`
  — establishes that `kicad-cli` itself has irreducible run-to-run noise on
  a byte-identical file; this doc's CI-vs-local-vs-bare discrepancy is a
  distinct, larger-magnitude gap that noise-floor characterization alone
  does not explain, since the categories involved (`creepage`,
  `track_width`) don't appear at all in some of the three configurations.
- `scripts/check_measurement_provenance.py`,
  `scripts/_lib/measurement_provenance.py` — the existing gate and its
  `VALID_SOURCES` enum, currently out of sync with
  `power_pcb_dataset/drc_ceiling.json`'s recorded `source` value.
- `docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md`,
  `docs/evidence/2026-07-28-measurement-provenance.md` — the original
  91-vs-710 incident that motivated building the provenance gate in the
  first place.
- `power_pcb_dataset/drc_ceiling.json` — the ceiling file itself (not
  modified by this doc, per this investigation's scope).
