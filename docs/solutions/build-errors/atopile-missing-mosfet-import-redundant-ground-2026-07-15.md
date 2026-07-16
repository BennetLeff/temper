---
title: "Atopile build broken by missing MOSFET_N import and redundant ground re-merges"
module: elec
date: "2026-07-15"
problem_type: build_error
component: tooling
severity: critical
symptoms:
  - "KeyError: power_in.q_relay_drv.S not found (6 cascading KeyErrors)"
  - "Error: source and target separately defined values for attribute 'required' (3 conflicts in main.ato)"
  - "ato build fails entirely; netlist not regenerated since original working-tree build"
root_cause: missing_import
resolution_type: code_fix
tags:
  - atopile
  - build
  - import
  - ground
  - required
---

# Atopile build broken by missing MOSFET_N import and redundant ground re-merges

## Problem

`ato build src/main.ato:Top` produced 9 errors (6 KeyErrors + 3 attribute conflicts). These were two independent bugs in `elec/src/modules.ato` and `elec/src/main.ato`, not a cascade. The build had never succeeded in the committed state -- the checked-in `elec/build/default.net` was produced from an uncommitted working tree.

## Symptoms

- **6 KeyErrors**: `power_in.q_relay_drv.G`, `.D`, `.S` all unresolved -- cascading from a single missing import.
- **3 attribute conflicts**: `main.ato` lines 226, 250, 310 each erroring "The source and target separately defined values for the attribute 'required'" with both source and target pointing to `modules.ato:363`.

## What Didn't Work

- **Commenting out `required` declarations.** Tried removing `.required = true` from `ac_l`, `ac_n`, `pe` in `PowerInput`. This exposed the second bug (missing import) but broke the first one -- they were independent, not masking each other.

## Solution

Two 2-line fixes, zero connectivity change:

**Fix 1 -- modules.ato**: Add the missing import.
```diff
 import Capacitor from "components.ato"
+import MOSFET_N from "components.ato"
```
The `q_relay_drv = new MOSFET_N` instantiation in `PowerInput` was added in commit `3814311b` but the import was never included.

**Fix 2 -- main.ato**: Remove three redundant ground re-merges.
```diff
-    power_in.power_15v.gnd ~ gnd
+    # power_in already ties power_15v.gnd ~ gnd internally; redundant

-    hb.power_3v3.gnd ~ gnd
+    # hb already ties power_3v3.gnd ~ gnd internally; redundant

-    safety.ntc_sense.reference ~ gnd
+    # safety already ties ntc_sense.reference ~ gnd internally; redundant
```
Atopile 0.2 rejects merging a net with itself when the net carries an attribute assignment. `ac_n.required = true` (modules.ato:363) joins the ground supernet at line 223, making subsequent re-connections of `gnd` through different paths illegal. The design's own comments already documented the rule ("connect the shared ground once", main.ato:235) -- these three lines violated it.

## Why This Works

The missing import is straightforward. The ground re-merges fail because atopile treats `~ gnd` with an attribute-bearing signal (`ac_n.required`) as an attribute assignment on the merged net. Re-merging the same net through a different path creates a duplicate attribute assignment, which atopile 0.2 rejects. Removing the redundant connections leaves exactly one path per ground node -- the correct topology.

## Prevention

- **Verify `ato build` in CI.** The build was broken in committed state because CI never ran it. `python-tests.yml` already has `make netlist` in the `test` job -- this catches the error now.
- **Don't re-connect shared grounds.** When every module internally ties its local `gnd` to the top-level `gnd`, main.ato should not redundantly re-state those connections. The convention already existed in the comments; the 3 violating lines were the exception.

## Related

- `elec/src/modules.ato` -- PowerInput module (line 353)
- `elec/src/main.ato` -- top-level sheet (lines 226, 235, 250, 310)
