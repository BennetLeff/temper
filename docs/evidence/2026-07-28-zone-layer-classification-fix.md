# Two zone/layer classification bugs fixed: a one-char substring match and a hardcoded netclass list

provenance: commit=fed05e82b45c7612a2f1e636b007511e7deda8c1 dirty=true

**Date:** 2026-07-28
**Base commit:** `fed05e82` (`docs/methodology-loop-discipline`) -- "merge:
barrier-constrained placement is INFEASIBLE -- and it is a BOM problem"
**Scope:** two live classification bugs in the placer/router that between
them cost the router both outer copper layers; extending
`scripts/check_net_classification.py` to catch the first bug's shape;
measuring the routing effect against the harness in the task brief.

## FALSIFIER -- stated up front, per instructions

> *"Fixing the layer-classification substring bug returns the outer layers
> to the routing space and raises completion above 38.54%. If completion
> does not move, the layer set was never the binding constraint and that
> is the finding."*

**The falsifier did NOT fire.** Completion is **38.54% (59/96 unrouted)**
before and after both fixes, bit-for-bit identical, reproduced N=2 each.
This is reported as a genuine negative result, not a failure to find an
effect -- see "Why the falsifier didn't fire" below for the mechanism,
which is fully explained and does not contradict the prior pour-audit
finding (`docs/evidence/2026-07-28-pour-strategy-audit.md`) that pours
were not the binding constraint either. Both audits now agree: **the
classifier bug and the pour-deletion question are both real, both fixed
where fixable, and neither moves this number on the currently-committed
board**, because the layers are legitimately classified `"plane"` today
by zones that are not part of either bug.

## Bug 1 -- a one-character substring match excludes an entire copper layer

`packages/temper-placer/src/temper_placer/io/_parse_board.py:132-137`
(pre-fix):

```python
is_power = (
    "GND" in zone.netName
    or "VCC" in zone.netName
    or "+" in zone.netName
    or "PWR" in zone.netName
)
```

`"+" in netName` matches `+3V3`, `+15V`, `+15V_LS` (all `Power` class, per
`TEMPER_NET_ASSIGNMENTS`). A single matching zone on a layer sets
`plane_assignments[layer]`, and `_extract_stackup()` then marks that
*entire physical layer* `"plane"` -- `routing_space.py:85` excludes any
non-`"signal"`/`"mixed"` layer from the router's grid entirely. The old
test was also case-sensitive (missed lowercase `vcc`) and unanchored
(`"GND" in "CGND"` incorrectly matched a distinct net, chassis ground, not
literal `GND`).

### Fix

Added `_is_plane_required_net()` in `_parse_board.py`: SSOT-first (a net's
class's `routing_strategy == "plane_required"`, from
`TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` in `core/design_rules.py` --
today only `ACMains`/`HighVoltage`), falling back to a word-boundary
anchored `GND`/`VCC`/`PWR` regex (never a bare `in`) for nets absent from
the per-net assignment table. This is the same SSOT field Bug 2's fix
(below) drives zone-*generation* eligibility from, so the two decisions
can't independently drift again.

Verified directly:

```
+3V3            -> False   (was True -- the bug)
vcc             -> False   (was False by case-sensitivity accident; now
                             correctly False by design)
+15V, +15V_LS   -> False   (was True -- the bug)
PWR_RTN         -> False   (was True -- GND is not plane_required; see
                             "why the falsifier didn't fire")
CGND            -> False   (was True -- false collision with "GND"; now
                             correctly excluded via anchoring)
SW_NODE, DC_BUS_RTN -> True   (HighVoltage, correctly plane_required)
ac_l, ac_n          -> True   (ACMains, correctly plane_required)
+340V_BUS           -> True   (HighVoltage, correctly plane_required --
                                matched via SSOT even though it never
                                matched the old substring test at all)
```

## Bug 2 -- the pour generator ignores the project's own declared intent

`_zone_layers_for_net()` (`packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py:420-428`,
pre-fix) hardcoded five zone-eligible net classes:

```python
nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
if nc in ("GND", "Power", "GateDrive", "HighVoltage", "ACMains"):
    return ["F.Cu", "B.Cu"]
return []
```

`TEMPER_NET_CLASSES` (`core/design_rules.py`) declares `routing_strategy`
per class; only `ACMains`/`HighVoltage` set it to `"plane_required"`.
`Power`/`GateDrive`/`GND` never asked for automatic zone treatment; the
emitter's own unsynchronized list gave it to them anyway. This is why
`+3V3`/`vcc`/`+15V`/`+15V_LS`/`V_BUS_SENSE` (Power) and
`GATE_HS`/`GATE_LS`/`PWM_HS`/`PWM_LS` (GateDrive) carry pours today with
no netclass-metadata justification (`docs/evidence/2026-07-28-pour-strategy-audit.md`
Task 0/1).

### Fix

`_zone_layers_for_net()` now checks
`TEMPER_NET_CLASSES.get(nc).routing_strategy == "plane_required"` instead
of the hardcoded tuple. Also de-duplicated a third, independent copy of
the same hardcoded list in `_stitch_isolated_pads()` (it now delegates to
`_zone_layers_for_net()` rather than repeating the eligibility check) --
three hand-maintained copies of "which classes get zone treatment" in one
file is exactly the class of drift this fix closes, and leaving two of
the three unfixed would have been an incomplete fix in its own right.
`_CONTINUITY_EXEMPT_CLASSES` (a separate, still-hardcoded set controlling
*clustering* behavior for nets that DO get zones) is left as-is with a
comment noting `"GND"` is currently dormant there (unreachable, since GND
no longer reaches that check) rather than wrong -- it would reactivate
immediately if GND's `routing_strategy` is ever set to `"plane_required"`.

**Important scope note:** this fix changes the *generator*, which only
affects zones written into freshly `route_pcb(enable_zone_pours=True)`-
regenerated output. It does **not** retroactively change
`pcb/temper.kicad_pcb`'s 96 already-committed zones (confirmed: `git
status`/`check_copper_net_consistency` show the board file untouched, 96
zones, byte-identical, throughout this work). Per the pour audit, the
committed zones are a *snapshot* of a past generator run; this fix is what
stops the *next* commit from re-baking the same over-broad pour set, not
a change to today's board.

## Why the falsifier didn't fire

The measurement harness routes directly from `pcb/temper.kicad_pcb`
(`route_pcb(stub, {}, ...)` with empty `placements` reads the committed
file as-is; Bug 2's generator fix only affects zones *written into
output*, not the stackup/plane classification computed from the *input*
board's existing zones). So Bug 1's fix is the only one that could move
this specific measurement, and it changes `_is_power` for exactly the
nets shown above.

`F.Cu`/`B.Cu` were "plane" before the fix because `PWR_RTN` (`"PWR"`
substring match -- a true, if SSOT-inconsistent, match) and
`+3V3`/`+15V`/`+15V_LS` (the `"+"` bug) all had zones on both outer layers.
After the fix, `PWR_RTN` no longer flags "plane" (GND is not
`plane_required`) and the Power-class false positives are gone -- **but
`SW_NODE`/`DC_BUS_RTN` (HighVoltage) and `ac_l`/`ac_n` (ACMains) zones are
also present on both `F.Cu` and `B.Cu`** (every cluster is mirrored across
both outer layers, per the pour audit's Task 1 zone census), and these
**are** legitimately `plane_required` -- they never matched the old buggy
substring test at all (none of the four contain `GND`/`VCC`/`+`/`PWR`),
but they correctly flag `is_power` under the fixed, SSOT-driven check.
**The layers were "plane" for the wrong reason before the fix, and are
"plane" for the right reason after it** -- same physical layers excluded
from the routing grid either way, because at least one genuinely
plane-required zone remains on each outer layer regardless of which
classifier bug is fixed. This is consistent with, and now doubly
confirms, the pour audit's finding that "the pours that are electrically
justified to keep... are exactly the ones triggering the layer-blocking
heuristic" -- extended here to cover the classifier side, not just the
zone-deletion side.

## Gate coverage: why `check_net_classification.py` didn't catch Bug 1, and the fix

**It is not a file-scoping gap.** `_parse_board.py` is under
`packages/temper-placer/src/temper_placer/**/*.py`, already a scan
target, and the AST detector's "Case 1: direct literal string compared
with `in`" structurally matches each of the four `Compare(in)` nodes in
the original code (confirmed by re-running the gate against a temporary
checkout of the pre-fix file -- see below). **It is a vocabulary-scoping
gap, by original design.** `SAFETY_VOCAB` was deliberately restricted to
the HV/SELV mains-adjacent boundary (per its own docstring: *"GND/VCC/VDD/
POWER-style low-voltage-domain checks are out of scope... the defect
class is the HV/SELV boundary specifically"*). Bug 1's classification
question -- "does this net's copper make its layer non-routable" -- is a
different question from "is this net HV or SELV", sharing only the
identical unanchored-`Compare(in)` AST shape, not the domain. The
original scoping decision was reasoned but, as of this bug, proven too
narrow.

### Extension made

`GND`, `VCC`, `PWR`, and the literal `"+"` were added to `SAFETY_VOCAB`
in `scripts/check_net_classification.py`, with the module docstring
updated to record this as a documented "FOURTH INSTANCE" scope
broadening (not a silent policy reversal). `VDD`/`POWER` were
deliberately left out for now -- no confirmed instance has used them yet
as a bare `Compare(in)` call site; per the best-practices doc's own
guidance, add them the next time one does rather than guessing ahead of
evidence.

### Verified the extension actually would have caught this instance

Checked out the pre-fix `_parse_board.py` temporarily (via `git show
HEAD~1:...` into a scratch copy, never touching the committed history)
and re-ran the extended gate against it:

```
VIOLATION _parse_board.py:133 in _extract_stackup -- ['GND']
VIOLATION _parse_board.py:134 in _extract_stackup -- ['VCC']
VIOLATION _parse_board.py:135 in _extract_stackup -- ['+']
VIOLATION _parse_board.py:136 in _extract_stackup -- ['PWR']
```

All four lines, including the exact `"+"` line responsible for the bug,
flagged as violations. Restored the fixed file immediately after
(confirmed via `git diff` showing zero changes to the fixed version).

### The extension surfaced 5 more, real, previously-unfixed sibling instances

Re-running the widened gate against the full repo (not just the one
file) found **8 new violations** beyond Bug 1 -- the identical defect
shape, in files that had *already been partially fixed* for HV/gate-drive
keywords in the 2026-07-27 sweep but left bare for GND/VCC/POWER/`+`:

| File | Function | Bare keywords | Disposition |
|---|---|---|---|
| `_constraint_types/config.py:443,446` | `get_net_class` | GND, VCC (+VDD/+3V3/+5V/+15V) | **Fixed** -- anchored; HV/BUS branch just below it was already anchored |
| `router_v6/clearance_check.py:810,812` | `_classify_net_class` | GND/VSS/PGND/CGND/AGND, VCC/VDD/+3V3/+5V/+12V/+15V/POWER | **Fixed** -- anchored; HV branch (`_is_hv_keyword_match`) was already anchored |
| `router_v6/routing_demand.py:94` | `estimate_routing_demand` | GND/VCC/VDD/VSS/+/- | **Fixed** -- anchored; bare `"+"/"-"` matched almost every net (hyphenated pin suffixes like `-p2`) |
| `router_v6/trace_width_assignment.py:145` | `_determine_trace_width` | GND/VCC/VDD/VSS/+/POWER | **Fixed** -- anchored via the file's own existing `_kw_boundary_match` helper (HV/gate-drive branches already used it) |
| `core/design_rules.py:201` | `get_rules_for_net` | `"GND" in self.net_classes` | **Allowlisted** -- dict-key membership (class-name-keyed dict), not a net-name substring test; the real classification is delegated one line above to the already-fixed `net_classification.is_ground_net` |
| `tests/requirements/validators/markings.py:182` | `check_polarity_markings` | `+`/`-`/ANODE/CATHODE/... | **Allowlisted** -- matches free-form silkscreen label text for a polarity symbol, not a net name; same shape as the pre-existing `check_hv_warning_present` allowlist entry |

`heuristics/structural.py`'s `_classify_connector_purpose` and
`router_v6/_astar_ordering.py`'s `cluster_sort_key` also newly matched the
widened vocabulary but needed no new action -- both were already covered
by pre-existing, justified allowlist entries from the 2026-07-27 sweep.

**Final gate state:** 478 `Compare(in)` call sites discovered (413
resolved, 65 unresolved -- all previously-known unresolved sites, not
newly introduced), 17 vocabulary-matching candidates, **17 allowlisted, 0
violations**. `check_net_classification.py` exits 0.

## Measurement

Harness exactly as specified in the task brief, against
`pcb/temper.kicad_pcb`, N=2 each:

| State | Completion | Unrouted |
|---|---:|---:|
| Before (pre-fix, `HEAD~1` checkout of the two files, run 1) | 38.54% | 59/96 |
| Before (run 2) | 38.54% | 59/96 |
| After (both fixes applied, run 1) | 38.54% | 59/96 |
| After (run 2) | 38.54% | 59/96 |

Bit-for-bit identical across all four runs. Matches the documented
37/96 = 38.5% baseline and the pour audit's own reproduction.

## Hard rules compliance

- **No pours deleted.** `pcb/temper.kicad_pcb` is untouched throughout
  this work (`git status`/`git diff --stat pcb/temper.kicad_pcb` empty;
  `check_copper_net_consistency` confirms 96 zones, byte-identical,
  before and after). Both fixes are to classification *logic*
  (`_parse_board.py`, `_adapter_convert.py`), never to board geometry.
- **No `git stash` used.** Before/after measurements used `git checkout
  HEAD~1 -- <2 files>` / `git checkout HEAD -- <2 files>` (targeted,
  reversible, no shared stash ref touched).
- **No `run_in_background`/Monitor waiting requested by this agent.**
  (Two long-running `pytest` invocations were auto-moved to background by
  the harness after exceeding its default/explicit timeout on this
  machine; both were killed immediately without reading their output or
  waiting on their completion notifications, and the same test scope was
  re-run to completion in the foreground with `-n 4 --dist loadgroup`
  before being trusted.)
- Committed after each meaningful step (Bug 1 + Bug 2 code fix; gate
  extension + 5 sibling fixes + test updates).
- No `elec/build/` artifacts committed (`make netlist` output is
  gitignored, confirmed absent from `git status`).

## Verification

- **10/10 gates green:** `check_domain_partition` (0 crossings/breaches/
  chain defects, 54 nets/2 domains/10 isolators/2 protective-impedance
  chains), `capacity_budget_gate` (0 defects), `mpn_fabrication_gate` (0
  new violations, 118 parts), `check_derived_doc_drift` (132 fields across
  3 docs), `check_copper_net_consistency` (0 violations, 2,482 copper
  items + 510 pads), `check_rust_drc_presence`, `check_undeclared_imports`
  (3,208 imports), `check_stale_extensions` (9/10 fresh, 1 optional
  accelerator not built locally -- expected, matches prior audits),
  `check_net_classification` (478 call sites, 17/17 allowlisted, 0
  violations), `check_pll_range_consistency` (4/4 agree).
- **Expected non-green gates, as documented:** `check_isolation_keepout`
  exits 3 (no physical keepout zone placed yet -- pre-existing, unrelated
  to this fix); `check_measurement_provenance` exits 5 (malformed
  provenance value on an unrelated dataset record -- pre-existing).
- `make netlist` passes.
- `uv run --no-sync python -m pytest elec/validation -q` -- **30/30
  passed**.
- Stackup suites: `test_stackup_parsing.py`, `core/test_stackup.py`,
  `manufacturing/test_stackup_validator.py` -- **36/36 passed**.
- Router regression: `tests/router_v6/` (2,229 collected, excluding the
  pre-existing-broken `test_cp_sat_bench.py` collection error and 4
  pre-existing `test_astar_3d_production_scale_spike.py` production
  failures, both confirmed present identically before AND after this
  fix via temporary `HEAD~1` checkout) -- **2,178 passed, 15 skipped, 23
  xfailed**. 10 additional failures in this run were also confirmed
  pre-existing (identical failure set before/after, same technique):
  `test_dfm_interaction.py` (x2), `test_finish_board_gate.py`,
  `test_grid_prep_pbt.py`, `test_los_numba_correctness.py`,
  `test_via_insertion_anti_false_zero.py`,
  `test_via_layer_properties_pbt.py` (x2), `test_wave2_structural_small.py`,
  `test_temper_production_board_routing.py`.
- `tests/router_v6/test_adapter.py` -- **70/70 passed** after updating 10
  tests whose assertions encoded the pre-fix (buggy) hardcoded-list
  behavior (`_zone_layers_for_net`/cross-class-clearance/priority-
  inversion/stitch-pad fixtures using now-ineligible `GND`/`GateDrive`/
  `Power`-class net names); each rewritten test's docstring documents
  what changed and why, preserving original test intent with
  still-eligible net names (`ACMains`/`HighVoltage`) where the original
  intent required two zone-eligible classes.
- `tests/constraint_types/`, `test_clearance_check.py`,
  `test_routing_demand.py`, `test_trace_width_assignment.py` -- **172/172
  passed** (covers the 5 sibling-fix files).

## UNVERIFIED

- Whether relocating the genuinely plane-required `HighVoltage`/`ACMains`
  zones to an inner layer (per the pour audit's Task 3 stackup
  recommendation) would change this measurement was not tested here --
  out of scope for this pass, which fixes classification logic only and
  does not touch board geometry or the stackup recommendation's
  implementation.
- Whether `GND`'s `routing_strategy` should be set to `"plane_required"`
  (given `PWR_RTN`/the pour audit's "KEEP, SHRINK, RELOCATE" verdict for
  it) is a design decision this pass does not make -- the fix drives
  eligibility from whatever `routing_strategy` says today, correctly, but
  does not itself decide what `routing_strategy` *should* say for GND.
- `VDD`/`POWER` were not added to `check_net_classification.py`'s
  vocabulary -- no confirmed live instance uses them as a bare
  `Compare(in)` literal yet; flagged for the next occurrence per the
  gate's own "ask where else this shape occurs" discipline.
