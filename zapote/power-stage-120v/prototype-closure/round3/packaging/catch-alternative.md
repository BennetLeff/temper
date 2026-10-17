# Wider catch-carrier alternative — 2026-10-04

**A wider, lower carrier can accommodate the proposed holder and capacitor body envelopes in the existing rear volume, with changed harness routing.** This is the next concrete alternative to the rejected 80 × 60 × 60 mm catch box. The design remains conditional on supplier permission to mount the holder sideways, actual leads/terminals, insulation and service qualification. It preserves the R4 exterior and D22 location.

The [declarative geometry](catch-alternative.json), [collision report](../../../../../output/temper-prototype-closure/round3/packaging/catch-alternative-checks.json) and [assembled proposal STEP](../../../../../output/temper-prototype-closure/round3/packaging/r4-catch-alternative-design-only.step) are separate from the baseline. The original round2/native19 files are untouched.

| Item | World minimum X/Y/Z, mm | Body reservation X/Y/Z, mm | Meaning |
| --- | --- | --- | --- |
| Mersen US141 / Z331153 | 17 / 348 / 12 | 107 / 76.5 / 26.5 | Rotate the manufacturer's 107 mm body length across X; the pole width becomes vertical. Mount on a dedicated vertical DIN rail/carrier, subject to supplier orientation approval. |
| TDK B32778H8476K000 candidate capacitor | 25 / 355 / 45 | 57.5 / 45 / 30 | Body on its side above the low fuse holder. Energy-team dimensions; actual lead forming and terminal reinforcement are open. |
| IDW40G65C5 diode plus carrier | 25 / 335 / 45 | 25 / 12 / 25 | Forward raised pocket. No diode thermal or pin-layout qualification. |
| Bleed / isolated-sense card | 45 / 404 / 45 | 36 / 20 / 10 | Rear raised pocket; allocation only, not the finished circuit board. |
| Fuse opening projection | 17 / 330.5 / 12 | 107 / 94 / 26.5 | Conservative filled manufacturer projection. Exact hinge sweep still needs a part model/sample. |

The low shell is 111 × 99 × 31.5 mm at [15.5,328.5,10], with 1.5 mm proposed walls. A removable front panel allows fuse access. The capacitor, diode and sense card have separate raised cover pockets: respectively 64 × 51 × 36.5, 31 × 18 × 31.5 and 42 × 26 × 17 mm starting at Z41.5. Highest point is Z78, below the nominal coil support. These are glass-laminate enclosure concepts using the same unselected material system as the PCB hood; no laminate spacing or thickness has been qualified for its insulation role. Front-panel latches/fasteners and lead exits still need real details.

The first 58 mm-wide rear sense-card reservation and its cover intersected the left exhaust duct. The revised card allocation is only 36 × 20 × 10 mm at X45; this is an explicit constraint on the actual circuit layout, not evidence that a complete isolated monitor already fits. If it cannot fit with its required spacing, a separate reviewed local card or another packaging change is necessary.

The original left wall intersected the retained PE braid. Moving the carrier 2 mm right clears that nominal intersection without moving or cutting the protective bond. The holder's closed rear edge is Y424.5. The conservative open front edge is Y330.5, leaving **3.5 mm nominal** to the PCB hood rear face Y327. This is a packaging number, not a safe distance or tolerance allowance. Remove the catch front panel before opening the holder. Supplier holder category DC20B does not permit opening it under load: isolate, verify both the main bus and separately stored catch energy discharged, then service it.

The initial broad unfiltered L/N channel at Y416..432 would overlap this wider catch module. In this variant, move the channel to **Y428..433, Z25..39**, X−140..142. Its 5 mm width is a tight corridor for individually insulated conductors, not the complete 10.92 mm cable jacket. Strip the jacket only after the internal clamp, then retain the individual wires in a closed channel; preserve separate PE and control paths. The next fixture must demonstrate actual insulated wire diameters, required bend radii, entry transition, terminal boots and assembly access. If that cannot fit, do not compress the wires to force the model: a new rear cable entrance or larger rear volume is the remaining tradeoff. The mains adapter now uses a 70 mm plate and existing X106/164 mounting centres; obsolete hardware poses were removed pending the new real bolt stack.

The nominal CAD checks compare body, cover, service projection and replacement channel against the updated retained assembly, not against a coarse box alone. They still omit the fuse terminal boots, DIN clip/support, capacitor leads, bus connection pair and finished bleed/sense board. A clean result therefore establishes available nominal space for this arrangement; it does not establish complete assembly, electrical isolation or access with manufacturing variation.

A likely carrier construction is a removable rear bracket carrying the short vertical DIN rail and a separate insulated shelf for the capacitor. Locate the bracket on the floor with one round locating hole and a transverse slot, then retain it with separate screws; do not transfer cable pull or capacitor mass through the bus studs. Exact bracket thickness, holes, captive nuts, standoffs and load/temperature creep remain to be drawn after the holder orientation is approved. No new native19 holes are assumed.

Assembly sequence: build and electrically inspect the catch carrier outside R4; install dedicated bracket/earth features if any metal is used; attach the paired bus harness at J8 BUS_P / J10 HV_RET using a qualified lug stack; install and retain the carrier; connect local sense/bleed wiring; then close the local covers, PCB hood and coil/top. The 150–220 mm approximate route to the bus region remains an extraction requirement. The new geometry does not convert that route into a low-inductance connection. First test one cold mockup for fit, holder opening, tool reach, harness retention and repeatable removal before considering a powered article.

The US141 dimensional source is [Mersen DS-PACYUS14-11-1220_EN, page 4](https://www.mersen.com/sites/default/files/medias/PIM/files/DS-Semiconductor-Modular-Fuse-Holders-UltraSafe-US14-EN.pdf), downloaded and visually inspected; SHA-256 `776c47a6781b1d82d762a827d2ceed9d7e17b15439217b9fb5dc259aa9884562`. The actual fuse/holder combination, mounting orientation and insulation construction still require component and circuit review.

Replay after the main packaging builder:

```sh
/private/tmp/temper-center-sensor-env/bin/python zapote/power-stage-120v/prototype-closure/round3/packaging/build_catch_alternative.py
```

It verifies the previously exported R4 proposal hash, constructs the declared alternative, measures intersections, exports/reimports STEP and writes the receipt. It does not claim an actual thermal, dielectric, opening-force or electrical test.
