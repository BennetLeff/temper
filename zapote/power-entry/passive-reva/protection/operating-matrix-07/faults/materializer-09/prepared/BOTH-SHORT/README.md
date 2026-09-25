# BOTH-SHORT prepared fault deck

Status: **PREPARED_UNEXECUTED**.

This directory was mechanically copied from the hysteretic-driver candidate and rewritten for T_FAULT=1.000000000000e-5 s, TSTOP=2.000000000000e-5 s, and the explicitly supplied PREFAULT_WINDOW=1.000000000000e-6 s. It has not been simulated and carries no accepted operating-point claim.

The original normal `.save` diagnostics remain, followed by the exact 17-column fault schema and four branch/marker extras. F2 and both boost diode legs have ideal 0-V sense sources. The pacing source is isolated, alternates at 25 ns corners from T_FAULT-PREFAULT_WINDOW-25 ns through TSTOP, and is instrumentation that requires production revalidation.

The `fault_inject` marker is the actual control voltage continuously (`5-V(f2ctl)` for an F2 open, the switch-control voltage for a short, and the maximum of both for BOTH-SHORT); acceptance can threshold that marker at 2.5 V. SW models use approximately 2.6 V rising and 2.4 V falling thresholds around Vt=2.5 V, so marker/source timing is bounded by the 1 ns finite PWL edge plus accepted solver sampling, not an arbitrary hard-time marker.

Execution remains blocked until the accepted normal source, event selection, and prefault instrumentation are reviewed.
