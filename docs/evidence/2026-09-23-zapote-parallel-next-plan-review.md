# Review of the next Zapote parallel digital milestone plan

Date: 2026-09-23. Reviewed `docs/plans/2026-09-23-zapote-parallel-next-digital-milestone-plan.md` after independent feasibility and adversarial passes. Both read the committed U2 unit evidence and Rev38 source. Their five actionable findings were applied before implementation.

| Finding | Plan correction |
| --- | --- |
| HOT0 is mains-referenced on energized Rev38; a bench fixture with no AC trace can still become hazardous when mated. | Restrict P1 to a standalone mains-disconnected DUT with isolated current-limited supplies. Any powered board hookup needs separate pad, isolation, instrument and operator review. |
| Ideal inverter switches and diodes cannot produce a complete thermal heat map. | P3 conserves only modeled stored/source/ohmic terms; unmodeled device/capacitor losses remain explicit and cooling heat indeterminate. |
| Cooling producer has both Heatsink fault and SENSOR_LIVE outputs. | P4 tests paired J1-4/J2-5 states and labels downstream permit propagation as a logical contract pending electrical measurement. |
| NC discharge relay recovery may chatter against a charged bus. | P2 requires pickup/hold/dropout and repeated-brownout schedules; missing DC-life/timing data makes recovery indeterminate. |
| F2 opening at nonzero current has omitted arc/interconnect energy; PFC source semantics were undefined. | P3 tests conservation within fixed F2 states; the opening interval is indeterminate without an interconnect model. Source current is a nonnegative command clipped by declared current/power limits, with no reverse flow. |

The plan is ready for its four disjoint implementation units. This review accepts only the scope and tests, not a source, discharge circuit, inverter operating range, cooling assembly or physical qualification.
