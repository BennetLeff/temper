# Local compensation routing receipt

Final revision C places **C104 = 100 pF directly across U7A**, independently of the selected RF jumper. C41 and C105 are removed. The parent reviewer measured the retained native PCB; `results.json` and the first line of `native-geometry.tsv` pin its SHA-256.

| Conductive path | Native centerline length | Layer changes |
|---|---:|---:|
| U7.2 → C104.1 | 2.337500 mm | 0 |
| C104.2 → U7.1 | 2.110902 mm | 0 |
| Total local capacitor path, excluding capacitor conductor | **4.448402 mm** | **0** |
| 100 Ω RF path, including input and both sides of header | 16.903293 mm | 0 |
| 5 kΩ RF path, including input and both sides of header | 48.073316 mm | 0 |
| 100 kΩ RF path, including input and both sides of header | 29.455772 mm | 0 |

The RF totals exclude resistor and removable header/shunt conductors. Local C104 endpoints are relieved on In1, In2 and B, as independently recorded in `../independent-layout-rev-c.json`. Its signal connection uses no through via. The high-range feedback traces are deliberately outside this local capacitor loop.

`export_native.py` is a thin adapter exposing KiCad's actual pad, track and via positions. The Rust graph splits native segments at junctions and permits layer transitions only at exported vias or plated pads. `measure.rs` sums planar centerline distances; it does not simulate pad copper current density or calculate electromagnetic inductance. The explicit 0.125 mm C104 output-pad-center stub makes the local route traceable without inferring connectivity through a pad's area. Native DRC independently confirms copper connectivity and clearance.

Run `sh run.sh [absolute-board-path]` with Rust and KiCad's bundled Python. Set `KICAD_PYTHON` when using a different installation. The run deletes its previous result before starting and publishes a new result only after successful reduction. It does not change CAD.

## Inductance assumptions and connector fit

The [analog report](../../docs/analog-validation-rev-c.md) separately stresses **RF/header lead inductance** and **local capacitor lead inductance**, including component/supply corners. Those lumped inductances are sensitivity tests, not extracted or measured properties of this PCB. The short local geometry supports using a few nH as an engineering estimate, but its actual value depends on pad/package current paths, return geometry, dielectric stackup and the capacitor's ESL. The 5 nH case must not be described as a proven upper bound; additional 10 nH local-path stress is retained in the report. TI's [PCB trace discussion](https://www.ti.com/lit/pdf/slva790) explains why length and return-plane spacing matter. A length-to-inductance rule is not a layout extraction.

Use **Samtec TSW-102-07-G-S** headers with **SNT-100-BK-G** shunts fully seated. The [TSW catalog](https://suddendocs.samtec.com/catalog_english/tsw_th.pdf) specifies the -07 post; the [shunt catalog](https://suddendocs.samtec.com/catalog_english/pk.pdf) specifies its 4.32 mm minimum insertion. The [SNT drawing](https://suddendocs.samtec.com/prints/snt-100-xx-x-x-mkt.pdf) gives its 5.08 × 2.54 mm plan envelope and 6.10 mm body height. Shorter posts cannot be substituted merely because they reduce conductor length.

JP4 uses a local footprint with unchanged pad/drill geometry and a 0.28 mm nominal courtyard allowance around the 2.54 mm body; native footprint-library parity passes. The specified shunt envelope fits inside it. The compact header and nearby passive bodies pass courtyard clearance without exclusions. The capacitor bypasses this header, so acceptance no longer rests on an unverified 20 nH header bound.

First-board scope checks on every range, with representative fixtures/loads and recorded probe capacitance, remain required. This geometry receipt and typical macro-model simulations do not establish physical phase margin or calibrated LCR accuracy.
