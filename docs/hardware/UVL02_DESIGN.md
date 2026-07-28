# UVL-02 Design: Logic-Rail (3.3V) Under-Voltage Lockout

**Date:** 2026-07-26 (fault integration superseded 2026-07-27, see SS7.2)
**Status:** Circuit designed and simulated. First confirmed
implementation of UVL-02 in this repository as a *monitor* circuit.
**WIRED into the fault interlock** as of 2026-07-27 (`15b9a33b`), via the
third fan-in package `SafetyInterlock.fault_or3` — see SS7.2. `fault.line`
also still lands on `SafetyInterlock.tp_uvlo2_fault` (the test point is
retained for bench observability; it is no longer the *only* destination).

**Revision note (2026-07-27):** SS7 and SS7.1 below record the survey and
the zero-capacity structural finding **as they stood on 2026-07-26**, and
are preserved verbatim because SS7.1's capacity argument is what motivated
`scripts/capacity_budget_gate.py` and the remediation that followed. That
remediation (SS7.1 option 2 — add a third OR package) **was subsequently
implemented**, so SS7's "no genuine spare SET-path input exists" and
SS7.1's "zero SET-path capacity" are **no longer true of the current
tree**. SS7.2 is the current state and supersedes both. Read SS7/SS7.1 as
history, SS7.2 as ground truth.

**Revision note (2026-07-26, post-review):** the first version of this
document and its accompanying circuit wired `uvlo_logic.fault.line` into
`fault_any_or.C1`, based on a survey of the worktree's tree at the time,
which had that input grounded. That worktree was stale relative to the
project's actual current tree (base commit `2758f228` vs. the real head at
the time, `ca9281d1`+), which had already landed THM-02
(`coil_thermal.fault.line ~ fault_any_or.C1`, commit `d99c88e2`) eight
commits earlier. Rebasing surfaced a genuine conflict on that exact line.
SS7 below is the corrected survey, done against the rebased tree. The
circuit design itself (SS3-SS6) is unaffected — only the interlock wiring
changes.

## 0. Requirement (verbatim)

`docs/FUNCTIONAL_TEST_CRITERIA.md` SS2.4:

| Rail | Trip Threshold (Falling) | Recovery (Rising) |
|------|--------------------------|--------------------|
| **Logic (3.3V)** | **< 2.9 V** | **> 3.0 V** |

The falling trip must land *below* 2.9V and the rising recovery *above*
3.0V. That is >100mV (>3.4%) of hysteresis around a 2.9V-ish threshold —
wide for a logic-supply monitor, and worth checking for satisfiability
before designing anything.

## 1. Ambiguity: what UVL-02 actually is

Before this work, two circuits existed in `elec/src/modules.ato` that could
plausibly be called "the" logic UVLO, and neither was confirmed as UVL-02.

**Candidate A — TPS3823-33 (`Watchdog` module, `wdt`, `components.ato:414-429`
pre-edit / now with corrected `v_threshold`).** This is the whole-board
3.3V supervisor (also the hardware watchdog), so it's the literal reading
of "Logic (3.3V)". Its threshold is fixed silicon set by the `-33` part
suffix. **Rejected as UVL-02** — see SS2 below; it fails the spec in both
directions even at nominal, and has no SPICE model (UNMEASURED in
simulation, and unmeasurable without a model).

**Candidate B — `RTDSensing.rail_monitor` (TPS3700, `modules.ato:1449-1467`
pre-edit).** Simulated at 2.8253V trip (hand-derived 2.825V, 0.3mV
agreement — `docs/evidence/2026-07-25-uvl02-rtd-avdd-monitor-candidate-sim.json`).
That number is conservatively under the 2.9V ceiling, but this circuit
monitors **RTD_AVDD**, a downstream, post-ferrite rail feeding the RTD
analog front end — not `power_3v3`, the board logic rail — per its own
component docstring ("Dual window supervisor; OUTA is low on RTD_AVDD
undervoltage"). It also has **no hysteresis resistor at all**, so its
recovery threshold was never designed to any target and was never checked
against the 3.0V floor. **Rejected as UVL-02** — right rail-monitoring
*mechanism*, wrong rail, and no hysteresis design.

**Resolution:** UVL-02 did not exist before this work. Neither candidate is
picked "because the number looks better" — both are rejected on identity
grounds (wrong threshold class / wrong rail), and a new circuit
(`LogicUVLOComparator`, SS4 below) is added specifically to monitor
`power_3v3` with a deliberately designed hysteresis window. This is the
same TPS3700 part as candidate B (same rail-monitoring mechanism that
candidate B proved plausible), applied to the correct rail with a
positive-feedback network candidate B never had.

## 2. Satisfiability: can a fixed-threshold supervisor do this at all?

**Falsifier, stated before any design work:** *"The spec is achievable with
a fixed-threshold supervisor."* Checked against primary sources. **It
fired — false.**

### 2.1 TPS3823-33, verified against TI's datasheet directly

Fetched TI's TPS382x datasheet (SLVS165O, April 1998, revised **March
2025**) directly — not through `SAFETY_INTERLOCK_DESIGN.md`'s secondhand
2.93V citation, which turned out to be *closer* to correct than the
`components.ato` component's own `v_threshold = 3.08V` attribute (source
of the 3.08V figure could not be established; it matched neither the
datasheet nor the project's own design doc — corrected in this change).

SS6.5 Electrical Characteristics, TPS3823-33 / TPS3823A-33 row (−40°C to
85°C):

| Parameter | Min | Typ | Max | Unit |
|---|---|---|---|---|
| V_IT− (falling threshold) | 2.86 | 2.93 | 3.00 | V |
| V_HYS (hysteresis at V_DD) | — | 30 | — | mV |

V_HYS has **no min/max spec** — 30mV typical is not a guaranteed number.
Rising threshold = V_IT− + V_HYS ⇒ **2.89 / 2.96 / 3.03 V min/typ/max**.

Nominal alone already fails UVL-02 in **both directions**:
- Falling trips at 2.93V typ — **above** the 2.9V ceiling.
- Rising recovers at 2.96V typ — **below** the 3.0V floor.

The device's factory hysteresis (30mV / 2.93V ≈ 1.0%) is an order of
magnitude short of the >100mV (>3.4%) this spec needs, and even the
best-case corner (2.86V falling, 3.03V rising if V_HYS held to its typical
value at the low VIT− corner) only reaches 170mV — and V_HYS has no
guaranteed minimum, so that can't be relied on either. **This part cannot
meet UVL-02 as specified**, confirmed from the primary datasheet, not
assumed.

### 2.2 Generalizing: is this a TPS3823-specific problem, or true of the class?

Checked TPS3808 (TI's *adjustable*-threshold supervisor family — the more
capable cousin of TPS3823, threshold set via an external SENSE-pin
divider) directly against its datasheet (SBVS050M, May 2004, revised March
2023), SS7.5:

| Parameter | Typ | Max | Unit |
|---|---|---|---|
| V_HYS (hysteresis on V_IT pin) — G01 | 1.5% | 3% | V_IT |
| V_HYS — fixed versions | 1% | 2.5% | V_IT |

Hysteresis here is specified as a **percentage of V_IT**, so it scales
through the external divider unchanged: even TI's *adjustable*-threshold
supervisor caps out at 1–3% hysteresis internally. **A fixed- or
adjustable-threshold supervisor IC's own internal hysteresis spec — not
just TPS3823-33's — tops out around 1–3%, roughly an order of magnitude
short of the >3.4% UVL-02 demands.** This is a genuine property of the
device class, not a part-selection mistake.

**Conclusion:** UVL-02 as specified is *not* achievable by relying on any
supervisor IC's internal hysteresis, fixed or adjustable-threshold. It
*is* achievable — see SS3 — with a comparator (or comparator-like device)
plus an **externally designed positive-feedback resistor network**, the
same approach this codebase already uses for THM-01, THM-02, and OVP-01
(`ThermalComparator`, `CoilThermalComparator`, `OVPComparator` in
`modules.ato`). The spec was written as if a wide-hysteresis part exists
off the shelf; it doesn't, but the effect is reproducible by design.

### 2.3 Consistency check against UVL-01

UVL-01 (15V gate-drive rail): <12.0V falling / >13.0V rising, 1V hysteresis
on ~12.5V (≈8%) — also demanding for a fixed-threshold part, and also,
per `docs/evidence/2026-07-25-uvl01-gate-drive-uvlo-unmeasured.json`,
**never given a dedicated circuit**. UVL-01 instead relies on the
UCC21550B gate driver's internal, fixed-silicon UVLO (VCC 7.6/8.1V,
VCCI 10.5/11.5V) — numbers that don't match the spec's 12.0/13.0V language
at all, on either rail. So the same design intent (a wide, deliberately
engineered hysteresis window) was **not applied consistently**: UVL-01
was left unresolved (UNMEASURED, no circuit), while UVL-02 is resolved
here with a purpose-built circuit. This asymmetry is a pre-existing
project gap, not something this change fixes — flagged, not silently
carried forward.

## 3. Chosen topology

`LogicUVLOComparator` (new module, `elec/src/modules.ato`): a **second,
independent TPS3700 instance**, monitoring `power_3v3` directly (not
RTD_AVDD), with a divider on channel A (`INA_P`) and a positive-feedback
hysteresis resistor — the same part as candidate B, the same "OVPComparator
hysteresis" pattern already established in this file, applied to the
correct rail.

**Why TPS3700 works for self-referenced rail monitoring at all:** its VIT_A
threshold (≈394.5mV, TI datasheet SBVS187G) is an internal bandgap-derived
reference, essentially independent of VDD (down to the part's own 1.3–1.7V
internal UVLO — far below anything relevant here). So a resistor divider
fed from the *same* rail the chip is powered from still produces an
**absolute**, not ratiometric, trip point. (A plain comparator referencing
its threshold off its own VCC via a divider — as `ThermalComparator` and
`OVPComparator` do, correctly, since *they* aren't monitoring VCC itself —
would NOT work here: both the sense node and the reference would scale
together with VDD, and the comparator would never detect an absolute
undervoltage. This is the reason a window-supervisor IC with an internal
reference, not a bare comparator, was the right choice for this
particular gate.)

**Hysteresis pattern:** follows `OVPComparator`, not `ThermalComparator`.
In `OVPComparator`, the *sense* node (bus divider, `comp.INP`) carries the
externally-set signal and is fed positive feedback from `comp.OUT`; the
*reference* node (`comp.INN`) is fixed. In `ThermalComparator`, it's the
other way around (NTC on the sense input, hysteresis loads the reference
divider instead) because the NTC is the sense element there. For UVL-02,
`INA_P` (the VCC divider) is the externally-set sense node and `VIT_A` is
TPS3700's fixed internal reference — structurally identical to
OVPComparator's case — so `r_hyst` loads `INA_P` directly from `OUTA`,
exactly like OVPComparator's `r_hyst` loads `comp.INP` from `comp.OUT`.

`mon.OUTA` is open-drain and active-low (LOW = undervoltage). It's pulled
up to `power.vcc` (10k, same convention as `RTDSensing.r_rail_ok_pullup`)
and inverted to the project's active-high fault convention with an
`SN74LVC1G38` NAND, one input tied high — the same inverter idiom
`SafetyInterlock`'s own SR-latch gate 1 uses (`latch.B1 ~ power_3v3.vcc`).
The inverter's own output is also open-drain, so it gets its own 10k
pull-up feeding `fault.line` — the same two-pull-up pattern
`RTDSensing.fault_nand` already uses for `rtd_hw_fault`.

## 4. Derivation

Let G_t = 1/R_div_top, G_b = 1/R_div_bot, G_h = 1/R_hyst.

```
V(INA_P), OUTA high (pre-trip, no fault) = VCC * (G_t + G_h) / (G_t + G_b + G_h)
V(INA_P), OUTA low  (post-trip, fault)   = VCC * G_t         / (G_t + G_b + G_h)

Trip    (falling, OUTA about to go low): VIT_A = VCC_trip    * (G_t+G_h)/(G_t+G_b+G_h)
                                       => VCC_trip    = VIT_A * (G_t+G_b+G_h) / (G_t+G_h)
Recover (rising,  OUTA about to go high): VIT_A = VCC_recover * G_t/(G_t+G_b+G_h)
                                       => VCC_recover = VIT_A * (G_t+G_b+G_h) / G_t
```

**Chosen values (E96, 1%):** R_div_top = 698kΩ, R_div_bot = 100kΩ,
R_hyst = 3.74MΩ, R_outa_pullup = R_fault_pullup = 10kΩ.

With VIT_A = 394.5mV (nominal, TPS3700 datasheet typ / model default):

```
G_t = 1/698000 = 1.43266e-6 S
G_b = 1/100000 = 1.00000e-5 S
G_h = 1/3740000 = 2.67380e-7 S

VCC_trip    = 0.3945 * (1.43266e-6 + 1.00000e-5 + 2.67380e-7) / (1.43266e-6 + 2.67380e-7)
            = 0.3945 * 1.170004e-5 / 1.700040e-6
            = 2.715 V

VCC_recover = 0.3945 * 1.170004e-5 / 1.43266e-6
            = 3.222 V

hysteresis  = 0.507 V  (15.4% of the 3.3V rail)
```

This was NOT the first value tried. An earlier pass targeted a tighter
nominal window (trip 2.85V / recover 3.05V, ~194mV hysteresis) to minimize
how far the design departs from nominal. Worst-case analysis (SS5) showed
that window has essentially **zero margin** in the worst corner (worst-case
trip 2.940V — *above* the 2.9V ceiling; worst-case recovery 2.935V —
*below* the 3.0V floor and even below the worst-case trip value). That
attempt is recorded here because it's the honest first result of "just
clears nominal," and it failed under tolerance — the final 2.715V/3.222V
design point was chosen specifically because it survives the corner sweep
with margin, not because it looks nicer nominally.

Quiescent current through the divider at VCC = 3.3V, pre-trip: ≈4.0µA
(negligible against board power budget, similar order to candidate B's
~4.6µA).

## 5. Worst-case tolerance analysis

Each of `R_div_top`, `R_div_bot`, `R_hyst` independently at ±1% (E96 part
tolerance, as committed), and `VIT_A` swept across its full TI-datasheet
range (387mV–400mV, not just the 394.5mV typ/model value) — 2³×2 = 16
corner combinations, exhaustively evaluated (see
`simulation/harness/run_uvl02_logic_sim.py::worst_case_corners`):

| | Nominal | Worst-case | Spec limit | Margin |
|---|---|---|---|---|
| Trip (falling, must stay **below**) | 2.715 V | **2.800 V** (max across corners) | < 2.9 V | **100 mV** |
| Recovery (rising, must stay **above**) | 3.222 V | **3.106 V** (min across corners) | > 3.0 V | **106 mV** |

Both directions clear with ~100mV of margin in the worst corner, not just
at nominal — this is the check the earlier 2.85V/3.05V attempt (SS4) failed.
The opposite (best-case) corner gives trip ≥ 2.618V, recovery ≤ 3.325V,
i.e. hysteresis never collapses below spec either.

**Caveat on the VIT_A range used:** TPS3700's datasheet gives VIT_A over the
full 1.8–18V VDD range and −40–125°C; the ngspice behavioral model
(`TPS3700_ngspice.lib`) implements only the single 394.5mV nominal value
with no min/max parameterization, so the corner sweep above is an
**independent analytic calculation**, not something ngspice itself swept.
The simulation (SS6) validates the nominal design point; SS5's numbers are
computed directly in Python, using the same formulas, cross-checked
against the simulated nominal result (which matched the hand derivation to
≤1mV — see SS6).

## 6. Simulation

`simulation/harness/run_uvl02_logic_sim.py` +
`simulation/harness/nets/uvl02_logic_uvlo_trip_point.cir`, following the
`run_thm02_sim.py` / `thm02_trip_point.cir` pattern exactly (a single
transient run driving the monitored quantity down past trip, then back up
past recovery, so both thresholds come from one latched-comparator run).

VCC ramps 3.3V → 2.0V over 300µs, then 2.0V → 3.4V over the next 300µs.
`TPS3700_ngspice.lib`'s behavioral model (`VIT_A=394.5m` fixed constant, no
internal hysteresis, no timing model) drives the divider + `r_hyst`
network exactly as committed in `elec/src/modules.ato`.

**Measured (5 identical ngspice runs, byte-for-byte determinism confirmed):**

```
t_trip    = 134.77 µs   ->  V(vcc_3v3) = 2.7160 V   (hand: 2.715 V, agreement 0.0010 V)
t_release = 561.80 µs   ->  V(vcc_3v3) = 3.2217 V   (hand: 3.222 V, agreement 0.0000 V)
measured hysteresis = 0.5057 V
```

Both `t_trip` and `t_release` land inside their respective ramp legs (not
at the endpoints), confirming the comparator actually crossed threshold
during the run rather than the measurement silently defaulting to a ramp
boundary. `V(vcc_3v3)` at each measured time is internally consistent with
the ramp's own known linear rate (independently recomputed from the PWL
breakpoints; matches to <0.1µs). Full evidence:
`docs/evidence/2026-07-26-uvl02-logic-uvlo-sim.json`.

**Model-fidelity note:** `V(INA_P)` sampled exactly at `t_trip` reads
~370mV, not the 394.5mV threshold itself. This is expected, not an error:
the trip is a genuine positive-feedback (regenerative) snap — as `OUTA`
begins pulling low, `r_hyst` pulls `INA_P` down further, reinforcing the
transition — so by the moment `OUTA` has swept fully across the 1.65V
logic-threshold crossing used for the `t_trip` measurement, `INA_P` has
already moved partway toward its post-trip settled value. The reported
trip/recovery voltages are `V(vcc_3v3)` at that same instant — the
externally observable quantity, and the one both the hand-derivation and
the spec care about — not `V(INA_P)`, which is only an internal diagnostic
node.

**Not measured by this harness (reported, not silently omitted):**
- Propagation delay / response time — `TPS3700_ngspice.lib` declares no
  timing model.
- Real regulator dynamics — the VCC ramp is an idealized PWL source, not a
  simulation of the actual buck-converter (`power_mgmt.buck_3v3`) output
  under a genuine brownout.
- Bench/hardware calibration of any kind — every model used is marked
  `calibrated: false` in the evidence JSON.

## 7. Fault integration (2026-07-26 survey — SUPERSEDED by SS7.2)

> **SUPERSEDED 2026-07-27 by SS7.2.** Everything in SS7 and SS7.1 was true of
> the tree at `ca9281d1`+ and is preserved as the record of how the
> capacity problem was found. It is **not** a description of the current
> design: a third `SN74HC4075DR` (`fault_or3`) was added in `15b9a33b` and
> UVL-02's fault **is now wired into the SET path**. Do not re-derive
> "zero available SET-path inputs" from this section.

**Corrected finding (this section replaces an earlier version that wired
the fault in — see the revision note at the top of this document for why).**

Surveyed the `fault_or` / `fault_any_or` (`SN74HC4075`) fault-aggregation
tree in `SafetyInterlock`, against the current tree (post-rebase onto
`docs/methodology-loop-discipline` @ `ca9281d1`+, which includes THM-02,
`d99c88e2`), for a genuinely free SET-path input:

- **`fault_or` gate 1** (`A1`/`B1`/`C1` → `Y1`): full — OCP/OVP/thermal.
- **`fault_or` gate 2** (`A2`/`B2`/`C2` → `Y2`): full — `Y1` feedback,
  watchdog (`latch.Y4`), `runaway_cut`.
- **`fault_or` gate 3** (`A3`/`B3`/`C3` → `Y3`): all three inputs tied
  GND, and `Y3` **drives nothing anywhere in the module**. A genuinely
  unused gate, but its output has no path into the SET aggregation
  without adding a further OR stage. (Same conclusion as the OCP-02
  finding.)
- **`fault_any_or` gate 1** (`A1`/`B1`/`C1` → `Y1`, and `Y1` is what
  drives `latch.A1`, the SET input): full — `fault_or.Y2`, `rtd_hw_fault`,
  and **`coil_thermal.fault.line` (THM-02, `d99c88e2`)**. THM-02 landed
  before this circuit was designed and took what had been the last spare
  input here. **This is the correction**: an earlier pass of this survey
  was run against a stale worktree (base `2758f228`, missing THM-02 and
  seven other commits) where this input was still grounded and looked
  free. It is not free on the actual current tree.
- **`fault_any_or` gate 2** (`A2`/`B2`/`C2` → `Y2`): `C2` is GND-tied and
  *looks* free, but this gate computes the RESET qualifier
  (`Y2 -> latch.A3`: `OR(any_fault, reset_request)`, which blocks firmware
  reset during a live fault). Wiring a fault here would only block reset —
  it would never SET the latch. Not usable (same conclusion as OCP-02).
- **`fault_any_or` gate 3** (`A3`/`B3`/`C3`/`Y3`): **entirely
  unreferenced** anywhere in `modules.ato` — not grounded, not wired, just
  absent. Structurally identical to `fault_or` gate 3: a genuinely unused
  gate whose `Y3` has no path into the SET aggregation without another OR
  stage to combine it in. Wiring inputs here alone does not reach
  `latch.A1`.

**Conclusion: no genuine spare SET-path input exists for UVL-02.**
`uvlo_logic.fault.line` is **left unwired into the interlock** and brought
to a test point instead (`SafetyInterlock.tp_uvlo2_fault`,
`elec/src/modules.ato`) — the same "flag it, don't fake a connection"
outcome already established as correct for OCP-02. An honestly-labelled
unwired fault is a better result than tying a second comparator output
onto an input a different comparator (THM-02) already drives, which would
be a driver conflict, not just a logical one.

### 7.1 Structural finding: two gates, zero SET-path capacity (SUPERSEDED by SS7.2)

**OCP-02 and UVL-02 are now both fully designed circuits with no available
SET-path input.** This is not a coincidence of two unlucky gate surveys —
it is a capacity problem: the fault-aggregation tree has exactly two
3-input `SN74HC4075` OR ICs (6 usable gates, 3 of which — `fault_or`
gates 1-2 and `fault_any_or` gate 1 — actually chain into the SET path,
giving `2×3 - 1 = ~5` effective independent SET-aggregation slots after
accounting for the `fault_or.Y1 -> fault_or.A2` and `fault_or.Y2 ->
fault_any_or.A1` cascade inputs). Those slots are now: OCP-01, OVP-01,
THM-01, watchdog, runaway-cut, RTD-hardware-fault, THM-02 — **seven**
fault sources already occupying them, with OCP-02 and UVL-02 as an eighth
and ninth source with nowhere to go. Adding another circuit here always
"just barely" doesn't fit from now on; the tree is out of room, not
temporarily short one input.

**What a fix would require (recommended, not implemented here):**

1. **Rework the existing gates into a wider tree.** The two
   `SN74HC4075`s already provide `fault_or.Y3` and `fault_any_or.Y3` as
   completely free 3-input OR gates (SS7 above) — they just don't
   currently feed anywhere. Re-plumbing one more OR stage (e.g. combine
   `fault_or.Y3` and/or `fault_any_or.Y3` into the existing
   `fault_or.Y2 -> fault_any_or.A1` link, or add one more cascade level)
   would absorb OCP-02 and UVL-02 using parts already on the BOM, at the
   cost of one extra gate delay in that path — which was exactly the
   "timing-budget decision for humans" the OCP-02 finding already
   declined to make silently. Zero new part numbers, but touches the
   timing of every existing fault source that gets re-routed through the
   new stage, and needs the timing budget (SS9 of
   `SAFETY_INTERLOCK_DESIGN.md`, ~50ns logic budget per gate today)
   re-checked for whichever paths move.
2. **Add a third OR IC** (another `SN74HC4075`, or a wider part such as a
   74HC4078 8-input OR/NOR if the aggregation is restructured as a single
   wide stage instead of cascaded 3-input gates). No re-routing of
   existing fault sources, one new BOM line, and a clean 3 further SET
   slots (enough for OCP-02, UVL-02, and one spare) — the simpler change,
   at the cost of a real part addition rather than a free one.

Either approach is a fault-tree-level decision affecting every existing
protection gate's timing or the BOM, not a leaf-level fix that belongs in
a single gate's design doc — flagged here for a human decision, not made
unilaterally. Until it's made, OCP-02 and UVL-02 both terminate at test
points: real, simulated, spec-meeting circuits that do not yet participate
in hardware shutdown.

### 7.2 Current state (2026-07-27): third package added, UVL-02 wired

**This section supersedes SS7 and SS7.1.** The decision SS7.1 flagged for a
human was taken, and **option 2** (add a third OR IC) was chosen over
option 1 (rework the existing dead gate 3s into a wider cascade): option 1
adds the same one gate of propagation delay to the same path while
additionally requiring re-verification of every existing connection it
re-routes. Full write-up, including the falsifier and the
propagation-delay recheck, in
`docs/evidence/2026-07-27-fault-tree-capacity-expansion.md` (`15b9a33b`).

**`SafetyInterlock.fault_or3`** — a third `SN74HC4075DR`, the same MPN
already twice on the BOM, so no new part number — is wired in
`elec/src/modules.ato` as:

| Gate | Inputs | Output |
|---|---|---|
| `gate1` (new-source aggregator) | `A1 = uvlo_logic.fault.line` (UVL-02, **wired**), `B1` = GND (reserved for OCP-02, deliberately not wired), `C1` = GND (spare) | `Y1 -> fault_or3.B2` |
| `gate2` (merge with the existing bus) | `A2 = fault_any_or.Y1` (the existing 7-source SET bus), `B2 = fault_or3.Y1`, `C2` = GND (spare) | `Y2 ~ latch.A1` (**the SET pin**) |
| `gate3` | all three GND-tied, unused | `Y3` drives nothing (dead, same convention as the other two packages' gate 3s) |

`fault_any_or.Y1`'s *other* consumer (`fault_any_or.Y1 ~ fault_any_or.A2`,
the RESET-qualifier feed) is untouched — only its SET-path consumer moved
from `latch.A1` to `fault_or3.A2`.

**Capacity, before and after** (`scripts/capacity_budget_gate.py`, whose
BFS reachability check is the automated form of the SS7 survey):

| | 2026-07-26 (SS7/SS7.1) | Current |
|---|---|---|
| Aggregator packages | 2 | **3** |
| SET-path inputs evaluated | 18 | **27** |
| **AVAILABLE** | **0** | **3** |
| UNUSABLE | 18 | 24 |
| OCCUPIED | 11 | 14 |
| Capacity defects | 0 | 0 |

**The three available inputs are exactly `fault_or3.B1`, `fault_or3.C1`
and `fault_or3.C2`** — each GND-tied today, each on a gate whose own
output reaches `latch.A1` (`U26.A1`). `B1` is held for OCP-02; `C1` and
`C2` are genuine spare capacity. This triple is asserted by name in
`scripts/tests/test_capacity_budget_gate.py`, so this table and the gate
cannot drift apart silently: if the tree changes, that test fails and
sends the reader back here.

**`fault_or3` gate 3's three inputs remain UNUSABLE** (`Y3` drives
nothing), exactly like `fault_or` and `fault_any_or` gate 3. That is
headroom for a *future* cascade stage, not usable capacity today — the
same distinction SS7 drew, and the reason the honest count is 3 and not 6.

**OCP-02 is still not wired, and that is deliberate** — not a capacity
problem any more. `SecondaryOCPComparator` remains un-instantiated in
`main.ato` because its sensing domain is unresolved (the INA240 sits at
~170 V common mode against its −4 V…+80 V input range in the doubler
topology). `fault_or3.B1` is capacity held ready for that decision, not a
claim that OCP-02 works. `docs/hardware/OCP02_DESIGN.md`'s "there is no
spare OR input for the fault" finding is superseded by this section; its
sensing-domain blocker is not.

**Timing cost.** The new gate adds one OR stage to every fault path.
Against OCP-01's <1 µs budget, on datasheet worst case (VCC=2 V column,
−40…85 °C, as a conservative stand-in — neither part is characterised at
3.3 V): **686 ns → 811 ns**, margin **31.4% → 18.9%**. Still clears, with
the reduction reported rather than absorbed. `SAFETY_INTERLOCK_DESIGN.md`
SS9's lumped 50 ns logic budget undercounts the real gate depth and
predates this change; flagged there, not corrected here.

## 8. Summary

| Question | Answer |
|---|---|
| Does a compliant UVL-02 monitor circuit exist? | **Yes, as of this change** — `LogicUVLOComparator`, new. Neither pre-existing candidate qualified. |
| Is the spec satisfiable by a fixed-threshold supervisor? | **No** — confirmed against TI's TPS3823 and TPS3808 datasheets directly; ~1-3% is the ceiling for that device class, spec needs >3.4%. |
| Is the spec satisfiable at all? | **Yes** — with a window-comparator IC (internal absolute reference) plus an externally designed positive-feedback resistor network, the same idiom already used for THM-01/THM-02/OVP-01 in this codebase. |
| Measured trip (nominal) | 2.716 V (sim), 2.715 V (hand) |
| Measured recovery (nominal) | 3.222 V (sim and hand) |
| Worst-case trip (16-corner, ±1% + datasheet VIT_A range) | 2.800 V — 100mV inside the 2.9V ceiling |
| Worst-case recovery | 3.106 V — 106mV inside the 3.0V floor |
| **Fault wired into interlock?** | **Yes, as of 2026-07-27 (`15b9a33b`)** — `uvlo_logic.fault.line ~ fault_or3.A1 -> Y1 -> B2 -> Y2 ~ latch.A1`. SS7/SS7.1 found zero SET-path capacity on the then-two fan-in packages (THM-02, `d99c88e2`, owned the last one); SS7.1's option 2 was taken and a third `SN74HC4075DR` added, restoring 3 available SET-path inputs. `fault.line` still also reaches `SafetyInterlock.tp_uvlo2_fault` for bench observability. See SS7.2. |
| UVL-01 comparison | Also demanding (~8% hysteresis needed) and, unlike UVL-02, still left UNMEASURED with no dedicated circuit — inconsistent application of the same design intent, flagged not fixed here |

**Remaining UNVERIFIED:**
- TPS3823-33's true silicon behavior on this specific board (no SPICE
  model exists anywhere for this part; the datasheet numbers are read
  correctly but the part itself is not simulated or bench-measured here or
  anywhere in this repository).
- `LogicUVLOComparator` response time / propagation delay (no timing model
  in `TPS3700_ngspice.lib`).
- Any bench measurement of the new circuit — everything here is simulation
  plus hand derivation, both explicitly `calibrated: false`.
- Interaction with the real `power_mgmt.buck_3v3` regulator's own output
  dynamics during an actual brownout (this harness uses an idealized PWL
  ramp, not a regulator model).
