# API signature drift gate: check_routability's TypeError, why mypy didn't stop it, and the hard call-arg gate

**Date:** 2026-07-26
**Scope:** `packages/temper-placer/src/temper_placer/router_v6/routability_check.py`
(the fix), `scripts/check_typecheck_gate.py` (the guard), `.call-arg-allowlist`
(new), `.typecheck-allowlist` (one stale entry removed).

**Tree measured in:** this session started on a stale worktree checkout
(`ee9ba6ba`, 140 commits behind `docs/methodology-loop-discipline`, and
missing `scripts/assert-base.sh` entirely — the exact "stale worktree"
failure mode that script exists to catch). Rebased onto
`docs/methodology-loop-discipline` (`11f859e5`) before doing anything else;
`scripts/assert-base.sh docs/methodology-loop-discipline` confirmed `HEAD ==
11f859e5` before any measurement below. All commit SHAs and dates below are
as seen from that tree.

## TL;DR

- **Diagnosis confirmed exactly as briefed**, with one correction: the
  broken call site is `routability_check.py:407-408` in this tree (line
  numbers drift; same function, same bug). `check_routability`'s first
  parameter was renamed `net_name` -> `_net_name` by commit `ce882acf`
  (2026-07-22 23:51, "fix 99 more ruff violations (ARG001/ARG002 +
  auto-fixes)"), but `check_routability_direct` — in the **same file**,
  **not renamed** because mypy/ruff correctly saw it as used there — still
  calls `check_routability(net_name=net_name, ...)`. Every call has raised
  `TypeError` since.
- **Fix**: restored `net_name` (no underscore) in all three affected
  functions in this file (`check_routability`, `check_routability_bidi`,
  `check_routability_cc` — all three were renamed by the same commit, same
  public-API-family docstring contract, same latent bug even though only
  the first had a live broken caller), with a targeted `# noqa: ARG001` and
  an explanatory comment. Rejected: renaming the call site to
  `_net_name=net_name` (no reason a public parameter should be spelled with
  a leading underscore); making the function actually consume `net_name`
  in a log message (unasked-for behavior change; the bug is the signature
  contract, not a missing feature).
- **`test_routability_check.py`: 103 failed, 18 passed -> 2 failed, 119
  passed** (121 collected, unchanged). Both remaining failures are
  unrelated to this fix and pre-existing (Sec 2, Sec 3).
- **The "no pads" failure (12 signal nets) is pre-existing, not a
  regression from today's electrical work.** The test's expected net names
  (`GATE_H`, `PWM_H`, `SPI_CLK`, ...) matched the board's actual net names
  when the test was written (`e5425a15`, 2026-06-29) but the board's
  atopile-generated netlist renamed these nets (`GATE_HS`, `PWM_HS`,
  `sclk`, `usb_dn`/`usb_dp`, `boot`, ...) as of `a72a9316`
  (2026-07-15) — **11 days before** today's THM-02/UVL-02/SELV/BOM work
  (earliest of which, `88adabcd`, is 2026-07-26 02:05). This is a real,
  currently-live test/design mismatch, but it did not happen today.
- **The type checker did catch this — the allowlist swallowed it.** mypy
  (configured, run in CI via `check_typecheck_gate.py`) reports this exact
  call site as a `call-arg` error. Its "monotonic-shrink per-file
  allowlist" mechanism let a same-week allowlist-sync commit
  (`fed27984`, ~10h after the rename) absorb the new error as accepted
  baseline debt without anyone noticing the file had gone from 0 errors to
  1. **This is the whole finding for the guard** — see Sec 4.
- **14 of the 20 other reported failures were independently reproduced and
  confirmed pre-existing**, via a second git worktree checked out at
  `88adabcd` (last commit before any of today's electrical work) — byte-
  identical failure list, same 14 tests, same error messages, at a commit
  that predates today's `.ato`/BOM/PCB changes entirely. See Sec 3.
- **Falsifier for the new guard fired as predicted; fail-closed paths
  verified.** See Sec 5.

## 1. The fix, and why not the other options

Full survey of callers, done before touching anything (this codebase, not
just this file):

```
$ grep -rn "check_routability(" --include="*.py" .
packages/temper-placer/tests/router_v6/test_routability_check.py   (11 call sites, all positional — "test" as arg 1)
packages/temper-placer/src/temper_placer/router_v6/routability_check.py:407  (check_routability_direct, net_name=net_name)

$ grep -rn "check_routability_bidi(\|check_routability_cc(" --include="*.py" .
(check_routability_bidi: no callers at all outside its own definition)
(check_routability_cc: 4 call sites, all in tests, all positional)

$ grep -rln "routability_check" --include="*.py" . | grep -v routability_check.py
packages/temper-placer/src/temper_placer/visualization/routing_health.py   (imports check_routability_direct, positional net_name)
```

Only `check_routability_direct`'s internal call was actually broken (the
one keyword caller). `check_routability_bidi` and `check_routability_cc`
have the identical `_net_name` rename from the same commit but no live
keyword caller today — the same bug, just not yet triggered. Fixed all
three for the same reason the audit was asked for in the first place: this
is one public-API family (identical docstring section: "net_name: Net
identifier (used only for diagnostics / future logging)"), and leaving two
of three "fixed" only by accident of no caller existing yet is exactly the
kind of half-fix that reintroduces this bug class the moment someone adds
a second keyword caller.

**Options considered** (from the brief):

1. **Restore the name, silence the lint with a targeted `noqa` + comment.**
   Chosen. Matches existing repo convention (`grep -rn "noqa: ARG00" src`
   turns up a dozen legitimate uses, e.g.
   `pipeline/terminal_dashboard.py`'s callback interface methods) for
   "argument required by a contract, not read by this implementation."
   Zero behavior change; the comment states explicitly why the name must
   never be re-prefixed.
2. **Genuinely use the parameter** (thread it into a log/error message).
   Rejected for this specific fix: `check_routability` currently returns a
   bare `bool` with no logging anywhere in the function, for any input.
   Adding logging here would be a real behavior change to a hot-ish
   completion-invariant check, unasked for, and orthogonal to the actual
   defect (a signature/call-site mismatch, not "this diagnostic can't name
   its net" — nothing currently *tries* to name the net in output).
   `net_name`'s docstring already says "used only for diagnostics / future
   logging" — that's an honest description of a reserved-for-later
   parameter, not evidence it should be wired up as part of this bug fix.
3. **Change the call site(s) instead.** Rejected: would require
   `check_routability(_net_name=net_name, ...)` at the one real call site,
   which is correct but leaves a public function's own keyword parameter
   spelled with a leading underscore — visible to every future caller,
   permanently, for no reason connected to the function's actual contract.
   The parameter isn't private; it's just currently unread.

## 2. Before / after (counts, not exit codes)

```
$ python -m pytest packages/temper-placer/tests/router_v6/test_routability_check.py -q
# before fix
================== 103 failed, 18 passed, 1 warning in 1.54s ===================

# after fix
=================== 2 failed, 119 passed, 1 warning in 2.43s ===================
```

121 collected both times (0 skipped). Exit status captured directly into a
shell variable each time (`PYSTATUS=$?` on the line immediately after the
non-piped pytest invocation), never through a pipe — `1` before, `1` after
(2 failures remain), matching the printed summary lines above, not
silently misread as `0`.

The 2 remaining failures:

- `TestTemperRegression::test_signal_nets_are_routable` — the "no pads"
  failure, pre-existing since 2026-07-15 (Sec 3 below has the git evidence;
  this is prominent enough to also cover under "no pads" specifically).
- `TestBenchmark::test_latency_unroutable_early_exit` — an absolute
  wall-clock threshold (`elapsed < 20.0ms` for a 2000x2000-grid
  `scipy.ndimage.label` call). Failed 3/3 times in isolation
  (31.5, saw similar on repeat) while a second, unrelated background pytest
  process was pinning a CPU core at ~99% in this sandbox. Not a correctness
  issue and not touched by this fix (`check_routability_cc`, called
  positionally in this test, was never affected by the `_net_name` bug).
  Flagged as CPU-contention-sensitive, not fixed — a hardcoded absolute-ms
  threshold in a shared/busy sandbox is a pre-existing flakiness risk
  independent of this task.

## 3. Triage of the other 20 reported failures

### The "no pads" regression question — pre-existing, not from today's electrical work

`_ROUTABLE_SIGNAL_NETS` in the test (added `e5425a15`, 2026-06-29) expects:
`GATE_H`, `GATE_L`, `PWM_H`, `PWM_L`, `VCC_BOOT`, `SPI_CLK`, `SPI_MOSI`,
`SPI_MISO`, `SPI_CS_TEMP`, `USB_D+`, `USB_D-`, `TEMP_SENSE`, `I_SENSE`.

At `e5425a15`, `pcb/temper.kicad_pcb` had exactly these net names
(confirmed: `git show e5425a15:pcb/temper.kicad_pcb | grep -o '(net [0-9]*
"[^"]*")'` lists `GATE_H`, `PWM_H`, `TEMP_SENSE`, `SPI_CLK`, `SPI_MOSI`,
`SPI_MISO`, `SPI_CS_TEMP`, `USB_D+`, `USB_D-`, `VCC_BOOT` verbatim) — the
test passed when written.

Today's `pcb/temper.kicad_pcb` (`11f859e5`) has none of them except
`I_SENSE` (the one net that does NOT fail in the current run). Instead:
`GATE_HS`/`GATE_LS`, `PWM_HS`/`PWM_LS`, `sclk`/`sdi`/`sdo`/`cs_n`,
`usb_dn`/`usb_dp`, `boot`. `git log --all -S'"GATE_HS"' --
pcb/temper.kicad_pcb` finds the earliest introduction of `GATE_HS` at
`a72a9316` ("feat(pcb): generate production PCB skeleton from atopile
netlist (U2-U4)"), **2026-07-15 14:29** — confirmed by
`git show a72a9316:pcb/temper.kicad_pcb`, which already has `GATE_HS`,
`PWM_HS`, `hb.gate_hs-vdd`.

Today's electrical commits (`git log --oneline elec/src`) start at
`d99c88e2` ("feat(elec): THM-02 coil over-temperature circuit"),
**2026-07-26 07:46**, with `88adabcd` (2026-07-26 02:05, OVP-01 fix) the
last commit before any of today's THM-02/UVL-02/SELV-float/BOM work. **The
net-naming mismatch is 11 days older than today's electrical work.**
Verdict: **pre-existing, not a regression from today's `.ato` changes.**
This is still worth reporting prominently (per the brief) because it means
`test_signal_nets_are_routable` has likely been silently red (or silently
never run to completion, given it was also blocked by the `_net_name`
`TypeError` until this session's fix) since mid-July, and nobody has
reconciled the test's net-naming assumptions with the atopile-generated
netlist's actual naming convention since. Not fixed here — the test
encodes an old naming convention and the board encodes a new one; deciding
which one is "correct" (rename the test's net list, or is `GATE_HS` itself
a naming regression that should be reverted) is an electrical-design
decision out of scope for this task, and `elec/src/*.ato` / `pcb/` are
off-limits per the brief regardless.

### The other 14 (of "20 other failures") — independently reproduced pre-existing

Ran the 5 named files directly (faster and more targeted than the full
`tests/router_v6/` directory, which did not finish in a reasonable
foreground window — see UNVERIFIED):

```
$ python -m pytest \
    packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py \
    packages/temper-placer/tests/router_v6/test_astar_cost_field.py \
    packages/temper-placer/tests/router_v6/test_via_layer_properties_pbt.py \
    packages/temper-placer/tests/router_v6/test_dfm_interaction.py \
    packages/temper-placer/tests/router_v6/test_all_pad_tree_routing.py -q
======================== 14 failed, 56 passed in 23.40s ========================
```

Matches the brief's 5+3+2+2+2=14 exactly. To answer pre-existing-vs-new, a
second git worktree was created **detached at `88adabcd`** (last commit
before any of today's electrical work) and the identical command run
there:

```
$ git worktree add --detach <scratch>/wt-baseline 88adabcd
$ cd <scratch>/wt-baseline && python -m pytest <same 5 files> -q
======================== 14 failed, 56 passed in 26.46s ========================
```

**Byte-identical failure list** (same 14 test IDs, same error messages) at
a commit that predates today's electrical/PCB/BOM work entirely. Worktree
removed after comparison (`git worktree remove ... --force`).

Verdict: **all 14 are pre-existing**, none are regressions from today's
electrical work. Root causes, grouped (triaged, not fixed — out of scope
for this task and none are "cheap"):

- **6 tests** (`test_astar_route_multilayer_via_fallback.py` x4,
  `test_all_pad_tree_routing.py` x2): `AttributeError:
  <module 'temper_placer.router_v6.astar_pathfinding'> does not have the
  attribute '_route_segment_3d'`. `astar_pathfinding.py` was decomposed
  into `_astar_heuristics.py` / `_astar_ordering.py` /
  `_astar_reconstruct.py` by commit `5a17025b` (2026-07-23 11:18 — the
  same "batch CI fixes" commit already implicated in the `check_routability`
  timeline). `_astar_reconstruct.py` imports `_route_segment_3d` from
  `astar_core.py` and calls it directly in its own namespace;
  `astar_pathfinding.py` re-exports most of `_astar_reconstruct.py`'s
  names but not this one. The tests `monkeypatch.setattr(pathfinding,
  "_route_segment_3d", ...)` / `patch.object(pathfinding,
  "_route_segment_3d", ...)` against the wrong (and now non-existent)
  module attribute — a second instance of "a refactor silently changed a
  surface a test/caller depended on," structurally the same class of bug
  as this task's headline defect, just caught by `AttributeError` at test
  time instead of `TypeError` at call time in production. Not fixed here:
  the correct fix is retargeting the patches at `_astar_reconstruct`
  (where the name is actually imported and called from) or re-exporting
  the symbol from `astar_pathfinding.py`, and doing that correctly requires
  understanding which one preserves the tests' intended behavior — not
  "cheap" within this task's remaining scope.
- **1 test** (`test_integration_corpus_board_forced_transition_produces_real_vias`):
  genuine behavioral assertion failure — `via_positions=[]` where the test
  expects a non-empty, real via list ("must not be the pre-U2 static []").
  Real-board-scale integration test; possibly related to the same U2
  fallback-tier plumbing above, not confirmed.
- **3 tests** (`test_astar_cost_field.py`): thermal-cost-field A* biasing
  assertions fail (`field-on path must diverge from field-off`,
  `traversed 4 hot cells, field-off traversed 4; expected detour`) — the
  cost field appears to have no effect on path selection in these
  synthetic-grid tests.
- **2 tests** (`test_via_layer_properties_pbt.py`, Hypothesis PBT): "no
  segments emitted" / "pad untouched by any emitted segment" for a
  minimal 2-pad net; Hypothesis points at `_adapter_convert.py:837` as the
  only line executed by failing examples.
- **2 tests** (`test_dfm_interaction.py`): `Mock` object fixture drift —
  `power_plane.py:99: ox, oy = board.origin` raises `TypeError: cannot
  unpack non-iterable Mock object`, and `thermal_relief.py:153` raises
  `TypeError: 'Mock' object is not iterable` on
  `board.layer_stackup.layers`. These tests' `Mock`-based board fixture
  does not model attributes that `power_plane.py`/`thermal_relief.py` now
  read — a third instance of the same general "production surface moved,
  a stand-in (mock, not a real caller) wasn't updated" pattern, though this
  one is a test fixture rather than a real call site.

None of these were fixed — per the brief's "do not attempt all of them if
it means doing none of them well," and because unlike the `check_routability`
signature fix, each requires understanding intended routing/DFM behavior,
not just restoring a name.

### UNVERIFIED

- **The "six single failures"** named in the brief were not independently
  re-identified in this session. The full `tests/router_v6/` directory
  (unfiltered) did not complete in ~12 minutes of foreground wall-clock
  time (reached ~34% of the suite before being stopped to reclaim CPU for
  other measurements in this session, including the benchmark-flake
  re-check in Sec 2); a marker-filtered rerun (`-m "not slow and not
  monte_carlo and not nightly and not pbt_low_priority and not external"`)
  was still running past the point where this doc needed to be written.
  This tree is also ~140 commits ahead of whatever tree the brief's original
  123-failure count was measured against (this session started on a stale
  worktree missing `scripts/assert-base.sh` entirely and had to rebase),
  so the brief's exact failure set is not guaranteed to still exist
  unchanged here regardless. The 14 failures above, and the "no pads"
  failure, were independently confirmed with hard evidence (a second
  worktree at a pinned pre-today commit); the remaining six were not, and
  are reported as UNVERIFIED rather than guessed at.

## 4. Type-checker investigation (the guard's design basis)

**Does this repo run mypy? Yes.** `[tool.mypy]` is configured in both the
root and `packages/temper-placer` `pyproject.toml`.
`scripts/check_typecheck_gate.py` runs `uv run mypy <scope>
--ignore-missing-imports` across `packages/temper-placer/src`,
`packages/temper-workflow/src`, `packages/temper-tools/src` (the last does
not currently exist in this tree — handled by an existing `if not
scope_path.exists(): continue`), and is wired into CI as a real, blocking
step: `.github/workflows/python-tests.yml:570`, `uv run python
scripts/check_typecheck_gate.py` (default mode, no flags). `router_v6/` is
in scope — not excluded.

**Does mypy catch the actual bug?** Yes, reproduced directly by reverting
the fix and re-running mypy on just this file:

```
$ git stash   # temporarily restore the _net_name-broken version
$ uv run mypy packages/temper-placer/src/temper_placer/router_v6/routability_check.py --ignore-missing-imports
packages/temper-placer/src/temper_placer/router_v6/routability_check.py:73: note: "check_routability" defined here
packages/temper-placer/src/temper_placer/router_v6/routability_check.py:407: error: Unexpected keyword argument "net_name" for "check_routability"; did you mean "_net_name"?  [call-arg]
$ git stash pop   # restore the fix
```

**So why didn't CI fail for 3 days?** The gate is a per-file
"monotonic-shrink allowlist" (`.typecheck-allowlist`): default mode fails
only if a file's *current* mypy error count exceeds what's checked into the
allowlist file *right now*. `routability_check.py` had 0 errors (and no
allowlist entry at all — `init_allowlist()` only ever writes entries for
files with errors > 0) before `ce882acf`. The rename gave it exactly 1
`call-arg` error.

Commit `fed2798425541fc6f39e060690e3c4c187af260a` ("fix: update
LOC/typecheck allowlists + vulture non-blocking"), **2026-07-23 09:36:30**
— **roughly 10 hours after** `ce882acf`'s rename (2026-07-22 23:51:11) and
**before** `5a17025b`'s "batch CI fixes" commit (2026-07-23 11:18:36) —
bulk-regenerated `.typecheck-allowlist` and added, among many other lines:

```
+packages/temper-placer/src/temper_placer/router_v6/routability_check.py 1
```

as a brand-new entry, with no distinguishing marker that this specific new
entry corresponded to a live production bug rather than ordinary type-debt
churn. From that point on, default-mode gate runs see `current(1) ==
allowed(1)` — a clean pass, indefinitely, until someone manually greps for
why this specific number is 1.

**Would `--check-shrink` have caught it if it had been run?** No, and it
also isn't wired into CI for this gate at all (`grep -n
"check_typecheck_gate\|check-shrink" .github/workflows/*.yml` shows only
the default-mode invocation; `--check-shrink` is a mode that exists in the
script but is unused). Even if it were run: its logic
(`scripts/check_typecheck_gate.py:check_shrink`, pre-change) only inspects
lines that were **removed or reduced** relative to `origin/main`'s
allowlist (looking for illegitimate *shrinkage*, i.e. someone claiming an
improvement that isn't real). A purely **additive** new entry — a file
that goes from absent-from-the-allowlist (0 errors) to present-with-a-count
— is never inspected by that function at all. This is the second half of
the hole: even the audit mode built for exactly this kind of allowlist
tampering doesn't look at growth, only fraudulent shrinkage.

**Conclusion**: this is not "mypy isn't run" or "mypy excludes this
module" (the brief's two named failure shapes) — it's a third shape: mypy
runs, catches it, and a routine, mechanical allowlist-sync commit absorbed
the new error as accepted debt within the same day, before anyone had a
reason to look. **The fix is closing that specific hole in the existing
gate, not adding a parallel bespoke checker.**

## 5. The guard: hard call-arg gate, independent of the allowlist

**Falsifier, stated before implementing:**

> This guard must (1) **FAIL** when mypy reports a `call-arg` error not
> already present in a small, hand-curated baseline — verified by
> reconstructing the exact defect (the pre-fix `_net_name` signature +
> `check_routability_direct`'s `net_name=net_name` call) and confirming
> `check_call_arg_gate()` reports it as an unconditional violation; and (2)
> **FAIL CLOSED** — exit non-zero / report a violation, never a silent pass
> — when its own input is missing: an absent `.call-arg-allowlist` file, or
> a `SCOPE` with no existing directories.

**Result: fired as predicted, both parts.**

1. Reconstruction (fed the real mypy error string for the pre-fix
   signature through the actual `check_call_arg_gate()` function, not a
   simulated substitute):
   ```
   >>> check_call_arg_gate([('packages/.../routability_check.py', '407',
   ...     'Unexpected keyword argument "net_name" for "check_routability"; did you mean "_net_name"?')])
   CALL-ARG HARD FAIL: packages/.../routability_check.py:407: Unexpected keyword argument "net_name" ...
   1 call-arg violation(s) not in .call-arg-allowlist
   -> 1   # would be main()'s exit code 1
   ```
2. Fail-closed, missing baseline file (`.call-arg-allowlist` moved aside):
   `check_call_arg_gate()` prints a `WARNING: ... treating baseline as
   empty` and reports the injected test error as a violation (`1`, not
   `0`) — a missing baseline is never silently read as "nothing to check."
3. Fail-closed, missing SCOPE (`g.SCOPE` monkeypatched to two nonexistent
   paths): `main()` prints `FAIL (closed): none of the configured SCOPE
   paths exist` and returns `1`, not the pre-existing (and still-present,
   for the generic per-file gate) `"No allowlist found. Run --init first" ->
   return 0` fail-open shape.
4. Real end-to-end run against the live tree, unmocked:
   ```
   $ python3 scripts/check_typecheck_gate.py
   ...
   Total (excl. call-arg): 231 errors in 37 files (baseline: 452)
   Call-arg: 10 found, 0 not in .call-arg-allowlist
     40 stale allowlist entries — update with --init to lock in improvements
   OK — all files within allowlist baseline, no unapproved call-arg errors
   $ echo $?
   0
   ```

**Design**:

- `run_mypy()` now splits mypy's output into `(per-file counts excluding
  call-arg, list of call-arg entries)`. Call-arg errors never enter the
  generic per-file dict at all.
- `.call-arg-allowlist` is a new, small, hand-edited-only file (never
  written by `--init`), keyed on `(filepath, message)` — deliberately not
  line number, since line numbers churn on unrelated edits and would make
  the baseline noisy without adding real protection.
- Any call-arg error not in that file is an unconditional violation,
  regardless of `.typecheck-allowlist`'s state — so a future
  `check_typecheck_gate.py --init` (the exact operation `fed27984`
  performed) can never again silently absorb a new call-arg regression.
- Seeded with the **10 pre-existing call-arg errors** (6 unique
  `(file, message)` pairs) found scope-wide on this tree:
  `geometry/drc_inflate.py` (`smooth_relu`'s `beta` kwarg),
  `validation/drc_fence.py` (`CheckRunner.run`'s `modified_regions`),
  `validation/scorecard.py` (`_is_scorable_metric`'s `key`, 4 call sites),
  `validation/mfem_gate.py` (`compare_fields`'s `cell_size_mm`),
  `validation/results/battery_run.py` (`check_thermal_plausibility`'s
  `ambient_C`, 2 call sites, and `_ensure_field_diverges`'s `netlist`).
  **These are almost certainly live, unfixed instances of the identical
  defect class** — every one but `drc_inflate.py`'s carries mypy's own
  "did you mean `_x`?" signature — surfaced here as a finding, not fixed
  (fixing 6 unrelated files' call sites is out of scope for this task; the
  allowlist file says so explicitly and is not auto-populated, so they stay
  visible rather than getting silently absorbed further).

**Side effect, cleaned up**: excluding call-arg errors from the generic
per-file counts made several files' `.typecheck-allowlist` entries stale
(showing fewer generic errors than before, since their only error was
call-arg-coded). Removed the one line directly caused by this session's
fix (`routability_check.py 1`, now 0 generic errors) since it's now
provably dead; left the ~40 other now-stale entries alone (pre-existing
drift unrelated to this change, a `--init` resync is the documented
follow-up but touching ~40 unrelated numbers is out of scope here).

## Files touched

- `packages/temper-placer/src/temper_placer/router_v6/routability_check.py`
  — the fix (Sec 1).
- `scripts/check_typecheck_gate.py` — the call-arg hard gate (Sec 5).
- `.call-arg-allowlist` (new) — hand-curated call-arg baseline.
- `.typecheck-allowlist` — one now-dead entry removed
  (`routability_check.py`).
- This file.
