# Standalone RTD unit boundary

This is a source and BOM proposal for an independently reviewed RTD unit. It
does not connect an MCU, buck converter, or host harness and does not authorize
placement or routing. The internal instance remains `rtd_pan`, preserving the
existing compiled identity; the boundary connector instance is `unit_io`.

The exact proposed connector is Samtec `FTSH-105-01-F-D`, a 10-position,
2-row, 1.27 mm through-hole header. Samtec's product page is
[FTSH-105-01-F-D](https://www.samtec.com/products/ftsh-105-01-f-d). The local
proposal footprint is
`footprints/Temper_RTD.pretty/FTSH-105-01-F-D_2x5_P1.27mm.kicad_mod`; its pad
and courtyard dimensions remain subject to a final comparison with the
vendor's mechanical print before release.

| Pin | Boundary net | Direction at unit | Internal endpoint |
|---:|---|---|---|
| 1 | `+3V3` | input | `rtd_pan.power.vcc` |
| 2 | `GND_A` | return | `rtd_pan.power.gnd` |
| 3 | `GND_B` | return, same unit ground net | `rtd_pan.power.gnd` |
| 4 | `RTD_SCK` | input | `rtd_pan.spi.sclk` |
| 5 | `RTD_SDI` | input | `rtd_pan.spi.mosi` |
| 6 | `RTD_SDO` | output | `rtd_pan.spi.miso` |
| 7 | `RTD_CS_N` | input, active low | `rtd_pan.cs.line` |
| 8 | `RTD_DRDY` | output, active low | `rtd_pan.drdy.line` |
| 9 | `RTD_HW_FAULT` | output, active high fault indication | `rtd_pan.rtd_hw_fault.line` |
| 10 | `SHARED_REF_2V5` | analog reference boundary | `rtd_pan.reference.VREF` |

`GND_A` and `GND_B` are two connector contacts on the unit's common ground
net. They are separate contacts for return-current and harness redundancy;
they are not isolated grounds. `SHARED_REF_2V5` is the REF2025 output net,
which is also the existing upstream OVP/OCP2 reference identity when this unit
is used in the cooker. The host must supply or accept that net at the boundary;
this proposal does not create a second reference source.

## Connector and footprint risks

The Samtec product page establishes the exact orderable family and 10-pin,
2-row, 1.27 mm pitch. The Samtec FTS/FTSH DTH print specifies a 0.028 inch
(0.71 mm) finished hole; the proposal uses 1.05 mm copper pads, leaving a
0.22 mm row-to-row copper gap. The `-D` part is a plain double-row header and
does not provide a keyed shroud; the silkscreen dot only marks pin 1. The
vendor drawing must be checked for final plated-hole, body keepout, and
mating-side orientation before fabrication. That check is a mechanical
acceptance item; no claim of completed board placement or routing is made here.

## Supervisor package retained by the unit proposal

The RTD rail guard remains `TPS389001DSER`, TI DSE WSON-6, with the local
proposal footprint `Temper_RTD:TPS389001DSER_WSON-6_DSE`. The DSE top-view pin
map is SENSE=1, GND=2, MR=3, VDD=4, CT=5, RESET=6. MR is tied to the local
RTD rail (`power.vcc`) so the monitor is enabled. CT is intentionally left
open, selecting the no-capacitor delay; TI specifies approximately 25 µs for
that condition. RESET is the open-drain active-low rail-permission output and
uses the existing 10 kΩ pullup. The package drawing shows six perimeter pads
and no exposed thermal pad; the local footprint therefore has exactly six SMD
pads and no pad for an invented exposed metal area. See the
[TPS3890 Rev A datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf).

The local footprint is an auditable proposal, not a substitute for the TI
land-pattern check. Its six pads are numbered in the TI top view and use a
0.50 mm row/pitch arrangement. A render receipt is kept with the circuit
artifacts.

## Timing boundary

The MAX31865 RTD open-lead timing model remains conditional on the separately
recorded SINC3 boxcar assumption and the selected 1 nF differential C0G plus
paired 1 MΩ diagnostic pullups. The unit-side detector bound ends at the
`RTD_DRDY`/fresh resistance observation; any downstream MCU fault sink and
interlock propagation budget is separate. Physical cable, EMC, connector
continuity, supervisor ramp, and shutdown measurements remain **NOT RUN**.
