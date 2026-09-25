# Instrumentation repair probe 15

This folder isolates the startup-candidate-13 convergence failure with six
short ngspice probes, each capped at 15 seconds and TSTOP=10 ms. The original
startup candidate remains untouched. The accepted baseline topology completes
10 ms (`142459` data rows). The prepared fault case, with its added branch
current probes and marker/schedule instrumentation, aborts at
`4.41687 ms`, timestep `6.25e-19`, node `vbody#branch`.

The retained final probes are diagnostic transformations, not one-change
experiments. `no-diode-sense` completes 10 ms (`142410` rows) after restoring
the direct `Dboost1/2 sw vd` connections, removing both zero-volt diode sense
sources, and removing their saved branch fields. `no-f2-sense` also completes
10 ms (`142492` rows), but applies that same diode-topology transformation and
additionally changes `Vf2sense` from 0 V to 1 mV while removing the diode sense
fields. Because each passing case changes several electrical and saved-signal
items together, these results establish only that the combined transformations
avoid the observed failure. They do not isolate sensor removal, reconnection,
or saved-field export as the individual cause, and a 1 mV source is a physical
topology change rather than a measurement-only change.

`no-schedule` leaves the zero-V diode topology in place and removes only the
isolated 1 Gohm timing instrument; it still fails at the same timestep. The
retained directory named `no-marker` is mislabeled: its final case changes
`Vbody` from a 0 V source to 1 mV and does not remove the fault marker. It also
fails at the same point, so `vbody#branch` is a reported branch location, not
an established root cause.

These are diagnostic topology probes. Replacing the zero-V current sensors
changes the measurement graph and drops their saved branch fields in the two
passing variants; it is not an adopted electrical fix or a protection claim.
No repair is recommended by these probes. A future instrumentation variant
must use a new case directory and preserve the exact 42-field schema; a
solver-only candidate is being evaluated separately. No full fault or campaign
run was launched.

## Provenance correction

The `no-diode-sense` and `no-f2-sense` directories were edited in place during
the bounded probe work. Before the final cases recorded here, the parent agent
observed two intermediate failures: an earlier `no-diode-sense` variant with
1 mV diode sources stopped after 24,920 rows, and an earlier `no-f2-sense`
variant with zero-V diode sources plus a 1 mV F2 source stopped after 24,758
rows. Those files and logs were overwritten by the final transformations, so
the counts are historical observations only and have no retained case or log
hash. They must not be treated as reproducible one-change evidence. The hashes
in `verification.json` and `manifest.json` identify only the final retained
cases and logs.

## Reproduction

```sh
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
for d in baseline10ms originalfault10ms no-diode-sense no-f2-sense no-schedule no-marker; do
  (cd "$d" && perl -e 'alarm 15; exec @ARGV' /opt/homebrew/bin/ngspice -a -o run.log case.cir)
done
```

`probe-results.tsv` records the exact source change and observed result. The
case include closure is copied into every probe directory; original startup
raw/log artifacts are not modified.
