<!-- provenance: commit=92a5d41a75425b5d35898381c2932cc7b98a4d6b dirty=false -->

# Router-free R8 producer — placement-derived zones, harness net-class wiring, and the honest coverage boundary

**Date:** 2026-08-07
**Task:** `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §4 recommended
extending the R2 board producer (`tools/wasm/r2_serialize_board.py`) to
re-derive zone/clearance geometry from the committed placement without
invoking `route_pcb()`, since both `route_pcb()` code paths fail (issue
#871's OOM, and a newly-exposed O(n²) skeleton-connectivity blowup) and R8's
literal text — "the board the tier checks is regenerated from the committed
placement, so the input changes when the harness changes" — does not
actually require a *routed* board, only a *re-derived* one. This document
implements that producer, measures it against the real committed board, and
states exactly which of the 27 registered DRC/ERC/EMC/safety/placement/
routing rule kernels (`packages/temper-drc-rs/src/rules/mod.rs`'s
`create_default_registry()`) it makes non-vacuous and which it does not.
**Does not touch `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`,
or `elec/`. Does not attempt to fix #871.**

**Bottom line up front:**

1. **R8 is partially met.** The producer now regenerates zone/pour geometry
   and net-class metadata (creepage, voltage, safety category, routing
   strategy, per-net class assignment) from the committed placement plus the
   harness's net-class SSOT (`temper_placer.core.design_rules`), without
   `route_pcb()`. Verified deterministic (byte-identical across independent
   process runs) and verified sensitive to both a placement change and a
   harness-only change (same `pcb/temper.kicad_pcb` bytes, different output).
2. **Per kernel, measured against the real board: 6 of 27 kernels are now
   genuinely non-vacuous** (fire real, non-zero findings) purely from
   placement + harness input, two of which (`drc_zone_containment`,
   `safety_hv_lv_separation`) were previously *always* vacuous regardless of
   routing, for reasons unrelated to #871 — this change found and fixed
   that separately. **9 kernels structurally require routed traces/vias**
   and remain unreachable without `route_pcb()`. **1 kernel is half-blocked**
   on `route_pcb()` and half already placement-derivable. **7 kernels are
   placement-derivable in principle but currently vacuous for a third,
   distinct reason** — a keyword-vocabulary or missing-field gap in the
   harness's own classification tables, not routing, and not fixed here
   (see §6's honest boundary). **4 kernels are structurally reachable and
   report zero findings**, plausibly a clean board rather than a gap.
3. **The whole point of "regenerate, not re-serialize" is demonstrated with
   real numbers, not just a design argument**: the placement-derived board
   has 32 zones and the committed (already-routed) board has 96; running
   both through the actual DRC engine produces *different* findings
   (`drc_zone_containment`: 3 vs 9; `routing_copper_pullback`: 28 vs 42) —
   not just different bytes.

---

## 1. What R8 actually requires, from the kernels' own inputs

The task's method: read every rule kernel's `check(&self, board: &BoardState,
constraints: &ConstraintSet)` body in `packages/temper-drc-rs/src/rules/`
and record which `BoardState`/`ConstraintSet` fields it actually reads —
not assumed from the rule's family name. All 27 rules registered by
`create_default_registry()` (`rules/mod.rs:230-259`) were read in full.

**Finding: routing-family naming is not a reliable proxy for a traces/vias
dependency.** Several rules under the `routing_` prefix read only
`board.zones` (already-poured copper geometry, not traces) or only
`board.electrical_components`:

- `routing_copper_pullback` (`rules/routing/copper_pullback.rs`) — iterates
  `board.zones` only; no `board.traces`/`board.vias` reference at all.
- `routing_tht_thermal_relief` (`rules/routing/tht_thermal_relief.rs`) —
  iterates `board.electrical_components` only.
- `routing_isolation_slot` (`rules/routing/isolation_slot.rs`) — matches
  `constraints.zones` entries against `board.zones` polygons; no traces.
- `routing_isolation_barrier` (`rules/routing/isolation_barrier.rs`) — has
  *two* sub-checks, one over `board.traces` and one over `board.zones`; the
  zone half is placement-derivable, the trace half is not.

Conversely, `drc_via_spacing` and `placement_thermal_via_count` (not
`routing_`-prefixed) are fully gated on `board.vias`.

**Method note on `ConstraintSet`, a second, independent input surface.**
Several placement-derivable rules are keyed not on `board.zones`/
`board.electrical_components` directly but on `constraints.zones`/
`constraints.critical_loops`/`constraints.isolation_barriers` — a *separate*
schema (`packages/temper-drc-rs/src/constraints.rs`) that every producer in
this repo, including the one this task extends, has always emitted empty
(`"zones": [], "critical_loops": [], "isolation_barriers": []`, verbatim in
`build_constraints_dict` before this change). A rule reading `board.zones`
correctly (no traces needed) can still report zero findings forever if
`constraints.zones` never names it — a second, independent vacuity axis from
"does this need `route_pcb()`," and one this document tracks separately
(§4, §5) because conflating the two would misstate what routing actually
blocks.

The full per-rule table is §3.

---

## 2. The producer built

`tools/wasm/r2_serialize_board.py` (`build_board_dict`, `build_constraints_dict`)
now defaults to `zone_source="placement"` (was: always re-serialize
committed geometry verbatim, the gap the status audit identified). Three
independent pieces changed:

### 2.1 Zone/pour geometry re-derived from pad positions

`_zones_from_placement()` (line 493) groups pad positions by net
(`_pad_positions_by_net()`, line 463, from `ParseResult.pads` — a second
`parse_kicad_pcb(..., normalize=False)` call, since `ParsedPCB` from
`parse_kicad_pcb_v6` does not carry pads) and, for each net the harness
marks zone-eligible, calls the SAT router's *own* zone-emission functions:

- `_zone_layers_for_net()` / `_zone_params_for_net()`
  (`router_v6/_zone_pour_stitch.py`) — net-class eligibility
  (`routing_strategy == "plane_required"`) and margin/clearance lookup.
- `compute_zones_for_net()` (`router_v6/zone_emission.py`) — convex hull +
  hierarchical clustering over pad positions (shapely/scipy).

None of these four functions call `route_pcb()` or the CP-SAT/SAT solver —
confirmed by reading them, not assumed; they are pure geometry plus a dict
lookup into `TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS`
(`temper_placer.core.design_rules`). Reusing the production functions,
rather than reimplementing eligibility/clustering a second time, is what
keeps the producer's zones representative of what the router would actually
pour rather than an independent approximation.

`build_board_dict(..., zone_source="committed")` keeps the prior behaviour
(`_zones_from_parsed`, re-serializing `parsed.zones` verbatim) for
comparison/measurement — it does not satisfy R8 and is not the default.

### 2.2 Two adjacent gaps found and fixed while wiring this

Both were pre-existing, independent of routing, and made the corresponding
rule kernels vacuous on every prior producer run, not just this one:

**Net classification was never applied.** `parse_kicad_pcb_v6` calls
`parse_kicad_pcb(pcb_path, normalize=False)` internally with no
`design_rules` argument, so `_apply_safety_classifications`
(`temper_placer/io/_parse_nets.py`) — which reclassifies HV/AC-connected
components from the KiCad-literal `"Signal"` to `"HighVoltage"` — never
runs. Verified directly against the production board:

```
$ parsed = parse_kicad_pcb_v6('pcb/temper.kicad_pcb')
$ set(c.net_class for c in parsed.components)   # -> {'Signal'}
$ set(n.net_class for n in parsed.nets)         # -> {'Signal'}
```

Every component and every net showed up as class `"Signal"` regardless of
being tied to 240V mains or a 3.3V logic rail. `net_class_rules` (the K1
schema's per-class metadata dict) compounded this: it only ever filled
`trace_width_mm`/`clearance_mm` from the KiCad-declared block (which itself
only ever declares the one literal class `"Signal"`) and hardcoded
`creepage_mm`/`voltage_v`/`max_current_rating`/`safety_category`/
`required_layer`/`routing_strategy` to `None` — the exact fields
`safety_hv_lv_separation`, `safety_creepage`, `safety_isolation`, and the
zone-eligibility helpers above need.

Fixed (`_harness_component_safety_classes`, line 286; `net_classes`/
`net_class_rules` construction, lines 187-253): component-level
classification now mirrors `_apply_safety_classifications`'s severity rule
(HV > AC > LV, computed directly over `TEMPER_NET_ASSIGNMENTS`/
`TEMPER_NET_CLASSES` rather than the vestigial `parsed.design_rules`
extraction — `_extract_design_rules`'s own docstring: "Native netclass
extraction from KiCad PCB files is **vestigial**. The authoritative source
is `configs/netclass_rules.yaml`... injected into the pipeline by
`route_pcb()`" — exactly the call this task must not make); per-net class
name prefers `TEMPER_NET_ASSIGNMENTS` over the KiCad-declared literal; and
`net_class_rules` is now built from the full 11-class harness table
(`ACMains`, `HighVoltage`, `HighVoltageIsolated`, `GateDriveHV`,
`GateDriveSELV`, `HighCurrent`, `HighSpeed`, `FinePitch`, `Power`, `GND`,
`Signal`), union'd with any KiCad-declared class the harness doesn't know
about. Measured after the fix: `net classes: 11` (was 1) in
`r2_full_board_pass`'s own board summary.

**`ConstraintSet.zones` was always empty.** `drc_zone_containment`
(`rules/drc/zone_containment.rs`) reads `board.zones` (geometry) *and*
`constraints.zones` (which net classes are supposed to be contained in a
zone) — with the latter always `[]`, the rule's `matching_zones` was always
empty and it never checked a single component, regardless of whether
`board.zones` held real geometry. Fixed (`_zone_eligible_class_names()`,
line 591; `build_constraints_dict`, line 614): one `ZoneDefinition` per
harness zone-eligible class, named after the class itself
(`{"name": "HighVoltage", "net_classes": ["HighVoltage"]}`) — the same
classes `_zones_from_placement` already derives `board.zones` geometry for,
so the two inputs agree by construction rather than by coincidence.

**Deliberately not attempted**, and why, is §5.

---

## 3. Per-kernel classification (all 27 registered rules)

Measured columns are from `temper_drc_rs.run_drc(board_dict, constraints_dict)`
against the real board at this commit, `zone_source="placement"` (32 zones),
with the constraints fix from §2.2 applied.

| # | Rule | Category | Input needed | Measured violations | Status |
|---|---|---|---|---|---|
| 1 | `drc_clearance` | drc | components + net_class_rules | 90 | **Working** |
| 2 | `drc_component_overlap` | drc | components | 38 | **Working** |
| 3 | `drc_courtyard` | drc | components | 38 | **Working** |
| 4 | `drc_zone_containment` | drc | components + board.zones + constraints.zones | 3 | **Working (fixed §2.2)** |
| 5 | `routing_copper_pullback` | drc | board.zones only | 28 | **Working** |
| 6 | `safety_hv_lv_separation` | safety | components + net_class_rules | 94 | **Working (fixed §2.2)** |
| 7 | `erc_net_connectivity` | erc | nets | 0 | Reachable, plausibly clean |
| 8 | `erc_power_domain` | erc | nets | 0 | Reachable, plausibly clean |
| 9 | `erc_floating_pins` | erc | nets | 0 | Reachable, plausibly clean |
| 10 | `placement_wave_solder_keepout` | dfm | components | 0 | Reachable, plausibly clean |
| 11 | `emc_ground_plane` | emc | components + constraints.zones **role-keyword-matched** | 0 | Blocked — §6.1 |
| 12 | `emc_noise_coupling` | emc | components, net-class **role-keyword-matched** | 0 | Blocked — §6.1 |
| 13 | `safety_isolation` | safety | components with `safety_category=="iso"` | 0 | Blocked — §6.2 |
| 14 | `safety_creepage` | safety | components with `safety_category=="iso"` | 0 | Blocked — §6.2 |
| 15 | `routing_isolation_slot` | safety | constraints.zones **role-keyword-matched** + board.zones | 0 | Blocked — §6.1 |
| 16 | `emc_loop_area` | emc | constraints.critical_loops | 0 | Blocked — §6.3 |
| 17 | `routing_tht_thermal_relief` | dfm | components + net_class_rules.max_current_rating | 0 | Blocked — §6.4 |
| 18 | `routing_isolation_barrier` | safety | board.traces (half) + board.zones (half), gated on constraints.isolation_barriers | 0 | **Blocked — needs a routed board AND §6.3** |
| 19 | `drc_trace_clearance` | drc | board.traces | 3636 | **Needs routed board** |
| 20 | `drc_via_spacing` | drc | board.vias | 5 | **Needs routed board** |
| 21 | `placement_thermal_via_count` | drc | board.vias (routing artifact) + `power_dissipation_w` (see §6.5) | 0 | **Needs routed board** |
| 22 | `routing_parallel_run` | emc | board.traces | 0 | **Needs routed board** |
| 23 | `routing_stitching_via_density` | emc | board.vias | 0 | **Needs routed board** |
| 24 | `routing_power_pad_teardrop` | dfm | board.traces/vias | 0 | **Needs routed board** |
| 25 | `routing_partial_discharge` | safety | board.traces | 0 | **Needs routed board** |
| 26 | `routing_pad_entry_width` | dfm | board.traces | 0 | **Needs routed board** |
| 27 | `routing_split_plane_crossing` | emc | board.traces (gated) | 0 | **Needs routed board** |

**Totals: 6 working (2 fixed by this change) + 4 reachable-and-clean + 7
blocked-by-a-non-routing-gap + 1 half-blocked + 9 needs-routed-board = 27.**
9 of 27 (33%) are unreachable without `route_pcb()`. 17 of 27 (63%) need no
routed board at all — 6 fire real findings today, 4 more are structurally
ready and simply report a clean board, and 7 are gated on a harness-table
gap unrelated to routing (§6). Rows 19-27 (traces/vias) use the *committed*
copper regardless of `zone_source` — this producer does not and cannot
regenerate them.

---

## 4. Determinism verification

Two independent process-level runs of the producer against the real board
(`tools/wasm/r2_serialize_board.py --output ...`, default
`zone_source="placement"`):

```
Run 1: 301,579 bytes, sha256 258b4ba3d25fc1a10050a155162dff66e991176fcb8ec5053af0bda7e581d35f
Run 2: 301,579 bytes, sha256 d815f3d5d338138246b44f7173fb90e202a8b6fd5415bffafa85f511fcc98754
```

The two top-level hashes differ. Diffing the deserialized `BoardState`
field-by-field isolates the cause precisely: `width_mm`, `height_mm`,
`margin_mm`, `electrical_components`, `mechanical_components`,
`net_class_rules`, `traces`, `vias`, and **`zones`** are byte-identical
across both runs. Only `nets` (the top-level `Vec<Net>`) differs, and only
in *order* — sorted by name, the two runs' `nets` lists are set-equal:

```python
sorted(a["nets"], key=lambda n: n["name"]) == sorted(b["nets"], key=lambda n: n["name"])  # True
a["nets"] == b["nets"]                                                                     # False (order)
```

This is a **pre-existing, already-documented, out-of-scope** finding, not
introduced by this change: `test_real_board_traces_vias_zones_are_deterministic_across_parses`
(`packages/temper-placer/tests/scripts/test_r2_serialize_board.py`, landed
before this task) already records "`nets` is itself nondeterministic across
process-level re-parses of the real board (order depends on Rust `HashMap`
iteration inside `extract_nets_pure`/`build_netlist` in
`packages/temper-design-bundle/src/parse_engine.rs`... a pre-existing bug in
a different crate, outside this change's scope... fixing it here would be
scope creep." That reasoning applies identically here — the bug is upstream
of `_zones_from_placement`/`_harness_component_safety_classes`, in the
parser's own `parsed.nets` iteration order, not in anything this task added.

**Honest statement:** the fields this producer actually regenerates
(zones, net-class metadata, and the component-level classification
override) are verified byte-identical across independent runs. The
full-artifact top-level hash is not yet stable, purely because of this
pre-existing, separately-owned `nets`-ordering bug — not because of
anything R8-specific.

Automated coverage: `test_real_board_placement_zones_are_deterministic_across_parses`
(scoped to `zones`/`net_class_rules`, matching the pre-existing test's own
scoping rationale) — 22/22 tests pass in
`packages/temper-placer/tests/scripts/test_r2_serialize_board.py`.

---

## 5. Sensitivity verification — "the input changes when X changes"

### 5.1 Placement changes the output

Perturbing every pad on one zone-eligible net (`+15V_LS`) by +5mm/+5mm, in
memory, without touching `pcb/temper.kicad_pcb`:

```
zones before: 32 polygons
zones after:  32 polygons
zones before == zones after: False
```

Same zone *count* (the perturbation doesn't cross a clustering threshold),
different *geometry* — the convex hull moved. Automated:
`test_real_board_placement_zones_change_when_placement_changes`.

### 5.2 The harness changes the output — with a real, measured effect on findings

Monkeypatching `TEMPER_NET_CLASSES["HighVoltage"]` to raise its clearance by
3mm, in-process, with a byte-identical `pcb/temper.kicad_pcb` on disk:

```
                          before                                                              after
artifact sha256:  b680463471c7c768c0c05c0df3df4dece0fe261b47b35744c7a01b6af202305b  a700cd851071bf857f4a8d6775f4416c79ee77b768619c1e8d94f09836a8b680
zones == :                                                                          False
net_class_rules == :                                                                False
DRC violations:   3932                                                             5378
```

A pure harness edit (no board change) altered the produced artifact's hash
AND changed what the DRC engine actually finds on the same physical board —
the property R8 is protecting: a stale board silently outliving the tooling
that would have produced a different one. Automated:
`test_real_board_net_class_rules_change_when_harness_changes`.

### 5.3 Placement-derived vs. committed zones produce different findings, not just different bytes

Running the actual DRC engine (`temper_drc_rs.run_drc`) against both zone
sources for the same committed board:

| Rule | `zone_source="placement"` (32 zones) | `zone_source="committed"` (96 zones) |
|---|---|---|
| `drc_zone_containment` | 3 | 9 |
| `routing_copper_pullback` | 28 | 42 |
| all others | identical | identical |

This is the concrete proof that `zone_source="placement"` is *regenerating*
geometry, not merely reformatting `parsed.zones` under a different code
path that happens to produce the same numbers — the two paths disagree, and
disagree specifically on the zone-driven rules, exactly where a
re-derivation vs. a verbatim copy would be expected to diverge. Automated:
`test_real_board_placement_zones_differ_from_committed_zones`.

---

## 6. The honest coverage boundary — what this does NOT cover, and why

**Traces/vias (9 kernels, §3 rows 19-27, plus half of row 18): genuinely
requires a routed board.** Confirmed by reading every kernel's inputs, not
assumed. This producer reads `traces`/`vias` verbatim from the committed
copper (`_traces_from_parsed`/`_vias_from_parsed`, unchanged) — it cannot
regenerate them without `route_pcb()`, which is blocked by #871 (stripped-
copper path OOM) and the newly-exposed skeleton-connectivity blowup (direct
path), per the status audit this task is based on. **This is stated
directly, not implied**: a board regenerated by this producer is *not* a
substitute measurement for the routing-family kernels, and any future
verdict citing this producer's coverage must exclude them.

**Three further gaps, found while measuring §3, deliberately not fixed
here** — each would require inventing semantics the harness does not
declare, which risks being a wrong guess dressed up as coverage rather than
an honest gap:

### 6.1 Role-keyword vocabulary (`emc_ground_plane`, `emc_noise_coupling`, `routing_isolation_slot`)

These three rules classify a component or a `ConstraintSet.zones` entry by
matching English-language keywords against a name string — `"gnd"`/
`"ground"`/`"return"` (ground-plane role), `"power"`/`"clock"`/
`"switching"`/`"pwm"`/`"high_freq"` vs. `"analog"`/`"sensor"`/
`"small_signal"`/`"victim"` (noise-coupling aggressor/victim), `"slot"`/
`"isolation"` (isolation-slot role). None of the 11 classes in
`TEMPER_NET_CLASSES` are named with this vocabulary (`ACMains`,
`HighVoltage`, `HighVoltageIsolated`, `GateDriveHV`, `GateDriveSELV`,
`HighCurrent`, `HighSpeed`, `FinePitch`, `Power`, `GND`, `Signal`) — no
existing harness table maps a class or a component to one of these English
roles. Synthesizing that mapping here (e.g. deciding `GND` "is" a ground
zone, or that a `HighCurrent`-classed component "is" noisy) would be this
producer inventing a classification the codebase does not already assert
anywhere, not deriving one from an existing source of truth. Left
unpopulated; these three rules remain vacuous.

### 6.2 `safety_category == "iso"` is never declared (`safety_isolation`, `safety_creepage`)

Both rules gate on a component whose `net_class_rules[class].safety_category`
equals the literal string `"iso"`, or whose class name keyword-matches
`"iso"`/`"opto"`/`"coupler"`/`"isolator"`/`"transformer"`/`"adum"`/
`"dcdc"`/`"mev1"`. `TEMPER_NET_CLASSES`'s 11 classes declare
`safety_category` only as `"HV"`, `"AC"`, or `"LV"` — never `"iso"` — and
`_apply_safety_classifications`'s own severity model (which this producer's
`_harness_component_safety_classes` deliberately mirrors, §2.2) only ever
assigns components to `"HighVoltage"`, never introduces an isolation
category. The board's real isolation devices (optocouplers, the gate-drive
isolator) are presumably identifiable by refdes/footprint, not by net
class — but that mapping is not in `TEMPER_NET_CLASSES`/
`TEMPER_NET_ASSIGNMENTS` either, and guessing it (e.g. by footprint
substring) would be a materially different, unverified derivation.

### 6.3 `ConstraintSet.critical_loops`/`isolation_barriers` have no harness source (`emc_loop_area`, half of `routing_isolation_barrier`)

Neither field has an analogous SSOT table anywhere in
`temper_placer.core.design_rules` or elsewhere searched
(`ConstraintSet`/`isolation_barriers`/`critical_loops` grepped across
`packages/temper-placer/src` — every hit was an unrelated, differently-named
`ConstraintSet` type in the placer's own constraint-compiler code, not a
zones/loops/barriers table this producer could read). Left empty, as every
prior producer left them.

### 6.4 `max_current_rating` is never set (`routing_tht_thermal_relief`)

All 11 `TEMPER_NET_CLASSES` entries have `max_current_rating: None`.
`routing_tht_thermal_relief` requires `Some(rating) if rating <= 10.0` to
fire at all — with the field universally `None`, the rule cannot produce a
finding regardless of what this producer emits elsewhere. This one is
notably *not* about routing or about missing zone-eligibility data; it is
simply an unpopulated harness field, unrelated to this task's zone-geometry
scope, recorded here because it was discovered while measuring §3 rather
than filed separately.

### 6.5 `power_dissipation_w` is always `None` (`placement_thermal_via_count`)

This one compounds a routing dependency rather than substituting for it,
recorded for completeness: `placement_thermal_via_count` needs both
`board.vias` (a routing artifact this producer never regenerates -- §3 row
21 stays classified under "needs routed board" for that reason) *and*
`comp.power_dissipation_w`, which `build_board_dict`'s components loop
hardcodes to `None` for every component (line 178, pre-existing, untouched
by this change). Even with committed vias present (48 on the real board),
the rule's `Some(p) if p > 0.0 => p, _ => continue` guard skips every
component before it ever looks at a via. Fixing this would need a
per-component power-dissipation source (a BOM/thermal budget table) this
task did not go looking for -- out of scope for the same reason as §6.1-6.4.

**None of §6.1-6.5 is a routing gap.** Fixing them is a harness-data /
role-taxonomy question for `design_rules.py`, not a router or WASM-tier
question, and is out of this task's scope for the same reason #871 itself
is: this task's charter is to sidestep the router, not to redesign the
project's safety-classification vocabulary.

---

## 7. Verdict

**R8 is partially met.** The board the tier's rule kernels check is now,
by default, regenerated from the committed placement and the current
harness for the zone/pour-geometry and net-class-metadata portion of the
board — verified deterministic, verified sensitive to both a placement-only
change and a harness-only change, and verified to change the DRC engine's
actual findings, not just its serialized bytes. Two previously-vacuous
kernels (`drc_zone_containment`, `safety_hv_lv_separation`) are fixed as a
direct consequence and now produce real findings against the production
board (3 and 94 violations respectively).

**It is not a complete R8** in the router's own literal sense. 9 of 27
kernels (33%) structurally require routed copper this producer cannot
regenerate, and a further 7 (26%) are placement-derivable in principle but
blocked today by harness-table gaps this task did not attempt to close
(§6). A future claim that "R8 is met" without naming these two boundaries
would be the "claimed-complete R8 that quietly excludes the routing
kernels" this task was explicitly warned against producing.

---

## Sources

- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §4 — the
  reachability assessment and recommendation this document implements.
- `tools/wasm/r2_serialize_board.py` — the producer, this change (commit
  `92a5d41a`): `build_board_dict` (line 44), `_harness_component_safety_classes`
  (line 286), `_pad_positions_by_net` (line 463), `_zones_from_placement`
  (line 493), `_zone_eligible_class_names` (line 591), `build_constraints_dict`
  (line 614).
- `packages/temper-placer/tests/scripts/test_r2_serialize_board.py` — 22
  tests, including the new placement-path determinism/sensitivity/
  non-vacuity coverage.
- `packages/temper-drc-rs/src/rules/mod.rs` — `create_default_registry()`,
  the canonical 27-rule list §3 classifies.
- `packages/temper-drc-rs/src/rules/{drc,erc,emc,safety,placement,routing}/*.rs`
  — every kernel's `check()` body, read in full for §1/§3.
- `packages/temper-drc-rs/src/constraints.rs` — `ConstraintSet`/
  `ZoneDefinition` schema.
- `packages/temper-drc-rs/examples/r2_full_board_pass.rs` — the native
  benchmark harness this producer's output feeds; `temper_drc_rs.run_drc`
  (pyo3 binding) used directly for the per-rule violation counts in §3/§5.3.
- `temper_placer.core.design_rules` (`TEMPER_NET_CLASSES`,
  `TEMPER_NET_ASSIGNMENTS`, `create_temper_design_rules`) — the harness
  SSOT this producer now reads.
- `temper_placer.io._parse_nets._apply_safety_classifications`,
  `_extract_design_rules` — the pre-existing classification function this
  producer's `_harness_component_safety_classes` mirrors, and the
  "vestigial, not authoritative" extraction it deliberately does not use.
- `temper_placer.router_v6._zone_pour_stitch` (`_zone_layers_for_net`,
  `_zone_params_for_net`, `_CONTINUITY_EXEMPT_CLASSES`),
  `temper_placer.router_v6.zone_emission` (`compute_zones_for_net`) — the
  router-free zone-derivation functions reused, not reimplemented.
