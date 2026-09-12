# Validate the fault boundary, not just a digital truth table

Before accepting a sensor-disconnection detector, compare the coldest valid sensor against the most difficult open-wire corner. Apply leakage in the direction that reduces each margin; use the source network's Thevenin resistance. Document the operating range and the loading obligations at connectors. Typical input bias is not an aggregate cable-leakage guarantee.

Calculate the time to cross the actual comparator threshold from the worst initial capacitor voltage. One RC time constant does not prove a near-rail detector meets its deadline. Bind filter capacitance and tolerance to source values and mutate them until the timing rule fails.

Evaluate comparator input voltages under normal, hot, each lead open, short-to-ground/supply and reconnect scenarios, then apply the real logic gate. A correct OR truth table alone cannot prove those analog inputs produce the required states. Keep hysteresis feedback attached to its intended raw comparator output.

Transfer this procedure, not thermal resistor values, beta extrapolations, or fault-time claims. Rev A's historical open-sensor gap is repaired in Rev B under explicit assumptions; shutdown latching, power loss and physical qualification remain separate obligations. See thermal-sense/MODEL.md and its Rust defect controls.
