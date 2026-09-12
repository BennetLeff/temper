# Coordinator integration checkpoint

P0 now executes the maintained unit suites and adopted P1–P3 implementations
through one command. **The full P1–P3 implementation plan remains incomplete.**
A subagent final message is a handback for review, not acceptance of the batch.

## Latest committed checkpoint

The subsequent [independent PFC instrument validation](p1-current/oracle-2026-09-12/README.md)
adds closed-form, live-SPICE and exhaustive-graph references and repairs three
instrument defects. The fresh seven-board run retains the same five PFC
screening failures. Its receipt records the exact source identity; this does
not close thermal or area-current qualification gaps.

The [PFC current-screen implementation](p1-current/README.md) now runs through
the common runner: source-bound switching waveforms, native branch graphs,
repeated-pad identity, sharing bounds and actual pad/drill contact polygons.
It finds five nominal trace-capacity screening failures on the unchanged PFC
board. This supersedes the statement below that all adopted checks have no
failure findings. The [new receipt](runs/2026-09-12-pfc-current/verification.json)
records the final results and remaining software/model gaps. P1–P3 as a whole
remain incomplete; zone/side-contact sharing and pad minimum cuts are not
silently reclassified as hardware-only work.

The implementation and preceding handoff repairs are committed in `734435ed1`.
The final receipt records **312 passing Rust tests**, a passing live KiCad
geometry oracle, and all seven boards passing fresh native ERC/DRC and common
binding checks. Power-entry's overall verdict is **FAIL** from the five nominal
capacity-screen findings; the other six remain **INDETERMINATE**. Saved PCBs
were not edited. The final board run started with clean, committed source, and
its recorded source hashes match the implementation.

The earlier [handoff-repair receipt](runs/2026-09-12-handoff-repair/verification.json)
recorded 287 passing tests and seven INDETERMINATE verdicts before the new PFC
screen. It is historical evidence, superseded by the final PFC receipt above.
This checkpoint does not complete P1–P3 or a shipping review. Formatting and
whitespace checks pass; Clippy retains warnings in unchanged files, so strict
Clippy is not a passing gate. The archives retain both board runs, development
logs and rejected attempts, with the remaining evidence limits in the receipt.

## Reproduce

From the repository root on this host:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check \
  KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli \
  KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9
```

The output directory must be new. The command evaluates all seven boards even
when one fails. Exit 0 means pass, 1 means failure, and 2 means incomplete. Make
reports a nonzero status for an incomplete run; that is intentional. It must
not be converted into acceptance. `check-native-oracle` runs the live pcbnew
asymmetric rotation, slotted drill, via and diagonal-track transport probe.

Buck remains owned by the legacy `harness-lab` experiment. A standalone MCU is
not registered here. Both are explicit deferrals, not implied suite passes.

## What is connected

| Batch | Adopted behavior | Remaining implementation / contract work |
|---|---|---|
| P0 | Seven required units; actual source/native/PCB/contract identity; current truth functions; missing-rule rejection; fresh ERC/DRC with dependency/report hashes; every outcome retained | Uniform per-rule candidate/evaluated/skipped counts are not yet exposed by the older unit functions. Counts in output are explicitly native input censuses. |
| P1 | PFC and gate-drive source/native package pins; explicit gate-domain mapping; nominal outer copper; rectifier/choke/switch/bus and gate-net candidates; nonempty native via/pad associations; optional declared RMS via-barrel screen with net binding | PFC nominal switching-state currents and native pad/drill contacts are now implemented (see the PFC receipt). Remaining: gate-drive branch waveforms, zone/side-contact area sharing, pad minimum cuts, plating/hot-current contracts, and surface creepage/material/barrier modeling. |
| P2 | Current native F.Fab polygons, pad/track/via copper, native round/slot drills, filled zones and Edge.Cuts/cutouts; Rust body overlap, annular ring, drill conflicts, outline containment and malformed-input checks; evaluated/skipped IDs emitted from actual Rust loops | Curved/open F.Fab detail interpretation remains per-object incompleteness. Unresolved native geometry is retained separately in coverage gaps. Authored fabrication/assembly limits, mask checks and 3D body/height checks remain open. |
| P3 | Correct HS/LS Kelvin and boost gate/source return; native cluster binding; current/return bounding-box screen; same-layer parallel overlap on exact switching-output/control-or-sense net pairs, aggregated across split native traces; thermal/timing scalar kernels | Full commutation paths, cross-layer and nonparallel coupling models, authored noise/loop bounds, populated loss/thermal and worst-case delay contracts. Current sense/interlock retain operating-input obligations. |

P1 uses a nominal 20 °C-rise external-trace screening equation, not a qualified
ampacity model. It does not distribute a whole bus current through every branch.
P2's absent fabrication limits do not become defaults: zero in its transport is
only a geometric overlap boundary, and missing authority forces incompleteness.
P3's bounding box is not inductance. Missing thermal/timing inputs and missing
geometry implementations are recorded separately from hardware NOT RUN.

## Defects corrected during integration

- A count-only common command did not execute every unit truth function. The
  new runner uses current inputs and checks the retained rule obligations.
- Old native receipts could be associated by filename alone. New receipts bind
  current source, board, dependencies and exact report bytes to fresh commands.
- P1 guessed RMS current for every same-net branch and misclassified isolated
  control/bias nets. Those findings were rejected. Unknown currents stay unknown;
  gate control, high-side floating and low-side floating groups are explicit.
- P2 approximated pads and traces, omitted vias/zones and mishandled F.Fab poses.
  Native geometry transport replaces those paths. Earlier PFC manufacturing
  failures are rejected evidence, not reasons to modify the board.
- P3 paired a floating gate with control ground and could retain a stale PASS
  after appending a failure. Exact driver/output/Kelvin endpoints and final
  report aggregation now prevent these errors. A trace count is insufficient
  to establish return connectivity; a complete native cluster must bind it.
- Minimum total trace length was called parallel spacing. That false acceptance
  path was removed; geometric coupling implementation remains open.

## Completion contract for further agents

A batch is accepted only after its coordinator has imported the exact files,
reviewed concrete failure cases, run meaningful regressions, and executed the
common command against the current maintained boards. A test count or a
callable library function alone does not finish a batch. Handbacks must name
remaining software gaps as software gaps, not only as physical qualification.

The nominal PFC branch-current/native contact screen is now implemented.
Its next board follow-up is the five recorded capacity-screen failures, with
remaining area-sharing and pad-minimum-cut models kept explicit. P3 populated
thermal/shutdown contracts remain the next separate validation workstream.
P2 body interpretation and authored fabrication limits remain separate work.
The new same-layer overlap screen is geometric, not an EMC model: when its
spacing threshold is absent, the observed overlap is not filtered by distance
and remains INDETERMINATE. Tests split native trace objects and change actual
transported board geometry; they do not mutate saved PCB files.

Coordinator review rejected untested handback code that did not compile,
unpopulated runtime checks, a full-pad-width proxy for entry geometry, a
duplicated scalar creepage helper, rule-count claims in Python transport, and
projection aggregation that could change when a trace was split. The corrected
P2 counts originate in the evaluation loops. The P1 candidate scope is described
in [its evidence note](p1-final/README.md). Full P1–P3 completion is still open.

## Earlier committed-source run (superseded above)

Code commit: `8648e2f77e89f321889957902b64efc7000d8d13`.
The [verification receipt](runs/2026-09-12-integrated/verification.json) records
**276 passing Rust tests, zero failures**, and a passing live KiCad transport
oracle. All seven current boards passed fresh native ERC/DRC and the common
identity/required-rule gates. No failure findings remain in the adopted checks;
all seven overall verdicts are **INDETERMINATE**, not qualified passes.

The [suite identity](runs/2026-09-12-integrated/suite-identity.json) binds the
executable and 82 source files. The worktree was clean at run start, and the
suite inputs did not change during the run. No board bytes changed.

[Per-unit reports and logs](runs/2026-09-12-integrated/verification.json) sit
alongside the verification receipt. The complete raw exports, native commands
and reports, two preceding baselines and development logs are retained in
[the evidence archive](runs/2026-09-12-integrated/raw-evidence.tar.gz), with
[member hashes](runs/2026-09-12-integrated/raw-evidence-index.json).
The final run is under archive prefix `committed-8648e2f77/`; absolute temporary
paths inside receipts describe the original execution environment.
