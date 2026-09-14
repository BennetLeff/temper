# Bridge connection comparison

The same-package candidates differ in the four U1 neck geometries; the GBJ
candidate also changes package pitch. Copper resistance values below are
first-order comparisons for 0.07 mm copper and do not replace the coupled
thermal model.

| candidate | neck width | U1 neck R range | native ERC/DRC | Rust clearance profile | disposition |
| --- | ---: | ---: | --- | --- | --- |
| baseline | 2.5 mm | 0.591–0.887 mΩ | 0/0, no unconnected/parity | pass | retained reference; current screen finding remains |
| same-package-3mm | 3.0 mm | 0.493–0.739 mΩ | 0/0, no unconnected/parity | pass | constrained model input; 15 A screen remains open |
| same-package-6mm | 6.0 mm | 0.246–0.369 mΩ | 0/0, no unconnected/parity | **fail** (0.58 mm min vs 2.0 mm) | rejected geometry experiment |
| shaped-pad-entry | 3.0 → 4.2 mm | 0.493–0.739 mΩ at entry | 0/0, no unconnected/parity | pass | constrained shaped input; 3 mm bottleneck remains |
| alternate-gbj | 4.2 mm local draft; 10/7.5/7.5 mm pads | source-bound | 0/0, no unconnected/parity | indeterminate thermal copper checks | native-clean exact-package input; thermal model required |

The wider constant-width trace lowers the idealized neck loss, but the 5.08 mm
GBU2510A pin pitch makes 6 mm incompatible with the Zapote voltage-domain
profile. KiCad's native rules do not express that product-specific 2 mm floor,
which is why the Rust finding is retained. The 3 mm candidate clears spacing but
does not, by itself, prove 15 A RMS capacity or acceptable temperature. The
shaped candidate makes that bottleneck explicit. The GBJ candidate uses the exact 10/7.5/7.5 mm drawing dimensions and is now
native-clean with fresh source-bound extraction; no current capability is
inferred from pad area.

The [resolved joint comparison](../../thermal/physical-model/comparison.md)
now compares baseline and 3 mm under identical assumptions: nominal peaks
102.207 → 100.924 °C; weak-assembly peaks 164.349 → 159.562 °C. These whole-joint
peaks are conditional and do not establish die or PCB qualification. The gain
is modest; the four current-screen failures remain. Keep the maintained board
unchanged and evaluate the wider-pitch GBJ assembly or obtain the missing
package/assembly/cooling evidence before selection. GBJ and shaped geometries
are unsupported by the GBU joint importer and receive no inherited thermal pass.
