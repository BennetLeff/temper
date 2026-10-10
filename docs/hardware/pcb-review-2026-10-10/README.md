# PCB review evidence packet — 2026-10-10

This packet supports [the applied review](../PCB_DESIGN_REVIEW_2026-10-10.md) and all 160 rubric records. It preserves negative and indeterminate results. No PCB, circuit source, fabrication profile or acceptance baseline was changed. Hardware status: **NOT RUN**.

## Evidence index

| Code | Evidence | Scope and limitation |
| --- | --- | --- |
| E01 | [Unit summary](unit-summary.json); full [RTD](units/rtd.json), [current](units/current-sense.json), [thermal](units/thermal-sense.json), [interlock](units/interlock.json), [gate](units/gate-drive.json) runner results | Actual maintained registry, native/report bindings, stackup, fab, model and operating/assembly gaps; all overall indeterminate. |
| E02 | [Native-20 board result](native20-board-report.json) | Exact board/schematic/profile, checker findings and manufacturing coverage gaps; overall fail. |
| E03 | [Current extraction receipt](native20-current-command.json), [current failure](native20-current-failure.json), [runner log](native20-current-run.log) | Extraction succeeds; Rust rejects zero-length track. No resistance/ampacity/temperature result. Full snapshot remains in local scratch with its hash recorded. |
| E04 | [Supply inventory](supply-inventory.json), [raw pad geometry](geometry/) | 53 supply/reference-pin records, 38 IC/reference footprints, six actual boards. Straight pad-center distances are screening data, not routed loop metrics. |
| E05 | [Native-21 compiled net facts](native21-netfacts.json) | 331 resolved components and compiled nets, including all four exact TPS709 pin connections. Source-only, no invented board coordinates. |
| E06 | [Native-21 ECO](../../../zapote/power-stage-120v/native-21/ECO.md) and [source](../../../zapote/power-stage-120v/elec/src/power_stage_120v.ato) | Current source handoff; changes from native-20 and still-required physical acceptance. |
| E07 | [IC advice and source register](../PCB_IC_DATASHEET_GUIDANCE.md), datasheet identities in [provenance](identities.json) | Manufacturer requirements/recommendations, exact source/suffix applicability. Source PDFs remain locally retained and linked at official URLs; PDFs are not reproduced here. |
| E08 | [Layer and native 3D renders](renders/) | Every copper layer on six boards; original SVG plus complete PNG previews. 3D bodies are incomplete and no installed enclosure is represented. |
| E09 | [Native current model](../../../zapote/layout-quality/CURRENT.md), [older native-17 thermal study](../../../zapote/power-stage-120v/validation-results/04-board-current-thermal/round4/README.md), [current source rail campaign](../../../zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D33/README.md), unit model receipts under E01 | Conditional model evidence; old geometry, current allocation and parasitic assumptions do not transfer automatically. |
| E10 | Explicit evidence gap | Not an empty successful check. Score U means the required evidence was not established in this review; it does not assert that no such evidence could exist elsewhere. |

F01–F12 refer to specific findings in the review. [scorecard.csv](scorecard.csv) has one manually assessed project-level record for each rubric ID, with explicit applicability, actual rationale and closure evidence. [score-summary.json](score-summary.json) records the deterministic arithmetic only; it is not a new electrical validator or production acceptance policy.

## Reproduce the executed checks

Run from the review checkout root. Executables on this host were:

```sh
KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
KICAD_PYTHON=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
```

Run the native framework in a logged-in macOS session. The supplied runners initialize their own native environment and copy sidecars; do not substitute an incomplete ad-hoc board directory. The Rust builds used the shared target cache `/Users/bennet/Desktop/temper/target-shared`, with `CONDA_PREFIX` removed. Exact extractor, executable, profile and input hashes are retained in their receipts.

```sh
env -u CONDA_PREFIX CARGO_TARGET_DIR=/Users/bennet/Desktop/temper/target-shared \
  make -C zapote check-units \
  KICAD_CLI="$KICAD_CLI" KICAD_PYTHON="$KICAD_PYTHON" \
  RUN_DIR=/tmp/temper-pcb-rubric-review/units-reproduce

env -u CONDA_PREFIX CARGO_TARGET_DIR=/Users/bennet/Desktop/temper/target-shared \
  make -C zapote check-board \
  BOARD=power-stage-120v/native-20/section.kicad_pcb \
  SCHEMATIC=power-stage-120v/native-20/section.kicad_sch \
  PROFILE=fab-profiles/jlcpcb-4layer-2oz.json \
  KICAD_CLI="$KICAD_CLI" KICAD_PYTHON="$KICAD_PYTHON" \
  CHECK_RUN_DIR=/tmp/temper-pcb-rubric-review/native20-board-reproduce

env -u CONDA_PREFIX CARGO_TARGET_DIR=/Users/bennet/Desktop/temper/target-shared \
  make -C zapote check-current \
  LAYOUT_BOARD=power-stage-120v/native-20/section.kicad_pcb \
  KICAD_PYTHON="$KICAD_PYTHON" \
  CURRENT_RUN_DIR=/tmp/temper-pcb-rubric-review/current-native20-reproduce
```

Choose a fresh, nonexistent evidence directory for each run; the runners refuse to overwrite an existing run. The preserved current log is from `current-native20-repeat`, using the same PCB/extractor identities and the same offending track record as the original `current-native20` run. The complete exported snapshots have different byte hashes because per-track `pad_contacts` UUID arrays differ in order. Sorting only those arrays yields identical snapshots; the original bytes and both hashes remain retained. No assumption of byte-stable exporter ordering is required for this failure. A directory-reuse attempt stopped before extraction and is not used as evidence for F05.

Expected recorded exits: unit suite **2**, board suite **1**, current runner **2**. These results were not suppressed or converted to passes. The current snapshot schema is `zapote.layout-native.v3`, with 725 straight tracks, 192 vias, 25 zones and 434 exported pad records; raw pcbnew inspection includes all native pads and is a different population. Native exporters distinguish flashed copper from all-layer/all-pad objects.

The native pad oracle was a second pcbnew read of each board with `wx.App(False)`, comparing per-reference **multisets** of pin, net and world position. Preserve repeated physical pads with the same electrical number. The completed all-board oracle receipt is [native-pad-oracle.json](native-pad-oracle.json). A dictionary keyed only by number initially manufactured 45 apparent native-20 position disagreements; the complete multiset had **zero** disagreements. All five units also had zero mismatches. Direct pad positions came from KiCad, not independently reimplemented rotation arithmetic.

For plots, the executed export pattern was:

```sh
"$KICAD_CLI" pcb export svg --layers F.Cu,F.Silkscreen,Edge.Cuts \
  --page-size-mode 2 --output /tmp/temper-pcb-rubric-review/renders/native20-fcu-full.svg \
  zapote/power-stage-120v/native-20/section.kicad_pcb
```

Other copper layers were exported individually with Edge.Cuts. PNGs were rendered from the original SVGs with the bundled `sharp` library at 180 DPI and 1800 px width, preserving full aspect ratio. macOS Quick Look's first thumbnails cropped the wide board; **only full-aspect previews** are preserved and used for the completed visual inspection. Some unit exports retain drawing-sheet decoration; purple frame lines are not copper. Native-20 top 3D used KiCad's native renderer; its simplified models cannot close interference or assembled-insulation checks.

## Preservation and identity

[identities.json](identities.json) stores full hashes and source paths. The broader unmodified raw run directories remain at `/tmp/temper-pcb-rubric-review/`; that temporary directory is useful locally but is not durable storage. This committed packet retains the authoritative unit/board JSON results, all raw pad facts used for the decoupling findings, native-21 net facts, current failure/command/log and inspection renders. Existing circuit/model evidence stays at its linked repository paths. Native-generated SVG/log files are marked binary in the local `.gitattributes` to preserve their original whitespace/bytes and keep generated drawing markup out of text diffs; inspect the SVG/PNG artifacts and explicit native findings. JSON/CSV/review prose retain ordinary text diffs. File hashes for the packet itself are in [packet-hashes.json](packet-hashes.json).

Native warnings were observed in a single inspection run per board, not used as a newly measured DRC ceiling. No source or PCB fix is implied by this documentation. Any next edit must reopen affected rows, update source-derived artifacts, recheck physical stackup and execute the revision-matched validators.
