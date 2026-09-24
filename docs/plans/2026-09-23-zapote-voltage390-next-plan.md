# Rev38 bus-monitor selection and construction plan

**Milestone:** a bounded, reviewable Rev38 voltage-sense interface decision.
**Current outcome:** selection dossier at
`zapote/voltage-sense/rev390-interface-01/README.md`; native schematic and
PCB are gated by missing product and integration inputs.

## Brainstorm and review

The legacy 0–250 V half-bus board exposes its return as the host ground.
Rev38's `VB_BANK` is a separate, roughly 390–400 V bank referenced to HOT0,
with a local F2-separated `VD_LOCAL` island and a HOT-side fault detector.
The intended new function is isolated SELV telemetry while the HOT-local
detector retains trip authority. Three alternatives were screened: direct
divider reuse (domain short), integrated-supply AMC3330 (8 mm intrinsic
package path below the current 12.6 mm PD3 target), and an AMC1411 stretched
package with separate HOT/SELV supplies (preferred for further selection).
The preferred part is a **candidate** because the adopted bus maxima,
supplies, divider, receiver, interconnect and governing insulation row are
still unknown. Review specifically rejected deriving a maximum from the
450 V capacitor nameplate or treating any amplifier output as the complete
shutdown chain.

## Next executable sequence

1. Freeze a Rev38 source revision. Recompute the source hashes in the
   dossier, then adopt continuous and transient VD/VB voltage envelopes,
   including source tolerance, startup, lost control, F2 open/closed and
   discharge interactions. State insulation working/impulse conditions.
2. Decide VB-only versus both VD/VB monitor channels, receiver use, and
   invalid-data policy. Keep Rev38's HOT-local detector as a separate
   independent protection producer.
3. Validate AMC1411DWLR against the adopted insulation rule and package
   assembly. Confirm HOT logic5 and SELV3V3 startup/load budgets, or select
   a rated independent isolated supply; check each rail-loss ordering.
4. Select divider resistor and connector MPNs from manufacturer datasheets.
   Compute nominal and worst-case input, per-resistor working voltage/power,
   tolerance/temperature/aging, surge and single faults. Select and verify
   differential receiver ADC/interface and fault-state decoding.
5. Author a new Atopile source with explicit HOT0 and SELV nets and exact
   component identities. Audit no copper/cable short across the barrier,
   device pins, divider nodes, connector pad map and invalid-state defaults.
6. Generate native schematic and standalone PCB; inspect plotted schematic,
   netlist and board renders. Run ERC/DRC with the adopted isolation rules,
   review footprint and enclosure clearance, and record any waivers by cause.
7. Qualify a fabricated sample for transfer/error, startup/brownout, input
   open/short and surge, partial-power, insulation, receiver acquisition,
   and fault-to-both-stage inhibition. No energized hookup follows from the
   digital checks alone.

**Exit criterion for this milestone:** evidence-linked architecture and an
explicit blocked construction gate. **Exit criterion for the later PCB
milestone:** source/native parity, accepted envelope and parts, reviewed
ERC/DRC, and a physically qualified standalone article. Neither criterion
can be replaced by a self-authored PASS flag.
