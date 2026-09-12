# Coordinator integration checkpoint

P0 now executes the maintained unit suites and adopted P1–P3 implementations
through one command. **The full P1–P3 implementation plan remains incomplete.**
A subagent final message is a handback for review, not acceptance of the batch.

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
| P1 | PFC and gate-drive source/native package pins; explicit gate-domain mapping; nominal outer copper from parsed stackup; selected bus/bias trace width screens; explicit via/pad/isolation incompleteness | All power branches, RMS/peak waveform contracts, via current sharing, pad-entry current geometry, surface creepage/material/barrier modeling. Extend to other interfaces after these are sound. |
| P2 | Current native F.Fab polygons, pad/track/via copper, native round/slot drills, filled zones and Edge.Cuts/cutouts; Rust body overlap, annular ring, drill conflicts, outline containment and malformed-input checks | Curved and open F.Fab detail interpretation remains explicit per-object incompleteness. Authored fabrication/assembly limits are absent. 3D body/height checks and fabrication qualification are not claimed. |
| P3 | Correct HS/LS Kelvin gate returns and boost gate/source return; native cluster population binding; current/return bounding-box screen; thermal/timing scalar kernels | Full commutation paths, actual layer-aware parallel coupling/spacing, approved loop bounds, populated loss/thermal and worst-case delay contracts. Current sense/interlock run the operating-input obligations; they are not mislabeled power commutation loops. |

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

The next bounded implementation is P1 branch-current and current-sharing
coverage, followed by P3 geometric coupling and populated operating contracts.
P2 body interpretation and per-rule population counts remain separately owned
software work. These tasks must preserve the existing board verdicts and may
not relax limits or rewrite the PCB to accommodate an unverified instrument.
