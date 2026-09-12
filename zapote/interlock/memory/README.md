# Interlock memory use

`attempt-001/` records the task and actual Rust memory preparation from the thermal-sensing lesson catalog. Selected guidance concerns source/model binding, external pin/geometry oracles, explicit qualification boundaries and preservation of failed attempts. Thermal thresholds and sensor-specific assumptions were not transferred as interlock facts.

Worker dispatch records distinguish the text sent by the coordinator from provider-internal prompt forwarding, which was not observed. A retrieved note or a worker's claim to have used it is not proof of correct implementation: the coordinator still checks actual artifacts and counterexamples.

Lessons identified during construction:

1. A latch model must retain Q between events. Testing only reset/fault snapshots can accept a pulse generator in place of a latch; include reset → healthy no-edge → fault → healthy no-edge → fresh reset traces.
2. Verify package-specific pin diagrams. Q/QBAR and supervisor RESET/GND reversals can leave a plausible schematic with opposite behavior.
3. Watchdog high-impedance behavior is part of the electrical model. Use the manufacturer's explicit bias recommendation, not an arbitrary familiar pull value.
4. An unpowered sensor and a broken signal conductor are different cases. A local pullup does not prove remote power-off behavior; require a qualified liveness producer and separate injection-current assessment.
5. Native unconnected-count zero is insufficient: straight-line net connections can produce hundreds of shorts. Acceptance requires all error categories and schematic parity, plus rendered review.

The accepted graph counterexamples and native-report correction are published in
`zapote/skills/revisions/interlock-lessons-v1/catalog.json`, with hashes of the
actual tests and final evidence. That revision is for subsequent attempts; the
current attempt's original selection remains unchanged. These lessons do not
expand the demonstrated qualification scope of earlier boards.
