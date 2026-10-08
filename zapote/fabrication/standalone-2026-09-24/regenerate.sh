#!/usr/bin/env bash
set -euo pipefail

# Run from this repository's root with KiCad 10.0.4. The saved board is never
# modified: zone refill/check happens in memory, with no --save-board.
cd "$(dirname "$0")/../../.."
out=zapote/fabrication/standalone-2026-09-24

for name in rtd current thermal interlock gate; do
  case "$name" in
    rtd) base=zapote/rtd/unit; layers=F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,F.Fab,B.Fab,Edge.Cuts ;;
    current) base=zapote/current-sense; layers=F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,F.Fab,B.Fab,Edge.Cuts ;;
    thermal) base=zapote/thermal-sense; layers=F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,F.Fab,B.Fab,Edge.Cuts ;;
    interlock) base=zapote/interlock; layers=F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,F.Fab,B.Fab,Edge.Cuts ;;
    gate) base=zapote/gate-drive; layers=F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,F.Fab,B.Fab,Edge.Cuts ;;
  esac
  pcb="$base/candidate/section.kicad_pcb"
  sch="$base/candidate/section.kicad_sch"
  dest="$out/$name"
  mkdir -p "$dest"

  kicad-cli sch erc --format json --units mm --severity-warning --severity-error \
    --exit-code-violations -o "$dest/erc.json" "$sch"
  kicad-cli pcb drc --format json --units mm --severity-warning --severity-error \
    --all-track-errors --schematic-parity --refill-zones --exit-code-violations \
    -o "$dest/drc.json" "$pcb"
  kicad-cli pcb export gerbers --output "$dest/gerbers" --layers "$layers" \
    --crossout-DNP-footprints-on-fab-layers \
    --sketch-DNP-footprints-on-fab-layers --subtract-soldermask \
    --precision 5 --check-zones "$pcb"
  kicad-cli pcb export drill --output "$dest/gerbers" --format excellon \
    --drill-origin absolute --excellon-units mm \
    --excellon-zeros-format decimal --gerber-precision 5 \
    --generate-report --report-path "$dest/drill-report.txt" "$pcb"
  kicad-cli sch export bom \
    --fields Reference,Value,Footprint,Datasheet,Manufacturer,MPN,DNP \
    --labels Reference,Value,Footprint,Datasheet,Manufacturer,MPN,DNP \
    --sort-field Reference --output "$dest/bom.csv" "$sch"
  kicad-cli pcb export pos --output "$dest/positions.csv" \
    --format csv --units mm --side both --exclude-dnp "$pcb"
  kicad-cli pcb render --output "$dest/top-3d.png" --width 1200 \
    --height 900 --background opaque --quality basic --side top "$pcb"
done

# Review images were rendered separately with pygerber 2.4.3. Keep the Gerber
# files as the fabrication source of truth; images are inspection aids only.
