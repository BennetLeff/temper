# What the 10 obstacle controls and 23 routing regression checks mean

These are deterministic, scripted tests of the **measurement and tool harness**, not model trials. We construct a known board or deliberately corrupt evidence, then assert the expected result. A control succeeds when the evaluator accepts a valid candidate, rejects an invalid one, or reports `indeterminate` for evidence it cannot trust. Therefore an expected board `fail` is a successful test.

The evaluator combines native KiCad DRC, pcbnew physical connectivity, and a Rust judge enforcing this experiment's frozen task contract. The contract requires C9.1–U3.3 (+15V) and C9.2–U3.1 (ground), with fixed footprints and 0.25 mm F.Cu tracks. U3.5 must remain disconnected, even though it shares +15V. This is a deliberately restricted fixture, not a production-board sign-off.

## The 10 obstacle controls

Source: [qualify_obstacle.py](qualify_obstacle.py). These add one native track keepout to the two-route fixture.

| # | Recorded case | What we construct or exercise | Expected result |
|---|---|---|---|
| 1 | `blank` | No copper routes. | Reject: required connections are missing. |
| 2 | `native-keepout-context` | Read the keepout through pcbnew. | Exact rectangle, F.Cu layer and track prohibition appear in inspection context. |
| 3 | `direct-route-blocked` | Draw the direct +15V route through the keepout. | Reject with KiCad `items_not_allowed`. |
| 4 | `detour-1` | Draw a known valid detour and ground route. | Accept. |
| 5 | `detour-2` | Repeat that same detour on a fresh fixture. | Accept. |
| 6 | `detour-3` | Repeat it again on a fresh fixture. | Accept. |
| 7 | `centerline-clear-copper-intrudes` | Put the track centerline outside the keepout but let its physical width overlap it. | Reject with native keepout DRC. |
| 8 | `deleted-keepout` | Delete the keepout, then draw the direct route. | Reject protected-state tampering, even though keepout DRC disappears. |
| 9 | `disabled-keepout` | Turn off its track prohibition, then draw the direct route. | Reject protected-state tampering, even though keepout DRC disappears. |
| 10 | `native-feedback-repair-remove-replace` | Through real tools: create a blocked route, replace it with a detour, add ground, remove +15V, restore it, check. | Feedback names introduced/resolved violations; removal fails; restoration passes; five edits recorded. |

The three detours are repeatability checks of **one geometry**, not three different routing challenges. The agent is not given this scripted solution.

## The 23 routing regression checks

Source: [qualify_routing.py](qualify_routing.py). These rerun the earlier two-route tests after changes, to catch regressions. Cases 1–18 evaluate native boards; 19–21 deliberately corrupt measurement input to the judge; 22–23 exercise tools, logs and limits.

| # | Recorded case | What we construct or exercise | Expected result |
|---|---|---|---|
| 1 | `multi-segment-witness-1` | Known valid multi-segment routes for both nets. | Accept. |
| 2 | `multi-segment-witness-2` | Same routes on a fresh fixture. | Accept. |
| 3 | `multi-segment-witness-3` | Same routes on another fresh fixture. | Accept. |
| 4 | `blank-same-net-labels` | Correct net labels, no copper. | Reject: labels alone do not connect pads. |
| 5 | `missing-ground` | Remove the ground route. | Reject missing connectivity. |
| 6 | `broken-native-cluster` | Open a physical gap between ground segments, retaining their net labels. | Reject missing connectivity. |
| 7 | `wrong-net` | Assign a track to the unapproved `sw` net. | Reject unsupported copper. |
| 8 | `wrong-admitted-net-not-auto-repaired` | Put ground-labelled copper along the +15V route. | Reject extraneous copper; native loading/connectivity must not silently hide the original assignment. |
| 9 | `short-across-pads` | Run +15V copper through the ground pad. | Reject with native short-circuit DRC. |
| 10 | `clearance` | Route copper too close to other copper. | Reject with native clearance DRC. |
| 11 | `wrong-layer` | Move a track onto B.Cu. | Reject: this task allows only F.Cu. |
| 12 | `wrong-width` | Change a track from 0.25 mm to 0.30 mm. | Reject: width is fixed for this experiment. |
| 13 | `via` | Add a via. | Reject: vias are outside the admitted interface. |
| 14 | `outside-copper` | Route beyond the allowed board outline. | Reject copper outside the outline. |
| 15 | `unwanted-enable-pad` | Extend +15V to U3.5. | Reject an unintended connection, despite the matching net name. |
| 16 | `moved-fixed-capacitor` | Move C9 while routing. | Reject protected-state tampering. |
| 17 | `changed-pad-net` | Change U3.5's net assignment. | Reject protected-state tampering. |
| 18 | `changed-rules` | Replace the frozen DRC rules file. | Reject protected-context tampering. |
| 19 | `missing-connectivity` | Remove the entire routing measurement. | Indeterminate: insufficient evidence to judge. |
| 20 | `partial-connectivity` | Remove one pad's connectivity record. | Indeterminate: incomplete census. |
| 21 | `asymmetric-connectivity` | Make physical cluster membership inconsistent. | Indeterminate: inconsistent evidence. |
| 22 | `native-remove-replace-transcript-audit` | Inspect, route both nets, remove ground, restore it, check; audit the tool transcript against action logs and board snapshots. | Correct state transitions, four edits, and a passing action audit. |
| 23 | `routing-budgets-invalid-inputs-preflight` | Attempt an unsupported operation/net, boolean coordinate, too-short polyline, edit after the ten-edit limit, check after deadline, and a preflight edit. | Reject each; malformed edits leave the board unchanged; preflight performs zero edits. |

These are **23 named cases**, not an exhaustive count of assertions. Some bundle several checks; three repeat the same valid board. They establish confidence in the particular instrument and task boundary. They do not measure the model's routing skill, generalization, production electrical suitability, or stream reliability. Model trials and transport fault-injection tests supply separate evidence.
