# Phase 7: Analytical Legalization (DEFERRED)

**Status**: DEFERRED / Future Work.
**Reasoning**: The Physics-Based Legalizer (Phase 6) successfully resolved the critical collisions (`AC_L`/`CGND`) and enabled 100% routing. Implementing a complex LP/Graph solver now would be over-engineering without a proving failure case.

---

# Phase 6.5: Visual Verification

## Objective
Generate visual artifacts (SVG/PNG) of the routed board to confirm placement quality and routing cleanliness manually or via computer vision.

## Experiments

### Experiment V1: SVG Export
**Goal**: Render the output PCB layers.
**Method**:
`kicad-cli pcb export svg --layers F.Cu,B.Cu,F.SilkS --output output.svg pcb/temper_router_v6_output.kicad_pcb`
**Verification**: Check if `D1` and `U_GATE` are visibly separated.

## Implementation
- `scripts/render_result.py`: Automates `kicad-cli` export for Top/Bottom layers.
