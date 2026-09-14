# Bridge connection comparison (checkpoint)

The three bounded candidates differ only in the four U1 package-neck widths.
Endpoints, nets, lengths, layers, stackup, package and downstream routing are
held constant. Copper resistance values below are first-order comparisons for
0.07 mm copper and do not replace the coupled thermal model.

| candidate | neck width | U1 neck R range | native ERC/DRC | Rust clearance profile | disposition |
| --- | ---: | ---: | --- | --- | --- |
| baseline | 2.5 mm | 0.591–0.887 mΩ | 0/0, no unconnected/parity | pass | retained reference; current screen finding remains |
| same-package-3mm | 3.0 mm | 0.493–0.739 mΩ | 0/0, no unconnected/parity | pass | constrained model input; 15 A screen remains open |
| same-package-6mm | 6.0 mm | 0.246–0.369 mΩ | 0/0, no unconnected/parity | **fail** (0.58 mm min vs 2.0 mm) | rejected geometry experiment |

The wider constant-width trace lowers the idealized neck loss, but the 5.08 mm
GBU2510A pin pitch makes 6 mm incompatible with the Zapote voltage-domain
profile. KiCad's native rules do not express that product-specific 2 mm floor,
which is why the Rust finding is retained. The 3 mm candidate clears spacing but
does not, by itself, prove 15 A RMS capacity or acceptable temperature.

No thermal ranking is made here. The physical-model owner must evaluate the
saved copper, pad, barrel and solder geometry with the common 15 A RMS / 40 °C
inlet assumptions; the cooling owner must apply the same contact and airflow
boundaries. The coordinator should only promote a candidate after those
source-bound results and the current screen agree.
