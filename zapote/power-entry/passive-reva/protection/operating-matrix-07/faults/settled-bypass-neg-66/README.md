# BYPASS-NEG settled direct-capture launch packet

Status: **prepared, unlaunched, and awaiting explicit parent launch**. This
directory contains only launch materials; no solver, raw trace, or acceptance
result has been started or copied here.

The wrapper materializes the exact eight-file closure from
`../settled-compact-prep-24/prepared/BYPASS-NEG` into a fresh `full-BYPASS-NEG`
directory, checks source hashes before and after copying, checks the reviewed
tool/library hashes, then invokes the parent-reviewed runner-45 and direct-
fault37 tools. It refuses to run with less than 16 GiB free (10 GiB runtime
floor plus 6 GiB archive reserve), a known solver/campaign process, or an
existing output directory. `SPICE_SCRIPTS` is pinned to ngspice 45.2.

The immutable contract is `t_fault=0.6541666666667 s`, `TSTOP=0.662 s`,
2 ms prefault/event/observation windows, 2 us turnoff, 25 ns local capture
gap, and 1 us outer adapter/validator gap. Runner kind is `bypass-neg`, mapped
to validator kind `f2-open`, with the required `--bypass` flag; the parent must rerun all gates and
explicitly launch `./launch.sh` after the current F2-ZERO session has ended.

This is the negative control: the frozen `--bypass` checker rejects before
waveform evaluation, so that rejection alone is never a successful negative
control or protection result. The parent must separately review the complete
saved raw archive, own healthy prefix/phase/endpoint, detector/fault markers,
q/en/gate/channel rows, and any waveform-only counterfactual audit. Adapter
detector-dependent latch fields may remain absent by construction. F2 opens at
the declared fault time: `Vf2ctl` falls from 5 V to 0 V. The bypass disables the
detector while retaining that same scripted opening. Initial F2-ZERO pipeline
header failure remains unexplained; independent saved-archive recovery passed
with the same decoder, adapter and validator. The parent decides when to launch.
