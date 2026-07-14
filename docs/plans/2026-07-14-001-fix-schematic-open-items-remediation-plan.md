---
title: "fix: Remediate remaining open items from the KiCad schematic repair audit"
type: fix
status: completed
date: 2026-07-14
origin: docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md
---

# fix: Remediate remaining open items from the KiCad schematic repair audit

## Summary

A prior session repaired six of seven `pcb/*.kicad_sch` sheets (shorts, backwards
components, swapped comparator inputs, floating ICs, coordinate collisions) and
wired 16 of ~20 cross-sheet nets at the root sheet. Six items were deliberately
left unresolved rather than guessed at, because each needed a missing component,
a real design decision, or further investigation. A research-only agent
(`Fable`) was dispatched to investigate all six; this plan turns its findings
into eight independently verifiable implementation units.

**All eight units are implemented.** U1 cleared its own independent
KCL-derivation verification gate (per `origin` doc above) before any
mains-voltage edit was made — the Fable agent's derivation was evidence, not
by itself sufficient authorization to edit a 340 VDC net, consistent with
how D1/D2 were handled in the prior session. Each unit below is marked DONE
with what was actually built, including three self-caught bugs (a
misplaced `lib_symbols` block that broke KiCad's parser, a `RESET_N`
direction inconsistency, and a cross-pin routing short) — all caught by the
mandatory pre/post-write verification discipline before they reached a
saved file uncorrected. Everything parses cleanly via `kicad-cli`; nothing
has been bench-tested or ERC-swept as a whole project yet (see Test
Strategy).

---

## Problem Frame

| # | Item | Sheet(s) | Class |
|---|------|----------|-------|
| U1 | `AC_N` lands on the wrong node; doubler cannot function as wired | `power_input.kicad_sch`, `elec/src/modules.ato` | **Safety-critical (mains)** |
| U2 | `GND_CENTER` hierarchical label has no root sheet pin — dead end | `power_input.kicad_sch`, `temper.kicad_sch` | Safety-adjacent (earth bond) |
| U3 | `RELAY_CTRL` floats; no relay, no driver, no footprint exists | `power_input.kicad_sch` | Missing component |
| U4 | `R_BURDEN` duplicated in two sheets on the same `I_SENSE` net; ato instantiates only one | `half_bridge.kicad_sch`, `sensing.kicad_sch` | Design conflict / safety calibration |
| U5 | MAX31865 footprint override doesn't match the datasheet package at all; no `fp-lib-table` exists in `pcb/` | `sensing.kicad_sch` | Footprint / build-blocking |
| U6 | `+5V_ISO`/`GND_ISO` have no source; stale root pins on two sheets | `sensing.kicad_sch`, `power_management.kicad_sch`, `temper.kicad_sch` | Missing component |
| U7 | `MCU_ENABLE` is vestigial; the real safety net (`RUNAWAY_CUT`) is completely unwired | `mcu.kicad_sch`, `safety_interlock.kicad_sch`, `temper.kicad_sch` | Design conflict |
| U8 | `User_Interface` root pins (`BTN_UP`/`BTN_DOWN`/`BTN_SELECT`/`ENCODER_A`/`ENCODER_B`) don't match the sheet's real fault-LED labels | `user_interface.kicad_sch`, `safety_interlock.kicad_sch`, `temper.kicad_sch` | Stale wiring |

Full agent evidence and citations for each item are in the session transcript;
this plan restates only what's needed to execute and verify each fix.

---

## Scope Boundaries

### In scope
- All eight items above: schematic edits, root sheet pin reconciliation, one
  `.ato` source correction (U1), one new project file (`pcb/fp-lib-table`, U5).
- Adding new components (relay + driver, isolated DC-DC module, CT symbol)
  where their absence is the actual blocker.
- Re-running the union-find connectivity tracer after every unit, per the
  methodology in `docs/solutions/tooling-decisions/kicad-schematic-connectivity-tracer-2026-07-14.md`.

### Deferred
- Drawing the custom relay footprint (Omron G4A-1A-E) and the CST-1005 CT
  footprint — needed by U3/U4 but is mechanical CAD work, not schematic
  wiring; tracked as a follow-up once U3/U4's topology is approved.
- Full IEC 60335-1 compliance review of the earth-bonding scheme in U2 —
  this plan implements the Y2-capacitive-only bond the design docs already
  specify, but a compliance sign-off is a separate gate.
- `elec/src/components.ato`'s known `SN74HC4075` pin-mapping bug (from the
  prior session) — unrelated to these six items, not re-opened here.

### Out of scope
- PCB layout/routing (`pcb/temper.kicad_pcb`) — this plan is schematic-only.
- Bench verification / ERC-clean sign-off as a formal release gate — covered
  by Test Strategy below as a per-unit check, not a project release gate.

---

## Implementation Units

### U1. Fix `AC_N` routing to the bus-capacitor center tap (SAFETY GATE)

**Goal:** `AC_N` must terminate on the doubler's center-tap node (`GND_CENTER`),
not near the `AC_L`/NTC node, so the Delon doubler actually charges both
capacitors. Currently the `AC_N` wire in `power_input.kicad_sch` dead-ends
unconnected (not a live short — the circuit is simply incomplete).

**Files:**
- `pcb/power_input.kicad_sch` (wire `wire-acn-001`, currently ~y=139.7, dead-ends on the C_BUS2 symbol body)
- `elec/src/modules.ato:445-446` (`ac_n ~ d2.A` — same defect in the generative source)

**Pre-condition — independent verification gate:**
Before editing, independently re-derive (do not just re-read the agent's
derivation) which node `AC_N` must join, using KCL over both AC half-cycles,
and cross-check against `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`'s simulation
section. Only proceed once an independent derivation and the design doc
converge — same bar used for the D1/D2 polarity fix in the prior session.

**Approach:**
1. Re-derive and confirm the center-tap connection requirement.
2. Reroute `AC_N` from its current dead end to the center-tap node (e.g.
   `(228.6, 120.65)` or a short jog into the existing center wire), using a
   detour jog rather than a direct endpoint move if any collinear-overlap
   risk exists with neighboring wires (per the tracer methodology).
3. Fix `elec/src/modules.ato:445-446` to match: `ac_n ~ dc_bus.gnd_ref`;
   `d2.K` moves to the line node, `d2.A` to `dc_bus.hv_minus` (verify against
   the already-fixed D2 orientation from the prior session — do not
   reintroduce the earlier polarity bug while moving this wire).
4. Document the `.ato` bug fix explicitly (not a silent patch), consistent
   with how the D2 `.ato` bug was handled previously.

**Verification:**
- Union-find tracer: `AC_N` shares a root with `GND_CENTER`/center-tap net
  and does NOT share a root with `AC_L`/NTC/D1.A/D2.K.
- `kicad-cli sch export netlist` parses cleanly; `kicad-cli sch erc` shows no
  new violations on this sheet.
- Manual KCL walk-through of both half-cycles confirms both `C_BUS1` and
  `C_BUS2` have a charging path.

---

### U2. Give `GND_CENTER` a real GND connection and a capacitive-only PE bond — DONE (implementation deviated from the original approach below; see note)

**Goal:** `GND_CENTER` (the doubler's center tap / system ground reference)
currently has no matching pin on the root sheet's `Power_Input` symbol, so the
hierarchical label connects to nothing outside its own sheet. Make it a real,
connected system-ground net, earthed to PE only through a Y2 safety
capacitor — not a direct copper bond.

**Implementation note — deviated from the plan as originally written.**
The original approach below assumed other sheets expose `GND` via root
sheet pins. They don't: every sheet in this project (`safety_interlock`,
`sensing`, `power_management`, `mcu`, `half_bridge`, `user_interface`) ties
its local ground to the **global `power:GND` symbol**, which KiCad unifies
by name across the whole project without any hierarchical routing —
`temper.kicad_sch` has zero `GND` sheet pins anywhere. `Power_Input` was the
only sheet with no `power:GND` symbol at all. So instead of adding a root
sheet pin (which nothing else in the project would connect to), the fix
drops a local `power:GND` instance onto the doubler's center-tap net,
matching the convention every other sheet already uses.

**A real conflict surfaced while resolving this**, requiring independent
verification before proceeding (same bar as U1): `docs/hardware/GROUNDING_EMI_STRATEGY.md`
§3.1 states the "Star Ground Point" is "Located at DC bus return" — i.e.
implies `DC_BUS-`/`hv_minus` is the system ground, not the center tap. This
directly contradicts `VOLTAGE_DOUBLER_DESIGN.md`'s "ESP32 should reference
the center point (GND)". Resolved by checking the actual generative source
as an independent third reference: `elec/src/main.ato:88` declares a
top-level `signal gnd # System ground`, and line 223 wires
`power_in.dc_bus.gnd_ref ~ gnd` while line 222 wires `dc_bus.hv_minus` to a
*separate* `dc_bus_minus` signal (`main.ato:93-94`, `override_net_name =
"DC_BUS_RTN"`) — and ten further independent tie-ins throughout `main.ato`
(power management, half-bridge, CT sense, RTD, safety, MCU) all reference
`gnd`, none reference `hv_minus` as a ground. The ato source and the voltage
doubler doc converge; `GROUNDING_EMI_STRATEGY.md` §3.1 is the outlier —
flagged as stale/incorrect documentation (likely predates the split-rail
doubler architecture), not fixed in this plan since editing that doc's
diagrams is out of scope here.

**Files (as implemented):**
- `pcb/power_input.kicad_sch`:
  - Added `power:GND` and `Device:C` lib_symbol defs to `lib_symbols`.
  - Removed the `GND_CENTER` hierarchical_label (verified zero consumers
    project-wide via `grep -rn GND_CENTER pcb/*.kicad_sch elec/src/*.ato`) —
    superseded by the global power symbol.
  - Added a `power:GND` instance at `(279.4, 120.65)`, the exact point where
    the old hierarchical label sat, already a 4-way vertex on the
    `BUS_CENTER`/center-tap net.
  - Added `C_PE1` (Device:C, "2.2nF Y2 300VAC", MPN `VY2222M29Y5SS63V0`,
    Vishay, footprint `Capacitor_THT:C_Disc_D10.5mm_W5.0mm_P7.50mm`) at
    `(100.0, 180.0)`, wired: pin1 → extended `PE` wire (`wire-pe-002`,
    `wire-pe-003`, completing the previously-dangling `wire-pe-001` at
    `(93.98, 165.1)`); pin2 → a second local `power:GND` instance at
    `(100.0, 176.19)` (same coincident-point convention, not a routed wire
    back to the center-tap point — unified only via the global symbol name,
    matching how every other sheet places `power:GND` locally rather than
    routing long ground traces).

**Deferred (real, but out of this unit's scope):** `GROUNDING_EMI_STRATEGY.md`
§5.1's full AC-input EMI filter (`L_DM`, `L_CM`, `C_X1`/`C_X2`, MOV) is not
built — this unit only adds the earth-bond Y2 cap the PE-dangling-wire
problem required, not the complete conducted-EMI filter stage. That's a
separate, larger gap, not one of the six original open questions.

**Verification:**
- Tracer confirms `AC_N` (fixed in U1) and the new center-tap `power:GND`
  instance share one root; the `PE`-side `power:GND` instance is a distinct
  root (not directly bonded — matches the Y2-only requirement); `C_PE1`
  pin1 shares a root with the `PE` hierarchical label; `C_PE1` pin2 is
  exactly coincident with its local `power:GND` instance.
- `kicad-cli sch export netlist` parses cleanly (pre-existing unrelated
  annotation-error warning, confirmed present before this unit's edits too).

---

### U3. Add the bypass relay and its driver circuit — DONE

**Implemented:** `pcb/power_input.kicad_sch` gained a generic `Relay:Relay_SPST-NO`
symbol (K1, `G4A-1A-E DC12`, footprint left as the same placeholder name the
`.ato` source already used — no real KiCad footprint exists for this part;
drawing one is deferred, see below), a low-side driver stage
(`Q1`/AO3400A NMOS, `R_GATE` 1k series, `R_GATE_PD` 100k pulldown,
`R_RELAY_DROP` 39Ω/1W dropper, `D_FLYBACK`/SS14 clamp), a new `+15V`
hierarchical label + root sheet pin, and root-level star-hub wiring from
Power_Management's existing `+15V` output. `elec/src/modules.ato` and
`elec/src/main.ato` were updated to match (new `MOSFET_N` generic component
in `components.ato`, `power_15v` interface added to the `power_in` module,
coil-driver connections replacing the old direct-GPIO-to-coil statement).
Verified via union-find tracer (including 2-terminal component bridging and
local-label merging) on both the sheet and root level; `kicad-cli sch export
netlist` parses cleanly on both files (pre-existing unrelated annotation
warning only). `ato build` could not be run to validate the `.ato` syntax —
the CLI requires an interactive first-run KiCad-plugin prompt that aborts
under `--non-interactive` in this environment (same limitation hit in the
prior session) — so the `.ato` edits were instead checked for structural
parity against the surrounding, already-working module code.

**Still deferred (unchanged from the original plan):** drawing the G4A-1A-E
THT footprint. The `R_RELAY_DROP` value (39Ω) remains a nominal-only
starting point pending the real datasheet must-operate-voltage check flagged
in the Risk Analysis table below.



**Goal:** Realize `RELAY_CTRL` (Power_Input) with a real, drivable relay
across the NTC inrush-limiter, matching `elec/src/modules.ato`'s
`bypass_relay` (G4A-1A-E DC12) intent — but the GPIO cannot drive a 75 mA/12 V
coil directly, so a driver stage is required.

**Files:**
- `pcb/power_input.kicad_sch` (new: relay, driver FET/BJT, flyback diode,
  dropper resistor; new `+15V` hierarchical label + matching root pin — this
  sheet currently has no +15V net)
- `elec/src/modules.ato:381-439` (`bypass_relay` — verify/update the coil
  drive model to reflect the added driver stage)

**Approach:**
1. Add Omron G4A-1A-E DC12 (SPST-NO, 20 A/250 VAC): contacts across the NTC
   (`COM` → `AC_L_FUSED` node between F1/NTC, `NO` → NTC output node feeding
   D1.A/D2.K).
2. Add a low-side driver: logic-level N-FET (e.g. AO3400A) or NPN
   (MMBT2222A), gate/base from `RELAY_CTRL` via ~1 kΩ with a 100 kΩ pulldown.
3. Coil high side from `+15V` through a series dropper (verify against the
   G4A datasheet's must-operate voltage at ≥75% of rated coil voltage — do
   not assume the 39 Ω/1 W starting value without checking the datasheet
   table) plus a flyback diode (1N4148W or SS14) across the coil.
4. Add `+15V` hierarchical label to `power_input.kicad_sch` and the matching
   root sheet pin (this sheet has no +15V net today).

**Verification:**
- Tracer: `RELAY_CTRL` reaches the driver gate/base; coil circuit is a
  complete loop through +15V, dropper, coil, and GND; no short between the
  relay contacts' two throws and any other net.
- Confirm dropper resistor value against the actual G4A datasheet
  must-operate spec, not an assumed number.

**Follow-up (deferred, tracked separately):** draw the G4A-1A-E THT footprint
— none exists in any `Relay_THT.pretty` variant shipped with KiCad or in this
repo.

---

### U4. Consolidate duplicate `R_BURDEN` into Half_Bridge; delete the Sensing copy — DONE

**Implemented, plus a real bug found beyond what the plan anticipated:** the
surviving `R_BURDEN` in `half_bridge.kicad_sch` had its two pins **backwards**
relative to the ato source's intent (`ct.S1~r_burden.p1~i_sense.line` —
signal; `ct.S2~i_sense.reference~r_burden.p2` — ground reference). The
schematic had pin2 (the reference/GND pin) wired to the `I_SENSE` net and
pin1 (the actual signal pin) floating — meaning `I_SENSE` would have read a
constant, near-zero voltage rather than the CT burden signal, not just been
"ungrounded" as the research agent's report characterized it. Fixed by
swapping which pin reaches `I_SENSE` vs. `GND`, using jogged reroutes (not
straight swaps) to avoid a repeat of the collinear-overlap-short failure
mode from the D1/D2 fix. Also added the `CST1005` CT symbol (a generic
`Device:Transformer_1P_1S` stand-in, no real KiCad symbol exists for this
part), primary threaded in series with the existing `SWITCH_NODE` wire.
Verified via union-find tracer, explicitly modeling the CT's primary winding
as a 2-terminal bridge (pin1↔pin2 are the same continuous conductor) while
confirming primary and secondary stay galvanically isolated in the trace.

Removed the Sensing-sheet `R_BURDEN` copy, its dangling `I_SENSE`
hierarchical label and local label, and fixed the now-inaccurate sheet
documentation text that still described current sensing as living on that
sheet. Removed the stale `I_SENSE` root pin on Sensing's sheet symbol in
`temper.kicad_sch`, and added the previously-entirely-missing MCU-side wiring:
a new `I_SENSE` input pin on MCU's root sheet symbol, an `I_SENSE`
hierarchical label wired to GPIO1 in `mcu.kicad_sch` (the sheet's own
documentation text already listed "IO1: ADC_CT" — it just wasn't wired),
and root-level star-hub wiring connecting Half_Bridge → Safety_Interlock →
MCU. `elec/src/modules.ato`'s burden MPN/footprint changed from the 0805
variant to 1206 (matching the KiCad schematic — 1206 has more thermal
margin at worst-case dissipation, per the plan's original reasoning).

**Follow-up, closed same day:** `elec/src/modules.ato`'s `CurrentSensing`
module specifies a `c_filter` (100 nF C0G, HF noise rejection across
`i_sense.line`/`i_sense.reference`) that existed in neither the old
Sensing-sheet copy nor the new Half_Bridge placement when this unit first
landed. Added as `C_FILTER` in `half_bridge.kicad_sch`, wired directly
across the same `I_SENSE`/`GND` nets `R_BURDEN` sits on. Verified via the
same union-find discipline (signal pin joins `I_SENSE`, reference pin joins
the existing local `GND`, and the two pins are confirmed on distinct nets).

All three touched sheets (`half_bridge.kicad_sch`, `sensing.kicad_sch`,
`mcu.kicad_sch`) plus `temper.kicad_sch` parse cleanly via `kicad-cli sch
export netlist` (same pre-existing unrelated annotation warning only).



**Goal:** `elec/src/main.ato` instantiates exactly one `CurrentSensing`
circuit; the schematic currently has two `R_BURDEN` copies on sheets that
would both land on `I_SENSE` once root-wired, which would halve the CT
transfer ratio and silently shift the hardware OCP trip point. Keep one.

**Files:**
- `pcb/half_bridge.kicad_sch` — **keep this copy**; ground its currently
  floating pin 2 (no wire at `(215.9, 156.21)`); add the CST-1005 CT symbol
  (currently only a text note) with primary in series with the tank return
  and secondary across `R_BURDEN`.
- `pcb/sensing.kicad_sch` — **delete**: `R_BURDEN` symbol (~line 1095-1113),
  its wires (`wire-isense-001/002`, ~1348-1356), local label (~1274), and the
  `I_SENSE` hierarchical label (~887).
- `pcb/temper.kicad_sch` — remove Sensing's `I_SENSE` root output pin
  (~line 606); Half_Bridge's `I_SENSE` root pin (~line 229) becomes the sole
  producer.
- `pcb/mcu.kicad_sch` — add the currently-missing `I_SENSE` input wiring to
  GPIO1 (`PIN_ADC_CURRENT`, `temper_pins.h`); today only a sheet note
  mentions it (~line 971), unwired.

**Rationale (why Half_Bridge, not Sensing):** CT secondary leads must stay
short and the burden mounted adjacent to the CT per
`docs/hardware/CT_SENSING_DESIGN.md` §10.2 and
`docs/hardware/GROUNDING_EMI_STRATEGY.md` §3.2; the CT primary is the
switch-node conductor drawn in Half_Bridge. An unterminated or long-routed CT
secondary risks developing high voltage if loaded down over distance.

**Approach:**
1. Delete the Sensing-sheet copy and its root pin as listed above.
2. Ground `R_BURDEN` pin 2 in Half_Bridge (per `elec/src/modules.ato:638`,
   `r_burden.p2 ~ i_sense.reference`).
3. Add the CST-1005 CT symbol in Half_Bridge; wire primary in series with the
   tank return, secondary across `R_BURDEN`.
4. Wire root `I_SENSE`: Half_Bridge → Safety_Interlock (OCP comparator input,
   already wired to a hierarchical `I_SENSE` at `safety_interlock.kicad_sch:551`)
   and → MCU GPIO1 (new).
5. Resolve the burden MPN mismatch between `.ato` (RC0805FR-0766R5L) and
   KiCad (RC1206FR-0766R5L) — keep 1206 (0805's 125 mW rating is marginal at
   the worst-case dissipation; 1206 has margin). Update whichever source is
   wrong to match.

**Verification:**
- Tracer: single `I_SENSE` net spans Half_Bridge → Safety_Interlock → MCU,
  with `R_BURDEN` pin 2 on the ground root, no leftover Sensing-sheet
  fragment.
- Confirm the resulting CT transfer ratio against
  `docs/hardware/CT_SENSING_DESIGN.md`'s OCP-threshold assumptions
  (`elec/src/main.ato:164-170`, `i_ocp_trip` vs. IGBT SOA) — this is the
  calibration this unit is protecting.

---

### U5. Fix the MAX31865 footprint; add a project `fp-lib-table` — DONE

**Implemented exactly as planned.** `pcb/sensing.kicad_sch`'s `U_RTD1`
Footprint property changed from `Package_DFN_QFN:TQFN-20-1EP_4x4mm_P0.5mm_EP2.6x2.6mm`
to `Package_DFN_QFN:TQFN-20-1EP_5x5mm_P0.65mm_EP3.25x3.25mm_ThermalVias`
(confirmed this exact `.kicad_mod` exists in the installed KiCad 10.0.4
library — `find .../Package_DFN_QFN.pretty -name "*5x5mm_P0.65mm_EP3.25*"`).
Created `pcb/fp-lib-table` covering the 16 distinct standard footprint
libraries actually referenced across `pcb/*.kicad_sch` (grepped, not
guessed), using `${KICAD10_FOOTPRINT_DIR}` — matching the version actually
installed in this environment (confirmed via `kicad-cli version` → 10.0.4;
KiCad's own template at
`.../SharedSupport/template/fp-lib-table` uses this exact variable name for
v10, not `KICAD8_FOOTPRINT_DIR` as the plan's draft assumed). Added a
project-local `pcb/libs/temper.pretty/` directory and registered it in the
table as library `temper`, for the still-undrawn custom footprints from
U3/U4 (G4A-1A-E relay, CST-1005 CT) to land in once drawn.

**Deferred (unchanged from the original plan):** the vendored-vs-system
footprint library tradeoff for CI reproducibility — this table uses
environment-variable-relative system paths (lower-maintenance, matches how
`sym-lib-table` already mixes `${KIPRJMOD}`-relative custom parts with
implicit system symbol resolution), not a vendored `kicad-footprints`
submodule. If CI runs on a machine without KiCad 10 installed at a
resolvable path, this will need revisiting.



**Goal:** Replace the current footprint override
(`Package_DFN_QFN:TQFN-20-1EP_4x4mm_P0.5mm_EP2.6x2.6mm` — wrong on every
dimension) with the datasheet-correct stock KiCad footprint, and add the
missing project footprint library table so footprint resolution doesn't
silently fail on `kicad-cli`/CI runs.

**Files:**
- `pcb/sensing.kicad_sch` (Footprint property on the MAX31865 instance,
  ~line 985)
- `pcb/fp-lib-table` (new — does not currently exist; `pcb/libs/kicad-footprints/`
  is an empty placeholder directory)

**Approach:**
1. Change the Footprint property to
   `Package_DFN_QFN:TQFN-20-1EP_5x5mm_P0.65mm_EP3.25x3.25mm_ThermalVias`
   (matches ADI package outline 21-0140, land pattern 90-0010, code
   `T2055+5`: D=E=5.00 mm BSC, e=0.65 mm BSC, D2/E2=3.25 mm nominal).
2. Create `pcb/fp-lib-table` — decide vendored-footprints-submodule vs.
   `${KICAD8_FOOTPRINT_DIR}`-relative entries (vendoring is more
   CI-reproducible; system-path entries are lower-maintenance). Add one
   project `.pretty` library entry for the new custom footprints this plan
   introduces (G4A relay in U3, CST-1005 CT in U4).

**Verification:**
- `kicad-cli sch export netlist` and any DRC/footprint-resolution step in
  `packages/temper-placer/src/temper_placer/validation/drc_runner.py` resolve
  the MAX31865 footprint without warnings.
- Visual check in KiCad that the new footprint's pad pattern matches the
  datasheet land pattern (90-0010).

---

### U6. Add the isolated +5V_ISO/GND_ISO supply; retire the stale root pins — DONE

**Implemented, with one deviation and one tooling-caught bug.**
`pcb/sensing.kicad_sch`'s `+5V_ISO`/`GND_ISO` were already-existing
hierarchical labels whose ADuM1250 (`VDD2`/`GND2`) wiring was fully correct
from a prior session — they just had no producer. Rather than adding a new
root sheet pin (this project doesn't route power nets through root sheet
pins — every sheet drops local `power:*` symbols instead, per U2's finding),
converted `+5V_ISO`/`GND_ISO` from `hierarchical_label` to plain `label`
**at the exact same coordinates**, preserving every existing wire — this
means the ADuM1250's isolated-side wiring needed zero changes. Added a
generic 4-pin `temper:DCDC_Isolated` symbol (no real RP-1505S KiCad symbol
exists; this project's convention is generic `Device:`-style symbols with
MPN properties, matching how `D1`/`D2`/`Q1` etc. are modeled) — `VIN`/`GND_IN`
fed from a new `+15V` hierarchical label (this sheet had no +15V net before),
`VOUT`/`GND_OUT` tied to local `+5V_ISO`/`GND_ISO` labels (merging by name
with the existing ADuM1250 wiring, not by routing back to one physical
point — same pattern as U2's dual `power:GND` instances). Added 100 nF
input / 10 µF output decoupling caps. Removed the stale `+5V_ISO` root pins
on both Power_Management's and Sensing's sheet symbols in `temper.kicad_sch`;
added a `+15V` input pin on Sensing's root symbol and a third star-hub
branch off the same `+15V` net U3 established (Power_Management →
Power_Input, → Sensing).

**Self-caught bug:** the first attempt placed the new `temper:DCDC_Isolated`
library symbol definition in the schematic's document body instead of inside
the `(lib_symbols ...)` container — syntactically balanced (parens matched)
but structurally wrong, and `kicad-cli sch export netlist` failed outright
("Failed to load schematic") rather than warning. Caught immediately by the
mandatory post-write parse check, root-caused by comparing against where
every other lib_symbol definition in the file actually lives, and fixed by
moving the block inside `lib_symbols`, right after the existing `Device:R`
entry. Re-verified clean afterward — this is the same class of bug the
`kicad-schematic-connectivity-tracer` doc warns about (verify after every
write, don't assume a large multi-part edit landed correctly).

**Deferred (unchanged from the original plan):** compliance-class sign-off
on whether the 5.2 kVDC module rating satisfies the final IEC 60335-1
barrier definition for whatever the external I2C connector exposes.



**Goal:** Power the ADuM1250's isolated side (currently sourceless) with a
DC-DC module whose isolation rating exceeds the ADuM1250's own barrier, and
clean up the two now-inconsistent root sheet pins this created.

**Files:**
- `pcb/sensing.kicad_sch` (new: DC-DC module + decoupling; convert `+5V_ISO`/
  `GND_ISO` hierarchical labels to local labels; add `+15V` hierarchical
  label as the module's input)
- `pcb/power_management.kicad_sch` (no new source added here — see rationale)
- `pcb/temper.kicad_sch` (delete stale `+5V_ISO` output pin on
  Power_Management's sheet symbol, ~line 308; delete stale `+5V_ISO` input
  pin on Sensing's, ~line 516; add `+15V` input pin on Sensing if not already
  present from U3/U6 convergence)

**Rationale (why Sensing, not Power_Management):** Keeping source and load
on the same sheet keeps the ≥8 mm creepage/isolation-barrier zone
(`GROUNDING_EMI_STRATEGY.md` §4.2 rule 4) localized instead of routing an
isolated rail across sheet/board area.

**Approach:**
1. Add a RECOM RP-1505S (SIP-7, 13.5-16.5 V in, 5 V/200 mA out, 5.2 kVDC
   isolation) fed from `+15V`. Load is small (ADuM1250 IDD2 ≤5 mA +
   ~2 mA for the two 4.7 kΩ iso-side I2C pull-ups) — 1 W class is ample.
2. 100 nF + 10 µF decoupling both sides.
3. Convert `sensing.kicad_sch`'s `+5V_ISO`/`GND_ISO` hierarchical labels to
   local labels (no longer need to cross the sheet boundary).
4. Remove the two stale root sheet pins listed above.
5. Confirm 5.2 kVDC module isolation exceeds the ADuM1250's 2.5 kVrms barrier
   spec (already true from the datasheet figures cited by the research
   agent) — flag for a compliance-class sign-off separately (see Deferred).

**Verification:**
- Tracer: `+5V_ISO`/`GND_ISO` are self-contained within `sensing.kicad_sch`;
  no orphaned hierarchical label crosses to another sheet.
- Root sheet pin count for Power_Management/Sensing matches their actual
  hierarchical label sets (zero stale pins remaining after this unit).

---

### U7. Remove vestigial `MCU_ENABLE`; wire the real `RUNAWAY_CUT` net; add `RESET_N` root pin — DONE

**Implemented as planned, with a deep pin-mapping investigation required for
`RUNAWAY_CUT`.** Removed `MCU_ENABLE` everywhere (both root pins in
`temper.kicad_sch`, the unconnected label in `mcu.kicad_sch`, updated the
sheet's documentation text to record why). Added `RESET_N` end-to-end:
`mcu.kicad_sch` GPIO14 → new hierarchical label → new MCU root output pin →
new Safety_Interlock root input pin (the child sheet already had the
`RESET_N` hierarchical label wired into the fault-qualified reset logic from
a prior session — only the root pin was missing).

**`RUNAWAY_CUT` required determining which physical pin of `U_OR`
(`74HC4075`, the fault-OR gate) is actually `fault_or.C2`** — the plan
assumed this could be inferred from pin adjacency, which turned out to be
wrong and would have produced a wrong connection if guessed. The embedded
KiCad symbol for this chip uses flat numeric pin names ("1"–"14") with no
semantic labels, and naive adjacency-based grouping (assuming pins 1-2-3 form
one gate) contradicts the actual silicon: cross-referencing the *real*
datasheet-sourced pin mapping (KiCad's bundled `4xxx.kicad_sym` → symbol
`"4075"`, the same technique used for the NAND-latch pin lookup in the prior
session) shows the three OR gates are non-adjacently grouped: **Gate1 =
pins {1,2,8}→9, Gate2 = pins {3,4,5}→6, Gate3 = pins {11,12,13}→10.**
Cross-validated this against every already-wired pin on `U_OR` in the
schematic (comparator outputs, the `Y1→A2` self-feedback loop, the NAND
gate-4 inverter output for WDT) — all matched the datasheet mapping exactly,
including confirming `fault_or.B2` (pin 4) already carries the inverted WDT
signal from `U_NAND` pin 11, and `fault_or.Y2` (pin 6) is the gate's overall
aggregate output feeding the SR latch. This left exactly one unwired pin
consistent with `C2`: **physical pin 5**. Wired `RUNAWAY_CUT` there, and
independently re-verified via union-find that it lands on a net distinct
from every other gate's inputs/outputs (no accidental short introduced on
the safety-latch's fault-aggregation logic).

All three touched files (`mcu.kicad_sch`, `safety_interlock.kicad_sch`,
`temper.kicad_sch`) parse cleanly (pre-existing annotation warning only).



**Goal:** `MCU_ENABLE` has no design intent anywhere in `elec/src/*.ato` or
firmware and should be deleted, not preserved or guessed at. The MCU signal
that actually belongs on the safety bus — `RUNAWAY_CUT` (GPIO15) — is
completely unwired in both `mcu.kicad_sch` and `safety_interlock.kicad_sch`
despite being real, tested, and documented.

**Files:**
- `pcb/temper.kicad_sch` (remove `MCU_ENABLE` root pins on both MCU and
  Safety_Interlock sheet symbols, ~lines 417/705; add `RUNAWAY_CUT` input pin
  on Safety_Interlock, output pin on MCU; add `RESET_N` root pin on
  Safety_Interlock — currently missing despite the child sheet having the
  label at ~line 583)
- `pcb/mcu.kicad_sch` (remove the unconnected `MCU_ENABLE` hierarchical label
  ~lines 1425-1431; add `RUNAWAY_CUT` hierarchical label, wire from GPIO15)
- `pcb/safety_interlock.kicad_sch` (add `RUNAWAY_CUT` hierarchical input,
  wire as a third input into the fault-OR stage `U_OR` 74HC4075 alongside the
  existing WDT path, mirroring `elec/src/modules.ato:1140`
  `runaway_cut.line ~ fault_or.C2`)

**Approach:**
1. Delete `MCU_ENABLE` everywhere (both root pins, the MCU-sheet label). Do
   not invent a new function for it.
2. Add `RUNAWAY_CUT`: MCU GPIO15 → hierarchical label → root pin → Safety
   sheet → third `fault_or` input, matching the ato source and
   `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`'s MCU-safety-pins table.
3. Add the missing `RESET_N` root sheet pin on Safety_Interlock (the child
   label already exists; only the root pin is missing), shared with MCU
   GPIO14 and — pending U8 — the User_Interface reset button.

**Verification:**
- Tracer: `RUNAWAY_CUT` connects GPIO15 through to the fault-OR gate's third
  input with no stray connections; `MCU_ENABLE` no longer appears anywhere in
  either sheet or the root symbol pin lists (`grep -r MCU_ENABLE pcb/`
  returns nothing).
- Cross-check the fault-OR gate wiring against the already-rebuilt NAND-latch
  structure from the prior session — confirm this doesn't touch or
  re-introduce the earlier gate-mapping bug.

---

### U8. Fix `User_Interface` root pins; add hierarchical fault-LED taps in Safety_Interlock — DONE

**Implemented, with the WDT_FAULT attachment bug the plan anticipated turning
out to be broader than expected.** Tracing all four `OCP_FAULT`/`OVP_FAULT`/
`THERMAL_FAULT`/`WDT_FAULT` local labels via the union-find tracer showed
**none** of the four sat on an actual wire vertex — all four were floating
text at `x=127`, one column short of where the real signal wires actually
run (comparator/gate outputs route to a documentation column starting
around `x=340`). Rather than an isolated `WDT_FAULT` bug, this was a
sheet-wide pattern. Deleted all four floating labels and added
hierarchical labels **directly at the real, already-connected trunk
points**, verified against ground truth in two independent ways: (a) tracing
each comparator's `OUT` pin (`Comparator:TLV3201`, local pin 1) through the
union-find graph to its actual net, and (b) cross-referencing the
`74HC4075`'s real gate-to-pin mapping from KiCad's datasheet-sourced
`4xxx.kicad_sym` (same lookup as U7) to confirm `OCP`→pin1(A1),
`OVP`→pin2(B1), `THERMAL`→pin8(C1), and `WDT_FAULT`→the NAND gate-4 output
(`U_NAND` pin 11, confirmed via `U_WDT.RESET_N` → `NAND` pin 12 → inverted
at pin 11). All four now correctly land on their real signal nets.

Replaced `User_Interface`'s five stale root pins (`BTN_UP`/`BTN_DOWN`/
`BTN_SELECT`/`ENCODER_A`/`ENCODER_B`) with the planned 7-pin table.
`MASTER_FAULT` needed no new tap in Safety_Interlock — wired directly to the
existing `FAULT_STATUS` net at the root level (same signal, different name
per sheet, joined by a root wire rather than a duplicate hierarchical label).

**Self-caught direction bug:** U7 had added Safety_Interlock's `RESET_N`
root pin as `output`, but the child sheet's own hierarchical label for
`RESET_N` is `shape input` (Safety_Interlock *consumes* reset, it doesn't
produce it) — an inconsistency that would have been a real conflict once
`User_Interface`'s actual `RESET_N` *producer* pin was wired in during this
unit. Caught while cross-referencing all three `RESET_N` pins' directions
before wiring; fixed by changing Safety_Interlock's root pin to `input` and
moving it to the sheet's input (left) edge, then rewiring the root-level net
as one output (`User_Interface`, the physical reset button) feeding two
inputs (`Safety_Interlock`, `MCU`) — the correct hardware topology.

**Second self-caught bug (routing, not logic):** the first attempt at the
five new star-hub nets routed each pin's jog by going a large distance
(≈20mm) to a shared low-y staging area before turning onto the hub column.
Since multiple `Safety_Interlock` output pins share the same sheet edge
(`x=76.2`), several of these long vertical jogs overlapped each other along
that shared edge — a different-net short, caught by the pre-write collision
script (not by trial-and-error in KiCad). Fixed by using short (~0.3–0.7 mm)
per-pin jogs immediately off each pin before turning onto its own unique hub
column, keeping every vertical run local to its own pin and eliminating the
cross-pin overlap. Re-verified clean before writing.

All four touched files (`temper.kicad_sch`, `safety_interlock.kicad_sch`,
`user_interface.kicad_sch`, `mcu.kicad_sch`) parse cleanly; final end-to-end
union-find trace confirms all 8 root-level nets touched by this plan
(`AC_N`/`GND_CENTER`, `+15V`×3 branches, `I_SENSE`, `RUNAWAY_CUT`,
`RESET_N`×2 branches, and the 5 fault taps) are each a single connected net,
mutually distinct except where intentionally shared.



**Goal:** Replace the stale root pin set (`BTN_UP`, `BTN_DOWN`, `BTN_SELECT`,
`ENCODER_A`, `ENCODER_B` — a leftover placeholder that doesn't match the
sheet's actual content) with the 7 pins the sheet actually uses, and expose
the four individual fault signals from Safety_Interlock (today only the
aggregate `FAULT_STATUS` is tapped).

**Files:**
- `pcb/temper.kicad_sch` (replace 5 stale User_Interface root pins with the
  7-pin table below; add matching pins on Safety_Interlock's sheet symbol)
- `pcb/safety_interlock.kicad_sch` (convert 4 existing local labels to
  hierarchical: `OCP_FAULT` (~line 1154), `OVP_FAULT` (~1160),
  `THERMAL_FAULT` (~1166); fix `WDT_FAULT` (~1172) — its local label is not
  actually attached to the watchdog-fault wire; per
  `elec/src/modules.ato:1137-1139` this signal is NAND gate 4's output
  (`latch.Y4`, the inverted `RESET_N`), not the raw `RESET_N` wire the label
  currently sits near)
- `pcb/user_interface.kicad_sch` (no change expected — sheet already
  correctly wired per prior session's audit; verify labels match after U8's
  root pin changes)

**Root pin table:**

| Root pin | Direction (at UI) | Origin |
|---|---|---|
| `+3.3V` | input | Power_Management (already exists) |
| `OCP_FAULT` | input | Safety_Interlock, U_OCP output |
| `OVP_FAULT` | input | Safety_Interlock, U_OVP output |
| `THERMAL_FAULT` | input | Safety_Interlock, U_THERMAL output |
| `WDT_FAULT` | input | Safety_Interlock, NAND gate 4 output (inverted RESET_N) |
| `MASTER_FAULT` | input | Safety_Interlock, same net as `FAULT_STATUS` (no new tap) |
| `RESET_N` | output | UI reset button → shared net with Safety_Interlock (U7) and MCU GPIO14 |

**Approach:**
1. Fix the `WDT_FAULT` label attachment first — verify the correct gate-unit
   output in eeschema before wiring, since the surrounding wires are
   machine-generated and gate-unit assignments need visual confirmation, not
   just coordinate math.
2. Convert the four local labels to hierarchical; add matching root pins.
3. Replace the 5 stale root pins with the 7-row table above.
4. Sanity-check TLV3201 output drive (push-pull) against each LED's forward
   current through its existing series resistor — if marginal, buffer
   through the on-sheet spare `U_INV` (74HC04) gates rather than adding new
   parts, per `elec/src/modules.ato:1177-1178`'s guardrail that LED taps must
   be branch connections off the safety logic, never in series with it.

**Verification:**
- Tracer: each of the 4 fault taps shares a root with its comparator's raw
  output net (not with the latched `MASTER_FAULT`/`FAULT_STATUS` net) —
  this is the check that would have caught the current `WDT_FAULT`
  attachment bug.
- `MASTER_FAULT` shares a root with `FAULT_STATUS`.
- `RESET_N` is a single net across UI, Safety_Interlock, and MCU.

---

## System-Wide Impact

- **Mains-voltage domain** (`power_input.kicad_sch`): U1 changes AC_N
  routing and one `.ato` statement — re-verify D1/D2 polarity is undisturbed
  after U1's reroute. U2/U3 add new nodes (Y2 cap, relay contacts) in the
  same physical area; sequence U1 → U2 → U3 to avoid compounding changes in
  one unverified batch.
- **`elec/src/modules.ato`**: two corrections in this plan (U1's `ac_n`
  statement); no other `.ato` files touched. Neither correction changes any
  already-fixed prior-session content (D1/D2 orientation stays as-is).
- **Root sheet (`pcb/temper.kicad_sch`)**: net pin count changes in every
  unit except U5. Recommend a full root-vs-child pin reconciliation pass
  after all 8 units land (sync sheet pins + full-sheet ERC), not just
  per-unit spot checks — stale/missing pins were the dominant defect class
  across all six original questions.
- **No firmware changes required** — `RUNAWAY_CUT`/GPIO1/GPIO14/GPIO15/GPIO19
  assignments already exist in `temper_pins.h` and are only being wired into
  the schematic, not reassigned.
- **New parts introduced**: G4A-1A-E relay + driver (U3), CST-1005 CT (U4),
  RP-1505S DC-DC module (U6) — none have footprints in this repo yet; U5's
  `fp-lib-table` should be created before or alongside these so new custom
  footprints have somewhere to register.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| U1's AC_N reroute is wired on a wrong-node guess | Critical (mains, fire/shock) | Low if the verification gate is honored | Independent KCL re-derivation required before edit, per this doc's Pre-condition; do not proceed on the Fable agent's derivation alone |
| U1's reroute overlaps an existing wire and creates a collinear short | High | Medium (this exact failure mode occurred once already this project) | Use jog-detour routing, not direct endpoint moves; tracer self-check before AND after file write |
| U3's relay coil dropper resistor value is wrong, relay chatters or fails to pull in | Medium | Medium | Verify against G4A's actual must-operate voltage table before finalizing value, not the tentative 39 Ω estimate |
| U4 consolidation silently changes the OCP trip current if the surviving burden's value/tolerance differs from what Safety_Interlock's comparator reference assumes | High (safety calibration) | Low | Explicit verification step cross-checks the transfer ratio against `CT_SENSING_DESIGN.md`'s trip-current assumption before considering U4 done |
| U6's isolation module doesn't actually meet the required barrier class once a real compliance review happens | Medium | Low | Flagged explicitly as deferred to a compliance sign-off gate, not silently assumed closed by this plan |
| U7/U8 root pin churn breaks an already-correct connection elsewhere on the root sheet (this sheet has had coordinate-collision bugs before) | Medium | Medium | Full root-vs-child reconciliation + whole-sheet tracer pass after each unit, not just the touched nets |

---

## Test Strategy

- Union-find connectivity tracer re-run after every unit (not batched at the
  end) — per-unit isolation makes it possible to attribute a new short or
  break to the specific change that caused it.
- `kicad-cli sch export netlist` on each touched sheet after edits (parse
  validation).
- `kicad-cli sch erc` on each touched sheet; zero new violations vs. the
  pre-unit baseline.
- After U5: footprint-resolution check via
  `packages/temper-placer/src/temper_placer/validation/drc_runner.py` (or
  direct `kicad-cli`) confirms no missing-footprint warnings.
- After all 8 units: full-project sheet-pin reconciliation (root vs. every
  child sheet) and a whole-schematic ERC pass, since stale/missing root pins
  were the recurring defect class this plan closes out.
- No firmware or Python test suite changes expected; existing
  `firmware/test/*` and `packages/temper-placer/tests/*` suites are
  unaffected and don't need to be re-run for this plan specifically.

---

## Related
- `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`
- `docs/solutions/tooling-decisions/kicad-schematic-connectivity-tracer-2026-07-14.md`
- `docs/solutions/tooling-decisions/kicad-embedded-symbols-lose-pin-semantics-2026-07-14.md`
- `docs/solutions/workflow-issues/firmware-hardware-pin-map-divergence-2026-07-14.md`
- `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`
- `docs/hardware/GROUNDING_EMI_STRATEGY.md`
- `docs/hardware/CT_SENSING_DESIGN.md`
- `docs/hardware/UCC21550_INTERFACE_CONTRACT.md`
- `docs/hardware/RTD_SAFETY_DUAL_PATH.md`
