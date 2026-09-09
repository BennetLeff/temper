# Experiment 00R-O: one obstacle, two connections

Keep the proven U3/C9 placement and required connections. Add one protected
native KiCad track keepout on F.Cu, rectangle (7.55, 10.5)–(7.95, 12.0) mm.
It blocks the direct C9.1–U3.3 trace. The ground pair remains unobstructed.
Use a rule area so the experiment retains two footprints and the existing
native DRC acceptance path. A third component or a new geometric collision
checker would add unrelated scope.

The four tools, 0.25 mm track width, F.Cu-only routing, fixed footprints,
protected rules, no unintended pad connections, one out-of-scope U3.5 open
connection, five-minute budget and ten-edit limit remain. Inspect reports
native keepout polygons. The agent receives no example route or waypoint hint.
No new routing algorithm or refinement policy is introduced.

A pass requires both physical pad connections and zero applicable native DRC
findings, including no track copper entering the keepout. All three fresh
repetitions must pass and receive separate host verification. Each repetition
starts from the same blank board; this tests one obstacle, not generalization
to unseen boards. Preserve every scored outcome without retries or hints.

Before scoring, qualify: blank board fails connectivity; the old direct
route fails specifically on the keepout; a manually constructed detour passes
three native checks; a centerline outside with track width intruding fails;
removing or disabling the keepout fails protected-state acceptance; removing
and replacing a route refreshes native findings. Validate native keepout
context and exact four-tool admission. Re-run the prior routing qualification.

Run an inspection-only preflight and three Muse Spark Contributor Free trials
through the selected OpenCode Zen profile. The user explicitly authorized the
obstacle payload with “do it,” resolving the earlier approval block. Retain
the same destination and Contributor terms.
Freeze source, fixture, contract and evaluator hashes before preflight.

The YC thin-tool principle and Chase's context-at-decision-time idea are
tested here by exposing native obstacle geometry and DRC deltas. These traces
can inform a later Continual Harness refinement loop; this experiment does
not claim improvement from such a loop.
