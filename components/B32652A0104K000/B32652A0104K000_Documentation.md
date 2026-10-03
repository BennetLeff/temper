# TDK B32652A0104K000 — local DC-link capacitor

**Selected part:** TDK 100 nF ±10%, 1000 VDC polypropylene radial capacitor. Four are fitted: C38/C39 close to bridge leg A and C40/C41 close to leg B. All connect BUS_P to **HV_RET**. A LEG_RET return would let shoot-through current bypass the shunt R5 and blind the DC over-current comparator. The four add 0.4 µF to the two 2.7 µF bulk parts, giving 5.8 µF nominal total.

The manufacturer's table gives 5.4 A RMS at **85 °C and 100 kHz** and 975 V/µs; those conditions do not establish current sharing, heating or pulse survival in this board. The unit footprint `temper:TDK_B32652A0104K000_P15.00_ReviewOnly` has pad 1 BUS_P at `(0,0)` and pad 2 HV_RET at `(15,0)` mm. Both pads are Ø2.4 mm copper / Ø1.2 mm drill for Ø0.8 mm leads. The part is nonpolar. Maximum body envelope is 18 × 9 × 17.5 mm. The local variant keeps the matching stock 2D pattern but omits a WIMA 3D model that understated the TDK part's height.

Place two parts near each MOSFET pair within the heatsink and insulation envelope. The commutation return must pass through R5's power path; keep Kelvin sense separate. Measure each capacitor's temperature, the bus/MOSFET voltage and current division. The 1 kV nameplate is not a measured transient limit for the assembled loop.

Sources: [TDK series datasheet](https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf), [footprint derivation](../../zapote/power-stage-120v/RADIAL-FOOTPRINTS.md), [power loop review](../../zapote/power-stage-120v/PROTOTYPE-POWER-LOOP.md).
