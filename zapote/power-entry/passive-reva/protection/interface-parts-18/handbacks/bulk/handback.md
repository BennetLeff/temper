# C4 bulk capacitor screen — interface-integration-17

## Result

`Rubycon 50ZLJ220M10X16` is a concrete **prototype candidate**, not a fully
qualified production selection. It meets the 220 µF / 50 V target, has a
manufacturer low-impedance/high-ripple series, and is active/in stock. It
passes the initial-tolerance 300 µF screen under the revision-17 hypothetical
ceramic maximum, but it does **not** pass a conservative end-of-life screen
that combines Rubycon's specified initial ±20% tolerance with its specified
endurance capacitance change (±25% of initial value).

No CAD or schematic files were changed. This handback is the only output owned
by this worker.

## Evidence

PCBParts `jlc_search` (Capacitors → Aluminum Electrolytic Capacitors—Leaded,
subcategory 2931; query 220uF, voltage ≥50 V; stock ≥10) returned many radial
parts. Representative fields are preserved in `raw-mcp.json`. JLC data is a
stock/package search, not sufficient proof of ESR, lifetime, or full-corner
capacitance.

The exact candidate was cross-referenced through PCBParts:

- DigiKey MPN `50ZLJ220M10X16`, PN `1189-1433-ND`, stock 2049, lifecycle data
  active; [DigiKey record](https://www.digikey.com/en/products/detail/rubycon/50ZLJ220M10X16/3134389).
- Mouser PN `232-50ZLJ220M10X16`, stock 2621; [Mouser record](https://www.mouser.ca/en/ProductDetail/Rubycon/50ZLJ220M10X16).
- Rubycon ZLJ datasheet (rev/source retrieved 2026-09-22):
  [manufacturer PDF](https://www.rubycon.co.jp/wp-content/uploads/catalog-aluminum/ZLJ.pdf).

Rubycon ZLJ datasheet pages (PDF page numbers):

- p1: category temperature −40…+105 °C; capacitance tolerance ±20% at 20 °C,
  120 Hz; low-temperature impedance ratio Z(−40)/Z(+20) ≤3 for 50 V;
  endurance test at 105 °C with rated voltage+ripple; post-test capacitance
  change within ±25% of initial value. For 10×16 mm at 10–50 V, endurance is
  9000 h (the table distinguishes 10×16/10×20/10×25 from smaller cases).
- p2: 50 V, 220 µF, 10×16 mm standard size: rated ripple 1650 mA rms at
  105 °C/100 kHz and maximum impedance 0.053 Ω. The DigiKey record additionally
  reports 825 mA at 120 Hz and 53 mΩ impedance.
- p1/p2: radial lead part number is 50ZLJ220M10X16; nominal lead spacing 5 mm.
  DigiKey lists maximum seated height 17.50 mm and diameter 10.00 mm. The JLC
  package string (`D10xL16`) is shorter than DigiKey's 17.5 mm max height;
  resolve the mechanical drawing before assigning a KiCad footprint.

## Electrical bounding

Known downstream ceramic nominal sum is 12.1 µF. Revision-17's conservative
hypothetical +20% ceramic screen gives:

```
Cceramic,max = 12.1 × 1.20 = 14.52 µF
10×Cceramic,max = 145.2 µF
```

For the Rubycon 220 µF part, the datasheet's separate initial tolerance gives
`C_initial,min = 220×0.80 = 176 µF` and `C_initial,max = 220×1.20 = 264 µF`.
Therefore the initial screen passes both the LT4363 ratio floor (176 ≥ 145.2)
and the 300 µF total allocation (264 + 14.52 = 278.52 µF).

The same datasheet separately specifies endurance capacitance change of ±25%
of the initial value after the stated 105 °C test. If the design treats this as
an independent end-of-life bound, the conservative compounded bounds are
`C_EOL,min = 176×0.75 = 132 µF` and `C_EOL,max = 264×1.25 = 330 µF`.
That fails the ratio floor (132 < 145.2) and the total cap ceiling (330 +
14.52 = 344.52 µF > 300). This is a documented procurement/requirements
conflict, not evidence that the part is defective. Do not silently multiply
factors in the schematic; the manufacturer does explicitly provide both
initial tolerance and endurance change, so they must be reviewed together by
the system owner.

For reference, using only the initial tolerance (without EOL drift) leaves
`220 µF` inside the existing 181.5–237.9 µF initial-only nominal window from
revision 17. No claim is made for capacitance versus DC bias; this is an
aluminum electrolytic part and the relevant manufacturer controls are ripple,
temperature, impedance, and endurance rather than MLCC DC-bias curves.

## Candidate status and next decision

**Candidate, initial-screen pass; production qualification open.** Before
adoption, confirm the actual bypass component tolerances (rather than the
revision-17 +20% hypothetical), define whether the 300 µF ceiling is an
initial or end-of-life requirement, and check the LT4363 ripple/current waveform
against the 825 mA/120 Hz and 1.65 A/100 kHz ratings with temperature derating.
Resolve the 10×16 mm radial footprint, 5 mm pitch, 17.5 mm maximum height, and
polarity/clearance on the PCB.

If the 300 µF limit and full independent EOL bounds remain mandatory, the
current 220 µF nominal target has no feasible point under this candidate's
separate ±20% and ±25% data: raising nominal value fixes the lower bound but
raises the upper bound faster. Revisit the allocation together with the
ceramic maximum and required LT4363 minimum; do not automatically increase C4.
