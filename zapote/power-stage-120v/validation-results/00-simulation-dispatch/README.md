# Native-13 simulation results — 2026-09-27

Source revision: `36ba41f24`. Board SHA-256:
`8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.

The official Infineon ZIP/library match both runbook hashes. The coordinator
ran all 16 smoke checks on ngspice 45.2 successfully. All five workers also passed this
gate independently before task work. These reference runs use placeholder
inputs and establish the simulator setup only, not design acceptance.

| Task | Result | What remains unresolved |
| --- | --- | --- |
| [01 Switching](../01-switching-parasitics/README.md) | BLOCKED; geometry extracted | Missing exact capacitor ESL, incomplete paired paths, and no complementary-drive ZVS model |
| [02 Protection](../02-protection-timing/README.md) | Partial SPICE; full verdict BLOCKED | CT solver stalls, small-overdrive comparator delay, final gate-off/device stress |
| [04 Copper/thermal](../04-board-current-thermal/README.md) | BLOCKED; solver audit reproduced | Four-layer barrel resistance, multisource loss interpretation, invalid-node and singular-grid handling |
| [05 Tank](../05-resonant-tank-envelope/README.md) | Partial envelope; acceptance BLOCKED | Exact capacitor limits at modeled frequency/temperature and task 01 ZVS boundary |
| [07 EMI](../07-conducted-emi/README.md) | BLOCKED; confirmed part/footprint contradiction | C1/C2 pitch mismatch, missing parasitics/edges/pad and incomplete common-mode source model |

All workers use GPT-6 Sol at xhigh effort, each on a separate task branch and
worktree based on the same source revision. Outputs stay under their assigned
`validation-results/NN-*/` folder. The coordinator integrates those files and updates the master status.
No board, source, placement, routing or shared kit edits are authorized by this
validation run. Vendor libraries remain ignored and are not committed.

The master/task documents contain historical native-09 references. The runbook's
native-13 instruction and the actual input hash above govern this run. Missing
values, failed criteria and unsupported model conclusions must remain explicit
BLOCKED/FAIL findings, never guessed inputs or silent solver changes.

## Coordinator checks communicated to workers

- The runner does not expose ngspice return codes and ignores the second raw
  run's status. Workers must inspect full logs, required measurements and raw
  time coverage before consuming results.
- The switching starter deck imposes hard turn-on with the high side held off.
  It does not by itself establish a complementary-drive dead-time/ZVS boundary.
- The sheet solver applies its full barrel resistance to every adjacent-layer
  edge. The four-layer topology and multi-source resistance/loss interpretation
  require independent checks before board conclusions; the supplied two-layer
  near-zero-via-resistance self-test does not establish those cases.

These instrument limitations are documented in the task reports. They do not
establish an electrical failure of the board, nor support a board PASS.

## Confirmed board finding

C1 and C2 specify **KEMET R463R410000M1M**, whose manufacturer drawing gives
**27.5 ± 0.4 mm lead pitch** and a 32 × 20 × 11 mm body. Native-13 has
**22.50 mm pad pitch** for both. The 5.0 mm nominal mismatch is independently
reproduced using KiCad's board reader and checked against the exact ordering
code in the official [KEMET datasheet](https://content.kemet.com/datasheets/KEM_F3095_R46_X2_310_110C.pdf).
Task 07 retains the PDF, hash, dimensional inputs and checking script.
Resolving the part/footprint choice requires a design revision; this validation
round has not changed the PCB or substituted a part.

## Next work

1. Resolve C1/C2 part and footprint dimensions, including body fit, and rerun
   affected placement, routing and board checks after an approved revision.
2. Correct and externally check the sheet solver before using it for board
   resistance/current sharing. Supply task 03 heat sources for total temperature.
3. Establish board loop/return geometry and exact-part parasitics, then extend
   the switching deck for complementary-drive/dead-time behavior.
4. Resolve the protection solver stalls and low-overdrive timing model, and
   obtain capacitor frequency/temperature limits before completing the sweeps.
5. Revisit EMI with validated switching edges, heatsink-pad capacitance and
   physical two-node common-mode return paths.

No fabrication release, full electrical acceptance, or physical test result
follows from this round. Smoke PASS describes the simulator setup only.

## Coordinator verification

The coordinator independently replayed task 01's loop extraction, all four
task 04 analytic solver probes, and task 07's native-board pitch check. Outputs
matched (excluding checkout paths). One CT and one shunt case reproduced all
reported measures exactly; one retained tank case reproduced both reported
peaks exactly. The [verification receipt](coordinator-checks.json) preserves
those replayed values. These spot checks do not expand the reported sweep
coverage or remove the model limitations.

All five result sets are committed on `codex/ps-sim-validation`. The native-13
board hash is unchanged; no source, routing, placement, shared simulation-kit
or vendor-model files were committed by this round.

## Kit corrections after this round (2026-09-27, Claude)

The shared kit defects that the task-04 audit and the coordinator reported are
fixed in `validation-plan/sim-kit/`. Results already recorded above were
produced with the uncorrected kit, and they stand as recorded.

- **`04-current/sheet_solver.py`:**
  - The via barrel length is split across hops by real layer spacing.
  - Resistance is loss-equivalent, ΣV·I / I², with source voltages reported.
  - Off-copper injection points are refused.
  - A connectivity preflight excludes unused islands and refuses a source with
    no sink.
  - Seven self-tests pass. They include the audit's four-layer via
    (0.5811 mΩ) and unequal-source (2.8996 mΩ) cases, now matching the
    analytic values.
- **`common/run_ngspice.py`:**
  - It reports `returncode` and `raw_returncode`.
  - A nonzero exit or a failed waveform run counts as aborted.
  - Full logs are saved as `run.log` and `raw_run.log`.

Still open from the coordinator notes: the switching deck is not a
complementary-drive ZVS model. Extending it is task-01 work.
