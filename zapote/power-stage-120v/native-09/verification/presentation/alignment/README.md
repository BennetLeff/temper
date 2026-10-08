# Model alignment correction, 2026-09-26

Corrected J6, L1 and T1 by converting footprint Y to negative model Y in
their STEP and optional VRML sources. Corrected PS2's body Y interval while
retaining its already aligned pins. Regenerated the four STEP assets, updated
their map hashes, and refreshed the assembly render. No PCB bytes changed;
the electrical verification therefore remains applicable.

The earlier model-coverage check established file availability, not alignment.
The earlier visual acceptance missed these errors and is superseded here.

## External geometry check

`before.glb` and `after.glb` were exported by KiCad 10.0.4 from the same
native-09 board with the old and corrected model assets respectively:

```sh
kicad-cli pcb export glb --component-filter J6,L1,T1,PS2,PS1 \
  --no-board-body --output after.glb native-09/section.kicad_pcb
python check_alignment.py after.glb pcb-pad-centres.json
```

The probe reads the exported mesh bounds and scene transforms, then compares
the 14 explicitly ordered model terminals with pcbnew's actual pad centres.
It also checks PS2's body against its footprint's fabrication outline. It does
not reconstruct the STEP generators' geometry.

| Probe | Original | Corrected |
| --- | --- | --- |
| Maximum terminal centre error | 50 mm | below 0.005 mm tolerance |
| PS2 body offset | 3 mm | below 0.005 mm tolerance |
| Result | FAIL | PASS |

The check fails on the original exported models, providing a regression control.
The corrected render was visually inspected: J6 no longer overlaps PS1 and L1
sits over its footprint instead of the fuse/board edge. This is an alignment
check only; the models remain provisional and do not qualify physical fit.

The board SHA remains
`f45f2ffdcaf4b41ba6c9259e711d8f070471e4606ff8b7277dd85c1ed5775b4b`.
The current render receipt also records model asset hashes: board identity
alone does not identify a render when externally linked models change.
