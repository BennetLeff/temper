<!-- provenance: commit=caec25d61 (main, HEAD at start of this task), worktree agent-aa0fd3a4b1b6f7aa2.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged before/during/after this task (read-only; never opened for writing).
STUB — being filled in during this task. -->

# netclass_constraints.py manifest-backed classification + IECCreepageGate/DeltaMapper stale-6.0mm fix

Status: IN PROGRESS. Stub committed first per operating rules; will be filled in as work
lands, one concern per commit.

Scope (per assignment):
1. `netclass_constraints.py` classifies HV nets by name-keyword heuristic and
   misclassifies K1's HV relay-contact nets (`power_in.ntc-no`, `w1_2`) as
   `"signal"` — same bucket as J1's SELV RTD nets — so zero cross-class
   separation constraint is emitted for that pair. Fix: classify from
   `elec/domain_manifest.yaml` (and/or `pcb/temper.kicad_pro` netclass
   assignments) instead of net-name keywords.
2. `IECCreepageGate` (`gates.py`) is dead (never registered in either of
   `loop.py`'s gate lists) and stale (hardcoded 6.0mm vs the 12.6mm PD3 SSOT),
   and that stale 6.0mm leaks into `DeltaMapper`'s live feedback path
   (`delta_mapper.py`'s `CREEPAGE` branch). Decide revive-with-SSOT-value or
   delete; either way stop the stale 6.0mm reaching `DeltaMapper`.

Out of scope (sibling's work): `domain_clearance.py`, `solve_placement()`'s
main wiring.

Findings and diffs will be appended below as they land.
