# Independent validation of #1313's oracle-hash-drift evidence + SafetySpec defaults — STUB

Status: IN PROGRESS. This is a survival stub committed as the first action in
this session, per the handoff's §15 operational note (a worktree with no
commits is destroyed on stop). Will be filled in / superseded by dedicated
commits as work proceeds.

Task, in brief (see orchestrator brief for full text):

1. Independently validate `docs/evidence/2026-08-17-oracle-hash-drift-evidence-and-repin-values.md`'s
   two findings (`_via_validation_run_py_oracle.py` dropped re-pin,
   `_graph_py_oracle.py` undocumented drift) before applying anything.
2. Apply the two re-pins separately, each with its own evidence, iff my own
   validation holds.
3. Execute `docs/evidence/2026-08-17-fact-dedup-inventory-and-gate.md`'s plan
   for `SafetySpec`'s stale mains_voltage_v/pollution_degree defaults
   (230.0/PD2 -> 120.0/PD3), once the oracle entanglement is resolved.
4. Fix `test_safety_spec_defaults`'s misleading justification/assertion.
5. Investigate (not necessarily fix) `MIN_BARRIER_WIDTH_MM`'s PD2-pinned
   status in `pcb/temper.kicad_dru`'s header.

Board sha256 at session start: `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
(matches task brief; `pcb/temper.kicad_pcb` NOT to be modified — will be
reverified at the end of this session).

Main at session start: `775a7a40e`.
