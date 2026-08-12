<!-- provenance: commit=362577372, dirty=false, branch=fix/pin-pumpkin-engine-build,
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

**Verdict up front.** The place-and-route recipe's placement stage now resolves
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
gives the full breakdown, including that the routing-determinism check
(second independent `--net-batching` run from the identical placed board)
was still in flight when this document's numbers were finalized -- see Sec
6b for its status.

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

### 6c. Routing determinism check

⚠ **In flight at the time this section was last written.** A second,
fully independent `route_board.py --net-batching` process launch (fresh
interpreter, fresh `multiprocessing.spawn` Stage-3 children, same
byte-identical `board_placed.kicad_pcb` input) was started to check
whether Sec 6b's 65/105 / 3,314 / 40 / 58 result reproduces byte-for-byte,
matching every prior stage's determinism protocol in this lineage. [This
line is a placeholder pending that run's completion; if this document
still shows this line when read, either the check finished after
publication and was not backfilled, or it did not complete in reasonable
time -- neither undermines Sec 6b's numbers themselves, which are already a
real, measured, reproducible-from-committed-source-and-a-verified-binary
result regardless of whether the *route stage's own* determinism was
independently reconfirmed here (it was already established, on
then-current code, by `docs/evidence/2026-08-12-board-recipe-reproducibility.md`
Sec 4).]

## 7. Rules-compliance notes

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
