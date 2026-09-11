# TPS54302 fallback screen — proposal only

Checked September 10, 2026. No schematic, BOM, fixture, requirement or approved
model identity was changed. The downloaded model was inspected, not executed.

TI's [LMR51430 product page](https://www.ti.com/product/LMR51430) explicitly
lists TPS54302 as pin-to-pin compatible. The [TPS54302 product page](https://www.ti.com/product/TPS54302)
specifies 4.5–28 V input and 3 A output capability, so the declared Temper
voltage/current envelope fits those ratings. This is an initial screen, not
proof of thermal, transient or circuit performance.

TI also publishes the [unencrypted transient model, SLVMBL9A](https://www.ti.com/lit/zip/slvmbl9).
The original archive and extracted library are retained here:

- `SLVMBL9A.ZIP`: SHA-256
  `d06e58535f99c35ee5da259e68c09c471b819d00c2fe98d4d5d1da49ea730f77`.
- `TPS54302_TRANS.LIB`: readable text with the exact TPS54302 subcircuit.
  Its header names PSpice 16.2, Final 1.00, May 18, 2016 and the TPS54302EVM-716.
  It lists overvoltage/overcurrent protection, shutdown, pulse skip and spread
  spectrum among modeled functions. Temperature effects are explicitly absent.
  Ground is internally tied to global zero. ngspice compatibility has not been
  tested or established. Preserve the embedded TI notices when using the file.

[DigiKey's exact TPS54302DDCR listing](https://www.digikey.com/en/products/detail/texas-instruments/TPS54302DDCR/6572466)
showed 16,860 in stock and USD 1.41 for quantity one on September 10. Distributor
cut-tape number: `296-46237-1-ND`. Stock and price are a dated observation,
not a reservation or purchasing commitment.

## Changes a real substitution would require

TPS54302 uses nominal 400 kHz switching and pulse skipping/spread spectrum;
the current exact-model contract requires LMR51430X at 500 kHz PFM. A physical
pin match does not make their electrical models interchangeable. Recheck
inductor sizing/ripple, output-capacitance and loop stability, divider/reference
tolerance, startup, current limits and thermal margin. The new model cannot
qualify LMR51430 and cannot close capacitor or hot-inductor evidence by itself.

The practical choice is to retain LMR51430 pending an exact-model response
from TI, or explicitly evaluate a TPS54302 redesign with its actual vendor
model. The second path has a verified downloadable artifact and current
distributor availability; it still needs simulator replay and design
qualification before adoption. No silent substitute or behavioral proxy was
introduced into the current admission path.
