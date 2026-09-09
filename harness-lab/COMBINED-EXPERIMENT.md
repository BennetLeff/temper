# Experiment 00PR: placement and routing together

Accepted September 9, 2026: “that all looks great, continue,” following the proposed combined U3/C9 milestone. Use the same Muse Spark 1.3 Contributor Free model through OpenCode Zen under the previously accepted Contributor terms.

## Frozen scope

Three starts use C9 poses (22,15,0), (22,5,180), (16,16,270), the earlier placement experiment's starts. U3 stays at (10,10,0). Keep the protected native obstacle and the same two required connections, C9.1–U3.3 (+15V) and C9.2–U3.1 (ground). U3.5 remains disconnected. Initial copper is empty.

Five operations: inspect, place C9, replace one net's route, remove one net's route, check. A placement moves only C9 and its native footprint children. Existing copper remains byte-for-byte equivalent in its native track census, including raw net assignments. It neither follows the footprint nor disappears. The agent must inspect feedback and fix stale copper if it moves after routing.

All operations share the existing five-minute trial deadline. Placement, routing and removal share one **ten-edit** budget. Tracks remain straight 0.25 mm F.Cu segments, at most 22; no vias or zones. C9 orientation is 0/90/180/270. The existing placement checks (outline, courtyard, clearance and mapped pad distances at most 5 mm) and routing checks both apply. The native keepout, U3, pad geometry/nets, outline and sidecars remain protected.

The adapter normalizes only C9 pose and removes inventoried tracks when computing protected-state identity. It uses native pcbnew transforms and raw serialization; no local geometry kernel or hidden routing search is admitted. The existing Rust judge already combines placement and routing constraints; its logic remains unchanged.

## Qualification before model execution

Verify all three starts are invalid but untampered, and a scripted place-plus-two-routes sequence succeeds from each. Verify placement alone cannot pass. Move C9 after routing: copper census must remain identical, physical connectivity must fail, and returning C9 must restore the valid state. Exercise wrong-net copper through placement to prove serialization does not silently fix it.

Verify U3 movement, pad-net changes, pad-shape changes, keepout removal and changed rules are rejected. Verify mixed operations consume a single budget, preflight denies edits, and invalid inputs leave state unchanged. Run the previous placement, routing, obstacle and repair qualifications plus Python/Rust tests before freezing the apparatus.

## Scored batch

One inspect-only preflight, then three fresh sequential trials, one per start. The agent receives the combined task and normal native feedback, without witness poses or route coordinates. No trial reruns or mid-batch changes.

**Pass:** all three runs begin by inspecting the failing start, perform placement and copper routing, finish with check returning pass, satisfy the full wire/action/snapshot audit, and pass independent host verification within five minutes and ten total edits. Missing/inconsistent evidence or incomplete streams cannot pass.

Record every requested pose/polyline, observed state, introduced/resolved findings, final pose/tracks, time and reported cost. This tests joint operation on three known small-board starts, not generalization, global routing optimality, electrical suitability or a learned harness-refinement loop.

## Results

All three fresh combined trials passed in 133.50, 73.67 and 155.20 seconds, with 3, 4 and 3 total edits. See [the results, different placements and retained evidence](COMBINED-RESULTS.md).
