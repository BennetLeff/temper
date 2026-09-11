# Buck closure wave — 2026-09-10

Three Luna agents investigated components, exact-model access and layout
qualification, then followed up the findings. The host integrated the changes
in the existing feature worktree, preserving unrelated edits.

## Implemented

- Adopted the previously proposed design targets in
  `harness-lab/engineering/requirements.json`, revision
  `temper-buck-requirements-2026-09-10-closure`. The capacitor effective-value
  and inductor hot-current requirements remain unresolved. Target adoption
  does not prove measured performance.
- Added explicit load profiles and U3 junction/L2 hotspot requirement fields.
  Malformed explicit lists cannot fall back to legacy scalar values.
- Bound simulation profiles to the exact retained requirements bytes and hash.
  Simulation requires both profiles, checks declared endpoints and measured
  current extrema, and limits endpoint tolerance to the adopted 2%. Each load
  scenario has a separate contained output directory.
- Retained [component findings](components.md), [model feasibility](model.md),
  and [layout evidence](layout.md). The Samsung C9 candidate's soft termination
  does not itself require a footprint redesign; electrical margin remains open.

These changes check profile identity and endpoints. They do not yet implement
the full three-pulse protocol, both edge directions, slew, per-edge recovery,
all startup/input corners, or thermal measurement. The exact-device model
registry remains empty, so software controls cannot admit real scored trials.

## Remaining gates

1. C9 electrical margin and remaining component evidence, including L2 at
   105°C. Samsung `CL32B106KBJZW6E` remains the preferred candidate; no source
   BOM replacement has been made.
2. Exact LMR51430XDDCR model retrieval, license, simulator replay and independent
   qualification. The TI terms question remains pending; terms were not accepted.
3. Native KiCad missing-route negative control: the real KiCad 10.0.4 binary
   crashes reproducibly. The Rust judge rejects that mutant, but that does not
   substitute for a completed native result. A corrected reference and all
   four variants still need formal qualification.
4. After those gates and the remaining waveform checks pass, run preflight,
   four development slots, freeze inheritance, then six reserved slots.

## Validation

Rust: 31 tests passed; Clippy and Rust formatting passed. Changed Python files
pass lint and formatting; Python compilation passed. The full `make check`
stopped at existing formatting differences in `run_buck_trials.py`, `telemetry.py`
and `test_telemetry.py`; these unrelated edits were preserved. All 131 Python
tests passed outside the sandbox in 126.317 seconds; the sandbox had blocked
loopback sockets and child workers. The final changed simulation/requirements
tests also passed separately (8 tests). Logs are retained as `checks.log`,
`python-checks-unsandboxed.log` and `focused-python.log`.

The simplification pass applied two quality improvements (a thermal validator
helper and explicit numeric matching) and two efficiency improvements (one
requirements-byte snapshot and an allocation-free uniqueness scan). Reuse
changes were not needed: the hashing helper predates this scope and the two
profile validators have distinct reporting contracts. Further helper extraction
for the small profile predicate was skipped. No safety check was removed.

Code review completed with no remaining findings after the thermal-condition
fix; the [review receipt](../../../../docs/reviews/ce-code-review/2026-09-10-buck-final.json)
records the review scope and limits. Review did not qualify electrical or
physical performance. No additional operational monitoring is required for
these local harness changes; no deployed system was changed.

The corrected candidate passes its native collection and Rust layout check.
The twelve frozen positive checks used the older witnesses, three repetitions
per variant; they do not qualify the corrected reference. Native crash logs and
candidate judge evidence are retained under `layout-evidence/`.

The production PCB hash remains
`00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9`;
the empty approved-evidence registry hash remains
`99d23e692550345dc0e036083e4f0ee29ed8837cb39392eff58b01c84b5550fd`.
No hardware validation, scored trial, purchase, vendor message, commit or remote
publication was performed in this wave.
