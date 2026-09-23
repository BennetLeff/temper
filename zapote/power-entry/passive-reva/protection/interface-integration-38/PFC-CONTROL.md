# Rev38 PFC controller and PWM producer

Status: **compiled UCC28180-to-UCC27624 control join; power path and
electrical response acceptance OPEN**. The separate `pfc_controller.ato`
module carries candidate Rev35 compensation and sense values into the Rev38
joined entry. Its `PFC_PWM` output reaches UCC27624 INA, which has a local
low default. STW source is locally joined to HOT0 in the driver module.

The [UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf) pin paths are
explicit: VCC to protected AUX, GND to HOT0, ISENSE through 220 Ω from the
rectifier-side terminal of the 10 mΩ shunt, 1 nF to HOT0, and a negative
clamp diode; FREQ uses 16.2 kΩ; ICOMP uses 2.7 nF; VCOMP uses 40.2 kΩ plus
4.7 µF and 220 nF compensation. Five 200 kΩ parts from VD and a 13 kΩ
bottom resistor feed VSENSE, with 680 pF to HOT0. These values are
provisional and require controller design and stability review.

One AO3400A pulls VSENSE to HOT0 when its gate is biased by an AUX-driven
100 kΩ/100 kΩ divider. A second AO3400A can pull that gate low only when
the retained local `DRIVER_PERMISSION` is high through 1 kΩ. A 100 kΩ
pull-down on its gate keeps it off if permission is missing. This is a
second inhibition route alongside the UCC27624 ENA clamp. TI describes
VSENSE below its 0.82 V open-loop-protection threshold as a controller
disable condition; the actual Q1/Q2 resistance, AUX corners, VD divider
current, input leakage and controller delay must establish a guaranteed
below-threshold value and response. A netlist alone does not prove it.

`RECT_MINUS` is still an external port; the bridge and inductor/switch/diode
network have not been joined. The UCC's internal peak-current limit is
cycle-by-cycle and is not treated as retained session-invalidating shutdown.
An independent overcurrent detection and trip path, or a supported argument
that no separate one is required for the accepted operating envelope, is
still open. No current-limit threshold has been promoted to a safe peak.

The standalone and joined Atopile builds pass, and `audit.rs` checks exact
UCC pins, the VSENSE ladder, shunt and clamp polarity, AUX/HOT0 domains,
inhibit FETs, retained permission, and PWM-to-driver join. Deliberate opens
and swaps fail. The many `TBD_REVIEW_ONLY` footprint keys avoid Atopile
0.2.69's same-footprint MPN collision; they require actual package, voltage,
thermal, and BOM review before native placement.
