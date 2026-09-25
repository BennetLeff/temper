# SW-SHORT settled direct-capture launch packet

Status: **prepared, unlaunched, and awaiting explicit parent launch**. This
directory contains only launch materials; no solver, raw trace, or acceptance
result has been started or copied here.

The wrapper materializes the exact eight-file closure from
`../settled-compact-prep-24/prepared/SW-SHORT` into a fresh `full-SW-SHORT`
directory, checks source hashes before and after copying, checks the reviewed
tool/library hashes, then invokes the parent-reviewed runner-45 and direct-
fault37 tools. It refuses to run with less than 16 GiB free (10 GiB runtime
floor plus 6 GiB archive reserve), a known solver/campaign process, or an
existing output directory. `SPICE_SCRIPTS` is pinned to ngspice 45.2.

The immutable contract is `t_fault=0.6541666666667 s`, `TSTOP=0.662 s`,
2 ms prefault/event/observation windows, 2 us turnoff, 25 ns local capture
gap, and 1 us outer adapter/validator gap. Runner and validator kind are
`switch-short`; there is no bypass flag. The parent must rerun all gates and
explicitly launch `./launch.sh` after the current F2-ZERO session has ended.

Interpretation remains precise: a failed-short category can never be `PASS`,
and node or detector-event failures take precedence. `PROTECTION_GAP` is a
categorical result after those screens, while `i(Vchannel)` includes the
failed parallel branch. The frozen checker's “after latch” message actually
describes post-detector accumulation. This case commands no F2 opening; F2
stays closed. Full prefix, phase, endpoint, event, and electrical review is
required after capture; no F2-CREST/F2-ZERO evidence may be reused.
