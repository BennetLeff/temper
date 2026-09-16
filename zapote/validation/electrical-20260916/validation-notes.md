# Electrical validation run notes

Baseline: 7f506ba86; canonical worktree codex/buck-harness-experiment-plan.

The first targeted new test run rejected two assertions that expected the new
identity-check wording. Existing saved-board UUID validation rejected the
mutations earlier. Removed the redundant identity implementation and asserted
that authoritative failure instead. Also corrected the mutation from invented
`id` to the actual native `uuid` field.

The first workspace test run failed only power_entry_routed's old assertion
that every individual finding was PASS. New explicit external obligations
correctly produce four INDETERMINATE findings. The replacement checks their
exact rule IDs and still requires every other finding to PASS.

Strict clippy stopped at 14 pre-existing warnings: gate_drive (6),
power_stage_models (2), domain_clearance (5), stackup test ordering (1).
Normal workspace/all-targets/all-features clippy completed successfully with
those warnings and no new ones.

Simplify reviews: removed duplicate native identity checking; derived shunt
resistance from the validated source value instead of three literals; removed
unused future loop-scope enum; named average heating mean dissipation.
Deferred pre-existing parser/graph/geometry caching suggestions because this
change does not establish a performance problem and those refactors affect
independent evidence boundaries. Extra source parsing in the new boundary
check is small and preserves the complete existing source validation.

Final reviewed run: 452 tests passed, one live Gmsh test ignored. Final full
clippy traversal also reports one unchanged gate-drive integration-test lint
(filter_map_bool_then): 15 distinct existing warnings total. Both final native
runs preserve the board distinction: GBU has four current-screen failures;
GBJ has no FAIL findings and remains INDETERMINATE. Their modeled-net via
populations differ (35 vs 36), as expected from the saved alternative geometry;
a first manual summary check incorrectly reused the baseline count for GBJ,
then was corrected against the actual UUID population before publication.
