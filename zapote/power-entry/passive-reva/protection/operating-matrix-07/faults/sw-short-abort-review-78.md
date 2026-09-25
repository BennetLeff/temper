# SW-SHORT numerical abort review

The retained `full-SW-SHORT` run is incomplete and cannot earn acceptance. `stop.txt` records `solver_stopped` at simulation time `0.654402648629686778 s`, after 30,686,230 points. The host reports a transient timestep of `6.25e-19 s` and trouble at `vdboost2sense#branch`, then aborts. This is only 235.981963 microseconds after the expected fault marker (`T_FAULT=0.6541666666667 s`) and leaves 7.597351370 ms before the required `TSTOP=0.662 s`.

The metadata also records `first_invalid=true`, 143 duplicate timestamps, zero backwards timestamps, and no nonfinite time. Those diagnostics describe the failed capture; they do not establish a physical fault result. The named branch is the solver's reported convergence location, not proof that the diode-sense branch is the root cause.

Two bounded hypotheses remain testable:

1. The 1 mOhm, gate-independent `Sswfail` branch turns on in parallel with `Msw` while the ideal 0 V `Vdboost2sense` probe is present. That hard topology/conductance transition may be the local convergence trigger.
2. The failed-short edge overlaps mixed-signal protection/PWM transitions and ideal zero-volt probes. Their combined algebraic event may create stiffness even if the named branch is only where Newton fails.

A small discriminating experiment can avoid another 650 ms run: build a standalone micro-deck containing the retained `Sswfail`/`SWFAIL`, diode, `Vdboost2sense`, and `Vchannel` topology, with the same transient options and a normalized event at zero over tens of nanoseconds. Compare a variant without `Sswfail` against one retaining it while suppressing the controller/PWL edge. Convergence and timestep collapse at the sense branch would distinguish the two hypotheses, but neither fixture result would prove full-deck behavior.

Only regular logs, the frozen case deck, and prior review documents were read. No FIFO, raw trace, solver, process control, or source file was touched.
