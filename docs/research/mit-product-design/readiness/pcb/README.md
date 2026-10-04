# PCB integration readiness — 2026-10-04

The next useful hardware milestone is an integrated engineering prototype.
The present source correction and routed power board are different artifacts;
neither is a manufacturing release. This review uses the Temper PCB/power,
KiCad PCB, schematic, and export skills. No native PCB, schematic, circuit
source, shared toolchain, or production artifact was changed.

## Exact baseline and fresh evidence

| Artifact | Identity and result |
|---|---|
| Latest routed power board found | `ps-oracle` checkout, commit `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, `zapote/power-stage-120v/native-18/section.kicad_pcb`; SHA-256 `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002` |
| Native18 source | 135 components, 83 nets; independent pcbnew extraction and existing Rust parity validator PASS: 388 copper pads, 368 source pins. [Fresh result](evidence/native18-parity-recheck.json) |
| Native17→18 bounded revision | Fresh identity replay PASS; R9/R17 are retained at RT0603BRD0749K9L, 49.9 kΩ. [Fresh result](evidence/native18-identity-recheck.json) |
| Corrected HOT5 source | This checkout at `dea4649ff466cf36b49a0523d8232c94c317b163`, `zapote/power-stage-120v/frozen/default.net`, SHA-256 `26f95d5aa092d3aba2890421204d53aab16ce332c2e81d22990de64fb30ddb02`; 142 components, 88 nets; prior compiled source/audit receipt retained |
| Fresh DRC | KiCad 10.0.4, scratch copy with matching rules, project, schematic, footprint table and libraries, in-memory refill, all-track-errors and schematic parity: exactly the same 39 violation objects as native18's saved refill report; 36 library-mismatch warnings, three silk-overlap warnings; one Kelvin-split open error; zero schematic parity findings. [Raw report](evidence/drc-live-1.json) |

The fresh DRC was one corroborating run, not a replacement for native18's
historical three-repeat campaign. Its one open is consistent with the
documented R5 Kelvin split; its representative endpoints are not a complete
connectivity proof. Never bridge it merely to obtain a green report. The
original board and scratch board still have the hash above. Sandboxed CLI
attempts crashed in the macOS Swift runtime before yielding a report; a
read-only run outside the sandbox completed. Native18's warnings are real
review items, not missing-library resolution: the expected 135/0 resolution
failure signature was absent.

Fresh ERC completes with zero errors and 280 warnings: 135 unavailable
symbol-library identities, 134 off-grid endpoints, and 11 isolated-pin
labels. These are not 135 bad components: the generated schematic lacks
resolvable library identities. More seriously, all 139 embedded symbol pin
declarations are `bidirectional`, so ERC cannot meaningfully check intended
input/output/power-pin compatibility. Restore typed, function-labeled symbols
and independently audit selected-package pin functions before claiming an
electrical-rule pass. Source parity proves agreement with the authored
source; it cannot prove that source's electrical assumptions. [Raw ERC](evidence/erc-live.json)
and [verification receipt](evidence/verification.json) preserve this limitation.
No fabrication or populated STEP export was produced because the existing
DRC error does not meet the export skill's gate. The
[geometry inventory](../../../../../output/temper-manufacture-readiness/pcb/native18-geometry.json)
is a read-only inspection artifact, not an assembly export.

## HOT5 integration is a small circuit change, but not an IC drop-in

The [machine-readable component and pin delta](evidence/hot5-integration-map.json)
compares the *native18* frozen source to the corrected source. All 135
existing source paths/reference designators are retained. Only one existing
component changes identity: U8. R9/R17's native18 correction is preserved.

| Part | Required native change |
|---|---|
| U8 | SN74LVC1G00DBVR / SOT-23-5 → SN74LVC1G10DBVR / SOT-23-6. Existing location (74.8, 38.8) mm, 0°. Rebuild its symbol and footprint; do not retain old pad assignments. |
| U14 | Add TPS3700DDCR, SOT-23-6: 1 HOT5_UV_RAW, 2 LEG_RET, 3 HOT5_UV_SENSE, 4 LEG_RET, 5 V15_LS, 6 unused OUTB. |
| U15 | Add SN74LVC1G17DBVR, SOT-23-5: 1 NC, 2 HOT5_UV_RAW, 3 LEG_RET, 4 HOT5_OK_HOT, 5 HOT5. |
| R48 / R49 | Add 105 kΩ / 10 kΩ divider from HOT5 through HOT5_UV_SENSE to LEG_RET. |
| R50 | Add 10 kΩ pullup from HOT5 to HOT5_UV_RAW. |
| C48 / C49 | Add 100 nF bypasses: V15_LS–LEG_RET at U14 and HOT5–LEG_RET at U15. |

**U8 pins 2 and 3 exchange roles.** Old pin 2 is OVP_OK_HOT; new pin 2
is LEG_RET. Old pin 3 is LEG_RET; new pin 3 is OVP_OK_HOT. New pin 6
is HOT5_OK_HOT. Pins 1/4/5 retain OCP_OK_HOT/BUS_FAULT_HOT/HOT5,
but changing a five-pad footprint to six pads also moves pad 5 in the
standard land pattern. Every attached route must be checked by pin identity
and actual pad position, not by proximity. TI's
[SN74LVC1G10 datasheet, page 1](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf)
confirms the DBV pin assignment. The U5 unused pin-3 net is renamed from
`nc` to `u_ref-nc`; preserve its isolated/no-connect intent. U14.OUTB and
U15.NC are isolated source nets, not a request to join unused pins together.

The existing native generator makes an unrouted placement; native18's own
receipt states it cannot preserve the routed presentation board. Therefore
running `build_native.py` over native18 would discard the route work. A
controlled integration needs a source-generated candidate for comparison
and a reviewed patch of the routed board, with original copper receipts
preserved and new/removed copper explicitly recorded. No such candidate
was generated during this readiness review: unresolved device/heatsink
placement and controller interfaces make a full board revision premature.

## Mechanical and manufacturing interfaces now established

- Edge.Cuts centerline rectangle: **240 × 160 mm**. pcbnew's drawing bounds
  are −0.05, −0.05, 240.1, 160.1 mm because they include the 0.1 mm line
  stroke. Do not add that stroke to the mechanical nominal outline.
- Saved thickness **1.653 mm**, from the declared stackup sum. Supplier
  target is nominal 1.6 mm ±10%; outer copper is 70 µm, inner copper 61 µm.
  The older claim of 70 µm on all four layers is not this saved stackup.
- There are no dedicated board-mounting `H` footprints or dedicated `TP`
  test-point footprints. Component NPTHs serve their own connectors/studs;
  they are not an approved enclosure mounting pattern. Define mounting,
  retention, insulated hardware, probe access and mechanical keepouts before
  route freeze. Existing accessible pads may support some tests, but access
  and safe probing have not been proven.
- Q5/Q6/Q3/Q2 are vertical TO-247s at x = 92.55/110.55/132.55/150.55 mm,
  respectively, all y = 4.215 mm and 0°. This row faces the **y=0 edge**.
  A sink placed against the opposite long edge is not directly coupled.
  Footprint origins are not tab-contact planes; validate exact package and
  clamp/insulator geometry. Distinct live tabs must retain their insulation
  from a shared PE-bonded sink.
- J4 is at (112.5, 64.08) mm, 0°. J1 is at (6.7, 150.455), −90°;
  coil studs J2/J5 at (231, 70.5)/(225, 151). Full pad positions, other
  terminals, model paths and transformations are in the geometry inventory.
- All **135 model assignments resolve** on this host, including **24 local
  provisional envelope assignments**. Resolution is not dimensional
  qualification. The library driver model also approximates a 14-pin DWK
  with a 16-lead body. Harnesses, terminal hardware, mating connectors,
  insulators, sink, fans and mounting are not represented by model coverage.

## Board work in dependency order

1. **Freeze one integrated interface revision.** Power work must choose a
   feasible operating envelope below the *actual* complete protection
   limits. The previous 45 A model allocation is not a hardware limit;
   existing hot-corner shunt evidence reaches approximately 38.44 A. Resolve
   the power worker's result before treating 40–45 A as an operating target.
   Mechanical work must place device contact row, sink/duct, board mounting,
   coil leads and dedicated fan supply. Controller/interlock work must
   allocate J4, four PWM signals, reset/permit and sense receivers.
2. **Integrate corrected source into native schematic.** Preserve all 135
   original path/ref pairs and R9/R17. Add the seven parts and five net names
   exactly as the delta; verify package drawings and intentional unused pins.
   Restore electrical pin types/function names and resolvable symbol-library
   identities; inspect the 134 off-grid endpoints and 11 isolated labels
   against intended connectivity. Rebuild schematic visuals and compiled source with the pinned toolchain;
   repeat 58 source-audit tests including mutation tests. Add native parity
   expectations for all 142 components; do not certify only the old 135.
3. **Patch placement and routing in an isolated next native revision.**
   Detach U8's changed/moved pads first. Place monitor/divider/bypasses near
   HOT5/U3 (62,17.7 mm) and U8, keeping divider/return quiet and the monitor
   on V15_LS. Maintain a Kelvin return to the existing protection ground;
   do not route fault/sense returns through switching-power copper. Add
   agreed test access and mounting keepouts. Do not move bridge parts merely
   to fit these small parts without redoing their parasitic/thermal review.
4. **Verify saved bytes and violation sets.** Compare source, symbol pins,
   pad nets, MPNs, refdes, UUIDs and saved copper against the approved delta.
   Refill with matching rules/libraries, run full ERC and at least three
   DRC checks with all-track-errors and schematic parity, compare normalized
   violation sets and connected pad clusters. Resolve the 36 footprint
   mismatches against intended supplier lands; repair three silk overlaps.
   Explicitly disposition the R5 internal Kelvin connection without adding
   a bypass. Recheck insulation barrier, stackup, PTH annuli, power sections,
   creepage/clearance rule basis and model collisions after each native edit.
5. **Release one matched prototype pack.** Only after those checks, produce
   board STEP, Gerber/drill, assembly drawings, BOM and placement files from
   the exact same board/source hash. Include stackup/material tolerances,
   controlled alternates, terminal assembly/torque process, probe map and
   the manufacturing worker's inspection/test traveler. Supplier review
   must confirm the actual material, finished copper/plating and assembly
   process; a generated file's existence is not acceptance.
6. **Close the hardware gates on built samples.** Establish startup inhibit
   throughout the supervisor's validity delay; inject independent HOT5 loss
   while V15_LS remains; capture full fault-to-current-extinction timing and
   verify latch/restart behavior. Test controller supply/harness faults,
   complete OCP/OVP/CT behavior and shorted-device upstream interruption.
   Validate losses/temperature, insulation and earthing construction,
   leakage, EMI and mechanical abuse under the agreed product basis. The
   [TPS3700 datasheet](https://www.ti.com/lit/ds/symlink/tps3700.pdf) does not
   bound the complete appliance shutdown chain. No physical result exists
   in this packet.

This order allows a safe digital HOT5 integration once the interface revision
is fixed. It does not require waiting for every production qualification test
before drawing a board; it does prevent buying an ostensibly final assembly
whose controller, heat path and protection envelope are still incompatible.
