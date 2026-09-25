# Rev38 /03 native insulation coverage receipt

**Status: FAIL for release; topology census only (2026-09-24).** The saved
`placement-review/03/native-diagnostic/section.kicad_pcb` remains an unrouted
candidate. This receipt binds to board SHA-256
`c277e9cae08213557f8bed43253253966229c695a9e754474d229babcf786ff5`,
native export SHA-256
`3c539845b5e6e7b841d2450732d9ac6bc25b8b64d0abe9d24637ce9fd651b56e`,
and source manifest SHA-256
`46bd18598f2717da1891d0398639a60bebc798e13bfecb529ac60cbe05de4798`.
The Rust test checks those hashes, the embedded board bytes, the source/native
named-net census, and the strict native pad/copper binder before counting
pairs. The separate `/03` parity test checks all 1,052 numeric source pad
edges against both the native connection list and the exported physical pad
list; a stale connection projection fails.

The binder checks saved-board pad UUIDs and nets but does not itself compare
world pad geometry or layers. This test separately compares the type and
layers of all 19 empty-net pad objects against the KiCad board and rejects a
mask/paste-to-copper mutation. KiCad 10.0.4's `pcbnew` extractor was rerun on
the exact `/03` board with
`zapote/current-sense/tools/extract_current_sense_native.py` SHA-256
`42b771f81f46b3054c26d3e3f80c79ab02a78964e048f2db29e88fd2cf2bea8b`.
Its new export was **byte-identical** to the saved `native-export.json`
(SHA-256 above), including pad types, layers, positions and shapes. This
reproduction anchors the frozen diagnostic geometry to KiCad; every future
board or extractor change requires a fresh extraction and comparison.

## Pair census

Each of the **246 named source/native nets** has exactly one physical pad
side: 62 SELV, 183 live, and one PE. The side assignments use source and
source-MCU component ownership, the two isolators' numbered 1–8 and 9–16
pin banks, the four identified SELV receiver parts, and both PE terminals.
Conflicting owners on one net fail. The 19 unassigned pad objects are mask,
paste, or NPTH objects as recorded in `NATIVE-DOMAIN-SCREEN.md`; they do not
create a named copper net.

Every unordered pair of distinct named nets is counted once. Pair identity
is the lexicographically ordered pair of exact net names in the frozen source
manifest. The five classes below are **physical-side categories for coverage**,
not approved electrical insulation grades or voltage assignments.

| Physical-side pair category | Exact pairs | Accepted release rule |
| --- | ---: | --- |
| SELV to SELV | 1,891 | Missing: functional differential and construction schedule |
| Live to live | 16,653 | Missing: AC, HOT control, VD, VB and fault differential schedule |
| SELV to live | 11,346 | Missing: reinforced crossing schedule; provisional copper-distance diagnostic only |
| SELV to PE | 62 | Missing: accessible-part and PE relationship decision |
| Live to PE | 183 | Missing: basic/protective separation and fault schedule |
| **Total** | **30,135** | **30,135 unresolved release pairs** |

The 16.0 mm FR-4 value from `INSULATION-BASIS.md` is retained solely as a
provisional projected **copper-distance** screen for the SELV/live category.
It is not a KiCad creepage or air-clearance rule, and it does not cover the
package surface, solder, slots, coating, enclosure, or PE paths. The DWW
opposed-pad gap remains **15.2 mm** against that provisional screen. The test
requires the diagnostic rule's exact identifier, category, and 16.0 mm value;
removing it or reducing it to 15.0 mm fails the diagnostic coverage check.
No diagnostic rule is counted as an accepted release rule.

## Negative controls and limits

`cargo test -p zapote-drc --test rev38_insulation_coverage` checks that a
missing source net, an extra native net, an unclassified new component,
a changed unassigned pad that becomes copper, a mixed-side isolator net, and a
PE-to-HOT miswire fail the side census. A synthetic F.Cu SELV trace crossing
an isolator HOT pad is detected by the native geometry screen and rejected
by the strict saved-board binder. These mutations are test fixtures; they do
not modify the candidate PCB.

There is **no accepted `section.kicad_dru`**. Before one can be released,
the product-safety review must approve the standard and edition, voltage
and transient ceiling for every relevant AC/HOT/VD/VB/SELV/PE pair, insulation
grade, air and surface distances, material/slot/package construction, and
exceptions. The integration owner must then map each exact pair to a native
rule, test rule removal and a copper bridge against the routed board, and
review assembled physical paths. The current census does not make the
board's insulation PASS.
