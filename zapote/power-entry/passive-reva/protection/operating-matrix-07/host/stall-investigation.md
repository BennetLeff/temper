# Corrected cold-start stall investigation

Observed reproduction: `final-cold-continuation.cir` (hash
9925f3da8b8891ca0348b540831be2a1b33a2f86814570a3fd283b031d9d469d)
advanced to the printed time 0.351501 s, then repeated that value for more
than three minutes. It never reached its 500 ms breakpoint or requested
1 s endpoint. This is a printed, rounded time, not an exact captured state.
The controlled attempt was terminated and retained under
`../normal-startup/stalled-351ms/`. It has no exported waveform.

Verified assumptions: all four includes match host-reviewed hashes; the
source starts the bus/controller capacitors at zero; the corrected clamp and
physical standby are included; 5.2 GiB free disk was reported; output export
had not begun, so the waiting compressor was not blocking simulation; the
500 ms stop/resume command had not yet executed. A separate 20 us fixture
has 20,511 strictly increasing-time rows across stop/resume. Batch SIGINT
terminates this build without executing post-run export commands.

Not verified: exact time and electrical/digital state at the stall, accepted
and rejected timestep counts, the troublesome node, event rollback counts,
memory pressure, and the causal relationship between any model expression
and this symptom. Short controller fixtures passing does not settle these.

Leading hypothesis: a timestep/event boundary keeps the solver working with
negligible or no forward time. Support is the repeated rounded simulation
clock while the log continues growing; the model contains hard comparator
transitions and mixed-signal events. Prediction: a capture will show dense
or rejected steps/event rollbacks around a specific boundary. Competing
explanation: resource pressure has collapsed throughput. It ranks lower
because progress stopped within the same narrow printed-time interval,
but memory and iteration observations are required to distinguish them.
Neither is an established root cause. Do not change tolerances, model
behavior or acceptance limits on the strength of these hypotheses alone.

The next instrument is the installed libngspice 45.2 shared API, which can
pause a background run and inspect/export its vectors without an X display.
Pause/export/resume now passes on the short PWM fixture, with its resumed
waveform byte-identical to the earlier CLI fixture; arbitrary pause/resume
also passes on an RC fixture. The observed shared-library background
callback boolean means stopped/ready when true, despite the header label.
The host-reviewed transport waits for both completion and an idle solver.
See `../transport-capture/receipt.md`.

Fresh-process snapshots cannot replace same-process continuation for this
circuit: the isolated XSPICE probe reports that `snsave` is not implemented
for A devices and creates no snapshot. See `snapshot-restore/result.md`.
The next replay uses the same
electrical source with extra saved diagnostic nodes and a 300 ms breakpoint
before the known stall. Preserve that checkpoint before resuming. At the
stall request `bg_halt`, `where`, `rusage`, and event statistics and export the
available state. The shared-library interface is transport; Rust checkers
continue to own engineering verdicts.

Execution refinement: the chosen diagnostic breakpoint is 351.49 ms, with
stored output beginning at 340 ms; the solver still integrates from cold
initial conditions. The parent CLI reference stops/exports there, while a
shared-library replay can continue and pause at the troublesome state.
This limited recorded window is diagnostic only and cannot pass the normal
cold-start acceptance checker.

## Captured replay, 2026-09-20

The CLI checkpoint exported 501,348 finite, strictly increasing rows from
340 ms through 351.49 ms. The minimum observed timestamp separation is
5.5511151231257827e-17 s. This is a separation in the exported trace, not a
direct measurement of the solver's internal timestep. At the checkpoint
VB is 364.446973 V, with enable asserted and no reported protection fault.
The shared-library replay reproduced the checkpoint's row count, numerical
state and solver counts: 17,009,937 timepoints, 45,377,215 iterations and
3,144,441 rejected timepoints.

After resume, the shared run passed the former rounded stall time without
an electrical-model change. After 60 seconds of further execution it was
deliberately halted at 0.373498343395387178 s, VB=369.311725 V. That halt is
not itself evidence of another stall. The exported continuation nevertheless
fails strict monotonicity: row index 502304 repeats timestamp
0.351508835331273084 s. The harness returned an error before its planned
ready marker or inspection wait. No accepted operating point results.

The pre-checkpoint analysis localizes the smallest timestamp separations
away from raw-comparator edges: all 2,966 held-PWM crossings of 2.5 V occur
in intervals <=1e-10 s, while all 2,966 raw-comparator crossings occur in
larger intervals. This motivates an isolated test of the hard gate/blanking
switching expressions at the held-PWM threshold. It does not yet prove
which expression causes the duplicate or establish a valid repair.

Independent inspection of the entire resumed export found 1,499,613 rows
and 7,847 non-increasing timestamp intervals. The first affected one-based
data row is 502305 (the transport reported zero-based index 502304).
Its unequal values include analog nodes and blanking state; it is not an
external PERMIT transition. PERMIT remains 5 V. The canonical capture and
inspection are under `../diagnostic-capture/shared-replay/`. The CLI and
shared pre-checkpoint traces have identical uncompressed SHA256
`86e39b93761aa9143b4c83bfec0c2949b59eed098ad91b473d8dc91e683c8c85`.

A bounded standalone fixture with the hard gate/blanking expressions and
gate R/C path, driven by a prescribed held-state ramp, did not reproduce
duplicate timestamps at either an early or late absolute time. It omits
the full mixed-signal latch/plant feedback interaction, so this negative
result does not exonerate the complete model. It does rule out claiming
that those expressions alone are a demonstrated sufficient cause. No
numerical repair or valid complete startup is established by this work.

## Mixed-signal reproduction and candidate repair

The next fixture restored the actual ADC/DFF/DAC chain omitted by the
prescribed-ramp probe. It reproduces a `Timestep too small` failure at both
early and late absolute time. Controlled ablations localize that fixture's
failure to re-thresholding the finite DAC ramp into an ideal gate step.
Scaling the existing finite ramp allows the fixture to complete. Independent
review then exposed an undefined-state compatibility defect in that first
candidate: 2.5 V DAC output became 7.5 V gate output. The complete candidate
also maps undefined PWM to zero. See `../numerical-repair/README.md` for
source, traces, and positive/negative controls.

All six controller fixtures pass with the complete candidate. The final
500 ms full cold run is underway in `../normal-finite-edge-safe/`; that
run's strict trace/operating-point check is still required. Isolated causal
evidence does not yet establish the cause of every old full-plant symptom.

## Tracked finite-edge-safe attempt: complete failure capture

The previously unobservable CLI run was terminated after 76 minutes and
replaced by the same electrical inputs in the shared transport. A one-minute
probe first verified accepted-time reporting and partial export. The full
tracked attempt then stopped advancing at 0.348534537976268155 s while
callbacks continued. Its 120-second non-advancement guard halted and exported
the complete partial trace; no waveform state from the old CLI run was
recovered or inferred.

The strict normal checker rejects the export. There are 14,951,468 rows and
1,126,438 nonincreasing intervals; the first repeated timestamp is already
0.256990362212805523 s at one-based data row 9,736,224. Equal-time rows carry
different analog values. The ending VB is 366.544469 V; q/en remain high and
fault low. The last gate value is approximately -5.836 uV. This establishes
a numerical failure with retained evidence, not a power-stage safety result.
See `../normal-tracked/inspection.txt`, `tail.tsv`, and `execution.json`.

The complete-model cause is still under investigation. In particular,
isolated success of the finite-DAC-edge repair must not be generalized to
this feedback-coupled circuit. Next work is a targeted reduced reproduction
or targeted added-node capture, not another uninstrumented long run.
