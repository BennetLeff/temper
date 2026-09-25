# interface-parts-18 review

## Findings

1. **No blocking part-identity or footprint error found.** The selected C3 MPN `R75GN415050H0J` decodes to KEMET R75H, 160 V, 22.5 mm pitch, 1.5 uF, 5%; the R75H table gives 10.0 mm body thickness, 18.5 mm body height, and 26.5 mm body length for the 1.5 uF/22.5 mm variant. The schematic footprint `C_Rect_L26.5mm_W10.5mm_P22.50mm_MKS4` is dimensionally compatible (slightly conservative body width). The 330 uF C4 footprint (`CP_Radial_D10.0mm_P5.00mm`) matches Rubycon 63ZLJ330M10X20's 10 mm diameter and 5 mm pitch, though the 20 mm height is not encoded in the generic footprint and still needs mechanical clearance review.

2. **C3 arithmetic is supported by the KEMET datasheet but remains a screen.** R75H specifies temperature coefficient `-(200 +/- 100) ppm/C`, storage capacitance drift max 0.5% after two years, and endurance capacitance change max 3% at 105 C/1.25xVR for 2,000 h. The Rust screen's 1.3403--1.6597 uF bounds use the conservative -300/+300 ppm extremes, 0.5% storage, and 3% endurance. The 1.30--1.70 uF allocation contains that range. Keep the existing qualification caveat: this does not prove actual assembly temperature, startup waveform, lifetime, or dynamic gate behavior.

3. **C4 arithmetic is a conservative conditional composition, not a datasheet EOL guarantee.** Rubycon ZLJ specifies initial +/-20% at 20 C/120 Hz and endurance capacitance change within +/-25% after rated voltage/ripple at 105 C. Multiplying the extrema gives 198--495 uF; adding the 18 uF bypass allocation gives 513 uF, under the 520 uF prototype allocation. The documentation should state explicitly that the multiplication is a worst-case screening composition of separate specifications, not a manufacturer guarantee of simultaneous endpoint values.

4. **Frozen pin/net structure is preserved.** `clamp-expected.tsv` is identical to interface-capture-16: C1 AUX_RAW/HOT_GND, C2 TMR/HOT_GND, C3 CG/HOT_GND, C4 AUX_PROTECTED/HOT_GND; the native audit still reports 39 pins and 14 components. The schematic diff changes only revision text, prototype part properties/footprints, and allocation notes.

## Checks performed

- Read KEMET R75H and Rubycon ZLJ PDFs with `pdftotext`; verified exact C3 table row and C4 dimensions/specifications.
- Compared interface-capture-16 and interface-parts-18 schematic/net expectation files.
- Reviewed `parts-screen.rs`, `parts-screen.csv`, `pcbparts-selected.json`, and native-audit logs.

## Open adoption boundaries

- Verify C4's 20 mm seated height and C3's 18.5 mm body height/lead-forming option against the actual PCB enclosure and creepage/clearance constraints before adopting either footprint.
- Keep PCBParts stock as indexed availability only; it is not an order reservation.
- Exact downstream ceramic effective capacitance under DC bias, temperature, aging, and the TPS54202/LT4363 startup transient remains to be measured or datasheet-qualified.
