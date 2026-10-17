# Round 3 execution record

Started 2026-09-27 from `44417ae1489fd00e2d652fd3b2c1582b76d17630` (PR #1615).
Dispatch authority: `validation-plan/ROUND-3.md` and the operator's request for
parallel Sol agents. All workers use `gpt-6-sol`, high reasoning, isolated
`codex/ps-r3-aN` branches. The coordinator reviews and integrates results in
`codex/ps-r3-integration`; the main checkout is not a results destination.

Board: `native-15/section.kicad_pcb`, SHA-256
`a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
Board, frozen parts, placement and source are unchanged by this work.

| Unit | Owned output | Dispatch state |
| --- | --- | --- |
| A1 | [ZVS and edges](../01-switching-parasitics/round3/a1-zvs/README.md) | Integrated 540-case grid; required independence check FAIL |
| A2 | [inductance](../01-switching-parasitics/round3/a2-inductance/README.md) | Integrated heuristic scenarios; field solve unavailable |
| A3 | [protection](../02-protection-timing/round3/README.md) | Integrated; static shunt criterion FAIL; guaranteed shutdown blocked |
| A4 | [copper](../04-board-current-thermal/round3/a4-copper/README.md) | Integrated conditional electrical cases; transferred to B3 |
| A5 | [tank](../05-resonant-tank-envelope/round3/README.md) | Integrated 135-case grid/R5/trip; capacitor acceptance and ZVS blocked |
| A6 | [loss budget](../03-loss-thermal-budget/round3/README.md) | Integrated conditional losses, two pads and partial heat map |
| A7 | [EMI](../07-conducted-emi/round3/README.md) | Integrated topology/fit/scenario evidence; B5/C1 margins blocked |
| B1 | [switching stress](../01-switching-parasitics/round3/b1-board-grid/README.md) | Stopped at first model stress failure; physical bounds unavailable |
| B2 | [gate-off handoff](../02-protection-timing/round3/b2-gate-off/README.md) | Actual gate-off current and dynamic F3 blocked |
| B3 | [thermal](../04-board-current-thermal/round3/b3-thermal/README.md) | Integrated conditional studies; peak mesh convergence and operating inputs incomplete |
| B4 | [ZVS status](../05-resonant-tank-envelope/round3/b4-status.md) | Blocked on qualified thresholds and low-bus coverage |
| B5/C1 | [EMI](../07-conducted-emi/round3/README.md) | Assumed spectra saved; total emissions/margins blocked |

This is an execution receipt, not engineering acceptance. Workers preserve
source and raw-output hashes, distinguish assumptions from guarantees, and
hand back reproducible commands. The coordinator checks producer outputs
before authorizing dependent B/C conclusions. Prior uncommitted intake in
`worktrees/ps-validation-round3` is a read-only seed, not silently accepted
evidence for this new revision.

## Dependency checks

- B1: A2 loop/return definitions and extraction or qualified estimate.
- B2: A3 timing assumptions, B1 gate turn-off, A5 trip topology.
- B3: A4 converged electrical heat and A6 board heat allocation.
- B4: A5 switching-event currents and A1 sensitivity-qualified ZVS thresholds;
  if A1 fails independence, use B1 instead.
- B5/C1: validated A7 topology, A6 pad capacitance and A1 sensitivity-qualified
  edges; otherwise wait for B1 edges. Peak spectra are not quasi-peak results.

No fabrication release or physical qualification follows from dispatch or
simulation completion. Owner decisions remain in ROUND-3 §4.

## Verified handbacks

`check_handoffs.py` verifies 84 A3 input/artifact hashes and independently
reconstructs electrical-to-thermal energy transfer for 37 A4 saved solves
(35 cases plus two convergence meshes). The two ignored Infineon vendor
inputs were restored and hash-checked locally in the kit; they are not
distributed in the result packet. See [handoff-checks.json](handoff-checks.json).
This is an evidence-integrity check, not a design-acceptance test.

The A3 report corrects a premise in ROUND-3 A3.2: the datasheet's 20 mV
step-response maximum does not establish the proposed arbitrary-ramp bound.
Those estimates remain conditional. The shunt's +85°C static result fails
the 44 A nuisance criterion even before dynamic shutdown is considered.

The integration checkout also replayed the A1 coverage/source audit and kit
smoke test (`SMOKE PASS`). `audit_packet.py` records every delivered file's
hash and checks JSON, local report links, package size and edit scope.
Packet-local ignore exceptions preserve raw runs and logs for a future
commit while excluding vendor model copies and Python caches.
All nine Sol workers have handed back and stopped. The main checkout and
the saved board, netlist and parts remain unchanged.

Committed 2026-09-28 to PR #1615 with the operator's co-author line.
The owner chose storage option 1: reports, scripts, sources and summaries in
git; raw evidence packaged for the release asset described in
[raw-evidence/README.md](raw-evidence/README.md) (not yet published). The owner's decisions on the
findings are in [decision-review/README.md](decision-review/README.md). The
TDK model-license confirmation remains unanswered; A7 uses its public-curve
fallback.
