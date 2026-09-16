# Shunt assembly review closure — 2026-09-16

The original `review.json` is retained as a historical review receipt rather
than rewritten to imply the reviewer observed later validation.

- The selected mesh/solver-binding finding was rejected by the Luna finding
  validator after inspection of the pre-solve hashes and cross-mesh identity
  checks. Those checks remain in the implementation and regression suite.
- The pre-existing local replay receipt omission is now fixed. Both local
  and assembly paths share exact command-contract validation. Local v3 hashes
  all 45 original invocation receipts. The original local v2 report is saved
  alongside the revalidated report; no new local solve is claimed. A mutation
  changing solver arguments and recomputing hashes is still rejected.
- The missing end-to-end test is implemented and passed:
  `retained_assembly_replay_passes_numerics_without_qualifying_hardware`.
  It uses the retained compressed run-15 profile and source-bound PFC model,
  and asserts assembly numerical PASS plus qualification INDETERMINATE.
- Corrected run 15 completed all 19 solves. The parsed stackup has a 1.44 mm
  core, two 70 µm copper layers and two omitted adiabatic 10 µm mask skins.
  Historical runs 01–14 remain rejected/superseded, not acceptance evidence.
- The final workspace suite completed with 491 passed, zero failed, one
  ignored. Clippy completed with pre-existing warnings. Regeneration and
  import-boundary gates passed. Source/document whitespace checks passed;
  unedited raw solver trailing whitespace remains byte-for-byte preserved.
- The common seven-unit run completed with seven INDETERMINATE, zero FAIL,
  and unchanged validator sources during execution. Native ERC/DRC,
  unconnected and schematic-parity checks passed for every unit, with
  KiCad CLI 10.0.4 recorded by the actual invocations. Both power-entry shunt
  numerical checks passed; assembly qualification stayed INDETERMINATE.

Evidence: `zapote/power-entry/shunt-assembly/run-15/report.json`, its adjacent
archive manifest and execution logs, and
`zapote/validation/runs/shunt-assembly-20260916-final-01/`.

The board SHA-256 remains
`b1e06afbf0e9a8b41a3bbbbd046abeb5495e9b42f3fc07e1b312095bc7e97583`.
No PCB edit, fabrication or powered test occurred in this work.

Remaining limits are unchanged: sampled arbitrary concave copper containment,
unknown resistor-internal heat path, prescribed rather than demonstrated board
cooling, omitted neighboring/copper losses, and unmodeled transients. The
same-provider Luna review is not independent cross-model verification. The
earlier automatic approval rejection of external private-code review was not
bypassed. Physical qualification remains open, but the numerical implementation
and its harness closeout are complete.
