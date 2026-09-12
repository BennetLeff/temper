# Standalone voltage sensing and harness closeout

## Goal and scope

Complete the requested command/shared-gate closeout, then build a separate
voltage-sensing/OVP unit using Atopile source, agent-authored KiCad placement
and routing, Rust source/model/geometry checks, native ERC/DRC, and retained
review evidence. This is a digital unit milestone, not cooker integration,
fabrication approval or physical qualification.

## Contract

- Measure the positive half-bus relative to an explicit measurement return:
  170 V nominal, 0–250 V analytical measurement envelope. The existing cooker
  expects a 195–205 V rising OVP trip and 5–10 V hysteresis at this half-bus.
- Standalone return is common with analog/logic return. Outputs are not
  galvanically isolated. Mapping this return into the full cooker's PE/bus
  midpoint architecture is a required integration review, not assumed here.
- Preserve OVP 3×430k /16.9k /487k and TLV3201 with a local REF2025 2.5V
  reference, supply bypass and reference output capacitor. Explicit 3.3V host
  power, ground, active-high OVP and analog monitor connector.
- Correct ADC headroom: 3×300k /10k, 100nF filter. At 250V nominal output
  is 2.747V; verify tolerance/temperature corners and receiver loading in Rust.
  Host ADC acquisition, hot leakage, transients, power-off and brownout
  response remain unqualified until device/bench evidence exists.
- Use an explicit two-layer 1.6 mm stackup and a low-current high-voltage input
  connector. Keep HV copper at the input/resistor-chain end; no claim that
  resistor spacing alone qualifies an insulation system.

## Work and verification

1. Standard Make commands build/test Zapote Rust. Common board CLI checks the
   actual saved bytes and hashes them; RTD/current-sense/new voltage paths are
   registered. Missing or malformed board data cannot become a pass.
2. Independent circuit audit, official part evidence and memory selection.
   Check numerical suggestions independently before adopting them.
3. Compiled standalone source and native generation with exact component/pad
   census. Reuse existing Python/KiCad transport. All poses and route vertices
   are agent decisions; no optimizer/router algorithm.
4. Rust checks source/net identity, source values, divider output/stress,
   OVP thresholds, connectivity, clearance/locality and physical stackup.
   Retain negative controls for actual defects and independent numerical
   comparisons. Native ERC/DRC/parity must have no unexplained findings.
5. Visually inspect schematic, layout and 3D, record final file identities,
   limits and acceptance, then update durable memory and next-unit handoff.

## Completion boundary

A routed standalone unit with source-derived connections, passing required
construction checks and explicitly reported qualification gaps. Physical tests
are NOT RUN. Do not modify legacy full-cooker source, accepted frozen outputs,
firmware integration, or release packages to imply this unit is integrated.

## Closeout — 2026-09-11

Digital construction complete. See [acceptance](../../zapote/voltage-sense/ACCEPTANCE.md) for final native/Rust results, the strict CLI exit contract, evidence identities and remaining qualification obligations. The receiver loading/acquisition item is retained as INDETERMINATE; the implemented geometry locality check measures pad-centre distance, not loop inductance.
