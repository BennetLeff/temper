# Rev38 cross-domain placement diagnostic 04

**Status: saved native placement candidate; U7 OPEN (2026-09-24).** This
diagnostic refines `placement-review/03` on the approved 360 × 250 mm
planning outline. It is an unrouted, unqualified source-to-PFC section board,
not a fabrication or insulation release. The governing electrical source
remains `source-build-06`.

Four SELV-owned receiver parts had been packed among HOT receiver logic in
`/03`. `/04` moves only those four to the source side of the DWW isolators:

| Source instance | `/03` origin (mm) | `/04` origin (mm) |
| --- | --- | --- |
| `receiver.c_iso1_selv` | (227, 91) | (273, 65) |
| `receiver.c_iso2_selv` | (232, 91) | (273, 105) |
| `receiver.source_permit_fb_pd` | (231, 79) | (273, 69) |
| `receiver.source_session_fb_pd` | (212, 80) | (273, 101) |

The [KiCad placement overview](native-diagnostic/placement-fit.png) shows
the resulting courtyards and outline. Native courtyard bounding boxes leave
at least 11.45 mm to the planning-board edge. Ordinary live footprints end
at `x=233.525` mm; SELV/source footprints begin at `x=271.475` mm. Only
the two DWW isolators cross the reserved `x=235–270` mm corridor. All 295
candidate-local library footprints load in KiCad 10.0.4, with zero missing
or out-of-date footprints. These are placement checks, not validated cable,
fastener, thermal, field, creepage or routing constraints.

The exact Rust `domain_clearance` screen projects every classified
SELV/live copper pad onto one layer and applies a **provisional 16.0 mm**
distance. It reports 663 below-floor pairs on `/03` and **104 on `/04`**,
a reduction of 559. Every `/04` pair is internal to one of the two DWW
isolators (52 each); no external cross-domain pad pair remains below that
provisional floor. Both packages retain a **15.2 mm minimum opposed-pad
gap**. Moving whole components cannot alter this intrinsic pad geometry.
The screen is still **FAIL** and does not establish an accepted insulation
class, creepage, air clearance, package-surface path, slot, PE spacing or
net-pair rule. The board has no routes, vias or copper zones. The pinned
test is `zapote/packages/zapote-drc/tests/rev38_placement04.rs`.

The saved source manifest and native export contain the same 295 components,
246 named nets and 1,052 distinct numeric pad edges; 1,070 physical pad
connections include duplicate lands under the same electrical pad number.
The Rust exact-board binder passes component/MPN, pad/net/UUID and copper
census. `zapote-board` passes the saved PCB hash, all six source-input hashes
and provisional six-layer 1.8 mm CAD stackup. A second `build_native.py`
run from the saved `poses.json` reproduced byte-identical PCB and manifest
files. KiCad 10.0.4 ERC has zero findings. DRC with all severities and
schematic parity reports zero violations and zero parity issues. Its 499
unconnected items are capped and the board is unrouted. The current DRC
configuration retains its listed ignored checks; no Rev38 insulation
net-pair rules exist.

## Saved evidence

| Artifact | SHA-256 |
| --- | --- |
| `poses.json` | `46364cc2f125acea987f740bf145a6e786c43327d945869d8acc152e856ec3ed` |
| `native-diagnostic/section.kicad_pcb` | `03dfa0f74a62666215315c880f49bc2b9ce7e7b2a9b964607a58c3f104cabb79` |
| `native-diagnostic/source-manifest.json` | `5de94dbf38b1d67cd764293f76fde93583f2642d21b4942140422fd94b8d5147` |
| `native-diagnostic/native-export.json` | `71165f96f527a2821b6cc40bfee3ac0aa64f02e7672a1d40f0fbf6b4d630bee6` |
| `native-diagnostic/drc.json` | `174a38c2712bb0ada498c51046000d641148eb5639445f301348dedc8af6e938` |
| `native-diagnostic/erc.json` | `19ee683978717ebc15a1d97381c9f0a465aac250f33aec8bc9baabfedbdaeb6e` |
| `native-diagnostic/identity-report.json` | `2d49909d6c641a6429a835b79c080094718a7b4a12e6135088f6e94b25b8a2fb` |
| `native-diagnostic/footprint-parity.json` | `419b8126e83012d7b1d6ca2dd96d71ba852678bcd1c401d4eb79daf30ac41958` |
| `native-diagnostic/source-native-parity.json` | `5b80ed20299ab86e960a9f82cd4946d675414fc97f197f225facd59edcd77648` |
| `native-diagnostic/placement-region-check.json` | `39215d77aa2ccb4623bac53adf15c0b9cc193914e7453a85d3da682c4167f7ae` |

**Not ready for reviewed routing.** U4 electrical review, F1/AUX/F2
construction and qualification, connector and physical-volume review,
current-loop/return and thermal placement review, and a chosen insulation
construction with complete net-pair rules remain open. The DWW 15.2 mm
pad geometry requires a deliberate barrier decision. Any routing, zone,
slot or component move requires a fresh exact-board extraction and screen.
