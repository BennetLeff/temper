
*The coil's large initial response relative to its small final DC response includes its physical L/R behavior. Calling that ratio feedback-loop overshoot would be misleading, so no coil overshoot percentage is assigned. Settling uses a ±1% band of the measured peak TIA change around the final plateau or initial baseline. It is not 1% of the coil's small DC step.

`current-windows.csv` reports actual RG, feedback-inductor and DUT currents, together with HIGH-buffer, LOW-buffer and TIA macro-model output currents. Negative output current indicates current sunk by the amplifier. ADC windows use actual pin voltages, not only differential signals. The export includes `rf_end`, so the physical placement of the inductance can be audited from the deck and trace.

A bounded 20 µs transient does not establish every loop's stability or phase margin. The 50 nH negative control can remain bounded while failing the separate 45° margin criterion. These are imposed lumped inductances, not extracted PCB measurements; routing qualification remains separate. No physical-board accuracy or noise claim follows.
