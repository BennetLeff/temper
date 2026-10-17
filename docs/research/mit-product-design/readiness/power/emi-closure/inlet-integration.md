# Protected inlet proposal — not released hardware

**Observed gap:** the current power-section path is `J1.1 L → F1 → original L1`. D22 adds a module before J1 and assumes an upstream fuse/disconnect. Existing board F1 cannot interrupt a short upstream of itself. The filter must not be energized as an unfused addition. This proposal supplies that missing construction without changing the current 15 A input basis or deleting F1.

```text
fixed grounded cord L → F_IN + enclosed holder → S_IN line pole → D22 L input → J1.1 → existing F1
fixed grounded cord N ─────────────────────────→ S_IN neutral pole → D22 N input → J1.2
fixed grounded cord PE → dedicated chassis bond → filter Y returns / other required bonds
```

PE is neither fused nor switched. The line fuse precedes both the filter and line switch contact. The two switch poles interrupt L and N together; the selected breaker's one thermally protected pole is wired in L. Preserve F1 pending coordination review; the two series fuses do not promise selective clearing. Unplugging remains the service isolation procedure; an OFF rocker does not authorize touching upstream terminals.

## Exact electrical candidates

| Function | Candidate | Verified rating and qualification limit |
| --- | --- | --- |
| F_IN | Littelfuse **KLDR020.TXP** | 20 A time-delay Class CC, 600 VAC, 200 kA AC interrupting rating; body 38.1×Ø10.3 mm. This rating covers the 140 V corner without borrowing a 125 V rating. |
| Fuseholder | Littelfuse **LPSC0001Z**, catalog LPSC001 | Matched Class CC, 30 A, 600 V AC/DC, 200 kA with Class CC fuse; 35 mm DIN rail. Rev B drawing: 78.5±0.5×17.78±0.25 mm, 61 mm maximum closed depth; 80 mm maximum open-door projection. Copper wire only: #14–8 AWG stranded UL Class B/C or #14–10 solid; suggested terminal torque 2 N·m. |
| S_IN | Schurter **4435.0002**, TA35-CBTWF200C0-000 | 20 A, two poles, one bimetal, nonilluminated rocker; 240 VAC IEC/277 VAC UL/CSA; −30…60°C. Supplemental thermal breaker used here for switching plus supplemental overload response; no magnetic release and no independent branch-circuit protection credit. |

Manufacturer basis: [KLDR datasheet pp. 1, 4–5](https://www.littelfuse.com/assetdocs/kldr-classcc-fuse-datasheet-final?assetguid=8f8c3052-d0e1-411d-9a86-62bff0e1cf9a), [LPSC ordering/rating catalog p. 19](https://www.littelfuse.com/~/media/files/littelfuse/technical-resources/documents/product-catalogs/littelfuse_solar_fuse_catalog.pdf), [current LPSC001 outline revision B](https://www.littelfuse.com/assetdocs/lpsc001-2d-print-pdf?assetguid=e0be2d74-f59f-4582-85a5-d5c636a5de64), [Schurter selected part and drawings](https://www.schurter.com/en/part/4435.0002). Use the Class CC rejection holder; a generic 10×38 mm midget holder is not this matched selection. Do not substitute unapproved fine-stranded appliance wire directly into the holder's terminals.

**Selection decision:** the board's 0326020.MXP has 400 A interrupting at 250 VAC and 10 kA at 125 VAC, with approval-specific exceptions. That is an inadequate basis for an unknown prospective fault current at the 140 V test corner. The proposed upstream pair therefore uses the 600 VAC / 200 kA Class CC family, rather than inventing a 400 A test-source bound. Existing board F1 is not silently replaced; its series coordination must be reviewed. [326 manufacturer data, p. 2](https://www.littelfuse.com/assetdocs/littelfuse-fuse-325-326-datasheet?assetguid=ae3ab906-06ef-423d-ac90-3af4e021e2e1).

This closes the upstream fuse/holder breaking-capacity selection gap. It does **not** assign a 200 kA rating to the complete appliance. Obtain prospective fault current and verify every intervening connection/part and the assembly rating. The TA35's 2 kA conditional figure requires its specified upstream coordination and is not automatically granted by the Class CC fuse. The fuseholder is not a load-break disconnect: open it only after unplugging and verifying absence of energy.

**Twenty amperes is a coordination candidate, not a fifteen-ampere limit.** Normal input remains ≤15 A. Validate the fuse's temperature/current derating, repetitive inrush and the rocker thermal response at the actual local ambient. A 20 A fuse does not automatically protect a 15 A cord, inlet, terminal or module. At 200% current the KLDR specification permits at least 12 s before opening: 40²×12 = **19,200 A²s minimum** for a sustained 40 A overload. The table's **1,363 A²s total clearing at 200 kA** is a different test condition; it cannot be applied to all lower fault currents. Require maximum clearing-time/let-through curves across actual prospective currents and compare them with conductor, choke, carrier, terminal, switch and capacitor fault withstand. Nominal/pre-arcing data cannot substitute for total clearing. Neither fuse nor rocker replaces semiconductor overcurrent protection.

Fuse, holder, switch and added terminal hot losses are **not inside the filter's 8 W allowance** and remain to be bounded from selected-part voltage-drop data and a thermal test. No cold resistance from the old 326 part is transferred to KLDR. Preserve the 15 A operating allocation until the thermal/current and fault coordination are established; do not increase fuse current to cure inrush without repeating those checks.

## Procurement evidence and missing mechanical inputs

Retrieved 2026-10-04; web pages may be cached and stock is not reserved. Direct distributor listings showed **222 KLDR020.TXP fuses**, **1,051 LPSC0001Z holders**, and **4 Schurter rockers**: [fuse](https://www.digikey.com/en/products/detail/littelfuse-inc/KLDR020-TXP/3740830), [holder](https://www.mouser.com/en/ProductDetail/Littelfuse/LPSC0001Z?qs=gu7KAQ731UTaa%2FsFry13Yw%3D%3D), [rocker](https://www.digikey.com/en/products/detail/schurter-inc/4435-0002/1576903). Reconfirm availability/price when quoting the prototype cohort. No contact or order has been made; seller data is used only for availability.

The proposal retains the fixed-cord architecture. The exact cord/gland construction and panel cutouts cannot yet be frozen because the current cooling reservation omits:

- Rear/side panel selected for the entries; its exact thickness, coordinates, nearby bends, service access and whether liquid can reach the openings. Dead-front construction does not establish liquid ingress protection.
- Cord assembly rating/market plug, conductor cross section, insulation temperature and outer diameter; these determine the approved strain-relief/gland and crimp family. Use a mains-rated grounded cord and listed insulation/terminals matched to actual wire; no low-voltage harness substitution.
- DIN-rail/holder orientation and rocker cutout, terminal barriers, mating connectors and minimum bend radius. Reserve the holder’s full opening/service sweep and rail/terminal space separately; do not fit its 61 mm depth into a 50 mm filter-height allowance without an explicit rotated assembly study. Import manufacturer drawings before cutting; the filter's 110×80×50 mm box does not contain these parts.
- Applicable insulation coordination (working/impulse voltage, pollution, material group, altitude and accessible-metal boundary). No invented universal spacing is assigned. Freeze numerical creepage/clearance rules and inspect the real carrier/harness against them.
- A dedicated PE stud/contact construction with torque, coating removal, anti-loosening, conductor retention and bond-test access. PE wiring must remain secure under cord-pull and service loads, without relying on a removable functional mounting screw.

Before a powered build, the electrical owner must sign the as-wired netlist and protection coordination; the mechanical owner must release the panel/terminal/cord drawing and barrier inspection. A guarded external fused test fixture can be designed as a separate test article if these enclosure inputs are not yet available; its protection must cover the module from its first energized lead and meet the same fault-current/inrush constraints.
