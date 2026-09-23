# Discharge interface contract — draft U1

The unit receives `VD_LOCAL`, `VB_BANK` and `HOT0` from the Rev38 PFC section, with F2 separating VD and VB. The proposed active discharge must have a physical control default that engages on the relevant loss of supply; firmware may monitor and sequence it but cannot be the sole power-loss trigger. Exact control rail, relay/switch, return and insulation boundary remain to be selected.

Provide **separate** measured or otherwise guaranteed residual-charge information for VD and VB to service and restart logic. The Rev38 VD/VB comparator detects certain discrepancies but equal readings cannot prove F2 continuity or safe discharge. A third energy island is added if the inverter introduces capacitance behind a disconnect. The unit must publish its residual-charge and ready/unsafe outputs, their powered-off behavior and their timing evidence before integration.

The historical split-rail `BusDischarge` in `elec/src/modules.ato` and its two ~170 V strings are not adopted for this circuit. Any reuse requires a fresh 390 V/DC contact, resistor pulse/continuous power, creepage and physical envelope calculation. No mains or service-touch claim follows from this draft.
