# Rejected runtime experiment

The 1 pF / 1 ohm artificial blanking integrator was suspected of adding
numerical stiffness. A narrow candidate replaced it with a 300 ns XSPICE
digital delay, keeping the remaining revised controller and warm fixture
identical. This is a diagnostic performance experiment, not normal startup.

A single paired run took 8.482 s for baseline and 8.409 s for the candidate;
rows fell from 154269 to 147975. This small difference does not demonstrate
a useful runtime improvement. The candidate is NOT adopted. No physical
component parameters or acceptance limits were adjusted. Source, traces,
logs and timing receipts are retained; the active startup model is unchanged.

The installed ngspice 45.2 also supports KLU. A separate identical-model
solver trial (`klu/`) took 8.895 s and passed the same warm-witness checks.
That did not improve this workload, so Sparse 1.3 remains the active solver.
The trial followed the [ngspice solver documentation](https://ngspice.sourceforge.io/applic.html).
These single paired timings reject an obvious speedup; they are not a
general performance comparison between solvers.
