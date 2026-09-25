# C3 gate-timing capacitor search handback

## Requirement used

- Nominal 1.5 uF, minimum 63 V (higher voltage is acceptable).
- Effective capacitance target: 1.35--1.65 uF over the provisional -40 to +105 C range.
- Prefer polypropylene film, radial through-hole, and tolerance no worse than 5%; larger packages are allowed.

## PCBParts MCP results

The Film Capacitors subcategory is ID 3244. KEMET exact 1.5 uF / >=63 V / <=5% search returned only:

- `R82DC4150AA60J`, LCSC `C6262911`, 63 V, PET, ±5%, P=5 mm, stock 40. This is the previously rejected PET candidate.
- `R60EF4150506AK`, LCSC `C3767107`, 100 V, PET, ±10%, P=10 mm, stock 119. Rejected on tolerance/material.

PCBParts `jlc_get_part` found no exact R76 1.5 uF part, so no LCSC number is claimed for the recommended R76 candidate. The JLC database does show the KEMET R75/R76 families, but only other capacitance values.

Raw MCP search calls/results were performed through `mcp__pcbparts__jlc_search_help`, `jlc_search`, `jlc_get_part`, `cse_search`, `mouser_get_part`, and `digikey_get_part` on 2026-09-22. The distributor lookups returned no exact stock record; this is not evidence that the part is unavailable through KEMET distribution.

## Recommended prototype candidate

`R76IN4150SE30H` (KEMET R76 family; verify ordering suffix with distributor before release)

- 1.5 uF, 250 VDC / 180 VAC, polypropylene, radial, ±2.5% (`H`).
- 22.5 mm lead spacing (`N`), short leads 4 mm (`SE`), internal suffix `30`; the datasheet row is `76IN4150(1)30(2)`.
- Body dimensions from the 250 V / 1.5 uF row: T=14.5 mm, H=29.5 mm, L=26.5 mm; lead diameter 0.8 mm. The 22.5 mm pitch has ±0.4 mm nominal tolerance.
- Electrical row: dV/dt 300 V/us, peak current 450 A, ESL 16 nH, ESR max 3.7 mOhm at 100 kHz, Irms 14.1 A at 85 C, thermal resistance 27 C/W.
- The R76 datasheet specifies -55 to +110 C operation, -200 +/-100 ppm/C temperature coefficient at 1 kHz, <=0.5% capacitance drift after two years' storage, and >200,000 h operational life at 85 C. Endurance qualification is 1.25 x VR at 85 C for 2,000 h, with |delta C/C| <=3%.
- This is a large 22.5 mm radial package and needs a dedicated footprint/clearance review. It is not a drop-in replacement for the 5 mm placeholder.

## Requirement arithmetic

Using the catalog limits conservatively: 1.5 uF nominal, ±2.5% initial tolerance, temperature coefficient worst magnitude 300 ppm/C, 0.5% storage drift, and ±3% endurance drift:

- Cold-side maximum at -40 C: 1.5 x 1.025 x (1 + 0.0003 x 60) x 1.005 x 1.03 = about 1.613 uF.
- Hot-side minimum at +105 C: 1.5 x 0.975 x (1 - 0.0003 x 85) x (1 - 0.005) x (1 - 0.03) = about 1.377 uF.

Both remain inside 1.35--1.65 uF if these independent catalog limits are allowed to stack. A ±5% version would have a much smaller high-side margin once ±3% endurance and storage are stacked; use ±2.5% unless procurement proves the tighter suffix unavailable.

## Datasheet sources

- Official KEMET R76 datasheet (3/21/2025): https://content.kemet.com/datasheets/KEM_F3034_R76.pdf
- Official KEMET R75 datasheet (4/7/2025): https://content.kemet.com/datasheets/KEM_F3106_R75.pdf
- R76 exact 1.5 uF table row is also indexed at the official source: https://content.kemet.com/datasheets/KEM_F3034_R76.pdf

## Release blockers / gaps

- Confirm the complete customer MPN and distributor stock; PCBParts did not return an LCSC listing for `R76IN4150SE30H`.
- Verify the actual measured operating-temperature envelope and ripple/pulse waveform. The datasheet ratings are not a substitute for the LT4363 gate-drive transient qualification.
- Add the 22.5 mm radial footprint and mechanical keepouts only after parent approves the package choice. No shared CAD files were edited.
