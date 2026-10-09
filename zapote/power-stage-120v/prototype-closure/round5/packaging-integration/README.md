# Nine-board installation candidate

The inherited round2 power-board reflection was found and rejected. This candidate now imports native19 with a proper 180° Z rotation, replaces the cooling and edge-retention assembly, reroutes the catch takeoff, and recreates the sense harness. `check_power_orientation.py` checks actual exported solids against independent native/model anchors and requires the historical mirror to fail. Read the current receipts before treating an export as the completed corrected chain.

This is a digital assembly proposal for a few engineering prototypes. It installs the actual exported supervisor and eight sensor boards around the existing R4 cooker and 500 × 500 × 220 mm external protection pod. It is not a fabrication, insulation, thermal, EMC or powered-build release. Native boards, historic enclosure packages and frozen PC125-CATCH-R5-2 protection files are unchanged.

The two extra KPA/KPB contactors are the **additive protection-closure proposal**, not an assertion that the frozen circuit already contains them. The final central capture is SHA256 f307cdd9c75840c6b90c42dadd8eeb334c827fefedf520cd4b79076bdc8c9221; the geometry check fails closed if the native file subsequently changes. Read `geometry-receipt.json` and `native-capture.json` in the matching output directory for the actual inputs used.

## What changed

- Replaced the pod's small generic control-board placeholder with the populated 275 × 240 mm supervisor, mounted on a removable inner insulating panel. The capture includes the R-78B5.0 supply, TPS7A4700 regulator and final backside receiver/session circuitry. U27 uses a clearly named conservative package reservation because its native library model is absent.
- Arranged five LC1D18BD contactor reservations in one lower row; moved the three fuse holders to the right. Their 45 × 101 × 85 mm reservations contain Schneider's exact 45 × 95 × 77 mm body, with separate 25 mm terminal working zones. These are body/service allocations, not vendor terminal or DIN-clip models.
- Placed LINE/PRE voltage cards on the pod's upper-right insulating carrier and the two CT cards on a front removable carrier. Both CT bodies use the Talema drawing envelope at the native T1 pin position; their primary loops, boots and CT bore are not modeled.
- Replaced the catch sensor rectangle with the populated native card, facing inward. This is a proper rigid transform; no mirrored board. The earlier outward-facing trial hit the guard with its mating envelope. Rotating the inward-facing card 180° in its own plane puts the connector near the front and avoids both existing guard bosses.
- Mounted OUT above D22 and put TANK/BUS in a guarded front-floor tray. The initial BUS under-main-PCB trial hit a real carrier rail and floor screw; that rejected trial is preserved in `probe.json`. The front placement needs electrical validation of the longer sensing leads and is not an accepted sensing-loop design.

## Datums and installation coordinates

All dimensions are mm. Pod: X right, Y front-to-back, Z up; front door Y=0 and backplate face Y=200. R4 uses the existing enclosure datum. The STEP origin is the native board's bottom plane; the exported substrate is approximately Z=0…1.51, despite nominal stack thickness 1.6. Through-hole model leads project below it. Source and placement precision do not represent manufactured accuracy.

| Board | Origin X,Y,Z | Native X / native Y / component normal | Nominal support |
|---|---|---|---|
| Central | 30,65,260 | +X / −Z / −Y | Four 15 mm insulating standoffs to panel Y80–82 |
| LINE | 390,175,465 | +X / −Z / −Y | Three 15 mm standoffs to panel Y190–192 |
| PRE | 390,175,400 | +X / −Z / −Y | Same panel |
| IPROOF | 330,70,165 | +X / −Z / −Y | Three 10 mm standoffs to panel Y80–82 |
| ILINE | 400,70,165 | +X / −Z / −Y | Same CT panel |
| CATCH | 115,408,78 | −Y / −Z / −X | Three 3 mm standoffs to rail X118–119.5 |
| OUT | −130,410,75 | +X / −Y / +Z | Three 4 mm standoffs to tray Z69.5–71 |
| TANK | −75,82,16 | +X / −Y / +Z | Three 4 mm standoffs to tray Z10.5–12 |
| BUS | 125,45,16 | −X / +Y / +Z | Same front tray |

`installation-coordinates.json` contains every actual native mounting hole and connector pad transformed into world coordinates, including net and pin. The adapter never infers pad positions from footprint angle: pcbnew supplies their native world coordinates. The actual board outlines and component models are imported from KiCad's STEP export, not drawn as board-sized blocks.

Central mounting-hole centers are (33.5,65,256.5), (301.5,65,256.5), (33.5,65,23.5), (301.5,65,23.5), Ø3.2. Catch Ø2.7 centers become (115,391,46), (115,351,46), (115,351,75). Do not reuse the old mirrored catch mounting coordinates.

## Supports and assembly sequence

The new panels and candidate frame have explicit drill patterns and fastener stacks. Read [installation-ECO.md](installation-ECO.md) for the revised supports, candidate floor, guarded sense paths and rejected alternatives. Material qualification, tracking/flammability classification, fastening torque and hot behavior still require evidence.

1. Build and inspect the unpowered pod backplate, hot resistor plate and independent PE bonds. Retain HS400's 100 × 45 mm mounting pattern and the existing isolated cutoff-contact coupon proposal. Keep the hot zone separate from the supervisor and sensing cards. Do not credit the enclosure as a verified heatsink.
2. Install the five contactors, three fuse holders and AUX supply on qualified rails/brackets. Their CAD bodies end at the backplate; the actual DIN rail stack and clips still need vendor assembly geometry. Preserve AUX's manufacturer ventilation allocations. Route line terminals before fitting the central panel.
3. Fit LINE/PRE, then CT cards and their independently restrained insulated primary loops. CT burdens remain on their cards. Fit the central removable panel last; mate its keyed cables from the front. Contactors cannot be serviced through the installed central panel. Remove mains and stored energy, disconnect/label harnesses, then remove the panel to reach them. This is a detachable panel, not a modeled hinge or live swing-out assembly.
4. Fit the cooker front tray, BUS/TANK cards, and the separate top barrier. The tray is 225 × 61 × 1.5 at (−90,22,10.5). Four Ø3.4 proposal holes at (−86,26), (131,26), (−86,70), (131,80) retain both the tray and its four insulating tie posts. The barrier steps from Z24–25 at Y22–47 to Z43–44 at Y48–83, joined by the Y47–48 riser. The right-hand section X44–135 stays at Z43–44 for the sensor connectors; the left section steps down to clear the sloping front-control cover. The supported/routed candidate includes those floor drillings, recessed board heads, blind-threaded posts and separate top screws. The canonical floor remains unchanged; use the candidate floor export and matching hole records together.
5. Fit OUT's revised independent machined brackets, frame and 62 × 37 mm tray above D22 using the installation ECO. The frame avoids loading the filter cover or disturbing the PE route. The narrow side-slot proposal was rejected; use the bracket feet beneath the PE corridor and uprights beyond it. Catch now has three explicitly modeled M2.5 guard holes, spacers, screws and nuts. Handling loads, thread durability and material properties still need qualification. Keep CATCH_P hardware isolated from PE.
6. Install harnesses, inspect all insulation/supports, then close guards. Catch/fuse service still requires the prescribed top/hood removal and verified discharge. These new cards do not make that fuse door accessible during normal use.

The folded-aluminum and manufacturing-r2 packages are not interchangeable. This candidate uses the R4 assembly already carrying the manufacturing-r2 cooling/filter/catch arrangement. It preserves that main exterior and front controls. No successful fit is claimed for the older folded-aluminum package; transplanting this candidate there requires a separate datum/stack check.

## Harness and insulation plan

The CAD checks a 15 mm axial mate/wire working volume above each connector at its actual native pad pattern. This is an installation reservation, not an exact mating housing or bend-radius model. The final supported/routed cooker STEP adds four BUS/TANK wire and guide paths, candidate grommets and bolted guide blocks. Other harnesses remain installation reservations; source/sensor solder tails are not fully modeled or qualified.

- Pod LINE/PRE are in the rear live chamber. Run their low-voltage six-wire outputs down the right-hand segregated corridor, then forward to the central panel. Keep LINE and PRE live pairs separately identified and restrained; their crossing through an insulating panel requires an appropriate feedthrough, not a raw drilled edge.
- IPROOF/ILINE front cards keep burden/TVS local. Restrain the insulated primary lead on both sides of the CT. A PCB footprint or model body does not support a mains conductor mechanically. Wire gauge, pass count, bore clearance and bend strain still need actual harness parts.
- CATCH J2 mates inward, toward decreasing X. Its HV pads stay at the opposite card edge and require two separately restrained insulated leads from capacitor terminals. The inward plug cannot be replaced with an arbitrarily longer housing.
- OUT stays after D22. Its sense pair must originate at the filtered output; do not route a return from the pod that bypasses the physical filter boundary. Keep the unfiltered and filtered power routes apart.
- BUS/TANK have actual R32 jacket paths from the C5/C21 native takeoffs, around the retained cooling hardware, to their front sensor cards. Exact tubes, candidate wall apertures, grommets and block fasteners are checked for nominal interference. See the installation ECO and harness receipt. Termination boots, axial grip, transfer accuracy, common-mode pickup and immunity remain unqualified; a clear route is not electrical acceptance.
- Six voltage cards use 6-way XH connections with paired supply/return, differential output pair, and diagnostic/return. Cable capacitance and common-mode coupling must be checked against the amplifier load limits and the final ADC acquisition/diagnostic design. Do not select cable length from visual fit.
- Pod-to-cooker control cable, secondary-only feedthrough allocation, line output cable and protective earth remain distinct. A live sense wire is not a SELV control wire. AUX must not backfeed the cooker PS1 rail.
- Preserve separate START, RESET and supplemental hardware STOP inputs. Put their pod operator controls to the right of the central panel, e.g. centers X340/390/440 at Z240. These remain panel reservations, not drilled operators or an emergency-stop claim.

## What the checks establish

`integration-checks.json` records exact Boolean material intersection against the retained assembly, board-to-board intersections, supports against boards, and connector working reservations against retained/new parts. This is stronger than comparing outer boxes, but it is still nominal geometry. The export contains exact native-model solids and explicitly named drawing/reservation solids; absence of an omitted cable cannot constitute a clearance result.

Use `geometry-receipt.json`, `support-receipt.json`, `harness-receipt.json` and `installation-verification.json` together for the current result, not an older screenshot. The chain contains 13 placement/power/catch checks, 8 support/service checks and 10 harness checks; the verifier also checks the native takeoff hashes, bend margins and matching candidate floor. `temper-installation-review.pdf` marks itself as a pending checkpoint until that full chain and the current source hashes match. Source and output hashes are full SHA256. `capture_native.py` rejects a board changed during export. A later board ECO requires recapture and rerun before the installation is associated with that revision.

Critical unresolved stacks include the 0.5 mm tray-to-existing-floor air gap, 4 mm PCB standoffs above the trays with through-hole leads underneath, OUT bracket/filter/PE corridor tolerance stack, catch mating-to-boss margin, the front top barrier's clearance to button hardware, and pod rail/wire stack depth. Allocate real PCB/part/fabrication/assembly tolerances and verify worst-case separation before accepting them. No arbitrary millimeter value here establishes mains/reinforced insulation, accessibility, fire safety or certification.

## Reproduce

Run `capture_native.py` and `capture_pickoffs.py` with KiCad's bundled Python/pcbnew, then `build_integration.py`, `build_supports.py`, and `build_harness.py` in that order with the existing CadQuery environment. Finish with `check_power_orientation.py`, `check_floor.py`, `check_installation.py`, the installation drawings/PDF, and `write_checkpoint.py`. All generated files go only to the matching output directory. No native board, canonical housing, circuit or frozen protection source is written.

## Primary geometry references

- Schneider LC1D18BD: https://iportal.se.com/Contents/docs/SQD-LC1D18BD.PDF — exact 45 × 77 × 95 mm body; the CAD keeps the larger prior conservative envelope.
- Talema AC current-transformer drawing: https://talema.com/wp-content/uploads/datasheets/AC-1005.pdf — 23.8 × 23.8 × 11.12 mm drawing body. The placeholder intentionally lacks a qualified bore/primary wiring model.
- TI ADS131M08: https://www.ti.com/lit/ds/symlink/ads131m08.pdf — correct PBS 32-pin 5 × 5 mm body family. The missing native model is replaced only by a named 7.2 × 7.2 × 1.8 mm working reservation, not claimed vendor geometry.
- Existing round5 protection source records own the HS400, thermal cutoff, catch interposer and their manufacturer references. This work reuses their modeled mount pattern and preserves their qualification holds.

The measured front-guard mechanical gap is **1.467 mm** between the stepped high roof and the sloped user-control rear lid. `qualification-holds.json` proposes a combined 0.90 mm adverse-variation budget, leaving 0.567 mm nominal mechanical margin, but supplier capability and hot displacement are unverified. The header leads have 2.195 mm nominal distance to their new insulating trays. These numbers are mechanical distances, never insulation acceptances. The model presently omits final side closures and cable feedthroughs of the front guard; its top barrier does not establish touch protection.
