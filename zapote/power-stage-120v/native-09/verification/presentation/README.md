# Native-09 labels and models, 2026-09-26

**Follow-up:** the [model alignment correction](alignment/README.md) supersedes
the initial visual acceptance below. Four external model assets were corrected;
board bytes and electrical checks are unchanged. The assembly preview is current.

The active file remains `native-09/section.kicad_pcb`.

- Input: commit `540170dcc`, board SHA-256
  `ccaa385921f686d6d08859cf4e81fb2e93014c434a935996a85257a1f3594112`.
- Output: `f45f2ffdcaf4b41ba6c9259e711d8f070471e4606ff8b7277dd85c1ed5775b4b`.
- Runtime: KiCad 10.0.4. Work delegated to four GPT-6 Sol agents at xhigh effort,
  each in an isolated worktree; integrated and independently checked here.

All 114 reference fields are visible on F.Silkscreen within 4 mm of their
footprint courtyard. `Sheetpath`, `SourceInstance` and `MPN` are hidden and
located at their footprint origin. Their values remain available in properties.
The scattered captions were misplaced metadata, not missing electrical parts.

All 114 components resolve a visible model. Sixteen added STEP assets cover 22
components; 92 stock assignments are retained. The new assets are provisional
dimensioned envelopes, with sources and limitations in `../../../models3d/`.
They do not include the heatsink, enclosure, loose links or wiring hardware.

## Verification

`physical-invariance.json` compares the parsed KiCad board before and after,
excluding only immediate footprint property/text/model nodes. Every remaining
node is identical, including footprint poses, pads, copper, zones, outlines and
stackup. `compare_physical.py` records the comparison procedure. The separately
extracted copper-item digest also matches the earlier verification exactly.

| Check | Result |
| --- | --- |
| Model assets | 114/114 references resolve; added asset hashes checked |
| Source/native parity | PASS, 114 components, 313 source pins, 333 copper pads |
| Saved copper identity | PASS, 560 tracks and 147 vias |
| Stackup | PASS, four layers, 1.653 mm |
| JLCPCB geometry screen | PASS |
| All-layer barrier | 0 findings |
| Full DRC, three runs | Each: 28 existing library mismatches, 3 existing silk overlaps; 0 schematic mismatch |
| Unconnected items | 1 existing intentional R5 Kelvin split |
| Tests | Initial suite 41/44; all 15 routing-evidence tests pass after preserving the frozen generator, resolving the three failures |

The initial failures correctly detected that a proposed generator metadata edit
would stale the replay input. That edit was not retained. Presentation adapters
remain a separate, repeatable final step; no historical manifest was repinned.
Raw test logs and DRC reports are retained here. Existing parent-directory
verification reports describe the input board and are intentionally preserved.

The combined board was rendered and inspected in KiCad. Current previews:
[3D assembly](../../previews/assembly-3d.png),
[reference drawing](../../previews/reference-labels.png),
[front copper and labels](../../previews/front.png).
This is a visual/documentation revision, not fabrication or powered-operation
approval. The existing physical qualification items remain open.
