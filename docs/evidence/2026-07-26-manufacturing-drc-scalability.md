# Manufacturing DRC does not scale — `verify_clearance` is O(n²) pure Python

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
