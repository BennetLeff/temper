# RTD conditional passive-network timing result

Exact-source fact for the bound RTD design only. Do not use this number as a constraint for another unit or a modified RTD circuit.

The reviewed external passive-network certificate gives a maximum conditional detection bound of 0.971459818540245 ms within a fixed 2 ms detector allocation for its declared topology and parameter envelope. Rust independently recomputes the five fault certificates and checks runtime fault-row consistency.

Overall qualification remains INDETERMINATE. Comparator hysteresis, common-mode/input-capacitance conditions, the MAX31865 force-path idealization and guaranteed brownout timing are not fully qualified. Physical measurements are NOT RUN. This note does not promote the hardware to PASS.

Read the bound certificate and applicability review before citing the result. Any source identity mismatch makes this entry inapplicable; requalification must produce a new reviewed memory revision.
