# via_dangling +17: board, not oracle — attributed to e5a89b1e — 2026-08-07

<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false -->

**Base commit:** `7e1194b776` (`main`), worked in an isolated worktree
(`worktree-agent-ad6d49136abdf2281`). `dirty=false` — this document adds no
tracked-file changes; `power_pcb_dataset/drc_ceiling.json` and
`pcb/temper.kicad_pcb` are untouched, per this task's hard constraints.

## 0. The question

`power_pcb_dataset/drc_ceiling.json` records `warnings_by_type.via_dangling
= 15`. A 130-sample re-measurement on the CI-pinned kicad-cli 10.0.5
(commit `835474e4`, branch `fix/drc-ceiling-remeasure-10.0.5`) measured
**32** (+17) on the current board and correctly withheld it — no
`Ceiling-Approval:` trailer — because that PR could not attribute the rise
with certainty. Its own `_march` entry names the reasoning as
**circumstantial**: a companion investigation had seen the identical
uniform +17 on unrelated commits and PRs (consistent with a global
instrument change), but "no old-board-on-10.0.5 data point exists to test
directly." This document supplies that data point.

**Answer, in one line: the delta is the board, not the oracle** — fully
attributable to a single, already-analyzed, already-merged commit,
`e5a89b1e0f6f5d77e16a11b05a5c0e06ecffca9c` ("fix(router): stop emitting a
zero-length track at every via (#771)"), which was sitting in `main`'s
history the whole time. The "uniform +17 across unrelated commits" signature
that motivated the oracle hypothesis has a simpler explanation: e5a89b1e
landed 2026-08-05 and the ceiling was never bumped, so *every* commit after
it — regardless of what that commit itself touches — inherits a board whose
true `via_dangling` is 32 against a still-stale ceiling of 15. Uniform +17
is exactly what you'd expect from one unbumped ancestor commit, not
exclusive evidence of a global tool-version effect.

## 1. Locating the old board

`drc_ceiling.json`'s committed `provenance.measured_at_commit`
(`3410ee4e1fe8c3a5cce13b9262585016a06fce8d`) does not resolve in git
history. Per this task's instructions, the board the ceiling's numbers were
actually measured against was instead identified by content hash:
`provenance.inputs[0].sha256 =
51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af`.

Hashing `pcb/temper.kicad_pcb` as of every commit that ever touched it
(`git log --all --format=%H -- pcb/temper.kicad_pcb`, 52 commits) finds
exactly one match:

```
$ git show de59c045822194bbaffbefeb542cc48f895ecc82:pcb/temper.kicad_pcb | sha256sum
51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af
```

`de59c045` ("feat(pcb): K3 RT314012 swap + validator-gated board write +
DRC ceiling re-measure (#602)", 2026-08-03) is the **old board**. Exactly
two commits changed `pcb/temper.kicad_pcb` between `de59c045` and this
worktree's `HEAD` (`git log --oneline de59c045..HEAD -- pcb/temper.kicad_pcb`):

| commit | date | what it did to the board |
|---|---|---|
| `e5a89b1e` | 2026-08-05 | removed 48 zero-length track segments (one per via) — see §2 |
| `7e3608bc` | 2026-08-06 | moved R24 (unrouted, zero segments on its nets) for a barrier-admissibility fix; its own commit message reports "unchanged from the committed board in every per-type count and both aggregates" |

`design_rules.py` (the source `scripts/generate_kicad_dru.py` reads) and
`pcb/temper.kicad_pro` are both byte-identical between `de59c045` and
`HEAD` (`git diff` empty for both), so the DRU and project rule-severity
settings used below are valid for the old board unchanged.

## 2. e5a89b1e already ran this exact A/B test — on kicad-cli 10.0.4

`e5a89b1e`'s own commit message ("stop emitting a zero-length track at
every via", #771) reports a controlled before/after DRC comparison **on the
old and new board content, both on kicad-cli 10.0.4**, macOS arm64, 12
interleaved sample pairs:

```
tracks_crossing        3      -> 1       (2 of 3 involved a 0.0000 mm track)
clearance               377-378 -> 368    (also now deterministic)
copper_edge_clearance   12     -> 10
shorting_items          199-200 -> 199    (also now deterministic)
TOTAL errors            1261-1263 -> 1247-1249
via_dangling (warning)  15     -> 32
```

Mechanism, from the same commit message: the router's path-emission loop
paired a via's from-layer point with its to-layer point without checking
they were on the same layer, emitting a zero-length `(segment (start X Y)
(end X Y) ...)` at every one of the board's 48 vias (24 on F.Cu, 24 on
B.Cu). A zero-length segment has no extent and cannot carry connectivity,
but KiCad's `via_dangling` check was counting the mere *presence* of a
track item at that point — so the stub suppressed a warning the routing
had already earned. The commit proves this electrically inert, not merely
plausible: union-find over the board's copper graph (segment endpoints as
`(point, layer, net)` nodes, vias tying their two layers) is identical
before and after — 2389 nodes, 51 connected components, same partition —
and `check_netlist_board_reconciliation.py` / `check_footprint_drift.py`
both pass unchanged. All 17 newly-dangling vias are exactly the ones whose
zero-length stub was the *only* track item at that point on that layer (20
such stubs measured; the other 3 have pad or zone copper there, so no
change). `drc_ceiling.json` was deliberately not touched by that commit —
the rise needs approval — and it was reported for the owner, but no
`Ceiling-Approval:` ever landed.

This is already a same-tool-version (10.0.4-vs-10.0.4) A/B that isolates
the board effect from the oracle. What was missing — and what motivated
this task — is the cross-check on the CI-pinned 10.0.5 oracle: does the
*old* board also read 32 on 10.0.5 (oracle explanation) or still 15 (board
explanation, confirming e5a89b1e)?

## 3. Measurement: old board on kicad-cli 10.0.5

**Tooling.** This sandbox has no root. kicad-cli 10.0.5 was obtained the
same way the prior `fix/drc-ceiling-remeasure-10.0.5` measurement did:
`kicad_10.0.5~ubuntu24.04.1_amd64.deb` from `ppa:kicad/kicad-10.0-releases`
(the exact package `.github/docker/ci.Dockerfile:41` pins) plus
`kicad-footprints_10.0.5` and the stock-archive runtime deps
(`libgit2-1.7`, `libnng1`, the six `libocct-*-7.6t64` modules,
`libwxgtk-webview3.2-1t64`, `libmbedtls14t64`/`libmbedx509-1t64`,
`libhttp-parser2.9`), extracted with `dpkg-deb -x` into a user-space
prefix and run via `LD_LIBRARY_PATH` — nothing installed outside `/tmp`.
**This fetches and runs an external binary; it is the same package the
repo's CI pins**, verified before every measurement run:

```
$ kicad-cli version
10.0.5
```

**Board.** `git show de59c045822194bbaffbefeb542cc48f895ecc82:pcb/temper.kicad_pcb`,
written to a *temporary* scratch copy (`/tmp/.../old_board_measure2/`) —
`pcb/temper.kicad_pcb` in this worktree was never checked out over or
modified. Hash re-verified on the scratch copy before measuring:
`51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af` (exact
match). Placed alongside a copy of the unchanged `pcb/temper.kicad_pro`
(same stem) so kicad-cli picks up the project's `rule_severities`
overrides instead of stock defaults, and a `pcb/temper.kicad_dru`
regenerated from `scripts/generate_kicad_dru.py`'s unchanged source — the
same "DRU regenerated first" protocol every `_march` entry since
`2026-08-02-k2-resolve-remeasure` uses.

**Method.** A byte-faithful standalone copy of
`temper_placer.validation._drc_api.run_drc()` (same `--all-track-errors`
flag, same single-thread `KICAD_CONFIG_HOME` pin, same JSON parse —
extracted so it runs without importing the full `temper_placer` package,
which needs a built pyo3 extension this sandbox's ad hoc venv doesn't
have) — the identical harness `835474e4`'s 130-sample measurement used.

**Result: 30 samples, fully deterministic, `via_dangling = 15/15`.**

```
=== aggregate ===
errors:   [1261, 1262, 1263]
warnings: [607]                 (see note on lib_footprint_issues below)

=== errors_by_type (observed range, 30/30 samples) ===
  annular_width:          [4]
  clearance:               [378]
  copper_edge_clearance:   [12]
  courtyards_overlap:      [11]
  creepage:                [185, 186, 187]
  drill_out_of_range:      [4]
  hole_clearance:          [105]
  hole_to_hole:            [3]
  shorting_items:          [199]
  solder_mask_bridge:      [154]
  track_width:             [199]
  tracks_crossing:         [3]
  via_diameter:            [4]

=== warnings_by_type (observed range, 30/30 samples) ===
  lib_footprint_issues:    [169]   <- measurement artifact, see below
  missing_courtyard:       [5]
  pth_inside_courtyard:    [1]
  silk_edge_clearance:     [1]
  silk_over_copper:        [172]
  silk_overlap:            [199]
  track_dangling:          [45]
  via_dangling:            [15]
```

A second, independent 40-sample run (same board and tool, without the
project-file copy — run first, as a quick sanity check before the
protocol was corrected) also reproduced `via_dangling = 15/15` on every
run (errors 842/842, unrelated because that run's stock rule-severities
reclassify some categories between error/warning). **Combined: 70/70
samples of the old board on kicad-cli 10.0.5 read `via_dangling = 15`,
zero scatter.** `nondeterministic_error_types` in the committed ceiling
lists only `creepage` as nondeterministic on this board, and this
measurement reproduces exactly that: `creepage` is the only category with
more than one observed value (185–187, identical to the committed
ceiling's own band), everything else — including `via_dangling` — is
bit-stable.

**`lib_footprint_issues: 169`** is a known artifact of this measurement,
not a real finding: the scratch directory's `pcb/temper.kicad_pro` points
at footprint-library paths that don't resolve from `/tmp`, so kicad-cli
can't find any project footprint library and flags the whole board
(real value on a properly-configured checkout is 11, matching the
committed ceiling). It has no bearing on `via_dangling` or on any of the
four error categories this task asked about, and it is called out here so
it is not mistaken for a real 158-count regression.

## 4. Verdict: board, not oracle

| category | old board / 10.0.4 (e5a89b1e's own A/B, §2) | old board / 10.0.5 (this measurement) | new board / 10.0.5 (`835474e4`, 130 samples) |
|---|---|---|---|
| `via_dangling` | 15 | **15** (70/70) | 32 (130/130) |
| `clearance` | 377–378 | **378** (30/30) | 368 (368/368) |
| `copper_edge_clearance` | 12 | **12** (30/30) | 10 (10/10) |
| `tracks_crossing` | 3 | **3** (30/30) | 1 (1/1) |
| `shorting_items` | 199–200 | **199** (30/30) | 199 (199/199) |
| `creepage` | (DRU rule, unaffected) | 185–187 | 185–187 |
| error total | 1261–1263 | 1261–1263 | 1247–1249 |

The old-board-on-10.0.5 column reproduces e5a89b1e's old-board-on-10.0.4
numbers exactly, on a different platform (Linux x86_64 vs. macOS arm64)
and a different kicad-cli minor version. **The 10.0.4 → 10.0.5 oracle
change contributes ~0 to any of these five categories.** All of them —
`via_dangling`'s +17 and the four falls the task asked to check
(`clearance`, `copper_edge_clearance`, `tracks_crossing`,
`shorting_items`) — move together, by the same amount, only between the
old and new *board content*, never between the old and new *tool version*.
They are the same event: e5a89b1e's zero-length-track removal, and nothing
else. (`shorting_items` shows 0 net movement here because both boards'
observed range already includes 199 as their floor — 199–200 → 199 is a
determinism improvement, not a count change, consistent with the commit
message's own framing.)

This is **not** the "something in the routing genuinely regressed, find
the commit" branch of the task's decision tree in the naive sense — §2
already establishes, with an independent proof (union-find over the copper
graph, unaffected by netlist/footprint-drift gates), that no via or track
that was ever a real connection stopped being one. It *is* the "board, not
oracle" branch: the delta is 100% attributable to a specific, identified,
already-merged commit (`e5a89b1e0f6f5d77e16a11b05a5c0e06ecffca9c`), it is
just not a *defect* — it is the correction of a pre-existing under-count.
32 is what the board honestly measures; 15 was an artifact of the same
zero-length stubs that also depressed `clearance`, `copper_edge_clearance`,
`tracks_crossing`, and `shorting_items`.

## 5. Why the "uniform +17 across unrelated PRs" evidence pointed the wrong way

The companion investigation `835474e4`'s `_march` entry cites — the same
`drc_warnings 489 vs baseline 472 (+17, via_dangling)` delta appearing on
every unrelated commit/PR it checked — is real, but its inference (uniform
⇒ global instrument change) doesn't follow once the timeline is laid out:
e5a89b1e merged 2026-08-05, and `drc_ceiling.json` was never updated to
match (that commit deliberately withheld the update itself, "reported for
the owner"). Every commit and PR built on top of `main` after 2026-08-05 —
regardless of what it touches — carries a board whose true `via_dangling`
is 32, checked against a ceiling still frozen at 15. A single unbumped
ancestor commit produces exactly this signature: constant +17, uncorrelated
with each PR's own diff, because the ceiling's staleness — not the metric
— is the constant.

## 6. Recommendation

- The board's `via_dangling` really is 32, not 15, and has been since
  `e5a89b1e` (2026-08-05). It is fully attributed, not a swept-under
  regression, and independently reproduced on the CI-pinned 10.0.5 oracle
  (this document) in addition to the original 10.0.4 measurement in
  `e5a89b1e`'s own commit message.
- `power_pcb_dataset/drc_ceiling.json` should be re-measured for real
  against the current board (`835474e4`'s 130-sample record already has
  the numbers: `via_dangling: 32`, `warning_ceiling: 489`, plus the four
  correlated error-side falls) and landed with a `Ceiling-Approval:`
  trailer whose `_march` entry names `e5a89b1e0f6f5d77e16a11b05a5c0e06ecffca9c`
  as the cause — not "oracle version," which this document rules out.
- This document makes no change to `drc_ceiling.json` or
  `pcb/temper.kicad_pcb`, per the task's hard constraints; landing the
  ceiling update is a maintainer decision.
