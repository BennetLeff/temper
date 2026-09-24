---
title: Rev38 single-bank cooker integration
type: design
date: 2026-09-24
status: candidate topology selected; electrical qualification open
parent: docs/superpowers/specs/2026-09-23-power-entry-hot-receiver-design.md
---

# Rev38 single-bank cooker integration

## Decision and evidence boundary

The product candidate uses one Rev38 fused inlet, rectifier, PFC, F2, and
`VB_BANK`/`HOT0` reservoir. It retains the existing cooker ESP32-S3 and its
SELV 3.3 V rail. The cooker inverter is redesigned around that bank. The
selected *evaluation topology* retains a half bridge and puts the series
capacitor/coil tank and its current-transformer primary between the half-bridge
switch node and `HOT0`. The user selected this direction on 2026-09-24. It is
not an accepted operating point or permission to energize the assembly.

The existing `cooker-mate` source is a control-header fixture: it imports
`Top`, including the older `PowerInput` doubler, midpoint, and `AuxSupply`.
Its 16-contact audit remains evidence for those SELV pin assignments only.
The product source must compose the cooker loads without that old inlet or
half-bus supply. The canonical passive board, cooker `Top`, and cooker PCB
remain reference artifacts.

## Selected electrical boundaries

| Boundary | Candidate producer and consumer | Design rule and unresolved proof |
| --- | --- | --- |
| AC input | One Rev38 `AcInput38` and its separately qualified off-board F1; Rev38 `PfcPower38` owns the rectifier and boost | No surviving cooker `PowerInput` fuse, CMC, NTC, relay, rectifier, or doubler in the product source. F1 fault-current, inrush, holder and thermal work remains open. |
| DC bank | `PfcPower38.VB_BANK` after F2 to half-bridge positive rail; bank-capacitor `HOT0` to half-bridge negative rail | Both high-current conductors, return, connector/cable or same-board copper, fault current, creepage, current rating, F2 behavior and physical layout must be specified and checked. Keep inverter HF return out of the Rev38 `RECT_MINUS`-to-`HOT0` 10 mΩ PFC shunt and its Kelvin sense loop; `HOT0` as one schematic net does not prove a quiet physical star. The inverter cannot be connected to `VD_LOCAL` to bypass F2. |
| Tank | Half-bridge switch node through the existing parallel 300 nF series capacitor bank, 88 µH coil, and tank-current CT primary to `HOT0` | The capacitor blocks the DC component of the 0-to-`VB_BANK` drive. Its bias, AC ripple, inrush, loss and voltage sharing, plus coil current, pan cases, switch stress, ZVS and controller range require a new analysis. Do not inherit the 340 V doubler's 47 kHz/1.8 kW acceptance. |
| Inverter return sense | Existing second CT primary in series between the low-side emitter and `HOT0` | Preserve the exact through-primary path and isolate both CT secondaries from HOT. Re-evaluate thresholds and pulse capture against the new current waveform and fault trajectory. |
| SELV supply | A separately qualified isolated 15 V source from the protected AC path to the cooker's existing `PowerManagement` 3.3 V buck and SELV loads | Remove the old `AuxSupply` input from +170 V to midpoint. Keep SELV return separate from `HOT0`; retain the deliberate SELV-to-PE reference only after insulation, leakage and fault review. The Rev38 HOT auxiliary supply is **not** this SELV source. Include cooker and Rev38 3.3 V loads and startup in one budget. |
| HOT inverter drive supply | Rev38 `AUX_PROTECTED`/`HOT0` as the candidate producer for `HalfBridge.power_15v_ls`/low-side UCC21550 VDDB–VSSB and its high-side bootstrap | The old source leaves this floating gate supply without a real producer. Add both IGBT gate-charge and driver quiescent/startup loads to Rev38 protected-AUX and cutoff budgets, then verify its voltage, collapse/default-disable and noise at the driver pins. Do not bridge the isolated UCC21550 input side or the cooker SELV rail to `HOT0`. |
| Inverter gate permission | Cooker safety latch and a new default-disable physical indication of Rev38 retained RUN | A lost Rev38 RUN, invalid HOT rail, broken inter-board indication or cooker latch trip must inhibit UCC21550 independently of ESP firmware scheduling. The existing 16-contact control port has no RUN conductor. Select an isolated reverse channel and a rated connector/pin contract; do not repurpose a duplicate 3.3 V or return contact without proving its current and fault budget. Preserve the cooker's `SOURCE_INTERLOCK_N` path that clears Rev38 permission on cooker fault. |
| Bus voltage | New full-bank divider/comparator/ADC interface for `VB_BANK` relative to `HOT0`, with an insulation-aware SELV readout | Legacy `OVPComparator` senses the old +170 V half-bus relative to the doubler midpoint and cannot be reconnected unchanged. Choose a trip window above the accepted PFC operating maximum and below the weakest bank/inverter limit with tolerances and transients. Fail-low driver permission on sensor/rail faults. |
| Discharge | New single-bank active discharge path plus the Rev38 bank bleeder, and a separately considered `VD_LOCAL` path across open F2 | Do not instantiate old `BusDischarge` with its two 170 V strings and midpoint. Size contact DC breaking, resistor pulse/continuous power, insulation and loss-of-rail state from the real capacitor energy. Test F2 open, stuck-open/stuck-closed contact and single-open bleeder cases. |

The half-bridge switch-node waveform is nominally 0 to 400 V relative to
`HOT0`. With an ideal 50% drive, its AC component is approximately +/-200 V,
versus approximately +/-170 V across the old split-bus tank. That 17.6%
amplitude change is sufficient to invalidate the old fixed operating point;
it does not by itself predict real power or current in a pan-coupled resonant
load. The `VB_BANK` source has four 560 µF, 450 V capacitors in parallel:
2.24 mF nominal and 179.2 J at 400 V. Its existing three 150 kΩ series
bleeders have a nominal 1008 s time constant. Those are arithmetic inputs,
not a safe-discharge claim. The local 22 µF reservoir remains energized on
`VD_LOCAL` after F2 opens and needs its own fault/discharge evaluation.

## Source and firmware contract

Create a new product composition from selected cooker modules rather than
importing `Top`. It has exactly one cooker ESP, one Rev38 front end, one
SELV 15 V-to-3.3 V chain, one inverter, one tank and both current-sense
primaries. Its source must expose typed power, return, fault and control
boundaries so the Rust audit can reject a duplicate inlet, old midpoint,
open tank return, bypass of F2, HOT-to-SELV short, lost physical inverter
inhibit, or dangling supply. Freeze a complete build receipt before native
board work. A source netlist proves connectivity, not voltage, startup,
heat, timing, isolation or physical routing.

The source ESP keeps one owner for cooker PWM and Rev38 authorization. PWM
remains disabled until both the cooker latch and physical Rev38 RUN gate are
valid, but firmware sequencing is an additional control and cannot replace
the physical UCC21550 inhibit. Rev38 PFC RUN and cooker inverter PWM are
separate actuators: a fault must clear both through the selected physical
paths. Recalculate bus ADC conversion, PLL/ZVS operating range, power and
current limits, OCP thresholds, startup and stop sequencing for the new
waveform. Existing independent RTD and thermal protections remain present
and must be rechecked against the new thermal envelope.

## Digital and physical acceptance sequence

1. Select the isolated SELV 15 V source, full-bank OVP path, single-bank
   discharge, physical RUN-to-inverter channel, and both high-current joins.
   Record exact parts, pin ownership and a power/thermal budget. Keep every
   unselected or unqualified value explicitly open.
2. Build the one-front-end Atopile composition, export a frozen receipt and
   extend the exact-pin Rust audit with negative mutations for every power,
   fault and isolation boundary above. Compare the selected source pin map
   with the existing ESP driver and receiver firmware.
3. Model and test normal, line/high-bank, low-bank, open-F2, loss of RUN,
   cooker trip, partial-power, reset, stuck discharge, sensor-open and
   sensor-short cases. Re-derive the inverter and fault-response allowable
   times independently of device propagation times.
4. Only after the source, parts and interface contract agree, create native
   schematic and PCB candidates. Run source/native pin parity, ERC/DRC,
   stackup/domain, BOM/footprint and connector checks. Preserve the
   canonical board.
5. Keep physical response, discharge, thermal, current cessation, isolation,
   F1/F2 interruption, and mains/appliance acceptance **NOT RUN/OPEN** until
   measured on an assembled, appropriately instrumented prototype.

The original Rev38 authorization plan remains the authority for session and
watchdog behavior. This supplement defines the product power join needed to
make that authorization candidate auditable as one cooker assembly.
