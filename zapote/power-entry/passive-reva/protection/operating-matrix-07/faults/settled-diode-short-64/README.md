# DIODE-SHORT settled direct-capture launch packet

Status: **prepared, unlaunched, and awaiting explicit parent launch**. This
directory contains only launch materials; no solver, raw trace, or acceptance
result has been started or copied here.

The wrapper materializes the exact eight-file closure from
`../settled-compact-prep-24/prepared/DIODE-SHORT` into a fresh `full-DIODE-SHORT`
directory, checks source hashes before and after copying, checks the reviewed
tool/library hashes, then invokes the parent-reviewed runner-45 and direct-
fault37 tools. It refuses to run with less than 16 GiB free (10 GiB runtime
floor plus 6 GiB archive reserve), a known solver/campaign process, or an
existing output directory. `SPICE_SCRIPTS` is pinned to ngspice 45.2.

The immutable contract is `t_fault=0.6541666666667 s`, `TSTOP=0.662 s`,
2 ms prefault/event/observation windows, 2 us turnoff, 25 ns local capture
gap, and 1 us outer adapter/validator gap. Runner and validator kind are
`diode-short`; there is no bypass flag. The parent must rerun all gates and
explicitly launch `./launch.sh` after the current F2-ZERO session has ended.

This is a terminal graph experiment: the diode-side short spans `sw` to `vd`,
and F2 remains held closed at constant 5 V. Common-cathode branch probes are
instrument paths, not independent die currents, so no die allocation,
package-sharing, thermal, or SOA claim is permitted. Node or detector-event
failures take precedence. Full prefix, phase, endpoint, event, and electrical
review is required after capture; no other fault evidence may be reused.
Initial F2-ZERO pipeline header failure remains under investigation; parent
decides whether runner-45 is fit.
