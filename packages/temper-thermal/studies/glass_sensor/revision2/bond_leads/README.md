# PR2 bond and lead buildout

**Keep M222 as the assembled baseline; prepare IST161 as a parallel response coupon.** The miniature part offers enough modeled improvement to test, but changing the element alone does not solve contact, support or lead bias. No sensor, bond, weld or wire fatigue test was performed. [BOM.csv](BOM.csv), [model-inputs.json](model-inputs.json) and [SOURCES.md](SOURCES.md) distinguish supplier facts from process proposals.

Run `bash run.sh` to build standalone Rust, run 11 tests, and regenerate 270 thermal comparisons, 54 lead comparisons, 36 fin cases, 27 CTE cases and 9 shared-stub cases. It does not touch pyo3 or Cargo caches. These simulations are uncalibrated. The parent revision2 assembled model, including finite support, is authoritative for cartridge performance. This two-node reduction isolates chip/interface tradeoffs and omits hooks, puck, seal, pan spreading and contact-pressure covariance.

## Findings

With an 8 mm 316L face, 0.15 mm thick, assumed contact h=1000 W/m²K, cold loss 0.0005 W/K and conduction-only copper leads 0.000131287 W/K:

| Conditional comparison | M222 | IST161 |
|---|---:|---:|
| Modeled element heat capacity | 0.013563 J/K | 0.002248 J/K |
| t90 relative to sensor final rise | 2.376 s | 1.592 s |
| t90 relative to imposed pan rise | 2.512 s | 1.700 s |
| Error at 200°C pan / 60°C body | −2.014°C | −2.311°C |

IST is 33% faster in this comparison, but its smaller footprint increases interface resistance and bias. M222 uses a solid-envelope heat-capacity proxy. IST uses its actual 0.25 mm substrate plus an assumed 0.3 mm³ fixing drop with volumetric heat capacity 2.5 MJ/m³K. Actual masses and material heat capacities need measurement. IST's 0.6 mm total height must not be treated as a 0.6 mm solid substrate.

Long wires do **not** guarantee low installed heat loss. Four 60 mm, 40 AWG copper extensions plus two 1 mm native Ni stubs give end-to-end G=0.000131287 W/K. A one-dimensional fin model with all surroundings at 60°C gives G=0.000327 / 0.000446 / 0.000536 at assumed distributed h=5 / 10 / 15 W/m²K. PFA outer area and radial resistance are included. Across 190 K, this is 25 mW conduction-only versus 62–102 mW with distributed cooling. Actual air/radiation temperatures vary along the route, so these are boundary sensitivities, not measured bounds. Retain the adverse copper-fin case in the assembled model.

Constantan 36 AWG reduces G to 0.0000172 W/K conduction-only, but still 0.000185 at h=10. Each 60 mm wire has 2.215 Ω versus copper's 0.202 Ω. At 0.3 mA the two current leads cost only 1.329 mV or 0.121 mV respectively. Thermoelectric offsets matter more: an uncorrected 40 µV offset corresponds to 0.368°C at 250°C and 0.3 mA. The 40 µV value is a test offset, not a measured thermopower. Constantan is **not selected** without demonstrated offset measurement or current reversal and settling. Copper/Ni joins also need matched thermal gradients and installed offset checks.

The calculated Johnson noise floor at 250°C, 10 Hz bandwidth and 0.3 mA is about 0.000069°C; this is not ADC or interference performance. Resistance values use room-temperature material proxies, so retain hot-resistance margin in current compliance. RTD dissipation at 250°C and 0.3 mA is about 17.5 µW. Nominal contact self-heating is below 0.001°C in this isolated network. Contact loss and real readout duty can change it. Supplier free-air/water coefficients do not directly describe a bonded cartridge.

## Interface decision

Retain Resbond 908 at a proposed 0.10 mm bond, with 0.075 and 0.15 mm coupon variants. Across M222's nominal 4.83 mm² face, the bond alone is 9.57 K/W; roof, ceramic and spreading add more. Catalog conductivity does not verify a thin bond process. Filler distribution, shrinkage and flatness are unspecified. Reject a thinner process if it starves the joint or bridges on particles, regardless of its favorable calculation.

A 0.25 mm alumina or AlN plate provides controlled bulk dielectric geometry but adds two bonds and heat capacity. The model includes both 0.075 mm films. AlN conductivity cannot remove these interface resistances. The 2.8 × 2.8 mm plate is a custom coupon RFQ, not a verified shelf part or safety barrier. A custom Pt meander directly deposited on an insulating film over the cap could remove the chip/bond stack, but no exact qualified part or process was found. It receives no numerical performance credit.

Resbond's catalog CTE of 8.1 ppm/K versus the inherited 316L proxy of 16 ppm/K produces 4.09 µm differential expansion across 2.3 mm for 25→250°C. Dividing by a 0.10 mm bond gives 4.09% kinematic relative shear: **not stress, failure strain or fatigue life**. Edges relax, cure conditions establish residual strain, and fillets alter constraint. The 1.6 mm chip span reduces mismatch to 2.84 µm; brittle cement still requires qualification. No elastic modulus or fracture-energy curve was invented.

A thermal guard shifts heat into its anchor; bonding wires to a hot puck does not remove net loss. A warm shield might reduce radiation but adds mass and conductances that must be modeled. This package takes no guard credit.

Read [ASSEMBLY.md](ASSEMBLY.md) for coupon, wiring and inspection preparation. All physical acceptance remains **NOT_RUN**.
