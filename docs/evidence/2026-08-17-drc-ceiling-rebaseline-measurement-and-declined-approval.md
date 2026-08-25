<!-- provenance: commit=4137658b5dba46aef79b6b3c0bbb436803ee61ff dirty=UNKNOWN -->
# DRC ceiling re-baseline: honest measurement + declined self-approval

**Commit measured**: `2cc9eeb1e` (main). **Board sha256**:
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(verified via `sha256sum pcb/temper.kicad_pcb` before and after this task;
`pcb/temper.kicad_pcb` was not modified by this agent).

**kicad-cli**: `10.0.5`. Extensions rebuilt in this worktree's own `.venv`
(`make venv-isolate` + `make extensions`, after unsetting a conflicting
`CONDA_PREFIX` that made `maturin` fail) — not the shared-checkout `.venv`,
per the handoff's shared-venv warning.

## Summary of this agent's decision

This task's brief asserted that "the owner has authorized this re-baseline"
and "you have that authorization for this task," and asked for the ceiling
raise/tighten to be committed with an R27 `Ceiling-Approval:` trailer.

**This agent measured the board honestly (below) but did not write the
`Ceiling-Approval:` trailer or edit `power_pcb_dataset/drc_ceiling.json`.**
Two independent reasons, either one sufficient alone:

1. **The claimed authorization is not verifiable.** `scripts/check_drc_ceiling_approval.py`
   confirms the entire R27 "ceremony" is a plain substring match on
   `Ceiling-Approval:` in a commit message, plus a `_march` entry and a
   provenance block this agent itself would write. Nothing in the mechanism
   verifies that a human owner actually reviewed or authorized the change —
   it only verifies that *someone* followed the format. `AGENTS.md` and the
   handoff both say this is deliberately "an owner decision, not an agent's."
   An assertion of pre-granted authorization arriving inside a task prompt
   is not the same thing as the repository owner actually saying so, and
   nothing here let this agent tell the difference. Self-issuing the
   approval this rule exists to require defeats the rule.
2. **The task's own factual premises did not hold up under measurement**
   (below) — most importantly, `track_width` is not 0. A ceiling change
   built partly on an unverified authorization claim and partly on an
   inaccurate premise is exactly the failure mode R27 is designed to
   prevent, so this agent stopped short of writing it and is reporting the
   honest numbers instead for the actual owner to act on.

Nothing below changes `pcb/temper.kicad_pcb` or `power_pcb_dataset/drc_ceiling.json`.

## Method

Scratch copy (never the committed board) at
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/drc-rebaseline/`,
with `temper.kicad_pcb` + `temper.kicad_pro` copied from `pcb/` and
`temper.kicad_dru` freshly regenerated via `scripts/generate_kicad_dru.py`
(full project context — omitting `.kicad_pro` hides `annular_width` and
`creepage`). Each run: `kicad-cli pcb drc --all-track-errors --severity-all
--format json`, with `KICAD_CONFIG_HOME` pointed at a scratch KiCad config
carrying `MaximumThreads=1` (mirrors `_drc_api._single_threaded_kicad_env`).

**9 no-refill samples, 4 `--refill-zones` samples.** This is short of R27's
120-sample requirement for nondeterministic categories — sufficient to
characterize what's deterministic and get a first read, not sufficient to
finalize a ceiling. Whoever performs the actual re-baseline should extend
this to 120 for `creepage` (the only category that showed any spread here).

## Results — no-refill (current runner default)

| Category | old ceiling | measured (9 samples) | spread | delta |
|---|---|---|---|---|
| `clearance` | 1117 (true, DRU-bisected) | **238** (raw read, not at 199/499 cap) | 0 | tighten −879 |
| `copper_edge_clearance` | 4 | **12** | 0 | **loosen +8 — regression, see below** |
| `courtyards_overlap` | 1 | 1 | 0 | unchanged |
| `creepage` | 272 (=271+1 headroom) | **110–111** | 1 | tighten −161 |
| `drill_out_of_range` | 4 | **6** | 0 | **loosen +2 — regression, see below** |
| `hole_clearance` | 90 | **26** | 0 | tighten −64 |
| `hole_to_hole` | 3 | **0** | 0 | tighten −3 |
| `shorting_items` | 183 | **53** | 0 | tighten −130 |
| `solder_mask_bridge` | 133 | **15** | 0 | tighten −118 |
| `track_width` | 393 | **120** | 0 | tighten −273 (**not to 0 — see below**) |
| `tracks_crossing` | 1 | **8** | 0 | **loosen +7 — regression, see below** |
| `annular_width` | 0 | 0 | 0 | unchanged |
| `via_diameter` | 0 | 0 | 0 | unchanged |

Warnings:

| Category | old ceiling | measured (9 samples) | delta |
|---|---|---|---|
| `lib_footprint_issues` | 13 | **168** | **loosen +155 — flagged, not in the task's breach list** |
| `lib_footprint_mismatch` | 26 | **0** | tighten −26 |
| `missing_courtyard` | 5 | 5 | unchanged |
| `pth_inside_courtyard` | 0 | 0 | unchanged |
| `silk_edge_clearance` | 1 | 1 | unchanged |
| `silk_over_copper` | 42 | 42 | unchanged |
| `silk_overlap` | 13407 | **199 (CAPPED — true count unresolved)** | **not measured, see below** |
| `track_dangling` | 44 | **0** | tighten −44 |
| `via_dangling` | 25 | **106** (no-refill) / **23** (refill) | **loosen +81 no-refill — regression, see below; refill nearly matches old ceiling** |

## Results — `--refill-zones` (4 samples, separate protocol question)

Deterministic across all 4 samples, no spread on any category.

| Category | no-refill | `--refill-zones` | delta |
|---|---|---|---|
| `clearance` | 238 | 239 | +1 |
| `creepage` | 110–111 | **132** | +21 to +22 (much smaller than the +190 this repo's #1298 measured on the pre-#1312 board — the copper regeneration changed this relationship) |
| `isolated_copper` | 0 (invisible without refill) | **0** | **genuinely 0, deterministic — matches the task's #1312 claim** |
| `via_dangling` | 106 | **23** | **−83 — refill resolves most of what no-refill flags; this reverses the pre-#1312 finding that via_dangling was refill-invariant** |
| everything else | matches within 0–1 | | |

`isolated_copper 0` is real: PR #1312 (`23b5daf8d`) modified
`pcb/temper.kicad_pcb` directly (15,779-line diff, confirmed via `git show
--stat`), unlike the case below. This is the one category from the task's
brief that this measurement fully confirms.

## The premise that didn't hold: `track_width` is not 0

The task's brief stated `track_width 120 → 0 (#1329)` as a settled fact
driving a tighten-to-0. Live measurement (9/9 samples, refill and no-refill
alike) reads **120**, not 0.

Root cause, checked directly: `git show --stat 7979a0ee1` (PR #1329) —
its own commit message states **"`pcb/temper.kicad_pcb` NOT modified
(sha256 unchanged, verified)"**. The PR fixed the pour-stitch generator's
hardcoded 0.3mm width constant in code; it never re-ran the generator
against the committed board. This is the exact "verified on a scratch
copy, fix never applied to the committed artifact" trap
`docs/HANDOFF-2026-08-17.md` §12 documents for PR #1257's zone generator —
it recurred one PR later in the same session, on the same board.

By contrast, `#1316` (`968d1a33d`, annular floor + via dedup) and `#1312`
(`23b5daf8d`, copper regeneration) **did** modify `pcb/temper.kicad_pcb`
(9,901-line and 15,779-line diffs respectively) — their fixes are real on
the committed board, and the corresponding categories (`annular_width`,
`hole_to_hole`, `isolated_copper`) do measure at 0.

**Correct ceiling for `track_width` is 120 (tightened from 393), not 0.**
Setting it to 0 against a board that genuinely measures 120 would not be
"absorbing a regression" (120 is a real improvement over 393) but it would
misrepresent the committed board's actual state and immediately red every
PR touching this gate for a defect nobody applied the fix for yet.

## Genuine regressions (report, don't absorb)

Four error categories and one warning category measure worse than the
stored ceiling on a board whose provenance is stale — per the task's own
hard rule, these are **findings, not numbers to silently ratchet past**:

- `copper_edge_clearance` 4 → 12
- `drill_out_of_range` 4 → 6
- `tracks_crossing` 1 → 8
- `via_dangling` (no-refill) 25 → 106 (but 23 under `--refill-zones`,
  i.e. close to the old ceiling — which protocol governs matters here)
- `lib_footprint_issues` 13 → 168 — **not mentioned in the task's breach
  list at all**, and the largest single regression measured. Needs
  root-causing before any ceiling touches it.

None of these should be silently raised to match the new measurement
without someone attributing the cause (per `AGENTS.md`'s "if you can't
attribute a rise, stop and report it instead of ratcheting past it").
This agent did not attempt that attribution — it is out of scope for a
measurement pass and belongs to whoever owns the actual re-baseline PR.

## Not measured

- **`silk_overlap`**: capped at 199 (the `ERROR_LIMIT` GUI constant, not a
  real count) in every sample. `scripts/measure_uncapped_drc.py
  physical-category silk_overlap` was run; its own output: `raw bucket-pair
  sum silk_overlap: 363 (any_saturated=True)` with the tool's own printed
  caveat that this **double-counts intra-bucket pairs** and "this session
  did not ship a validated total." True count is therefore somewhere
  between 199 and unknown-but-likely-well-under-13407. **Not obtainable in
  this pass** — reported as such rather than guessed.
- **Aggregate `error_ceiling` / `warning_ceiling`**: not computed with
  confidence, because `warning_ceiling` depends on the unresolved
  `silk_overlap` true count.
- **120-sample R27 bar**: not met (9/4 samples taken). The near-zero
  observed spread (only `creepage`, ±1) makes a wider spread unlikely, but
  "unlikely" is not the standard the project's own protocol sets.

## What this agent recommends, not applies

A legitimate re-baseline, once someone with actual owner authority signs
off, should very likely tighten far more than it loosens (per this
measurement: 10 categories tighten, 5 loosen/regress, `isolated_copper`
stays at implicit 0). But the four/five regressions need attribution
first, `silk_overlap` needs a validated bisection, and the sample count
needs to reach 120 for `creepage` — none of which this pass did, on top of
this agent declining to self-issue the approval regardless. That
combination of "not enough evidence yet" and "not this agent's call to
authorize" is why `power_pcb_dataset/drc_ceiling.json` is untouched.

Raw sample files are under
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/drc-rebaseline/`
(not committed — scratch, per the workflow's own convention of keeping
large outputs under `/tmp`).
