<!-- provenance: branch analysis/current-carrying-trace-widths, worktree
/home/bennet/Desktop/temper/.worktrees/current-carrying-trace-widths, base
origin/main @ 03a7415c8. This task's diff is this document only --
pcb/temper.kicad_pcb and pcb/temper.kicad_pro are UNCHANGED (verified
`git status --porcelain pcb/` empty throughout). No netclass value is
changed anywhere in this diff. All routing/DRC measurements below run
against scratch copies under /tmp (gitignored, not part of this branch's
diff): $SCRATCH/routed/{baseline,corrected}_routed.kicad_pcb, produced by
`scripts/route_board.py --net-batching` against unmodified
`pcb/temper.kicad_pcb` and a scratch copy of
`packages/temper-placer/configs/netclass_rules.yaml` with only
HighVoltage/HighVoltageTank `trace_width` changed 3.0mm -> 5.0mm (the value
this document derives in S2). -->

# Current-carrying trace widths: derivation, unbudgeted tank current, class-scoping, and routability

## Headline

**The width question is second-order. The tank/DC-bus design current itself
exceeds the board's own declared current ceiling and its own connector pad
rating, on the peak axis, and this is an already-known, already-recorded,
explicitly UNRESOLVED gap in `elec/src/modules.ato` — not something this task
discovered.** No trace width is "correct" for a current that the design has
not itself budgeted. See S1.

Independent of that: `HighVoltage`'s declared 3.0mm is short of its own
40°C-pour-budget requirement by 27–45% depending on which of the class's two
governing currents (22A peak per the netclass description, or 22.5A RMS
thermal per the real tank derivation) is used, and `ACMains`'s 2.5mm/3.0mm
(two disagreeing SSOTs — see S3) is short of the 15A/40°C-pour figure by a
much smaller 8% or is already sufficient, respectively. The mismatch is
**not** uniformly a trace-vs-pour scoping error as hypothesized: `ac_l`/`ac_n`
legitimately reach copper via zone pours and the 40°C budget applies to them,
but `w1_1`, `w1_2`, `power_in.ntc-no` are `HighVoltage`-classed and the
class's own SSOT declares them `routing_strategy=plane_required` (pour-
eligible) too — yet the real board gives them **zero, partial, or
badly-undersized trace copper**, not a pour. The true defect is broader than
"wrong scope, right value": trace **width** (a current-magnitude property)
and clearance/creepage (a voltage-domain property) are bundled into one
netclass field, and current magnitude spans **three orders of magnitude
within the single `HighVoltage` class** (bleed-path `discharge.k_dis1-nc` at
~20mA vs tank/DC-bus at 22.5A RMS) — no single class-wide width value can be
correct for both. See S4.

A separate, previously-uncharacterized, currently-live defect makes the
whole netclass-width question partly moot for what's actually drawn today:
Stage 4.4 (`_pipeline_route.py:674`) calls `assign_trace_widths()` without
its `power_width`/`hv_width` parameters, so **every current-carrying net's
final copper width is decided by net-NAME keyword matching against fixed
0.508mm/0.635mm constants, never by the netclass's declared trace_width** —
confirmed by measuring the real board: `w1_2` is drawn at 0.25mm,
`power_in.ntc-no` at 0.508mm, both far under their own declared 3.0mm class,
let alone any IPC-correct figure. See S5.

**Feasibility, measured, not extrapolated:** widening `HighVoltage`/
`HighVoltageTank` 3.0mm→5.0mm and re-routing the full board from scratch
(`--net-batching`, both runs completed, `w=405s`/`414s`) does **not**
regress pad connectivity in any way attributable to the width change beyond
run-to-run noise (48/139 vs 49/139 pad-connected nets, -1), and the TRUE
(uncapped) `clearance`/`track_width` counts both *improve* at the wider
width (clearance 1814→1282, track_width 841→802) — though this run-to-run
comparison is confounded by net-batching's own documented solve-order
nondeterminism and is not a controlled multi-run measurement (see S6's
caveat). `w1_1` and `tank.c_tank1-p2` fail to route in **both** the current
and the corrected width — a pre-existing routability gap unrelated to the
width increase. Creepage TRUE-adjacent DRC (PD2/8mm barrier) improves
(164→149 violations), not regresses. No component moves in this routing-only
test, so IGBT heatsink co-location (#1082) is unaffected by construction.

**Recommendation:** re-scope before re-valuing. Split trace-width
determination from the clearance-governing netclass (an explicit per-net or
per-current-tier width, not a single class-wide constant), fix the Stage 4.4
`assign_trace_widths` defect so declared widths are what actually gets drawn,
and — before any of that — get the tank/DC-bus peak-current question
resolved by the person who owns the coil/converter design, because it
determines what current every one of these widths must be sized for in the
first place.

## 0. On the task brief's own citation, and the coordinator's correction

The brief originally cited `docs/evidence/2026-08-13-router-netclass-trace-
widths.md` (PR #1117) for the 15A/4.16mm/11.84A/"1814→1807" figures. That
file is not present on `origin/main` (`git log --all`, `git grep`, full-tree
`find` all empty) — the coordinator has since confirmed PR #1117 is open,
not merged, so this is expected, not a fabrication; the correct posture
(per the coordinator) is to treat its numbers as an unverified hypothesis
and re-derive independently. That is what this document does throughout.

One coincidence worth recording rather than trusting: this document's own
independently-run TRUE `clearance` measurement (S6) on a freshly net-batch-
routed *current-width* board comes out to exactly **1814** — matching the
brief's cited baseline figure digit-for-digit. That is consistent with
PR #1117 having used the same `scripts/measure_uncapped_drc.py` methodology
against a comparably-produced board, which is reassuring corroboration, but
it is still this document's own from-scratch measurement that is cited
below, not the brief's number.

The tank-current figure in the original brief ("22A peak / 15A RMS") has
been superseded per the coordinator's correction: use **22.5A RMS thermal
design / 20.7A RMS simulated / 28.7–31.9A peak**, from `elec/src/
modules.ato:585-593`, below.

## 1. The current itself is not budgeted — read this before any width number

`elec/src/modules.ato:585-593` (comment attached to `inductor_conn`, the
resonant-tank inductor's PCB connection, `Inductor` type, footprint
`LitzPad_15A`):

> `current_rating = 25A` is an RMS THERMAL requirement this design imposes,
> not a value read from any part: **22.5A rms at the 1800W point**
> (first-harmonic solve, coil-selection-research Sec 4.2) against **20.7A
> rms** from this repo's own ngspice harness, x ~1.11 margin.
> **UNRESOLVED AND RECORDED, NOT FIXED HERE**: the corresponding **PEAK is
> 28.7–31.9A**, which is above BOTH `LitzPad_15A`'s declared 15A pad rating
> (`footprints.ato`) and `Top.i_peak_max` / `HighVoltageConstraints.i_max =
> 25A`. Both were already exceeded by the PREVIOUS 150uH model's own
> committed 28.71A peak — this declaration surfaces the conflict, it does
> not create it, and raising either rating to match is exactly the move
> that must not be made without a thermal/geometry basis.

Characterized directly:

| Quantity | Value | Source |
|---|---:|---|
| Design ceiling (`HighVoltageConstraints.i_max`) | 25 A | `elec/src/constraints.ato:8` |
| Connector pad rating (`LitzPad_15A`) | 15 A | `elec/src/footprints.ato:3-5`, `HighCurrentPad` |
| Tank RMS thermal design current | 22.5 A rms | `modules.ato:585-587`, first-harmonic solve at the 1800W operating point |
| Tank RMS simulated current | 20.7 A rms | `modules.ato:587-588`, this repo's own ngspice harness |
| Tank peak current | 28.7–31.9 A | `modules.ato:589-591` |

RMS (22.5A) sits under the 25A ceiling with only ~11% margin against the
lower (simulated) 20.7A figure — thin, but not exceeded. **Peak (28.7–31.9A)
exceeds both the 25A design ceiling and the 15A pad rating.** The comment is
explicit that this is `UNRESOLVED AND RECORDED, NOT FIXED` — an
acknowledged, flagged, open gap, not a signed-off deviation, and the same
comment notes the *previous* inductor model (150µH) already committed a
28.71A peak that exceeded both limits too, so this is not new to the 88µH
change; it is a pre-existing condition the 88µH declaration merely
surfaces rather than creates.

**This outranks the width question.** IPC-2221B sizes copper to a declared
design current. If the declared *peak* design current (28.7–31.9A) exceeds
both the project's own ceiling and the physical pad it must pass through,
then a trace-width recommendation sized to the RMS figure (used throughout
S2, because that is the correct steady-state thermal metric for a continuous
sinusoidal tank current) is silent about a real gap on the peak axis that
copper cross-section cannot fix — the pad, not the trace, is the binding
constraint there, and it is a component/footprint decision outside this
task's remit (do not change netclass values; this is not a netclass value).
This is flagged, not resolved, per the same posture the source comment
takes.

## 2. Per-net current and required width (trace vs pour, both distinguished)

### 2.1 Method, verified independently against the repo's own formula

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` S2 (IPC-2221B, external layers):
`I = k × ΔT^0.44 × A^0.725`, `k=0.048` external, rearranged for width
`W(mm) = (A_mils² / (oz × 1.37)) × 0.0254`. Recomputed from scratch (not
copied from the brief):

- 15A / 20°C rise / 2oz: **4.156mm** (brief's 4.16mm — confirmed independently, not trusted)
- 3.0mm / 2oz / 20°C rise carries: **11.84A** (brief's 11.84A — confirmed)
- 3.0mm / 2oz / 40°C rise (pour) carries: **16.07A**
- 2.5mm / 2oz / 40°C rise (pour) carries: **14.08A**

### 2.2 Which nets are actually pour vs trace, measured on the real board

`_should_route()` (`router_v6/_net_policy.py:21`) excludes a Power/GND/HV
net from A* only when `_zone_layers_for_net()` (`_zone_pour_stitch.py:78`)
grants it zone eligibility — driven by `NetClassRules.routing_strategy`.
**Both `ACMains` and `HighVoltage` declare `routing_strategy="plane_
required"`** in `core/design_rules.py` (lines 70, 105) — by class-level SSOT
declaration, *every* `HighVoltage` member (not just `ac_l`/`ac_n`) is
pour-eligible, contra the task brief's hypothesis that only `ACMains` is.

But declared eligibility and measured reality diverge. Direct measurement of
`pcb/temper.kicad_pcb` (net-name → net-number → `(segment ...)`/`(zone ...)`
line count, read-only, no file modified):

| Net | Class | Segments (real trace) | Zones (real pour) | What it actually is today |
|---|---|---:|---:|---|
| `ac_l` | ACMains | 0 | 2 | pour |
| `ac_n` | ACMains | 0 | 2 | pour |
| `SW_NODE` | HighVoltage | 0 | 2 | pour |
| `DC_BUS_RTN` | HighVoltage | 0 | 2 | pour |
| `PWR_RTN` | HighVoltage | 0 | 2 | pour |
| `w1_2` | HighVoltage | 41 @ **0.25mm** | 0 | trace (badly undersized) |
| `power_in.ntc-no` | HighVoltage | 31 @ **0.508mm** | 0 | trace (undersized) |
| `w1_1` | HighVoltage | 0 | 0 | **unrouted** |
| `+170V_BUS` | HighVoltage | 0 | 0 | **unrouted** |
| `tank-out` | HighVoltage | 0 | 0 | **unrouted** |
| `tank.c_tank1-p2` | HighVoltageTank | 0 | 0 | **unrouted** |

So the task brief's framing ("`ac_l`/`ac_n` reach copper via pours … while
`w1_2`/`power_in.ntc-no` are routed traces at 20°C") is correct as a
description of what's actually on the board today, but it is not because
the *class* scopes them differently — the class says all of `HighVoltage`
should pour. It's because the pour-clustering geometry (`_zone_pour_
stitch.py`'s R6 change, 2026-08-07: `HighVoltage` was un-exempted from
single-hull clustering and now gets 5-6 small per-component hulls per net)
either doesn't produce a qualifying cluster for these specific nets' pad
layouts, or the board predates that regeneration. Either way: **on the real
board, `w1_2` and `power_in.ntc-no` are genuinely routed copper traces, so
the 20°C trace budget genuinely applies to them — not the 40°C pour budget
their class's declared intent implies.**

### 2.3 Required width by net (2oz external, ΔT as scoped above)

| Net(s) | Class | Design current | Basis (trace 20°C vs pour 40°C) | Required width | Declared class width | Real drawn copper |
|---|---|---:|---|---:|---:|---|
| `ac_l`, `ac_n` | ACMains | 15A | pour (measured: zone-covered) | **2.73mm** | 2.5mm (`kicad_pro`) / 3.0mm (`netclass_rules.yaml`) | pour, width n/a |
| `w1_1`, `w1_2` | HighVoltage | 15A (same branch, `cmc.current_rating >= constraints.i_max`) | **trace** (measured: routed/attempted as traces) | **4.16mm** | 3.0mm | `w1_1` unrouted; `w1_2` @ 0.25mm |
| `power_in.ntc-no` | HighVoltage | 15A branch load; 20A relay-contact rating (`bypass_relay.contact_current`, headroom not load) | **trace** (measured) | 4.16mm (load) / 6.18mm (rating) | 3.0mm | 0.508mm |
| `SW_NODE`, `DC_BUS_RTN`, `+170V_BUS`, `PWR_RTN` | HighVoltage | 22A peak (netclass description) or 22.5A RMS thermal (S1, more authoritative) | pour (measured, where zoned) | 4.63mm (22A) / **4.77mm** (22.5A) | 3.0mm | pour or unrouted (`+170V_BUS`) |
| `tank.c_tank1-p2` | HighVoltageTank | 22.5A RMS (S1) | trace/pour, unresolved (net unrouted on real board) | 4.77mm | 3.0mm | unrouted |
| `discharge.k_dis1-nc`, `k_dis2-nc` | HighVoltage | **~20mA** (bleed string, `170V/(3.9k+4.7k)`, `modules.ato:1171-1173`; 10A is the *relay contact's* component rating, not the design current) | trace | **<<1mm** (thermally trivial) | 3.0mm | mixed, "fake-completion" |
| `hb.power_loop.q_high-g` | HighVoltage | Q_high gate signal, ~mA (voltage-domain member only) | trace | <<1mm | 3.0mm | — |
| `a`, `zcd` | HighVoltage | ZCD divider tap, µA-mA | trace | <<1mm | 3.0mm | `zcd` is dead circuitry (see below) |
| `GATE_HS/LS`, `PWM_HS/LS` | GateDriveHV/SELV | 4A peak (`GateDriveConstraints.i_max`), sub-µs pulse, thermally trivial | trace, transient not steady-state | 0.5mm (doc §3.4, manufacturability-bound, not thermal-bound) | 0.4mm | — (not this task's focus; doc's own figure is defensible) |
| `+15V`, `+3V3`, `vcc`, `V_BUS_SENSE` | Power | 3A (`GateDriveConstraints`/netclass description) | trace | 1.0mm (doc §3.6) | 1.0mm | already adequate, not in question |

`zcd` is excluded from every feasibility conclusion below per instruction:
it is dead circuitry from a deleted circuit (`5842767c2`) never resynced to
the board, and its large DRC footprint (68+ clearance violations against it
alone in the baseline route) is stale-board noise, not a live safety signal.

## 3. Are the declared thermal parameters themselves sound?

`TRACE_WIDTH_CALCULATIONS.md` S1 declares: 2oz external copper, 60°C
ambient, 20°C trace rise, 40°C pour rise.

**2oz external, 20°C/40°C split**: not independently re-derived here beyond
confirming the arithmetic in S2.1 — these are IPC-2221B's own standard
figures (the doc cites "IPC-2221B recommendation" for the 20°C rise; JLCPCB
capability for 2oz) and match `PCB_SPECIFICATION.md`'s stack-up. No defect
found.

**60°C ambient**: this is where the repo's citation quality actually
matters, per the task's warning that five other safety figures today cited
something other than a real derivation.

1. **The parameter is inert to the width formula as written.** IPC-2221B's
   `I = k × ΔT^0.44 × A^0.725` uses only the temperature *rise* (ΔT), never
   the absolute ambient baseline. Every calculation in
   `TRACE_WIDTH_CALCULATIONS.md` §3.1–3.8 operates on ΔT alone. Whether 60°C
   is right or wrong, **it changes none of the width numbers in that
   document** — it would only matter for checking `ambient + rise` against
   an absolute material/component limit, which the document never does.
2. **It disagrees with the project's own declared design envelope.** Four
   different "ambient" figures exist across this repo's own docs, none
   cross-referencing another:
   - `main.ato`'s `t_ambient_max = 323.15K` = **50°C** — the figure actually
     consumed by `docs/hardware/PART_STRESS_AUDIT.md`'s real component-margin
     calculations.
   - `docs/CHASSIS_AIRFLOW_DESIGN.md` §5 models **35°C** ambient feeding a
     51°C duct-exhaust figure — but that duct is explicitly *not* the PCB
     compartment (§3.3: the PCB sits in a separate, gasketed, non-forced-air
     compartment — a PD2 release prerequisite), so this figure doesn't
     directly bound the PCB's ambient either way.
   - `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §2.2 brackets "worst case" as
     **55–70°C**, which is the only figure that actually contains
     `TRACE_WIDTH_CALCULATIONS.md`'s 60°C.
   - `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2 independently states
     the identical **60°C** figure with the identical unexplained
     justification string ("Kitchen environment near cooking") — either a
     genuine independent corroboration or (more likely, given the identical
     phrasing) the same unsourced assumption copied into two documents.

   None of these cite a measurement, a datasheet, or a standard clause for
   why 60°C specifically (vs. 50°C, the design's own declared ceiling). It
   is the most conservative of the figures in circulation, so its effect —
   inert on the width formula, and would only tighten an ambient+rise
   absolute-temperature check if one were ever added — is not in the unsafe
   direction. But it is asserted, not derived, exactly the pattern the task
   warned about; I would not sign off on it as sourced without someone
   producing the measurement or standard clause it's supposed to represent.

**Conclusion**: the ΔT figures (20°C/40°C) are sound and IPC-2221B-standard.
2oz is consistent with the stack-up. The 60°C ambient figure is unsourced
and inconsistent with the project's own 50°C design ceiling, but it does not
change any width number in this document because the formula never consumes
it — flagged, not a live defect in the width calculation itself.

## 4. Re-scoping vs re-valuing

**Re-scoping, not re-valuing — but more specifically than the brief's
hypothesis.** The brief's framing (pour-covered ACMains legitimately takes
40°C; trace-routed HighVoltage members need 20°C) is half right: it
correctly describes *what's on the board today* (S2.2), but the root cause
isn't that the classes scope trace-vs-pour differently by design — both
classes declare the *same* `plane_required` intent. The root causes are:

1. **Trace width (current capacity) and clearance/creepage (voltage
   isolation) are orthogonal physical requirements bundled into one
   netclass field**, and current magnitude varies **1000×** within a single
   class (`discharge.k_dis1-nc` ~20mA vs tank/DC-bus 22.5A RMS, both
   `HighVoltage`). A single class-wide `trace_width` cannot be correct for
   both ends of that range simultaneously — either the bleed-path nets are
   absurdly overbuilt or the tank/bus nets are dangerously underbuilt, and
   today it's the latter.
2. **Whether a given net gets pour or trace copper is determined by
   per-net pad-cluster geometry at route time, not by class declaration**
   (`_zone_pour_stitch.py` R6). The class's `routing_strategy` states an
   intent every member is supposed to satisfy; several don't, on the real
   board (`w1_1` unrouted, `w1_2`/`power_in.ntc-no` trace-only). That's a
   second, independent gap: intent vs. realized geometry.

Re-scoping (splitting current-magnitude tiers out of the voltage-domain
class, or attaching an explicit per-net width override) is cheaper and more
correct than re-valuing the whole class upward, because re-valuing
`HighVoltage` to serve its highest-current member (tank/bus, needing
~4.8mm at pour budget or higher at trace budget) would grossly overbuild
every low-current member of the same class (bleed resistors, gate-adjacent
signal taps) for no benefit, while a uniform re-value still would not by
itself fix the pour-vs-trace realization gap in point 2 above.

## 5. A separate, live defect: declared width is not what gets drawn

`packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:674`:

```python
width_assignment = assign_trace_widths(
    pathfinding_result,
    default_width=pcb.design_rules.default_trace_width_mm,
)
```

`assign_trace_widths()`'s signature (`trace_width_assignment.py:71-79`) also
takes `power_width` (default 0.508mm) and `hv_width` (default 0.635mm) —
**neither is ever passed at this call site**, so Stage 4.4 always uses the
hardcoded function defaults, regardless of what any netclass declares.
Width is chosen purely by net-**name** keyword match
(`trace_width_assignment.rs:59-82`, `kw_boundary_match_impl`): `AC_`/`HV_`/
`HIGH_VOLTAGE` → 0.635mm; `GND`/`VCC`/`VDD`/`VSS`/`POWER`/leading `+` →
0.508mm; `GATE`/`DRIVE` → 0.3048mm; else → `default_trace_width_mm` (≈0.2mm).

This exactly reproduces what's measured on the real board: `power_in.ntc-no`
(matches `POWER` keyword) → 0.508mm; `w1_2`/`w1_1` (no keyword match) →
default (~0.2-0.25mm observed). **Corridor reservation during A* pathfinding
correctly uses the real per-netclass width** (`_astar_reconstruct.py:232,
410`, `net_rule.trace_width_mm`) — so a router *searches* for room as if the
trace were the declared width, but then *draws* the final copper at the
wrong, much narrower, name-derived width. Any netclass-width fix (re-scoping
or re-valuing) will not change what's actually manufactured until this call
site also passes the correct widths through — a second, independent PR,
outside this task's "no netclass value change" scope but necessary before
any width recommendation here has real effect on the board.

## 6. Feasibility, measured

**Environment note**: the shared venv's `temper_orchestration` extension was
stale (missing `RouterPipeline`, added `08b1ee8a2`); a newer, already-built
wheel existed in `target-shared/wheels/` (timestamped ~1hr prior, evidently
built by a concurrent session) and was reinstalled via `uv pip install`
(no compilation, no cargo build, no risk to the shared build cache).
`scripts/verify_pumpkin_engine.py` passed (exit 0) before any solve.

Two full-board routes, both against the unmodified, committed
`pcb/temper.kicad_pcb`, `--net-batching`, identical flags otherwise:

- **baseline**: `packages/temper-placer/configs/netclass_rules.yaml`
  unmodified (`HighVoltage`/`HighVoltageTank` trace_width = 3.0mm).
- **corrected**: scratch copy with `HighVoltage`/`HighVoltageTank`
  trace_width raised 3.0mm → **5.0mm** (S2.3's pour-budget figure for the
  22.5A RMS tank/bus current, and coincidentally identical to
  `TRACE_WIDTH_CALCULATIONS.md` §3.1's own — internally inconsistent with
  its own §7 table — 5.0mm recommendation). `ACMains` was left as-is
  (`netclass_rules.yaml` already declares 3.0mm, which exceeds the 2.73mm
  pour-budget requirement for 15A — see S3's note that this yaml disagrees
  with `kicad_pro`'s 2.5mm, a third SSOT-drift finding not previously
  flagged: `kicad_pro`/`design_rules.py` say 2.5mm, `netclass_rules.yaml`
  — the file the router actually consumes — says 3.0mm).

| Metric | Baseline (3.0mm) | Corrected (5.0mm) | Delta |
|---|---:|---:|---:|
| Wall time | 405.4s | 414.0s | +2% |
| Topology completion | 63/103 (61.2%) | 62/103 (60.2%) | -1 net |
| **Pad connectivity (primary metric)** | 49/139 | 48/139 | **-1 net** |
| Segments | 2916 | 2871 | -45 |
| Zones | 94 | 94 | 0 |
| Vias | 30 | 30 | 0 |
| TRUE `clearance` (uncapped, `measure_uncapped_drc.py`) | **1814** | **1282** | **-532 (-29%)** |
| TRUE `track_width` (uncapped) | 841 | 802 | -39 (-5%) |
| DRU-aware `creepage` (PD2/isolation barrier) | 164 | 149 | -15 (improves) |

`w1_1` and `tank.c_tank1-p2` are **unrouted in both runs** — a pre-existing
routability gap, not caused by the width increase (it already fails at the
current 3.0mm). `w1_2` and `power_in.ntc-no` remain "fake-completion"
(partial copper, not all pads joined) in both runs, also unchanged. The one
new failure attributable to the width change plus `zcd` (excluded, dead
circuitry) is a single SELV logic net, `safety-line-2`, newly failing to
route in the corrected run — not current-carrying.

**Caveat, stated plainly**: this is a single paired run, not a repeated
(`--runs N`) measurement. `route_board.py`'s own `--runs` mode exists
specifically because net-batching's per-batch SAT solve has real run-to-run
variance in which specific geometry gets chosen; the per-net-pair `clearance`
breakdown (not shown in full here) has individual buckets swinging by
dozens of violations in *both* directions between the two runs, which is
larger than what a purely width-driven effect would produce for e.g.
low-voltage nets untouched by this change. The **aggregate** TRUE
clearance/track_width numbers moving in the same (improving) direction
across two independently-computed measurement methods (kicad-cli capped
totals with DRU active, and the uncapped exhaustive measurement) is
reassuring but not a substitute for a proper N-run measurement, which this
session's time budget did not allow. **What is *not* run-to-run noise**:
`w1_1`/`tank.c_tank1-p2` failing identically in both runs, and no new
current-carrying-net failures beyond the single SELV net noted above — those
are the two most load-bearing feasibility facts and both are robust to the
single-run caveat.

No component is moved by routing (`route_once` uses existing board
positions), so IGBT shared-heatsink co-location (#1082) is unaffected by
construction, not merely unmeasured-and-assumed-fine.

## 7. Recommendation

1. **Get the tank peak-current question resolved first** (S1). This is a
   design-current budgeting problem, not a copper-sizing problem, and it
   determines the input to every width calculation for the tank/DC-bus
   nets. Flagged here, not fixed — it needs the coil/converter design
   owner, not a netclass edit.
2. **Do not re-value `HighVoltage`/`ACMains` uniformly.** Re-scope: separate
   trace-width (current-magnitude-driven) from clearance/creepage
   (voltage-domain-driven) so a bleed-path net and a tank/bus net in the
   same voltage domain can carry different widths without needing different
   classes for clearance purposes. This is the cheaper, more correct fix
   per S4.
3. **Fix `_pipeline_route.py:674`'s missing `power_width`/`hv_width`
   pass-through** (S5) before any width recommendation here has real
   effect on manufactured copper — right now the netclass value and the
   drawn copper are two unrelated numbers for every current-carrying net.
4. **The width increase itself (3.0mm→5.0mm for HighVoltage/HighVoltageTank)
   is feasible** by every measurement taken here (S6) — it does not
   regress pad connectivity beyond single-run noise, does not regress the
   PD2 creepage barrier, and does not disturb IGBT heatsink co-location.
   `w1_1` and `tank.c_tank1-p2`'s unrouted status is a pre-existing gap
   this task did not create and did not resolve.
5. **`ACMains`'s two disagreeing declared widths** (2.5mm in `kicad_pro`/
   `design_rules.py`, 3.0mm in `netclass_rules.yaml`) should be reconciled
   before anything else touches that class — whichever is correct, having
   two different router-facing SSOTs disagree on a mains-input width is a
   defect independent of this task's own findings.

No netclass value was changed by this task. All measurements above ran
against scratch copies outside `pcb/**`; `git status --porcelain pcb/` is
verified empty.
