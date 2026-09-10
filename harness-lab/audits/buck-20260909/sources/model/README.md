# LMR51430XDDCR exploratory SPICE model

[`LMR51430XDDCR_datasheet_approx.lib`](LMR51430XDDCR_datasheet_approx.lib)
is a datasheet-derived switching model authored with Luna and corrected and
measured by the host. It targets the 500 kHz PFM X variant. It requires
ngspice with XSPICE; the retained runs used ngspice 45.2.

Terminal order is `VIN SW GND FB EN CB`, corresponding to TI package pins
3, 2, 1, 4, 5, 6. External feedback sets the voltage. External inductance,
capacitance, load, and bootstrap capacitor belong in the surrounding circuit.
The model draws input power through finite-resistance switches.

See [the measured audit](../../model-simulation.md) for parameters,
limitations, independent calculations, measurements, and reproduction commands.
No normal harness model-approval entry has been created: this is useful for
exploration, and is not a qualified substitute for TI or hardware evidence.

## Vendor search provenance

The [TI product page](https://www.ti.com/product/LMR51430) and
[Rev. A datasheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf) were inspected
on 2026-09-09. No downloadable vendor model bytes were obtained in this audit.
That observation does not establish that no vendor model exists.

WEBENCH offers `LMR51430X (Buck)`, alongside XF, Y and YF. The family-level X
selector is a legitimate vendor route; failure to find the full DDCR ordering
suffix in its search is not proof of a device mismatch. The audit did not
obtain an exported model or retained vendor simulation from that route.
A TI forum response about the XF sibling does not prove X model availability.

The legacy `simulation/models/LMR51430_avg.lib` in this repository uses an
incorrect 0.8 V reference and an averaged voltage-source output. It was not
used as the basis for this model or admitted as qualification evidence.
