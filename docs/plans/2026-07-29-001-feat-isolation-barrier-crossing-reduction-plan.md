---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
date: 2026-07-29
topic: isolation-barrier-crossing-reduction
focus: Reduce the NUMBER of mains<->SELV isolation barrier crossings, not the
  per-crossing footprint geometry -- deletion is the premise, footprint fixes
  are explicitly deprioritized. Run as solo rigorous analysis (ce-brainstorm
  in non-interactive mode): every place a real dialogue would ask the user,
  the most defensible assumption is stated explicitly and surfaced as an
  Outstanding Question.
origin: Task brief (board re-floorplanning out of scope; CP-SAT already
  proved INFEASIBLE at the current creepage target in both orientations for
  the current component set); prior work
  docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md (footprint
  fix-classification for C6/K2/K3/U3/U7, explicitly the complementary
  document to this one -- that one asks "how do we fix each crossing's
  geometry," this one asks "which crossings can we delete or merge instead")
status: research-only, no elec/src or pcb/ changes made -- this is a
  requirements document for a human/planning decision, not an implementation
actors: elec/domain_manifest.yaml, elec/src/modules.ato (OVPComparator,
  BusDischarge, CurrentSensing, PowerInput), scripts/check_isolation_keepout.py,
  docs/hardware/IEC60335_CRITICAL_COMPONENTS.md, PCB footprint/BOM author
  (human), safety sign-off (human)
---

# Reduce Mains<->SELV Isolation Barrier Crossing Count -- Plan

## Goal Capsule

**Objective:** identify which of the design's currently-declared mains<->SELV
isolation crossings can be *deleted* or *merged* outright -- reducing the
count a creepage gate has to satisfy at all -- as opposed to improving the
footprint geometry of each existing crossing individually (that is the
subject of the sibling document,
`docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md`, and is
explicitly out of scope here).

**Product/design authority:** `elec/domain_manifest.yaml` (the manifest of
record for what crosses the barrier and how), cross-checked directly against
`elec/src/modules.ato` and `elec/src/main.ato` for every claim below --
nothing in this document is inferred from a comment alone without reading the
wiring it describes.

**Open blockers (not resolved by this document, stated up front):**
- Board re-floorplanning, the two-PCB split, and any footprint/part-geometry
  fix for an individual crossing are all explicitly out of scope (hard
  constraint from the task brief) -- this document assumes the current
  single-board floorplan throughout.
- The exact governing reinforced-creepage figure is itself unsettled in this
  repo's own recent history: the task brief cites PD3/12.6mm
  (`ENVIRONMENTAL_SPEC.md` Sec 3.1, commit `c58c94d8`, "PD3 GOVERNS"), while
  the currently-committed `clearance.py` enforces 10.0mm reinforced (a
  separate, more recent correction --
  `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`, which
  found the validator had been checking every >300V boundary against the
  wrong IEC 60335-1 Table 16 row) and `check_isolation_keepout.py` still
  hard-codes 8.0mm, unchanged. **This document does not reconcile that
  number.** It does not need to: every recommendation below is "delete or
  merge a crossing," which reduces the number of *places* the gate has to be
  satisfied regardless of what the target millimeter figure eventually
  settles to. Flagged as a pre-existing, independently-tracked open item, not
  something this pass resolves.

---

## 1. The Crossing Inventory, Verified Against the Repo

`elec/domain_manifest.yaml` declares **10 crossings total**, in two
structurally different categories that this document classifies before
proposing anything (per the task's own instruction -- these two kinds reduce
by different means and must not be flattened together):

### 1a. Galvanic / mechanical isolators (`isolators:` block, 8 entries)

| # | Instance | Part | Kind | Current footprint status | Function |
|---|---|---|---|---|---|
| 1 | `aux_supply.psu` | Mean Well IRM-10-15 | Certified AC-DC module, 4.2kVAC withstand | Passes (not in the currently-failing set) | Powers the entire SELV domain (MCU, safety logic, sensing) |
| 2 | `hb.gate_hs.driver` (U7) | TI UCC21550BDWKR | Certified reinforced dual-channel gate driver | Fails by 0.75mm (footprint-only, out of scope) | Drives both half-bridge IGBT gates from one physical isolator |
| 3 | `ct_sense.ct` (T1) | Coilcraft CST3015-100ED | Current-sense transformer | Passes (9.100mm, exact model) | Senses tank/bus current for OCP |
| 4 | `power_in.bypass_relay` (K1) | Omron G4A-1A-E | SPST relay, mains contacts / SELV coil | Passes (pads regenerated with zero HV copper, dropped out of the HV set) | Shorts the NTC inrush limiter after soft-start |
| 5 | `discharge.k_dis1` (K2) | Omron G5LE-1 | SPDT relay | Fails by 4.441mm (3.559mm measured) | Fail-safe active discharge, +170V half-bus |
| 6 | `discharge.k_dis2` (K3) | Omron G5LE-1 | SPDT relay | Fails by 4.441mm (3.559mm measured) | Fail-safe active discharge, -170V half-bus |
| 7 | `power_in.zcd_opto` (U3) | onsemi H11L1TVM | Schmitt-trigger optocoupler | Fails by 1.980mm on the *committed board*; already fixed in `elec/src` (400-mil footprint), just not regenerated onto the PCB | AC-line zero-cross detection |
| 8 | `power_in.y_cap_pe` (C6) | Y1-class EMI/PE-bonding capacitor | Protective bond (declared here, not under `protective_impedance_chains:`, per the manifest's own capacitor-policy comment) | Fails by 4.800mm (placeholder stub footprint, real part not yet applied) | EMI/PE bonding, IEC 60384-14 Y1 |

### 1b. Protective-impedance chains (`protective_impedance_chains:` block, 2 entries)

| # | Chain | Construction | Feeds | Current status |
|---|---|---|---|---|
| 9 | `ovp01_comparator_divider` | 3x430k (redundant top) + 16.9k bottom, `+170V_BUS` -> `safety.ovp.comp-inp` | TLV3201 hardware comparator (independent-of-MCU OVP trip) | Not in the footprint-fail set (distributed resistors, not one packed footprint) |
| 10 | `ovp01_adc_sense_divider` | 3x169k (redundant top) + 10k bottom, `+170V_BUS` -> `V_BUS_SENSE` | ESP32 ADC (`mcu.adc_v_bus`), telemetry | Same |

**These are legitimate under IEC 60335-1 only because no single component
failure removes the current-limiting function** -- verified directly against
the manifest's own arithmetic (both chains keep touch current 3.5x-10x under
the 1.35mA IEC 60335-2-6 limit even with two of three top resistors shorted).
This is why they reduce differently than #1-8: shortening either chain below
3 elements reintroduces the exact single-point-of-failure defect the ADC
divider's 2026-07-26 fix (510k -> 3x169k) corrected. Any merge proposal below
preserves the >=3-element redundant construction.

**Task-brief cross-check:** the brief's own table names 9 rows by grouping
K2/K3 together; the manifest itself declares them as two independent
`discharge.k_dis1`/`discharge.k_dis2` entries, which is the count this
document uses throughout (10, not 9) since it is what the isolator-barrier
gate and CP-SAT model actually see.

---

## 2. What Is Already Minimal (Verified, Not Assumed) -- No Action Recommended

Two crossings in the inventory above are **already the design applying the
correct "combine" pattern** -- worth stating explicitly, because they are the
precedent the top recommendation below is copied from, not a generic idea
imported from outside this codebase:

- **`ct_sense.ct` (CT1).** The transformer's SELV-side secondary lands on
  exactly one node, `i_sense` (`I_SENSE`), which fans out on the *SELV* side
  (no further barrier crossing) to three independent consumers: the
  hardware `OCPComparator` (fast trip), the MCU's ADC
  (`main.ato:816`, `mcu.adc_i_sense`), and `SafetyInterlock`
  (`main.ato:817`, `safety.i_sense`). **One physical crossing, three
  downstream uses.** This is the exact shape recommendation #1 below asks
  the OVP-01 dividers to copy.
- **`hb.gate_hs.driver` (U7).** One certified reinforced part already
  carries *two* independent PWM channels (`OUTA`/`OUTB`, high-side and
  low-side gate drive) across a single physical barrier, instead of two
  separate single-channel isolators. This is "combine several discrete
  parts into one multi-channel reinforced isolator" already done, for the
  one function in this design (power gate drive) where a multi-channel
  certified part exists off the shelf.

`aux_supply.psu` (powers the whole SELV domain, nothing to combine it with)
and `power_in.zcd_opto` (see Sec 4) are likewise already single-component,
already-minimal implementations of their respective functions. No further
crossing-count action is proposed for any of these four.

---

## 3. Ranked Options

### Option 1 -- Merge the OVP-01 comparator and ADC dividers into one shared chain

**Rank: highest value, lowest cost, immediately actionable.**

**Finding, verified directly in `elec/src/modules.ato`'s `OVPComparator`
module:** the comparator divider (`v_bus.line ~ r_div_top1.p1 ...
r_div_top3.p2 ~ comp.INP`, lines ~2259-2264) and the ADC divider
(`v_bus.line ~ r_adc_top1.p1 ... r_adc_top3.p2 ~ adc_v_bus.line`, lines
~2389-2394) both start at the **exact same node** (`v_bus.line`, i.e.
`+170V_BUS`) and both return to the **exact same reference**
(`power.gnd`). They are two complete, independent, physically separate
protective-impedance chains built from the same HV node to the same SELV
reference, for the sole reason that one feeds a comparator and the other
feeds an ADC.

**Recommendation:** collapse to one shared 3-resistor top chain (preserving
the >=3-element redundant construction the standard clause requires) whose
single SELV-side node is the already-analyzed `safety.ovp.comp-inp` --
domain-manifest already proves this node sits at ~1.4V normal / ~3.6V
worst-case-single-fault, i.e. already established as safe SELV-range. Feed
the comparator from that node exactly as today (unchanged trip math, `r_div_bot`
unchanged), and feed the ADC from the same node (directly, or through a
SELV-side-only anti-alias resistor/filter cap that carries no HV content and
therefore is not itself a barrier crossing).

**What this deletes:** the three `r_adc_top1-3` resistors and the entire
second physical crossing -- `protective_impedance_chains:` count drops from 2
to 1, total declared crossings from 10 to 9. **What is preserved, not
lost:** both functions -- the independent hardware-comparator OVP trip
(unchanged, safety-critical, MCU-independent) and the MCU's bus-voltage
telemetry (same signal, needs its scale factor recomputed against the
16.9k-referenced node instead of its own former 10k-referenced one -- a
firmware constant, not new hardware).

**Open items, not resolved here:** (a) confirm the ESP32-S3 ADC pin's own
input leakage/sample-and-hold loading is negligible against the ~130uA
divider current (expected yes -- ESP32 ADC leakage is nA-scale -- but not
pulled from the datasheet in this pass); (b) confirm the hysteresis
feedback's fast transient (bounded by the existing 619k `r_hyst`) does not
corrupt ADC sampling in a way that matters for telemetry accuracy (standard
analog practice -- small series R + filter cap -- but not designed here);
(c) a fresh single-fault review of the *merged* node, since the existing
per-chain analyses were written for two independent nodes.

### Option 2 -- Merge K2/K3 into one full-bus-bridging relay

**Rank: medium value, medium cost, requires an explicit safety trade-off
sign-off. Realistic, not a slam dunk -- see Sec 4 for the honest verdict.**

Today: `BusDischarge` instantiates two Omron G5LE-1 SPDT relays, each
bridging **its own half-bus to the doubler midpoint** (`hv_plus <-> mid` for
K2, `mid <-> hv_minus` for K3) through its own NC contact and its own 7.8k
resistor string -- confirmed directly from the module (`elec/src/modules.ato`
lines 1159-1163 and the module docstring's own "One relay-switched resistor
string across each 170V half-bus").

**The idea:** replace both with **one** relay whose NC contact bridges
`hv_plus` directly to `hv_minus` (bypassing the midpoint entirely) through
one resistor string. Because the two bulk-capacitor banks sit in series
across that same span, the same discharge current flows through both when
one contact closes end-to-end -- both halves discharge together, not
independently, but neither is skipped.

**Why this is a better "combine" than the one already tried and reverted:**
`docs/evidence/2026-07-28-pd3-retarget-relay.md` already tried consolidating
K2/K3 into a Finder 40.52 **DPDT** (two poles, one coil, one footprint) and
retracted it -- not because combining was the wrong idea, but because that
*specific* DPDT part's real, fixed pin pitch (7.5mm center-to-center,
MEASURED from the manufacturer's own catalog drawing) gives only 5.3mm
edge-to-edge, and no larger-pitch DPDT family (~14.4-14.8mm needed) has been
found or verified. **A full-bus-bridge only needs a single-pole SPDT/SPST
relay** -- the same category as today's individual G5LE-1, not a DPDT --
which means the two already-vetted, already-datasheet-verified candidates
from `docs/evidence/2026-07-28-discharge-relay-isolation.md`
(`AZ770-1C-12D`, 8mm coil-to-contact; `ALZN1B12W`, 10mm) are usable
starting points without a new part search, unlike the DPDT path.

**What this deletes:** one of the two `discharge.k_dis*` isolator
declarations -- 10 crossings to 9, one relay, one footprint, one BOM line
removed.

**What this does NOT get for free, stated plainly (per hard constraint #4 --
be realistic):**
- **Does not reduce the per-pole creepage requirement.** The single combined
  relay still needs the same 10-12.6mm coil-to-contact separation the
  footprint-fix work is already chasing for K2/K3 individually -- this is a
  count reduction, not a geometry reduction.
- **Roughly doubles contact voltage/energy stress.** Today each relay
  breaks ~170V DC; a full-bus bridge breaks the full ~340-400V differential
  on one contact set -- needs its own resistor-string/contact-rating
  re-derivation (not done in this pass) before either candidate part's
  170-200V-duty evaluation can be trusted at the new, higher duty.
- **Trades independent redundancy for a single mechanism.** Today, if K2's
  coil sticks energized (a relay-internal mechanical fault, not a
  power-loss event), only the +170V half loses fast discharge -- the -170V
  half (K3) still discharges actively. With one combined relay, that same
  class of fault takes out fast discharge on *both* halves at once. The
  existing passive 22k bleeders on each half (independent of either relay,
  unchanged by this proposal) remain as the backstop either way -- ~9
  minutes instead of <60s -- so this is not a total loss of discharge
  capability, but it does turn "one relay's internal failure degrades one
  half" into "one relay's internal failure degrades both halves
  simultaneously." **This is the honest cost, and it is a decision the
  project's own risk model has to make, not something this document
  resolves.**

**Fail-safe property (hard constraint #5) check:** preserved for the primary
trigger. Coil de-energized (any loss of power) still closes the NC contact
with zero MCU involvement, exactly as today -- the fail-safe *mechanism* is
unchanged, only the *redundancy against a second, independent relay-internal
fault* is reduced, as described above.

### Option 3 -- HV-side digitizer + one shared reinforced digital isolator (the "sense on the hot side" bullet, taken to its conclusion)

**Rank: highest conceptual ceiling, not verifiable against this repo's
existing gates today -- named per the task's explicit prompt to explore it,
not recommended for near-term adoption.**

The most literal reading of "sense on the hot side and digitize there":
replace `power_in.zcd_opto` (U3) and the OVP-01 protective-impedance
chain(s) with a small HV-referenced (i.e., `PWR_RTN`-referenced) ADC/
comparator front-end that measures AC-line zero-cross and bus voltage
*entirely within the HV domain*, powered from the already-present HV-side
`+15V_LS` rail (an internal-to-HV-domain regulator tap, not a new barrier
crossing), and sends the results to the MCU as one digital serial stream
over **one** certified multi-channel reinforced digital isolator.

**Why this is named but not recommended now:**
- It does not eliminate a barrier crossing so much as **replace several
  with a new one** -- a digital isolator IC is itself a physical part
  subject to the identical creepage requirement every other isolator in
  this inventory is failing today (see U7's own 0.75mm shortfall on an
  already-"Isolated"-branded footprint family for how close to the edge
  even a dedicated isolator package runs).
- It introduces a second active die on the HV side of the barrier (a new
  component class this design does not currently have), its own local
  power derivation, new firmware, and a **new single-fault safety case**
  from scratch -- an HV-side active IC failing does not fail the same way
  a passive resistor divider fails, and nothing in this repo's existing
  evidence chain analyzes that failure mode.
- Per hard constraint #2, this is not verifiable against the repo's own
  existing gates or CP-SAT model today -- it would need to be designed,
  not merely selected, before any of this document's other
  verification-first standards could be applied to it.
- **Even in its fullest realization, the crossing count does not go to 1.**
  Power transfer (`aux_supply.psu`), gate drive
  (`hb.gate_hs.driver`), and mechanical mains switching (`power_in.bypass_relay`,
  the discharge relay(s)) are each doing a physically different job
  (power, drive current, mechanical contact) that a signal-only digital
  isolator cannot substitute for. The realistic floor this direction points
  toward is roughly 5-6 crossings, not 1: aux supply + gate driver + one
  shared sensing/comms isolator + bypass relay + discharge relay(s) + Y-cap.

**Verdict:** worth recording as the direction with the largest theoretical
upside, and worth a dedicated future investigation if the project wants to
pursue it deliberately -- but it is a different-sized project than Options
1-2, and this document does not recommend starting it now.

### Ruled out, kept for the record

**Delete the bypass relay (K1) by leaving the NTC inrush limiter permanently
in circuit.** Checked quantitatively, not assumed: `NTC_Inrush`'s rated cold
resistance is 10 ohm at a 15A continuous branch current
(`elec/src/modules.ato:743-744`, `docs/hardware` branch-current figures) --
continuous dissipation would be on the order of 10ohm x (15A)^2 ~= 2.25kW,
which is not physically viable for a 1.8kW-class appliance. This is exactly
the "do not delete a crossing by deleting a needed function" trap named in
the task brief's hard constraints -- included here so it is not
re-discovered and re-rejected by a future pass.

**Delete or relocate the Y-cap (C6).** `power_in.y_cap_pe` is the design's
IEC 60384-14 Y1 EMI/PE-bonding capacitor -- its function is conducted-EMI
compliance, not something any other crossing in this inventory does or could
absorb. Its current 4.8mm shortfall is a part-sourcing/footprint problem
(wrong placeholder part), already tracked in the sibling footprint document
-- not a crossing-count problem. No deletion proposed.

---

## 4. K2/K3: The Direct Answer to "Is Crossing-Reduction Addressable There At All?"

**Yes, partially, and honestly, not as cleanly as the digital-isolator
cases.** Option 2 above is a real, grounded, board-verifiable reduction (10
crossings to 9, one fewer relay/footprint/BOM line, reusing already-vetted
parts rather than requiring a new part search) -- but it buys that reduction
by (a) not touching the underlying per-pole creepage requirement at all, (b)
introducing a real, quantifiable, currently-unresolved contact-voltage
re-derivation, and (c) trading independent per-half discharge redundancy for
a single mechanism, mitigated but not eliminated by the untouched passive
bleeder backstop. Every one of the manifest's other galvanic isolators
(gate driver, CT, opto) is a signal or power path where "combine" straightforwardly
reduces both count and, often, footprint pressure. K2/K3 is a mechanical
contact gap serving a safety-critical fail-safe function; combining two of
them costs something real (redundancy) that combining two PWM channels in
one gate-driver IC does not. **Realistic verdict: crossing-reduction helps
here, but it is a safety trade-off requiring explicit sign-off, not a free
win** -- reported exactly that way per the task's own instruction not to
oversell a direction.

---

## Requirements

- R1. Combine the OVP-01 comparator-sense and ADC-sense protective-impedance
  dividers (`ovp01_comparator_divider`, `ovp01_adc_sense_divider`) into a
  single shared >=3-element redundant chain from `+170V_BUS`, preserving both
  the independent hardware-comparator OVP trip and the MCU ADC telemetry
  function without degrading either's safety margin. (Option 1)
- R2. Before implementing R1, verify the ESP32-S3 ADC pin's loading does not
  materially shift the TLV3201 comparator's trip voltage, and re-run the
  single-fault analysis for the merged node (currently only analyzed
  per-chain).
- R3. Evaluate (design decision, not committed by this document) merging
  `discharge.k_dis1`/`discharge.k_dis2` into one full-bus-bridging relay,
  contingent on: (a) explicit project sign-off on the discharge-redundancy
  trade-off in Sec 3/Option 2, (b) a fresh contact-voltage/energy-stress
  re-derivation at the doubled (~340-400V) duty, (c) re-verifying that
  `AZ770-1C-12D` or `ALZN1B12W` (or an equivalent) actually meets that
  doubled duty -- their existing verification was done at 170-200V.
- R4. Do not attempt to delete `power_in.bypass_relay`, `power_in.zcd_opto`,
  or `power_in.y_cap_pe` for crossing-count purposes -- each is verified
  necessary and already a minimal single-component implementation of its
  function (Sec 2-3).
- R5. Treat Option 3 (HV-side digitizer + shared digital isolator) as a
  separate, deliberate future investigation, not part of this reduction
  pass -- it is a different-sized project (new active HV-side hardware, new
  firmware, new safety case) than R1-R3.

## Success Criteria

- A human can decide, without re-deriving Sec 1-4, exactly which crossings
  are being proposed for deletion (R1, always a net win), which for merging
  under an explicit trade-off (R3, needs sign-off), and which are
  confirmed necessary and out of scope (R4).
- The distinction between galvanic/mechanical isolators and
  protective-impedance chains is preserved throughout -- no recommendation
  here treats the two as interchangeable or reduces them by the same
  mechanism.
- Nobody re-proposes deleting the bypass relay or re-attempts the
  already-reverted DPDT consolidation for K2/K3 without reading why both
  were rejected/limited here.

## Scope Boundaries

- No `elec/src/*.ato`, `elec/domain_manifest.yaml`, or `pcb/` files were
  modified by this document -- research/requirements only.
- Footprint/geometry fixes for any individual crossing (C6, K2, K3, U3, U7)
  are explicitly out of scope -- see the sibling document
  `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md`.
- Board re-floorplanning, the two-PCB split, and moving the barrier line are
  out of scope per the task's hard constraints; every option above assumes
  the current single-board floorplan.
- The governing creepage millimeter figure (8.0 / 10.0 / 12.0 / 12.6mm,
  currently inconsistent across `clearance.py`, `check_isolation_keepout.py`,
  and `ENVIRONMENTAL_SPEC.md`) is not reconciled here -- noted as a
  pre-existing open item this document's recommendations are insensitive to.
- No CP-SAT re-solve or gate re-run was performed -- R1-R3 are design
  proposals for a human/planning decision, not implemented or verified
  end-to-end in this pass.

---

## Key Decisions

- **Classify before proposing, and keep the two kinds separate throughout.**
  Galvanic/mechanical isolators (Sec 1a) reduce by combining physical
  components (Options 2-3); protective-impedance chains (Sec 1b) reduce by
  sharing the HV-facing element while keeping the redundant construction
  rule intact (Option 1). Treating them the same would either weaken the
  protective-impedance chains' fault tolerance or miss the mechanical
  relays' redundancy trade-off.
- **Ground the "combine" recommendation in a pattern the design already
  uses successfully (CT sense), not an imported generic idea.** This is
  why Option 1 is ranked highest -- it is the same shape the repo's own CT
  circuit already proves works, applied to a place it was not yet applied,
  rather than a novel architecture.
- **Reject the tempting "just make K2/K3 a DPDT" framing** in favor of a
  full-bus-bridge SPDT/SPST, specifically because the DPDT path was already
  tried, measured, and found to need an unfound part family -- the
  full-bus-bridge reuses already-vetted candidates instead.
- **Do not round Option 2's honest cost down to zero.** The redundancy and
  contact-voltage trade-offs are reported in full rather than glossed over,
  per the task's own instruction to be realistic about K2/K3.

## Dependencies / Assumptions

1. **Assumption:** the "crossing count" this document optimizes is the
   count of declared entries in `elec/domain_manifest.yaml`'s `isolators:`
   and `protective_impedance_chains:` blocks (10 today), not a board-area or
   BOM-cost metric that might rank these options differently.
   **Question for the user:** is the manifest's declared-entry count the
   right proxy, or is there a different metric (e.g., total isolation-
   relevant board area, or dollar cost) that should govern ranking instead?
2. **Assumption:** tying the ADC input to the OVP-01 comparator's already-
   analyzed `comp-inp` node (Option 1) does not introduce a new safety-
   relevant single-fault path beyond what the existing per-chain analyses
   cover. **Question for the user:** is the existing single-fault analysis
   (written per-chain) an acceptable basis to extend to the merged node by
   inspection, or does the project want a from-scratch fault-tree pass
   before this is implemented?
3. **Assumption:** ESP32-S3 ADC input leakage/sampling behavior is
   negligible against the ~130uA divider current in the merged OVP node.
   **Not verified in this pass** -- flagged as a concrete pre-implementation
   check (R2), not assumed safe by default.
4. **Assumption:** trading K2/K3's independent per-half discharge redundancy
   for a single combined mechanism (Option 2) is an acceptable safety
   posture, given the untouched passive-bleeder backstop remains on both
   halves regardless. **This is explicitly the user's call, not decided
   here** -- see the Outstanding Question below.
5. **Assumption:** the governing creepage millimeter figure's current
   inconsistency (8.0/10.0/12.0/12.6mm across three files) does not change
   which crossings this document recommends deleting or merging, since
   deletion/merging helps regardless of the exact target. **Not fully
   verified** -- a sufficiently large future correction to the target could
   in principle change relative priority (e.g., if the target rose enough
   that even Option 1's merged single chain became geometrically
   constrained in a way today's spread-out resistor placement is not) but
   no such effect is expected for a resistor-chain protective-impedance
   crossing, which is not packed into one component footprint the way K2/K3
   or U3 are.

## Outstanding Questions

### Resolve Before Planning

- [Affects R3][User decision, safety-critical] Is trading K2/K3's
  independent per-half discharge redundancy for a single combined
  full-bus-bridge relay (Option 2) an acceptable safety posture for this
  product, given the passive 22k bleeder backstop is unchanged and remains
  independent on both halves? This is the central trade-off Sec 4's honest
  verdict turns on, and this document does not decide it.
- [Affects R1/R2][Needs research] ESP32-S3 ADC pin input leakage and
  sample-and-hold loading, to confirm sharing the OVP comparator's sense
  node with the MCU ADC does not shift the hardware trip point.
- [Affects R3][Needs research] Contact-voltage/energy-stress re-derivation
  for a single relay bridging the full ~340-400V bus differential
  (roughly double today's per-relay ~170-200V duty), and whether
  `AZ770-1C-12D`/`ALZN1B12W` (already vetted at the lower duty) still
  clear it.
- [Affects R5][User decision, scope] Does the project want to open Option 3
  (HV-side digitizer + shared reinforced digital isolator) as its own,
  separately-scoped investigation, or leave it recorded here as a future
  direction only?

### Deferred to Planning

- [Affects R1][Technical] Firmware-side ADC scale-factor recalculation once
  the OVP dividers are merged (16.9k-referenced node instead of the ADC's
  former independent 10k-referenced node).
- [Affects R3][Technical] New `Relay_SPST`/`Relay_SPDT`-equivalent
  `components.ato` definition and KiCad footprint for whichever
  full-bus-bridge relay candidate is chosen, plus the discharge-resistor
  string re-sizing for the doubled duty.
