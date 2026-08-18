# `lib_footprint_issues` 13 → 168 attribution — STUB, investigation in progress

**Status: STUB.** This document will be filled in as the investigation
proceeds. Committed first per this task's operating rule ("commit a stub
evidence doc as your first action").

**Task**: attribute the `lib_footprint_issues` regression (stored ceiling 13,
measured 168 in
`docs/evidence/2026-08-17-drc-ceiling-rebaseline-measurement-and-declined-approval.md`)
found during the 2026-08-17 DRC ceiling re-baseline attempt. Not in any
breach list, unexplained, the single largest regression against the stored
ceiling.

**Leads already on record** (from
`docs/evidence/2026-08-17-drc-ceiling-methodology-gaps-silk-overlap-and-sampling.md`
§2.2 side finding): an ad-hoc-pinned sweep using
`measure_uncapped_drc.py`'s `_single_thread_env` (which does not seed the
scratch `KICAD_CONFIG_HOME` with copies of the real library tables) read
`lib_footprint_issues=165`, wildly different from the real-protocol
(`_drc_api.py`'s `_single_threaded_kicad_env`) reading of `13` at N=125. That
doc flags this as a plausible explanation for the `13 → 168` figure but
explicitly did not verify it against the same protocol — that verification
is this task.

Work in progress; will update in place.
