# Native startup readiness capture, protocol v2

Fresh native ngspice 45.2 development capture using the unchanged model
(`62d3bda599e7f7a301b9cc7115e305d33e48edb07957e7f5602c19b92956e096`). The
fixture begins with a 1 us discharged hold, then ramps VIN from 0 to 15 V
over 1 ms (1 us to 1.001 ms), and captures through 21.001 ms. EN is tied to
VIN; the load is voltage-compliant `0.5*clamp(VOUT/0.1,0,1)`. The zero-volt
`LOAD` source is a current probe and does not alter the load topology.

The untouched binary rawfile has exactly five native vectors: `time`,
`v(out)` voltage, `v(in)` voltage, `i(vin)` current, and `i(load)` current.
It contains 4,015,356 points. The first saved point is within the 1 us
discharged hold (the transient starts at the simulator's initial positive
time step); the VIN ramp reaches 15 V at 1.001 ms, so the 13.5 V crossing is
0.901 ms. Native measurements: final load average 0.500000 A and final output
average 3.314848 V over 20.001–21.001 ms. The run exited 0 with no simulator
error. Model, deck, provenance, log, simulator version, rawfile, and complete
hashes are retained in this directory.

This is decoder and harness readiness evidence only, not qualification or
hardware evidence.
