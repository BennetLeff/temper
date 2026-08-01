<!-- provenance: commit=57f0c7550a312bafd69d14f7ae8c0ace16fa12eb dirty=false -->

# C27 board-vs-netlist "defect": already fixed upstream; the freshness-check gap that let it look real, closed

Base branch: `fix/rotation-convention-standalone` (PR #479 lineage), which
descends from both `bd352015` (#445, "wire check_copper_net_consistency
into CI") and `8bf18b41` (#459, "resync board designators/footprints
against elec/src and pcb/libs") -- confirmed via `git merge-base
--is-ancestor`. Worked in an isolated worktree
(`wt-c27-netfix`, own `.venv` via `make venv-isolate`), never touching
`/Users/bennet/Desktop/temper` directly. All commands below were run with
`uv run --no-sync` against a `make netlist` freshly built in this worktree
(digest `1b1d641f6647…`, sha256 `5a5e17231899…` -- full value in Section 6).

## Summary (read this first)

**The C27 board-vs-netlist mismatch described in this task's brief does not
exist on the current board.** It existed once, was found and characterized
in detail on 2026-07-30 (`docs/evidence/2026-07-30-copper-net-consistency-drift.md`,
branched from `66ae51fc`), and was fixed by PR #459 the same day, which
resynced the board's designators against the post-`3ae26dfe` netlist
(the commit that added `tank.c_tank3` and shifted 13 subsequent `C`
designators by one). Both #445 (CI wiring for the gate that found it) and
#459 (the actual board fix) are ancestors of this task's base branch.

Measured directly, on the current board, against a netlist rebuilt from
current `elec/src` in this worktree:

- **`C27`'s board pad-net annotations are CORRECT**, not stale: pad 1 =
  `SW_NODE`, pad 2 = `tank.c_tank1-p2`. The freshly compiled netlist agrees
  exactly (`C27` = `tank.c_tank3`, the third resonant-tank capacitor, HV).
  `C27` is genuinely HV, on both sides, with no disagreement.
- **`scripts/check_copper_net_consistency.py` reports 0 violations**
  across all 512 exactly-matchable pads (521 total, 9 legitimately skipped
  -- see Section 2).
- The board-vs-netlist mismatch this task's brief describes (board says
  SELV `I_SENSE`/`gnd`, netlist says HV `SW_NODE`/`tank.c_tank1-p2`) is
  reproduced **only** by comparing the (correct, current, git-tracked)
  board file against the **stale** `elec/build/default.net` sitting in the
  shared `/Users/bennet/Desktop/temper` checkout -- a gitignored build
  artifact last rebuilt before `elec/src/modules.ato`, `components.ato`,
  and `main.ato` were last modified (confirmed: `find elec/src -newer
  elec/build/default.net` lists all three). That stale netlist predates
  even `3ae26dfe` (it has no `tank.c_tank3` entry at all, and prices the
  tank caps at the pre-resource WIMA MPN, not CDE's `942C16P1K-F`) -- it is
  not merely a few hours old, it is stale by weeks of design history.
  Comparing today's (correct) board against that artifact reproduces
  exactly the reported symptom by coincidence of designator arithmetic,
  not because of any live defect.
- **Real, closeable gap found and fixed**: `check_copper_net_consistency.py`'s
  own freshness guard used a hand-rolled, mtime-only staleness check,
  unlike its sibling `check_domain_partition.py`, which migrated to the
  shared content-hash stamp (`scripts/_lib/freshness.py`) specifically
  because mtime comparison is known to give **false verdicts in both
  directions** under checkout/cache-restore (documented 2026-07-28 CI
  incident, `scripts/_lib/freshness.py`'s own module docstring). This is
  fixed in this change: `check_copper_net_consistency.py` now shares the
  exact same `check_freshness()` call `check_domain_partition.py` uses.
  This does not change today's verdict (mtime already happened to catch
  the shared checkout's staleness correctly) -- it removes the
  possibility that it *wouldn't*, the exact failure class this task asked
  to be closed.
- **REQ-SAFE-01** on the current, correct board+netlist reports **123
  violations across 86 pairs** (159 components matched, 6 unclassified
  components within the largest IEC margin) -- not the 102/10-C27 figure
  in the task brief. **Zero of the 123 violations involve C27.** Section 5
  accounts for the delta.
- **F1**: the footprint/holder mismatch is real and already fully
  documented (`docs/hardware/BOM.md` line 74, dated 2026-07-26) --
  reported, not re-discovered or fixed here. Section 7.

No line of `pcb/temper.kicad_pcb` or `elec/src/**` was touched. The only
changes are to `scripts/check_copper_net_consistency.py` (freshness-check
hardening), its test file (6 new regression tests), `scripts/manifest.yaml`
(import list), and this document.

## 1. C27: board vs. a genuinely fresh netlist

```
$ make netlist                       # this worktree, fresh build
...
INFO     Build complete!
[write-build-stamp] elec/build/default.net: 8 input(s), digest 1b1d641f6647…

$ uv run --no-sync python3 -c "
import sys; sys.path.insert(0,'scripts')
from check_copper_net_consistency import parse_netlist
from pathlib import Path
nl = parse_netlist(Path('elec/build/default.net'))
for pin in ['1','2']:
    code = nl.pin_net.get(('C27', pin))
    print('C27 pin', pin, '-> code', code, 'name', nl.nets.get(code))
"
C27 pin 1 -> code 44 name SW_NODE
C27 pin 2 -> code 59 name tank.c_tank1-p2
```

```
$ grep -n '"C27"' pcb/temper.kicad_pcb
1304:    (property "Reference" "C27")
$ sed -n '1299,1329p' pcb/temper.kicad_pcb   # Sheetpath "tank.c_tank3"
    (property "Reference" "C27")
    (property "Sheetpath" "tank.c_tank3")
    ...
    (pad "1" ... (net 22 "SW_NODE"))
    (pad "2" ... (net 151 "tank.c_tank1-p2"))
```

Board and fresh netlist agree exactly, on both pads. `C27` is the third
resonant-tank film capacitor (`tank.c_tank3`), genuinely HV, correctly
labeled on both sides. `pcb/temper.kicad_pcb` in this worktree is
byte-identical to `origin/main`'s copy (`diff <(git show HEAD:pcb/temper.kicad_pcb)
<(git show origin/main:pcb/temper.kicad_pcb)` -- empty), so this is not an
artifact of this worktree's own state; it is the current, canonical board.

### Why the task brief's numbers reproduce anyway

```
$ find elec/src -name '*.ato' -newer elec/build/default.net   # in the
                                                                # SHARED checkout
elec/src/modules.ato
elec/src/components.ato
elec/src/main.ato

$ uv run --no-sync python scripts/check_copper_net_consistency.py \
    --board /Users/bennet/Desktop/temper/pcb/temper.kicad_pcb \
    --netlist /Users/bennet/Desktop/temper/elec/build/default.net \
    --src-dir /Users/bennet/Desktop/temper/elec/src
=== COPPER-NET CONSISTENCY GATE ERROR ===
Reason: netlist is STALE: .../elec/src/modules.ato was modified after
.../elec/build/default.net was built. Run `make netlist` to rebuild before
running this gate (3 source file(s) newer than the compiled netlist).
GATE RESULT: ERROR -- not PASSED, not a violation.
```

The gate's own freshness guard **correctly refuses to give a verdict**
against that stale artifact -- it does not silently pass, and it does not
silently produce a false violation report either. The false "C27 is
mislabeled" read only happens if the comparison is done by hand (parsing
board vs. that stale `.net` file directly, bypassing the gate and its
freshness check entirely) rather than by running
`scripts/check_copper_net_consistency.py`, which is exactly what happened
in this task's own briefing and, on the very first pass of this task's own
investigation, in this worktree too (both corrected once the actual gate
was run against a freshly built netlist).

That shared checkout's `elec/build/default.net` is not merely a few hours
stale -- it lacks a `tank.c_tank3` entry entirely and prices the tank caps
at the pre-`3ae26dfe` WIMA MPN, meaning it predates the commit that
originally caused this defect class, and post-dates nothing that fixed it
either. It is simply a build artifact nobody has rebuilt in that checkout
in a long time; `elec/build/` is gitignored by design (`.gitignore:7`), so
nothing enforces its freshness except actually running `make netlist` or a
freshness-checked gate before trusting it.

## 2. Priority 2 -- full sweep: every board pad vs. the fresh netlist

```
$ uv run --no-sync python scripts/check_copper_net_consistency.py
Board: pcb/temper.kicad_pcb
Netlist: elec/build/default.net
Copper: 2482 item(s) total (Segment=2338, Via=48, Zone=96), 2482 checked
(net != 0), 0 skipped (net == 0, no-net).
Pads: 512 checked (exact ref+pin match in netlist), 9 skipped (no exact
match -- resync's positional-fallback candidates, not independently
verified by this gate).

PASSED -- 0 violations across 2482 copper item(s) and 512 pad(s) checked.
```

**Denominator, spelled out**: 521 total pads across 169 footprints; 512
checked by exact `(Reference, pad number)` identity against the compiled
netlist, 0 disagreements; 9 skipped because their pad numbers don't match
the netlist's numeric pin convention. The 9 are enumerated, not merely
counted, so "0 violations" cannot be mistaken for "nothing was compared":

```
K1 pad A1  -> board net 'power_in.bypass_relay-coil1'   (relay coil, EN50005 pin naming)
K1 pad A2  -> board net 'power_in.bypass_relay-coil2'
K1 pad 13  -> board net 'power_in.ntc-no'                (Faston contact tab)
K1 pad 14  -> board net 'w1_2'
K1 pad ''  -> board net ''  (x4, np_thru_hole -- mechanical mounting holes,
                              footprint's own descr: "NPTH (mechanical
                              only, no net)")
U3 pad 3   -> board net ''  (DIP-6 H11L1 optocoupler; netlist has no C27-
                              style entry for U3 pin 3 either -- pins
                              1,2,4,5,6 are wired, pin 3 is genuinely NC on
                              this part)
```

Every one of the 9 is accounted for: 4 are non-electrical mechanical
mounting holes by the footprint's own design documentation, 4 are K1's
relay pins whose EN50005 lettered/numbered pad scheme doesn't line up with
the netlist's numeric pin convention (this is the gate's documented,
deliberate limitation -- it does not duplicate resync's positional-match
heuristic, per the module docstring), and 1 (U3 pin 3) is a genuinely
unconnected package pin. None is a hidden violation.

**Conclusion: zero components on the current board have any board-vs-netlist
pad annotation drift.** There is no "whole class" to enumerate beyond C27
because C27 itself is not, currently, an instance of it.

## 3. Priority 1 -- the real gap, precisely, and its fix

`check_copper_net_consistency.py`'s pad-comparison logic (`run_checks`,
Check 3 in its own docstring) is sound: it compares the board's actual
per-pin net **name**, not merely the reference designator or the net
ordinal, against the compiled netlist's declaration for the exact same
`(ref, pin)` -- this is precisely the check that would catch (and, per
`docs/evidence/2026-07-30-copper-net-consistency-drift.md`, DID catch, with
a real board defect on 2026-07-30) a designator-drift class of error. There
is no gap in what it compares or how it compares it.

The actual gap was in what stands **in front of** that comparison:
`check_netlist_freshness()` used its own hand-rolled mtime-only staleness
check, while its sibling gate `check_domain_partition.py` migrated to
`scripts/_lib/freshness.py`'s content-hash stamp mechanism specifically
because mtime comparison gives **false verdicts in both directions**:

- False STALE: `git checkout`/worktree creation stamps every source file
  with the checkout time, so a perfectly fresh, cache-restored netlist
  always looks older than sources it actually matches (measured
  2026-07-28 on `check_domain_partition.py`: CI run 30383701486 rebuilt
  and passed; run 30384514627 restored an unchanged netlist from cache
  and errored STALE -- same sources, same netlist content, different
  verdict).
- False FRESH (the dangerous direction for THIS gate specifically, whose
  entire purpose is trusting the netlist's content): a netlist whose mtime
  happens to be newer than every source file, purely by file-timestamp
  happenstance (e.g. touched, copied, or restored after the sources were
  last written, without ever actually being rebuilt from them) passes the
  old check with no content comparison at all.

`check_copper_net_consistency.py` had NOT been migrated to the shared,
already-fixed mechanism -- its own docstring even claimed "identical
contract to check_domain_partition.py's own freshness guard," which had
been true when written but had silently gone stale itself once
`check_domain_partition.py` was hardened and this gate was not.

**Fix applied** (`scripts/check_copper_net_consistency.py`,
`check_netlist_freshness`): now calls `scripts/_lib.freshness.check_freshness()`,
the exact function `check_domain_partition.py` uses -- same contract, one
shared implementation instead of two independently hand-rolled (and now
independently provably-in-sync) copies. `make netlist`'s existing
`write_build_stamp.py` step (already run for every local/CI build, see
`Makefile`'s `netlist` target) means this gate now gets the stronger
content-hash check for free in the normal build path, with the same
mtime-only fallback (unchanged behavior) for any netlist built by an older
path with no stamp.

This does not change today's verdict against the real board -- mtime
happened to correctly flag the shared checkout's netlist as stale, by
luck of that checkout's actual history -- but it removes the possibility
that it wouldn't, on the next cache-restore or copied-artifact scenario,
which is precisely "closing the gap so this class cannot recur silently."

### Regression coverage added

`scripts/tests/test_check_copper_net_consistency.py` gained a
`TestNetlistFreshness` class, 6 tests, mirroring
`check_domain_partition.py`'s own `TestNetlistFreshness` 1:1 (fresh netlist
passes; stale-by-mtime fails closed; missing netlist is a gate error; a
stamped netlist survives newer-but-unchanged sources -- the exact
2026-07-28 cache-restore case; a stamped netlist still catches a real edit;
a stamped netlist still catches a back-dated edit that would fool mtime
alone):

```
$ uv run --no-sync pytest scripts/tests/test_check_copper_net_consistency.py -v --tb=short
...
scripts/tests/test_check_copper_net_consistency.py::test_pad_mismatch_detects_designator_drift PASSED
scripts/tests/test_check_copper_net_consistency.py::test_matching_board_and_netlist_pass_clean PASSED
scripts/tests/test_check_copper_net_consistency.py::test_dangling_ordinal_detected PASSED
scripts/tests/test_check_copper_net_consistency.py::test_orphaned_net_detected PASSED
scripts/tests/test_check_copper_net_consistency.py::test_zone_name_mismatch_detected PASSED
scripts/tests/test_check_copper_net_consistency.py::test_no_net_copper_is_skipped_not_checked PASSED
scripts/tests/test_check_copper_net_consistency.py::test_pad_without_exact_netlist_match_is_skipped_not_flagged PASSED
scripts/tests/test_check_copper_net_consistency.py::test_parse_netlist_rejects_empty_file PASSED
scripts/tests/test_check_copper_net_consistency.py::test_parse_netlist_rejects_missing_file PASSED
scripts/tests/test_check_copper_net_consistency.py::test_load_board_rejects_zero_footprints PASSED
scripts/tests/test_check_copper_net_consistency.py::test_gate_is_wired_into_ci_workflow PASSED
scripts/tests/test_check_copper_net_consistency.py::test_load_board_rejects_zero_copper PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_fresh_netlist_passes PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_stale_netlist_fails_closed PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_missing_netlist_is_gate_error PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_stamped_netlist_survives_newer_sources PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_stamped_netlist_still_fails_on_real_edit PASSED
scripts/tests/test_check_copper_net_consistency.py::TestNetlistFreshness::test_stamped_netlist_catches_backdated_edit PASSED
============================== 18 passed in 0.26s ==============================
```

12 pre-existing tests unchanged and still passing; 6 new.

## 4. Priority 3 -- no board fix needed, and why hand-editing would have been wrong

The premise ("the board's C27 annotations are stale and must be
resynced/hand-corrected") does not hold against the current board: it was
already resynced by PR #459 (`8bf18b41`, "resync board designators/
footprints against elec/src and pcb/libs"), an ancestor of this task's base
branch. That PR's own commit message documents exactly this fix: "13
sheetpaths (ct_sense.c_filter..mcu.c_en) resynced from C27..C39 to
C28..C40" and "`scripts/check_copper_net_consistency.py`: 10 -> 0
violations" -- the same 10-violation defect
`docs/evidence/2026-07-30-copper-net-consistency-drift.md` found and left
unfixed (by design, board was read-only for that task) one PR earlier.
Hand-editing C27's net fields now, on an already-correct board, would have
been the actual defect: it would have overwritten a correct HV annotation
with a fabricated SELV one, based on a stale local artifact rather than the
design's own source of truth.

**Mechanism note for any future recurrence of this class**: were a real
drift to reappear (e.g. another `elec/src` insertion shifting designators
without a board resync), `scripts/resync_pcb_netlist.py` is the existing,
documented, designed-for-purpose mechanism -- it matches by `Sheetpath`
identity (stable across renumbering), not by reference designator, and
correctly relabels drifted designators while staging any genuinely new,
unplaced component. This was confirmed by reading the tool
(`old_by_sheetpath.get(comp.sheetpath)`, never by designator) and by its
proven use in #459, not re-derived or re-run here since there is nothing
for it to fix on the current board.

## 5. REQ-SAFE-01: 123 violations now, not 102; zero involve C27

```
$ uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py \
    -k test_temper_board_clearance_compliance -v -s
...
DOMAIN CLASSIFICATION COVERAGE: 159 of 169 components classified (94.1%),
54 of 162 compiled nets classified (boundary set ASSERTED by the hard
check below: 159 components / 54 nets).
FULL-COVERAGE CROSS-CHECK: 123 REQ-SAFE-01 violation(s) over the full
54-net manifest declaration (159 components).
...
E   123 REQ-SAFE-01 clearance/creepage violations on the real board across
86 pair(s) (11 of the records are intra-footprint, i.e. unfixable by moving
anything). Components matched: 159.
```

`C27` does not appear anywhere in the 123-violation output (`grep -c C27`
on the full pytest output: 0 matches). This is expected and consistent
with Section 1: `C27` is correctly HV on both board and netlist, so it
participates in this board's real, pre-existing HV/SELV clearance
shortfalls exactly like any other correctly-classified HV component would
-- and, measured directly, it currently does not appear in any of the 86
violating pairs.

### Accounting for 102 -> 123

The task brief's cited 102-violation/10-C27 baseline traces to
`docs/evidence/2026-07-29-rotation-convention-sign-fix-cpsat-rerun.md`
(provenance commit `21b4c96345d415d13685c2d6057c11124d0f1e45`). That commit
is **not** an ancestor of this task's `HEAD` (`git merge-base
--is-ancestor` returns false) -- it is the same logical rotation-sign fix,
authored in a separate worktree/session, with different commit objects.
Diffing the two histories' `pcb/temper.kicad_pcb` directly shows the net
tables differ starting at line 121 (different net numbering/ordering),
while `elec/src/modules.ato` is byte-identical between them. This
worktree's board file, by contrast, is verified byte-identical to
`origin/main`'s current copy (Section 1). The most defensible reading:
that baseline's board came from a different resync/build lineage than the
canonical one this task measured against, which is sufficient on its own
to shift which cross-domain pairs clear or miss the 12.6mm/6.0mm/3.0mm
margins -- REQ-SAFE-01's distances are sensitive to exact copper geometry,
and a different net-table/resync state is a different geometry-adjacent
input even when component positions themselves are unchanged. **What is
not in question**: `C27` is uninvolved in either measurement's underlying
electrical classification once the board is correctly resynced (per
Section 1), so the "10 involve C27" figure specifically does not survive
against the current, canonical board regardless of which worktree it was
originally measured in.

This delta is reported, not chased -- re-placing the board to clear any of
the 123 violations is out of scope (board re-floorplanning is explicitly
excluded from this task).

## 6. Netlist sha256, before/after

```
$ sha256sum elec/build/default.net
5a5e172318993f967779477c6a6bcfd049a1b714012d048c764efc9d27921ceb  elec/build/default.net
```

Computed once, immediately after this worktree's single `make netlist`
run, and unchanged for the remainder of this task -- no further netlist
rebuild, and no code change in this task touches `elec/build/` or
`elec/src/**`. Before == after by construction; the value above is both.

## 7. `check_pad_orientation.py` / `check_domain_partition.py` re-run

```
$ uv run --no-sync python scripts/check_pad_orientation.py
checked 169 footprints, 521 pads, 1683 different-net pad pairs
PASS: no unrotated pad bodies, no intra-footprint copper overlaps

$ uv run --no-sync python scripts/check_domain_partition.py
Checked 54 declared nets across 2 domains (HV, SELV), 10 declared
isolators, 2 declared protective-impedance chain(s) (6 chain member(s)
total), over 162 compiled nets / 169 components.
NOTE: 23 net record(s) with zero connected pins (dangling signal
declarations, not a violation): [...]
PASSED -- 0 domain crossings, 0 isolator-barrier breaches, 0
protective-impedance chain defects
```

Both clean. Neither gate's manifest/netclass/domain declarations were
touched.

## 8. F1: findings (report only, per this task's constraint)

Already established and fully documented in this repo
(`docs/hardware/BOM.md` line 74, dated 2026-07-26; corroborated
2026-07-29-bom-blocker-resolution.md and the 2026-07-26 BOM revision
history entry) -- confirmed still accurate against the current board, not
re-derived here:

- `elec/src/components.ato`'s `Fuse` component (`F1`, MPN `0034.3129`) is
  explicitly documented as a **bare fuse LINK**, not a holder+fuse
  assembly. Its `footprint = "Fuse:Fuse_Holder_5x20mm"` is, by its own
  docstring, "a placeholder stub, not a real verified footprint."
- The board's `F1` footprint (`pcb/temper.kicad_pcb`, `descr "Stub for
  Schurter 0034.3128 fuse holder."`) is 2-pin THT, pads at `(0,0)` and
  `(22.5,0)` -- 22.5mm pitch, matching `Fuse_Holder_5x20mm`'s stock
  KiCad geometry.
- The actual holder BOM.md specifies, **F1_HOLDER = Schurter 0031.2510
  (FUP series)**, confirmed against Schurter's own FUP datasheet: PCB/THT
  solder-pin mount, 16A(VDE)/30A(UL,CSA), approved to IEC 60127-6 (the
  fuseholder-specific standard) and suitable per IEC 60335-1. BOM.md states
  its real drilling diagram is **~30.48mm primary pin spacing plus a third
  orientation pin** -- both the pin **count** (2 vs 3) and the **pitch**
  (22.5mm vs ~30.48mm) disagree with the current board footprint.
- BOM.md explicitly flags: "**New footprint required, not yet drawn**."
  Per this task's hard constraint against inventing geometry or a pinout,
  and consistent with BOM.md's own caution, no footprint was drawn here.
  The third pin's exact position needs the FUP datasheet's own drilling
  diagram, not an inferred value.

**Not re-fixed or re-drawn here** -- this is a report of an existing,
already-correctly-flagged gap, not a new finding, and drawing the correct
footprint requires the datasheet's drilling diagram rather than
extrapolation from the 2-pin stub.

## Constraints honoured

- No safety constant, target, netclass, or domain declaration changed:
  `elec/domain_manifest.yaml`, `8.0`, `12.6` untouched (`git diff
  --stat` against those paths is empty).
- No geometry or pinout invented: F1 reported, not fixed; `tank.c_tank3`'s
  correct placement (already resolved by #459) was not re-touched.
- No board re-floorplanning: `pcb/temper.kicad_pcb` byte-identical
  throughout this task (`git diff --stat -- pcb/temper.kicad_pcb` empty).
- No `git stash` used at any point.
- Worked exclusively in an isolated worktree with its own `.venv`
  (`make venv-isolate`); `/Users/bennet/Desktop/temper` was only ever read
  from, for the stale-netlist comparison in Section 1, never written to.
- REQ-SAFE-01's test file/baseline was not edited -- it is asserted as
  failing (123 violations), reported, and left exactly as found.
