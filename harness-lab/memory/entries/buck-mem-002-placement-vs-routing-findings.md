# buck-mem-002 — Track placement findings separately from incomplete routing

- **Claim / procedure:** When reading validator feedback, distinguish
  placement-constraint failures from incomplete-copper states: a `place`
  response can report `fail` while placement constraints are satisfied
  simply because copper is not complete yet. Resolve the specific
  placement findings first (e.g. retry placement against the remaining
  pad-distance findings), and only then route.
- **Applicability:**
  portable general feedback-reading procedure, board-independent.
  Required capabilities: validator-findings inspection, placement
  reading, routing reading. Trial 2's C9 poses ([14,10] → [13.8,10],
  90°) and edit counts are buck-fixture context, not MCU values (R3).
- **Evidence:**
  `harness-lab/COMBINED-RESULTS.md`
  (`sha256:199107c7…071b04`) — Trial 2 narrative: first placement failed
  the distance requirement, second placement resolved those specific
  findings; retained trace distinguishes satisfied-placement-yet-failing
  responses from genuine placement failures. Limits: two connections on
  a two-footprint fixture, three known starting poses; no optimality or
  fabrication-readiness claim.
- **Provenance class:** expert-curated (manual curation 2026-09-10; not
  automatic learning — the full-buck pilot has not run).
- **Validation state:** source-reviewed. No live full-buck inheritance
  result claimed.
