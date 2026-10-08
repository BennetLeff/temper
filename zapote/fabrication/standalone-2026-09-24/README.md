# Standalone PCB prototype fabrication review — 2026-09-24

**Disposition: review packages prepared; fabrication and assembly release held.**
These are five separate sensor/protection/drive boards, not an integrated cooker
PCB. No boards or parts were ordered, built, or energized. The exported Gerbers
are for fabricator DFM and prototype planning until the items below are closed.

The source of each package is the saved `candidate/section.kicad_pcb` and
matching schematic in the board's directory. `manifest.json` pins their SHA-256
identities and every generated artifact. `regenerate.sh` records the KiCad
commands and deliberately does not save zone-refilled source boards.

| Board | Outline | Stackup declared in board | Installed BOM refs | Fresh ERC / DRC / opens / parity | Package |
| --- | ---: | --- | ---: | --- | --- |
| RTD | 60.1 × 60.1 mm | 4 Cu × 0.035 mm; 0.20 / 1.04 / 0.20 mm dielectric; 1.60 mm nominal | 36 | 0 / 0 / 0 / 0 | [`rtd/`](rtd/) |
| Current sense | 80.05 × 83.05 mm | 2 Cu × 0.070 mm; 1.44 mm core; 1.60 mm nominal | 21 | 0 / 0 / 0 / 0 | [`current/`](current/) |
| Thermal sense Rev B | 100.1 × 45.1 mm | 2 Cu × 0.070 mm; 1.44 mm core; 1.60 mm nominal | 27 | 0 / 0 / 0 / 0 | [`thermal/`](thermal/) |
| Interlock Rev A | 100.1 × 65.1 mm | 2 Cu × 0.070 mm; 1.44 mm core; 1.60 mm nominal | 25 | 0 / 0 / 0 / 0 | [`interlock/`](interlock/) |
| Gate drive Rev A | 100.1 × 80.1 mm | 2 Cu × 0.070 mm; 1.44 mm core; 1.60 mm nominal | 20 | 0 / 0 / 0 / 0 | [`gate/`](gate/) |

All five use 0.01 mm mask layers in the saved stackup. KiCad 10.0.4 ERC and
DRC were rerun on 2026-09-24 with warnings and errors included, all track
errors, schematic parity, and in-memory zone refill. Every report has zero
included findings. The saved Rust `stackup_check` executable passed on all
five saved boards with the nominal total matching 1.60 mm. The executable is
the frozen artifact at `zapote/current-sense/evidence/acceptance-stackup-v2/stackup_check`;
fresh Cargo rebuild was unavailable because the host could not resolve
`static.crates.io`. Its SHA-256 is in the manifest. This is a stackup syntax
and arithmetic gate, not a fabricator's laminate certificate.

## Fabrication output inspection

Each board folder contains copper, mask, paste, silk, fab and edge Gerbers,
Excellon drill data, a drill report, a native KiCad BOM and position CSV,
the native check reports, and a top 3D render. RTD additionally has its two
inner copper Gerbers. PyGerber 2.4.3 rendered top and bottom Gerber composites
for all five, and both RTD inner copper layers; these PNGs were visually
inspected. Board outlines, exposed pads, major keepouts, connector legends,
the current-transformer primary lands, and the gate-drive split copper were
present as expected. No obvious missing layer, outline break, or stray copper
was seen at this review scale. This visual check cannot establish all copper
clearances, plating quality, or assembled insulation; KiCad DRC covers the
authored board rules only. The drill reports show plated holes and no NPTH
holes; there are 69 / 34 / 54 / 151 / 31 drill hits in table order.

`footprint-audit.json` in each folder compares every PCB reference, footprint
ID and value against the fresh KiCad BOM. All 129 references match and all
have assigned footprints. RTD J2/U6 and current-sense J1/T1 have no 3D model;
current-sense J1 (bare solder lands, not a purchased connector) has no
courtyard. These are review limitations, not unexplained source mismatches.
The existing [CST3015 land-pattern review](../../current-sense/evidence/cst3015-footprint-review.md)
checks T1 against Coilcraft's recommended copper lands. The existing
[RTD custom-footprint receipt](../../rtd/circuit/footprint_receipt.txt)
checks J2 and U6 pad geometry but leaves final J2 body keepout and host
orientation for mechanical signoff. The [gate-drive 3D model note](../../gate-drive/models/README.md)
labels its UCC21550 model approximate and unsuitable for mechanical approval.

## Assembly BOM review

The native CSVs contain 129 placed references; current-sense J1 is explicitly
`NON_PURCHASED_BARE_LANDS`, so 128 are purchased placements. Their `Value`
fields carry selected MPN-like identities and their footprint fields agree
with the PCB. **All 129 native BOM rows have blank `Manufacturer`, `MPN` and
`Datasheet` fields.** These exports are inspection records, not order-ready
assembly BOMs. The existing board-specific BOM documents and source manifests
hold the exact part identities; manufacturer and authorized-channel sourcing
must be reconciled into a reviewed assembly BOM. Do not treat the current
position CSV as a vendor-specific pick-and-place file: origin, rotation and
format need the chosen assembler's signoff.

The dated procurement documents for [RTD](../../rtd/unit/bom/availability-review.md)
and [current sense](../../current-sense/bom/README.md) are historical. A spot
check on 2026-09-24 found exact `TLV3201AIDBVR` displayed as zero stock at
[DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TLV3201AIDBVR/3188691)
and [Mouser US](https://www.mouser.com/en/ProductDetail/Texas-Instruments/TLV3201AIDBVR?qs=5771e39Rz9GGuYwPEKy7fA%3D%3D).
It appears twice each on RTD, current-sense and thermal-sense. The old
`BAT54H,115` concern has changed by channel: [Mouser US](https://www.mouser.com/en/ProductDetail/Nexperia/BAT54H115?qs=me8TqzrmIYVuhJavRbr9OQ%3D%3D)
displayed stock, while [DigiKey](https://www.digikey.com/en/products/detail/nexperia-usa-inc/BAT54H-115/1127168)
displayed zero. Exact RTD reference resistor `RG2012V-431-W-T1` still lacks
an authorized stock confirmation; [DigiKey's comparison listing](https://www.digikey.com/en/products/detail/vishay/MCU08050D4300BP500/462245)
showed zero for that exact MPN. These were spot checks, not a complete
128-placement procurement audit. Stock depends on region and time; no
electrical substitution is approved by this package.

## Release items by board

- **RTD:** confirm 4-layer fabrication stackup and 0.20 mm copper minimum;
  check J2 body keepout, mating cable orientation, exact comparator and 430 Ω
  reference sourcing, and the physical RTD/fault response bench plan.
- **Current sense:** approve the insulated high-current primary land/busbar
  soldering and fixture process; inspect the T1 body envelope without a 3D
  model; qualify CT transfer, thermal and assembled isolation; source the
  exact comparator and clamp parts.
- **Thermal sense:** choose and document both off-board NTC assemblies,
  cables, mating housings and contact process; qualify thermal/open-wire
  behavior and exact comparator supply.
- **Interlock:** obtain fabricator capability confirmation for its authored
  0.15 mm clearance, and approve connector/harness keying so its two 8-pin
  headers cannot be interchanged in the appliance. Physical watchdog and
  fail-safe behavior remain unmeasured.
- **Gate drive:** replace or verify the approximate U1 package model for
  mechanical signoff; qualify isolation, bootstrap startup, loaded switching,
  timing and thermal behavior before any energized use.

For every board, the selected fabricator must review the actual copper
weight, dielectric construction, drill/plating capability, mask, and final
panel/assembly constraints against these files. The digital acceptance
records remain separate from that vendor DFM decision and from powered
hardware qualification. No fabrication order or assembled-board test is
claimed here.
