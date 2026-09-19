# Build receipt

Build date: 2026-09-19. Worktree: `/private/tmp/temper-active-bridge-alternative`.

Commands run:

```sh
cd zapote/power-entry/active-rectifier/experiments/infineon-schematic
uv tool run --from 'atopile==0.2.69' ato --non-interactive build src/main.ato:InfineonActiveBridge
python3 zapote/power-entry/tools/draw_schematic.py --repo . --source \
  zapote/power-entry/active-rectifier/experiments/infineon-schematic \
  --output zapote/power-entry/active-rectifier/experiments/infineon-schematic/native \
  --receipt zapote/power-entry/active-rectifier/experiments/infineon-schematic/native/receipt.json
kicad-cli sch export netlist --output native/exports/active-bridge.xml native/section.kicad_sch
kicad-cli sch export pdf --output native/exports/active-bridge.pdf native/section.kicad_sch
kicad-cli sch erc --output native/exports/erc.rpt --exit-code-violations native/section.kicad_sch
```

Atopile 0.2.69 build: PASS. Native export: PASS. KiCad netlist/PDF export: PASS.
Native ERC with the standard KiCad table and candidate-local exact footprints:
0 errors and 0 warnings; see `native/exports/erc.rpt`.

The native emitter is an existing adapter under `zapote/power-entry/tools`; no
new Python engineering model was introduced. No PCB was edited.
