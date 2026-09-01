# Net-41 In3.Cu corridor declaration

This evidence authorizes a bounded scratch campaign, not a production-board change. The predecessor R14 east-shift family evaluated all 240 declared candidates and stopped indeterminate: every candidate retained the J1-to-net-41 safety veto, while live pcbnew rotation evidence was unavailable and one baseline DRC category was capped. That result supports a new route-topology hypothesis; it does not prove the predecessor design space exhausted.

The production net-41 predecessor is open: its 15-segment chain starts at `(112, 218)`, while the actual C7.1 pad is at `(112, 206)`. The proposed family repairs that 12 mm disconnection by replacing the complete route from the exact C7.1 pad. It keeps the production connector interface, K1, U8, outline, mounting geometry, net identity, 0.5 mm route width, and 0.9/0.3 mm In3.Cu-to-F.Cu blind via, then uses a same-layer dogleg through one of four corridor centerlines and three entry portals to one of four R14 endpoints. Combined with the 60 predecessor neighborhood placements, the immutable Cartesian product is 2,880 candidates.

## Designer admission result

The design basis replayed every predecessor placement against the board hash in `design-basis.json`. The independent Rust pad-to-capsule instrument examined all 19 LV_CONTROL pads present on the route layer/all-copper denominator for the 720 placement/template pairs in the 122.64 mm endpoint column. The smallest straight-line separation was 12.9 mm, above both the 6.0 mm project clearance target and the 12.6 mm PD3 production creepage role. This proves one complete endpoint column is worth screening, which is the declaration admission bar; it makes no bound claim for the other 2,160 candidates and does not replace routed creepage or KiCad DRC.

`declaration.json` is immutable pre-run authority. Later execution may write separate manifests and a terminal receipt, but must not rewrite the declaration. `validate_declaration.py` invokes the Rust topology owner and checks the board, predecessor, design basis, domain manifest, generated inputs, declaration digest, and the full content-addressed candidate set.

Execution must use the bound v3 screening API. It rejects a missing, extra, substituted, or duplicated candidate before ranking, so a partial screen cannot be mistaken for the declared 2,880-candidate campaign. Its result is deliberately named `clearance_creepage_prefilter_subset`: no candidate may enter the route-first set until the execution driver also applies every other declared hard veto to a materialized scratch board.

## Explicit exclusions

This work does not change `pcb/temper.kicad_pcb` or `power_pcb_dataset/drc_ceiling.json`, release a board for fabrication, approve an IEC interpretation, move K1/U8, change connector access, add a layer transition, or authorize a manufacturing slot. A qualified appliance-safety review of the current standards editions remains required.
