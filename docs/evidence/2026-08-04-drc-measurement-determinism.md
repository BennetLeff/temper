# Making the KiCad DRC measurement reproducible — 2026-08-04

<!-- provenance: commit=96fb58871c6d3951c70342784f9bcc07119bd7e1 dirty=true -->

**Base commit:** `96fb58871` (`origin/main`), branch
`fix/drc-measurement-determinism` in an isolated worktree. `dirty=true`
because this document is committed together with the fix it describes.

**Task.** `power_pcb_dataset/drc_ceiling.json` recorded three error categories
as nondeterministic on a byte-identical board over 120 samples — `clearance`
(377–378), `creepage` (185–187) and `shorting_items` (199–200) — each carrying
a `max + 1 headroom` ceiling. The file's stated goal is `error_ceiling: 0`; a
count cannot be ratcheted toward zero through an instrument that wobbles, and
every unit of headroom is slack a real regression can hide in. The job was to
make the *measurement* reproducible, not to reduce the error count.

**Platform for every number below:** macOS 15.5 (Darwin 25.5.0), arm64,
`kicad-cli 10.0.4`, board `pcb/temper.kicad_pcb` at sha256
`51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af` (the exact
content `drc_ceiling.json`'s provenance block records), `pcb/temper.kicad_dru`
regenerated from `scripts/generate_kicad_dru.py` before measuring, measured
through `temper_placer.validation._drc_api.run_drc` with `--all-track-errors`.
CI runs `kicad-cli 10.0.5` on Linux; **none of these numbers may be compared
across that boundary** — the creepage ceiling already encodes a documented
+1 version-band delta, and macOS/Linux diverge by roughly +107 errors in
total.

## 1. The zone-fill hypothesis is wrong — disproved, not assumed

The brief's leading hypothesis was that zone filling is itself
nondeterministic and that the copper geometry therefore differs run to run.
It is a reasonable hypothesis and it is **false for this measurement**, for a
reason that is checkable in one command:

```console
$ grep -c "filled_polygon" pcb/temper.kicad_pcb
0
$ grep -c "(zone " pcb/temper.kicad_pcb
96
```

The committed board has 96 zones and **zero** stored fill geometry, and
`run_drc` does not pass `--refill-zones` (KiCad 10's `pcb drc` only fills when
that flag is given). So the zones contribute no copper at all to the gate's
measurement, identically on every run. There is no fill step in the measured
path to be nondeterministic.

The note in `drc_ceiling.json`'s `2026-07-28-routed-rebaseline` entry that
"the gate fills zones first" is **stale**. It described an older code path;
today's `_drc_api.run_drc` does not fill, which is why it and a raw
`kicad-cli` call now agree rather than disagree for that reason.

Worth recording as a separate finding, because it is true and will mislead
someone later: KiCad's zone filler **is** nondeterministic. Filling the same
board six times with `--refill-zones --save-board` (on a sandboxed copy with
`.kicad_dru`/`.kicad_pro` co-located) produced six different results, with the
`filled_polygon` block count varying 94 / 96 / 97 / 99 / 100 / 101 and a
different geometry hash every time. That is a real hazard for any future
change that starts filling zones before DRC — it is simply not the cause of
*this* instability.

## 2. What the instability actually is

The instrument used throughout is `scripts/check_drc_determinism.py` (added by
this PR), which compares not just the per-category **count** but the **set** of
violations, with net *names* normalised away. Both refinements were necessary
to see the mechanism:

**Finding A — KiCad renames nets on load, arbitrarily.** The board declares

```
(via (at 101.705 47.13) (size 0.4) (drill 0.2) (layers "B.Cu" "F.Cu") (net 146) ...)
(net 146 "sclk")
```

yet across 8 samples kicad-cli reported that same via as `Via [sclk]` in 7 runs
and `Via [cs_n]` in 1. Nothing about the file changed. This board has ~199
`shorting_items` — places where copper from two declared nets touches — so
KiCad's connectivity pass merges them into one cluster and must pick a single
net for it. The cluster *membership* is stable; the *name* it resolves to is
an arbitrary choice among its members, and that choice moves run to run.
About 34–36 copper items flip between `sclk` and `cs_n` this way.

This is why the naive set comparison marks nearly every category unstable:
`annular_width`, `drill_out_of_range`, `via_diameter`, `hole_clearance` and
`W:track_dangling` all have perfectly stable counts and stable geometry, and
differ only in the net name printed next to the same physical item. It is
cosmetic for ceiling purposes — `sclk` and `cs_n` both resolve to the
`Default` netclass, so no netclass-scoped rule matches differently — but it is
loud, and it hid the real signal until it was normalised out.

**Finding B — the worker pool moves the counts.** kicad-cli runs the DRC
providers across a shared `BS::thread_pool` (visible in the shipped
`libkicommon.dylib` symbols; the process runs at ~227% CPU). Several providers
accumulate per-item state from whichever worker reaches an item first. Pinning
the pool to one thread, via KiCad's `MaximumThreads` advanced-config key,
collapses two of the three unstable categories to a single value.

**Finding C — creepage is an upstream defect we cannot reach.** See §4.

## 3. The fix

`run_drc` now points `KICAD_CONFIG_HOME` at a throwaway settings tree
containing `MaximumThreads=1`, for the lifetime of the subprocess only.

Why this shape:

* `MaximumThreads` is readable **only** from a `kicad_advanced` file inside
  KiCad's per-user settings tree. There is no flag and no environment
  variable for it.
* Writing that file into the developer's real KiCad configuration would make
  the measurement depend on who ran it and would persist after the run — the
  precise class of ambient-input bug that `ci_check_drc._regenerate_kicad_dru`
  already exists to close for `.kicad_dru`.
* The throwaway tree is **seeded with a copy of the real one's top-level
  files** (`fp-lib-table`, `sym-lib-table`, `kicad_common.json`, …) so library
  resolution is unchanged. Verified: with a completely empty config home the
  library-dependent warning categories are byte-identical anyway
  (`lib_footprint_issues` 11, `lib_footprint_mismatch` 23, and the same set
  digests), so the copy is belt-and-braces rather than load-bearing on this
  host — but it is what keeps the change safe on a CI image whose global
  tables differ.
* If the kicad-cli version can't be read, the pin is skipped and the run
  proceeds **unpinned** rather than failing. A measurable-but-unpinned number
  beats no number; the harness reports which mode it got.
* `TEMPER_DRC_THREAD_PIN=0` disables the pin, which is how the "before"
  column below is produced on demand.

Cost: none worth measuring. Wall time is ~4.8 s per run either way — the DRC
is not thread-bound on this board (43 s user / 227% CPU unpinned vs 33 s user
/ 93% CPU pinned, for the same 8 runs in ~38 s wall both times).

## 4. Creepage: unfixable at our layer, with the reason

Pinning the thread pool does **not** stabilise `creepage`. Over 120 pinned
samples it measured 185×27 / 186×58 / 187×35, with **120 distinct violation
sets in 120 samples** — no two runs agreed. The churn survives net-name
blinding *and* distance blinding, so it is genuinely different pairs being
reported, not the same pairs measured differently: in one 8-sample slice, 82
of 228 reported pairs came and went.

The cause is inside KiCad. Its creepage provider deduplicates reported pairs
through

```cpp
std::set<std::pair<const BOARD_ITEM*, const BOARD_ITEM*>> m_reportedPairs;
```

— a container keyed and ordered by **raw pointer value**. Which of a pair
sorts first, and therefore whether a given pair is recognised as
already-reported, follows the two `BOARD_ITEM`s' addresses in that process.
Those are not reproducible across processes, so the dedup outcome is redrawn
on every run. That is a complete explanation for "a handful of pairs appear or
disappear each run at a roughly constant total", which is exactly the observed
signature — and it explains why the thread pin does nothing for it: the pin
fixes *ordering between workers*, and this defect does not need two workers.

This is a known upstream bug: KiCad issue
[#20048](https://gitlab.com/kicad/code/kicad/-/issues/20048), "Creepage DRC
violations disappear on repeated runs", reported against 9.0.0 on macOS arm64
and still reproducing on 10.0.4.

**No invocation of kicad-cli fixes it.** There is no flag, no severity switch
and no thread setting that changes pointer-ordered dedup, and it cannot be
post-processed into a canonical form either: post-processing can only
canonicalise what was reported, and the defect is that *different violations
get reported*. Deduplicating our side would still leave the union varying,
because a pair suppressed upstream never reaches us at all.

The three options we did **not** take, and why: widening the ceiling, taking a
median across samples, and discarding outlier samples all produce a smooth
number rather than a reproducible one, and all of them hide a real regression
of the same magnitude as the noise.

The honest options that remain, for the owner to choose:

1. **Leave `creepage` on its measured-max + 1 ceiling and label it as
   upstream-nondeterministic** — the status quo, now with a named cause and an
   upstream issue to track rather than an unexplained wobble.
2. **Move `creepage` to the Rust backend.** `packages/temper-drc-rs/src/rules/safety/creepage.rs`
   already implements a creepage rule, and `drc_ceiling.json` already has a
   per-category `category_source` field precisely so that different categories
   can be attributed to different engines. A deterministic engine we control
   is the only route to a ratchetable creepage number. This is a real piece of
   work (the two engines' definitions must first be shown to agree) and is out
   of scope here, but it is the structural answer.

Option 2 is the recommendation. It is not done in this PR.

## 5. Results — 120 samples before, 120 samples after

Two runs of 120 samples each, same host, same board, same `.kicad_dru`, back
to back. "Before" is produced by `TEMPER_DRC_THREAD_PIN=0` (the fix disabled),
so the only difference between the two columns is the pin.

| category | before (unpinned) | after (pinned) |
|---|---|---|
| `clearance` | **377**×20, **378**×100 | **378**×120 |
| `shorting_items` | **199**×100, **200**×20 | **199**×120 |
| `creepage` | **185**×16, **186**×48, **187**×56 | **185**×27, **186**×58, **187**×35 |
| `annular_width` | 4 | 4 |
| `copper_edge_clearance` | 12 | 12 |
| `courtyards_overlap` | 11 | 11 |
| `drill_out_of_range` | 4 | 4 |
| `hole_clearance` | 105 | 105 |
| `hole_to_hole` | 3 | 3 |
| `solder_mask_bridge` | 154 | 154 |
| `track_width` | 199 | 199 |
| `tracks_crossing` | 3 | 3 |
| `via_diameter` | 4 | 4 |
| *all 9 warning categories* | stable (472 total) | stable (472 total) |

**Count-unstable categories: 3 → 1.** The only remaining one is `creepage`.

The "before" column reproduces `drc_ceiling.json`'s recorded observations
exactly — `clearance` 377–378, `creepage` 185–187, `shorting_items` 199–200 —
which is independent confirmation that this harness is measuring the same
thing the ceiling file was measured with, on the same protocol.

### The mechanism, visible in the joint distribution

`clearance` and `shorting_items` are not two separate problems. Their joint
distribution over the 120 unpinned samples is:

```
(clearance, shorting_items) = (378, 199) ×100
(clearance, shorting_items) = (377, 200) ×20
```

Perfectly correlated, and the two categories' set-digest histograms are
identical (42 / 39 / 20 / 18 / 1 in both). One copper pair is classified as
*either* a `clearance` violation *or* a `shorting_items` violation depending on
which worker reaches it first — a single race, showing up as ±1 in two
different rows of the ceiling. Pinning the pool resolves it to the same side
every time.

## 6. Residual: clearance/shorting_items set-churn at a constant count

Pinning makes both counts single-valued, but the **sets** still take one of
two states, in an 80/40 split across the 120 pinned samples (and again
perfectly correlated between the two categories — one event, not two). One
observed instance, at a constant total of 378:

```
state A: Clearance violation (... actual 0.0000 mm) | Track [] on F.Cu, length 9.2000 mm | Via [] on F.Cu - B.Cu
state B: Clearance violation (... actual 0.0000 mm) | Pad 1 [] of C9 on F.Cu             | Track [] on F.Cu, length 2.1213 mm
```

Both are zero-distance (overlapping) items, and the copper-clearance provider
caches checked pairs in a pointer-keyed container of its own — the same class
of upstream defect as §4, at much lower amplitude and, here, with no effect on
any count.

**The ceiling gate does not see this**, because the ceiling gate counts. It is
recorded so that a future "clearance is deterministic now" claim is made
against the set and not the total, and `check_drc_determinism.py` prints both
columns for exactly that reason. It is also why this document does not claim
the measurement is *deterministic* — it claims two of three unstable counts
are now reproducible, which is what was measured.

## 7. Anti-vacuity

A determinism harness that always reports "deterministic" is worthless, and
that failure mode has appeared repeatedly in this repository. Three
independent demonstrations that this one can fail:

1. **`--inject-variance=unpin`** removes the real fix (sets
   `TEMPER_DRC_THREAD_PIN=0`) and re-measures. This is not a thought
   experiment — it is exactly how §5's "before" column was produced, at the
   same 120 samples, on the same host, minutes apart from the "after" column.
   The same analysis code that reports `count-unstable: ['creepage']` for the
   pinned run reports `count-unstable: ['clearance', 'creepage',
   'shorting_items']` for the unpinned one. Same code, same board, opposite
   verdict, in both directions.
2. **`--inject-variance=synthetic`** drops one violation on every other
   sample. The harness must report NOT REPRODUCIBLE; `scripts/tests/test_check_drc_determinism.py::test_synthetic_injection_makes_a_stable_measurement_unstable`
   asserts both directions of that.
3. **The harness caught something the count-only view cannot** — §6's
   constant-count set churn — which is the strongest available evidence that
   its set comparison is doing real work rather than rubber-stamping.

The unit tests additionally pin the two normalisation boundaries, both of
which were bugs during development: nets must be blinded **before** items are
sorted (otherwise a rename reorders a pair and reads as a different
violation), and the measured distance must **not** be blinded (otherwise a
genuinely different result reads as identical).

`test_run_drc_passes_the_pinned_env_to_kicad_cli` covers the corresponding
vacuity risk on the fix itself: every helper can be correct while `run_drc`
silently forgets to hand the environment to the subprocess, and the symptom
would just be "the numbers went back to wobbling", historically written off as
CI flake.

## 8. What `drc_ceiling.json` would need — not applied here

`power_pcb_dataset/drc_ceiling.json` is **not edited by this PR.** The values
below are what the post-fix measurement supports, for the owner to decide on.
Every one of them is a **decrease**, so none needs a `Ceiling-Approval:`
trailer under the file's own rule — but none of them is applied here either,
because a ratchet should be moved deliberately and by its owner.

| field | current | measured after fix | why |
|---|---|---|---|
| `violations_by_type.clearance` | 379 | **378** | single-valued over 120 samples; the `+1 headroom` for run-to-run noise is no longer buying anything |
| `violations_by_type.shorting_items` | 201 | **199** | same |
| `violations_by_type.creepage` | 188 | **188** (unchanged) | still nondeterministic, 185–187 locally; the ceiling's `+1 CI 10.0.5 version-band` reasoning is untouched |
| `error_ceiling` | 1267 | **1264** | `1267 − 1 (clearance) − 2 (shorting_items)` |
| `warning_ceiling` / `warnings_by_type` | — | unchanged | every warning category was already stable, before and after |

`nondeterministic_error_types` would drop its `clearance` and `shorting_items`
blocks and keep only `creepage`, with the note updated to name the upstream
cause (§4) rather than describing it as unexplained.

**Do not apply these numbers without re-measuring on CI.** They are
macOS/10.0.4 figures. Pinning the pool does not only make the value stable, it
selects *which* value you get — unpinned `clearance` was 377 or 378 and pinned
is 378 — and there is no guarantee CI's Linux/10.0.5 image lands on the same
side of that split. The first pinned CI run on this branch is the measurement
that should drive the edit.

## 9. What this does NOT change

* **`pcb/temper.kicad_pcb` is untouched.** No board change was made or
  attempted; the error count is not the subject of this work.
* **The `rust` DRC backend is untouched.** This is a kicad-cli-path fix.
* `placer/cp_sat/gates.py` makes its own raw `kicad-cli pcb drc` calls
  (`gates.py:174`, `gates.py:270`) which do **not** go through `run_drc` and
  are therefore still unpinned. They gate placement decisions rather than the
  ceiling, so they are out of scope here, but they inherit the same
  nondeterminism and should be routed through `run_drc` eventually.

## 10. Not verified

* **`scripts/check_drc_determinism.py` was never run end-to-end in this
  worktree.** The shared venv's `temper_design_bundle_python` extension is
  older than the checked-out Python expects (`AttributeError: module
  'temper_design_bundle_python' has no attribute 'ViaTemplate'`), so
  `import temper_placer` fails here and rebuilding it was ruled out under the
  session's disk constraint. Every measurement above was taken by loading the
  patched `_drc_api.py` and the harness's own analysis functions **by file
  path** and driving them directly — the same code, minus the package
  `__init__`. The script's argument parsing, DRU regeneration and
  `--inject-variance=synthetic` wiring are therefore covered by unit tests
  only. First real end-to-end run should be on CI or a synced checkout.
* **Everything here is macOS/10.0.4.** The fix is expected to help identically
  on CI's Linux/10.0.5 image — the mechanism is KiCad-internal, not
  platform-specific — but that is an expectation, not a measurement. The
  first CI run on this branch is the first evidence.
* **Whether CI's absolute values move.** Pinning the pool changes *which*
  value you get, not just how stable it is: unpinned `clearance` was
  377 or 378 and pinned is 378. If CI's pinned value differs from the
  ceiling's recorded figure, that is this change surfacing a value rather
  than a regression — §5 gives the local numbers to compare against.
* **That `MaximumThreads=1` is the minimal pin.** 2 or 4 threads were not
  tried; 1 was chosen because it is the only value that makes the ordering
  argument airtight and it costs nothing measurable.
