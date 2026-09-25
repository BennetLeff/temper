# ngspice 45.2 stall diagnostics (read-only research)

This note does not identify a failed node or change the active deck. The
current observation is repeated `Reference value` output around 351.501 ms,
with no `timestep too small` diagnostic. CPU activity alone does not establish
whether the run is progressing, backing up timesteps, or spending time in the
mixed-signal event solver.

## Supported interactive diagnostics

The ngspice 45 manual's `where` command is the most direct next observation.
It records the last node or device that caused non-convergence and may be
issued during a run or after failure. The manual explicitly recommends
interrupting a severely slowed/hung transient with Control-C and then issuing
`where`, while warning that only one troublesome node/device is reported.
Therefore it is a clue, not a root-cause proof.

In the interactive process, after the operator confirms the current run is the
intended PID, the supported sequence is:

```text
Control-C
where
status
rusage tranpoints traniter rejected trancuriters trantime
```

`status` reports active breakpoints. `rusage` reports accepted/rejected
time-points, total and current transient iterations, and transient time, so it
can distinguish active progress from repeated rejected-step work. `iplot` can
monitor selected analog/event nodes while transient analysis runs; the manual
specifically documents pairing `iplot` with `where` for a severe slowdown.

If the process returns to the control interpreter rather than terminating,
`wrdata` can export the vectors currently present, and `snsave FILE` can save a
controlled stop state. A breakpoint must be installed before `tran`/`run`:

```text
stop when time = 400m
tran 500n 1s
```

At a breakpoint, `resume` continues the simulation. `snsave`/`snload` are the
documented snapshot route, but require a deliberately tested original-circuit
loading arrangement; they are not a claim that arbitrary SIGINT is resumable.
Our isolated SIGINT probe separately showed batch ngspice 45.2 exits with
`-2` and does not reach post-`tran` `wrdata`.

For mixed-signal state, `edisplay` lists XSPICE event nodes and event counts,
`eprint NODE` prints event times/values plus event-solver statistics,
`eprvcd` can write event nodes to VCD, and `esave` restricts saved event
outputs. The manual's XSPICE example reports event/analog alternations,
event passes, transient load calls, and timestep backups in `eprint` output;
these are the useful observations for a digital/analog event-loop stall.

## What the candidate structure suggests (hypotheses only)

The candidate uses a `time-floor(time/PERIOD)` behavioral construction,
ideal ternary B comparators, `adc_bridge` with equal 2.5 V thresholds, a
`d_dff1ps`, and a 1 pF blanking capacitor discharged through 1 ohm. These
features can create dense discontinuity/event boundaries or very stiff analog
time constants, and XSPICE's analog/event rollback statistics could expose
that. They are plausible causes of high rejected-step/event work, but there is
no evidence yet that any one is the failing element.

Repeated `Reference value` lines are not, by themselves, a timestep failure.
Without `where`, `rusage`, event statistics, or a captured final time, the
root cause remains unknown. Do not infer which comparator, DFF, blanking node,
or power node failed, and do not widen engineering limits to make the run
green.

## Primary references

- [ngspice 45 User's Manual](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf), sections 13.5.43 (`iplot`), 13.5.70 (`rusage`), 13.5.89–91 (`status`, `step`, `stop`), 13.5.105 (`where`), 13.5.84–85 (`snload`/`snsave`), and XSPICE chapters 21–23.
- [ngspice XSPICE overview](https://ngspice.sourceforge.io/xspice.html), describing the event-driven analog/digital coordination and code-model subsystem.
- [ngspice documentation index](https://ngspice.sourceforge.io/docs.html), which identifies the versioned manuals and time-step-control documentation.
