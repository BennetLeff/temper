# Buck Rev A fabrication notes — frozen revision A

These notes are bound to `pcb/prototypes/buck-reva/source-manifest.json` and
`verification/board-freeze.md`. They describe the prototype board package;
ordering still requires a separate explicit decision.

## Frozen construction

- Outline: 50 × 40 mm, closed Edge.Cuts; two copper layers.
- Material/thickness: FR-4, 1.6 mm; 1 oz finished copper.
- Surface finish: lead-free HASL. Solder mask both sides; front silkscreen only.
- Top-side assembly. Minimum track width 0.2 mm, minimum clearance 0.2 mm,
  minimum copper-edge clearance 0.5 mm. Terminal holes are 1.5 mm PTH;
  H1–H4 are isolated 3.2 mm NPTH M3 holes.
- Fabrication ZIP contains only the actual copper, mask, silk, paste,
  Edge.Cuts and plated/non-plated drill outputs.

## Fabricator capability check

JLCPCB's published capability table documents 1.6 mm FR-4, 1 oz outer copper,
lead-free HASL, and 0.10/0.10 mm minimum track/space for 1 oz two-layer boards:
<https://jlcpcb.com/capabilities/Capabilities>. Those published limits cover
this board's 0.20/0.20 mm rules and 1.6 mm / 1 oz / lead-free HASL selection.
This is a capability match for bare-board fabrication; it is not an order,
quote, or assembly acceptance.

## Via-in-pad prototype treatment

The frozen board has nine 0.8 mm / 0.4 mm tented, unfilled/un capped
via-in-pad core vias, including U3 GND and the feedback divider. Generic SMT
reflow must not be represented as resolving this. The workable Rev A prototype
treatment is: fabricate the bare board to the frozen data, place/reflow the
ordinary SMT population, then hand-solder and inspect the affected via-in-pad
joints (and hand-solder J1/J2) under magnification. IPC-4761 Type VII filled
and capped vias remain an optional fab quotation path, but adding fill/cap is
not part of this frozen release. A later automated assembly order must obtain
explicit assembler acceptance of the unfilled via-in-pad treatment.

No fill, cap, copper weight, layer, thickness or finish change is implied by
these notes. Physical assembly and electrical qualification remain NOT RUN.
