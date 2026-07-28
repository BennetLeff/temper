# Router determinism: root cause, fix, and byte-identical proof

<!-- provenance: commit=9abf7ef880f25eb7ba4b725e81423f0fc9e7ad7c
dirty=packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py
(the fix itself) -->

**Date:** 2026-07-27

**Task:** make `route_pcb()` deterministic -- identical code and identical
input must produce an identical route -- per
`docs/evidence/2026-07-27-committed-route.md`'s finding that completion
varied 37.5%-53.1% across four runs on identical code/input, root cause
UNVERIFIED (candidates: `PYTHONHASHSEED`-driven iteration order, or SAT
solve timing sensitivity).

**Board and invocation:** `pcb/temper.kicad_pcb` (170 footprints, 108
nets), routed via the documented entry point
(`route_pcb(parsed_stub, {}, design_rules=...)`, empty placements --> reads
existing positions off disk, no CP-SAT placement, no manufacturing DRC).
Same call every doc in this repo's history uses. `pcb/temper.kicad_pcb`
itself was never written to during this task -- `route_pcb()` returns
`routed_pcb_content` in memory; every measurement below dumped that string
to a scratch file, never to the tracked path. `git status` on that file is
clean throughout.

## Falsifier, stated before diagnosing

**"The variance is `PYTHONHASHSEED` and disappears when it is pinned."**

**Result: did not fire.** Pinning `PYTHONHASHSEED=0` across two
back-to-back runs of the *pre-fix* code produced two different SHA-256
hashes (`bc6a6b87...` vs `9a519c9f...`) -- pinning the hash seed did not
make output byte-identical. The actual mechanism (below) is `uuid.uuid4()`
reading `os.urandom`, which is completely independent of
`PYTHONHASHSEED`. The falsifier's proposed cause (hash-seed-driven
iteration order) is not what was happening.

## Root cause

**`uuid.uuid4()`**, called at four sites in
`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
(pre-fix lines 486, 753, 825, 838) to generate the KiCad `(tstamp "...")`
identifier attached to every emitted `(segment ...)` and `(via ...)`
element. `uuid4()` draws from `os.urandom` -- true OS randomness, not
seeded by `PYTHONHASHSEED` and not reproducible across processes by
design. This is **not** a `HashMap`/`HashSet`/`set`/`dict` iteration-order
bug (the pattern flagged as precedent in this codebase, e.g. the Rust
clearance port's `HashMap`-\>`BTreeMap` fix); it is an explicit call to a
random-value generator for a field that KiCad uses only as an internal
object identifier (no electrical, geometric, or DRC meaning).

**Proof it is the *only* source of variance:** two independent pre-fix
routing runs (`board_a.kicad_pcb`, `board_b.kicad_pcb`, both default
randomized `PYTHONHASHSEED`) were diffed directly -- 3,540 differing
lines, all `tstamp` fields, confirmed by `sed`-normalizing every
`(tstamp "...")` to a placeholder and re-diffing: **0 lines differ** after
normalization. Net topology, routed geometry, layer assignment, via
placement, and even segment emission *order* were already identical
between the two runs.

## Pre-fix characterisation (N=10, before touching any code)

Ran the production-board route 10 times pre-fix: 8 with default
(randomized) `PYTHONHASHSEED`, 2 with `PYTHONHASHSEED=0` pinned. Each run
is a fresh process (`uv run --package temper-placer python3 ...`), so
default-mode runs each got a different, OS-randomized hash seed.

| # | `PYTHONHASHSEED` | Completion | Unrouted count | Content hash (first 16 hex) |
|---|---|---:|---:|---|
| 1 | random | 0.375 | 60 | `ad3ca1c34da885c0` |
| 2 | random | 0.375 | 60 | `2ddb40cd1bd8cb3e` |
| 3 | random | 0.375 | 60 | `547eaeecc5d43d17` |
| 4 | random | 0.375 | 60 | `5deb74e7e94f7e39` |
| 5 | random | 0.375 | 60 | `eadef32b5259c368` |
| 6 | random | 0.375 | 60 | `5bed2d033a88d724` |
| 7 | random | 0.375 | 60 | `59d3fec645d7bd51` |
| 8 | random | 0.375 | 60 | `a5e52e2d10121d69` |
| 9 | `0` | 0.375 | 60 | `bc6a6b8741c28ad8` |
| 10 | `0` | 0.375 | 60 | `9a519c9f3b97171a` |

**Did the failing-net *set* vary, or only the count?** Neither varied.
**All 10 runs produced the exact same 60 unrouted net names** (same
`sorted(unrouted_nets)` list, byte-for-byte) and the exact same completion
rate (0.375 = 36/96). Only the content hash varied, and only because of
`tstamp`. This is a materially different finding from
`docs/evidence/2026-07-27-committed-route.md`'s four-run sample (which
saw completion swing 37.5%-53.1% with, implicitly, a different routed-net
set on the 53.1% run) -- see UNVERIFIED below for why that isn't
necessarily a contradiction.

## The fix

Replaced all four `uuid.uuid4()` call sites with a deterministic
`_next_tstamp()` helper (`uuid.uuid5()` over a fixed namespace UUID and a
monotonically increasing per-call sequence number), threaded as a single
shared counter (`tstamp_counter: list[int]`) through
`_write_routes_to_content` -> `_emit_zone_pours` -> `_stitch_isolated_pads`
so every segment/via/zone-stitch element emitted in one `route_pcb()`
call draws from one continuous sequence. `tstamp_counter` is an optional
keyword argument on the two helper functions (default: a fresh `[0]`), so
existing direct unit-test call sites (`tests/router_v6/test_adapter.py`)
that invoke `_stitch_isolated_pads` standalone are unaffected.

This is **not** a hidden tie-break: the fix's docstring states explicitly
that it depends on segment/via emission already happening in a fixed
order (proven above -- plain `dict` insertion order, not hash order), and
that the counter is a sequence number over that order, not a decision
that affects what gets routed. `tstamp` carries no electrical or DRC
meaning, so this cannot change routing outcomes -- only makes the
identifier field reproducible.

File changed: `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
(only file touched).

## Byte-identical proof (post-fix)

**5 consecutive default-`PYTHONHASHSEED` runs**, each a fresh process,
each dumping `routed_pcb_content` to its own file, hashed independently
with `shasum -a 256`:

```
ae049ae47db20472b53517fa00f5b19f2ded0072cf164672bd0d2a8e6363f92b  fix_run1.kicad_pcb
ae049ae47db20472b53517fa00f5b19f2ded0072cf164672bd0d2a8e6363f92b  fix_run2.kicad_pcb
ae049ae47db20472b53517fa00f5b19f2ded0072cf164672bd0d2a8e6363f92b  fix_run3.kicad_pcb
ae049ae47db20472b53517fa00f5b19f2ded0072cf164672bd0d2a8e6363f92b  fix_run4.kicad_pcb
ae049ae47db20472b53517fa00f5b19f2ded0072cf164672bd0d2a8e6363f92b  fix_run5.kicad_pcb
```

**All 5 byte-identical.** Two further post-fix runs with
`PYTHONHASHSEED=0` and `PYTHONHASHSEED=1` explicitly pinned produced the
*same* hash (`ae049ae47db20472...`) as the 5 unpinned runs above,
confirming the fix is correct for the right reason (the hash seed was
never the mechanism) rather than accidentally masking it.

Combined with the pre-fix characterisation, this task performed **17
independent process launches** of `route_pcb()` against the same board:
10 pre-fix (10 distinct hashes, 1 shared completion outcome) and 7
post-fix (1 shared hash, 1 shared completion outcome).

## Settled completion rate

**0.375 = 36/96 nets routed (60 unrouted).** This is the **low end** of
the historical 37.5%-53.1% range, not the high end -- **below** the
committed board's 51/96 = 53.1%. Stated plainly per the task's own
instruction: this is not a regression to hide. The deterministic router,
run 17 times under this exact commit and environment, never once produced
the committed board's 53.1% outcome; it produced 37.5% every single time.
The 53.1% committed board is, on current evidence, an unreproduced
outlier relative to what this code/board/machine combination actually
and reliably produces today.

All 60 unrouted nets fail with the same single stated reason as prior
evidence docs: `no legal path found (forced segment disallowed)` -- 0
`congestion` or plain `no path found` failures. No new failure mode was
introduced by this fix (expected: the fix only touches an identifier
string, never a routing decision).

## Gate states (post-fix, this task)

| Check | Result |
|---|---|
| `cargo test --release` (`temper-rust-router-core`) | **101 passed, 0 failed** across 6 binaries (90+1+1+8+1+0) |
| `cargo clippy --release --all-targets -- -D warnings` (`temper-rust-router-core`) | 0 warnings |
| `make netlist` | **76 assertions, 76 passed, 0 failed** |
| `scripts/check_domain_partition.py` | exit 0 -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects |
| `scripts/capacity_budget_gate.py` | exit 0 -- Design capacity budget gate PASSED, 0 defects |
| `scripts/mpn_fabrication_gate.py` | exit 0 -- MPN fabrication gate PASSED, 0 new violations |
| `scripts/check_derived_doc_drift.py` | exit 0 -- 3 documents, 45 tables, 52 gate rows matched, 132 fields checked |
| `scripts/check_vacuous_gates.py` | exit 0 -- 532 files scanned, 0 violations |
| `tests/router_v6/test_adapter.py` + `test_via_output_writer.py` + `test_via_layer_properties_pbt.py` | 82 passed, 2 failed -- **both pre-existing**, confirmed identical failures on the unmodified code (`git stash` + re-run before restoring the fix); unrelated to `tstamp`/UUID (a hypothesis-based-example counter-example in the isolated-pad stitch-threshold property tests) |
| `tests/router_v6/` full suite | Not run to completion (time budget) -- reached 22% (through `test_capacity_check.py`) with **zero failures** before being stopped; not a substitute for the targeted adapter tests above, which did complete |

`pcb/temper.kicad_pcb` was not modified by any measurement in this task
(`git status` clean on that path throughout); the pre-existing 170-vs-168
footprint/netlist resync remains untouched and out of scope, as
instructed.

## UNVERIFIED

- **Whether the historical 37.5%-53.1% completion-rate swing (with,
  implicitly, a different routed-net set on the high end) ever reflected
  a real code-level nondeterminism, or was itself environment/machine-
  dependent** (e.g. a different CPU affecting floating-point operation
  order somewhere upstream of the SAT model, which the CaDiCaL solver
  could then amplify into a different satisfying assignment). This task's
  17 runs, all on one machine, never reproduced anything but 37.5% -- the
  53.1% outcome was not observed here even once. Not falsified either:
  a machine/thread-scheduling-dependent effect that requires different
  hardware to trigger cannot be ruled out from a single-machine
  measurement.
- **Exhaustive audit of `HashMap`/`HashSet` usage in
  `temper-rust-router-core`** (encoding.rs's `name_to_idx`, tension.rs's
  several `HashMap<usize, HashSet<&str>>` structures, extraction.rs,
  combinator/rewrite.rs) was **not** performed line-by-line. The
  byte-identical-after-tstamp-normalization result across many
  independent runs is strong indirect evidence none of these leak into
  observable output *on this board, today*, but it is not a proof by
  code reading that no such leak could occur on a different board shape
  or a different CNF where the affected code paths are actually
  exercised with a live tie. `net_ordering.py`'s `order_nets()` was
  spot-checked and found already well-designed: an explicit six-level
  priority chain ending in an alphabetical tiebreaker, not an incidental
  container-order artifact.
- Whether the 12-net gap between 108 parsed nets and 96 nets attempted by
  Stage 4 is fully explained by zone-pour-treated net classes -- carried
  over unverified from prior evidence docs, not re-traced here (out of
  this task's scope).
- Full `tests/router_v6/` suite result beyond the 22% executed before
  the run was stopped for time budget (zero failures in that 22%,
  including the file most relevant to this change).
