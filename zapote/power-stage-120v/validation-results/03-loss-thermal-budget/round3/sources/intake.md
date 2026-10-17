# Coordinator source intake

Retrieved 2026-09-27. Verify values and record hashes in the final input table.

- `henkel-tim-guide.pdf`: <https://dm.henkel-dam.com/is/content/henkel/Henkel_TIM_Guide_082917_US_LRpdf>, SHA-256 `6a739a3ee70ba1be1a08d71953e6eda79b58cf5426e7fa101ac40e3f6e80c502`. Printed p.63 SIL PAD 400, p.75 SIL PAD K-10. Typical properties, not guarantees. For the 0.229 mm SIL PAD 400 use its own 1.45 °C·in²/W row at 50 psi, not the headline 1.13 for the thinner 0.178 mm option. K-10 is 0.152 mm, 0.41 °C·in²/W at 50 psi. Both are area-normalized impedances including interfaces; published TO-220 resistance is not TO-247 resistance. Dielectric constants 5.5 and 3.7 are measured at 1 kHz, not the EMI band. Pressure/roughness/contact-area dependence is explicit.
- `gbj2510.pdf`: <https://www.diodes.com/datasheet/download/GBJ2510.pdf>, DS21221 Rev.11-2, May 2025. p.2 RthetaJC 1 °C/W is typical **per element**, with a 250×250×20 mm aluminum plate fixture. Do not multiply package-total loss by this per-element value. Exact manufacturer also offers a SPICE model at <https://www.diodes.com/part/view/GBJ2510>; A7 may use it for junction capacitance.
- `mc78l00a.pdf`: <https://www.onsemi.com/pdf/datasheet/mc78l00a-d.pdf>. Verify actual downloaded revision and SOT-89 thermal conditions. Include regulator quiescent dissipation as well as (Vin−Vout)Iout.
- `irm20.pdf`: <https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF>. Search indexed revision 2025-11-21; downloaded bytes decide. 84% is typical at rated load, 230 Vac, 25°C; cannot assign unchanged to low-load PS1 operation.

These were coordinator source leads, not accepted numerical results at intake.
The task-03 audit below now extracts a package-metal area range and a
conditional heatsink requirement; installed contact and airflow remain open.

## Task 03 verified source register (2026-09-27)

The following local PDF hashes are independently recorded by
`../outputs/provenance.json`; printed pages and scope of each value are in
`../README.md`. The coordinator leads above have been checked against the
downloaded bytes. All values remain subject to the printed test conditions.

| Local file | Source URL | Revision/date | SHA-256 |
| --- | --- | --- | --- |
| `ipw65r018cfd7.pdf` | <https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf> | Rev 2.0, 2021-04-19 | `c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2` |
| `gbj2510.pdf` | <https://www.diodes.com/datasheet/download/GBJ2510.pdf> | DS21221 Rev 11-2, May 2025 | `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02` |
| `wsk2512.pdf` | <https://www.vishay.com/docs/30108/wsk2512.pdf> | Rev 2023-12-11 | `2ee8a9067539bd2cabb08845219bac55d506b1ca892a2dbaeed343dd1ed10cff` |
| `942C.pdf` | <https://www.cde.com/resources/catalogs/942C.pdf> | no printed rev; PDF created 2021-11-16 | `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310` |
| `mc78l00a.pdf` | <https://www.onsemi.com/pdf/datasheet/mc78l00a-d.pdf> | live PDF, 2026-09-27 retrieval | `2e3acd62796195fd26fdf71845a6b71156302b648d8bbb50d05ed352ee3e9bc5` |
| `irm20.pdf` | <https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF> | 2025-11-21 | `aa1afdbcdf0bf6db796710e26bd5e258f4857ffb1c14bd1ac3d94af86f3b8789` |
| `irm05.pdf` | <https://www.meanwell.com/Upload/PDF/IRM-05/IRM-05-SPEC.PDF> | 2025-08-08 | `8e13f9373a39d8e0d92d540082cb97a9f3172111ea749b807af96db9e27d878a` |
| `henkel-tim-guide.pdf` | <https://dm.henkel-dam.com/is/content/henkel/Henkel_TIM_Guide_082917_US_LRpdf> | 2017 guide | `6a739a3ee70ba1be1a08d71953e6eda79b58cf5426e7fa101ac40e3f6e80c502` |
| `aavid-63730.pdf` | <https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/2331/63730_Datasheet.pdf> | Aavid Nov 2016 A02 | `529bcd302a25385f436a034c4b5633568df9adc13f1515c8d26c44126ad87c97` |

TDK B82726S2203A020 is a URL + hash record in
`../inputs/tdk-source.json`; the vendor PDF is not redistributed here.
