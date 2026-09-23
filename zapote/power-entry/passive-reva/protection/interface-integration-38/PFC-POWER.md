# Rev38 boost, F2, and reservoir candidate

Status: **compiled power-path topology; component and fault qualification
OPEN**. The joined Atopile entry now connects the GBJ2510-F bridge plus to
Würth 760800301 boost inductor, its switch node to STW drain and both
[C3D20065D](https://assets.wolfspeed.com/uploads/2023/12/Wolfspeed_C3D20065D_data_sheet.pdf)
anodes, and the diode cathode to local VD. Bridge minus reaches the
rectifier-side terminal of the 10 mΩ sense shunt; HOT0 is the controller and
STW-source side. The AC input legs remain external.

A candidate [Mersen A70QS50-14F](https://www.mersen.com/en/products/amp-trap-a70qs-700vac-700vdc)
F2 connects VD to bank-side VB. A
[TDK B32776P6226K000](https://product.tdk.com/en/search/capacitor/film/dc-link/info?part_no=B32776P6226K000)
22 µF ±10%, 630 V film reservoir and 470 nF film HF bypass remain on VD
when F2 opens. Four Nichicon LGX2W561MELC50 560 µF, 450 V capacitors and
a three-element 150 kΩ series bleeder are on VB. Both VD and VB feed their
distinct TLV3202 divider inputs; the UCC28180 VSENSE ladder stays on VD.
The local film reservoir stores about 1.76 J at 400 V nominal and remains
outside F2. This is a topology and nominal-energy observation, not an
allowance for its discharge or a thermal/interrupting qualification.

The exact F2 cartridge/clip/holder combination, 50 A rating relative to
the 15 Arms input requirement, F1/F2 coordination, DC interrupting duty,
inductor saturation over the fault trajectory, diode thermal path, local-C
ESR/ESL and surge current, VB capacitor ripple sharing, bleeder discharge
and single-open behavior, enclosure clearances and creepage, plus STW/diode
mechanical heatsinking all remain to be established. The 450 V bank rating
does not authorize a 500 V VB waveform. A voltage-equality observation
cannot prove F2 continuity; failed-short STW and stored-capacitor discharge
are not stopped by the gate path.

The standalone and joined Atopile builds pass. `audit.rs` checks exact
component identities and physical pin membership, F2 separation, local-C
placement, both diode anodes, shunt return, and the VD/VB detector joins.
Deliberate shorts/opens fail. `TBD_REVIEW_ONLY` footprints require native
package, clip, board spacing and assembly review before layout. The
canonical 54-part passive board is unchanged.
