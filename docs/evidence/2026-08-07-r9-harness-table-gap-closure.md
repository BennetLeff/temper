<!-- provenance: commit=a85e8c5789d5725926eeba3dbd820944ff385522 dirty=false -->

# R9: closing the 7 harness-table gaps — which of the 6 fixed, which stayed vacuous, and why

**Date:** 2026-08-07 / 2026-08-08
**Base:** `docs/evidence/2026-08-07-router-free-r8-producer.md` (commit `1fc965d8`), which
established that 17 of 27 registered DRC/ERC/EMC/safety/placement/routing rule
kernels are reachable from the router-free `zone_source="placement"` producer
without `route_pcb()` — 6 fire real findings, 4 report clean, and **7 remain
blocked by harness-table gaps unrelated to routing**: role-keyword vocabulary
(`emc_ground_plane`, `emc_noise_coupling`, `routing_isolation_slot`), an
undeclared `safety_category="iso"` (`safety_isolation`, `safety_creepage`),
and unpopulated `critical_loops`, `max_current_rating`, `power_dissipation_w`.
This document diagnoses each of the 7 precisely, finds (or rules out) an
authoritative, non-invented source for each, populates the producer where a
real source exists, and demonstrates a seeded defect for every kernel that
becomes reachable.

**Bottom line up front:**

1. **2 of the 7 gaps are fully fixed, converting 1 previously-vacuous kernel
   to functional and demonstrably strengthening a second.** `max_current_rating`
   is now populated for every net class via the IPC-2221 trace-width ->
   ampacity estimate already shipped in production
   (`config_loader.rs::validate_current_capacity`'s own fallback, not an
   invented number) — `routing_tht_thermal_relief` goes from permanently
   vacuous to 25 real findings on the committed board, verified sensitive to
   a harness-only edit (25 → 10 findings when `HighVoltage`'s declared
   rating is raised above the check's 10A threshold, no board change).
2. **A real, authoritative, previously-unconsulted source for `safety_category
   == "iso"` was found**: `elec/domain_manifest.yaml`'s `isolators:` list —
   the same declaration `scripts/check_domain_partition.py`'s CI gate already
   treats as ground truth — resolved against the parsed board's own
   `Sheetpath` footprint property (no `elec/` netlist re-parse needed). 8
   real components resolve (not 7 as first estimated — `C6`, the Y1
   safety-bonding capacitor, is a genuine 8th declared isolator found only by
   reading the manifest in full). `safety_creepage` is fully fixed: 0
   findings on the real board, and a seeded defect (shrinking `U7`'s
   footprint below the 6.0mm minimum) produces the expected violation.
   `safety_isolation` is **half**-fixed: its `is_iso_component` predicate is
   now correct (verified directly), but the check has a *second*,
   independent gate (`constraints.zones` must contain an entry whose *name*
   matches an isolation keyword) that has no non-guessed source — it remains
   vacuous, and this document says exactly why rather than papering over it.
3. **This fix has real, measured side effects on 2 already-working kernels**,
   reported here rather than hidden: `safety_hv_lv_separation` drops from 94
   to 66 violations (the 8 isolator components are now correctly exempted
   from the binary HV/LV check — the Rust kernel's own `"iso" => None`
   branch — rather than counted as "HighVoltage", which they never
   semantically were), and `drc_zone_containment` drops from 3 to 2 (`K3`
   is no longer a zone-eligible class member). Both deltas are fully
   explained: `drc_clearance`'s violation *set* is byte-identical
   before/after (90 == 90, zero added, zero removed) — the `IsolationDevice`
   class deliberately copies `HighVoltage`'s clearance/trace-width/creepage/
   voltage numbers so this reclassification cannot silently weaken that
   check.
4. **5 of the 7 gaps have no source I could find without guessing, and stay
   vacuous** — 3 role-keyword vocabulary gaps (unchanged from R8), half of
   `safety_isolation` (above), and `emc_loop_area`. The loop-area finding is
   sharper than "no source exists": a real, already-shipped
   production mechanism (`temper_placer.core.loop_extractor.auto_extract_loops`)
   exists and IS used elsewhere in the codebase, but produces **zero** loops
   when actually run against this board, because its component-classification
   heuristic assumes power switches are refdes `Q*` — this board's real
   IGBTs are `U5`/`U6` (`Q1`/`Q2` are unrelated small SOT-23 relay-drive
   transistors). Wiring it into the producer would not unblock the kernel.
   The only alternative sources found (`packages/temper-placer/configs/
   templates/loops/*.yaml`, `configs/constraints/*.yaml`) are explicitly
   named templates/references with stale refdes (`Q1`/`Q2`, `C_BUS1`) and,
   in one case, a stale net name (`DC_BUS+`/`DC_BUS-` do not exist on the
   real board; the live rail is `+170V_BUS`/`DC_BUS_RTN`) — using them would
   be exactly the invented/wrong data this task prohibits.
5. **Re-measured 27-kernel coverage (§5): 7 working (was 6), 5 reachable-
   and-clean (was 4, one of which — `safety_creepage` — is now clean
   *and verified capable of failing*, a stronger bar than the other 4), 5
   blocked-on-data (was 7), 1 half-blocked, 9 needs-router (unchanged).**

---

## 1. Method

Same as R8: read every blocked kernel's `check()` body in
`packages/temper-drc-rs/src/rules/` to see exactly which field is missing and
what the kernel does when it's absent, then search for a real, structured,
already-declared source for that field — not a plausible-sounding guess.
`elec/` was read (never modified, per this task's rules) as a candidate
source; `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` were
neither read for data-sourcing purposes nor modified.

## 2. Per-gap diagnosis, source, and fix

### 2.1 `emc_ground_plane`, `emc_noise_coupling`, `routing_isolation_slot` — role-keyword vocabulary

**Behaviour when the datum is absent:** none of the three ever early-return
on an empty-vec fast path in the way `safety_isolation`/`routing_isolation_slot`
do below — `emc_ground_plane` and `emc_noise_coupling` iterate every
component and simply never find one whose net-class name substring-matches
`["power","switching","clock","pwm","high_freq"]` (noisy) or
`["analog","sensor","small_signal","victim"]` (sensitive); `routing_isolation_slot`
does have a hard early return (`if slot_zones.is_empty() { return violations; }`)
gated on `constraints.zones` entries named `"slot"`/`"isolation"`. All three
**report clean by construction, not because the board has been verified
clean** — this is the vacuous-gate pattern the task asked me to flag
explicitly, and it is unchanged from R8's own diagnosis.

**Source search (re-verified, not assumed from R8):** grepped
`TEMPER_NET_CLASSES`'s 11 class names (`ACMains`, `HighVoltage`,
`HighVoltageIsolated`, `GateDriveHV`, `GateDriveSELV`, `HighCurrent`,
`HighSpeed`, `FinePitch`, `Power`, `GND`, `Signal`) against every keyword all
three rules use — zero matches. Checked whether `Component`/`Net` carries
any `role`-shaped field anywhere in `packages/temper-placer/src/temper_placer/core/netlist.py`
or the Rust parse engine's `CompOut` — none exists. Checked
`packages/temper-placer/configs/constraints/*.yaml` (the PCL "Placement
Constraint Language" template directory) — these ARE English-language-role
declarations in principle, but every one is refdes-keyed against a
generic/example board (`Q1`/`Q2` as the IGBTs, `U_MCU`, `C_BUS1`), not this
board's real refdes (`U5`/`U6`/etc — see §2.3), and the directory's own
README calls `temper_induction_cooker.yaml` "a reference for your own
project-specific constraint files," i.e. explicitly not live data.

**Fix:** none. No source. Left exactly as R8 left them.

### 2.2 `safety_category == "iso"` — `safety_isolation`, `safety_creepage`

**Behaviour when absent:** `is_iso_component` (shared by both rules) checks
`board.net_class_rules[comp.net_class].safety_category == "iso"` first, then
falls back to keyword substring matching on the net class *name*
(`"iso"/"opto"/"coupler"/"isolator"/"transformer"/"adum"/"dcdc"/"mev1"`).
Since no `TEMPER_NET_CLASSES` entry ever declares `"iso"` and none of the 11
class names substring-match those keywords, `is_iso_component` returns
`false` for every real component. `safety_creepage` then simply skips every
component (`continue` on `!is_iso_component`) — **reports clean, 0
violations, for the wrong reason**: not because every isolation device
passes its width check, but because the check never identifies a single
isolation device to check. `safety_isolation` additionally has its own
independent early return (`if iso_zones.is_empty() { return violations; }`,
§2.2.2) that fires regardless of `is_iso_component`.

**Source found:** `elec/domain_manifest.yaml`'s `isolators:` list — a
YAML-declared list of every component that physically implements the
board's HV/SELV isolation barrier, each entry naming an atopile
`instance_path` (e.g. `hb.gate_hs.driver`) and the pin groups on each side of
the barrier. This is not a guess: `scripts/check_domain_partition.py`'s own
CI gate (`load_manifest`/`Isolator`) already treats this exact list as
authoritative for exactly this fact, cross-checking it against the `elec/`
netlist on every PR. The same `instance_path` string is independently
present on `pcb/temper.kicad_pcb` itself — every footprint atopile emits
carries a `(property "Sheetpath" "<instance_path>")`, exposed already by the
parser as `Component.sheetpath` (`packages/temper-design-bundle/src/parse_engine.rs`
line 1690, `parsed.components[i].sheetpath`) — so resolving refdes needs no
second `elec/` parse, just matching two already-available strings.

Verified against the real board (all 8 resolve, none missing/ambiguous):

| `instance_path` | refdes | role |
|---|---|---|
| `aux_supply.psu` | `PS1` | Mean Well IRM-10-15 aux supply transformer |
| `hb.gate_hs.driver` | `U7` | UCC21550 reinforced-isolation gate driver |
| `ct_sense.ct` | `T1` | Coilcraft CST3015 current-sense transformer |
| `power_in.bypass_relay` | `K1` | Omron G4A-1A-E bypass relay |
| `discharge.k_dis1` | `K2` | Schrack RT314012 discharge relay 1 |
| `discharge.k_dis2` | `K3` | Schrack RT314012 discharge relay 2 |
| `power_in.zcd_opto` | `U3` | onsemi H11L1TVM ZCD optocoupler |
| `power_in.y_cap_pe` | `C6` | Y1-class EMI/PE-bonding capacitor (IEC 60384-14) |

`C6` was not in my first manual read of the manifest (I stopped at the
`power_in.zcd_opto` entry and the "capacitor policy" prose that follows it,
which *describes* C6's exemption but is not itself the list entry) —
`_isolator_component_refs` (which reads the whole list programmatically, not
by hand) found it, and its own extensive doc-comment in the manifest
explains exactly why it's declared as an isolator rather than defaulting to
"every passive conducts": it is a certified, IEC-60335-legitimate EMI bond,
not an accidental short, and treating it as a generic conducting component
would make the CI domain-partition gate permanently red over a legitimate
design.

**Fix implemented** (`tools/wasm/r2_serialize_board.py`,
`_isolator_instance_paths`, `_isolator_component_refs`): components whose
`sheetpath` matches a declared `instance_path` get their per-component
`net_class` overridden to a new synthetic class, `"IsolationDevice"`, whose
`net_class_rules` entry declares `safety_category: "iso"`. This is the same
per-component net-class-override mechanism R8's own
`_harness_component_safety_classes` already established (severity-based
HV/AC reclassification) — extended with a second, more specific override
that takes priority when a component is a *declared* isolator, which is a
stronger, sourced signal than the generic worst-case-severity heuristic.

**Why `IsolationDevice`'s other fields are not invented:** all 8 isolator
components already had at least one pin on an HV- or AC-severity net (`PS1`
mains primary, `U7`/`K2`/`K3` on the DC bus side, `T1` in series with the
tank, `U3`'s LED anode on the HV-side ZCD divider tap, `K1`'s mains
contacts, `C6` bonded to `PWR_RTN`), so every one of them was **already**
classified `"HighVoltage"` by R8's severity override before this change, and
`drc_clearance` was **already** enforcing `HighVoltage`'s 6.0mm
clearance / 3.0mm trace-width against their neighbours. `IsolationDevice`
copies those same numbers verbatim (clearance_mm, trace_width_mm,
creepage_mm, voltage_v) rather than picking new ones — a deliberate,
documented, non-weakening choice, not a new invented part spec. Measured
directly (§4): `drc_clearance`'s violation *set* is byte-identical before
and after this change.

**Verification — `safety_creepage` (fully fixed):**

- Real board: 0 violations (all 8 isolators' `max(width, height)` — 11.9mm
  to 46.2mm — comfortably clears the check's 6.0mm `min_iso_width_mm`
  threshold, hardcoded at registry construction and out of this producer's
  scope). This is a genuinely reachable, evaluated, clean result — not the
  same "clean" as before, which was clean because nothing was ever checked.
- **Seeded defect**: shrinking `U7`'s footprint to 3.0mm × 3.0mm in memory
  (no board file edit) produces exactly 1 `SAF_CRP_001` violation
  (`"Creepage violation: component U7 width 3.0mm < 6.0mm"`). Confirms the
  check fires when it should, not just that it runs without error.

**Verification — `safety_isolation`'s `is_iso_component` half (fixed, but
insufficient alone — see §2.2.2):** diagnostic-only (not shipped), injecting
a synthetic `ConstraintSet.zones` entry `{"name": "isolation_test_zone",
"net_classes": ["IsolationDevice"]}` produces 0 violations (every
`IsolationDevice`-classed component correctly exempts itself via
`is_iso_device { continue; }`); the same zone naming `["Signal"]` instead
produces 118 violations against real `Signal`-classed components. This
isolates and confirms the predicate fix independent of the second gap below.

### 2.2.2 `safety_isolation`'s second, independent, unfixed gate

`safety_isolation.check()` has a hard early return before it ever reaches
`is_iso_component`: `constraints.zones.iter().filter(|z| is_iso_zone(&z.name))`
must be non-empty, where `is_iso_zone` keyword-matches
`["iso","opto","coupler","transformer","gutter","slot"]` against the zone's
*name*. This producer's `constraints.zones` (`_zone_eligible_class_names`,
unchanged by this task) only ever contains entries named after
`routing_strategy == "plane_required"` classes — `"ACMains"` and
`"HighVoltage"` on the real board — neither of which matches any of those
keywords, so `iso_zones` is always empty and the check always returns before
`is_iso_component` is ever consulted, **regardless of §2.2's fix**.

I looked for and rejected one candidate before concluding there is no
source: `"HighVoltageIsolated"` (a real, already-declared class) *does*
substring-match `"iso"` (`highvoltageisolated` contains `iso`). Adding it to
`constraints.zones` would technically satisfy the early-return condition,
but the rule's actual semantics after that point (`comp.net_class` in
`zone.net_classes` ⇒ violation unless the component is itself an iso device)
would then flag every *legitimate* component downstream of the isolated
bootstrap rail (bootstrap diode/cap, gate-drive resistors, etc.) as a safety
violation for the sole reason that it draws power from an isolated supply —
that is not what "isolation zone" means for this check, and shipping it
would trade a silent vacuous gate for a noisy, semantically wrong one. I did
not implement this. `safety_isolation` remains vacuous; I found no
non-guessed way to close its second gate.

### 2.3 `critical_loops` — `emc_loop_area`

**Behaviour when absent:** `constraints.critical_loops.iter().filter_map(...)`
over an empty vec `.collect()`s to an empty vec — no early return, just
structurally nothing to iterate. Reports clean because there is nothing to
check, same vacuity shape as the role-keyword rules.

**Source found, but it does not work on this board.**
`temper_placer.core.loop_extractor.auto_extract_loops(netlist)` is real,
already-shipped production code — called from
`packages/temper-placer/src/temper_placer/physics/loop_area.py`
(`commutation_loop_area`) and
`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py`
(`_resolve_loop_components`) — that heuristically traces the commutation,
gate-drive, and bootstrap loops directly from parsed netlist topology (pin
nets, common-net detection, capacitor-between-nets search), no invented
domain knowledge. Run directly against the real board:

```
find_power_switches(nl)  -> []
find_gate_drivers(nl)    -> []
auto_extract_loops(nl).loops -> 0 loops
```

Root cause, confirmed by reading `classify_component`
(`temper_placer/core/loop_extractor.py`): it classifies a component as a
`power_switch` only if `ref.startswith("Q")`, then narrows by MPN or
footprint pattern. On this board the real IGBTs are `U5`
(`Sheetpath: hb.power_loop.q_high`, footprint `TO-247-3_Vertical`) and `U6`
(`hb.power_loop.q_low`, same footprint) — `Q1`/`Q2` are unrelated SOT-23
transistors (`Sheetpath`: `power_in.q_relay_drv` / `discharge.q_dis_drv`,
small relay-drive parts). `classify_component`'s footprint-package branch
(which *would* catch `TO-247`) is nested inside the `ref.startswith("Q")`
gate and never reached for `U5`/`U6`. `find_gate_drivers` independently
fails for a second reason: it MPN-matches (`"UCC"`, `"ISO"`, ...), and
`parse_kicad_pcb`'s `Component.attributes` never carries an MPN field at all
(confirmed reading `parse_engine.rs`: only `_center_offset_x/_y`/
`_rotation_deg` are populated) — so `U7`'s real MPN, UCC21550, is invisible
to this classifier via any code path.

I confirmed the *real* commutation loop exists and is exactly what
`auto_extract_loops` is meant to find, purely to make sure this isn't "no
loop exists" but "the heuristic can't see it": `U5` pin 2 = `+170V_BUS`
(collector), pin 3 = `SW_NODE` (emitter); `U6` pin 2 = `SW_NODE`
(collector), pin 3 = `DC_BUS_RTN` (emitter) — the textbook half-bridge
commutation path, using the real, live net names.

**Alternative sources checked and rejected, not just the heuristic:**
`packages/temper-placer/configs/templates/loops/commutation.yaml` (a
project template, not board-specific data) names `nets: [DC_BUS+, SW_NODE,
DC_BUS-]` — `DC_BUS+`/`DC_BUS-` do not exist as net names on the real board
at all (confirmed: `'DC_BUS+' in net_names -> False`); the live rail is
`+170V_BUS`/`DC_BUS_RTN`, exactly the stale-net-name failure mode
`design_rules.py`'s own comments repeatedly warn about elsewhere in this
codebase (`+340V_BUS`, the pre-R4 `GateDrive` class). Its `components`/`pins`
fields use `Q1`/`Q2`/`C_BUS1`, also wrong for this board.
`configs/constraints/safety_isolation.yaml` similarly uses `Q1`/`Q2`/
`C_BUS1`/`U_MCU`/`CT1` — none of which are real refdes on this board.

**Fix:** none. I deliberately did not patch `classify_component`'s
refdes-prefix assumption (footprint-only power-switch detection would work
here, since `TO-247`/`TO-220`/`TO-263` is unambiguous and this producer
already computes a `package_type` field from exactly that footprint
substring match for an unrelated purpose) — that is a change to a shared,
multi-consumer heuristic (also used by the CP-SAT placer's own loop-area
constraint and the physics `commutation_loop_area` gate, both of which are
therefore **also** silently not finding this board's real commutation loop,
an orthogonal finding worth a separate follow-up) with a wider blast radius
than "populate the producer," and redesigning a classification heuristic is
exactly the kind of guess R8 itself declined to make for the role-keyword
gaps. `emc_loop_area` remains vacuous.

### 2.4 `max_current_rating` — `routing_tht_thermal_relief`

**Behaviour when absent:** `net_class_rules.get(&comp.net_class).and_then(|r|
r.max_current_rating)` — with the field `None` on every class, the `match`
falls through to `_ => {}` (skip) for every component. Not a "reports
clean" vacuity (the rule's own `Severity::Info` framing is "verify
manually," not "board is compliant") but structurally unreachable
regardless of what else this producer emits — the same failure class.

**Source found:** `temper_placer.core.ipc2221.estimate_current_from_net_class`
(backed by the `temper_ipc` Rust crate's IPC-2221 trace-width -> ampacity
table) is **already the harness's own accepted fallback for exactly this
gap**, not something I invented for this task: `config_loader.rs`'s
`validate_current_capacity` (a real, production, already-shipped function —
confirmed reading it directly, not assuming from its pinned test oracle) does
`if net_class.max_current_rating is not None: current_a = that; else:
current_a = estimate_current_from_net_class(net_class.trace_width_mm)` when
loading any PCL constraints config that omits a class's rating. This
producer applies the identical fallback when building `net_class_rules`, for
every class (harness-sourced and KiCad-declared-only), so a class that DOES
one day declare a real rating keeps that value untouched — verified directly
(§4).

**Fix implemented:** `_current_rating()` helper in
`tools/wasm/r2_serialize_board.py`, applied uniformly.

**Verification:**

- Real board: 25 violations (all 21 `package_type == "tht"` components not
  reclassified `IsolationDevice`/`HighVoltage`, each with an IPC-2221
  estimate ≤ the check's 10A threshold given their harness-declared
  trace widths — e.g. `Signal`'s 0.2mm trace ⇒ 0.371A). `To247`/`To220`
  package types (`U1`/`U2`/`U5`/`U6`) are excluded by the kernel's own
  `PackageType::Tht`-only filter, unrelated to this fix.
- **Seeded / harness-sensitivity defect**: with a byte-identical committed
  board, monkeypatching `TEMPER_NET_CLASSES["HighVoltage"].max_current_rating`
  from `None` to `15.0` (above the 10A gate) drops the finding count from 25
  to 10 — the harness-only edit changed which real components' declared
  rating now exceeds the threshold, exactly R8's own "input changes when
  the harness changes" property, now demonstrated for this field too.

### 2.5 `power_dissipation_w` — `placement_thermal_via_count`

Unchanged from R8 (§6.5): `comp.power_dissipation_w` is hardcoded `None` for
every component in `build_board_dict`'s components loop, and even a fully
populated value would not unblock this kernel alone — it also needs
`board.vias`, a routing artifact this producer cannot regenerate without
`route_pcb()` (already the reason it's classified "needs routed board," not
one of the 7 harness-table gaps). I looked for a per-component power-budget
table (BOM/thermal-budget source) in `elec/` and `packages/temper-placer/configs/`
and found none — `docs/hardware/`'s thermal documents are prose design
rationale, not a structured per-refdes wattage table. No source found; no
fix attempted; this remains blocked on the routing dependency regardless.

---

## 3. Side effects on already-working kernels — measured, not asserted

Ran `temper_drc_rs.run_drc` against the real board through both the
pre-change (`git show HEAD:tools/wasm/r2_serialize_board.py`, commit
`1fc965d8`) and post-change producer, in the same process session, and
diffed violation sets by `(check_name, sorted(affected_items), code)`:

| Kernel | Before | After | Δ | Explanation |
|---|--:|--:|--:|---|
| `drc_clearance` | 90 | 90 | 0 added, 0 removed | `IsolationDevice` copies `HighVoltage`'s clearance/trace-width verbatim (§2.2) |
| `drc_zone_containment` | 3 | 2 | −1 | `K3` (isolator) no longer matches a zone-eligible class name |
| `safety_hv_lv_separation` | 94 | 66 | −28 | all 28 removed violations involve ≥1 of the 8 isolator refs, now correctly exempted (Rust's own `"iso" => None` branch) |
| `routing_tht_thermal_relief` | 0 (unreachable) | 25 | +25 | §2.4 fix |
| `safety_creepage` | 0 (vacuous) | 0 (verified reachable) | 0 | §2.2 fix; clean is now a real result, not a structural non-check |

`drc_clearance`'s zero-delta was verified as an exact set match (not just an
equal count) — no violation present before is absent after, and none present
after is new.

## 4. Determinism and sensitivity

- **Determinism**: two independent process-level `build_board_dict` calls
  against the real board produce identical `components` (including the new
  `IsolationDevice` overrides), `net_class_rules` (including the new
  `max_current_rating`/`IsolationDevice` entry), `zones`, `traces`, `vias`,
  and — this run — `nets` too (all `True`). `packages/temper-placer/tests/scripts/test_r2_serialize_board.py`:
  27/27 pass (22 pre-existing + 5 new).
- **Harness sensitivity**: demonstrated per-fix above (§2.2, §2.4) — an
  in-process harness-only edit (no `pcb/temper.kicad_pcb` change) changes
  the producer's output and the DRC engine's actual findings.

## 5. Re-measured 27-kernel coverage boundary

| Status | R8 (before) | Now | Kernels moved |
|---|--:|--:|---|
| **Working** (fires real findings) | 6 | **7** | `routing_tht_thermal_relief` added |
| **Reachable, plausibly/verifiably clean** | 4 | **5** | `safety_creepage` added (and verified capable of failing, not just structurally reachable — a stronger bar than the other 4, which were not seed-tested by either R8 or this task) |
| **Blocked on harness-table data gap** | 7 | **5** | `routing_tht_thermal_relief`, `safety_creepage` removed; `safety_isolation` stays (half-fixed, still net-blocked — §2.2.2); `emc_ground_plane`, `emc_noise_coupling`, `routing_isolation_slot`, `emc_loop_area` unchanged |
| **Half-blocked** (needs router + data) | 1 | 1 | `routing_isolation_barrier` unchanged |
| **Needs routed board** (traces/vias) | 9 | 9 | unchanged |
| **Total** | 27 | 27 | |

Working (7): `drc_clearance`, `drc_component_overlap`, `drc_courtyard`,
`drc_zone_containment`, `routing_copper_pullback`, `safety_hv_lv_separation`,
`routing_tht_thermal_relief`.

Reachable-and-clean (5): `erc_net_connectivity`, `erc_power_domain`,
`erc_floating_pins`, `placement_wave_solder_keepout`, `safety_creepage`.

Blocked-on-data (5): `emc_ground_plane`, `emc_noise_coupling`,
`routing_isolation_slot` (role-keyword vocabulary, §2.1), `safety_isolation`
(is_iso_component fixed, `iso_zones` gate unfixed, §2.2.2), `emc_loop_area`
(source exists, yields nothing on this board, §2.3).

**17 of 27 kernels remain reachable without `route_pcb()` (unchanged from
R8 — this task did not change which kernels are structurally
router-independent, only how many of the already-reachable ones are
non-vacuous)**; within that 17, the functional fraction rose from 6/17 (35%)
to 7/17 (41%), and the "reachable but never shown capable of failing"
population shrank from effectively all 10 non-working-reachable kernels to
9, with one (`safety_creepage`) now holding the stronger bar of a
demonstrated seeded-defect catch.

---

## Sources

- `docs/evidence/2026-08-07-router-free-r8-producer.md` — the R8 baseline
  this document extends; §6 is the exact 7-gap list this document closes
  where possible.
- `tools/wasm/r2_serialize_board.py` — the producer, this change:
  `_isolator_instance_paths`, `_isolator_component_refs`, `_current_rating`,
  the `IsolationDevice` `net_class_rules` entry construction.
- `packages/temper-placer/tests/scripts/test_r2_serialize_board.py` — 5 new
  tests (27/27 total pass).
- `elec/domain_manifest.yaml` — `isolators:` list, the source for §2.2 (read
  only, not modified).
- `scripts/check_domain_partition.py` — the existing CI gate that already
  treats `domain_manifest.yaml`'s `isolators:` list as authoritative for
  this exact fact, corroborating it is a real source and not this task's
  own invention.
- `packages/temper-design-bundle/src/config_loader.rs` (`validate_current_capacity`)
  and `packages/temper-placer/src/temper_placer/core/ipc2221.py`
  (`estimate_current_from_net_class`) — the already-shipped IPC-2221
  fallback this producer now reuses for §2.4, not a new formula.
- `packages/temper-placer/src/temper_placer/core/loop_extractor.py`
  (`auto_extract_loops`, `classify_component`) — the real production
  mechanism investigated and found non-functional on this board for §2.3.
- `packages/temper-placer/configs/templates/loops/commutation.yaml`,
  `packages/temper-placer/configs/constraints/safety_isolation.yaml` — the
  stale/generic template sources checked and rejected for §2.3/§2.1.
- `packages/temper-drc-rs/src/rules/safety/{isolation,creepage,hv_lv_separation}.rs`,
  `packages/temper-drc-rs/src/rules/routing/tht_thermal_relief.rs`,
  `packages/temper-drc-rs/src/rules/emc/{ground_plane,noise_coupling,loop_area}.rs`,
  `packages/temper-drc-rs/src/rules/routing/isolation_slot.rs`,
  `packages/temper-drc-rs/src/rules/drc/{clearance,zone_containment}.rs` —
  every kernel's `check()` body, read in full for §2.
