# Native-13 simulation dispatch — 2026-09-27

Source revision: `36ba41f24`. Board SHA-256:
`8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.

The official Infineon ZIP/library match both runbook hashes. The coordinator
ran all 16 smoke checks on ngspice 45.2 successfully. Every worker reruns this
gate in its own worktree before task work. These reference runs use placeholder
inputs and establish the simulator setup only, not design acceptance.

| Task | Sol assignment | Dependencies |
| --- | --- | --- |
| 01 | Board loop/gate inductance; supported switching sweeps | Datasheet ESL; deck must support the claimed switching condition |
| 02 | CT/shunt analog timing and chain reconciliation | 01 for final turn-off/stress closure |
| 04 | Multilayer current/Joule-only heating | 03 heat sources absent; total thermal result remains partial |
| 05 | Tank envelope and component stress | 01 for final ZVS boundary |
| 07 | EMI source intake and supported sensitivity | 01 edges and 03 pad choice; queued after an agent slot opens |

All workers use GPT-6 Sol at xhigh effort, each on a separate task branch and
worktree based on the same source revision. Outputs stay under their assigned
`validation-results/NN-*/` folder. The coordinator integrates only those files.
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

These are review observations to verify, not board findings. Each task report
will record the executed evidence and its remaining limits.
