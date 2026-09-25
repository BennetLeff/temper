# Rev38 temporary native generation diagnostic

**Status: diagnostic only, 2026-09-24. U7 native acceptance OPEN.** This
experiment tested whether the frozen `source-build-05` could pass the strict
source-to-KiCad bridge with the user-approved 360 × 250 mm planning outline.
The 295 board footprints were placed by a temporary courtyard shelf pack,
with selected power and connector anchors. Those poses were not reviewed for
current loops, EMI, probe access, thermal paths, cabling or insulation. No
tracks, independent vias, zones or safety slots were authored, and no board is committed
as the Rev38 `native/section.kicad_pcb` deliverable.

## Input and output identity

| Item | SHA-256 / scope |
| --- | --- |
| Frozen Atopile `source-build-05/build-receipt.json` | `4f07f1177fbe39eef940e665892c40285e77925ce4f4622ddbf21cd38672a7f5` |
| Planning `outline.json` | `afdbb58178cc269deb15191e829d93ac3784eac8486606a4fc49e84660b569b6` |
| Temporary 295-path poses | `46d114daca00f24e90a2362ae6ef9ff2b5ac65452d31afde73842fbddf73419b`; local `/tmp/temper-rev38-diagnostic-poses.json`, not a released placement |
| Temporary native board | `0a6888909828f51b407452f4e513ce7771fe97c1d35118f6b58d8b9c353f64c7`; local `/tmp/temper-rev38-native-05-canonical-fix1/section.kicad_pcb` |
| Temporary native schematic | `5cb331384af928e2b43cc9bb9cb89feff728047f92c95baf1b8c95f1737bb59b`; same temporary output directory |

The current native generator built the temporary board and flat schematic
with all **295 board references**, **246 nets**, and **1,052** mapped
`(net, reference, pad)` edges after excluding only the declared off-board F2
`U226`. The independent raw-pad oracle found no missing or extra edges and
no unmapped functional copper. KiCad 10.0.4 schematic-parity DRC found **zero**
issues after board Value fields were aligned to selected MPNs and legacy
footprint reference text was normalized. This proves a narrow connectivity
projection, not functional pin naming or a routed electrical layout.

The generator had previously rejected U130's five unnamed paste/mask
apertures as though they were copper pins. It now preserves those apertures
without electrical mapping and still requires the real copper thermal pad
9 on `HOT0`. Both generator repairs have focused regressions. These are
source-to-native transport repairs, not part or safety qualifications.

## Digital checks that remain red

KiCad 10.0.4 `pcb drc --schematic-parity --severity-all` on the temporary
board reported **36 violations**: 14 `lib_footprint_mismatch`, 10
`clearance`, 8 `drill_out_of_range`, 3 `silk_over_copper`, and 1
`silk_overlap`. It also reported **499 unconnected items**, KiCad's report
cap on this unrouted board. There were no courtyard or board-edge violation
types in this run; the shelf pack is still not a placement review. Of the
10 clearances, three are the temporary U2/U246 proximity; seven are the
0.15 mm adjacent-pad gap intrinsic to U264's stock MSOP footprint against
the donor 0.20 mm rule. The eight drill findings are four 0.20 mm thermal
vias in each TPS3431 U72/U137 footprint against the donor 0.30 mm rule.
The 14 library-footprint mismatches and four silkscreen findings need
individual disposition. These counts are diagnostic, not a DRC ceiling.

KiCad `sch erc --severity-all` on the temporary flat schematic reported
**677 warnings**: 295 `lib_symbol_issues`, 294 `endpoint_off_grid`, 63
`isolated_pin_label`, and 25 `footprint_link_issues`. It is not an ERC
pass. The generated numeric-pin symbols prove no manufacturer functional
pin labels; selected MPN identities are checked separately against the
frozen BOM. The six-layer declarations and 0.20/0.30 mm rules are inherited
from a donor skeleton, not a selected Rev38 fabricator stackup.

## Next native decisions

1. Review cable exits, F2 stud lugs and boots, large-component heat and
   vent space, actual mounting, probe access and the HOT/SELV crossing.
   The two DWW packages have a 15.2 mm nominal opposed copper gap against
   the provisional 16.0 mm Group IIIa board-surface screen; select and
   verify a specific barrier construction and net-pair rules.
2. Decide an application-qualified TPS3431 thermal-pad construction. TI
   shows the 0.20 mm vias as optional; a no-via exposed-pad footprint or a
   selected fabricator's filled-via capability needs review. A narrower
   U264 pad pattern can address the stock footprint's 0.15 mm gap only if
   its solderability and tolerances are accepted. Do not lower the whole
   board's rules to hide these findings.
3. Replace the shelf pack with reviewed, connection-aware poses and route
   the board after U4 electrical review. Resolve native ERC/DRC and
   library mismatches on those saved bytes, then run source/native parity,
   stackup and maintained unit gates. Physical captures remain NOT RUN.
