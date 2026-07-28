# DRC truth-gate discrepancy: 91 vs 729 — resolved

**Date:** 2026-07-28
**Commit under investigation:** `e87e8b90` (tip of `docs/methodology-loop-discipline` at time of writing)
**Board:** `pcb/temper.kicad_pcb`, sha256 `81551208...098ef1` (verified identical between `git show e87e8b90:pcb/temper.kicad_pcb` and the working-tree file used for every "local" measurement below)

## Falsifier, stated up front

> "The 729 is a local environment artifact and CI's 91 reflects the board a
> fabricator would get. If instead the newer local KiCad is correct, the
> project's DRC debt is ~8x what the ratchet records and the ceiling is
> measuring the wrong thing."

**The falsifier did NOT fire, but not for either of the reasons it names.**
KiCad version is not the cause (see §2 — CI's own `kicad-cli` binary, run
against the exact `e87e8b90` board, reproduces the high number). Environment
is not the cause either. **The 91 and the 729 are correct measurements of two
different boards.** CI run 30305088300 — the run the task cites — did not
test `e87e8b90`. It tested `9ddd7059`, a commit **8.5 hours earlier on the
same branch**. Three commits landed on `pcb/temper.kicad_pcb` between them
(`c6b1b463`, `556ccf4f`, `65bd0159` — a placement re-solve and the first
committed route). The board changed; the ceiling file did not. Read plainly:
**the project's current DRC debt is ~8x what `drc_ceiling.json` records**,
which is the falsifier's "if" clause — it fires, just via a different
mechanism than either hypothesis in the sentence.

## 1. What CI actually ran

```
$ gh run view 30305088300 --repo bennetleff/temper --json headSha,headBranch,event
{"headSha":"9ddd7059e4626250d4de60880d9a88efad1815fb", ...}
```

`9ddd7059` is an ancestor of `e87e8b90` (`git merge-base --is-ancestor 9ddd7059
e87e8b90` → true), created 2026-07-27T15:00:33-06:00. `e87e8b90` was created
2026-07-27T23:35:48-06:00. **No `regression.yml` run exists for `e87e8b90`
at all** — `gh run list --workflow=regression.yml` across every branch shows
nothing at that SHA; the branch's last CI-tested commit is `9ddd7059`, over
two hours before `e87e8b90` was created, and multiple untested commits
(including the acid-trap router fix and three PCB-touching commits) landed on
top of it without a subsequent CI run.

The raw CI log confirms the command and the number precisely:

```
2026-07-27T21:05:22.3824598Z Run uv run python scripts/ci_check_drc.py --backend kicad-cli
2026-07-27T21:05:24.2883088Z FAIL: temper: DRC 91 exceeds ceiling 85 (+6 errors)
```

Same command as the workflow at `e87e8b90` (`git show 9ddd7059:.github/workflows/regression.yml`
has the identical `--backend kicad-cli` invocation and the identical
`ghcr.io/bennetleff/temper-ci:latest` image) — the workflow did not drift
between the two commits. Only the board did.

## 2. KiCad version — determined, and ruled out as the cause

- Local: `kicad-cli version` → **10.0.4**
- CI container: pulled `ghcr.io/bennetleff/temper-ci:latest` (digest
  `sha256:56f08571...`) and ran `kicad-cli version` inside it → **10.0.5**

This is a real difference (patch version), but it is not the mechanism.
Running CI's own 10.0.5 binary, inside CI's own container, directly against
the byte-identical `e87e8b90` board file gives **707 errors** — in the same
band as local 10.0.4's 705–731 (§4). Version bump 10.0.4→10.0.5 accounts for
none of the ~638-error gap.

## 3. Backend confirmed like-for-like

`scripts/ci_check_drc.py --backend kicad-cli` in both environments resolves
to the same code path: `DrcRatchet._check_board` →
`temper_placer.validation._drc_api.run_drc()`, which shells out to
`kicad-cli pcb drc --format json` and counts every violation whose
`severity != "warning"` as an error, grouped by the JSON `type` field. No
`.kicad_dru` file exists in the repo; `pcb/temper.kicad_pro`'s
`rule_severities` block is unmodified between `9ddd7059` and `e87e8b90`
(`git diff` empty). The `rust` backend (`temper_drc_rs`) was never in play —
CI's log line quotes the `kicad-cli` invocation verbatim.

## 4. Reproduction

All raw JSON captured to `/private/tmp/.../scratchpad/drc/*.json` before
being queried (per METHODOLOGY.md §5, "the reader is not exempt" — raw
capture then query, never filter in the measuring pipeline).

### 4a. Current board (`e87e8b90`), local kicad-cli 10.0.4, N=5 raw runs

| run | total violations | errors | warnings |
|---|---|---|---|
| 1 | 1522 | 708 | 814 |
| 2 | 1522 | 708 | 814 |
| 3 | 1519 | 705 | 814 |
| 4 | 1542 | 728 | 814 |
| 5 | 1522 | 708 | 814 |

Warnings are perfectly stable (814/814/814/814/814). Error count varies
705–728 (median 708), consistent with the noise floor already measured and
recorded in `docs/METHODOLOGY.md` §5 ("five `kicad-cli pcb drc` runs ...
`shorting_items` of 124/113/119/120/123 ... spread of 11"). The originally
reported **729** and the final gate run below (**731**) both fall inside
this same noise band — they are not a different measurement, they are the
same measurement with kicad-cli's known ~3% run-to-run jitter on
`shorting_items`/`clearance`.

### 4b. Current board (`e87e8b90`), CI's own container, CI's own kicad-cli 10.0.5

```
$ docker pull ghcr.io/bennetleff/temper-ci:latest
$ docker run --rm -v .../pcb:/work/pcb:ro ... kicad-cli pcb drc --format json ...
Found 1521 violations
```
Errors: **707**, warnings: **814**. Same band as 4a. This is the decisive
control: identical board file, CI's exact binary, CI's exact OS (Ubuntu
24.04, amd64) — and it agrees with local, not with "91". The
environment/version hypotheses are falsified by this run alone.

### 4c. Gate script itself, `e87e8b90`, local, fully synced worktree

```
$ git rev-parse HEAD
e87e8b9021df202742639afe505fb7ad9f730c44
$ uv run --no-sync python scripts/ci_check_drc.py --backend kicad-cli
FAIL: temper: DRC 731 exceeds ceiling 85 (+646 errors)
```

### 4d. Prior board (`9ddd7059` — what CI 30305088300 actually tested), local kicad-cli 10.0.4, N=3

| run | total violations | errors | warnings |
|---|---|---|---|
| 1 | 787 | **91** | 696 |
| 2 | 787 | **91** | 696 |
| 3 | 787 | **91** | 696 |

Perfectly stable across all 3 runs — no noise on this board. This is an
**exact** reproduction of CI's number and CI's per-type breakdown (below).

## 5. Per-type breakdown, both boards, against the five ratchet categories

`drc_ceiling.json`'s `violations_by_type` ceiling and its own `_march` prose
both describe: `shorting_items: 33, solder_mask_bridge: 30,
courtyards_overlap: 15 (measured; ceiling held at 10), clearance: 9,
copper_edge_clearance: 4 (measured; ceiling held at 3)`. Sum = 91.

| Category | Ceiling | `9ddd7059` (CI-tested board) | `e87e8b90` (current board, local run 1 / run 4 / container) |
|---|---|---|---|
| shorting_items | 33 | **33** | 152 / 167 / 148 |
| solder_mask_bridge | 30 | **30** | 154 / 154 / 154 |
| courtyards_overlap | 10 | **15** | 11 / 11 / 11 |
| clearance | 9 | **9** | 337 / 341 / 340 |
| copper_edge_clearance | 3 | **4** | 15 / 15 / 15 |
| **sum (= reported error count)** | **85** | **91** | **708 / 728 / 707** |
| *other error categories* (not in ratchet, implicit ceiling 0) | 0 | **0** | annular_width 4, hole_clearance 24, hole_to_hole 1, tracks_crossing 2–3, drill_out_of_range 4, via_diameter 4 |

Two distinct things happened between the two commits, not one:

1. **Four of the five ratcheted categories exploded** — `clearance` 9→~340
   (38x), `shorting_items` 33→~155 (4.7x), `solder_mask_bridge` 30→154 (5.1x),
   `copper_edge_clearance` 4→15 (3.75x). `courtyards_overlap` is the one
   category that *improved* (15→11).
2. **Six entirely new error categories appeared** that do not exist in
   `9ddd7059`'s DRC output at all: `annular_width`, `hole_clearance`,
   `hole_to_hole`, `tracks_crossing`, `drill_out_of_range`, `via_diameter` —
   39 errors total, currently invisible to the ratchet because
   `violations_by_type` treats any absent category as ceiling 0, but the
   top-level `error_ceiling` check fails first and short-circuits before the
   per-type check ever runs, so these never get individually named in the CI
   output.

This pattern — big jump in the copper-derived categories (clearance,
solder_mask_bridge, shorting_items, copper_edge_clearance) plus new
drill/via/hole categories — is exactly what you'd expect from committing an
actual route on a board that previously had far less copper. `git log
9ddd7059..e87e8b90 -- pcb/temper.kicad_pcb` shows precisely that:

```
65bd0159 fix(pcb): resync board to netlist after OVP-01 Option C re-reference
556ccf4f feat(pcb): commit first route of temper.kicad_pcb (51/96 nets, 53.1%)
c6b1b463 fix(pcb): re-solve placement at full 47-net domain coverage, ...
```

`power_pcb_dataset/drc_ceiling.json` is **byte-identical** between `9ddd7059`
and `e87e8b90` (`git diff` empty) — it was never touched by, or re-measured
against, any of the three PCB-changing commits above.

## 6. Which number is correct

**Both were correct measurements — of different boards.** The mechanical
question the task poses ("why does the same command on the same board give
two answers") has a false premise: it was not the same board. Restated in
terms that matter for fabrication:

- **91 was correct for the board at `9ddd7059`.** That board no longer
  exists at HEAD.
- **~708–731 (median ~710, N=5 range 705–731) is correct for the board a
  fabricator would receive today**, i.e. the board committed at `e87e8b90`.
  This was independently confirmed with CI's own container and CI's own
  `kicad-cli` binary (10.0.5), not just local 10.0.4 — so it is not a local
  toolchain artifact by any measure available.

**The falsifier's dangerous branch is the one that held**: current DRC debt
is roughly 8x the ratchet's recorded number, and it must be stated plainly —
`power_pcb_dataset/drc_ceiling.json` is stale relative to HEAD by three
commits' worth of placement/routing work, and nothing caught it because
**no CI run has ever executed the regression suite against `e87e8b90`.**
The branch has been advancing past its last green (or, here, its last
*red-but-known*) DRC measurement without the gate re-running.

## 7. What should change

Per the hard rule, **no ceiling is raised or loosened here**; the file is
left untouched. Recommended, not executed:

1. **Re-run CI (or the local gate) against the actual current HEAD before
   trusting any DRC number** — the base bug here is a stale measurement, not
   a bad gate. This is the exact failure class METHODOLOGY.md §5 already
   names ("a measurement carries the commit it was taken at, or it is not a
   measurement") — this investigation's own opening premise ("same
   committed board") repeated it a second time, at one layer up (mistaking
   two different CI runs on the same *branch* for two runs on the same
   *commit*).
2. **`drc_ceiling.json`'s `_march` notes and `violations_by_type` need a new
   entry re-measuring against `e87e8b90`** (or whatever HEAD is by the time
   this is acted on), once whoever owns the ratchet has looked at the
   route-quality regression directly — this is a large jump that likely
   reflects an early/unrefined auto-router pass over-produces clearance
   violations, not 38x worse physical design intent. That re-measurement is
   out of scope here (no `Ceiling-Approval:` trailer exists, and this task's
   hard rules forbid touching the ceiling regardless).
3. **The six new, unratcheted error categories** (`annular_width`,
   `hole_clearance`, `hole_to_hole`, `tracks_crossing`, `drill_out_of_range`,
   `via_diameter`) are currently invisible in CI's console output because
   the aggregate `error_ceiling` check short-circuits before the per-type
   loop runs. Whoever re-measures the ceiling should also decide whether
   these are real (they look real — `hole_to_hole`/`drill_out_of_range` are
   physical fab-blocking classes) or an artifact of the new route's via
   choices, and add them to `violations_by_type` either way so they are
   never free again.
4. Nothing about the local environment needs to change. Local 10.0.4 and
   CI's 10.0.5 agree with each other on the same input to within the
   documented oracle noise floor.

## UNVERIFIED

- Whether the specific router/placement pass in `c6b1b463`/`556ccf4f` is a
  known-early/expected-messy first route (the commit message "commit first
  route of temper.kicad_pcb (51/96 nets, 53.1%)" suggests this may be an
  intentionally incomplete/unrefined checkpoint) or an actual regression
  against a cleaner prior route. This investigation did not evaluate route
  *quality* intent, only measured DRC counts before/after.
  Whether the ratchet's authors intended `9ddd7059`'s "91" to gate the new
  route at all, or whether it was already known to be stale, is not
  established here — no commit message or PR comment referencing this was
  found in the time available.
- kicad-cli's per-run jitter was characterized with N=5 on the current board
  and N=3 on the prior board; METHODOLOGY.md's own N=5 measurement (a
  different day, different board state) found `shorting_items` spread of 11
  (~9%). This investigation's N=5 spread on `clearance`+`shorting_items`
  combined (705–731, ~3%) is smaller but the same qualitative phenomenon —
  not independently re-derived from first principles, taken as consistent
  with the prior finding rather than re-proven from scratch.
- Container run used `linux/amd64` under QEMU emulation on an arm64 host
  (Docker printed a platform-mismatch warning). This should not affect
  `kicad-cli`'s DRC arithmetic, and the result it produced (707, matching
  local's native-arch 705–731) is itself evidence the emulation didn't
  change the answer — but true bit-for-bit CI parity (same arch) was not
  tested.

## Verification performed for this task

All commands run from this worktree at `e87e8b9021df202742639afe505fb7ad9f730c44` (rebuilt Rust extensions with `maturin develop --release` after `git reset --hard e87e8b90`, since checkout timestamps invalidated the prior mtimes):

- `check_domain_partition.py` → exit 0
- `capacity_budget_gate.py` → exit 0
- `mpn_fabrication_gate.py` → exit 0
- `check_derived_doc_drift.py` → exit 0
- `check_copper_net_consistency.py` → exit 0
- `check_rust_drc_presence.py` → exit 0
- `check_undeclared_imports.py` → exit 0
- `check_stale_extensions.py` → exit 0
- `make netlist` → exit 0
- `uv run --no-sync python -m pytest elec/validation -q` → 30 passed
