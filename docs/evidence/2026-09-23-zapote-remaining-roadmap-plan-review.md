# Review of the remaining Zapote roadmap plan

Date: 2026-09-23. The [plan](../plans/2026-09-23-zapote-remaining-roadmap-parallel-plan.md) was reviewed independently for feasibility and adverse false-readiness cases before implementation.

| Finding | Correction applied |
| --- | --- |
| A hashed, self-authored discharge `*_verified` record could still fabricate qualification. | R2 now requires evidence class, exact part/article/case and parameter match, raw capture or manufacturer-source identity, measurement uncertainty and independent adoption/review identity. Missing independently reviewed physical evidence keeps the hardware verdict indeterminate. |
| The gate-drive `HV_RETURN` and Rev38 `HOT0` join was absent from integration edges. | R6 now exposes it as an indeterminate low-side Kelvin/isolated-bias edge until join location and return current are reviewed; it cannot merge with `CTRL_GND`. |
| Typed integration ports could claim compatibility while native pins/nets disagree. | R6 now requires source/netlist/native pin-pad-net identity where it exists and traces cooling/sensing/interlock faults to both PFC inhibition and inverter PERMIT, including open-wire and unpowered defaults. |
| A programming connector can reset ESP control while power-stage permission persists. | R5 now requires isolated/discharged service access or measured reset-to-both-stage-stop and no automatic rearm before an electrically acceptable service candidate. |
| Hashing only present release files misses omitted obligations; hashing a handwritten PASS proves no tool ran. | R7 now has a closed mandatory-role registry and derives release results from replay or machine receipts bound to command, exit code, board input, tool version and raw output. |
| “Prior evidence” alone was too vague before HV injection. | R7 now requires demonstrated default-off and separately verified VD/VB discharge/stop paths before the energy-limited HV stage. |

The plan still cannot complete native integration, release, or assembled verification without accepted units, a frozen board, article and qualified measurements. The current round is readiness construction and conditional interface work, with explicit blocked outcomes.
