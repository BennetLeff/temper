---
artifact_contract: ce-unified-plan/v1
artifact_readiness: decision-ready
title: "Rev38 discharge board design-freeze milestone"
date: 2026-09-23
execution: hardware
---

# Rev38 discharge board: next milestone

## Decision

Keep product board capture **blocked**. The existing U1–U3 work defines the two Rev38 energy islands and screens a conditional topology, but no voltage/time criterion, maximum operating and fault voltage, inverter input capacitance, qualified active-switch drive, or mounted fan-off thermal result has been adopted. The user's Control Freak Home-like cooking goal specifies behavior, not any of those electrical limits. A 24 V coupon would demonstrate only RC separation and would not close the high-voltage DC switching, thermal, spacing, or service-observation risks. The useful milestone now is a frozen interface request and an executable evidence sequence, recorded in [board-candidate-01/DECISION.md](../../zapote/discharge/evidence/board-candidate-01/DECISION.md).

## Review of options

| Option | Decision | Reason |
| --- | --- | --- |
| Lay out the previously screened NC-contact / RH50 bank and passive VD strings | Hold | Its 34 V / 60 s examples are historical sensitivity inputs; the coil rail, installed chassis heat path, loaded DC contact life, and single-open acceptance are unproved. |
| Draw a generic 390 V board with TBD parts | Reject | A routed board would appear buildable without a justified footprint, creepage, source-interface or thermal envelope. Rev38 has no output/discharge connector. |
| Make a ≤24 V RC/F2 coupon | Defer | This would only confirm already-tested island arithmetic and could be confused with a product discharge stage. If a later specific low-energy experiment needs it, state that question and build a separate fixture. |
| Freeze prerequisites and run controlled part/thermal experiments | Proceed | These results can change topology and placement before copper is committed. |

## Work sequence and acceptance

1. **Adopt requirements.** Record source, edition, applicable clause or project authority; service access class; voltage and time at each accessible energy island; restart threshold; and whether one open resistor/contact must meet normal time or only cause a detectable lockout. Acceptance: one signed requirement record applicable to this appliance and Rev38 topology. Do not inherit the old split-bus 34 V / 60 s value.
2. **Freeze electrical envelope.** Rev38 owner provides maximum VD/VB steady and transient voltages, F2 behavior, source-fed AUX-loss behavior, and exact connection geometry. Inverter owner provides maximum direct/detached input capacitance and all disconnect states. Acceptance: article and source hashes, bounds over tolerance/age/temperature, and an energy-island map that is still valid with F2 open.
3. **Resolve physical default.** AUX owner gives a bounded coil or gate-bias rail and its collapse waveform; Rev38 owner gives restart-inhibit and observation interfaces. Acceptance: with AUX lost and mains still attached, discharge path engagement and indefinite resistor/contact stress are bounded or physical mains isolation is proven.
4. **Select and qualify exact parts.** Orderable resistor, switch/contact, snubber, connector, sense and insulation parts are evaluated at the frozen bounds. Acceptance: DC make/break and life, resistor pulse/repetition, voltage sharing, package/PCB spacing, mounted chassis temperature with fan off, and single-element faults are supported by manufacturer or measured evidence. The RH50 catalog mounted wattage is not an installed rating.
5. **Capture a standalone source and PCB.** Only after steps 1–4 choose the topology, build Atopile source and KiCad native outputs, route each island with its own path and observation, and check source/netlist/board identity, ERC, DRC, Gerbers and assembly geometry. Acceptance is **digital construction**, not safe-discharge qualification.
6. **Qualify the assembled article.** Follow `zapote/discharge/bench-qualification.md` with independently adopted criteria, raw waveforms for VD and VB, negative controls, instrument calibration, thermal and repeated switching data, and independent engineering review. Acceptance requires measured service/restart behavior; the existing Rust gate deliberately cannot self-certify it.

Steps 1–4 may proceed in parallel with the inverter, auxiliary and Rev38 owners, but each must be complete before product board placement and routing. Any change to the Rev38 source lock or inverter capacitance reopens the sizing and layout decision.

## Exit state of this milestone

The [decision record](../../zapote/discharge/evidence/board-candidate-01/DECISION.md) binds the present source, names the missing inputs and their owners, specifies the interface request, and makes the board status explicit. No `source-build-01` or `.kicad_pcb` is produced because there is no selected product circuit to encode.
