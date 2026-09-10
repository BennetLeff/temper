# buck-mem-001 — Inspect exact findings, edit the affected connection, then independently check

- **Claim / procedure:** Before editing, inspect the validator's exact
  findings (finding IDs, affected nets/pads). Edit the affected
  connection only, leaving healthy nets intact. Afterwards run an
  independent board check and confirm the intended finding IDs resolved
  (and no new ones appeared). Makes no claim of optimal placement or
  routing.
- **Applicability:**
  portable general construction guidance, board-independent.
  Required capabilities: validator-findings inspection,
  targeted connection edit, independent board check.
  Buck trial timings (85.11 s / 61.41 s / 25.96 s), the 0.075 mm vs
  0.2 mm clearance numbers, and the +15V/ground net names are context
  only — not MCU constraints (R3).
- **Evidence:**
  `harness-lab/REPAIR-RESULTS.md`
  (`sha256:2711a964…1d7aa42`) — three repair trials, each one copper
  edit, each satisfying the repair requirement to inspect the failing
  start first, request a route edit, and observe resolution of the
  intended defect IDs; retained action record with vertices, snapshots,
  and independent checks. Limits section noted: three supplied bad
  states on one tiny board; no held-out generalization or
  electrical/manufacturing suitability claim.
- **Provenance class:** expert-curated (manual curation 2026-09-10; not
  automatic learning — the full-buck pilot has not run).
- **Validation state:** source-reviewed. No live full-buck inheritance
  result claimed.
