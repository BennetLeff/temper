# Standalone safety interlock / Rev A

A separate 100 × 65 mm, two-layer logic board combines seven faults, a watchdog and a sensing-valid input into latched permission to heat. A fault clears permission. Clearing the fault does not restart: a fresh reset edge with every input healthy is required. This unit contains no enclosure or heater-power circuitry.

- [PCB](candidate/section.kicad_pcb), [KiCad project](candidate/section.kicad_pro), [schematic PDF](evidence/schematic-reva.pdf), [3D view](evidence/board-reva-3d.png).
- [Atopile source](../../elec/src/interlock_unit.ato), [interfaces](INTERFACES.md), [model](MODEL.md), [parts](BOM.md).
- [Acceptance](ACCEPTANCE.md), [validation and replay](VALIDATION.md), [memory](memory/README.md).

The flow is Atopile → native KiCad → agent-authored placement/routes → Rust and native checks. Luna contributed circuit review, native construction and validator scaffolding. Coordinator review corrected the latch evaluator, completed routing and strengthened the real-artifact mutation tests. Existing transport and geometry code was reused; no new placer/router was built.

Digital construction is complete under the declared interfaces. Physical tests remain NOT RUN and full qualification is INDETERMINATE. SENSOR_LIVE/AUX producers, downstream active-high PERMIT handling and physical timing remain integration obligations. The next separate construction unit is isolated gate drive; whole-cooker integration follows the separate-unit milestones.
