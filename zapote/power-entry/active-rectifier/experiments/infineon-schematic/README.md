# Active bridge schematic experiment

This directory is a construction candidate for the 120 Vac, 1.8 kW-class
input power-entry unit. It is deliberately separate from the existing TEA2209T
candidate and does not change the product CAD, BOM, or harness.

The source of truth is `src/main.ato` and `src/components.ato`. Atopile 0.2.69
produced `build/default.net` and `build/default.csv`; the native KiCad schematic
under `native/` was then emitted from those files. The native export is ready
for independent pin/net review and placement planning. It is not a production
release: bootstrap hold-up, auxiliary-rail tolerance, surge, fault interruption,
thermal design, creepage/clearance, and hardware qualification remain open.

Rebuild:

```sh
cd zapote/power-entry/active-rectifier/experiments/infineon-schematic
uv tool run --from 'atopile==0.2.69' ato --non-interactive build src/main.ato:InfineonActiveBridge
```

The native emitter is the existing source-bound adapter:

```sh
python3 zapote/power-entry/tools/draw_schematic.py --repo . \
  --source zapote/power-entry/active-rectifier/experiments/infineon-schematic \
  --output zapote/power-entry/active-rectifier/experiments/infineon-schematic/native \
  --receipt zapote/power-entry/active-rectifier/experiments/infineon-schematic/native/receipt.json
```

See `SOURCES.md`, `DOMAIN-TABLE.md`, `TIMING-REVIEW.md`, `REVIEW.md`, `DECISION.md`, and the
retained exports under `native/exports/` for the evidence boundary.
