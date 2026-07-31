# CI Enforcement + Outstanding Board Defects — Handoff

**Date:** 2026-07-31
**Scope:** large — CI gate enforcement, provenance integrity, tank-capacitor placement, PLL floor
**Status:** IN PROGRESS. Branch protection is one step from being enableable. Two board defects are unfixed and one of them makes hardware disagree with firmware.

---

## TL;DR — the three things that matter

1. **`main` is unprotected. Every gate is advisory.** PR #459 merged with the Provenance gate already failing. This is the root cause of every recurring red-gate class below. The aggregator that unblocks protection is now live; **two PRs need a nudge and then protection can go on.**
2. **The board cannot deliver the tank capacitance the firmware assumes.** `tank.c_tank3` is staged *outside the board outline*. The tank needs 3 × CDE `942C16P1K-F` in parallel for 300 nF, and `PLL_MIN_FREQ_HZ = 44000` was derived from that 300 nF. Hardware and firmware currently disagree about resonance.
3. **A real short exists on `main`:** C1 pad2 (`ac_n`) ↔ R7 pad2 (`zcd`), confirmed in **120/120** DRC runs. Both nets are HV domain, so it is a functional defect (it breaks the ZCD divider), *not* an isolation-barrier breach.

---

## Current gate state on `main`

| Job | Cause | Agent-fixable? |
|---|---|---|
| `Board & Netlist Gates` | `MAINS_SELV_ISOLATION_BARRIER` keepout does not exist | **No** — see "keepout falsified" |
| `Requirements Tests` | 75 REQ-SAFE-01 creepage violations / 44 pairs | **No** — needs placement re-solve |
| `Provenance & Anti-Vacuity` | recurs whenever an unstamped evidence doc merges | Yes, but it keeps coming back — see below |
| `Known-Failure Pin Registry Gate` | **undiagnosed** — appeared 2026-07-30, nobody has looked | Unknown |

---

## 1. Branch protection — the exact remaining step

**Why it was blocked:** `python-tests.yml` and `codeql.yml` are path-filtered. Required status checks match by *exact job name*, so a PR touching only non-filtered paths (`pcb/*.kicad_pro`, `CHANGELOG.md`) never reports them and sits on `Expected — waiting for status` **forever**, even with `strict: false`. Rebasing cannot fix that; it is not staleness.

**What was built (merged):** an always-on `Required Checks` workflow (`.github/workflows/required-checks.yml`) that reports a single stable context, `Required Python Tests`.

- Uses `pull_request_target` and checks out **`github.event.pull_request.base.sha`** — the trusted base, never PR head — with `persist-credentials: false` and read-only permissions. This is deliberate: a PR cannot modify the gate that is judging it.
- Semantics: *no matching trigger path is a legitimate skip; a matching path requires the checks.* This unwedges `.kicad_pro`-only and `CHANGELOG`-only PRs without creating a bypass.
- `.github/required-checks.json` holds the trigger-path manifest. `scripts/check_required_checks.py` **validates drift three ways**: `push` list vs `pull_request` list vs manifest. The paths list is duplicated across both triggers in `python-tests.yml`, so any addition must be made twice — the drift check is what stops them silently diverging.
- Poll timeout `2700s`, job `timeout-minutes: 50`. Sized deliberately: the `cp-sat, slow x3` job runs ~20m37s *once started*, and jobs have sat **queued 20+ minutes** under this repo's concurrent load (20–27 in-flight runs). A 30-minute wall would have failed closed on legitimate PRs.

**Acceptance status (measured 2026-07-31):** 9 open main-targeted PRs — **7 report** (1 pass, 5 fail, 1 pending), **2 absent** (#460, #96).

The aggregator fails for the *right* reason; sample output:

```
failed: Type Check (failure)
FAIL: an applicable candidate check failed
```

It correctly distinguishes `pending` (queued) from `failed`.

**The two absences are benign.** `pull_request_target` fires only on `opened` / `synchronize` / `reopened`. #460 and #96 have head commits predating the workflow landing (14:59 on 2026-07-30) and have had no event since.

### Next step, concretely

1. Nudge #460 and #96 (an empty push, or close-and-reopen) so their first aggregator run is created.
2. Confirm all 9 report.
3. Apply protection with **`Required Python Tests` as the sole required context** — *not* the 16 individual checks. Using the single aggregator context is the entire point; requiring the 16 reintroduces the exact-name-matching fragility.

```
# revert, one step
gh api --method DELETE repos/BennetLeff/temper/branches/main/protection
```

Scope it to required status checks only. No required reviews, no push restrictions, no force-push blocking — those are separate policy decisions nobody has asked for.

**Expect protection to block the 5 currently-failing PRs.** That is correct; their underlying checks are genuinely red.

---

## 2. Board defects — unfixed

### `tank.c_tank3` is not on the board

Staged outside the outline, unrouted. An exhaustive search considering **both courtyards and routed copper** found **zero** valid positions: the only courtyard-clean spot sits on a live trace (a real 0.0 mm short), and the only copper-clean spot creates 6 new courtyard collisions. Placing it requires moving/rerouting neighbours.

**Do not "fix" this by dropping it.** The 300 nF is load-bearing for `PLL_MIN_FREQ_HZ = 44000`.

### C1 ↔ R7 short

C1 pad2 (`ac_n`) ↔ R7 pad2 (`zcd`), 120/120 runs. HV-to-HV. Unfixed.

### 75 REQ-SAFE-01 creepage violations / 44 pairs

All are the same boundary crossing (`DC_BUS↔LV_CONTROL`) against the same threshold. **Note the threshold subtlety:** `min_creepage_mm: 8.0` is the IEC requirement, `design_value_mm: 10.0` is the project target, and the test enforces **10.0**. Quoting 8.0 as "the requirement the gate checks" is wrong.

Split: 5 component-level, 28 layout-level. Of the component ones, **only K2/K3 need a genuine new part** — C6 and U3 were `.ato`-vs-board footprint drift (now resynced), and U7 needs footprint authoring, not procurement.

### The keepout is falsified — do not retry it naively

An exhaustive search over every axis-aligned position and all 180° of orientation found the best possible separating line still misclassifies **90 of 318 pads (28.3%)**; HV and SELV centroids are **5.9 mm apart on a 152×234 mm board**. Placing it anyway took `check_isolation_keepout.py` from **1 violation to 84** and left REQ-SAFE-01 byte-identical — a keepout constrains *future* routing and cannot move existing copper.

**This board has no mains/SELV spatial partition.** Fixing it requires re-placement with the barrier as a constraint from the start, not a keepout added afterward. Full numbers preserved in `docs/evidence/2026-07-28-isolation-keepout.md`.

---

## 3. Traps — read before measuring anything

These each cost real time today.

**DRC numbers without `--all-track-errors` are noise.** Bare `kicad-cli pcb drc` swung **69–88 `shorting_items` across four runs on a byte-identical board**. Use `temper_placer.validation._drc_api.run_drc`, which bakes the flag in, 120 samples. Two investigations reached opposite conclusions from this alone.

**A provenance SHA can be well-formed and fabricated.** Two evidence docs cited commits that do not exist, both with a *correct 8-char prefix and a fabricated 32-char tail*:

```
ed5ee134 282083...      real: ed5ee134 bc0ef1...
02e907b9 d19eab77...    real: 02e907b9 a5e1dbca...
```

The second is 40 valid hex characters. `check_evidence_provenance.py` now verifies **existence**, not just format — but note existence is a *scan-level* batch check, so calling `check_file()` directly still misses it.

**Squash-merge orphans the SHA you stamped.** Stamping an evidence doc with its own branch commit produces a dangling reference once the PR is squashed and the branch deleted. Cite something that persists — the PR's `baseRefOid` or merge commit. After GC you cannot distinguish "never existed" from "no longer reachable."

**Match components by sheetpath, not refdes.** `preflight_identity` compares refdes *sets* at a 95% overlap threshold and cannot see a wholesale renumber. A designator can also be *reused*: board `C27` is the DC-link cap, while netlist `tank.c_tank3` has no board counterpart at all.

**A board change stales `drc_ceiling.json` immediately.** This happened three times in one day, twice within ~90 minutes of a fresh measurement landing. The re-measurement is logically *part of* a board change. `scripts/check_drc_ceiling_approval.py` now enforces the `Ceiling-Approval:` trailer on any ceiling raise (it checks per-type **error** ceilings too, which it previously did not).

**The ceiling-raise rule is not "noise only."** `drc_ceiling.json`'s own convention permits a rise for *measured run-to-run noise **or** an already-investigated, attributed, deliberate change* — never to silently absorb an unexplained regression.

**Verify a fix against the canonical library, not the tool's output.** A resync PR was closed because it carried U7's `SOIC16W_Isolated` at 2.05 × 0.6 mm pads where `pcb/libs/lib.pretty/` says 1.65 × 0.6. U7 is an isolator — wider pads mean *less* creepage. It would have merged.

**`resync_pcb_netlist.py` cannot resolve standard-library footprints as committed.** `pcb/fp-lib-table` uses `${KICAD10_FOOTPRINT_DIR}`, which none of this repo's Python expands (only `${KIPRJMOD}`). Still unfixed; work around with a scratch table.

---

## 4. Open decisions for a human

- **Enable branch protection?** Prerequisites are done bar the two nudges. It will block 5 currently-failing PRs.
- **K2/K3 part selection** — the only genuine procurement item. The binding parameter is reinforced creepage; the G5LE-1's pin topology cannot reach the requirement in any footprint.
- **Re-placement with the barrier as a constraint** — the large piece. An earlier `INFEASIBLE` verdict naming 7 isolators for re-sourcing was computed on the *buggy* pad model and must not be inherited; re-derive it, but do not assume it was wrong either.
- **Evidence docs misdated by one day** — five docs are filenamed `2026-07-30` but were committed `2026-07-29T19:34Z`, no timezone boundary crossed. Concurrent sessions appear to have run with a date context a day ahead. Filenames left alone; these are the audit trail for safety decisions.

---

## 5. Concurrency notes

This repo runs many concurrent agent sessions against one `.git` (44 worktrees at last count).

- **Never `git stash`** — the stack is repo-global. A `reference-transaction` hook blocks it. It was fixed on 2026-07-30 to stop aborting git's own `pack-refs`/`gc`; the discriminator is the invoking subcommand read from `$PPID`, which is a *cooperative* control, not a security boundary.
- Work in a throwaway worktree, never the primary checkout.
- Run `git diff --cached --name-only` before every commit — a commit was contaminated with another session's staged work once.
- Duplicated effort is real: two independent board resyncs (#458/#459) and two independent stamp fixes (#483/#487) were produced today. Check `gh pr list` before starting.
- Files can exist only in the primary checkout, untracked, indefinitely. Three such artifacts were committed in #461, including the requirements plan for work that had already merged.
