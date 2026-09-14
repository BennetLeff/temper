# Bridge connection redesign baseline

This bundle records the frozen power-entry board before candidate promotion.
The bridge is **U1 GBU2510A** (`Diode_THT:Diode_Bridge_GBU2510`) with the
manufacturer's 5.08 mm inline pin pitch. Pin/net identity is preserved from
the source manifest: 1=`minus`, 2=`ac1`, 3=`ac2`, 4=`plus`.

The four package necks are the limiting direct copper sections. They are
single straight tracks on the saved board, 0.07 mm copper, with no parallel
layer sharing in the neck itself:

| pin/net | layer | length | width | approximate copper resistance* |
| --- | --- | ---: | ---: | ---: |
| 1 / minus | B.Cu | 8.5 mm | 2.5 mm | 0.837 mΩ |
| 2 / ac1 | F.Cu | 9.0 mm | 2.5 mm | 0.887 mΩ |
| 3 / ac2 | B.Cu | 6.0 mm | 2.5 mm | 0.591 mΩ |
| 4 / plus | F.Cu | 7.0 mm | 2.5 mm | 0.690 mΩ |

\*Resistances use 1.724e-8 Ω·m and the declared 0.07 mm copper thickness;
they are comparison values, not a thermal qualification result. Pad annulus,
plated-hole barrel, solder fillet, connector and downstream 6/8 mm copper are
separate thermal elements and remain in the physical-model handoff.

## Evidence binding

- Board SHA-256: `84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317`.
- Source identity: `source-manifest.json` in this directory, with the board hash
  above and `candidate_variant=baseline`.
- Native copper export: `evidence/native.json` embeds the exact board bytes.
- Native manufacturing extraction: `evidence/manufacturing.json` (54
  footprints, 131 pads, 250 tracks, 44 vias, one zone).
- Native KiCad 10.0.6 ERC and DRC (all severities, all-track-errors and
  schematic parity): zero violations, zero unconnected, zero parity issues.
- Rust `zapote-power-entry`: all construction rules pass; result remains
  `indeterminate` because declared external bias/precharge, 15 A waveform,
  thermal and insulation qualifications are not implemented by this unit
  harness.

The baseline is retained for comparison and is not promoted by this bundle.
