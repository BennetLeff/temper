# R4 engineering notes

## Exterior and assembly

The aluminum front is one formed sheet. Cut the window and three button holes before
bending using the shared source features for both formed and developed geometry.
The sheet retains a continuous bridge between window and buttons. Finish/flatness around
these cuts is a critical supplier review item; the K-factor is still provisional.

Bond the rear lens support ring to the sheet and lens using a common exterior datum jig.
The jig holds the outward glass face flush with the local aluminum surface during cure.
Measure actual sheet/glass thickness and bondline variation; CAD nominal0.3mm is not a
production tolerance or a specified adhesive. Select primers, surface preparation and
an adhesive compatible with the actual metal finish and glass. Fill the0.4mm edge joint
flush with a compatible flexible seal. Inspect continuous wetting/voids and perimeter
profile; avoid a recessed bead that collects oil.

The ring supports inward loads. It does NOT mechanically capture the glass outward.
Specify and test the outward pull/peel load after heat, oil, cleaners, humidity and thermal
cycling. If that bond cannot be qualified, revise concealed retention rather than claiming
rear support alone is sufficient. A glass replacement is a debond/rebond operation.

Use six concealed bonded stud pads to locate the removable electronics carrier. The
modeled10mm pads have0.3mm adhesive layers,1.7mm bases and0.5mm spacers. These are design
allocations, not selected catalog parts. Bond strength/peel/creep must support handling,
button presses and servicing. No stud penetrates the exterior surface. Alternate welded
studs would require supplier trials for finish marking and heat distortion.

Assemble button membrane from inside, place carrier on studs, fit washers/nuts, and verify
compression and switch gap. Individual M2 blind holes are extended into the carrier plate
so modeled screw tips do not collide with solid material. Actual tapped/insert geometry,
thread engagement strength and torque require the selected carrier material.

Carrier removal releases membrane compression. The lens/ring stays with the enclosure.
The exploded view shows inspection offsets, not a validated assembly sequence or animation.
The cropped front-face piece in the detail view is visualization context from the actual
formed cover; it is not a separate product faceplate.

## Controls

Rotate: adjust highlighted temperature/time/power or navigate.
Back: cancel unconfirmed menu edits/go up one level, without changing heating.
Select/Start: confirm a selection; starting a stopped program requires an explicit action.
Stop: request heat off from every screen and stop automatic program progression. Necessary
cooldown and residual-heat indication continue. No automatic restart after stop/fault/power
restoration. These are design rules only: firmware is unchanged, knob click remains open.

## What to test before claiming heat/liquid robustness

- Lens bond and concealed stud bonds: hot pull/peel, creep under button/handling loads,
  temperature cycling, actual oil and detergent exposure, and aged re-test.
- Perimeter seal: voids, adhesion, expansion mismatch, wipe abrasion and oil/flour cleaning.
- Membrane: exact compound compatibility, compression set, off-axis and gloved presses,
  return, switch travel, overtravel, fatigue and leakage after cycling.
- Thermal mule: measure module front/rear/driver, glass, bondline, carrier, sheet and
  internal air during normal heat soak, pan overhang, blocked inlet, fan stall and cooldown.
- Initial module temperature design target65C is proposed, not achieved. The candidate
  Newhaven OLED is specified -40..85C operating; its3.3V/340mA full-on condition is about
  1.12W electrical input. Include other electronics and external heat soak. The closed
  housing can trap heat; no thermal benefit is credited just for sealing it.
- Begin water/hot-oil spill and retention trials on de-energized coupons. Appliance-level
  energized testing needs a controlled safety setup. A panel result does not qualify the
  fan vents, pan sensor, probe port, mains inlet, service hatch or complete cooker.

The inherited PCB-compartment clash is closed for nominal R4 geometry by a shallow
folded front roof that joins the existing lid at y=100mm and keeps a full-height side
and front barrier below it. The front controls and their removable lid were not moved.
This is a protected-volume allocation, not an insulation, ingress, joining, airflow,
or manufacturing result. Test the front fold/seam, tool access and leak path on hardware.
The current full-bridge board and sink require a separate integrated compartment review.

## DFM review scope

| Feature | Current definition | Status / next evidence |
| --- | --- | --- |
| Main front | 2mm formed sheet, lens and3button cuts | Shared formed/flat features; shop alloy/temper, bend table, cut/finish/flatness review required |
| Lens ring | Flat1.2mm plate, rounded aperture | Provisional cut DXF; thickness/flatness and bonding-process review |
| Glass |108x38x2, R4 corners| Supplier edge finish, glass grade/strengthening and thermal-shock/impact trials |
| Internal carrier | Machined-polymer or cold-print prototype geometry | Material, wall/tool access, inserts and heat/creep/flame behavior unqualified |
| Membrane | One piece with3flush domes | Process/material tooling trial; no force/strain simulation |
| Stud pads / adhesive | Concealed10mm bases | Supplier selection and hot/aged retention trials |

Measurements are nominal geometry; no universal supplier limits are inferred.
CAD/DFM skills: earthtojake/text-to-cad commit7b675ccb1edec68a2fb228043d8fb9772ff93094.
Display source: https://newhavendisplay.com/content/specs/NHD-3.12-25664UCW2.pdf
Drawing rev7(2024-08-25) retained in evidence. STEP Parts catalog had no model; mounting
outline is dimension-derived and component/header subdivisions remain allocations.
