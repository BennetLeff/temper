# Local high-frequency bus capacitor review

Source-build-20 supersedes source-build-19 and adds `c_hf`, a local polypropylene bypass across
`PFC_BUS_PLUS_390V` and `PFC_BUS_MINUS`. The added part is TDK/EPCOS
`B32672P6474K000`, 470 nF ±10%, 630 VDC PP film, with a candidate-local
15 mm-pitch footprint matching the datasheet maximum 18 x 14 x 8 mm envelope. The donor part number was wrong; it was not accepted as evidence. The capacitor
closes the local MOSFET/boost-diode/bus-capacitor switching loop. The input
bridge is not itself part of that fast commutation loop.

The TDK/EPCOS B32671L/672L data sheet distinguishes the 10 mm L-series from
the 15 mm B32672L series; its companion B3267P data sheet identifies
B32672P6474 as the 470 nF / 630 VDC / 15 mm-pitch row and its 18 x 14 x 8 mm
maximum envelope. The local footprint is a construction land pattern; exact assembled ripple, ESL, dv/dt, creepage,
thermal, and switching qualification remain open.

Source result: `zapote/power-entry/source-build-20/build-receipt.json`,
Atopile 0.2.69, return code 0. Existing source references are preserved and
the candidate remains unrouted and unqualified.

Reference: [TDK/EPCOS B32671L/672L data sheet](https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32671L_672L.pdf).

Exact part and dimensional evidence: [TDK B32672P6474K000](https://product.tdk.com/en/search/capacitor/film/snubbering_pfc/info?part_no=B32672P6474K000), [TDK P-series datasheet](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b3267_p.pdf).
