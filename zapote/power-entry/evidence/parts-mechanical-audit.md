# Power-entry passive and connector mechanical audit

This is a source and library audit only; no source or PCB files were changed.

## Bulk capacitor

`B43504A5567M000` is not the current exact identity used by the accessible TDK
catalog. A real same-value replacement is TDK/EPCOS `B43513C5567M080`: 560 µF,
450 VDC, 85 °C, 45 mm diameter × 40 mm length, four-pin snap-in, and rated
ripple current 3.44 Arms at 100 Hz/85 °C. The official TDK ordering page also
specifies the PVC insulation and additional PET terminal-side cap. Its official
series drawing calls for all four terminal holes; the exact terminal drawing
must be used before replacing the current two-pin `P10.00mm` footprint. No
unverified four-pin geometry was added here.

Sources: [TDK product result](https://www.tdk-electronics.tdk.com/en/3060056/products/product-catalog/aluminum-electrolytic-capacitors/snap-in-multi-pin-large-size-capacitors/search-results-single-ended-capacitors?so=%7B%22orderingCode%22%3A%22B43513C5567M080%22%7D),
[TDK B43513/B43523 series drawing](https://www.tdk-electronics.tdk.com/inf/20/30/db/aec/B43513_B43523.pdf).

## Boost inductor

The source's `IHV30EB150` is a real Vishay/Dale part. Vishay document 34022
gives style 2 dimensions A max 62.23 mm, B 41.91 mm body diameter, C 27.43 mm
terminal centre spacing, and E 3.28 mm lead diameter. Therefore the existing
footprint's circular 41.91 mm body and pads at -13.715/+13.715 mm are correct:
the ±13.715 mm coordinates encode half of the 27.43 mm C spacing, rather than
mistaking the 41.91 mm body diameter for the pitch. The part is 150 µH ±10%,
30 A rated DC current, 13 mΩ maximum DCR; full-current operation is specified
to +75 °C and no-load operation to +125 °C.

Source: [Vishay IHV series document 34022](https://www.vishay.com/docs/34022/ihv.pdf).

The Vishay document also limits the IHV family to a maximum usable frequency
of 20 kHz. That makes `IHV30EB150` unsuitable for the 130 kHz PFC switching
envelope even though its mechanical terminal coordinates are valid. The
selected frequency-capable replacement is Würth Elektronik
`760800301` (WE-TORPFC, T75): 180 µH nominal (specified at 100 kHz/100 mV),
±20%, 24.5 A rated at 40 K temperature rise, 43 A typical saturation current
(less than 30% inductance drop), 20 mΩ maximum DCR, 1000 VDC maximum working
voltage, and -40 to +155 °C operating range. The official T75 package is
99 mm maximum diameter and 62 mm maximum height. Its official KiCad bundle
was copied without geometry edits to `libraries/Inductor_THT_Wurth.pretty/`
and its matching STEP model to `libraries/Inductor_THT_Wurth.3dshapes/`.
The vendor drawing gives the actual pad/bolt pattern; no footprint was
derived from the old IHV circle.

Sources: [Würth WE-TORPFC family page](https://www.we-online.com/en/components/products/WE-TORPFC),
[Würth 760800301 datasheet](https://www.we-online.com/components/products/datasheet/760800301.pdf),
[Würth official KiCad bundle](https://www.we-online.com/components/products/download/KiCad_WE-TORPFC%20%28rev26b%29.zip).

## Bulk capacitor replacement

The selected two-terminal 560 µF / 450 V snap-in is Nichicon
`LGX2W561MELC50`: 35 mm diameter × 50 mm body, 10 mm terminal pitch, 2 mm
terminal holes, 1.98 A RMS ripple at 120 Hz/105 °C (the catalogue's high
frequency rating is 2.83 A RMS at 50 kHz, calculated from the catalogue's
1.43 high-frequency coefficient). The local footprint is the KiCad
35 mm P10 snap-in geometry with its courtyard tightened to a 36.5 mm maximum
diameter; the pad centres remain 10.00 mm apart and drills remain 2.00 mm.
The old TDK identity is therefore replaced by an exact, traceable Nichicon
ordering code in the mechanical record; source `.ato` integration remains a
separate owner decision.

Source: [Nichicon LGX catalogue, page 3](https://www.nichicon.co.jp/english/series_items/catalog_pdf/e-lgx.pdf).

## Mains connector

Phoenix Contact `MKDS 5/3-9,5`, item `1714984`, is the verified three-position
replacement identity. The official page specifies 9.52 mm pitch, 28.56 mm
overall width, 12.5 mm length, 26.5 mm height, 21.5 mm installed height, 5 mm
solder-pin length, 0.9 × 0.9 mm pin dimensions, and 1.3 mm PCB hole diameter.
It is rated 32 A, 1000 V (III/2), for 4 mm² conductors. The existing 5.08 mm
MSTB geometry is therefore not interchangeable and must be replaced only with
the 9.52 mm native footprint.

Source: [Phoenix Contact official product page](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-5-3-95-1714984).

The companion two-position output connector is Phoenix Contact `MKDS 5/2-9,5`,
item `1714971`: 19.04 mm overall width × 12.5 mm length, with 9.52 mm pad
pitch, 1.3 mm PCB holes, 0.9 × 0.9 mm solder pins, and the same 32 A/1000 V
rating family. `temper.pretty/Phoenix_1714971.kicad_mod` now uses the official
pad-relative coordinates (0 and 9.52 mm) and the full 19.04 × 12.5 mm body
envelope. `Phoenix_1714984.kicad_mod` provides the three-position input with
pad centres 0, 9.52, and 19.04 mm and the official 28.56 × 12.5 mm envelope.
Both footprints retain 1.3 mm drills and pin-1 rectangular marking.

Source: [Phoenix 1714971 product page](https://www.phoenixcontact.com/en-us/products/1714971),
[Phoenix 1714984 product page](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-5-3-95-1714984).

## Library-load receipt

Using KiCad 10's bundled Python `pcbnew.PCB_IO_KICAD_SEXPR().FootprintLoad`
against each local library directory, all four footprints loaded successfully
on 2026-09-11: `Phoenix_1714971` (2 pads), `Phoenix_1714984` (3 pads),
`L_Wurth_WE-TORPFC-T75` (3 pads including the vendor mechanical hole), and
`CP_Radial_D35.0mm_P10.00mm_SnapIn` (2 pads). The Würth footprint and STEP
files are vendor-bundled; the Phoenix footprints use the manufacturer drawing
dimensions above. No source or PCB files were changed.

The local file SHA-256 values are `120239f9f4ff837cd8970353c813e81818cc5f208922d06884e6fde30975f436`
(1714971), `f1ae86ba0c0cd52b24a15821f512bed2c4f09874e4611575300d5313c7e7e173`
(1714984), `87eada1311152b978e87f5909b601739eea9bfd4da73a3a3f339a8fb4f6c0ca1`
(Würth footprint), and `1c82628a22ea923253d7f967ca092d216088e65ef2ee77345f162fb20cfde011`
(bulk footprint). The Würth STEP model SHA-256 is
`3d9df491b8d4ac3f74257591eb23ba5f95d90395f769d1567f420b4b4cb1db79`.

## Follow-up package review

The Phoenix drawing gives a 12.5 mm body length and locates the solder-pin
row 4.6 mm from the body edge. The connector footprints therefore use a
pad-row origin with body bounds y = -4.60 ... +7.90 mm; centering the 12.5 mm
body on the pad row would misrepresent the manufacturer's drawing. The
two-position width is 19.04 mm and the three-position width is 28.56 mm.

The existing bridge footprint was a KBU package with 7.62 mm geometry and is
not valid for `GBU2510A`. The Yangjie official GBU2510A drawing specifies the
GBU body and the 5.08 mm four-pin inline pattern (pin 1 `-`, pins 2/3 `AC`,
pin 4 `+`). The local `Diode_THT/Diode_Bridge_GBU2510.kicad_mod` is the KiCad
GBU package geometry with pads 1–4 at 0, 5.08, 10.16, and 15.24 mm and 1.6 mm
drills; it replaces the KBU geometry at the library level. Source:
[Yangjie GBU25005A–GBU2510A datasheet](https://www.21yangjie.com/pdf/zlqj/zhengliuqiao/GBU25005A%20THRU%20GBU2510A.pdf).

For the safety capacitor, the exact Vishay ordering code
`VY1102M31Y5UQ63V0` is a 1 nF Y5U disc in the VY1 series, with X1/Y1
500 VAC qualification, 9 mm maximum body diameter, 5 mm maximum thickness,
and 10 mm lead spacing. `Capacitor_THT/C_Disc_Vishay_VY1102M31Y5UQ63V0.kicad_mod`
uses those limits, 10 mm pad spacing, and the datasheet's 0.6 mm lead basis.
Source: [Vishay VY1 datasheet 28537](https://www.vishay.com/docs/28537/vy1series.pdf).
