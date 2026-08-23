<!-- provenance: commit=36257737284839f18e1d11ac1fc0cb3b0383b4fc, dirty=false, branch=fix/pin-pumpkin-engine-build,
worktree=/home/bennet/Desktop/temper-worktrees/pin-pumpkin-engine, base=66a277d94
(origin/main tip at task start). Measured 2026-08-12. rustc 1.97.1 (8bab26f4f
2026-07-14), cargo 1.97.1 (c980f4866 2026-06-30). kicad-cli 10.0.5 at
/home/bennet/.local/opt/kicad-10.0.5 (LD_LIBRARY_PATH covering root/usr/lib*,
KICAD_STOCK_DATA_HOME=root/usr/share/kicad). All board regeneration under
/tmp/.../scratchpad/recipe-run/, never under pcb/** (`git status --short pcb/`
empty at every checkpoint in this worktree, verified before/after; the J1
Connector_JST footprint prerequisite `docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md`
Sec 7 records was applied to a SCRATCH COPY of pcb/, not to this worktree's
own pcb/, specifically so it never needed reverting). -->

# The pumpkin_engine binary is now pinned, verified before every solve, and fails loudly on mismatch -- proven against a real wrong binary that is STILL sitting unpinned in the main checkout right now

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task, later the same
> day as the "re-pinned post-#1054" update below, not by this document's original
> author.** §6's routing baseline -- **168 footprints / 3,314 segments / 40 vias / 58
> zones, 65/105 nets, `clearance`=499** -- is **VOID**, not merely "stale" as §7 already
> flagged it. It was measured on the *pre*-#1054 pin (`source_commit=e5539273a`), and a
> subsequent run against the current, post-#1054 pinned engine, with a separately
> corrected write path (`_apply_placements_to_pcb`'s `board_origin` parameter, dropped by
> an unrelated PR's scratch driver -- not a defect in this document's own method),
> established the true numbers below. This document's core deliverable -- the identity
> gate itself (§1-5, §7) -- is unaffected by this correction; only §6's specific board
> shape is void.
>
> **True baseline**: **2,514 segments / 22 vias / 76 zones / 168 footprints**;
> `SAF_HVL_001` 94 -> 74 (-21%); nets connected 22/112 (19.6%); `unconnected_items` 428 ->
> 351; kicad-cli `clearance`=499 across 130 samples, `creepage` 114-116, `shorting_items`
> 110, total errors 1075-1077. Current source of truth: `scripts/board_shape_baseline.json`
> (also records the two still-earlier VOID baselines this document's own §"Verdict up
> front" already superseded: 3,349/56/70 and PR #1050's 4,228/74). **Nothing below this
> notice has been edited.**

**Update, same day: re-pinned post-#1054.** Sections 1-6 below are the
original measurements, taken against `source_commit=e5539273a` (pre-#1054).
PR #1054 has since merged to `main` and edits the exact file this pin's
`build_command` compiles, which would have made this pin's own gate
spuriously reject a correct post-#1054 rebuild. **Sec 7 is the fix**: this
branch rebased cleanly onto `origin/main` (post-#1054), the engine was
rebuilt and re-pinned (`binary_sha256=7ff153f4...` /
`source_commit=5bbf650d47` -- current `main` HEAD), rebuild determinism was
re-measured (not assumed) on the new source, and the gate was re-proven
firing both ways. Read Sec 7 for the current pin; Sec 1-6's hash
(`57fe087e...283cd02`) and commit (`e5539273a`) below are historical, not
what `engine_pin.json` now contains. The Sec 6 routing baseline
(168/3,314/40/58, `clearance`=499) is now stale for the same reason and is
flagged outstanding in Sec 7, not silently carried forward.

**Verdict up front (original, pre-#1054 measurement -- see update above).** The place-and-route recipe's placement stage now resolves
its CP solver through `scripts/verify_pumpkin_engine.py`, which hashes the
candidate binary and compares it against a checked-in pin
(`docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json`). A binary that is
absent still produces a legitimate skip (unchanged behavior); a binary that
**exists but does not match the pin now raises `PumpkinEngineIdentityError`
and fails the caller outright** -- proven three ways below, including live
against the main checkout's actual current `target-shared/release/pumpkin_engine`,
which **right now, unmodified by this task**, is still the exact wrong build
PR #1058 found: sha256 `7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e`,
a build of the unmerged branch `fix/pumpkin-to-units-and-netclass-skip`, not
of `main`. Rebuild determinism was measured, not assumed: two independent
`cargo build --release --locked` invocations from `main`'s committed source,
into two independent `CARGO_TARGET_DIR`s, produced byte-identical output on
this toolchain -- so the pin is a manifest (hash + source commit + toolchain
+ build command), not a committed binary. With the pinned engine, the
recipe's reconciliation and placement stages were re-run from a clean
checkout and reproduced **exactly** every previously-published invariant
(netlist digest, reconciliation counts, partition, per-isolator feasibility,
170 barrier constraints, `status=optimal`, byte-identical positions across
two independent solves). Routing then completed (`--net-batching`): **168
footprints, 3,314 segments, 40 vias, 58 zones, 65/105 nets routed (61.9%),
kicad-cli `clearance`=499 (byte-stable across 5 DRC samples)**. This
**supersedes both prior published baselines** (3,349/56/70 and 4,228/74) --
neither is reproducible from an identifiable binary; this one is. Sec 6
gives the full breakdown. **One check is explicitly left outstanding**: a
second independent `--net-batching` run to reconfirm route-stage
determinism on this exact input was abandoned mid-run when a concurrent
agent's routing process was OOM-killed on this shared machine (Sec 6c) --
route-stage determinism itself was already established independently, on
unchanged code, by the prior reproducibility doc's Sec 4, so this gap does
not touch Sec 2-5 (the mechanism and its proof) or the single, completed,
uncorrupted routing run Sec 6b's numbers came from.

## 1. The problem (verified prior to this task; not re-derived here)

`test_golden_board_pumpkin_real_board.py::_find_pumpkin_binary` resolved the
placement solver to `target-shared/release/pumpkin_engine`
(`.gitignore:136`, untracked, `git ls-files | grep pumpkin_engine` -> 0) with
no identity check at all -- existence was the only test. PR #1058
(`docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md`)
proved this let an unmerged branch's build (`fix/pumpkin-to-units-and-netclass-skip`,
which changes `to_units`'s rounding rule and therefore every barrier
`value_mm` and `w0`/`h0`) silently stand in for `main`'s, producing a
materially different placement (`decision_sha 4a6f1652` vs `d2354778`) from
an **identical** 22,118-constraint payload, and a downstream route differing
by hundreds to thousands of segments. Six regenerations of "the same" recipe
this way produced four-figure-different boards with byte-identical inputs at
every stage upstream of the solver.

## 2. Mechanism

Two new files, both under this PR's `scripts/`/`docs/evidence/` scope (no
`pcb/**` change):

- **`docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json`** -- the pin.
  Records `binary_sha256`, `source_commit` (the last commit on `main` to
  touch this crate, `e5539273a`), `manifest_path`, `build_command`,
  `rustc_version`, `cargo_version`, and a `notes` field carrying the
  rebuild-determinism finding (Sec 4) inline so a future reader does not
  have to find this document to know the pin is backed by a measurement,
  not an assumption.
- **`scripts/verify_pumpkin_engine.py`** -- the single choke point for
  resolving *and* verifying the binary, modeled on this repo's existing
  content-hash gates (`scripts/check_oracle_hashes.py`,
  `scripts/check_stale_extensions.py`: pin file + sha256 comparison, fail
  closed, same exit-code convention). Exposes
  `resolve_verified_pumpkin_engine(repo_root) -> VerifiedPumpkinEngine | None`:
  - **No candidate anywhere on disk** -> returns `None`. Still a legitimate
    "not built" state (most machines never build this spike binary) --
    callers keep treating this as skip, unchanged from before this PR.
  - **A candidate exists and matches the pin** -> returns a
    `VerifiedPumpkinEngine` carrying `path`, `sha256`, and the pin's
    metadata, plus an `identity_line()` string
    (`pumpkin_engine sha256=... source_commit=... path=...`) meant to be
    folded into a caller's own evidence output -- the property the task
    asked for ("a pipeline run must be able to state which engine build
    produced it").
  - **A candidate exists and does NOT match the pin** -> raises
    `PumpkinEngineIdentityError`, uncaught. This is the one case the
    pre-existing code let through silently, and it is exactly the case that
    produced six different boards from "the same" recipe -- so it is a hard
    failure, never a warning, never downgraded to a skip.

  Also a CLI (`--build`, `--require`, exit 0/3/5 mirroring
  `check_oracle_hashes.py`) for standalone use outside pytest.

`packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py`'s
`_find_pumpkin_binary` (`path:153` before this PR) now delegates to
`resolve_verified_pumpkin_engine` and prints `identity_line()` before
solving (`path:246-253`). Its candidate-search logic (worktree-local,
`CARGO_TARGET_DIR`, main-checkout-via-`git-common-dir`) moved into
`verify_pumpkin_engine.py` unchanged -- one definition now, not one per
caller, which is what let the original bug hide (every ad hoc recipe script
that reused `_find_pumpkin_binary` inherited its existence-only check; none
of them checked identity because there was nowhere to check it against).

## 3. Proof it fires -- three ways, including live, unforced, right now

**3a. Live, on the main checkout's actual current binary -- not staged for
this document.** Run from this worktree, pointed at the main checkout with
this PR's pin:

```
$ python3 scripts/verify_pumpkin_engine.py --repo-root /home/bennet/Desktop/temper \
    --pin docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json
pumpkin_engine identity gate: MISMATCH
pumpkin_engine binary at /home/bennet/Desktop/temper/target-shared/release/pumpkin_engine does NOT match the pinned identity...
  expected sha256 57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02 (built from commit e5539273a01c030c0968006fcf61bb4bedba65be)
  actual   sha256 7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e
exit=3
```

`7ff153f478f8...` is byte-for-byte the same hash PR #1058 measured for a
build of the unmerged `fix/pumpkin-to-units-and-netclass-skip` branch. That
binary is **still sitting in `/home/bennet/Desktop/temper/target-shared/release/`
right now**, unpinned, untouched by this task -- proof that the bug this PR
closes is not hypothetical or historical, it is live in the shared checkout
at the moment of writing.

**3b. Synthetic, minimal.** Copied the verified, freshly-built binary,
flipped one byte, pointed the resolver at only that copy (temporarily moved
the good binary aside so the corrupted copy was the sole candidate):

```
$ mv target-shared/release/pumpkin_engine target-shared/release/pumpkin_engine.good
$ CARGO_TARGET_DIR=<scratch-dir-holding-the-1-byte-flipped-copy> python3 scripts/verify_pumpkin_engine.py
pumpkin_engine identity gate: MISMATCH
  expected sha256 57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02
  actual   sha256 de609965e942d8289cbc2c145df8632fa73967bf2e9a870cdeb12bdeaccccc95
exit=3
$ mv target-shared/release/pumpkin_engine.good target-shared/release/pumpkin_engine   # restored
$ python3 scripts/verify_pumpkin_engine.py
pumpkin_engine identity gate: VERIFIED -- pumpkin_engine sha256=57fe087e... source_commit=e5539273a...
exit=0
```

**3c. End to end, inside the actual golden test (`pytest`, not the CLI).**
With the correct binary in place:

```
tests/.../test_golden_board_pumpkin_real_board.py::test_golden_board_drc_regression_pumpkin_real_board
[pumpkin real-board golden test] pumpkin_engine sha256=57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02 source_commit=e5539273a01c030c0968006fcf61bb4bedba65be path=.../target-shared/release/pumpkin_engine
[pumpkin real-board golden test] components=169 constraints=22026 status=optimal solve_time_ms=1313.67
PASSED
```

With the same 1-byte-flipped binary in place, same test, same command:

```
tests/.../test_golden_board_pumpkin_real_board.py::test_golden_board_drc_regression_pumpkin_real_board FAILED
    pumpkin_bin = _find_pumpkin_binary()
tests/.../verify_pumpkin_engine.py:246: in resolve_verified_pumpkin_engine
    raise PumpkinEngineIdentityError(...)
E   verify_pumpkin_engine.PumpkinEngineIdentityError: pumpkin_engine binary at .../target-shared/release/pumpkin_engine does NOT match the pinned identity...
E     expected sha256 57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02
E     actual   sha256 32185e29bd6188b72c6e3e278298c49cf9de78b7e5baeac5db85a15ffdc5a830
1 failed in 0.24s
```

**FAILED, not SKIPPED, not a warning with a passing exit code.** This is the
exact property the task required verified, not asserted: "a guard never seen
to fail is not a guard." The correct binary was restored immediately after
(sha256 `57fe087e...283cd02` confirmed) before any further measurement in
this document.

## 4. Rebuild determinism -- measured, not assumed

Two independent `cargo build --release --locked --manifest-path
docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml` invocations, each into
its own `CARGO_TARGET_DIR` (different absolute scratch paths, so neither
could share incremental state with the other), from this worktree's
checkout of `main`'s committed source (`e5539273a`, unchanged on `main`
since -- `git diff e5539273a HEAD -- docs/evidence/2026-08-07-pumpkin-engine/`
is empty):

```
$ CARGO_TARGET_DIR=<scratch>/build1 cargo build --release --locked --manifest-path ...
$ CARGO_TARGET_DIR=<scratch>/build2 cargo build --release --locked --manifest-path ...
$ sha256sum <scratch>/build1/release/pumpkin_engine <scratch>/build2/release/pumpkin_engine
57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02  build1/release/pumpkin_engine
57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02  build2/release/pumpkin_engine
```

**Byte-identical.** A third build (`scripts/verify_pumpkin_engine.py --build`,
into this worktree's own `target-shared`, a third distinct absolute path)
produced the same hash again. This also matches, independently, PR #1058's
own "build of `origin/main`" measurement (`57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02`)
-- taken in a **different worktree, different session, same rustc/cargo
(1.97.1)** -- so this is not just two builds agreeing with each other, it is
three independent measurements, across sessions and worktree paths,
agreeing with a fourth.

**Decision: pin via manifest, do not commit the binary.** The build is fast
(<15s warm, ~1-2min cold -- a handful of small crates, not a heavyweight
dependency), reproducible on this toolchain across every worktree path
tested, and a 2MB binary in git would need to be re-committed on every
future source change with no way to verify from the diff alone that the new
binary actually corresponds to the new source. A pinned hash plus a
`--locked` build command gives the same guarantee (byte-identical
reproduction from committed state) without that maintenance burden.
**Caveat, stated plainly per the task's own bar:** this measures
reproducibility across worktree paths on **one machine, one rustc/cargo
version (1.97.1)**. It does not test a different OS or a different rustc
minor version -- `rustc_version`/`cargo_version` are recorded in the pin
precisely so a toolchain-driven mismatch is diagnosable (a version string
mismatch, not a mystery hash) rather than assumed away. If CI or a
contributor's machine runs a different rustc, re-pinning after verifying
that build's own reproducibility is the expected next step, not a sign the
mechanism is broken.

## 5. Source provenance (noted, not changed)

The engine's source lives at `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs`
-- an evidence directory, not a place a contributor auditing "what does the
build depend on" would normally look. This placement plausibly contributed
to the original bug: nothing under `docs/evidence/` reads as
build-dependency-bearing by convention, so the fact that a recipe's
correctness depended on an unpinned artifact built from files living there
was easy to miss. Per the task's explicit scope, **relocating it is a
separate proposal, not made here** -- this PR only pins what already
exists in place.

## 6. Baseline re-establishment

### 6a. What reproduced exactly, with the pinned engine, from a clean worktree

`make netlist` on this worktree: digest `8cfd715e60a3…`, matching the recipe
doc and #1049/#1058's independently-reported digest.

Reconciliation (`scripts/resync_pcb_netlist.py`, against a copper-stripped
copy of `pcb/temper.kicad_pcb` -- the real `pcb/` was never touched; a
scratch copy of the whole `pcb/` directory was used, with the J1
`Connector_JST` footprint prerequisite `docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md`
Sec 7 records applied only to that scratch copy):

```
kept=162 added=6 removed=7 moved=0
netlist_components=168 old_board_footprints=169 new_board_footprints=168
added:   [C37, J1, R65, T2, TP3, U19]
removed: [D2, R6, R7, R8, R9, R10, U3]
sha256(board_stripped.kicad_pcb) = f727fb1e416296e9773aa31f51b06eecd9e98b43d6ed8ff0d0d8a06ebf227268
```

Exact match to PR #1058's independently-measured `f727fb1e4162…` and to the
recipe doc's kept/added/removed/moved counts.

Placement (Pumpkin via the now-VERIFIED engine, netclass+courtyard
constraints, PD2/8.0mm horizontal isolation barrier per
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`, U6
relaxed per `docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s own
method section, seed=42, timeout_ms=30000):

```
netclass=9,647  courtyard_backfill=12,301  base_total=21,948
partition: hv_only=40 selv_only=109 isolators=8 unclassified=11
isolators: C6, K1, K2, K3, PS1, T1, T2, U6
corridor: [113.0, 121.0] mm  (board 152x234mm)
per-isolator feasibility (all 8, informational -- U6 relaxed from the wire constraints):
  C6  achievable_gap_mm=8.000  chosen_rotation=3  feasible=True
  K1  achievable_gap_mm=8.000  chosen_rotation=2  feasible=True
  K2  achievable_gap_mm=12.760 chosen_rotation=1  feasible=True
  K3  achievable_gap_mm=12.760 chosen_rotation=1  feasible=True
  PS1 achievable_gap_mm=35.500 chosen_rotation=3  feasible=True
  T1  achievable_gap_mm=9.100  chosen_rotation=0  feasible=True
  T2  achievable_gap_mm=9.100  chosen_rotation=0  feasible=True
  U6  achievable_gap_mm=8.100  chosen_rotation=1  feasible=True
barrier constraints=170  total=22,118
status=optimal  solve_time_ms≈2,516-2,599 (two independent runs)
positions equal across the two runs: True   rotations equal: True
```

Every published invariant matches PR #1058's table exactly: 9,647 / 12,301 /
21,948 / 170 / 22,118 base+barrier counts, 40/109/8/11 partition, the exact
isolator set, the exact corridor, and the per-isolator feasibility table "to
the last digit." Placement is deterministic (byte-identical positions and
rotations across two independent process launches, same as every prior
determinism check in this lineage). One deviation from the prior sessions'
process, disclosed rather than hidden: the diagnostic "all 8 isolators
hard-constrained" configuration (173 constraints, no U6 relaxation) was
tried first and reproduced PR #1058's own U6 joint-infeasibility finding
almost exactly (`status=infeasible` in 2.9s here vs. PR #1058's 3.1s) --
independent confirmation, not assumed, that the barrier encoding and the
U6-relaxed production configuration are both correct before trusting the
170/22,118 numbers above.

**Which side of PR #1054 this baseline sits on:** built and pinned from
`main`'s committed `pumpkin_engine` source (`e5539273a`), **not** from
`fix/pumpkin-to-units-and-netclass-skip` (`6ba28447e`, PR #1054, still
unmerged as of this task -- `git merge-base --is-ancestor` confirms it is
not an ancestor of `origin/main`). This baseline is therefore the
**pre-`to_units`-fix** side. If/when #1054 lands, the pin's `binary_sha256`
and `source_commit` must be updated (a new build, re-verified for
reproducibility the same way Sec 4 did) and this baseline re-measured
again -- it will not carry over silently, because the verification gate
this PR adds will refuse the old pin against the new binary.

### 6b. Routing -- the superseding baseline

`scripts/route_board.py --net-batching` against the pinned-engine placed
board (`board_placed.kicad_pcb` above, byte-identical across both
determinism-check solves):

```
Result: 65/105 nets (61.9%)  segments=3314 vias=40 zones=58  wall=255.1s
Result (pad connectivity, PRIMARY metric): 48/139 nets fully pad-connected  fake-completion=55 honest-gap=36
[net-batching] run completed via subprocess-per-batch Stage 3 dispatch
```

kicad-cli DRC (`--all-track-errors`, single-thread `KICAD_CONFIG_HOME` pin,
DRU regenerated fresh via `generate_kicad_dru.generate_dru()`, project
sidecar copied from `pcb/temper.kicad_pro` via `copy_kicad_project_sidecar`
-- same convention every prior evidence doc in this lineage uses), 5
repeated samples against the same, byte-identical routed board file:

| metric | value |
|---|---:|
| footprints | **168** |
| segments | **3,314** |
| vias | **40** |
| zones | **58** |
| nets attempted/routed (Stage 4 A* denominator) | 105 attempted, 65 routed (61.9%) |
| nets fully pad-connected (`pad_connectivity_audit`, PRIMARY metric) | 48/139 (fake-completion 55, honest-gap 36) |
| `clearance` (kicad-cli, 5 samples) | 499, 499, 499, 499, 499 -- **byte-stable, all 5** |
| `shorting_items` (kicad-cli, 5 samples) | 131, byte-stable all 5 runs |
| `creepage` (kicad-cli, 5 samples) | 60, 60, 61, 61, 61 -- range 60-61 |
| total DRC errors / warnings | 1196-1197 errors / 668 warnings |

**This table supersedes both prior published baselines
(3,349 seg / 56 vias / 70 zones / 80-of-105 nets, and #1050's
4,228 / 74) -- neither is reproducible from a binary anyone can now
identify (Sec 1, Sec 4).** This one is: it was produced by the
sha256-`57fe087e...283cd02` build of `main`'s committed
`e5539273a`, a build this document proves reproduces bit-for-bit from
committed source on this toolchain (Sec 4), verified against the checked-in
pin before it was allowed to solve (Sec 2-3). `clearance`=499 landing on
the same figure as both prior baselines, despite this board's copper
differing from both by double-digit percentages, is consistent with the
already-documented finding
(`docs/evidence/2026-08-12-clearance-regression-independent-spike.md`) that
`clearance` is driven by one congested region rather than board-wide
copper density -- noted, not treated as evidence the boards are otherwise
similar.

**Fewer nets routed (65/105, vs. the prior baseline's 80/105) is a real,
disclosed difference, not swept under "supersedes."** This document does
not have an explanation on hand (it was out of scope to chase -- the task
this document answers is engine identity, not routing-completion
regression) and does not speculate one. What it can rule out: the
placement feeding this route reproduced every independently-checkable
upstream invariant exactly (Sec 6a), so the difference is downstream of
placement, in routing itself or in this measurement's own environment
(single-threaded `KICAD_CONFIG_HOME`, `--net-batching` batch scheduling,
or ordinary run-to-run completion variance the recipe doc's own Sec 4-5
already documented for net-batching). A second independent
`--net-batching` run from the identical placed board was launched to check
whether this specific 65/105 result is itself deterministic; see Sec 6c.

### 6c. Routing determinism check -- OUTSTANDING, explicitly

**Not completed. Deliberately abandoned mid-run, not silently dropped.** A
second, fully independent `route_board.py --net-batching` launch (fresh
interpreter, fresh `multiprocessing.spawn` Stage-3 children, the identical
byte-identical `board_placed.kicad_pcb` input Sec 6b's run used) was
started to check whether that section's 65/105 / 3,314 / 40 / 58 result
reproduces byte-for-byte. It was killed before completion: a concurrent
agent on this same machine had a `route_board.py` run OOM-killed twice at
~59.5GB RSS from shared memory pressure, and running a second concurrent
routing pass here was more likely to degrade or corrupt that measurement
and this one than to finish cleanly.

**This does not weaken this document's actual deliverable.** Route-stage
determinism under concurrent load was already independently established,
on then-current code (unchanged in every file the routing stage touches,
per Sec 6a's `git diff` argument extending forward from #1050) by
`docs/evidence/2026-08-12-board-recipe-reproducibility.md` Sec 4: two
`--net-batching` runs launched as competing OS processes on the same 24
cores produced byte-for-byte identical output. This task's own finding is
orthogonal to that one -- the variable six mutually-inconsistent boards
traced back to was the **solver binary's identity**, not routing
nondeterminism, which was already ruled out. Closing this specific gap (a
fresh two-run determinism check with THIS binary's placement as input) is a
five-minute follow-up on a machine without concurrent memory pressure; it
does not change Sec 2-5 (the mechanism and its proof) or the trustworthiness
of Sec 6b's numbers, which came from a single, completed, non-corrupted run.

## 7. Re-pin post-#1054 (`to_units` ceil-to-even) -- rebased, rebuilt, re-verified

**#1054 merged to `main` after this document's original measurements (Sec
1-6) were taken, and it edits exactly the file this PR's pin's
`build_command` compiles**
(`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs`, `to_units`:
decrement-to-even -> ceil-to-even, changing 6 of 338 `w0`/`h0` dimensions on
the real board). Left alone, the old pin (`source_commit=e5539273a`,
`binary_sha256=57fe087e...283cd02`) would make a **correct** rebuild from
current `main` fail the gate this PR adds -- exactly the failure mode Sec 6
above flagged as expected ("If/when #1054 lands, the pin's
`binary_sha256` and `source_commit` must be updated... it will not carry
over silently"). This section is that update, measured fresh, not carried
over from Sec 1-6.

**Rebase.** This branch rebased cleanly onto `origin/main` (`5bbf650d47`,
HEAD at rebase time) with **zero conflicts** -- `main.rs` included, because
this branch never touched it; the file now matches `origin/main`'s
post-#1054 content exactly (`git diff origin/main -- .../src/main.rs` is
empty on this branch after the rebase).

**Rebuild.** Same toolchain as the original pin (`rustc`/`cargo` 1.97.1,
unchanged), same pin-recorded `build_command`
(`cargo build --release --locked --manifest-path
docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml`), two independent
`CARGO_TARGET_DIR`s:

```
$ CARGO_TARGET_DIR=<scratch>/pumpkin_build_a cargo build --release --locked --manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml
   Finished `release` profile [optimized] target(s) in 9.93s
$ CARGO_TARGET_DIR=<scratch>/pumpkin_build_b cargo build --release --locked --manifest-path docs/evidence/2026-08-07-pumpkin-engine/Cargo.toml
   Finished `release` profile [optimized] target(s) in 10.17s
$ sha256sum <scratch>/pumpkin_build_a/release/pumpkin_engine <scratch>/pumpkin_build_b/release/pumpkin_engine
7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e  pumpkin_build_a/release/pumpkin_engine
7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e  pumpkin_build_b/release/pumpkin_engine
$ cmp pumpkin_build_a/release/pumpkin_engine pumpkin_build_b/release/pumpkin_engine   # (no output: identical)
```

**Byte-identical.** Determinism was re-measured at this commit, not assumed
from Sec 4's pre-#1054 finding, because #1054 changed the source.

`docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json` updated:

| field | old (pre-#1054) | new (post-#1054) |
|---|---|---|
| `binary_sha256` | `57fe087ecf6cfd3c611e23c78c32c1cde5bf50c8dbda7bae78b7eb7fd283cd02` | `7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e` |
| `source_commit` | `e5539273a01c030c0968006fcf61bb4bedba65be` | `5bbf650d47d3a07fffd10a44e7c06c43a0a800bd` (main HEAD at re-pin) |
| `rustc_version` / `cargo_version` | 1.97.1 / 1.97.1 | unchanged |

`source_commit` is main HEAD rather than #1054's own commit (`3322d52da`)
because `git diff 3322d52da 5bbf650d47 -- docs/evidence/2026-08-07-pumpkin-engine/`
is empty -- no further changes to this directory between #1054 and HEAD, so
the two are equivalent as a pin target.

Note the new `binary_sha256` (`7ff153f4...`) is byte-for-byte the same hash
Sec 3a/Sec "verdict up front" above reported for the main checkout's actual
`target-shared/release/pumpkin_engine` at the time this document was
originally written, attributed there to "a build of the unmerged branch
`fix/pumpkin-to-units-and-netclass-skip`, not of `main`." That branch's
change *was* #1054 -- so that binary was the wrong build **then** (`main`
had not yet merged it) and is, by coincidence of unchanged bytes, the
**correct** build **now** that `main` has caught up to it. This is
recorded as a coincidence of this specific source change, not a general
property of the gate -- a future source change will produce a new hash.

**Gate re-proven, both directions, against real binaries in this
worktree's own `target-shared`:**

```
$ python3 scripts/verify_pumpkin_engine.py --repo-root .
pumpkin_engine identity gate: VERIFIED -- pumpkin_engine sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd path=.../target-shared/release/pumpkin_engine
exit=0
```

Byte-flipped copy (one byte XORed with `0xFF` in a copy of the just-built
binary, installed as the sole candidate, good binary moved aside):

```
$ python3 scripts/verify_pumpkin_engine.py --repo-root .
pumpkin_engine identity gate: MISMATCH
  expected sha256 7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e (built from commit 5bbf650d47d3a07fffd10a44e7c06c43a0a800bd)
  actual   sha256 40aa193ac5554e0cd137bd7de3c17e08c10b4a22f24a41ad5e5eb9bd682067de
exit=3
```

Good binary restored immediately after (`7ff153f4...` confirmed); gate
re-verified `exit=0` a second time. Additionally, unprompted: before the
correct binary was installed, this worktree's own `target-shared/release/pumpkin_engine`
still held a genuinely **stale** binary left over from before the rebase
(`57fe087e...283cd02`, a real build of the pre-#1054 source, not staged for
this test) -- the gate correctly flagged it as `MISMATCH` too, a second,
unforced real-world confirmation alongside the deliberate byte-flip.

**Baseline (Sec 6): outstanding, not regenerated.** Sec 6's 168/3,314/40/58,
65/105-net, `clearance`=499 numbers were measured on the pre-#1054 engine
(Sec 6 already flagged this) and are now stale, since #1054 moves
placement. Regenerating requires the same multi-stage recipe Sec 6
used (reconciliation against a scratch `pcb/` copy with the J1
prerequisite, Pumpkin placement, then `route_board.py --net-batching`,
which alone took 255s wall in Sec 6b and is the stage the task's own
briefing warned has OOM-killed two concurrent runs on this shared machine
today at ~54-59GB RSS). At re-pin time this worktree's machine showed a
load average around 10 (vs. 24 cores) with multiple other agents'
concurrent `cargo build`/`mypy` processes active and rising memory use
during this task's own two engine rebuilds -- not clearly saturated, but
not the clean conditions Sec 6's own baseline was measured under either.
Given the task's explicit instruction not to retry a died run repeatedly
and that this baseline is optional ("if cheap"), it was not attempted this
session; Sec 6's numbers remain published but should be read as
**pre-#1054 and now stale**, not as this pin's baseline. Regenerating them
with the newly-pinned `7ff153f4...` engine, under less contended
conditions, is the natural next step and does not require re-deriving any
of Sec 1-7's mechanism or gate proof above.

## 8. Rules-compliance notes

- `pcb/**` untouched throughout this task (`git status --short pcb/` empty
  at every checkpoint in this worktree). The J1 `Connector_JST` footprint
  prerequisite (`docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md`
  Sec 7, originally landed on the separate, unmerged `feat/land-candidate-board`
  branch) was applied to a **scratch copy of the entire `pcb/` directory**,
  never to this worktree's own `pcb/`, specifically so no revert was ever
  needed and this worktree's `pcb/` stayed byte-identical to `origin/main`
  the entire time.
- `docs/evidence/2026-08-07-pumpkin-engine/src/main.rs` was not modified
  (Sec 5: relocating it is out of scope for this PR).
- The known latent gap PR #1058 Sec 8 recorded
  (`isolation_barrier.classify_domain_partition` raising `TypeError` on an
  un-netted pad) was hit again here (4 such pads, all on K1, matching PR
  #1058's own count) and worked around at this task's own scratch call site
  only (`net=None -> ""`), production code untouched -- identical to how PR
  #1058 handled it.
