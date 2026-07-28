# Manufacturing DRC does not scale — `verify_clearance` is O(n²) pure Python

**Provenance: commit=UNKNOWN dirty=UNKNOWN** -- backfilled prior to the provenance gate's introduction (2026-07-26); no self-declared commit exists in this file's own content and none was fabricated. See .evidence-provenance-allowlist.

**Date:** 2026-07-26
**Severity:** high — makes `route_pcb()` unusable when the stage is enabled
**Status:** stage default reverted to off, now switchable and documented

## What happened

The manufacturing DRC stage was wired into `route_pcb()` on 2026-07-25 after
it was found never to have run (`2026-07-25-manufacturing-drc-crash-swallow.md`).
The first full routing run with it enabled, on the current board:

| | |
|---|---|
| Elapsed | **27 minutes, did not finish** |
| CPU | 98% sustained |
| RSS | **9.2 GB**, stable (not leaking) |
| Board | 149 footprints, ~3,265 emitted segments, 98 zones |
| Routing itself | completed — 65 nets routed, 19 failed |

Routing finished in the normal ~2 minutes. The remaining 25 minutes were
entirely inside Stage 5.

## Diagnosis

A stack sample (`sample 91902 5`) of the live process showed the hot path is
**pure CPython interpreter work**:

```
_PyEval_EvalFrameDefault
PyNumber_TrueDivide
_PyObject_GC_New
float_dealloc
tupledealloc
_Py_dict_lookup
pymalloc_alloc
```

No numpy, no Rust, no `temper_geometry`/`temper_drc_rs` in the hot frames —
they appear only as loaded modules. Heavy float and tuple
allocation/deallocation with division is the signature of a **pairwise
geometric distance loop written in interpreted Python**.

That matches `router_v6/clearance_check.py`, which computes clearance via
`_point_to_segment_dist` and `_segment_to_segment_dist` over conductor pairs.
With 3,265 segments the pair count is ~5.3 M before zone geometry is
considered at all, and each pair allocates tuples and floats.

**This was never discovered because the stage had never executed.** The module
is 498 lines with 17 test files exercising it — all on small fixtures.

## Why the default was reverted

Enabling the stage by default made every call to `route_pcb()` unusable. A
check that cannot complete is a worse failure than a check that is off, and
turning it on by default was a regression introduced by the fix for the
previous defect.

`enable_manufacturing_drc` is now a `route_pcb()` parameter defaulting to
`False`. The difference from the original state is that it is **switchable and
documented** rather than silently dead:

- before: hardcoded off inside the pipeline, no caller could enable it, nobody knew
- now: off by default, one keyword away, with the reason recorded here

## Also observed

`acid_trap` still raises on first contact with real router output:

```
acid_trap_detection.py:117
  path_coords = compiled_route.path.coordinates
AttributeError: 'RoutePath3D' object has no attribute 'coordinates'
```

It was written against an older `RoutePath` type. The `_run_one` fix from
2026-07-25 correctly caught and reported this rather than laundering it into
an empty "clean" report — the fix working as intended, on its first real
exposure.

## What has to happen before the stage can be turned back on

1. **`verify_clearance` needs to stop being O(n²) in Python.** Spatial indexing
   (grid or R-tree) to reduce candidate pairs, and/or moving the inner distance
   computation into `temper_geometry`/`temper_drc_rs`, both of which are
   already present and already used elsewhere in the router.
2. **`acid_trap_detection` must be updated for `RoutePath3D`.** Likely the same
   for the other checks — none has ever run on real output, so each should be
   assumed broken until it executes.
3. **A scale test.** Every one of the 17 clearance test files uses small
   fixtures. A test at real board size (thousands of segments) with a wall-time
   budget would have caught this the day the check was written.

Item 3 is the general lesson: the checks were thoroughly unit-tested and
completely unexercised at production scale.

## Reproduction

```bash
# with the stage on, this does not finish:
python -c "...route_pcb(stub, {}, design_rules=rules, enable_manufacturing_drc=True)"
# observe:
ps -o pid,etime,time,%cpu,rss -p <pid>
sample <pid> 5
```

---

## Attempted fixes, 2026-07-26 — both failed, both reverted

Two optimisation attempts, neither of which worked. Recorded because the
failure modes narrow the solution space considerably for whoever does this
next.

### Attempt 1 — route-level bounding-box prefilter

Reject a route pair without touching its segments when the gap between their
bounding boxes exceeds the required clearance plus half of each trace width.
Exact, not heuristic.

**Failed: it rejected almost nothing.** On a dense board a net that crosses
the board has a bounding box covering much of it, so route bboxes overlap
heavily even when the copper is nowhere near. Rejection has to happen per
segment, not per route.

### Attempt 2 — segment-level uniform spatial grid

Bucket every segment into a grid whose pitch is the search radius, then
compare only within cells.

**Failed on the clearance distribution.** The required clearance is not
uniform:

| Net pair | F.Cu | In1.Cu |
|---|---|---|
| `SPI_CLK` ↔ `SPI_MOSI` | 0.127 mm | 0.127 mm |
| `AC_L` ↔ `PWR_RTN` | **14.0 mm** | 4.2 mm |
| `HV_BUS` ↔ `GND` | **14.0 mm** | 4.2 mm |

A single grid must be sized for the 14 mm worst case, which puts roughly 138
items in every cell on this board and reinstates the quadratic behaviour for
the ~99% of pairs that only need 0.127 mm. Measured 14 GB RSS and no
completion.

The memory blow-up specifically was the pair-dedup `seen` set — ~2 M tuples.
It is unnecessary: the accumulator takes a minimum, so comparing a pair twice
is idempotent. **Drop the dedup set.**

### Attempt 3 — two-tier sweep (fine pass + asymmetric HV pass)

Fine sweep at 0.127 mm for the common case; a second sweep seeded only from
HV segments at the 14 mm radius, queried by everything else.

**Correct in principle, but the implementation broke 52 tests** and was
reverted. The idea is sound and is the recommended direction; the difficulty
is preserving exact parity with the existing per-route accumulation semantics
(per-layer minima, via-to-trace but not via-to-via, trace-width edge
distances) while restructuring from route-pairs to segment-pairs.

## Recommendation

**Do this in Rust, in `temper-drc-rs`, not in Python.** The reasoning has
changed since the first assessment:

- The algorithmic fix is not a small local edit. It requires restructuring
  the accumulation from route-pairs to segment-pairs while preserving several
  subtle behaviours, and the two-tier radius split is essential rather than
  optional.
- If the structure has to be rewritten anyway, the constant factor may as well
  come along. `temper-drc-rs` already exists, already has geometry primitives,
  and is already a pyo3 boundary the router uses.
- Correctness parity must be demonstrated against the current implementation
  on the existing 17 test files plus a real board, whichever language it is
  written in. That differential harness is the actual deliverable and is
  language-independent.

Whoever picks this up: the fine/coarse radius split and dropping the dedup set
are the two load-bearing insights. The 14 mm HV requirement against a 0.127 mm
default is what makes a single-radius spatial index useless here.

## Current state

`clearance_check.py` is unchanged from before these attempts — 160 tests pass.
`enable_manufacturing_drc` remains a `route_pcb()` parameter defaulting to
`False`. The stage is still unusable on a real board.

---

## Rust port attempt — blocked before it could be evaluated (2026-07-26)

A Rust implementation was written to `packages/temper-drc-rs/src/router_clearance.rs`
(357 lines) along with the two things that actually matter: a differential
parity harness (`tests/router_v6/test_clearance_check_rust_parity.py`, 458
lines) and a benchmark (`scripts/bench_clearance_rust_vs_python.py`, 261
lines).

**None of it could be validated, because `temper-drc-rs` does not build.**

```
ld: symbol(s) not found for architecture arm64
error: could not compile `temper-drc-rs` (lib)
```

**Control run: the crate fails identically when completely unmodified** on the
current branch. This is pre-existing and unrelated to the port. The crate does
have a `.cargo/config.toml` — the same mechanism that lets `temper-geometry`
and `temper-dsn` link their pyo3 `extension-module` cdylibs — so the cause is
something else and needs its own investigation.

**Consequence:** the recommendation to move this check to Rust is now blocked
on a build problem, not a design one. Fixing the crate build is a prerequisite
for the port, and is worth doing regardless: `temper-drc-rs` holds the
registered `IsolationCheck`, `IsolationBarrierCheck` and `IsolationSlotCheck`
rules, so a crate that cannot compile means those safety rules cannot run
either.

The parity harness and benchmark are the durable artefacts here and should
survive whatever the eventual implementation language is. They were the stated
deliverable precisely because they outlive the attempt.

**Status unchanged:** `clearance_check.py` remains the only working
implementation, `enable_manufacturing_drc` stays `False` by default, and the
stage is still unusable on a real board.
