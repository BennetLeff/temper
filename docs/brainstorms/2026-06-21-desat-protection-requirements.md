---
date: 2026-06-21
topic: desat-protection
status: ready-for-planning
---

# Requirements: IGBT Desaturation Protection

## Goal

Add IGBT desaturation (DESAT) protection to the Temper schematic before first high-voltage bring-up. The protection must detect Vce saturation voltage rise on overcurrent, latch off the gate driver within 500ns, and be enforced in the build system so it cannot be silently omitted.

## Problem

DESAT protection is completely absent from the current schematic. The gate driver — UCC21550BDW — has **no built-in DESAT pin**. Without an external discrete comparator circuit, a shorted switch or overcurrent event on the 340V DC bus destroys the IKW40N120H3 IGBT (~$15, 1200V, 40A) and potentially causes a fire. First high-voltage power-on with this gap is a one-shot gamble: any transient that pushes the IGBT into desaturation results in uncontrolled latch-up with no protection path.

The complete circuit design is documented in `docs/hardware/IGBT_DESATURATION_PROTECTION.md`. This workstream implements that design in atopile and wires it into the build system.

## Key Design Decisions (Already Made)

All component selections are final per `docs/hardware/IGBT_DESATURATION_PROTECTION.md`. Do not re-evaluate these choices.

| Component | Selection | Rationale |
|---|---|---|
| Comparator | TLV3201 | 260ns propagation delay, push-pull output, meets <500ns response requirement |
| Snubber diode | STTH1R06 | 1200V rating, matches DC bus voltage |
| Blanking capacitor | 100pF | 150ns blanking time, suppresses turn-on transient |
| Trip threshold | Vce > 6.4V | Resistor divider per design doc; catches desaturation before thermal runaway |

**NOT LM393**: The LM393 is disqualified — 1.3μs propagation delay (exceeds 500ns budget) and open-collector output is incompatible with the required drive path.

## Success Criteria

1. A `DesatProtection` module exists in `elec/src/modules.ato` with the comparator, snubber diode, blanking cap, and threshold divider from the design doc
2. The module is instantiated in `elec/src/main.ato` and wired to the UCC21550BDW shutdown/fault input
3. An atopile assertion in `elec/src/main.ato` causes `ato compile` to fail if the `DesatProtection` module is not instantiated — no routing session can proceed without it
4. Circuit parameters in the module match the values in `docs/hardware/IGBT_DESATURATION_PROTECTION.md` exactly
5. Pre-HV bench test passes: DESAT trip verified on the bench at reduced voltage before 340V bus is energized (see Bench Test section)

## Scope

### In Scope

**Workstream 1 — `DesatProtection` atopile module**

File: `elec/src/modules.ato`

Define a new `DesatProtection` module containing:
- TLV3201 comparator instance
- STTH1R06 1200V snubber diode
- 100pF blanking capacitor
- Threshold resistor divider (values from design doc; trip point Vce = 6.4V)
- Ports: `igbt_collector`, `gate_driver_fault`, `vcc`, `gnd`

Component values and resistor ratios must match `docs/hardware/IGBT_DESATURATION_PROTECTION.md` exactly. Do not invent values.

**Workstream 2 — Top-level wiring**

File: `elec/src/main.ato`

- Instantiate `DesatProtection` in `Top`
- Connect `igbt_collector` to the IKW40N120H3 collector node
- Connect `gate_driver_fault` to the UCC21550BDW shutdown/fault input (SD/FAULT pin)
- Connect power and ground rails

**Workstream 3 — Atopile assertion**

File: `elec/src/main.ato`

Add an assertion that blocks `ato compile` if the `DesatProtection` module is absent. If atopile's `assert` syntax cannot express a structural instantiation check natively, add a post-build Python validation script called from a Makefile target (same fallback pattern as the clean-base-sprint).

### Pre-HV Bench Test

Before energizing the 340V DC bus, verify the DESAT trip circuit on the bench:

1. Power the gate driver and comparator from a bench supply at rated auxiliary voltage
2. Apply a controllable DC voltage to the IGBT collector node via a resistive load (do not use the full HV bus)
3. Sweep collector voltage upward through the 6.4V threshold while scoping the TLV3201 output and the UCC21550BDW SD pin
4. Confirm the comparator output transitions and the gate driver latches off within 500ns of the threshold crossing
5. Confirm the blanking cap prevents false trips during the normal turn-on transient

This test must pass before the board is connected to the 340V rectified bus.

### Out of Scope

- **Gate driver PCB layout**: Physical placement and routing of the DESAT circuit relative to the IGBT is a separate routing workstream. This workstream covers schematic only.
- **Firmware DESAT fault handler**: Responding to a latched DESAT fault in firmware (logging, user notification, restart lockout) is a firmware workstream. This workstream ends at the hardware latch.
- **IGBT gate resistor tuning**: Switching speed / EMI tradeoffs on Rg are a separate workstream.
- **Other hardware gaps** (EMI filter, pan detection): Separate sessions.

## Dependencies

- `DesatProtection` module must exist in `elec/src/modules.ato` **before** the clean-base-sprint can write the atopile assertion `assert DesatProtection module is instantiated` in `elec/src/main.ato`. These two workstreams must be coordinated — the assertion in the clean-base-sprint is a blocker on this workstream completing first.
- `docs/hardware/IGBT_DESATURATION_PROTECTION.md` is the authoritative source for all component values. Any ambiguity in component parameters resolves to that document, not to the implementer's judgment.

## Risks

**Atopile structural assertion expressiveness**: Atopile handles value-range `assert` statements well (confirmed in existing `elec/src/main.ato`). Asserting that a module is instantiated may require a workaround — verify grammar before writing, use Makefile/Python fallback if needed.

**UCC21550BDW fault pin polarity and timing**: Confirm the SD/FAULT pin behavior (active-low, latching vs. auto-restart) in the UCC21550BDW datasheet before wiring the comparator output. A logic level mismatch between TLV3201 push-pull output and the SD pin would result in no protection.

**Blanking time vs. turn-on transient**: 100pF / 150ns blanking is specified in the design doc. If the actual IGBT turn-on transient is longer (varies with gate resistor and load inductance), the comparator will false-trip during normal switching. Validate blanking time during bench test before declaring the circuit functional.
