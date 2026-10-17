# Cooling module assembly and retention

## Datums and load paths

Use the actual device rear contact planes as the thermal datum A, a removable board-top gauge as datum B, and the left PCB outline as lateral datum C. The fixed sink must not pull already-soldered packages to a nominal common plane. Check package backs/board seating in a dry fixture first; fit the bridge land or individual interface stack to the measured plane. The model's 0.685 mm bridge step is only the provisional-box difference.

The sink and PCB need independent chassis retention. Device leads do not support the sink/fan mass. A four-point insulated carrier frame is the intended cold prototype approach: two fixed edge shoes define the left board edge, opposite shoes float laterally for thermal growth, and one longitudinal stop locates the front/rear axis. Top retainers capture the board without using clamping pressure to flatten it. Use replaceable electrically insulating shoes; choose their exact material/grade and creepage after the insulation review. Do not claim a generic printed plastic is a high-voltage barrier.

The modeled contact windows are board X=0..3 mm at Y=17..23 and 137..143 mm, and X=237..240 mm at Y=17..23 and 77..83 mm. The native PCB owner screened those complete rectangles against pads, track bounds and filled copper. The former right Y=137..143 mm proposal was rejected because it touches `res_a`. The current screen has zero extra clearance and is pending the final native-19 refill; it is not an electrical-distance or component-height qualification. No PCB holes or mounting footprints were added. The present CAD also checks the shoes against the native-18 component solids.

Each lower shoe is a custom machined PEEK candidate with a separate removable top cap. Its 3 × 6 mm underside lip supports the board at Z=30.347. Two left posts define X; the right posts sit 1.0 mm outside the nominal board edge so they do not become opposing hard stops. An arm from the left-front shoe ends at a front stop at Y=162. The left-rear arm ends at Y=323, leaving 1.0 mm rearward travel after the nominal board end at Y=322. Corner stop strips X=0..3, Y=0..1 and 159..160 mm require the PCB owner's final copper screen as well. The top caps are at Z=32.1, giving only 0.1 mm nominal capture gap; they must not press a real warped/thicker board flat.

The four M3 × 25 fasteners and 1.5 mm spacers are outside the board. The model includes Ø3.4 mm shoe/cap holes and Ø2.5 mm rail pilots; the rail pilots require finished M3 threads. Fastener envelopes are not a torque or thread-strength specification. Two 12 × 160 × 6 mm carrier rails stand on the existing floor at Z=10. **Their chassis attachment is still open**; contact with the floor is not retention. The right-rear shoe is at Y=80 in board coordinates, leaving a long rear overhang that needs deflection/handling verification. PEEK grade, creep, temperature capability, flammability and electrical-distance suitability remain selection inputs.

Accept the minimum measured float only if, separately for X and Y:

`available float_min >= max(0, α_PCB × L × ΔT_PCB − α_frame × L × ΔT_frame) + worst-case size/location stack + service deflection allowance`.

Use the actual material CTEs, PCB and frame temperatures, and signed datum stack; do not assume both parts are at the same temperature. The 1 mm value is a nominal allocation, not a derived growth requirement. Verify that the minimum remaining lip overlap supports the board at both travel extremes. In Z, minimum cap clearance must exceed the maximum board thickness/warp and shoe/rail height stack; maximum clearance must still prevent release during handling. The present 0.1 mm gap is therefore a cold adjustable-gauge target, not a production tolerance. No retention part may require deflecting a populated board or a soldered lead to fit.

A contact plane measured on one package must not consume the full assembly variation budget. Nominal solid clearance does not prove the board remains located after heating, transport or repeated service.

## Drawing-derived contact range

[Contact tolerance arithmetic](../../../../../../zapote/power-stage-120v/prototype-closure/cooling/contact-tolerances.json) uses the actual manufacturer side views, straight lead centerlines at the saved footprint positions and the flat backs facing the sink. A1/P measure from the rear face to the **near lead edge**. Add half the lead thickness to that distance to reach the centerline, then subtract the whole distance from the board lead-center Y. The independent reviewer and parent visually confirmed this interpretation; seating and forming variations remain additional. The initial opposite signs are withdrawn in the [drawing erratum](contact-plane-erratum.md).

| Interface | Formula, local board Y | Worst-case interval |
| --- | --- | --- |
| Four IPW65R018CFD7 backs | 4.215 − A1 − c/2 | 1.170..1.825 mm |
| GBJ2510 flat back | 4.6 − P − R/2 | 1.300..1.800 mm |
| Bridge minus MOS plane | Difference of independent bounds | −0.525..+0.630 mm |
| Bridge back minus fixed model interface | Actual back minus 2.200 mm | −0.900..−0.400 mm |

The library MOS back at 1.515 mm is **inside** the corrected drawing interval. Relative to its fixed 1 mm ceramic interface, the actual straight-lead rear plane has a signed difference of −0.345..+0.310 mm: the negative end is interference and the positive end is a gap. The former claim of an inevitable positive gap was wrong and is withdrawn. Neither zero nominal gap nor inclusion in the interval establishes simultaneous seating of four real devices. A compound film cannot be presumed to absorb the variation while preserving the contact budget. The bridge’s signed difference from its modeled interface at 2.200 mm is −0.900..−0.400 mm, indicating interference across this entire straight-lead interval. The common rigid pair tiles and fixed 0.685 mm raised bridge land are **not ready to machine for real power packages**. A positive-volume collision pass against the generic models cannot fix that.

For the first contact fixture, make the thermal datum adjustable and measure every device's rear plane with its leads seated freely in the actual board. Establish one approved method: manufacturer-permitted lead forming before soldering against a common rear-face gauge, or individually fitted contact lands/insulating interfaces with their additional thermal joints included. Never use the final clamp to drag soldered leads into position. Common pair ceramics require coplanar mating surfaces; varying package backs cannot be accommodated by simply tightening each clamp harder. The exact product drawing need not wait for vendor CAD if these drawing datums and an assembly method can be independently verified, but the current generic STEP is not that verification.

## First cold assembly sequence

1. Inspect sink machining, flatness, ceramic condition and exact packages. Confirm the manufacturer's metal-face and clamp positions; record the physical dimensions that replace the generic/provisional model datums.
2. Fit the devices, insulators and independent clamps to the sink in a fixture that supports the PCB at its actual top datum. Use a manufacturer-approved compound application process; examine a sacrificial disassembly for contact coverage. Measure loaded clamp force/deflection. Do not transfer a catalog normal-force label to a custom rail without that measurement.
3. With no electrical power, insert the real PCB without bending leads to meet it. Confirm each lead is free before soldering. Fit the independent insulated board carrier and sink brackets. Remove the positioning fixture only after retention is proven.
4. Add the selected fan and actual guards. Trial-fit the removable duct and wiring, including the EMI module, its upstream fuse/holder/rocker and dedicated fan supply. The current STEP includes only the EMI body allocation and top duct plate; those remaining items require a new measured fit check.
5. Remove/reinstall clamps with the coil support lifted. The clip anchor rail is Z64..70 beneath a support underside near Z85; this is not enough for an ordinary long driver from above with the coil installed. Record the actual pliers/driver sweep and cable disconnection sequence. A screw-mount alternative should be tightened in the module fixture before installation and have a planned service-removal path.
6. Run continuity/insulation and PE-bond inspection on the completed construction using the electrical authority's method before any powered test. Record torque/force process, part lot, interface replacement rule and inspection photographs. The chassis bond is separate from insulated semiconductor fasteners.

## Known missing hardware, without hiding it in the fit count

- The new PCB chamber/barrier is required; deleting the old chamber from a study does not eliminate its protective function.
- Native-19 HOT5 parts and its final source/native identity need an updated populated inventory and fit replay.
- The latest inlet protection proposal uses a Littelfuse LPSC0001Z Class CC holder, closed 78.5 × 17.78 × 61 mm and a larger opened-door/service envelope. It is **additional** to the 110 × 80 × 50 mm filter body and cannot be squeezed into that allocation. See the electrical worker's candidate/protection evidence before selecting panel position.
- Complete fan brackets/guards, inlet and exhaust bends, strain reliefs, fan control/tach wiring, temperature sensors and controller PCB remain to be drawn and checked.
- The external bench fan adapter is useful for first characterization, but it is not an integrated supply selection for a finished self-contained cooker.

No physical fitting or load test was performed. This document preserves the assembly dependencies so a collision-free rendering cannot be mistaken for a build release.
