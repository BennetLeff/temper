# Reduce the passive protection circuit before another layout

Status: architecture decision, 2026-09-19. The 133-part construction is rejected.
No smaller replacement is implemented or qualified by this document.
Baseline revision: `5dde29ab3e2f1223c2d33c129ced2cf647238307`.

Follow-up: [F2-open sensing experiment](f2-open-01/README.md) implements a
21-part isolated detector, replacing the equivalent 31-part sensing portion.
It preserves both absolute OV channels and bidirectional mismatch detection.
Static screening and numerical cross-checks pass; the complete shutdown/latch
system and its timing qualification remain unfinished. No revised whole-board
count or protection acceptance is claimed.

## Decision

Retain the 54-part passive power-entry baseline as the canonical candidate.
Develop local hardware shutdown and a fresh-arm latch as a separate protection
function. Assign precharge sequencing, startup deadline and downstream load
permission to system control, with explicit interfaces and verification before
counting that assignment as implemented. Keep F2 between diode and bank for this
comparison. Do not remove its voltage-difference observation merely to reduce
parts: the retained evidence does not yet justify that deletion.

This supersedes the assumption in `../INTERFACE-DESIGN.md` that all sequencing
must become a new discrete supervisor on this board. It does not withdraw the
fault cases, restart contract or qualification requirements in that document.
In particular, the two-second prototype timeout and nominal voltage-difference
threshold are not established requirements.

## What 133 actually contains

The source-bound [census](component-census.json) partitions every supervisor
instance exactly once. It reads the retained `native-05` compiled manifest;
these are assembled-component counts, not unique purchasing line items.

| Scope | Parts |
|---|---:|
| Existing power-entry baseline | 54 |
| Additional driver, bypass, resistors, F2 port and discharge path | 9 |
| Supervisor | 70 |
| Total rejected construction | 133 |

| Supervisor function | Parts |
|---|---:|
| Two high-voltage divider/filter networks | 14 |
| Buffered voltage-difference network | 12 |
| Reference and bias resistor | 2 |
| Auxiliary UV/OV divider networks | 4 |
| Two comparator packages and bypass capacitors | 4 |
| Precharge/ready threshold networks and startup timer | 11 |
| Latch, logic, input conditioning and control connector | 16 |
| Logic supply and power-on reset | 7 |
| Total | 70 |

The comparator and logic packages are shared between functions. Removing the
11 sequencing-specific components is not an electrically complete ECO. Further
savings require rewiring and proving the resulting circuit. Claiming a 90- or
100-part replacement now would be a target, not a compiled BOM. External fuse,
holder, auxiliary assembly, isolation and any new system-control components
must also remain visible in the assembly budget.

## Requirements that a smaller design must still satisfy

| Event/function | Required response | Implementation ownership |
|---|---|---|
| Diode-side or bank overvoltage | Direct hardware gate disable; retain fault | Local protection |
| Auxiliary invalid or protection power lost | Default driver off; no restart on supply return | Local protection and power-on reset |
| F2 opens | Contain diode-side energy; prevent repeated PFC retries; revoke load permission | Local energy path/detection plus system control |
| U10 and U9 short | Interrupt bank discharge; a gate command cannot clear it | F2 and qualified interconnect/withstand coordination |
| Deliberate startup | Precharge and continuity checks, then fresh arm/start request | System control; implementation still missing |
| Bank reaches operating voltage | Permit downstream load only after bank-side measurement | System control and an appropriate voltage producer |
| Startup does not complete | Revoke permission and retain fault | System control; deadline must be derived |
| Stuck arm/permit or fault clears | No automatic re-arm | Local fresh-edge latch and tested interface protocol |

The existing interlock has a hardware latch, but its HOT-domain integration is
unfinished. The existing voltage-sense unit covers a 170 V nominal half-bus,
with a 250 V monitoring envelope, not this approximately 400 V bank. Neither is
credited as a connected replacement. Relevant source: `elec/src/interlock_unit.ato`,
`elec/src/voltage_sense_unit.ato`, and `zapote/interlock/INTERFACES.md`.

## Three alternatives assessed

1. **Simplify protection while retaining F2 location — selected development
   path.** Keep independent observation, hardware disable and fresh-arm behavior.
   Move sequencing only with a real system producer/interface. First simplify
   shared logic and sensing; do not expand the PCB again before their complete
   component inventory and fault behavior are reviewable.
2. **Put F2 in the switch drain branch.** Opening F2 would leave the main
   diode-to-bank commutation path intact and remove this particular isolated
   diode-side reservoir problem. However, the selected offboard DIN fuse and
   wiring would enter the fast switching loop. Inductance, pulse heating,
   interruption and semiconductor stress need a different installation design.
   This is not a drop-in ECO with the selected hardware.
3. **Put F2 only at the inverter output, or omit it.** This leaves the internal
   bank-to-shorted-diode-to-shorted-switch loop uninterrupted. Reject under the
   existing simultaneous-short requirement.

An integrated monitor is a candidate building block, not a complete supervisor.
TI's listed TPS3762D02OVDDFR is an adjustable OV variant, without UV detection.
Holding LATCH_CLR high disables its latch; therefore that pin cannot directly
replace a fresh-edge arm circuit. Startup includes self-test before normal
monitoring. These behaviors require separate treatment of power return and
stuck commands. [TI TPS3762 datasheet](https://www.ti.com/lit/gpn/tps3762),
Table 9-1 and §§7.3.3.3, 7.3.6. No replacement part is selected here.

## Decisive unresolved comparison

Absolute OV alone cannot yet replace voltage-difference detection. The retained
controller screen places maximum static regulation at 409.307 V and minimum
controller OVP at 398.112 V across different allowed component/device corners.
That overlap prevents choosing a universal independent absolute threshold that
is both above all normal operation and below every controller OVP event. The
prototype's independent OV screen starts above the low controller OVP corner.
Consequently, controller shutdown is not proof that the external fault latch
will set before the controller retries.

The next circuit evaluation must include F2 opening during startup and steady
run, both sides initially charged, both discharged, and residual-charge restart.
Use consistent component corners and actual controller stop/restart behavior;
the cross-corner overlap is a screening argument, not a simulated trajectory.
If local OV plus system detection is shown to contain every retry interval,
the discrepancy network can be removed. Otherwise simplify its implementation
while retaining the function. Equal VD/VB voltages never establish continuity.
The existing `combined-screen.txt` remains INDETERMINATE on current-at-trip and
total shutdown delay; Boolean tests do not close those inputs.

## Artifact state and verification

The [archive](rejected-133/README.md) preserves the rejected source, placements,
board, schematic, libraries and construction adapters. `native-05` and
`source-build-07` remain its compiled evidence. The canonical source, candidate,
poses, outline and build adapter were restored from the baseline revision.

Restored source SHA-256:
`dd31c0addd5a5a5764955efca44d50d6fe89747f88c937e4c127398349b701d8`.
Restored PCB SHA-256:
`34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9`.
This restores the unprotected reference circuit; it is not a protection release.
The historical nine supervisor logic tests apply only to the rejected manifest.
