# NXP TEA2209DB1584 reference-Gerber comparison

Date: 2026-09-19  
Source archive: `source/TEA2209DB1584-GERBER-FILES.zip`  
SHA-256: `141eae8bfe37bf265f39997bc70799cb307dc791c8b7bdc8fc007313e6a80e6c`
Retained layers: `source/tea2209.gtl` (`3bb689828863b69525807367cee5c5d4ca52cddf55db6af498dca2cf53865d91`)
and `source/tea2209.gts` (`e5b3d4c4692c350b9bb65b6d1ce249af16c799f9f82c66e98ba7c78f6e52606c`).

This is a source-pattern comparison only. It is not an insulation certificate,
an NXP land-pattern recommendation, or an appliance qualification.

## Deterministic geometry found

The top-copper Gerber declares aperture D18 as
`%ADD18R,0.078740X0.024800*%`. With the file's `%MOIN*%` units, that is a
2.000 mm × 0.630 mm rectangular copper flash. The top-soldermask Gerber
declares aperture D35 as `%ADD35R,0.086740X0.032800*%`, or 2.203 mm × 0.833
mm. These are the apertures used by a repeated two-column SO16-like group in
the top-copper/mask files. The group has the 1.27 mm row pitch and approximately
5.6 mm between the two pad columns expected from the SOT109-1 outline; the
Gerber has no net names, so pin orientation and NC-pin identity cannot be
proven from this archive alone.

For comparison, the current candidate footprint uses 1.95 mm × 0.60 mm copper
pads. The NXP reference geometry is therefore **slightly wider**, not a
narrower-pad construction that would improve the generic screen. At a 1.27 mm
pitch, the nominal adjacent copper gap for a 0.630 mm row-direction dimension
is 0.640 mm (before fabrication tolerance); the current 0.600 mm dimension
would be 0.670 mm. These are nominal Gerber dimensions, not guaranteed
assembled clearance or creepage.

The matching D35 mask aperture is also larger than the copper flash. That
describes solder-mask opening geometry; it does not establish a credited
insulation surface or an accepted floating-conductor path.

For auditability, the raw D18 flash records are:

```text
X01075Y0162, Y0127, X00855D03, Y0162,
X00854Y01369, X01075Y01569, Y01519, Y01469, Y01419, Y01369, Y01319,
X00855D03, X00854Y01419, Y01469, Y01519, Y01569
```

The first four records and the later twelve records are retained exactly as
written because the Gerber zero-suppression stream has no semantic component
labels. They are not silently reinterpreted as pin numbers.

## What this does and does not resolve

The official reference Gerber does not supply a spacing escape for the three
TEA HVS pairs. It gives no net mapping, no assembly tolerances, no NC-land
instruction, and no product-standard insulation basis. It therefore does not
support omitting NC lands, narrowing pads, or waiving the current screen.

The exact next external question is narrower now: ask NXP whether the
reference Gerber's SO16 land pattern is intended to solder pins 4, 11, and 15
and whether NXP approves a no-land variant. Until that answer and the selected
appliance-standard disposition exist, the earlier **BLOCKED_EXTERNAL** status
stands. No CAD change is justified by this comparison.

## Reproducibility

The archive contains `tea2209.gtl`, `tea2209.gts`, `tea2209.txt`, `tea2209.gd1`,
`tea2209.gm1`, `tea2209.gbl`, `tea2209.gbs`, `tea2209.gto`, and a two-page PDF.
The D18/D35 declarations and their units were read directly from the Gerber
bytes. The PDF's schematic identifies the reference design as the TEA2209T
SO16 application, but the Gerber archive does not retain the source CAD
netlist, so no pin-number or pad-net claim is made here.

Official archive URL:
https://www.nxp.com/downloads/en/design-support/TEA2209DB1584-GERBER-FILES.zip
