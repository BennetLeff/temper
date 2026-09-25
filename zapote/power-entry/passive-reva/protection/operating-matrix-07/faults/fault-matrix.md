# Operating matrix 07 — bounded fault cases

Status: **prepared, execution gated** (2026-09-20).

The cases in this file are proposals until the host accepts a contiguous
cold-start normal prefix from `matrix07_normal`. No case may be run from a
hand-written operating-point `.ic` or from a precharged shortcut. If the
normal prefix is not accepted, the case is recorded `UNEXECUTED` with the
blocking receipt; its source, attempted command, and any failed trace remain
retained.

## Fixed model boundary

The earlier controller-integration-06 files are historical references.
They are not an accepted source for this campaign: that witness starts
precharged, and the controller has since been repaired. The campaign source
will be the accepted matrix07 cold-start deck and its exact include hashes,
recorded in a separate execution receipt. The repository base commit alone
does not identify these uncommitted model files. The power path is:

```
AC source -> Rsource -> AC1 NTC/relay branch -> bridge -> Lboost
          -> switch node -> boost diode(s) -> vd -> F2 -> vb capacitor bank
```

The NTC and bypass relay exist only in the AC1 source branch. They are not
allowed to be inserted into the boost loop. `Lboost`, the boost diode(s), and
F2 are the only feed path to the bank in these cases.

The normal worker must provide, before execution:

* a source deck and SHA-256 hash;
* an accepted cold-start prefix ending at `t_prefix`, with complete trace
  header/order and no hand-picked initial conditions;
* the command and Rust receipt that established the prefix; and
* the accepted normal operating interval from which a fault event can be
  selected.

Each fault deck shall be a mechanical edit of that accepted source. The only
new initial conditions permitted are those carried forward by the contiguous
prefix/restart mechanism; a fresh IC on `vd`, `vb`, `Lboost`, or controller
state is a rejection.

## Cases

| ID | Fault graph/state | Event source and required starting state | Expected protection interpretation |
|---|---|---|---|
| F2-CREST | `Sf2` transitions closed→open while AC1 source is at a mains crest | Accepted settled-normal interval; choose the first event where `abs(v(acsrc,acn))` is within 1% of the local crest and record phase/time | Detector/latch may stop a healthy switch. Report `i(Vchannel)` cessation separately from residual passive current through `Lboost`/diodes/capacitors. |
| F2-ZERO | Same F2 open graph state | Accepted settled-normal interval; choose the first event where `abs(v(acsrc,acn))` is within 1% of an AC zero crossing | Same screens as F2-CREST; crest and zero are distinct stress cases and both are required. |
| F2-START | `Sf2` opens during cold startup before normal regulation | Accepted cold-start prefix only; event must occur after the source/rail sequence begins and before the accepted normal interval | A startup fault is valid only if all rows before the event are contiguous and complete. No precharged bank or controller IC is evidence. |
| SW-SHORT | `Msw` failed-short state (low-ohmic channel independent of gate) | Accepted settled-normal interval, then mutate only the switch state | Gate command/latch is **not** credited with interrupting this path. If channel current remains, verdict is `PROTECTION_GAP`/unsafe even when `q` and `en` stay low. |
| DIODE-SHORT | Boost diode path shorted, switch remains healthy and controllable | Accepted settled-normal interval, then mutate one declared diode path; if the model has parallel Dboost legs, preserve the exact one-leg/two-leg identity in the receipt | A healthy switch may be turned off, but diode-short stress and residual passive current remain separate findings. Do not claim the switch opens a path it does not own. |
| BOTH-SHORT | `Msw` failed-short **and** boost diode path shorted | Accepted settled-normal interval, then apply both mutations in one deck | Distinct graph state from either single fault. No gate-interruption credit; persistent channel current is an explicit failure. |
| BYPASS-NEG | Protection detector bypass (`BYPASS=1` or equivalent bypass control) with one declared fault | Same accepted prefix and event as F2-CREST (re-run as a negative control) | The Rust validator must reject a trace lacking a valid fault/latch/current-cessation witness. A clean simulator run with bypassed protection is never a pass. |

`SW-SHORT`, `DIODE-SHORT`, and `BOTH-SHORT` must remain separate artifacts and
separate verdict rows. Combining them into one “short fault” loses the state
information needed to decide whether gate shutdown can interrupt the path.

## Evidence and validator contract

Every attempted deck, including a failed or indeterminate run, retains the
deck bytes, source hash, command, simulator version, stderr/stdout, trace,
and a Rust verdict. The verdict is one of `PASS`, `FAIL`, `PROTECTION_GAP`,
`INDETERMINATE`, or `UNEXECUTED`; `PASS` is unavailable for an unaccepted
normal prefix, a bypassed detector, a failed-short switch, or incomplete
evidence.

The independent Rust validator is `fault_checks.rs` and must enforce
all of the following before evaluating behavior:

1. **Strict finite complete trace.** Exact header and column order, every
   numeric field finite, strictly increasing time, bounded sample gaps, first
   time at zero, and last time at declared `TSTOP`. A truncated ngspice file
   is `INDETERMINATE`, never an empty success. The case receipt must also
   provide the expected fault time and event window; an unset window fails
   closed.
2. **Node-specific screens.** Screen the actual `vd`, `vb`, `sw`, `gate`, and
   `Lboost` columns against limits supplied by the accepted model receipt
   (`VB` nominal screen is 450 V in the frozen checker; these are model
   screens, not silicon maximum claims).
   Limits are fixed before a run; they cannot be widened after a violation.
   Also screen detector/fault/latch rails and report the first offending node
   and time.
3. **Current-channel split.** After the detector/latch event, report (a)
   current through the commanded switch channel (`i(Vchannel)`), and (b)
   remaining passive current (`i(Vbody)`, `i(Lboost)`, and any explicitly
   recorded diode/F2 branch currents). A low gate or low `q` does not imply
   current cessation. For `SW-SHORT` and `BOTH-SHORT`, any sustained channel
   current is a protection gap even if the latch remains low.
4. **Retained latch/no auto-rearm.** Locate the first valid detector event,
   then require a predeclared turnoff budget, separate `q`/gate/channel
   delays, and a complete post-event observation window. `q`, `en`, and the
   gate command must remain below their off thresholds through that window;
   any later rising edge is an auto-rearm failure. A detector bypass cannot
   satisfy this witness.
5. **Fault-state identity.** The result names the exact graph mutation and
   switch state (`healthy/on`, `healthy/off`, `failed-short`, or
   `failed-open`). A protection claim may credit only a device that is healthy
   and actually lies on the path being interrupted.

The checker is a Rust executable/library. Python or shell may copy the
accepted deck, launch ngspice, and record hashes only; no Python behavior
checks or tolerance calculations are authoritative.

Its bounded self-check is:

```text
rustc --edition=2021 --test fault_checks.rs -o /tmp/fault_checks_tests
/tmp/fault_checks_tests
```

The tests retain negative probes for a truncated trace, absent fault event,
detector bypass, latch re-arm, and a low gate with sustained channel current
in the failed-short switch state.

Campaign invocation must supply the per-case timing receipt explicitly:

```text
fault_checks TRACE.tsv TSTOP KIND EXPECTED_FAULT DETECTOR_WINDOW TURN_OFF_BUDGET OBSERVATION [MAX_GAP]
```

`MAX_GAP` defaults to 1 us for a long prefix; the checker applies a separate
25 ns bound from the detector window through the retained-off observation.

## Bounded execution gate

Execution remains blocked until the host sends an acceptance receipt for the
normal prefix. Once accepted, each case gets a bounded attempt with the
declared simulator options and wall-clock/deck budget. On a missing
prefix, malformed trace, timeout, or timestep abort, retain the failed
attempt and mark the case `UNEXECUTED` or `INDETERMINATE` as appropriate.
Any repaired rerun is a new retained attempt with the changed source and
reason identified; acceptance limits must not be widened to hide a failure.

No result from this matrix qualifies hardware, component ratings, thermal
limits, mains safety, or production protection. It is a model fault-state
screen only.
