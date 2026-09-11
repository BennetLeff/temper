---
title: "Stale KiCad zone fills can change newly assigned via nets"
date: 2026-09-10
category: architecture-patterns
module: zapote-rtd
problem_type: logic_error
component: tooling
symptoms:
  - "Explicit ground vias become supply vias after native refill and save"
  - "A pre-refill net census passes while the saved board has different nets"
root_cause: data_integrity
resolution_type: code_fix
severity: high
framework_version: "KiCad 10.0.4"
tags: [kicad, zone-fill, via-net, pcbnew, agent-harness, native-adapter]
---

# Stale KiCad zone fills can change newly assigned via nets

## Problem

Appending agent-authored ground stitching vias beneath previously filled supply
zones could change their net assignments during native KiCad refill/save. This
breaks the editing harness contract even when the authored operation and its
immediate saved net census are correct.

The fix is verified in the working branch; this document makes no merge claim.

## Symptoms

On a prepared RTD board fixture, all seven added vias were ground immediately
after replay. After native refill/save, five belonged to +3V3 or RTD_AVDD when
the cache-invalidation fix was removed. With the fix present, all seven stayed
ground. The board owner's original incident affected three vias; the independent
reproduction used a separately prepared baseline and is not that same capture.

## What Didn't Work

Explicitly setting each new object's net, using the low-level native serializer,
and checking the pre-refill result were insufficient. A clean-looking authored
operation is not proof that a later native reload/refill preserves its intent.

## Solution

Discard existing filled-zone polygons before modifying copper:

```python
for zone in board.Zones():
    zone.UnFill()
```

The working implementation does this in
`replace_copper` in `harness-lab/block_native.py` before replacement and in
`_replay` in `zapote/rtd/apply_routes.py` on the append destination before copying
new copper. Then let KiCad refill zones and inspect the saved native result.
Clearing the scratch source alone does not clear the append destination's cache.

## Why This Works

Filled polygons describe the old copper arrangement. Keeping them through an
edit permits the native connectivity/refill path to use stale geometry when
resolving the new vias. The independent experiment changed only the two
invalidation loops: the same frozen baseline and seven explicit via locations
failed without them and retained the intended nets with them. This establishes
the relevant cache dependency without claiming an audit of KiCad internals.

Frozen inputs, both output boards, native reports, adapter sources and hashes
are in `zapote/rtd/unit/evidence/root-cache-regression-01/receipt.json`.

## Prevention

Test edits against an already filled board, including a new via beneath a
different net's old pour. Compare object net identities after native refill/save
with the authored operation and source connectivity. Keep the legacy mutation
as a negative control; an empty-board serialization test cannot expose this
failure. Native DRC remains necessary, but it does not replace intent equality.

The reproduction is adapter evidence, not standalone RTD electrical acceptance
or physical hardware qualification.

## Related Issues

The earlier [zone geometry regression](zone-pour-bounding-box-shorting-regression-2026-07-21.md)
concerns oversized authored zone outlines. Here the defect is stale derived
fill surviving an edit, even with unchanged authored zone outlines.
