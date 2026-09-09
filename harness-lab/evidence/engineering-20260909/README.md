# Stages 1–4 implementation evidence

The executable validation harness is implemented; the buck reference is **not
engineering-qualified**. Luna subagents authored the stages and performed the
code review; the host integrated the changes, fixed review findings, and ran the
final checks. This delivery covers U6–U9 and the shared stage report. U2–U5
construction/refinement experiments and U10 bench-record implementation are not
part of the user's final stages-1–4 request.

## Verification

`make -C harness-lab build check` passed: **16 Rust tests, 48 Python tests**, Clippy
with warnings denied, Rust formatting, Ruff lint/format, and Python compilation.
See [checks.log](checks.log). Controls cover complete synthetic receipt chains,
missing/stale/tampered evidence, circuit identity mutations, unapproved component
and simulation receipts, path escapes, actual ngspice RC output against its
analytic response, and native KiCad layout collection. Synthetic controls cannot
qualify the buck.

Four fresh full evaluations used actual Atopile builds and KiCad measurements.
All retained artifact hashes and source inventories were checked against the
saved files after completion; no source drift was detected. [index.json](index.json)
contains their digests, measurements, and local raw-run locations. Per-variant
reports, admission inputs, source inventories, and toolchain records are retained
here; complete raw exports, board snapshots, and native reports remain in the
listed ignored run directories. These compact snapshots do not replace those raw
artifacts for receipt replay.

| Variant | Requirements | Circuit identity | Component qualification | Simulation | Layout | Hardware |
|---|---|---|---|---|---|---|
| buck-dev-a | blocked | pass | blocked | blocked | fail | not run |
| buck-dev-b | blocked | pass | blocked | blocked | fail | not run |
| buck-res-a | blocked | pass | blocked | blocked | fail | not run |
| buck-res-b | blocked | pass | blocked | blocked | fail | not run |

Twenty mandatory limits remain unresolved. Capacitor DC-bias and inductor
saturation evidence is absent, and no approved exact-device switching model is
available. The old average model is inadmissible. The RC simulation is an
instrument control, not buck-performance evidence.

Each reference has a **43.6673 mm** connected ground-return centerline path
against the **20 mm experiment proxy**, an 11.3875 mm input path, and a 0.6 mm
power-trace bottleneck. Visible reference/value labels are absent. These are
geometry/presentation findings, not measurements of loop area, EMI, temperature,
ampacity, or powered behavior. No production PCB, firmware, or frozen fixture
was changed; no model construction trial or bench test was run.

## Review and limits

The Luna review's three findings were resolved: exact trusted receipt pins now
prevent self-attested component/model qualification, model/deck/evidence paths
are contained before simulation, and the copper graph splits crossings and
T-junctions. See [review-resolution.json](review-resolution.json). Its retained
74 mm narrative predates the final junction-aware measurement; **43.6673 mm is
the final measured value**, and it still fails the same frozen 20 mm limit.
The review reported no remaining findings. No cross-model review was performed.

The host also completed the simplification skill's reuse, quality, and efficiency
passes inline under the repository's sequential-task mapping, removing duplicated
fallbacks and fabricated measurement paths while retaining admission checks.
This is a host review, not three additional independent reviewers.

A fully qualified reference still requires approved product limits, reviewed
component/model evidence, and a layout that passes the expanded contract.
Hardware remains unverified regardless of stages 1–4.
