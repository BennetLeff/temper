# Active-rectifier geometry repair receipt

This receipt records the bounded native-routing repair before the coordinator
refreshes the canonical native export, source digest, and manufacturing
evidence. It does not promote the board to a qualified design.

## Inputs and edits

- Board: `candidate/section.kicad_pcb`
- Route contract: `routes.json`
- Baseline board/source bytes: the branch `HEAD` versions, followed by the
  existing 10-node spacing repair recorded in `spacing-edits.json`.
- Eight high-current route paths were widened from 3.0 mm to 4.3 mm on the
  RECTIFIER_L and RECTIFIER_NEGATIVE trunks. The L path was then routed around
  the holder and L1 pads through `[5,127.0] -> [20,131] -> [35.08,131]`.
- RECTIFIER_NEGATIVE was lifted through `[-13.1,116] -> [5,116] ->
  [20,120] -> [30,123.5]` while retaining its downstream connection.

## Reproduction and results

The following were run against the final board bytes in this receipt:

```text
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc \
  --all-track-errors --schematic-parity --severity-all \
  --output /tmp/ar-kicad-final/drc.rpt \
  candidate/section.kicad_pcb
```

Result: exit 0, 0 KiCad violations, 0 unconnected items, 0 schematic-parity
issues. No `--refill-zones --save-board` run was performed; the coordinator
must perform the final refill and save before replacing the retained native
export.

```text
/Applications/KiCad/.../python3 zapote/current-sense/tools/
  extract_current_sense_native.py --repo . --board candidate/section.kicad_pcb \
  --output /tmp/ar-geometry-final3.json
/Users/bennet/Desktop/temper/target-shared/debug/zapote-power-entry \
  candidate/source-manifest.json /tmp/ar-geometry-final3.json \
  candidate/section.kicad_pcb
```

Result: native profile reports exactly three remaining findings, all the
known intrinsic 1.940 mm bridge-footprint pad spacings:

- `bridge.3 / bridge.5`
- `bridge.14 / bridge.16`
- `bridge.10 / bridge.12`

The eight prior `DRC.PFC.BRANCH_COPPER` 15 A RMS failures are absent. These
three pad findings are not waived or hidden; they require a footprint/package
decision if the 2 mm elevated-voltage floor is retained.

Board SHA-256: `419ad74a7af03950cd7acde20adf54c76c811defc4cb1bb7bca9a9c472e51abc`

## Retained outputs

- `geometry-native-profile-final.json` — native profile output, SHA-256
  `df230af9e8ee06e654f11bc4dbc4e97360c7a3135c8f717b0b792c69a95f9c11`
- `geometry-kicad-drc-final.rpt` — KiCad DRC output
- `routes.json` — updated replay contract, SHA-256
  `d36f6cecb0b4be255ab1fdc8bd401af4837883ac4a17c79cfa9fb5be41106441`

The native profile binary used for this receipt predates the coordinator's
additional half-bus bleeder-pair active-HV classification. Re-run the profile
with that updated binary before final acceptance; this receipt preserves the
geometry result and its exact remaining findings only.
