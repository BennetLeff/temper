# Radial footprints for the revised power section

These four unit-local footprints implement the selected parts for source and native-board generation. They are mechanical review patterns. Their pad geometry comes from the named manufacturer parts; the board still needs a physical fit check and its insulation review before fabrication.

| Part and local footprint | Manufacturer dimensions | Pad centers and holes |
| --- | --- | --- |
| C5/C6 TDK `B32656G0275J000`, `TDK_B32656G0275J000_4Pin_P37.50_P20.30_ReviewOnly` | 2.7 µF, 1000 VDC, four leads Ø1.2 ±0.05 mm; body maximum 42 × 33 × 48 mm (length × width × height); lead span 37.5 ±0.4 mm, other lead pitch P1 20.3 mm | 1 `(0,0)`, 2 `(0,20.3)`, 3 `(37.5,0)`, 4 `(37.5,20.3)` mm; all Ø2.8 mm copper, Ø1.8 mm drill. Pads 1/2 form one electrode end; 3/4 form the other. The datasheet drawing does not number its leads, so pad numbers are a local convention. Confirm paired-lead continuity on the actual received part. |
| Four local TDK `B32652A0104K000`, `TDK_B32652A0104K000_P15.00_ReviewOnly` | 100 nF, 1000 VDC, two Ø0.8 mm leads, body maximum 18 × 9 × 17.5 mm | Pads 1 `(0,0)` and 2 `(15,0)` mm; KiCad's existing Ø2.4 mm copper and Ø1.2 mm drill. The stock 2D pattern has the correct body and pitch; this local variant removes its 15 mm-high WIMA 3D model, which understates the selected TDK part's height. |
| PE branch Phoenix Contact KDS 3 `1704004`, `Phoenix_KDS3_1704004_1Pos_2Pin_ReviewOnly` | One electrical potential, two 1.1 × 0.8 mm solder pins; product width 5.08 mm, length 27 mm, installed height 25 mm; manufacturer's drill Ø1.4 mm | Pads 1 `(0,0)` and 2 `(0,15.24)` mm, both on PE; Ø2.6 mm copper and Ø1.4 mm drill. Phoenix's dimensioned drawing places pad 1 at 4.1 mm from one body end and pad 2 at 7.66 mm from the other, so the body extends from y = −4.1 to +22.9 mm. |
| C3/C4 Murata `DE1E3RA222MA4BP01F`, `Murata_DE1E3RA222MA4BP01F_P10.0_Pad1.5_ReviewOnly` | Y1/X1, 2.2 nF; ceramic body maximum Ø9 × 4 mm, leads Ø0.6 mm at 10 mm pitch | Pads 1 `(0,0)` and 2 `(10,0)` mm; Ø1.5 mm copper, Ø0.9 mm drill. The nominal pad-to-pad copper gap is 8.5 mm. The copied KiCad disc outline uses a conservative 10.5 × 5 mm body envelope; its unrelated 3D model was removed. |

The TDK 4-pin capacitor's paired leads are assigned separate pad numbers so the source netlist and native board can verify all four physical connections. The device is nonpolar. The selected capacitor is rated 22.8 A RMS at 85 °C and 100 kHz in the TDK table; application current and heating still require verification. Its 48 mm seated height and 42 × 33 mm board outline are placement constraints.

The PE terminal is a *branch* to PCB PE copper. Cord PE must connect directly to the chassis/heatsink protective stud; the PCB terminal and its solder joints must not be the only series path for protective earth. Keep its PE pads, exposed hardware, and copper at least the provisionally approved 8.0 mm from HOT, subject to the final D5 insulation decision.

The Murata pad change gives 0.5 mm nominal margin above the provisional 8.0 mm HOT-to-PE copper target. Solder fillets, exposed leads, body surface path, board material and production tolerances still need inspection. The Y1 approval does not by itself qualify PCB creepage.

`pcbnew.FootprintLoad` parsed all four footprints and returned the pad positions, sizes and drills listed above. A composite KiCad board/SVG render was visually reviewed. The YAML specifications beside the `.pretty` library record the dimensions and their source drawings. The two KiCad stock-derived capacitor patterns retain the official generator's 2D geometry; their generic 3D models were removed because their body dimensions do not match these exact parts. The installed official generators do not support the TDK four-pin pattern or the Phoenix one-potential/two-pad KDS 3, so those two patterns were transcribed from manufacturer drawings. No exact 3D models have been asserted for them.

Sources:

- [TDK B3265 series datasheet, drawing B1 and ordering table](https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf)
- [TDK B32656G0275J000 product page](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32656G0275J000)
- [Phoenix Contact 1704004 product page](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-kds-3-1704004)
- [Phoenix Contact 1704004 manufacturer drilling diagram, archived product sheet](https://www.micro-semiconductor.kr/datasheet/fb-1704004.pdf)
- [Murata DE1 RA reference specification](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/DE1_RA_P01F_E.pdf)

The reviewed stock Würth 74650074 and Phoenix 1711725 patterns are copied
under `libraries/TerminalBlock_Wuerth.pretty` and
`libraries/TerminalBlock_Phoenix.pretty`. Both shelf measurement and native
generation prefer these local bytes. Regression tests pin all four REDCUBE
solder-pad positions and paste apertures in the library and six native
instances, and reject deletion of one same-number copper leg.
