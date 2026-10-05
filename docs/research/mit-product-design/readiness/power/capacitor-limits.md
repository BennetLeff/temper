# Exact resonant-capacitor limit record

**Application qualification: unresolved.** C21/C22 are `942C12P22K-F` (two 0.22 µF); C23 is `942C12P1K-F` (one 0.10 µF). The 0.54 µF nominal bank is unchanged.

Source: [CDE 942C catalogue](https://www.cde.com/resources/catalogs/942C.pdf), saved manufacturer document SHA-256 `f99395446ba25a0adcef85862ff9eaee90bac68fae6664decccab1ebea3e4310`; `ps-oracle/.../05-resonant-tank-envelope/sources/942C.pdf`. Fresh retrieval on 2026-10-04 returned HTTP 403. The following transcribes facts from printed pp. 1,3–4, not a claim that a supplier confirmed the application.

| Parameter | 942C12P22K-F | 942C12P1K-F | Catalogue condition |
| --- | ---: | ---: | --- |
| Capacitance | 0.22 µF ±10% | 0.10 µF ±10% | Selected K tolerance |
| DC voltage | 1200 V | 1200 V | Full rated voltage at 85 °C; linear derating to half at 105 °C |
| AC voltage label | 430 V RMS | 430 V RMS | 60 Hz; not a 20–60 kHz operating allowance |
| RMS current row | 10.3 A | 9.2 A | 70 °C, 100 kHz |
| Typical ESR | 6 mΩ | 5 mΩ | Typical catalogue values, no hot guaranteed function supplied |
| Typical ESL | 26 nH | 23 nH | Component values; lead/board installation adds parasitics |
| dV/dt | 2854 V/µs | 2854 V/µs | Repetitive application/temperature qualification still required |
| Peak current row | 628 A | 285 A | Not a continuous current allowance |
| Body / lead diameter | 26.5 ×34 mm /1.2 mm | 19 ×34 mm /1.0 mm | Formed 42.5 mm pitch not manufacturer-approved by this table |

At the previously assumed **18.7 A bank RMS**, ideal capacitance sharing predicts 7.62/7.62/3.46 A. Independent ±10% corners raise each part's separate maximum to 8.54 A (0.22 µF) and 4.07 A (0.10 µF); those maxima are not simultaneous. This arithmetic is already in the supplier brief and is not a qualified operating point. Neither comparing those numbers with the 100 kHz row nor comparing a waveform peak with 1200 Vdc proves suitability.

The catalogue's 25 °C frequency curves omit the exact 0.22 µF variant. No guaranteed hot ESR/DF or installed thermal resistance is supplied. Therefore a safe current-vs-frequency function cannot be reconstructed from these rows. The old 650 V peak screen remains unqualified.

The remaining supplier/application questions can be reduced to three deliverables, using the existing [unsent request](supplier-questions.md):

1. Exact-part simultaneous **RMS current, AC RMS/peak voltage, dV/dt and lifetime limits** versus 20–60 kHz and ambient/case/hotspot temperature, with harmonic/burst and line-envelope treatment.
2. A bounded **ESR/ESL/thermal model** and acceptable branch-sharing/temperature evidence for the installed bank.
3. Approval of the actual **lead form, restraint, PCB clearance and mounting process**, or exact alternatives plus those limits.

Measure actual per-branch current, capacitor voltage and temperature on the first unit. Use the cold coil/pan fixture to define representative impedances before selecting controller limits; it cannot validate capacitor heating or high-current coil nonlinearity.
